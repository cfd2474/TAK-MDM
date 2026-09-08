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

"""Handing a device back: factory reset it, then forget it (W104).

The order is the whole design, and the agent already enforces its half.
`WipeCommandHandler` returns `CommandOutcome.okAfterReporting`, and the reconciler
runs deferred effects **only after** the results reach the server — if the
acknowledgement cannot be delivered, the wipe does not run and is retried later.
So the server learns "received, resetting now" from a device that still exists.

⚠️ **That acknowledgement does not mean the reset finished.** Nothing can report
that: the device which would report it has just been erased. A reset that fails
*after* acking leaves a tablet still owned by this agent, holding certificates the
server has revoked — unable to check in, recoverable only by a manual factory
reset at the device. That is the price of removing on acknowledgement, and it is
the only signal that will ever arrive.

⚠️ **A disenroll wipe is marked as one.** An ordinary `wipe` — a lost device, say —
must not silently delete the record an operator may still need; only a wipe
carrying [DISENROLL] removes anything.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.db.models import (
    CommandStatus,
    CommandType,
    Device,
    DeviceCommand,
)
from app.services import commands as command_service
from app.services.enrollment import revoke_device_certificates

logger = logging.getLogger(__name__)

#: Marks a wipe as "the operator is handing this device back", rather than "erase
#: a device I have lost". Only the former removes the record.
DISENROLL = "disenroll"

_OPEN = (CommandStatus.PENDING, CommandStatus.DISPATCHED)


def _disenroll_commands(session: Session, device: Device) -> list[DeviceCommand]:
    return [
        command
        for command in command_service.list_for_device(session, device.id)
        if command.command_type is CommandType.WIPE
        and bool((command.params or {}).get(DISENROLL))
    ]


def pending(session: Session, device: Device) -> DeviceCommand | None:
    """A disenroll already on its way to this device, if there is one."""
    return next(
        (c for c in _disenroll_commands(session, device) if c.status in _OPEN), None
    )


def request(session: Session, device: Device) -> DeviceCommand:
    """Queue the factory reset.

    ⚠️ **Idempotent.** An operator who presses twice, or reloads a page that
    posted, must not queue a second reset — the device would take the first,
    disappear, and leave an orphan command behind it.
    """
    existing = pending(session, device)
    if existing is not None:
        return existing

    logger.info("disenroll requested for %s", device.serial_number)
    return command_service.enqueue(
        session,
        device,
        command_type=CommandType.WIPE,
        params={
            DISENROLL: True,
            # ⚠️ Including the card. "Factory reset" that leaves external storage
            # readable is not one, and this device is being handed back — the
            # console says so before the button is pressed.
            "wipe_external_storage": True,
        },
    )


def acknowledged(session: Session, device: Device) -> bool:
    """Has the device confirmed it received the reset and is about to run it?"""
    return any(
        command.status is CommandStatus.SUCCEEDED
        for command in _disenroll_commands(session, device)
    )


def complete(session: Session, device: Device) -> str:
    """Forget the device. Returns its serial, for the log after it is gone."""
    serial = device.serial_number
    revoke_device_certificates(session, device, reason="disenrolled")
    session.delete(device)
    session.flush()
    logger.info("disenrolled %s: record removed, certificates revoked", serial)
    return serial
