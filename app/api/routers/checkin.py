"""Device-facing check-in, authenticated by mTLS.

A deliberate stub: it proves identity (Chunk 2) and the policy engine (Chunk 1) are
connected, and establishes the ``state_version`` handshake. The full desired-state
protocol — signed policy bundles, transient command queue, artifact URLs — is
Chunk 3.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import authenticated_device, get_db
from app.api.schemas import CheckinRequest, CheckinResponse
from app.db.models import Device
from app.services import effective_policy as eff

router = APIRouter(prefix="/api/v1/device", tags=["device"])


@router.post("/checkin", response_model=CheckinResponse)
def checkin(
    payload: CheckinRequest,
    device: Device = Depends(authenticated_device),
    session: Session = Depends(get_db),
) -> CheckinResponse:
    """Record a check-in and report whether the device's desired state has moved."""
    device.last_checkin_at = datetime.now(timezone.utc)
    device.agent_version = payload.agent_version or device.agent_version
    device.os_version = payload.os_version or device.os_version

    # Reading through the cache also settles any pending recompute, so
    # state_version is current before it is compared.
    eff.get_effective(session, device)

    policy_changed = payload.state_version != device.state_version
    session.commit()

    return CheckinResponse(
        device_id=device.id,
        state_version=device.state_version,
        policy_changed=policy_changed,
    )
