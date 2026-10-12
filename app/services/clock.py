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

"""What time the console says it is (W163).

Everything this system stores is UTC and stays UTC: `UtcDateTime` normalizes on
the way in and out, the agent reports epoch milliseconds, and the wire schema is
unambiguous. That is the right decision and none of it changes here.

⚠️ **This module is display only.** Nothing in it may be used to decide anything —
not an expiry, not a retention cutoff, not whether a fix is stale. A local time is
a rendering of an instant for a human to read, and the moment one is compared
against another the DST transitions start producing hours that happen twice and
hours that never happen at all. Convert at the edge, in the template, and nowhere
else.

⚠️ **`zoneinfo` needs an IANA database that is not part of Python.** Neither
`python:3.13-slim` nor Windows ships one, so both the container and this
workstation resolve zones only because the `tzdata` package is installed —
until W163 purely as a transitive dependency of `psycopg`. `requirements.txt`
now names it directly, because a psycopg release that dropped it would turn every
timestamp in the console into an exception.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

#: The setting that names the console's display zone.
SETTING_KEY = "general.timezone"

#: What the console uses when nothing is configured.
#:
#: UTC, and deliberately: it is what every stored timestamp already is, so an
#: unconfigured deployment renders exactly what it did before this existed. A
#: default of "the server's local zone" would make the console's output depend on
#: a host setting nobody administering ATLAS can see.
DEFAULT_TIMEZONE = "UTC"

UTC = timezone.utc


def available() -> list[str]:
    """Every zone an operator may choose, UTC first and the rest alphabetical.

    UTC is lifted out of the alphabetical run because it is the default and the
    one most likely to be wanted deliberately; leaving it filed under "U" between
    `US/Samoa` and `W-SU` hides the one answer that is always correct.
    """
    zones = sorted(available_timezones())
    rest = [z for z in zones if z != DEFAULT_TIMEZONE]
    return [DEFAULT_TIMEZONE, *rest]


def zone(name: str | None) -> ZoneInfo | timezone:
    """Resolve a zone name, falling back to UTC rather than raising.

    ⚠️ **This must never raise**, and that is not defensive habit — it runs on
    every page render. A zone name is a string an operator picked from a list that
    a future release may rename (the IANA database does retire names), and the
    failure of raising here is not a wrong time on one page, it is the entire
    console returning 500 until someone with database access fixes a settings row.
    """
    if not name or not name.strip():
        return UTC
    candidate = name.strip()
    if candidate == DEFAULT_TIMEZONE:
        return UTC
    try:
        return ZoneInfo(candidate)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        logger.warning(
            "%s is %r, which is not a known timezone; showing times in UTC",
            SETTING_KEY,
            candidate,
        )
        return UTC


def configured(session: Session) -> ZoneInfo | timezone:
    """The console's display zone, as set in Admin → General."""
    from app.services import settings_store

    return zone(settings_store.get(session, SETTING_KEY, DEFAULT_TIMEZONE))


def to_zone(moment: datetime, tz: ZoneInfo | timezone) -> datetime:
    """The same instant, expressed in ``tz``.

    ⚠️ A naive datetime is read as UTC. Everything reaching the templates through
    `UtcDateTime` is already aware, but not everything reaching them comes from the
    database, and the alternative — letting Python attach the *server's* local zone
    — would silently shift a timestamp by the host's offset. That is a bug that
    looks like correct behaviour on a machine set to UTC, which is every machine
    this has ever been developed on.
    """
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(tz)


def label(tz: ZoneInfo | timezone, moments: Iterable[datetime | None] = ()) -> str:
    """How to name this zone where a column of times is labelled once.

    A table whose rows carry no suffix needs its header to say which zone they
    are in, and the obvious answer — the current abbreviation — is wrong for a
    column that spans a daylight-saving transition. Half the rows would be PDT
    under a header reading PST, with nothing to indicate it.

    ⚠️ So the abbreviation is used **only when every row agrees on it**. When
    they do not, the header falls back to the zone's full name, which is true of
    all of them. The cost is a longer header twice a year; the alternative is a
    header that is silently wrong for some of the rows beneath it.
    """
    seen = {to_zone(m, tz).strftime("%Z") for m in moments if m is not None}
    if len(seen) == 1:
        return seen.pop()
    if not seen:
        # An empty table still needs a header. Nothing is being mislabelled.
        return datetime.now(UTC).astimezone(tz).strftime("%Z")
    return getattr(tz, "key", None) or DEFAULT_TIMEZONE


#: What `<input type="datetime-local">` sends, and what it accepts back. Seconds
#: are optional in the HTML spec and browsers differ on emitting them.
_LOCAL_FORMATS = ("%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S")


def from_local(text: str, tz: ZoneInfo | timezone) -> datetime:
    """Read an operator-typed local date and time as a UTC instant (W191).

    ⚠️ **This is the one thing in this module that feeds a decision**, and it
    does not break the rule at the top: it is a conversion *at the edge*, turning
    a human's local wall-clock into the instant everything downstream compares.
    What is forbidden is carrying a local time inward and comparing it there.

    ⚠️ **Two local times a year are not instants at all**, and neither is an
    error the operator can act on:

    * The hour that happens twice, when clocks go back. ``fold=0`` takes the
      first — the earlier instant, so a deployment scheduled in that hour lands
      at the sooner of the two candidates rather than an hour late.
    * The hour that never happens, when clocks go forward. Python resolves it by
      shifting, and the deployment lands at the equivalent real instant.

    Refusing either would be worse: the operator picked a time their calendar
    shows, and the only honest response is to deploy near it and *say which
    instant was understood*, which is what the console echoes back.

    Raises ``ValueError`` if the text is not a date and time at all.
    """
    candidate = (text or "").strip()
    for fmt in _LOCAL_FORMATS:
        try:
            naive = datetime.strptime(candidate, fmt)
        except ValueError:
            continue
        return naive.replace(tzinfo=tz, fold=0).astimezone(UTC)
    raise ValueError(f"{text!r} is not a date and time")


def to_local_input(moment: datetime | None, tz: ZoneInfo | timezone) -> str:
    """Render an instant for a ``datetime-local`` field, or "" if there is none.

    The inverse of :func:`from_local`, so re-opening a form shows the time the
    operator typed rather than UTC — which would otherwise drift the schedule by
    the zone offset on every save.
    """
    if moment is None:
        return ""
    return to_zone(moment, tz).strftime("%Y-%m-%dT%H:%M")


def format(moment: datetime | None, tz: ZoneInfo | timezone, fmt: str) -> str:
    """Render one instant for a human, or the empty string if there is none.

    The empty string rather than an exception: a template asking for a timestamp
    that is legitimately absent — a device that has never checked in, a policy
    never archived — should print nothing, and every call site guarding for `None`
    itself is 22 chances to forget.
    """
    if moment is None:
        return ""
    return to_zone(moment, tz).strftime(fmt)
