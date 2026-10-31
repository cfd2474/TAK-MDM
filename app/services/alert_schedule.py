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

"""When an update-check alert rule runs (W436, W437).

Operator: "i want to be able to adjust the schedule of the alerts on the admin
page. this includes the time" (W436). Then (W437): "keep the time entry, but
the days need to be a variable for "Every X Days" with x being an integer
field", counted from the date the schedule was saved.

A schedule is `{"time": "HH:MM", "every_days": X, "start": "YYYY-MM-DD"}`, read
in the console's timezone: it runs at the time on the start date and every X
days after it. Pure functions only: the scheduler and the page share them.

⚠️ **Due is "the latest slot is after the last scheduled run"**, worked out
from the zone in force *now*. So a timezone change moves every schedule with
it ("06:00" stays 06:00 on the operator's clock) without a stored next-run
time to recalculate, and a slot missed while ATLAS was down runs once on the
way back up, never once per missed slot. The cadence is fixed to the start
date, so a late run doesn't push the later ones back.

⚠️ **Each local date gives one instant, whatever daylight saving does.** A
06:00 that happens twice (clocks back) is taken the first time; a 02:30 that
never happens (clocks forward) lands on the equivalent real instant, as
`clock.from_local` resolves it. Either way the rule runs once that day.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from typing import Any

#: The bounds of X in "every X days".
MIN_DAYS, MAX_DAYS = 1, 365

#: A rule with no schedule stored: every day at 06:00. With X = 1 the start
#: date changes nothing, so the default needs none.
DEFAULT: dict[str, Any] = {"time": "06:00", "every_days": 1, "start": None}

_TIME = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")

#: A Monday, for turning a W436 one-weekday schedule into every 7 days.
_A_MONDAY = date(2026, 1, 5)


class ScheduleError(ValueError):
    """A schedule that cannot be saved; the message is for the operator."""


def validate(raw: dict[str, Any] | None, today: date | None = None) -> dict[str, Any]:
    """Normalise a schedule from a form, or explain why it can't be used.

    `today` is the local date the schedule is saved on, which becomes its start
    when it has none; a stored start is kept.
    """
    raw = raw or {}
    text = str(raw.get("time") or "").strip()
    if not _TIME.match(text):
        raise ScheduleError(f"{text or 'a blank time'!r} is not a time of day; write it as HH:MM, for example 06:00")
    every = str(raw.get("every_days") if raw.get("every_days") is not None else "").strip()
    try:
        days = int(every)
    except ValueError:
        raise ScheduleError(f"{every or 'a blank number'!r} is not a whole number of days") from None
    if not MIN_DAYS <= days <= MAX_DAYS:
        raise ScheduleError(f"every {days} days is out of range; choose {MIN_DAYS} to {MAX_DAYS}")
    start = raw.get("start")
    if start:
        try:
            start = date.fromisoformat(str(start)).isoformat()
        except ValueError:
            raise ScheduleError(f"{start!r} is not a date") from None
    else:
        start = (today or datetime.now(timezone.utc).date()).isoformat()
    return {"time": text, "every_days": days, "start": start}


def _from_weekdays(stored: dict[str, Any]) -> dict[str, Any]:
    """A W436 weekday schedule, in the W437 shape.

    One weekday is every 7 days from that weekday; anything else (every day,
    weekdays, two days a week) has no single cadence and becomes every day.
    """
    days = sorted({int(d) for d in stored.get("days") or [] if str(d).isdigit() and 0 <= int(d) <= 6})
    if len(days) == 1:
        return {"time": stored.get("time"), "every_days": 7,
                "start": (_A_MONDAY + timedelta(days=days[0])).isoformat()}
    return {"time": stored.get("time"), "every_days": 1, "start": _A_MONDAY.isoformat()}


def of(stored: dict[str, Any] | None) -> dict[str, Any]:
    """A rule's schedule, the default when none is stored or it no longer reads.

    Reads a W436 weekday schedule too. ⚠️ Never raises: it runs on every page
    render and every scheduler tick, and a row that can't be read must not stop
    the rest being checked.
    """
    if not stored:
        return dict(DEFAULT)
    try:
        if "days" in stored and "every_days" not in stored:
            stored = _from_weekdays(stored)
        return validate(stored, today=_A_MONDAY)
    except ScheduleError:
        return dict(DEFAULT)


def _clock(schedule: dict[str, Any]) -> time:
    hours, minutes = schedule["time"].split(":")
    return time(int(hours), int(minutes))


def _instant(day: date, at: time, tz: tzinfo) -> datetime:
    """One local date and time as a UTC instant; fold=0, as `clock.from_local`."""
    return datetime.combine(day, at).replace(tzinfo=tz, fold=0).astimezone(timezone.utc)


def _on_or_before(schedule: dict[str, Any], day: date) -> date:
    """The latest run date on or before `day` (the cadence runs both ways)."""
    start = date.fromisoformat(schedule["start"]) if schedule["start"] else _A_MONDAY
    return day - timedelta(days=(day - start).days % schedule["every_days"])


def previous_slot(schedule: dict[str, Any] | None, now: datetime, tz: tzinfo) -> datetime:
    """The latest scheduled instant at or before `now`."""
    schedule = of(schedule)
    at, step = _clock(schedule), timedelta(days=schedule["every_days"])
    day = _on_or_before(schedule, now.astimezone(tz).date())
    slot = _instant(day, at, tz)
    while slot > now:
        day -= step
        slot = _instant(day, at, tz)
    return slot


def next_slot(schedule: dict[str, Any] | None, now: datetime, tz: tzinfo) -> datetime:
    """The first scheduled instant after `now`."""
    schedule = of(schedule)
    at, step = _clock(schedule), timedelta(days=schedule["every_days"])
    day = _on_or_before(schedule, now.astimezone(tz).date())
    slot = _instant(day, at, tz)
    while slot <= now:
        day += step
        slot = _instant(day, at, tz)
    return slot


def is_due(schedule: dict[str, Any] | None, last_run: datetime | None, now: datetime, tz: tzinfo) -> bool:
    """Whether a slot has come round since the rule last ran on schedule."""
    return last_run is None or previous_slot(schedule, now, tz) > last_run


def describe(schedule: dict[str, Any] | None) -> str:
    """ "Every day at 06:00", "Every 3 days at 06:00". """
    schedule = of(schedule)
    every = schedule["every_days"]
    when = "Every day" if every == 1 else f"Every {every} days"
    return f"{when} at {schedule['time']}"
