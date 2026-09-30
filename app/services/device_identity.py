"""Resolving a device from the set of identifiers it reports.

Copyright 2026 TAK-Solutions LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

D24 matched a re-enrolling device on ``serial_number`` alone. One key, and a
device's reported identity is not guaranteed to hold still: when
``Build.getSerial()`` was refused the agent fell back to ``ANDROID_ID``, which
Android changes on factory reset — the very event re-enrolment exists to survive.
The result was several records for one tablet, each with its own history and group
membership.

A device now enrols with a *set* of identifiers. The server matches on any it
already knows and records the rest, so moving between identity sources re-adopts
the existing record rather than forking a new one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    IDENTIFIER_PRIORITY,
    Device,
    DeviceIdentifier,
    IdentifierKind,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ReportedIdentifier:
    kind: IdentifierKind
    value: str


@dataclass
class Resolution:
    """Which device a set of identifiers points at, and how confidently."""

    device: Device | None
    #: The identifier that decided it.
    matched_on: ReportedIdentifier | None = None
    #: Other devices that also matched. Non-empty means the fleet holds duplicate
    #: records for what is probably one piece of hardware.
    ambiguous_with: tuple[Device, ...] = ()

    @property
    def is_ambiguous(self) -> bool:
        return bool(self.ambiguous_with)


def parse_reported(
    raw: list[dict] | None, *, serial_number: str
) -> list[ReportedIdentifier]:
    """Normalise what the agent sent, and always include its stated serial.

    An older agent sends no list at all. Treating its ``serial_number`` as a
    ``LEGACY`` identifier keeps it working unchanged — the alternative, requiring
    every device to upgrade before it can enrol, is not available to a fleet whose
    devices may be dark for weeks.
    """
    seen: dict[str, ReportedIdentifier] = {}

    for entry in raw or []:
        value = (entry.get("value") or "").strip()
        if not value:
            continue
        try:
            kind = IdentifierKind(entry.get("kind"))
        except ValueError:
            # An unknown kind from a newer agent. Keep the value — it is still a
            # usable match key — rather than discarding identity we were given.
            kind = IdentifierKind.LEGACY
        seen.setdefault(value, ReportedIdentifier(kind, value))

    serial = (serial_number or "").strip()
    if serial:
        seen.setdefault(serial, ReportedIdentifier(IdentifierKind.LEGACY, serial))

    return list(seen.values())


def resolve(session: Session, reported: list[ReportedIdentifier]) -> Resolution:
    """Find the device these identifiers belong to.

    Resolved by identifier **kind priority**, not by the order the agent listed
    them: a device reporting both a real serial and an old fallback must land on the
    same record every time, whichever way round it sends them.
    """
    if not reported:
        return Resolution(device=None)

    rows = session.scalars(
        select(DeviceIdentifier).where(
            DeviceIdentifier.value.in_([r.value for r in reported])
        )
    ).all()

    if not rows:
        return Resolution(device=None)

    by_value = {r.value: r for r in reported}
    # Strongest reported kind wins, and a stable tiebreak on the value keeps the
    # result deterministic when two identifiers share a kind.
    rows_sorted = sorted(
        rows,
        key=lambda row: (
            IDENTIFIER_PRIORITY.index(by_value[row.value].kind)
            if by_value[row.value].kind in IDENTIFIER_PRIORITY
            else len(IDENTIFIER_PRIORITY),
            row.value,
        ),
    )

    winner_row = rows_sorted[0]
    winner = session.get(Device, winner_row.device_id)
    others = []
    for row in rows_sorted[1:]:
        if row.device_id != winner_row.device_id:
            other = session.get(Device, row.device_id)
            if other is not None and other not in others:
                others.append(other)

    return Resolution(
        device=winner,
        matched_on=by_value[winner_row.value],
        ambiguous_with=tuple(others),
    )


def record(
    session: Session, device: Device, reported: list[ReportedIdentifier]
) -> list[DeviceIdentifier]:
    """Attach every identifier to this device, refreshing what is already known.

    An identifier already claimed by a *different* device is left alone rather than
    reassigned. Silently moving it would rewrite which record a third device
    resolves to, and the fix for a genuine duplicate is a deliberate merge, not a
    side effect of someone else's check-in.
    """
    added: list[DeviceIdentifier] = []
    now = _utcnow()

    for item in reported:
        existing = session.scalar(
            select(DeviceIdentifier).where(DeviceIdentifier.value == item.value)
        )
        if existing is not None:
            if existing.device_id == device.id:
                existing.last_seen_at = now
                # A value first seen as a weak kind may now be reported as a strong
                # one; keep the better claim.
                if _rank(item.kind) < _rank(existing.kind):
                    existing.kind = item.kind
            continue

        row = DeviceIdentifier(
            device_id=device.id, kind=item.kind, value=item.value,
            first_seen_at=now, last_seen_at=now,
        )
        session.add(row)
        added.append(row)

    session.flush()
    return added


def promote_display_serial(
    session: Session, device: Device, reported: list[ReportedIdentifier]
) -> str | None:
    """Adopt the strongest reported identifier as the device's shown serial.

    A record created while `Build.getSerial()` was refused is named after an
    `ANDROID_ID` fallback, which is both meaningless to an operator and wrong on the
    asset register. Once the real serial is known there is no reason to keep showing
    the fallback.

    Returns the new value, or None if nothing changed.
    """
    strongest = min(
        (r for r in reported if r.kind in IDENTIFIER_PRIORITY),
        key=lambda r: IDENTIFIER_PRIORITY.index(r.kind),
        default=None,
    )
    if strongest is None or strongest.kind is not IdentifierKind.SERIAL:
        return None
    if device.serial_number == strongest.value:
        return None

    # Never take a name another record already holds: `serial_number` is unique, and
    # the collision is itself evidence of a duplicate that wants a human decision.
    clash = session.scalar(
        select(Device).where(
            Device.serial_number == strongest.value, Device.id != device.id
        )
    )
    if clash is not None:
        return None

    device.serial_number = strongest.value
    session.flush()
    return strongest.value


def for_device(session: Session, device_id) -> list[DeviceIdentifier]:
    return list(
        session.scalars(
            select(DeviceIdentifier)
            .where(DeviceIdentifier.device_id == device_id)
            .order_by(DeviceIdentifier.first_seen_at)
        )
    )


def _rank(kind: IdentifierKind) -> int:
    return (
        IDENTIFIER_PRIORITY.index(kind)
        if kind in IDENTIFIER_PRIORITY
        else len(IDENTIFIER_PRIORITY)
    )
