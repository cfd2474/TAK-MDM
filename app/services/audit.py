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

"""The console audit log: who changed what, and when (W421).

Two layers, one row per change:

* **Every** unsafe admin request is recorded by `security.audit_trail`, attached
  where admin authentication is, so a route added tomorrow is covered without
  anyone remembering to.
* A handler with something readable to say calls :func:`describe`, and its
  words and target go into that same row: "published policy 'Field Kiosk' v7"
  rather than `POST /profiles/…/sections/kiosk`.

⚠️ **Never a request body.** Forms carry passwords, keys and tokens. A row says
what a handler chooses to say, and nothing else.

⚠️ **Hash-chained.** Each row's `hash` is sha256 over the previous row's hash
and this row's content, so an edit or deletion made directly in the database
breaks the chain from that row on, and :func:`verify` says where. Writes are
serialized so two requests cannot both chain onto the same predecessor.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import AuditEvent

#: The chain's first link.
GENESIS = "0" * 64

#: The action retention records a prune under; its target is the last seq removed.
PRUNED = "audit.pruned"

#: Postgres advisory-lock key serializing chain writes ("W421" in ASCII).
_LOCK_KEY = 0x57343231

#: The path segments that name a thing worth filtering by, and its type.
_TARGETS = {
    "devices": "device",
    "profiles": "policy",
    "policies": "policy",
    "packages": "app",
    "apps": "app",
    "groups": "group",
    "enrollment-tokens": "enrollment_token",
    "files": "file",
    "storefronts": "store",
    "certs": "certificate",
}
_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
_TARGET_IN_PATH = re.compile(r"/(" + "|".join(map(re.escape, _TARGETS)) + r")/(" + _UUID + r")")

#: Where a handler's description waits for the trail to write it.
STATE_KEY = "audit_description"


@dataclass
class Description:
    action: str
    summary: str
    target_type: str | None = None
    target_id: str | None = None


def describe(request, action: str, summary: str, *, target_type: str | None = None,
             target_id: str | uuid.UUID | None = None) -> None:
    """Say, in words, what this request did. Recorded with it by the trail.

    ⚠️ Never put a secret in `summary`: it is shown to every administrator and
    exported to CSV.
    """
    setattr(request.state, STATE_KEY, Description(
        action=action[:64], summary=summary,
        target_type=target_type, target_id=str(target_id) if target_id is not None else None,
    ))


def device_label(device) -> str:
    """A device as an operator recognises it: its name, then its serial."""
    serial = device.serial_number or str(device.id)
    return f"'{device.name}' ({serial})" if device.name else serial


def description_of(request) -> Description | None:
    return getattr(request.state, STATE_KEY, None)


def target_from_path(path: str) -> tuple[str | None, str | None]:
    """The first thing a path names, as (type, id), or (None, None)."""
    found = _TARGET_IN_PATH.search(path or "")
    if not found:
        return None, None
    return _TARGETS[found.group(1)], found.group(2).lower()


def outcome_of(status: int | None, refusal: str | None = None) -> str:
    if status is not None and status >= 500:
        return "failed"
    if refusal or (status is not None and status >= 400):
        return "refused"
    return "ok"


def _summary(description: Description | None, refusal: str | None) -> str | None:
    said = description.summary if description else None
    if not refusal:
        return said
    return f"{said} (refused: {refusal})" if said else f"Refused: {refusal}"


def _canonical(event: AuditEvent) -> bytes:
    """The bytes a row's hash covers, in a fixed order."""
    occurred = event.occurred_at
    if occurred.tzinfo is None:
        occurred = occurred.replace(tzinfo=timezone.utc)
    fields = [
        str(event.id), event.seq, occurred.astimezone(timezone.utc).isoformat(), event.actor,
        event.actor_groups, bool(event.anonymous), event.source_ip, event.method, event.path,
        event.action, event.target_type, event.target_id, event.summary, event.outcome,
        event.status_code, event.prev_hash,
    ]
    return json.dumps(fields, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _hash(event: AuditEvent) -> str:
    return hashlib.sha256(_canonical(event)).hexdigest()


def _lock(session: Session) -> None:
    """Serialize chain writes. Postgres only; SQLite serializes writers itself."""
    if session.get_bind().dialect.name == "postgresql":
        session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _LOCK_KEY})


def _last(session: Session) -> tuple[int, str]:
    """(seq, hash) of the newest row, or (0, GENESIS) for an empty log."""
    last = session.execute(
        select(AuditEvent.seq, AuditEvent.hash).order_by(AuditEvent.seq.desc()).limit(1)
    ).first()
    return (last.seq, last.hash) if last else (0, GENESIS)


def record(
    session: Session,
    *,
    actor: str,
    groups: tuple[str, ...] = (),
    anonymous: bool = False,
    source_ip: str | None,
    method: str,
    path: str,
    status_code: int | None,
    refusal: str | None = None,
    description: Description | None = None,
    now: datetime | None = None,
) -> AuditEvent:
    """Append one row to the chain. Commits; the caller passes a session of its own.

    `refusal` is the reason the console gave the operator when it said no
    without an error status (a redirect to `?error=…`).
    """
    _lock(session)
    last_seq, last_hash = _last(session)
    target_type, target_id = target_from_path(path)
    event = AuditEvent(
        id=uuid.uuid4(),
        seq=last_seq + 1,
        occurred_at=now or datetime.now(timezone.utc),
        actor=(actor or "unknown")[:128],
        actor_groups=",".join(groups)[:512] or None,
        anonymous=anonymous,
        source_ip=(source_ip or None) and source_ip[:64],
        method=method[:8],
        path=path[:512],
        action=description.action if description else "request",
        target_type=(description.target_type if description and description.target_type else target_type),
        target_id=(description.target_id if description and description.target_id else target_id),
        summary=_summary(description, refusal),
        outcome=outcome_of(status_code, refusal),
        status_code=status_code,
        prev_hash=last_hash,
    )
    event.hash = _hash(event)
    session.add(event)
    session.commit()
    return event


@dataclass
class ChainCheck:
    ok: bool
    checked: int
    #: The first row whose hash, or link to the row before it, doesn't hold.
    broken_at: AuditEvent | None = None
    #: Why, in words for the page.
    reason: str = ""


def _expected_first(session: Session) -> int:
    """The seq the oldest remaining row should have: 1, or one past the last prune."""
    pruned = session.scalar(
        select(AuditEvent.target_id).where(AuditEvent.action == PRUNED).order_by(AuditEvent.seq.desc()).limit(1)
    )
    try:
        return int(pruned) + 1 if pruned else 1
    except ValueError:
        return 1


def verify(session: Session) -> ChainCheck:
    """Walk the chain oldest first.

    ⚠️ The oldest remaining row's `prev_hash` is taken as given, because
    retention removes old rows. What it may not be is anything other than the
    row right after the last recorded prune: rows missing from the start that
    no prune accounts for were removed by someone else.
    """
    expected = _expected_first(session)
    rows = session.scalars(select(AuditEvent).order_by(AuditEvent.seq).execution_options(yield_per=1000))
    previous: str | None = None
    checked = 0
    for row in rows:
        if previous is None and row.seq != expected:
            return ChainCheck(False, checked, row,
                              f"entries before it are missing and no retention prune removed them "
                              f"(the oldest should be #{expected})")
        if previous is not None and row.prev_hash != previous:
            return ChainCheck(False, checked, row, "the entry before it was changed or removed")
        if _hash(row) != row.hash:
            return ChainCheck(False, checked, row, "it was changed after it was written")
        previous = row.hash
        checked += 1
    return ChainCheck(True, checked)
