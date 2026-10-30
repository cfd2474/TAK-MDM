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

"""When an update-check alert rule runs (W436).

Operator: "i want to be able to adjust the schedule of the alerts on the admin
page. this includes the time". Then: update checks only, per rule, a time of
day and chosen weekdays.

A schedule is `{"time": "HH:MM", "days": [0..6]}`, Monday 0, read in the
console's timezone. Pure functions only: the scheduler and the page share them.

⚠️ **Due is "the latest slot is after the last scheduled run"**, worked out
from the zone in force *now*. So a timezone change moves every schedule with
it ("06:00" stays 06:00 on the operator's clock) without a stored next-run
time to recalculate, and a slot missed while ATLAS was down runs once on the
way back up, never once per missed day.

⚠️ **Each local date gives one instant, whatever daylight saving does.** A
06:00 that happens twice (clocks back) is taken the first time; a 02:30 that
never happens (clocks forward) lands on the equivalent real instant, as
`clock.from_local` resolves it. Either way the rule runs once that day.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Any

#: A rule with no schedule stored: every day at 06:00.
DEFAULT: dict[str, Any] = {"time": "06:00", "days": [0, 1, 2, 3, 4, 5, 6]}

DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

_TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class ScheduleError(ValueError):
    """A schedule that cannot be saved; the message is for the operator."""


def validate(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Normalise a schedule from a form, or explain why it can't be used."""
    raw = raw or {}
    text = str(raw.get("time") or "").strip()
    if not _TIME.match(text):
        raise ScheduleError(f"{text or 'a blank time'!r} is not a time of day; write it as HH:MM, for example 06:00")
    days = set()
    for day in raw.get("days") or []:
        try:
            value = int(day)
        except (TypeError, ValueError):
            raise ScheduleError(f"{day!r} is not a day of the week") from None
        if not 0 <= value <= 6:
            raise ScheduleError(f"{day!r} is not a day of the week")
        days.add(value)
    if not days:
        raise ScheduleError("choose at least one day for the check to run")
    return {"time": text, "days": sorted(days)}


def of(stored: dict[str, Any] | None) -> dict[str, Any]:
    """A rule's schedule, the default when none is stored or it no longer reads.

    ⚠️ Never raises: it runs on every page render and every scheduler tick, and
    a row that can't be read must not stop the rest being checked.
    """
    try:
        return validate(stored) if stored else dict(DEFAULT)
    except ScheduleError:
        return dict(DEFAULT)


def _clock(schedule: dict[str, Any]) -> time:
    hours, minutes = schedule["time"].split(":")
    return time(int(hours), int(minutes))


def _instant(day: date, at: time, tz: tzinfo) -> datetime:
    """One local date and time as a UTC instant; fold=0, as `clock.from_local`."""
    return datetime.combine(day, at).replace(tzinfo=tz, fold=0).astimezone(timezone.utc)


def _slots(schedule: dict[str, Any] | None, around: datetime, tz: tzinfo) -> list[datetime]:
    """The schedule's instants within eight local days either side of `around`.

    Eight days covers every weekly pattern, with a day to spare for zones whose
    date differs from UTC's.
    """
    schedule = of(schedule)
    at, days = _clock(schedule), set(schedule["days"])
    today = around.astimezone(tz).date()
    span = (today + timedelta(days=offset) for offset in range(-8, 9))
    return [_instant(day, at, tz) for day in span if day.weekday() in days]


def previous_slot(schedule: dict[str, Any] | None, now: datetime, tz: tzinfo) -> datetime | None:
    """The latest scheduled instant at or before `now`."""
    earlier = [slot for slot in _slots(schedule, now, tz) if slot <= now]
    return max(earlier, default=None)


def next_slot(schedule: dict[str, Any] | None, now: datetime, tz: tzinfo) -> datetime | None:
    """The first scheduled instant after `now`."""
    later = [slot for slot in _slots(schedule, now, tz) if slot > now]
    return min(later, default=None)


def is_due(schedule: dict[str, Any] | None, last_run: datetime | None, now: datetime, tz: tzinfo) -> bool:
    """Whether a slot has come round since the rule last ran on schedule."""
    latest = previous_slot(schedule, now, tz)
    return latest is not None and (last_run is None or latest > last_run)


def describe(schedule: dict[str, Any] | None) -> str:
    """ "Every day at 06:00", "Weekdays at 07:30", "Mon, Wed, Fri at 18:00". """
    schedule = of(schedule)
    days = schedule["days"]
    if days == list(range(7)):
        when = "Every day"
    elif days == list(range(5)):
        when = "Weekdays"
    elif days == [5, 6]:
        when = "Weekends"
    else:
        when = ", ".join(DAY_NAMES[d] for d in days)
    return f"{when} at {schedule['time']}"
