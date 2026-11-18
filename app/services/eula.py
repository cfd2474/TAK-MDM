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

"""The end-user licence agreement: accepted on the device, or the device is
reset (W399).

Operator, 2026-10-15: "the user must accept the elua. rejection should factory
reset the device (sending the disenroll and reset signal back to the server)",
and no acceptance record: a device is either accepted and managed, or gone.

⚠️ **The text was stored and shown nowhere** before this. The Admin page said
"Shown to a user during provisioning, if your agent build displays it"; no
build did, and nothing read `eula.text`.

⚠️ **A decline is a W104 disenroll, not a wipe of its own.** The agent only
reports it; the server queues the same reset the console's Disenroll does, so
Factory Reset Protection is cleared, the certificates are revoked and the record
removed on the acknowledgement — one proven path rather than a second one the
agent runs alone, which would leave the record and certificates behind.

The version is a digest of the text, so an operator who edits it is asking
every device to accept the new words; nothing to bump by hand.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Device, DeviceCommand
from app.services import alerts, disenroll, settings_store

logger = logging.getLogger(__name__)

TEXT_KEY = "eula.text"
MODE_KEY = "eula.mode"
AGENCY_KEY = "eula.agency_name"
GENERIC, CUSTOM = "generic", "custom"
DECLINED_EVENT = "eula_declined"
#: In the cached effective payload: the version alone, so a changed EULA moves
#: every device's state_version (the comparison in `effective_policy.refresh`).
PAYLOAD_KEY = "eula_version"

#: The operator's generic agreement (2026-10-15), "[Agency Name]" filled in.
_GENERIC_TEMPLATE = Path(__file__).with_name("eula_generic.txt")
_PLACEHOLDER = "[Agency Name]"


def agency_name(session: Session) -> str:
    """The name the generic text carries: what the operator typed on the EULA
    tab, else the agency ATLAS was installed for (`TAKMDM_AGENCY_NAME`)."""
    return (settings_store.get(session, AGENCY_KEY).strip()
            or get_settings().agency_name.strip())


def generic_text(name: str) -> str:
    template = _GENERIC_TEMPLATE.read_text(encoding="utf-8")
    # ⚠️ An empty name would leave "issued by  (“Agency”)"; the placeholder
    # stays visible instead, which says plainly what is missing.
    return template.replace(_PLACEHOLDER, name.strip() or _PLACEHOLDER)


def current(session: Session) -> dict[str, Any] | None:
    """What the device must show, or None when no EULA is set."""
    if settings_store.get(session, MODE_KEY) == GENERIC:
        text = generic_text(agency_name(session))
    else:
        text = settings_store.get(session, TEXT_KEY)
    # Line endings normalised before the digest: a checkout that turned the
    # template into CRLF must not hand every device a "new" agreement.
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return None
    return {"text": text, "version": hashlib.sha256(text.encode("utf-8")).hexdigest()}


def version(session: Session) -> str | None:
    shown = current(session)
    return shown["version"] if shown else None


def declined(session: Session, device: Device) -> DeviceCommand:
    """The device's user declined: queue the disenroll reset. Idempotent, like
    `disenroll.request` — the agent repeats the report until it is reset."""
    if disenroll.pending(session, device) is None:
        logger.info("EULA declined on %s: disenrolling", device.serial_number)
        alerts.note_event(session, DECLINED_EVENT, device, device.serial_number)
    return disenroll.request(session, device)
