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

"""Taking in where devices have been (W106).

Points arrive in batches on the check-in, because the device buffers them at its
reporting interval and flushes whatever it has whenever it next reaches the
server. A tablet that spends a day out of coverage should come back with a day of
track, not with one point and a gap.

⚠️ **Everything here treats the device's report as a claim, not as fact.** The
timestamp is the device's clock, the coordinates are whatever it computed, and
both reach us over a channel we authenticate but do not supervise. So a batch is
filtered rather than trusted:

* **Impossible coordinates are dropped**, and are separately refused by CHECK
  constraints on the table. A NaN latitude poisons every bounding box drawn from
  the table afterwards, including ones computed months later, and working out why
  at that point is genuinely hard.
* **Points from the future are dropped.** A device whose clock is wrong by years
  would otherwise pin itself to the top of every history view permanently, with
  nothing in the console to explain it.
* **Points already stored are dropped.** A flush whose response was lost is
  re-sent by a correct agent; answering that with duplicates would corrupt the
  track precisely when the network was bad.

A dropped point is counted and logged, never silently discarded — an agent that
starts sending nonsense should be visible as such.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Device, DeviceLocation, LocationSource

logger = logging.getLogger(__name__)

#: Most points one check-in may carry. A device offline for a week at a five
#: minute interval has ~2,000 buffered, so the agent must deliver them across
#: several check-ins rather than in one request. The cap exists so that a broken
#: or hostile agent cannot make the server write unboundedly in a single call.
MAX_BATCH = 500

#: How far ahead of our own clock a fix may claim to be before we disbelieve it.
#: Generous, because a device's clock legitimately drifts and NTP may not have run
#: yet; anything beyond this is not drift.
FUTURE_TOLERANCE = timedelta(minutes=10)


@dataclass(frozen=True)
class Ingested:
    """What a batch actually did, for the caller's log."""

    stored: int = 0
    duplicates: int = 0
    rejected: int = 0

    @property
    def total(self) -> int:
        return self.stored + self.duplicates + self.rejected


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(moment: datetime) -> datetime:
    """A naive timestamp is read as UTC — the agent sends nothing else."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def _plausible(latitude: float, longitude: float, accuracy_m: float | None) -> bool:
    # ⚠️ NaN fails every comparison, including the ones below, so it is rejected
    # by construction here rather than by a separate check that could be dropped.
    if not (-90.0 <= latitude <= 90.0):
        return False
    if not (-180.0 <= longitude <= 180.0):
        return False
    if accuracy_m is not None and (math.isnan(accuracy_m) or accuracy_m < 0):
        return False
    return True


def record(
    session: Session,
    device: Device,
    reports: Sequence[Any],
    *,
    source: LocationSource = LocationSource.PERIODIC,
) -> Ingested:
    """Store a batch of position reports, dropping what cannot be believed.

    ``reports`` is any sequence of objects carrying ``latitude``, ``longitude``
    and ``recorded_at``, optionally ``accuracy_m`` and ``provider`` — the check-in
    schema satisfies that, and so does the shape a ``locate`` result takes.
    """
    if not reports:
        return Ingested()

    now = _utcnow()
    horizon = now + FUTURE_TOLERANCE

    accepted: list[tuple[datetime, Any]] = []
    rejected = 0

    for report in list(reports)[:MAX_BATCH]:
        recorded_at = _as_utc(report.recorded_at)
        if recorded_at > horizon:
            logger.warning(
                "location from %s dropped: recorded_at %s is ahead of the server clock",
                device.serial_number,
                recorded_at.isoformat(),
            )
            rejected += 1
            continue
        if not _plausible(
            report.latitude, report.longitude, getattr(report, "accuracy_m", None)
        ):
            logger.warning(
                "location from %s dropped: implausible coordinates %r, %r",
                device.serial_number,
                report.latitude,
                report.longitude,
            )
            rejected += 1
            continue
        accepted.append((recorded_at, report))

    if len(reports) > MAX_BATCH:
        # Loud, because the agent is ours and is supposed to chunk below the cap.
        logger.warning(
            "location batch from %s carried %d points; only the first %d were read",
            device.serial_number,
            len(reports),
            MAX_BATCH,
        )
        rejected += len(reports) - MAX_BATCH

    if not accepted:
        return Ingested(rejected=rejected)

    already = _existing_times(session, device, [when for when, _ in accepted])

    stored = 0
    duplicates = 0
    seen: set[datetime] = set()

    for recorded_at, report in accepted:
        # Against the database and within the batch both: a retrying agent can
        # repeat a point, and a confused one can repeat it inside a single flush.
        if recorded_at in already or recorded_at in seen:
            duplicates += 1
            continue
        seen.add(recorded_at)

        accuracy = getattr(report, "accuracy_m", None)
        session.add(
            DeviceLocation(
                device_id=device.id,
                latitude=float(report.latitude),
                longitude=float(report.longitude),
                accuracy_m=float(accuracy) if accuracy is not None else None,
                provider=(getattr(report, "provider", None) or None),
                recorded_at=recorded_at,
                received_at=now,
                source=source,
            )
        )
        stored += 1

    session.flush()
    if stored or rejected:
        logger.info(
            "location batch from %s: %d stored, %d duplicate, %d rejected",
            device.serial_number,
            stored,
            duplicates,
            rejected,
        )
    return Ingested(stored=stored, duplicates=duplicates, rejected=rejected)


def _existing_times(
    session: Session, device: Device, times: Iterable[datetime]
) -> set[datetime]:
    """Fix times this device already holds, within the batch's own span.

    Bounded by the batch rather than scanning the device's whole history, which is
    what keeps this cheap as the table grows. The race — two check-ins from one
    device overlapping — is not a real scenario: a device runs one sync at a time.
    """
    moments = list(times)
    if not moments:
        return set()

    rows = session.scalars(
        select(DeviceLocation.recorded_at).where(
            DeviceLocation.device_id == device.id,
            DeviceLocation.recorded_at >= min(moments),
            DeviceLocation.recorded_at <= max(moments),
        )
    )
    return {_as_utc(moment) for moment in rows}


def latest(session: Session, device_id: Any) -> DeviceLocation | None:
    """The most recent point for a device, or None if it has never reported."""
    return session.scalars(
        select(DeviceLocation)
        .where(DeviceLocation.device_id == device_id)
        .order_by(DeviceLocation.recorded_at.desc())
        .limit(1)
    ).first()


def history(
    session: Session,
    device_id: Any,
    *,
    newest: datetime | None = None,
    oldest: datetime | None = None,
    limit: int | None = None,
) -> list[DeviceLocation]:
    """Points for a device, newest first.

    ⚠️ The bounds read backwards on purpose, and match the console: ``newest`` is
    the recent end of the window and ``oldest`` is further back in time. That is
    the shape the history page asks its question in, and translating between two
    conventions on the way through is exactly how an off-by-one range appears.
    """
    stmt = select(DeviceLocation).where(DeviceLocation.device_id == device_id)
    if newest is not None:
        stmt = stmt.where(DeviceLocation.recorded_at <= _as_utc(newest))
    if oldest is not None:
        stmt = stmt.where(DeviceLocation.recorded_at >= _as_utc(oldest))
    stmt = stmt.order_by(DeviceLocation.recorded_at.desc())
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(session.scalars(stmt))


# --------------------------------------------------------------------------- #
# The `locate` command, which already existed and already returns a position
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Point:
    """A position in the shape :func:`record` reads.

    Exists so that a `locate` result and a check-in report can be stored by the
    same code despite arriving under different field names.
    """

    latitude: float
    longitude: float
    recorded_at: datetime
    accuracy_m: float | None = None
    provider: str | None = None


def from_locate_result(result: Any) -> Point | None:
    """Read `LocateCommandHandler`'s JSON, or None if it is not a position.

    ⚠️ **The agent's field names are not the wire schema's**, and this is the only
    place that knows both. The handler reports `accuracy_metres` and
    `fixed_at_millis`; the check-in reports `accuracy_m` and `recorded_at`. They
    were named independently and renaming either now would break a released agent
    or a stored command result, so the mismatch is translated here rather than
    papered over in one of them.

    ``fixed_at_millis`` is `Location.getTime()` — Unix epoch milliseconds, UTC.
    """
    if not isinstance(result, dict):
        return None

    latitude = result.get("latitude")
    longitude = result.get("longitude")
    fixed_at = result.get("fixed_at_millis")
    if latitude is None or longitude is None or fixed_at is None:
        return None

    try:
        recorded_at = datetime.fromtimestamp(float(fixed_at) / 1000.0, tz=timezone.utc)
        accuracy = result.get("accuracy_metres")
        return Point(
            latitude=float(latitude),
            longitude=float(longitude),
            recorded_at=recorded_at,
            accuracy_m=float(accuracy) if accuracy is not None else None,
            provider=result.get("provider"),
        )
    except (TypeError, ValueError, OSError, OverflowError):
        # A malformed result is not worth failing a check-in over: the command
        # already reported its own success or failure, and this is a bonus point.
        return None


def record_locate_results(session: Session, device: Device, results: Sequence[Any]) -> Ingested:
    """Store positions from any `locate` commands acknowledged in this check-in.

    An operator asking "where is this device" is also, incidentally, the answer to
    "where has it been" — so the existing command starts building history without
    the device needing a tracking policy at all.
    """
    if not results:
        return Ingested()

    # Imported here: `commands` is a peer service and importing it at module
    # scope would tie every location read to the command model as well.
    from app.db.models import CommandStatus, CommandType, DeviceCommand

    ids = [r.command_id for r in results if getattr(r, "succeeded", False)]
    if not ids:
        return Ingested()

    rows = session.scalars(
        select(DeviceCommand).where(
            DeviceCommand.device_id == device.id,
            DeviceCommand.id.in_(ids),
            DeviceCommand.command_type == CommandType.LOCATE,
            DeviceCommand.status == CommandStatus.SUCCEEDED,
        )
    )

    points = [p for p in (from_locate_result(row.result) for row in rows) if p is not None]
    return record(session, device, points, source=LocationSource.COMMAND)
