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

"""ATAK session logs a device uploaded: storing, replacing, keeping (W416).

Retention, as the operator agreed: per device the newest **20**, none older than
**14 days**, and the whole deployment under :data:`MAX_TOTAL_STORED_BYTES`,
oldest first. Pruned on every upload, which is the only time any of it grows.

⚠️ **An upload is checked by decompressing it, not by trusting its sizes.**
The agent sends gzip. A small gzip can expand without limit, so the body is
streamed through a decompressor with a ceiling (:data:`MAX_LOG_BYTES`) before
it is kept, and a file that is not gzip at all is refused rather than stored
and found broken when an operator downloads it.
"""

from __future__ import annotations

import gzip
import re
import uuid
import zlib
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from typing import BinaryIO

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.artifacts.atak_log_store import AtakLogStore, TooLarge
from app.db.models import AtakSessionLog, Device

#: Per device, newest first by when it arrived.
KEEP_PER_DEVICE = 20
MAX_AGE = timedelta(days=14)
#: Compressed, across the deployment.
MAX_TOTAL_STORED_BYTES = 2 * 1024 * 1024 * 1024
#: One upload, compressed. Text logs compress about tenfold.
MAX_UPLOAD_BYTES = 32 * 1024 * 1024
#: One session, uncompressed.
MAX_LOG_BYTES = 256 * 1024 * 1024

#: ATAK's own names: a ring of ten (platform reference §6, W416 C1).
_FILE_NAME = re.compile(r"^logcat[0-9]\.txt$")


class UploadRefused(ValueError):
    """The upload cannot be kept. The message says why."""


class UploadTooLarge(UploadRefused):
    pass


def _uncompressed_size(handle: BinaryIO) -> int:
    """Decompress `handle` with a ceiling. Returns the uncompressed size."""
    inflater = zlib.decompressobj(16 + zlib.MAX_WBITS)  # gzip framing
    total = 0
    try:
        while chunk := handle.read(1024 * 1024):
            total += len(inflater.decompress(chunk, MAX_LOG_BYTES + 1 - total))
            # Capped output: past the ceiling it stops inflating, so a small
            # body that expands without limit costs nothing to refuse.
            if total > MAX_LOG_BYTES:
                raise UploadTooLarge(f"the log is over {MAX_LOG_BYTES} bytes uncompressed")
        total += len(inflater.flush())
    except zlib.error as exc:
        raise UploadRefused(f"the log is not valid gzip: {exc}") from exc
    if not inflater.eof:
        raise UploadRefused("the log is not valid gzip: it ends early")
    if inflater.unused_data:
        raise UploadRefused("the log has data after its gzip stream")
    return total


def store(
    session: Session,
    store_: AtakLogStore,
    device: Device,
    body: BinaryIO,
    *,
    file_name: str,
    started_at: datetime | None,
    complete: bool,
    atak_version: str | None = None,
    now: datetime | None = None,
) -> tuple[AtakSessionLog, bool]:
    """Keep one uploaded session. Returns ``(row, kept)``.

    ⚠️ **A finished copy is never replaced by a running one.** Uploads can
    arrive out of order (a retry of the early copy after the finished one),
    and the finished copy holds everything the early one does.
    """
    if not _FILE_NAME.match(file_name or ""):
        raise UploadRefused(f"{file_name!r} is not one of ATAK's session log files")
    key = f"{file_name}@{started_at.isoformat() if started_at else 'unknown'}"

    row = session.scalar(
        select(AtakSessionLog).where(
            AtakSessionLog.device_id == device.id, AtakSessionLog.session_key == key
        )
    )
    if row is not None and row.complete and not complete:
        return row, False

    # Into the store under a fresh id, checked there, and only then put in
    # place: the body is a stream the client sends once, and a bad retry must
    # not destroy the good copy it was meant to replace.
    incoming = uuid.uuid4()
    try:
        stored = store_.put(incoming, body, max_bytes=MAX_UPLOAD_BYTES)
    except TooLarge as exc:
        raise UploadTooLarge(str(exc)) from exc
    try:
        with store_.open(incoming) as handle:
            size = _uncompressed_size(handle)
    except UploadRefused:
        store_.delete(incoming)
        raise

    if row is None:
        row = AtakSessionLog(id=incoming, device_id=device.id, session_key=key)
        session.add(row)
    else:
        store_.move(incoming, row.id)
    row.file_name = file_name
    row.started_at = started_at
    row.complete = complete
    row.size_bytes = size
    row.stored_bytes = stored
    row.atak_version = (atak_version or None) and atak_version[:64]
    row.uploaded_at = now or datetime.now(timezone.utc)
    session.flush()
    prune(session, store_, now=row.uploaded_at)
    return row, True


def prune(session: Session, store_: AtakLogStore, *, now: datetime | None = None) -> int:
    """Apply retention everywhere, then delete files no row names. Returns rows removed."""
    now = now or datetime.now(timezone.utc)
    doomed: set[uuid.UUID] = set(
        session.scalars(select(AtakSessionLog.id).where(AtakSessionLog.uploaded_at < now - MAX_AGE))
    )

    ranked = (
        select(
            AtakSessionLog.id,
            func.row_number()
            .over(partition_by=AtakSessionLog.device_id, order_by=AtakSessionLog.uploaded_at.desc())
            .label("n"),
        )
    ).subquery()
    doomed |= set(session.scalars(select(ranked.c.id).where(ranked.c.n > KEEP_PER_DEVICE)))

    total = 0
    for log_id, stored in session.execute(
        select(AtakSessionLog.id, AtakSessionLog.stored_bytes).order_by(AtakSessionLog.uploaded_at.desc())
    ):
        if log_id in doomed:
            continue
        total += stored
        if total > MAX_TOTAL_STORED_BYTES:
            doomed.add(log_id)

    if doomed:
        session.execute(delete(AtakSessionLog).where(AtakSessionLog.id.in_(doomed)))
        session.flush()
    store_.sweep(session.scalars(select(AtakSessionLog.id)))
    return len(doomed)


def list_for_device(session: Session, device_id: uuid.UUID) -> list[AtakSessionLog]:
    """Newest session first."""
    return list(
        session.scalars(
            select(AtakSessionLog)
            .where(AtakSessionLog.device_id == device_id)
            .order_by(AtakSessionLog.started_at.desc().nulls_last(), AtakSessionLog.uploaded_at.desc())
        )
    )


def get(session: Session, device_id: uuid.UUID, log_id: uuid.UUID) -> AtakSessionLog | None:
    """One log, only if it is this device's (so an id cannot reach another device's)."""
    row = session.get(AtakSessionLog, log_id)
    return row if row is not None and row.device_id == device_id else None


def text_chunks(store_: AtakLogStore, row: AtakSessionLog) -> Iterator[bytes]:
    """The log, decompressed, in chunks, for a download."""
    with store_.open(row.id) as handle, gzip.GzipFile(fileobj=handle) as text:
        while chunk := text.read(1024 * 1024):
            yield chunk


def download_name(device: Device, row: AtakSessionLog) -> str:
    """`atak-<serial>-<session start, UTC>-<file>.txt`."""
    who = re.sub(r"[^A-Za-z0-9._-]", "", device.serial_number or "") or "device"
    when = (row.started_at or row.uploaded_at).strftime("%Y%m%d-%H%M%SZ")  # utc-by-design: filename, marked Z
    return f"atak-{who}-{when}-{row.file_name}"


def parse_started_at(value: str | None) -> datetime | None:
    """The session's first timestamp as ATAK writes it (`2026-10-20T20:16:53.867Z`)."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise UploadRefused(f"{value!r} is not a timestamp") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

