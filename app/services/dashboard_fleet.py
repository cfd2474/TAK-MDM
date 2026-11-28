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

"""The fleet by last check-in, overall and per group (W442).

Operator: "i want the other sections from the sample as well". Decided:
the sample's five buckets **plus "Never checked in"**, and a device counts
**in every group it is in**, with a "No group" row for the rest.

⚠️ **Enrolled devices only.** A pre-registered serial (inventory import) or a
retired record has no check-in to judge; counting it would make a healthy
fleet look stale.

⚠️ **"Stale" excludes "Never".** A device that has never checked in is not
stale, it is stuck, and the console already has a name for that (stalled
enrollment, W419). The sample has no such bucket; folding it into "> 1 y"
would hide every new tablet whose first sync failed among the abandoned ones.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.db.models import Device, DeviceLocation, EnrollmentState

ACTIVE, WEEK, MONTH, YEAR, OLD, NEVER = "active", "week", "month", "year", "old", "never"

#: (key, label), in the order the bar draws them: freshest first.
BUCKETS: tuple[tuple[str, str], ...] = (
    (ACTIVE, "Active <24h"),
    (WEEK, "Stale 1–7d"),
    (MONTH, "Stale 7–30d"),
    (YEAR, "Stale 30d–1y"),
    (OLD, "Stale >1y"),
    (NEVER, "Never checked in"),
)
STALE = (WEEK, MONTH, YEAR, OLD)

#: Battery under this, on a device seen in the last day, is "low battery".
LOW_BATTERY_PERCENT = 20

NO_GROUP = "No group"

#: The group bars' sorts, as the sample names them.
SORTS: tuple[tuple[str, str], ...] = (
    ("stale", "Most stale"),
    ("old", "Most >1 year"),
    ("share", "Stale share"),
    ("total", "Largest"),
)


def as_utc(moment: datetime | None) -> datetime | None:
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment


def bucket(last_checkin_at: datetime | None, now: datetime) -> str:
    """Which bucket a device's last check-in puts it in."""
    seen = as_utc(last_checkin_at)
    if seen is None:
        return NEVER
    age = now - seen
    if age < timedelta(hours=24):
        return ACTIVE
    if age < timedelta(days=7):
        return WEEK
    if age < timedelta(days=30):
        return MONTH
    if age < timedelta(days=365):
        return YEAR
    return OLD


@dataclass
class Counts:
    """Devices per bucket, and what the bars and tables say about them."""

    by_bucket: dict[str, int] = field(default_factory=lambda: {key: 0 for key, _ in BUCKETS})

    def add(self, key: str) -> None:
        self.by_bucket[key] += 1

    @property
    def total(self) -> int:
        return sum(self.by_bucket.values())

    @property
    def stale(self) -> int:
        return sum(self.by_bucket[key] for key in STALE)

    @property
    def stale_share(self) -> float:
        """Stale among the devices that have ever checked in, 0-100."""
        seen = self.total - self.by_bucket[NEVER]
        return 0.0 if seen == 0 else self.stale * 100.0 / seen

    def as_json(self) -> dict:
        return {
            "buckets": dict(self.by_bucket),
            "total": self.total,
            "stale": self.stale,
            "stale_share": round(self.stale_share, 1),
            "old": self.by_bucket[OLD],
        }


@dataclass(frozen=True)
class GroupRow:
    id: str | None
    name: str
    counts: Counts

    def as_json(self) -> dict:
        return {"id": self.id, "name": self.name, **self.counts.as_json()}


@dataclass(frozen=True)
class Fleet:
    counts: Counts
    groups: list[GroupRow]
    new_24h: int
    new_7d: int
    low_battery: int
    with_location: int

    def as_json(self) -> dict:
        return {
            **self.counts.as_json(),
            "new_24h": self.new_24h,
            "new_7d": self.new_7d,
            "low_battery": self.low_battery,
            "with_location": self.with_location,
            "groups": [g.as_json() for g in self.groups],
        }


def sort_groups(rows: Iterable[GroupRow], how: str) -> list[GroupRow]:
    """The sample's four orders, largest first; ties by name so the list holds still."""
    measure = {
        "stale": lambda r: r.counts.stale,
        "old": lambda r: r.counts.by_bucket[OLD],
        "share": lambda r: r.counts.stale_share,
        "total": lambda r: r.counts.total,
    }[how]
    return sorted(rows, key=lambda r: (-measure(r), r.name.casefold()))


def summarise(devices: Iterable[Device], now: datetime, with_location: int = 0) -> Fleet:
    """The fleet's figures from its enrolled devices, groups already loaded."""
    counts = Counts()
    groups: dict[uuid.UUID | None, GroupRow] = {}
    new_24h = new_7d = low_battery = 0
    for device in devices:
        key = bucket(device.last_checkin_at, now)
        counts.add(key)
        created = as_utc(device.created_at)
        if created is not None:
            new_24h += now - created < timedelta(hours=24)
            new_7d += now - created < timedelta(days=7)
        if (key == ACTIVE and device.battery_level is not None
                and device.battery_level < LOW_BATTERY_PERCENT):
            low_battery += 1
        for group in device.groups or [None]:
            gid = group.id if group is not None else None
            if gid not in groups:
                groups[gid] = GroupRow(
                    str(gid) if gid else None, group.name if group else NO_GROUP, Counts()
                )
            groups[gid].counts.add(key)
    return Fleet(counts, sort_groups(groups.values(), "stale"), new_24h, new_7d, low_battery, with_location)


def _n(count: int, one: str, many: str) -> str:
    return f"{count:,} {one if count == 1 else many}"


def summary_line(fleet: Fleet) -> str:
    """The sentence under the page title, as the sample has it."""
    c = fleet.counts.by_bucket
    if fleet.counts.total == 0:
        return "No devices are enrolled yet."
    parts = [
        f"{_n(fleet.counts.total, 'device', 'devices')}",
        f"{c[ACTIVE]:,} active in the last 24 hours",
        f"{c[OLD]:,} not seen in over a year",
    ]
    if c[NEVER]:
        parts.append(f"{c[NEVER]:,} never checked in")
    located = "has" if fleet.with_location == 1 else "have"
    return "; ".join(parts) + f". {fleet.with_location:,} {located} a last known location."


def details_line(fleet: Fleet) -> str:
    """The line under the fleet bar's legend."""
    return (f"New enrollments {fleet.new_24h:,} in 24h, {fleet.new_7d:,} in 7d. "
            f"Low battery (<{LOW_BATTERY_PERCENT}%, seen 24h): {fleet.low_battery:,}.")


def read(session: Session, now: datetime | None = None) -> Fleet:
    """The fleet's figures, from the database."""
    now = now or datetime.now(timezone.utc)
    devices = list(session.scalars(
        select(Device).where(Device.enrollment_state == EnrollmentState.ENROLLED)
    ))
    located = session.scalar(
        select(func.count(distinct(DeviceLocation.device_id)))
        .join(Device, Device.id == DeviceLocation.device_id)
        .where(Device.enrollment_state == EnrollmentState.ENROLLED)
    ) or 0
    return summarise(devices, now, int(located))
