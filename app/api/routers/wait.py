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

"""Long-poll wake endpoint (F3).

The agent parks here between check-ins. The request is released the instant this
device's state is invalidated or a command is queued for it, so a policy edit
reaches the fleet in milliseconds rather than at the next poll.

This is a **doorbell**: the response says "check in now", not what changed. Keeping
it contentless means a missed wake costs latency and nothing else — the device still
converges on its next poll, and D7's guarantee that polling is the correctness floor
survives intact.

**Lost-wake safety.** The doorbell ring can be lost — the notify runs in the
window between one check-in finishing and the next park registering, or a
recompute lands while the request is parked. So the endpoint does not park once
for the whole timeout; it sub-parks in short slices and re-reads the pending
reason between them. A lost ring therefore costs at most one slice (``_SLICE``
seconds) instead of the full timeout.

Written ``async`` deliberately. A parked request must not hold a worker thread or
a database connection: the session is closed between every pending check, so the
connection is only borrowed for the read itself, never held across a park.
"""

from __future__ import annotations

import time
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import authenticated_device, get_db
from app.db.models import CommandStatus, Device, DeviceCommand, EffectivePolicyCache
from app.services import effective_policy as eff
from app.services import notifications

router = APIRouter(prefix="/api/v1/device", tags=["device"])

# How long each internal sub-park lasts. A lost doorbell ring costs at most this.
_SLICE = 10.0


def _pending(
    session: Session, device_id: uuid.UUID, known_version: int | None
) -> tuple[str | None, int]:
    """(reason this device should check in now, its current state_version).

    Assumes a freshly-closed session so every read hits the database — the whole
    point of the loop is to observe ``state_version`` change while parked.
    """
    device = session.get(Device, device_id)
    if device is None:
        return None, known_version or 0
    current = device.state_version

    if known_version is not None and current != known_version:
        return "state_changed", current

    cache = session.get(EffectivePolicyCache, device_id)
    if cache is None or cache.stale:
        return "state_pending", current
    if eff.expired(cache):
        # ⚠️ A scheduled deployment came due and nothing wrote anything (W191).
        # Staleness is the trace a *write* leaves; a clock passing a date leaves
        # none, so without this a parked device holds its long poll through the
        # moment and applies the policy whenever the poll happens to expire.
        #
        # Self-clearing: the check-in this releases recomputes the payload and
        # with it the horizon, so the next slice sees either the following
        # scheduled moment or none at all.
        return "schedule_due", current

    live_command = session.scalar(
        select(DeviceCommand)
        .where(
            DeviceCommand.device_id == device_id,
            DeviceCommand.status.in_([CommandStatus.PENDING, CommandStatus.DISPATCHED]),
        )
        .limit(1)
    )
    return ("command_queued" if live_command is not None else None), current


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
    known = state_version
    deadline = time.monotonic() + timeout

    while True:
        reason, current = _pending(session, device_id, known)
        # Free the connection *and* expire the identity map, so the next
        # iteration's reads see committed changes rather than cached rows.
        session.close()

        if reason is not None:
            return {"should_checkin": True, "reason": reason, "state_version": current}

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {"should_checkin": False, "reason": "timeout", "state_version": current}

        # Sub-park: released instantly by a doorbell ring, or falls through after a
        # slice so the loop re-reads the pending reason.
        await notifications.bus.wait(device_id, min(remaining, _SLICE))
