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

"""Profile endpoints — the composite "policy" (DW5).

Assignment lives in W4b; this router covers creating a profile, editing its
sections, and archiving.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from sqlalchemy import select

from app.api.deps import fetch_or_404, get_db
from app.api.schemas import (
    PolicyTargets,
    PolicyTargetsResult,
    ProfileCreate,
    ProfileRead,
    ProfileSectionUpsert,
)
from app.db.models import (
    AssignmentScope,
    Device,
    DeviceGroup,
    PolicyProfile,
    ProfileAssignment,
)
from app.security.admin_auth import AdminIdentity, admin_required
from app.services import effective_policy as eff
from app.services import profiles as profile_service

router = APIRouter(prefix="/api/v1/profiles", tags=["profiles"])

_TARGET_MODELS = {
    AssignmentScope.DEVICE: (Device, "device", "device_id"),
    AssignmentScope.GROUP: (DeviceGroup, "group", "group_id"),
}


def _get(session: Session, profile_id: uuid.UUID) -> PolicyProfile:
    profile = profile_service.get_profile(session, profile_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "profile not found")
    return profile


@router.get("", response_model=list[ProfileRead])
def list_profiles(
    include_archived: bool = False, session: Session = Depends(get_db)
) -> list[PolicyProfile]:
    return profile_service.list_profiles(session, include_archived=include_archived)


@router.post("", response_model=ProfileRead, status_code=status.HTTP_201_CREATED)
def create_profile(
    payload: ProfileCreate,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> PolicyProfile:
    try:
        profile = profile_service.create_profile(
            session,
            name=payload.name,
            description=payload.description,
            sections=payload.sections,
            created_by=None if identity.is_anonymous else identity.username,
        )
    except profile_service.ProfileError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"a profile or policy named {payload.name!r} already exists",
        ) from exc
    return profile


@router.get("/{profile_id}", response_model=ProfileRead)
def get_profile(profile_id: uuid.UUID, session: Session = Depends(get_db)) -> PolicyProfile:
    return _get(session, profile_id)


@router.put("/{profile_id}/sections/{category_key}", response_model=ProfileRead)
def upsert_section(
    profile_id: uuid.UUID,
    category_key: str,
    payload: ProfileSectionUpsert,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> PolicyProfile:
    profile = _get(session, profile_id)
    try:
        profile_service.upsert_section(
            session,
            profile,
            category_key,
            payload.spec,
            published_by=None if identity.is_anonymous else identity.username,
        )
    except profile_service.ProfileError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    session.commit()
    return profile


@router.delete("/{profile_id}/sections/{category_key}", response_model=ProfileRead)
def remove_section(
    profile_id: uuid.UUID,
    category_key: str,
    session: Session = Depends(get_db),
) -> PolicyProfile:
    profile = _get(session, profile_id)
    try:
        profile_service.remove_section(session, profile, category_key)
    except profile_service.ProfileError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    session.commit()
    return profile


@router.put("/{profile_id}/targets", response_model=PolicyTargetsResult)
def set_profile_targets(
    profile_id: uuid.UUID,
    payload: PolicyTargets,
    session: Session = Depends(get_db),
) -> PolicyTargetsResult:
    """Assign one profile to many devices / groups / tags in a single call (F2).

    ``mode="replace"`` (the default) makes the request describe the profile's
    complete target set, so unticking a box unassigns.
    """
    profile = _get(session, profile_id)

    requested: set[tuple[AssignmentScope, uuid.UUID]] = set()
    for scope, ids in (
        (AssignmentScope.DEVICE, payload.device_ids),
        (AssignmentScope.GROUP, payload.group_ids),
    ):
        target_model, label, _ = _TARGET_MODELS[scope]
        for target_id in ids:
            fetch_or_404(session, target_model, target_id, label)
            requested.add((scope, target_id))

    existing = {
        (a.scope, a.device_id or a.group_id): a
        for a in session.scalars(
            select(ProfileAssignment).where(ProfileAssignment.profile_id == profile.id)
        )
    }

    affected: set[uuid.UUID] = set()
    created = removed = unchanged = 0

    if payload.mode == "replace":
        for key, assignment in existing.items():
            if key not in requested:
                affected |= eff.devices_targeted_by_profile_assignment(session, assignment)
                session.delete(assignment)
                removed += 1

    for scope, target_id in sorted(
        requested, key=lambda item: (item[0].value, str(item[1]))
    ):
        if (scope, target_id) in existing:
            existing[(scope, target_id)].rank = payload.rank
            affected |= eff.devices_targeted_by_profile_assignment(
                session, existing[(scope, target_id)]
            )
            unchanged += 1
            continue
        _, _, column = _TARGET_MODELS[scope]
        assignment = ProfileAssignment(
            profile_id=profile.id, scope=scope, rank=payload.rank, **{column: target_id}
        )
        session.add(assignment)
        session.flush()
        affected |= eff.devices_targeted_by_profile_assignment(session, assignment)
        created += 1

    session.flush()
    eff.invalidate(session, affected)
    session.commit()

    return PolicyTargetsResult(
        policy_id=profile.id,
        created=created,
        removed=removed,
        unchanged=unchanged,
        devices_affected=len(affected),
    )


@router.post("/{profile_id}/archive", response_model=ProfileRead)
def archive_profile(profile_id: uuid.UUID, session: Session = Depends(get_db)) -> PolicyProfile:
    profile = _get(session, profile_id)
    profile_service.archive(session, profile)
    session.commit()
    return profile


@router.post("/{profile_id}/restore", response_model=ProfileRead)
def restore_profile(profile_id: uuid.UUID, session: Session = Depends(get_db)) -> PolicyProfile:
    profile = _get(session, profile_id)
    profile_service.restore(session, profile)
    session.commit()
    return profile


@router.delete(
    "/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    # Explicit: FastAPI would otherwise infer a response model from the `-> None`
    # return annotation, and a 204 is not allowed to carry a body.
    response_model=None,
)
def delete_profile(profile_id: uuid.UUID, session: Session = Depends(get_db)) -> None:
    """Permanently remove an archived policy, its sections and all their history.

    **Archiving is the normal answer** — the project's standing instinct is to
    archive rather than delete (D20), and an archived policy is already off every
    device. This is for the ones that never reached a device and whose history
    answers nothing.

    Requires the policy to be archived first. That makes deletion two deliberate
    acts, and it also means nothing a device sees can change here: archiving
    already dropped the assignments and the resolver already skips it.
    """
    profile = _get(session, profile_id)
    try:
        profile_service.delete(session, profile)
    except profile_service.ProfileError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    session.commit()
