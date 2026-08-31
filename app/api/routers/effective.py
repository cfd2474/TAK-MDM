"""Effective-policy endpoints: the resolved answer, and the dry run before you commit."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import fetch_or_404, get_db, require_device
from app.api.schemas import PreviewRequest
from app.db.models import Device, Policy
from app.policies.resolver import AssignmentInput, PolicySnapshot
from app.services import effective_policy as eff

router = APIRouter(prefix="/api/v1/devices", tags=["effective-policy"])


@router.get("/{device_id}/effective-policy")
def get_effective_policy(
    device: Device = Depends(require_device), session: Session = Depends(get_db)
) -> dict[str, Any]:
    """Merged policy for this device, with per-field provenance and conflicts."""
    payload = eff.get_effective(session, device)
    session.commit()  # persist a freshly computed cache row and any state_version bump
    return {"state_version": device.state_version, **payload}


@router.get("/{device_id}/effective-policy/explain/{policy_type}/{field_name}")
def explain_field(
    policy_type: str,
    field_name: str,
    device: Device = Depends(require_device),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Why does this one field hold this value? The question stacking makes hard."""
    payload = eff.get_effective(session, device)
    session.commit()

    record = payload.get("provenance", {}).get(policy_type, {}).get(field_name)
    if record is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"no resolved value for {policy_type}.{field_name} on this device",
        )
    return {"policy_type": policy_type, "field": field_name, **record}


@router.post("/{device_id}/effective-policy/preview")
def preview_effective_policy(
    payload: PreviewRequest,
    device: Device = Depends(require_device),
    session: Session = Depends(get_db),
) -> dict[str, Any]:
    """Resolve a hypothetical assignment set. Writes nothing."""
    drafts: list[AssignmentInput] = []

    for index, draft in enumerate(payload.add):
        policy: Policy = fetch_or_404(session, Policy, draft.policy_id, "policy")

        if draft.pinned_version is not None:
            version = next(
                (v for v in policy.versions if v.version == draft.pinned_version), None
            )
        else:
            version = policy.latest_version

        if version is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"policy {policy.name!r} has no published version to preview",
            )

        drafts.append(
            AssignmentInput(
                # Synthetic id, marked so it is obvious in provenance that this
                # assignment does not exist yet.
                assignment_id=f"draft-{index}",
                scope=draft.scope,
                rank=draft.rank,
                policy=PolicySnapshot(
                    policy_id=str(policy.id),
                    policy_name=policy.name,
                    policy_type=policy.policy_type,
                    version=version.version,
                    spec=version.spec or {},
                ),
            )
        )

    return eff.preview(
        session,
        device,
        add=drafts,
        remove_assignment_ids=payload.remove_assignment_ids,
    )
