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

"""Profile management — the composite "policy" the operator builds (DW5).

A profile owns one single-concern ``Policy`` per configured category. This module
is the only place those child policies are created or versioned, so the naming
convention and the section↔category link live in one spot.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Policy, PolicyProfile, PolicyVersion, ProfileAssignment
from app.policies import creator_catalog
from app.policies.registry import PolicyTypeError, registry
from app.services import effective_policy as eff


class ProfileError(Exception):
    """A profile operation cannot be completed."""


def list_profiles(session: Session, *, include_archived: bool = False) -> list[PolicyProfile]:
    stmt = select(PolicyProfile).order_by(PolicyProfile.name)
    if not include_archived:
        stmt = stmt.where(PolicyProfile.archived_at.is_(None))
    return list(session.scalars(stmt))


def get_profile(session: Session, profile_id: uuid.UUID) -> PolicyProfile | None:
    return session.get(PolicyProfile, profile_id)


def section_for(profile: PolicyProfile, category_key: str) -> Policy | None:
    return next(
        (p for p in profile.sections if p.profile_section == category_key), None
    )


def _child_name(profile_name: str, category: creator_catalog.Category) -> str:
    return f"{profile_name} · {category.label}"


def _validate(category: creator_catalog.Category, spec: dict) -> dict:
    try:
        return registry.validate_spec(category.policy_type, spec)
    except PolicyTypeError as exc:
        raise ProfileError(f"{category.label}: {exc}") from exc


def create_profile(
    session: Session,
    *,
    name: str,
    description: str | None,
    sections: dict[str, dict],
    created_by: str | None = None,
) -> PolicyProfile:
    """Create a profile and a child policy for every non-empty wired section.

    `sections` maps a catalog category key to its raw spec. Empty specs are
    skipped — a section is only created once it has something in it.
    """
    name = name.strip()
    if not name:
        raise ProfileError("a profile needs a name")

    profile = PolicyProfile(name=name, description=(description or None), created_by=created_by)
    session.add(profile)

    for key, spec in sections.items():
        category = creator_catalog.get(key)
        if category is None or not category.wired:
            continue
        if not spec:
            continue
        validated = _validate(category, spec)
        child = Policy(
            name=_child_name(name, category),
            policy_type=category.policy_type,
            profile_section=key,
            description=f"Section of profile {name!r}",
        )
        child.versions.append(
            PolicyVersion(version=1, spec=validated, published_by=created_by)
        )
        profile.sections.append(child)

    session.flush()
    return profile


def upsert_section(
    session: Session,
    profile: PolicyProfile,
    category_key: str,
    spec: dict,
    *,
    published_by: str | None = None,
) -> Policy | None:
    """Create the section, or publish a new version of it. Empty spec is a no-op
    (removing a section is a separate, deliberate action)."""
    category = creator_catalog.get(category_key)
    if category is None or not category.wired:
        raise ProfileError(f"unknown or unwired category {category_key!r}")
    if not spec:
        return None

    validated = _validate(category, spec)
    child = section_for(profile, category_key)

    if child is None:
        child = Policy(
            name=_child_name(profile.name, category),
            policy_type=category.policy_type,
            profile_section=category_key,
            description=f"Section of profile {profile.name!r}",
        )
        child.versions.append(
            PolicyVersion(version=1, spec=validated, published_by=published_by)
        )
        profile.sections.append(child)
        session.flush()
        return child

    latest = child.latest_version
    if latest and latest.spec == validated:
        return child  # nothing changed

    session.add(
        PolicyVersion(
            policy_id=child.id,
            version=(latest.version + 1) if latest else 1,
            spec=validated,
            published_by=published_by,
        )
    )
    session.flush()
    eff.invalidate_for_policy(session, child.id)
    return child


def remove_section(session: Session, profile: PolicyProfile, category_key: str) -> None:
    child = section_for(profile, category_key)
    if child is None:
        return
    affected = eff.devices_affected_by_policy(session, child.id)
    profile.sections.remove(child)
    session.flush()
    eff.invalidate(session, affected)


def archive(session: Session, profile: PolicyProfile) -> None:
    """Archive the profile and take it off every device it was on.

    The assignment rows are deleted, not just ignored: 'archived' should mean the
    policy is genuinely off the fleet, and restoring it should not silently push
    it back out. History (the profile and its section versions) is kept.
    """
    if profile.archived_at is not None:
        return
    affected = eff.devices_affected_by_profile(session, profile.id)
    profile.archived_at = datetime.now(timezone.utc)
    for pa in session.scalars(
        select(ProfileAssignment).where(ProfileAssignment.profile_id == profile.id)
    ):
        session.delete(pa)
    session.flush()
    eff.invalidate(session, affected)


def restore(session: Session, profile: PolicyProfile) -> None:
    """Un-archive. The profile comes back assigned to nothing — archiving dropped
    its assignments — so it reaches no device until it is assigned again."""
    if profile.archived_at is None:
        return
    profile.archived_at = None
    session.flush()
    eff.invalidate_for_profile(session, profile.id)
