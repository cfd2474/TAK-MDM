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

"""ATAK's configuration as a .pref, extracted through the ATLAS plugin (W433).

Operator, 2026-10-26: a command on the device page that has ATAK write a .pref
of its current configuration, uploaded for download, kept as a line item until
deleted, named ``<DeviceName>.pref_extract.<MMDDYYYY.HH.MM.SS>.pref``.

The flow (contract `pref_extract`): an admin asks, which makes a row here and
queues the `extract_atak_prefs` command. The agent writes a request file and
acknowledges the command. The plugin exports the next time ATAK runs, and the
agent uploads the file, or the plugin's error, keyed by the command id.

⚠️ **Sensitive.** The export is kept exactly as ATAK writes it (operator's
decision), and it can carry a plaintext certificate password (platform
reference §10). Admins only, downloads and deletes audited, and the content is
never logged: not here, not in an error message.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AtakPrefExtract, CommandType, Device
from app.services import commands as command_service
from app.services import plugin_status

REQUESTED = "requested"
READY = "ready"
FAILED = "failed"

#: The plugin capability that says this build can export (contract).
CAPABILITY = "pref_extract"

#: The contract's cap. A .pref is the four preference groups as XML, a few KB
#: in practice; data packages are not inlined.
MAX_BYTES = 2 * 1024 * 1024


class ExtractError(ValueError):
    """An extract cannot be requested or stored."""


class ExtractTooLarge(ExtractError):
    """The upload is over :data:`MAX_BYTES`."""


class UnknownRequest(ExtractError):
    """No request with that id for this device (never made, or deleted)."""


def supported(device: Device) -> bool:
    """Whether this device's ATLAS plugin says it can export (`capabilities`)."""
    status = plugin_status.read(device.atlas_plugin_report, device.atlas_plugin_reported_at)
    return status is not None and CAPABILITY in status.capabilities


def request(session: Session, device: Device, *, requested_by: str) -> AtakPrefExtract:
    """Ask the device for an extract: the waiting row and its doorbell."""
    if not supported(device):
        raise ExtractError(
            "This device's ATLAS plugin can't extract ATAK's preferences yet "
            "(it needs plugin 1.4.0 or later, reporting in)."
        )
    command = command_service.enqueue(session, device, command_type=CommandType.EXTRACT_ATAK_PREFS)
    extract = AtakPrefExtract(
        device_id=device.id, command_id=command.id, status=REQUESTED,
        requested_by=(requested_by or "unknown")[:128],
    )
    session.add(extract)
    session.flush()
    return extract


_UNSAFE = re.compile(r"[^A-Za-z0-9 ._-]+")


def file_name(device: Device, received_at: datetime) -> str:
    """`<DeviceName>.pref_extract.<MMDDYYYY.HH.MM.SS>.pref`, the time in UTC.

    The device's name, else its serial, with anything a file system or a
    download header could misread (separators, quotes, control characters)
    replaced by `_`.
    """
    name = _UNSAFE.sub("_", (device.name or "").strip()).strip(" .") or \
        _UNSAFE.sub("_", device.serial_number or str(device.id))
    # The operator chose UTC for the name (2026-10-26), not the console zone.
    stamp = received_at.astimezone(timezone.utc).strftime("%m%d%Y.%H.%M.%S")  # utc-by-design: operator's choice for the file name
    return f"{name[:120]}.pref_extract.{stamp}.pref"


def receive(
    session: Session,
    device: Device,
    *,
    command_id: uuid.UUID,
    ok: bool,
    content: str | None,
    error: str | None,
    atak_version: str | None,
    now: datetime | None = None,
) -> AtakPrefExtract:
    """Store what the agent brought back for one request.

    Idempotent: a retried upload of a request already answered changes
    nothing, so a lost response can't name the file twice.
    """
    extract = session.scalar(
        select(AtakPrefExtract).where(
            AtakPrefExtract.device_id == device.id, AtakPrefExtract.command_id == command_id
        )
    )
    if extract is None:
        raise UnknownRequest("no such request for this device; it may have been deleted")
    if extract.status == READY:
        return extract

    if ok:
        if content is None:
            raise ExtractError("an extract reported ok carries no file")
        size = len(content.encode("utf-8"))
        if size > MAX_BYTES:
            raise ExtractTooLarge(f"the file is {size} bytes; the limit is {MAX_BYTES}")
        received = now or datetime.now(timezone.utc)
        extract.status = READY
        extract.content = content
        extract.size_bytes = size
        extract.received_at = received
        extract.file_name = file_name(device, received)
        extract.error = None
    else:
        extract.status = FAILED
        extract.received_at = now or datetime.now(timezone.utc)
        extract.error = (error or "the plugin gave no reason")[:2000]
    extract.atak_version = (atak_version or None) and atak_version[:64]
    session.flush()
    return extract


def list_for_device(session: Session, device_id: uuid.UUID) -> list[AtakPrefExtract]:
    """Newest request first."""
    return list(session.scalars(
        select(AtakPrefExtract).where(AtakPrefExtract.device_id == device_id)
        .order_by(AtakPrefExtract.requested_at.desc())
    ))


def get(session: Session, device_id: uuid.UUID, extract_id: uuid.UUID) -> AtakPrefExtract | None:
    extract = session.get(AtakPrefExtract, extract_id)
    return extract if extract is not None and extract.device_id == device_id else None


def delete(session: Session, extract: AtakPrefExtract) -> None:
    """Remove it, waiting or not. A late upload for it then gets 'unknown request'."""
    session.delete(extract)
    session.flush()
