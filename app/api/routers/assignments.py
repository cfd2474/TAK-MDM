"""Assignment endpoints — where policies get stacked onto targets."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import fetch_or_404, get_db
from app.api.schemas import AssignmentCreate, AssignmentRead, AssignmentUpdate
from app.db.models import Assignment, AssignmentScope, Device, DeviceGroup, Policy, Tag
from app.services import effective_policy as eff

router = APIRouter(prefix="/api/v1/assignments", tags=["assignments"])

_TARGET_MODELS = {
    AssignmentScope.DEVICE: (Device, "device", "device_id"),
    AssignmentScope.GROUP: (DeviceGroup, "group", "group_id"),
    AssignmentScope.TAG: (Tag, "tag", "tag_id"),
}


def _to_read(assignment: Assignment) -> AssignmentRead:
    target_id = assignment.device_id or assignment.group_id or assignment.tag_id
    return AssignmentRead(
        id=assignment.id,
        policy_id=assignment.policy_id,
        policy_name=assignment.policy.name,
        policy_type=assignment.policy.policy_type,
        scope=assignment.scope.value,
        target_id=target_id,
        rank=assignment.rank,
        enabled=assignment.enabled,
        pinned_version=(
            assignment.pinned_version.version if assignment.pinned_version else None
        ),
    )


@router.post("", response_model=AssignmentRead, status_code=status.HTTP_201_CREATED)
def create_assignment(
    payload: AssignmentCreate, session: Session = Depends(get_db)
) -> AssignmentRead:
    policy: Policy = fetch_or_404(session, Policy, payload.policy_id, "policy")

    scope = AssignmentScope(payload.scope)
    target_model, label, target_column = _TARGET_MODELS[scope]
    fetch_or_404(session, target_model, payload.target_id, label)

    pinned = None
    if payload.pinned_version is not None:
        pinned = next(
            (v for v in policy.versions if v.version == payload.pinned_version), None
        )
        if pinned is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"policy {policy.name!r} has no version {payload.pinned_version}",
            )

    assignment = Assignment(
        policy_id=policy.id,
        scope=scope,
        rank=payload.rank,
        enabled=payload.enabled,
        pinned_version_id=pinned.id if pinned else None,
        **{target_column: payload.target_id},
    )
    session.add(assignment)
    session.flush()

    eff.invalidate_for_assignment(session, assignment)
    session.commit()
    return _to_read(assignment)


@router.get("", response_model=list[AssignmentRead])
def list_assignments(
    device_id: uuid.UUID | None = None,
    policy_id: uuid.UUID | None = None,
    session: Session = Depends(get_db),
) -> list[AssignmentRead]:
    """List assignments. Filtering by device resolves group and tag membership."""
    stmt = select(Assignment)
    if policy_id:
        stmt = stmt.where(Assignment.policy_id == policy_id)

    assignments = list(session.scalars(stmt))

    if device_id:
        device = fetch_or_404(session, Device, device_id, "device")
        reaching = {a.assignment_id for a in eff.gather_assignments(session, device)}
        assignments = [a for a in assignments if str(a.id) in reaching]

    assignments.sort(key=lambda a: (-a.rank, a.policy.name))
    return [_to_read(a) for a in assignments]


@router.patch("/{assignment_id}", response_model=AssignmentRead)
def update_assignment(
    assignment_id: uuid.UUID,
    payload: AssignmentUpdate,
    session: Session = Depends(get_db),
) -> AssignmentRead:
    assignment: Assignment = fetch_or_404(session, Assignment, assignment_id, "assignment")

    updates = payload.model_dump(exclude_unset=True)
    for attribute, value in updates.items():
        setattr(assignment, attribute, value)

    if updates:
        eff.invalidate_for_assignment(session, assignment)
    session.commit()
    return _to_read(assignment)


@router.delete(
    "/{assignment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    # Explicit: FastAPI would otherwise infer NoneType from the return annotation,
    # which is truthy and trips its "204 must not have a body" assertion.
    response_model=None,
    response_class=Response,
)
def delete_assignment(assignment_id: uuid.UUID, session: Session = Depends(get_db)) -> None:
    assignment: Assignment = fetch_or_404(session, Assignment, assignment_id, "assignment")

    # Resolve the affected devices before the row is gone.
    affected = eff.devices_targeted_by(session, assignment)
    session.delete(assignment)
    session.flush()

    eff.invalidate(session, affected)
    session.commit()
