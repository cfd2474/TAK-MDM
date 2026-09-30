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
from app.policies import fence_rules
from app.policies.registry import PolicyTypeError, registry
from app.services import effective_policy as eff
from app.services import policy_admin


class ProfileError(Exception):
    """A profile operation cannot be completed."""


#: Profile names this system owns, and what each one is for.
#:
#: Declared here rather than imported from the services that own them, because
#: importing `breach` from this module is a cycle: it creates its profile
#: through `create_profile`.
RESERVED_NAMES: dict[str, str] = {
    "Breach mode": "breach-mode policy",
}


def is_reserved(profile: PolicyProfile) -> bool:
    """Is this one of the profiles the system manages for itself?"""
    return profile.name in RESERVED_NAMES


def exclude_reserved(stmt):
    """Filter a `PolicyProfile` select down to the ones operators own.

    ⚠️ Shared rather than repeated, because there are three query sites and a
    missed one does not fail — it offers the breach profile in a dropdown, where
    a single click applies it to a whole group.
    """
    return stmt.where(PolicyProfile.name.not_in(list(RESERVED_NAMES)))


def refuse_if_reserved(profile: PolicyProfile) -> None:
    """Raise if this profile is not an operator's to assign or edit.

    ⚠️ The lists and pickers hide it; this is what makes hiding it a control
    rather than a decoration. A hidden option is still a `POST` away for anyone
    who knows the id, and the breach profile applied to a group would strip
    every policy from every device in it.
    """
    if is_reserved(profile):
        raise ProfileError(
            f"{profile.name!r} is managed by ATLAS and is applied automatically. "
            f"It cannot be assigned or edited here."
        )


def list_profiles(
    session: Session,
    *,
    include_archived: bool = False,
    include_reserved: bool = False,
) -> list[PolicyProfile]:
    """Profiles an operator owns, newest rules first.

    ⚠️ `include_reserved` defaults to **False**, so a caller that has not
    thought about it gets the safe answer. The one page that wants the breach
    profile asks for it by name instead.
    """
    stmt = select(PolicyProfile).order_by(PolicyProfile.name)
    if not include_archived:
        stmt = stmt.where(PolicyProfile.archived_at.is_(None))
    if not include_reserved:
        stmt = exclude_reserved(stmt)
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


def _latest_spec(session: Session, profile: PolicyProfile) -> dict | None:
    """The tracking section's newest spec, read from the database.

    ⚠️ **Not `section.latest_version`.** That reads the relationship collection,
    which `upsert_section` does not refresh — it adds a `PolicyVersion` by id
    rather than appending to `child.versions`. So immediately after an operator
    releases a fence's password requirement, the relationship still reports the
    previous version, and removing the Password section would be refused on the
    strength of a spec that is no longer current. Found by the test that releases
    and then removes.
    """
    tracking = section_for(profile, fence_rules.TRACKING_KEY)
    if tracking is None:
        return None
    row = session.scalars(
        select(PolicyVersion)
        .where(PolicyVersion.policy_id == tracking.id)
        .order_by(PolicyVersion.version.desc())
        .limit(1)
    ).first()
    return row.spec if row else None


def _sections_after(
    profile: PolicyProfile, category_key: str, spec: dict
) -> dict[str, dict]:
    """The profile's sections with one replaced - what a save is about to make true."""
    out: dict[str, dict] = {}
    for section in profile.sections:
        if section.profile_section and section.latest_version:
            out[section.profile_section] = section.latest_version.spec
    out[category_key] = spec
    return out


def create_profile(
    session: Session,
    *,
    name: str,
    description: str | None,
    sections: dict[str, dict],
    created_by: str | None = None,
    reserved: bool = False,
) -> PolicyProfile:
    """Create a profile and a child policy for every non-empty wired section.

    `sections` maps a catalog category key to its raw spec. Empty specs are
    skipped — a section is only created once it has something in it.

    `reserved` is for the profiles this system owns, and only `app.services`
    passes it — see the refusal below.
    """
    name = name.strip()
    if not name:
        raise ProfileError("a profile needs a name")

    # ⚠️ **A reserved name is refused, because it is looked up by name.**
    # `breach.profile()` finds the breach profile by its name — it is created on
    # first use, so there is no id to hard-code. An operator who created an
    # ordinary profile called "Breach mode" would therefore have built, without
    # any way of knowing it, the policy that every breached device receives.
    #
    # The refusal names the reason rather than saying "that name is taken",
    # which would be a lie about a profile that does not exist yet.
    if not reserved and name in RESERVED_NAMES:
        raise ProfileError(
            f"{name!r} is reserved for the {RESERVED_NAMES[name]} this system "
            f"manages for you. Pick another name."
        )

    # ⚠️ Across sections, before any of them is written. A geofence may only
    # demand a lock the operator has actually defined - see `fence_rules`.
    refusal = fence_rules.check_sections(sections)
    if refusal:
        raise ProfileError(refusal)

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

    # ⚠️ Judged against the profile as it *will* be, not as it is: this section
    # is the one being changed, so reading it back from the database would check
    # the previous version and let the new one through.
    refusal = fence_rules.check_sections(_sections_after(profile, category_key, spec))
    if refusal:
        raise ProfileError(refusal)

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

    # ⚠️ Removing the Password section can strand a geofence that requires one.
    # This is the check that looks unnecessary and is not: every other one runs
    # while the operator is looking at geofences, and this one fires from a
    # different tab, with the thing it protects nowhere on screen.
    if category_key == fence_rules.PASSWORD_KEY:
        refusal = fence_rules.blocks_password_removal(_latest_spec(session, profile))
        if refusal:
            raise ProfileError(refusal)
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


def delete(session: Session, profile: PolicyProfile) -> None:
    """Destroy an archived profile, every section it owns, and all their history.

    Gated on ``archived_at`` for the same two reasons as
    :func:`app.services.policy_admin.delete`: deletion becomes two deliberate acts,
    and an archived profile is already off the fleet — :func:`archive` dropped its
    assignments — so nothing a device sees can change when it goes.

    Sections and their versions follow by cascade. Their *assignments* do not go
    that way on purpose; see :func:`app.services.policy_admin.drop_assignments`
    for why leaving that to the database is unsafe.
    """
    if profile.archived_at is None:
        raise ProfileError(
            "archive the policy before deleting it: deletion is permanent and "
            "destroys its version history, so it is deliberately two steps"
        )
    for section in list(profile.sections):
        policy_admin.drop_assignments(session, section.id)
    session.delete(profile)
    session.flush()
