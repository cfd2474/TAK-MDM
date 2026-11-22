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

"""The dashboard's trends: one reading a day, kept a year (W442).

Operator: "One year", one reading per day in the console's timezone; charts
over 30, 90 or 365 days.

⚠️ **There is no history before the first reading.** Nothing in ATLAS
records when each device checked in over time (only its latest), so the
charts start empty on the day this ships and gain a point a day. The page
says how many readings there are rather than drawing a flat line from zero.

⚠️ **Taken once per local day, whenever the thread first looks that day.**
The time of day is not fixed: a reading's figures are as of `taken_at`,
which the chart's tooltip shows. A server that was down all day has no
reading for that day; the gap is drawn as a gap.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import DashboardSnapshot, Device, EnrollmentState
from app.services import clock, dashboard_fleet

KEEP_DAYS = 365
RANGES = (30, 90, 365)


def local_day(now: datetime, tz) -> str:
    return now.astimezone(tz).date().isoformat()


def measure(session: Session, now: datetime, disk_percent: float | None,
            memory_percent: float | None) -> dict:
    """Today's figures. Device counts are enrolled devices only, as on the page."""
    devices = list(session.scalars(
        select(Device).where(Device.enrollment_state == EnrollmentState.ENROLLED)
    ))
    within_1h = within_24h = stale_30d = low = 0
    for d in devices:
        seen = dashboard_fleet.as_utc(d.last_checkin_at)
        if seen is None:
            continue
        age = now - seen
        within_1h += age < timedelta(hours=1)
        within_24h += age < timedelta(hours=24)
        stale_30d += age >= timedelta(days=30)
        low += (age < timedelta(hours=24) and d.battery_level is not None
                and d.battery_level < dashboard_fleet.LOW_BATTERY_PERCENT)
    return {
        "devices": len(devices),
        "checked_in_1h": within_1h,
        "checked_in_24h": within_24h,
        "stale_30d": stale_30d,
        "low_battery": low,
        "disk_percent": None if disk_percent is None else round(disk_percent, 1),
        "memory_percent": None if memory_percent is None else round(memory_percent, 1),
    }


def take_if_due(
    session: Session,
    *,
    now: datetime | None = None,
    tz=None,
    disk_percent: Callable[[], float | None],
    memory_percent: Callable[[], float | None],
) -> DashboardSnapshot | None:
    """Today's reading, if there is none yet; then the year's pruning.

    Returns the new reading, or None when today's already exists. Commits.
    """
    now = now or datetime.now(timezone.utc)
    tz = tz or clock.configured(session)
    today = local_day(now, tz)
    if session.scalar(select(DashboardSnapshot.id).where(DashboardSnapshot.day == today)) is not None:
        return None
    reading = DashboardSnapshot(day=today, taken_at=now,
                                **measure(session, now, disk_percent(), memory_percent()))
    session.add(reading)
    try:
        session.flush()
    except IntegrityError:
        # Another worker took today's in the meantime: theirs stands.
        session.rollback()
        return None
    prune(session, today)
    session.commit()
    return reading


def prune(session: Session, today: str) -> int:
    """Drop readings older than a year before `today`."""
    oldest = (date.fromisoformat(today) - timedelta(days=KEEP_DAYS - 1)).isoformat()
    return session.execute(delete(DashboardSnapshot).where(DashboardSnapshot.day < oldest)).rowcount or 0


def series(session: Session) -> dict:
    """Every reading kept, oldest first, as columns for the charts."""
    rows = list(session.scalars(select(DashboardSnapshot).order_by(DashboardSnapshot.day)))
    return {
        "days": [r.day for r in rows],
        "taken_at": [r.taken_at.astimezone(timezone.utc).isoformat(timespec="minutes") for r in rows],
        "devices": [r.devices for r in rows],
        "checked_in_1h": [r.checked_in_1h for r in rows],
        "checked_in_24h": [r.checked_in_24h for r in rows],
        "stale_30d": [r.stale_30d for r in rows],
        "low_battery": [r.low_battery for r in rows],
        "disk_percent": [r.disk_percent for r in rows],
        "memory_percent": [r.memory_percent for r in rows],
        "ranges": list(RANGES),
    }
