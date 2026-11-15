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

"""The distrusted-CA list (W432): certificates no device should trust.

Two halves, merged into one list that every device receives in its signed
bundle and reports against:

- **Built in** (`BUILTIN`): vetted here, shipped with a server release, so a
  new incident is a server release and never an agent release. An operator
  cannot remove one.
- **The operator's own** (`DistrustedCa` rows), added in Admin › Distrusted
  CAs.

⚠️ **Matched by SHA-256 of the whole certificate, never by name.** A subject
string is free text any CA can reuse; a fingerprint names one certificate.

⚠️ **Every built-in fingerprint was hashed from the certificate itself**
(platform reference §6e), not copied from an advisory. Keep it that way: a
mistyped fingerprint here silently checks for nothing.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DistrustedCa

#: In the effective-policy payload: the merged fingerprints, so a list edit
#: gives exactly the devices whose list moved a new state_version.
PAYLOAD_KEY = "distrusted_cas"
#: In the signed bundle the agent reads.
BUNDLE_KEY = "distrusted_cas"


class CaListError(ValueError):
    """A distrusted-CA entry cannot be added or removed."""


@dataclass(frozen=True)
class Entry:
    sha256: str
    name: str
    reason: str | None
    added: date | None
    #: Where the fingerprint can be checked. Built-in entries only.
    source: str | None = None
    builtin: bool = False
    #: The operator's row, for removal. None for a built-in entry.
    id: uuid.UUID | None = None


_EMUDHRA = "https://bugzilla.mozilla.org/show_bug.cgi?id=2083449"
_EMUDHRA_REASON = (
    "eMudhra intermediate CA private keys compromised (October 2026). "
    "Fixed only by an OS or Google Play system update."
)
_EMUDHRA_ADDED = date(2026, 10, 25)


def _emudhra(sha256: str, name: str) -> Entry:
    return Entry(sha256, name, _EMUDHRA_REASON, _EMUDHRA_ADDED, _EMUDHRA, builtin=True)


#: Platform reference §6e. Only the root can be in a device's system store;
#: the rest matter as user-installed copies.
BUILTIN: tuple[Entry, ...] = (
    _emudhra("86A1ECBA089C4A8D3BBE2734C612BA341D813E043CF9E8A862CD5C57A36BBE6B",
             "emSign ECC Root CA - G3"),
    _emudhra("3094025792039A68AF6E553686410BDAB7C0D4A36B9084CBA64202E35D6EBBDD",
             "emSign Root TLS CA - G3 (cross-signed by emSign ECC Root CA - G3)"),
    _emudhra("E7568FE6E12331F4FD7DE61DA4C7559D0F8EB192A218D4741A3BA75184333838", "EM EV TLS CA - G3B"),
    _emudhra("98B896625C0C230ADEEC3EB2CF6AAD5001ECF9156A68644E82374CE5833BC25B", "EM OV TLS CA - G3B"),
    _emudhra("42C4ACCD12C4F59597925E1A08A7A90102608543809308D50EC427E118BA1493", "EM DV TLS CA - G3B"),
    _emudhra("432EC25F0D28DE9006D97BF752F17BBB2CD41F669933FCB072D9A1148D0261F3", "EM EV TLS CA - G3C"),
    _emudhra("CB6E15165AC802E9B3F993F16C25D41F4E81C21EBDE71AE1B012AC00BF9C7C3F", "EM OV TLS CA - G3C"),
    _emudhra("0164D7CEAE5BB909C272AF151FF44B1177AE9B47D9424B94F1D9558C30934D19", "EM DV TLS CA - G3C"),
    _emudhra("9E39DE2881273ACC225A149C72BA3E0F51424963669AB633EE1DC7DF5DB067B4", "EM OV CS CA - G3B"),
    _emudhra("4B2460A466F95FD40113BCDCCA2CEB29B3B093921DE45474DA7DF48874C630B1", "EM OV CS CA - G3C"),
)

#: Roots that must never be listed, each with why. ⚠️ AAA Certificate Services
#: also anchors the revoked Sectigo cross-signs of the eMudhra intermediates,
#: and it anchors a great deal of unrelated traffic: listing it would flag
#: every Android device in the fleet for nothing (platform reference §6e).
REFUSED: dict[str, str] = {
    "D7A7A0FB5D7E2731D771E9484EBCDEF71D5F0C3E0A2948782BC83EE0EA699EF4": (
        "AAA Certificate Services is a current Sectigo root that most Android "
        "devices rely on. Listing it would flag every device."
    ),
}

_HEX = re.compile(r"[0-9A-F]{64}")


def normalize(fingerprint: str) -> str:
    """A SHA-256 fingerprint as upper-case hex, from the forms tools print it in.

    Takes `AB:CD:…` (openssl, Settings), spaced or lower-case hex, and an
    optional `SHA256:` / `sha256 Fingerprint=` prefix.
    """
    text = (fingerprint or "").strip()
    text = re.sub(r"^(?:sha-?256(?:\s*fingerprint)?\s*[:=]?)", "", text, flags=re.I)
    text = re.sub(r"[\s:]", "", text).upper()
    if not _HEX.fullmatch(text):
        raise CaListError(
            "A SHA-256 fingerprint is 64 hexadecimal characters "
            "(colons and spaces are fine)."
        )
    return text


def entries(session: Session) -> list[Entry]:
    """Built-in entries first, in their own order, then the operator's by name."""
    own = session.scalars(select(DistrustedCa).order_by(DistrustedCa.name)).all()
    return list(BUILTIN) + [
        Entry(row.sha256, row.name, row.reason, row.created_at.date(), id=row.id)
        for row in own
    ]


def fingerprints(session: Session) -> list[str]:
    """What devices receive: every listed fingerprint, sorted, no duplicates."""
    return sorted({entry.sha256 for entry in entries(session)})


def add(session: Session, *, sha256: str, name: str, reason: str | None,
        added_by: str) -> DistrustedCa:
    fingerprint = normalize(sha256)
    name = (name or "").strip()
    if not name:
        raise CaListError("Give the certificate a name, so a report can say which one it found.")
    if len(name) > 200:
        raise CaListError("The name is too long (200 characters at most).")
    if fingerprint in REFUSED:
        raise CaListError(REFUSED[fingerprint])
    if any(entry.sha256 == fingerprint for entry in BUILTIN):
        raise CaListError("That certificate is already on the built-in list.")
    if session.scalar(select(DistrustedCa).where(DistrustedCa.sha256 == fingerprint)):
        raise CaListError("That certificate is already on the list.")
    row = DistrustedCa(
        sha256=fingerprint, name=name, reason=(reason or "").strip() or None,
        added_by=added_by[:128],
    )
    session.add(row)
    session.flush()
    return row


def remove(session: Session, entry_id: uuid.UUID) -> DistrustedCa:
    """Remove one of the operator's entries. A built-in entry has no row to remove."""
    row = session.get(DistrustedCa, entry_id)
    if row is None:
        raise CaListError("That entry is not on the list (built-in entries can't be removed).")
    session.delete(row)
    session.flush()
    return row
