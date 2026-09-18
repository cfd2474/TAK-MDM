# Copyright 2026 TAK-Solutions LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Policy list-management: the tabs, templates, archive and restore.

A template and a policy are the same row with `is_template` flipped — a template
is just a blueprint that never reaches a device. "Save as template" and "Use
template" are therefore both *clones*: editing a policy must never retroactively
change the template it came from, and vice versa.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Assignment, Policy, PolicyVersion
from app.services import effective_policy as eff


class PolicyAdminError(Exception):
    """A requested list-management action cannot be performed."""


def list_tab(session: Session, tab: str) -> list[Policy]:
    """Policies for one console tab: 'device', 'templates', or 'archived'."""
    # Sections of a profile are managed through the profile, never listed as
    # standalone policies.
    stmt = select(Policy).where(Policy.profile_id.is_(None)).order_by(Policy.name)
    if tab == "device":
        stmt = stmt.where(Policy.archived_at.is_(None), Policy.is_template.is_(False))
    elif tab == "templates":
        stmt = stmt.where(Policy.archived_at.is_(None), Policy.is_template.is_(True))
    elif tab == "archived":
        stmt = stmt.where(Policy.archived_at.is_not(None))
    else:  # pragma: no cover - guarded by the route
        raise PolicyAdminError(f"unknown tab {tab!r}")
    return list(session.scalars(stmt))


def clone(
    session: Session,
    source_id: uuid.UUID,
    *,
    name: str,
    as_template: bool,
    published_by: str | None = None,
) -> Policy:
    """Copy a policy's type, description and latest spec into a fresh policy.

    The clone starts at v1 with no history of its own — it is a new policy, not a
    continuation of the source.
    """
    source = session.get(Policy, source_id)
    if source is None:
        raise PolicyAdminError("policy not found")

    latest = source.latest_version
    spec = dict(latest.spec) if latest else {}

    policy = Policy(
        name=name.strip(),
        policy_type=source.policy_type,
        description=source.description,
        is_template=as_template,
    )
    policy.versions.append(
        PolicyVersion(version=1, spec=spec, published_by=published_by)
    )
    session.add(policy)
    session.flush()
    return policy


def archive(session: Session, policy_id: uuid.UUID) -> Policy:
    policy = session.get(Policy, policy_id)
    if policy is None:
        raise PolicyAdminError("policy not found")
    if policy.archived_at is None:
        policy.archived_at = datetime.now(timezone.utc)
        eff.invalidate_for_policy(session, policy.id)
    return policy


def restore(session: Session, policy_id: uuid.UUID) -> Policy:
    policy = session.get(Policy, policy_id)
    if policy is None:
        raise PolicyAdminError("policy not found")
    if policy.archived_at is not None:
        policy.archived_at = None
        # It may reach devices again the moment it is un-archived.
        eff.invalidate_for_policy(session, policy.id)
    return policy


def drop_assignments(session: Session, policy_id: uuid.UUID) -> None:
    """Remove every assignment of a policy, ahead of deleting the policy itself.

    The database would cascade these away on its own, but not safely:
    ``Assignment.pinned_version_id`` references ``policy_version`` with ON DELETE
    **RESTRICT**, while both ``Assignment.policy_id`` and
    ``PolicyVersion.policy_id`` are ON DELETE CASCADE. Deleting a policy therefore
    fans out into two tables in an order no database promises, and if the versions
    go first the RESTRICT fires. Clearing the referencing rows here removes the
    race rather than betting on it.
    """
    for assignment in session.scalars(
        select(Assignment).where(Assignment.policy_id == policy_id)
    ):
        session.delete(assignment)
    session.flush()


def delete(session: Session, policy_id: uuid.UUID) -> None:
    """Destroy an archived policy and its entire version history, permanently.

    A deliberate exception to D20, which says archived policies are never deleted.
    That still holds as the default — archiving is the one-click action and this is
    only reachable from an already-archived policy — but it does not serve the
    policies that were never on a device and whose history answers nothing.

    Gating on ``archived_at`` does two jobs. It makes deletion two deliberate acts
    rather than one misplaced click, the same shape as retire-before-delete for a
    device; and it makes the delete *inert for the fleet*, because an archived
    policy is already skipped by the resolver. No device's effective state can
    move, so there is nothing to invalidate and no one to wake.
    """
    policy = session.get(Policy, policy_id)
    if policy is None:
        raise PolicyAdminError("policy not found")
    if policy.archived_at is None:
        raise PolicyAdminError(
            "archive the policy before deleting it: deletion is permanent and "
            "destroys its version history, so it is deliberately two steps"
        )
    if policy.profile_id is not None:
        # A section is part of a whole. Deleting one on its own would leave the
        # profile with a hole in it that the editor has no way to show.
        raise PolicyAdminError(
            "this policy is a section of a policy profile; delete the profile instead"
        )

    drop_assignments(session, policy.id)
    session.delete(policy)  # versions follow by cascade
    session.flush()
