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
