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
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import fetch_or_404, get_db
from app.api.schemas import PolicyCreate, PolicyRead, PolicyVersionCreate, PolicyVersionRead
from app.db.models import Policy, PolicyVersion
from app.policies.registry import PolicyTypeError, registry
from app.services import effective_policy as eff

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
    session: Session = Depends(get_db),
) -> list[Policy]:
    stmt = select(Policy).order_by(Policy.name)
    if policy_type:
        stmt = stmt.where(Policy.policy_type == policy_type)
    if not include_archived:
        stmt = stmt.where(Policy.archived_at.is_(None))
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
) -> PolicyVersion:
    policy: Policy = fetch_or_404(session, Policy, policy_id, "policy")
    spec = _validated_spec(policy.policy_type, payload.spec)

    latest = policy.latest_version
    version = PolicyVersion(
        policy_id=policy.id,
        version=(latest.version + 1) if latest else 1,
        spec=spec,
        notes=payload.notes,
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
    policy: Policy = fetch_or_404(session, Policy, policy_id, "policy")
    if policy.archived_at is None:
        policy.archived_at = datetime.now(timezone.utc)
        eff.invalidate_for_policy(session, policy.id)
        session.commit()
    return policy
