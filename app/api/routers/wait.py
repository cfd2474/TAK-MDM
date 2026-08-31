"""Long-poll wake endpoint (F3).

The agent parks here between check-ins. The request is released the instant this
device's state is invalidated or a command is queued for it, so a policy edit
reaches the fleet in milliseconds rather than at the next poll.

This is a **doorbell**: the response says "check in now", not what changed. Keeping
it contentless means a missed wake costs latency and nothing else — the device still
converges on its next poll, and D7's guarantee that polling is the correctness floor
survives intact.

Written ``async`` deliberately. A parked request must not hold a worker thread or a
database connection, or a few hundred waiting tablets would exhaust both. The
session is released before parking and a fresh one is taken afterwards.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import authenticated_device, get_db
from app.db.models import CommandStatus, Device, DeviceCommand, EffectivePolicyCache
from app.services import notifications

router = APIRouter(prefix="/api/v1/device", tags=["device"])


def _pending_reason(session: Session, device_id: uuid.UUID, known_version: int | None) -> str | None:
    """Whether this device already has something waiting, without parking."""
    device = session.get(Device, device_id)
    if device is None:
        return None

    if known_version is not None and device.state_version != known_version:
        return "state_changed"

    cache = session.get(EffectivePolicyCache, device_id)
    if cache is None or cache.stale:
        # A recompute is pending, so the state may already have moved.
        return "state_pending"

    live_command = session.scalar(
        select(DeviceCommand)
        .where(
            DeviceCommand.device_id == device_id,
            DeviceCommand.status.in_([CommandStatus.PENDING, CommandStatus.DISPATCHED]),
        )
        .limit(1)
    )
    return "command_queued" if live_command is not None else None


@router.get("/wait")
async def wait_for_change(
    state_version: int | None = Query(
        default=None, description="the version the agent currently holds"
    ),
    timeout: int = Query(default=60, ge=5, le=300, description="seconds to hold open"),
    device: Device = Depends(authenticated_device),
    session: Session = Depends(get_db),
) -> dict:
    device_id = device.id
    reason = _pending_reason(session, device_id, state_version)
    current_version = device.state_version

    # Release the connection before parking; holding one per waiting device would
    # drain the pool long before the fleet is large.
    session.close()

    if reason is not None:
        return {
            "should_checkin": True,
            "reason": reason,
            "state_version": current_version,
        }

    woken = await notifications.bus.wait(device_id, timeout)

    # No second database read after waking. The version reported here is only the
    # one the agent already had — the check-in that follows is what establishes the
    # authoritative value, and re-reading would mean either holding a connection
    # across the park or reaching around dependency injection for a new one.
    return {
        "should_checkin": woken,
        "reason": "woken" if woken else "timeout",
        "state_version": current_version,
    }
