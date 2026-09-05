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

"""Policy and policy-version endpoints.

Versions are append-only. There is deliberately no endpoint that mutates an existing
``PolicyVersion`` — editing a policy means publishing a new version (D2).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import fetch_or_404, get_db
from app.api.schemas import (
    PolicyClone,
    PolicyCreate,
    PolicyRead,
    PolicyVersionCreate,
    PolicyVersionRead,
)
from app.db.models import Policy, PolicyVersion
from app.policies.registry import PolicyTypeError, registry
from app.security.admin_auth import AdminIdentity, admin_required
from app.services import effective_policy as eff
from app.services import policy_admin

router = APIRouter(prefix="/api/v1/policies", tags=["policies"])


def _validated_spec(policy_type: str, spec: dict) -> dict:
    try:
        return registry.validate_spec(policy_type, spec)
    except PolicyTypeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.post("", response_model=PolicyRead, status_code=status.HTTP_201_CREATED)
def create_policy(payload: PolicyCreate, session: Session = Depends(get_db)) -> Policy:
    spec = _validated_spec(payload.policy_type, payload.spec)

    policy = Policy(
        name=payload.name,
        policy_type=payload.policy_type,
        description=payload.description,
        is_template=payload.is_template,
    )
    policy.versions.append(PolicyVersion(version=1, spec=spec, notes=payload.notes))
    session.add(policy)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"a policy named {payload.name!r} already exists"
        ) from exc
    return policy


@router.get("", response_model=list[PolicyRead])
def list_policies(
    policy_type: str | None = None,
    include_archived: bool = False,
    include_sections: bool = False,
    session: Session = Depends(get_db),
) -> list[Policy]:
    stmt = select(Policy).order_by(Policy.name)
    if policy_type:
        stmt = stmt.where(Policy.policy_type == policy_type)
    if not include_archived:
        stmt = stmt.where(Policy.archived_at.is_(None))
    if not include_sections:
        # Sections of a profile are managed through the profile.
        stmt = stmt.where(Policy.profile_id.is_(None))
    return list(session.scalars(stmt))


@router.get("/{policy_id}", response_model=PolicyRead)
def get_policy(policy_id: uuid.UUID, session: Session = Depends(get_db)) -> Policy:
    return fetch_or_404(session, Policy, policy_id, "policy")


@router.post(
    "/{policy_id}/versions",
    response_model=PolicyVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def publish_version(
    policy_id: uuid.UUID,
    payload: PolicyVersionCreate,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> PolicyVersion:
    policy: Policy = fetch_or_404(session, Policy, policy_id, "policy")
    spec = _validated_spec(policy.policy_type, payload.spec)

    latest = policy.latest_version
    version = PolicyVersion(
        policy_id=policy.id,
        version=(latest.version + 1) if latest else 1,
        spec=spec,
        notes=payload.notes,
        published_by=None if identity.is_anonymous else identity.username,
    )
    session.add(version)
    session.flush()

    # Assignments tracking "latest" now resolve differently for every device the
    # policy reaches.
    eff.invalidate_for_policy(session, policy.id)
    session.commit()
    return version


@router.post("/{policy_id}/archive", response_model=PolicyRead)
def archive_policy(policy_id: uuid.UUID, session: Session = Depends(get_db)) -> Policy:
    """Stop a policy applying without destroying the history of what it once set."""
    fetch_or_404(session, Policy, policy_id, "policy")
    policy = policy_admin.archive(session, policy_id)
    session.commit()
    return policy


@router.post("/{policy_id}/restore", response_model=PolicyRead)
def restore_policy(policy_id: uuid.UUID, session: Session = Depends(get_db)) -> Policy:
    """Un-archive a policy. It may reach devices again immediately (D20)."""
    fetch_or_404(session, Policy, policy_id, "policy")
    policy = policy_admin.restore(session, policy_id)
    session.commit()
    return policy


@router.delete(
    "/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    # Explicit: FastAPI would otherwise infer a response model from the `-> None`
    # return annotation, and a 204 is not allowed to carry a body.
    response_model=None,
)
def delete_policy(policy_id: uuid.UUID, session: Session = Depends(get_db)) -> None:
    """Permanently remove an archived policy and every version it ever published.

    **Archiving is the normal answer** — the standing instinct is to archive
    rather than delete (D20), because what a device once had stays answerable.
    This exists for policies that never reached a device: a mis-clicked clone, or
    something built while learning the console.

    Requires the policy to be archived first, which makes deletion two deliberate
    acts rather than one misplaced click — and means no device's effective state
    can move, since the resolver already skips an archived policy.
    """
    fetch_or_404(session, Policy, policy_id, "policy")
    try:
        policy_admin.delete(session, policy_id)
    except policy_admin.PolicyAdminError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    session.commit()


@router.post(
    "/{policy_id}/clone",
    response_model=PolicyRead,
    status_code=status.HTTP_201_CREATED,
)
def clone_policy(
    policy_id: uuid.UUID,
    payload: PolicyClone,
    session: Session = Depends(get_db),
    identity: AdminIdentity = Depends(admin_required),
) -> Policy:
    """Copy a policy or template into a new, independent policy.

    Both "save as template" (`as_template=true`) and "use template"
    (`as_template=false`) are this one operation.
    """
    fetch_or_404(session, Policy, policy_id, "policy")
    try:
        policy = policy_admin.clone(
            session,
            policy_id,
            name=payload.name,
            as_template=payload.as_template,
            published_by=None if identity.is_anonymous else identity.username,
        )
    except policy_admin.PolicyAdminError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"a policy named {payload.name!r} already exists"
        ) from exc
    return policy
