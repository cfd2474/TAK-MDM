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

"""The attestation exchange at check-in (W323 chunk 3).

The server hands a device a fresh challenge; the agent answers on a later
check-in with a key attested against it; :mod:`key_attestation` judges the
chain. One challenge, answered once (W323 D-f): a chain replayed from another
device, or from yesterday, answers a different challenge and is ignored.
"""

from __future__ import annotations

import base64
import binascii
import logging
import secrets
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppPackage, Device
from app.services import attestation_status, key_attestation

log = logging.getLogger(__name__)

#: How often a device is asked to attest again.
REATTEST_AFTER = timedelta(hours=24)
#: How long an issued challenge stays answerable.
CHALLENGE_VALID_FOR = timedelta(hours=24)


def challenge_for(device: Device, now: datetime) -> str | None:
    """The challenge to send this check-in, or None when no attestation is due."""
    if device.attested_at is not None and now - device.attested_at < REATTEST_AFTER:
        return None
    issued = device.attestation_challenge_at
    if device.attestation_challenge and issued is not None and now - issued < CHALLENGE_VALID_FOR:
        return device.attestation_challenge
    device.attestation_challenge = secrets.token_hex(32)
    device.attestation_challenge_at = now
    return device.attestation_challenge


def _agent_digests(session: Session, package: str) -> set[str] | None:
    pinned = session.scalars(
        select(AppPackage.signature_sha256).where(AppPackage.package_name == package)
    ).first()
    return {pinned.lower()} if pinned else None


def accept(session: Session, device: Device, challenge: str, chain_b64: list[str],
           now: datetime) -> bool:
    """Judge an answer and store the verdict. False when it answers nothing we asked."""
    from app.config import get_settings

    issued = device.attestation_challenge_at
    if (
        not device.attestation_challenge
        or challenge != device.attestation_challenge
        or issued is None
        or now - issued >= CHALLENGE_VALID_FOR
    ):
        log.info("attestation from %s ignored: not the outstanding challenge", device.serial_number)
        return False
    try:
        chain = [base64.b64decode(c, validate=True) for c in chain_b64]
    except (binascii.Error, ValueError):
        chain = []

    package = get_settings().agent_package_name
    verdict = key_attestation.verify(
        chain,
        challenge=bytes.fromhex(challenge),
        agent_package=package,
        revoked=attestation_status.revoked_serials(now),
        agent_digests=_agent_digests(session, package),
    )
    device.attestation = {
        "ok": verdict.ok,
        "problems": verdict.problems,
        "revocation_checked": verdict.revocation_checked,
        "facts": verdict.facts,
    }
    device.attested_at = now
    # Answered: the next attestation needs a new challenge.
    device.attestation_challenge = None
    device.attestation_challenge_at = None
    return True


def summary(attestation: dict[str, Any] | None) -> str:
    """One line for the device page and the rule's detail."""
    if not attestation:
        return "Not attested yet"
    facts = attestation.get("facts") or {}
    parts = []
    if facts.get("bootloader_locked") is not None:
        parts.append("bootloader locked" if facts["bootloader_locked"] else "bootloader unlocked")
    if facts.get("verified_boot"):
        parts.append(f"boot {facts['verified_boot'].replace('_', ' ')}")
    if facts.get("security_level"):
        parts.append({"tee": "secure hardware (TEE)", "strongbox": "StrongBox",
                      "software": "software only"}.get(facts["security_level"], facts["security_level"]))
    if facts.get("attested_patch"):
        parts.append(f"patch {facts['attested_patch']}")
    return ", ".join(parts) or "No details"
