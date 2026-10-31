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

"""How long the audit log is kept, and the daily prune (W421 C4).

⚠️ **Removes from the start of the chain only**, by sequence number, so what
remains still verifies from its oldest row.

⚠️ **Every prune is itself recorded**, naming the last entry it removed, and
:func:`audit.verify` checks the oldest remaining entry is the one right after
it. Without that, deleting the oldest rows in the database would look exactly
like retention, the one edit the chain could not otherwise see.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import AppSetting, AuditEvent
from app.services import audit

KEY = "audit.retention_days"
DEFAULT_DAYS = 365
#: Long enough that a prune cannot erase what someone did this week.
MIN_DAYS = 30

#: Who a prune is recorded as.
SYSTEM = "system"


class RetentionError(ValueError):
    """A retention the console refuses, in words for the operator."""


def days(session: Session) -> int:
    """The configured window; 0 keeps everything."""
    row = session.get(AppSetting, KEY)
    try:
        value = int(row.value) if row is not None else DEFAULT_DAYS
    except (TypeError, ValueError):
        return DEFAULT_DAYS
    return value if value == 0 or value >= MIN_DAYS else DEFAULT_DAYS


def set_days(session: Session, value: int, *, by: str | None) -> None:
    if value != 0 and value < MIN_DAYS:
        raise RetentionError(f"keep the audit log for at least {MIN_DAYS} days, or 0 to keep it all")
    row = session.get(AppSetting, KEY)
    if row is None:
        session.add(AppSetting(key=KEY, value=str(value), updated_by=by))
        session.flush()  # so a second call in this session finds it, not a duplicate key
    else:
        row.value, row.updated_by = str(value), by


def describe(value: int) -> str:
    return "kept for ever" if value == 0 else f"kept for {value} days"


def prune(session: Session, *, now: datetime | None = None) -> int:
    """Remove entries older than the window, and record that it did. Commits."""
    window = days(session)
    if window == 0:
        return 0
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=window)
    # ⚠️ Locked before deleting, not only when the record is written: a writer
    # between the two would chain onto a tail that is being removed.
    audit._lock(session)
    # ⚠️ The newest *old* entry, then everything up to it by sequence: a prefix,
    # never a gap, whatever order the timestamps landed in.
    last = session.scalar(select(func.max(AuditEvent.seq)).where(AuditEvent.occurred_at < cutoff))
    newest = session.scalar(select(func.max(AuditEvent.seq)))
    if last is None or newest is None:
        return 0
    # ⚠️ **Never the newest entry.** With every row gone, the next one would
    # start the chain again at #1, and Verify would call that tampering. On a
    # box idle for longer than the window, one old entry outlives it.
    last = min(last, newest - 1)
    if last < 1:
        return 0
    removed = session.execute(delete(AuditEvent).where(AuditEvent.seq <= last)).rowcount or 0
    audit.record(
        session, actor=SYSTEM, source_ip=None, method="-", path="/audit/retention", status_code=None,
        description=audit.Description(
            audit.PRUNED, f"Removed {removed} entr{'y' if removed == 1 else 'ies'} older than "
            f"{window} days, up to #{last}",
            target_type="audit", target_id=str(last),
        ),
        now=now,
    )
    return removed
