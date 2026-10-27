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

"""Reading the audit log back: search, today's activity, CSV (W421 C3).

`services.audit` writes and verifies the chain; this only reads it, for the
console page and its export.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.db.models import AuditEvent

#: The action a user's first request of the day is recorded under.
FIRST_SEEN = "console.first_seen"

PAGE_SIZE = 100


@dataclass
class Filters:
    actor: str = ""
    #: An exact action, or a prefix ending in "." ("device." for every device action).
    action: str = ""
    target_type: str = ""
    target_id: str = ""
    outcome: str = ""
    #: Console-local dates, inclusive.
    since: date | None = None
    until: date | None = None

    @property
    def any(self) -> bool:
        return any((self.actor, self.action, self.target_type, self.target_id, self.outcome,
                    self.since, self.until))


def _day_start(day: date, tz: ZoneInfo | timezone) -> datetime:
    return datetime.combine(day, time.min, tzinfo=tz).astimezone(timezone.utc)


def _filtered(query: Select, filters: Filters, tz: ZoneInfo | timezone) -> Select:
    if filters.actor:
        query = query.where(AuditEvent.actor == filters.actor)
    if filters.action.endswith("."):
        query = query.where(AuditEvent.action.startswith(filters.action, autoescape=True))
    elif filters.action:
        query = query.where(AuditEvent.action == filters.action)
    if filters.target_type:
        query = query.where(AuditEvent.target_type == filters.target_type)
    if filters.target_id:
        query = query.where(AuditEvent.target_id == filters.target_id.lower())
    if filters.outcome:
        query = query.where(AuditEvent.outcome == filters.outcome)
    if filters.since:
        query = query.where(AuditEvent.occurred_at >= _day_start(filters.since, tz))
    if filters.until:
        query = query.where(AuditEvent.occurred_at < _day_start(filters.until + timedelta(days=1), tz))
    return query


def search(session: Session, filters: Filters, tz: ZoneInfo | timezone, *,
           page: int = 1, page_size: int = PAGE_SIZE) -> tuple[list[AuditEvent], int]:
    """One page of matching rows, newest first, and how many match in all."""
    total = session.scalar(_filtered(select(func.count()).select_from(AuditEvent), filters, tz)) or 0
    rows = session.scalars(
        _filtered(select(AuditEvent), filters, tz)
        .order_by(AuditEvent.seq.desc())
        .offset(max(page - 1, 0) * page_size)
        .limit(page_size)
    )
    return list(rows), total


def every(session: Session, filters: Filters, tz: ZoneInfo | timezone):
    """Every matching row, newest first, streamed: what the CSV is made of."""
    return session.scalars(
        _filtered(select(AuditEvent), filters, tz)
        .order_by(AuditEvent.seq.desc())
        .execution_options(yield_per=1000)
    )


def actors(session: Session) -> list[str]:
    return list(session.scalars(select(AuditEvent.actor).distinct().order_by(AuditEvent.actor)))


def actions(session: Session) -> list[str]:
    return list(session.scalars(select(AuditEvent.action).distinct().order_by(AuditEvent.action)))


@dataclass
class Presence:
    actor: str
    first_seen: datetime
    last_seen: datetime
    changes: int


def today(session: Session, tz: ZoneInfo | timezone, *, now: datetime | None = None) -> list[Presence]:
    """Who has used the console today (console time), earliest first.

    ⚠️ "First seen" is the first request of the day, read or change, which the
    trail records once per user per day: a user who only looked is here too.
    """
    moment = now or datetime.now(timezone.utc)
    start = _day_start(moment.astimezone(tz).date(), tz)
    rows = session.execute(
        select(
            AuditEvent.actor,
            func.min(AuditEvent.occurred_at),
            func.max(AuditEvent.occurred_at),
            func.count().filter(AuditEvent.action != FIRST_SEEN),
        )
        .where(AuditEvent.occurred_at >= start)
        .group_by(AuditEvent.actor)
        .order_by(func.min(AuditEvent.occurred_at))
    )
    return [Presence(actor, first, last, changes or 0) for actor, first, last, changes in rows]


def seen_today(session: Session, actor: str, tz: ZoneInfo | timezone, *, now: datetime | None = None) -> bool:
    moment = now or datetime.now(timezone.utc)
    start = _day_start(moment.astimezone(tz).date(), tz)
    return session.scalar(
        select(AuditEvent.id).where(AuditEvent.actor == actor, AuditEvent.action == FIRST_SEEN,
                                    AuditEvent.occurred_at >= start).limit(1)
    ) is not None


# --------------------------------------------------------------------------- #
# CSV
# --------------------------------------------------------------------------- #

COLUMNS = (
    ("seq", "#"), ("occurred_at", "When (UTC)"), ("actor", "User"), ("actor_groups", "Groups"),
    ("source_ip", "From"), ("action", "Action"), ("summary", "What"), ("outcome", "Outcome"),
    ("status_code", "Status"), ("target_type", "Target type"), ("target_id", "Target"),
    ("method", "Method"), ("path", "Path"), ("hash", "Hash"),
)


def _cell(value) -> str:
    """⚠️ Neutralise a formula: summaries carry operator-typed names (OWASP)."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")  # utc-by-design: an export, heading says UTC
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


def to_csv(rows) -> str:
    """⚠️ Times in UTC, and the heading says so: an export outlives the console
    setting that produced it."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([heading for _, heading in COLUMNS])
    for row in rows:
        writer.writerow([_cell(getattr(row, key)) for key, _ in COLUMNS])
    return out.getvalue()
