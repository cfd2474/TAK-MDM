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

"""What happens to a device that keeps failing its compliance rules (W323 chunk 2).

Each action has a grace period counted from `Device.rules_failing_since`:

* **Suspend** the chosen apps (ATAK when none are chosen) and **lock** are
  *state*. They go into the signed desired state under `compliance_enforcement`,
  which the agent re-applies on every sync (~2 min), so they are re-asserted while
  the device fails and lifted the moment it passes.
* **Wipe** is a one-off `WIPE` command, queued once when due and **cancelled if
  the device recovers before it is delivered**.

:func:`due` is pure. The rest wires it in: the effective-policy refresh carries
the state and folds the next deadline into the cache horizon, and :func:`sync_wipe`
queues or cancels the command.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppPackage, CommandStatus, CommandType, Device, DeviceCommand

#: Marks a wipe this module queued, so it is the one cancelled on recovery and
#: never an operator's or a disenroll's.
COMPLIANCE = "compliance"

PAYLOAD_KEY = "compliance_enforcement"

_OPEN = (CommandStatus.PENDING, CommandStatus.DISPATCHED)


@dataclass(frozen=True)
class Enforcement:
    suspend: list[str] = field(default_factory=list)
    lock: bool = False
    wipe: bool = False
    #: The next moment one of these changes by the clock alone, or None.
    next_at: datetime | None = None

    def state(self) -> dict[str, Any]:
        """What the agent is sent. Empty when nothing is due, so a device with no
        actions carries the same bytes as before the feature existed."""
        out: dict[str, Any] = {}
        if self.suspend:
            out["suspend"] = self.suspend
        if self.lock:
            out["lock"] = True
        return out


def due(
    rules: dict[str, Any] | None,
    failing_since: datetime | None,
    now: datetime,
    atak_packages: list[str],
) -> Enforcement:
    """The actions in force at `now` for a device failing since `failing_since`."""
    rules = rules or {}
    if failing_since is None:
        return Enforcement()

    upcoming: list[datetime] = []

    def reached(after: timedelta | None) -> bool:
        if after is None:
            return False
        at = failing_since + after
        if now >= at:
            return True
        upcoming.append(at)
        return False

    hours = lambda key: None if rules.get(key) is None else timedelta(hours=rules[key])
    suspend = reached(hours("suspend_after_hours"))
    lock = reached(hours("lock_after_hours"))
    days = rules.get("wipe_after_days")
    wipe = reached(None if days is None else timedelta(days=days))

    packages = sorted(set(rules.get("suspend_packages") or atak_packages)) if suspend else []
    return Enforcement(packages, lock, wipe, min(upcoming) if upcoming else None)


@dataclass(frozen=True)
class Step:
    """One action on the device page's timeline."""

    action: str      # suspend, lock, wipe
    label: str
    at: datetime
    active: bool


def timeline(
    rules: dict[str, Any] | None, failing_since: datetime | None, now: datetime,
    atak: list[str],
) -> list[Step]:
    """Every action this device's rules set, when it starts, and whether it has."""
    rules = rules or {}
    if failing_since is None:
        return []
    steps: list[Step] = []
    if rules.get("suspend_after_hours") is not None:
        apps = ", ".join(sorted(set(rules.get("suspend_packages") or atak))) or "ATAK"
        at = failing_since + timedelta(hours=rules["suspend_after_hours"])
        steps.append(Step("suspend", f"Suspend {apps}", at, now >= at))
    if rules.get("lock_after_hours") is not None:
        at = failing_since + timedelta(hours=rules["lock_after_hours"])
        steps.append(Step("lock", "Lock the device on each check-in", at, now >= at))
    if rules.get("wipe_after_days") is not None:
        at = failing_since + timedelta(days=rules["wipe_after_days"])
        steps.append(Step("wipe", "Wipe the device", at, now >= at))
    return sorted(steps, key=lambda s: s.at)


def atak_packages(session: Session) -> list[str]:
    """ATAK as the library knows it: what "suspend ATAK" means."""
    from app.services import atak_compat

    return sorted(
        name for name in session.scalars(select(AppPackage.package_name))
        if atak_compat.is_atak(name)
    )


def for_device(session: Session, device: Device, values: dict[str, Any], now: datetime) -> Enforcement:
    from app.services import compliance_rules

    rules = values.get(compliance_rules.POLICY_TYPE) or {}
    # `record` keeps this None whenever the device isn't failing.
    return due(rules, device.rules_failing_since, now, atak_packages(session))


def pending_wipe(session: Session, device: Device) -> DeviceCommand | None:
    """A compliance wipe still on its way to this device, if there is one."""
    open_wipes = session.scalars(
        select(DeviceCommand).where(
            DeviceCommand.device_id == device.id,
            DeviceCommand.command_type == CommandType.WIPE,
            DeviceCommand.status.in_(_OPEN),
        )
    )
    return next((c for c in open_wipes if (c.params or {}).get(COMPLIANCE)), None)


def sync_wipe(session: Session, device: Device, enforcement: Enforcement) -> None:
    """Queue the wipe once it's due; cancel ours if the device no longer needs it.

    ⚠️ **Cancelled on recovery, before delivery.** The check-in checks the rules
    before it claims commands, so a device that comes back compliant never
    receives a wipe queued while it was failing.
    """
    from app.services import commands as command_service

    existing = pending_wipe(session, device)
    if enforcement.wipe and existing is None:
        command_service.enqueue(
            session, device, command_type=CommandType.WIPE,
            params={
                COMPLIANCE: True,
                # The card too: a factory reset that leaves storage readable isn't one.
                "wipe_external_storage": True,
                # ⚠️ Not `wipe_reset_protection`. Factory Reset Protection survives,
                # as for a lost device: only a disenroll hands a device back.
            },
        )
    elif not enforcement.wipe and existing is not None:
        command_service.cancel(session, existing)
        existing.error = "cancelled: the device passes its compliance rules again"
        session.flush()
