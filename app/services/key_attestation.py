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

"""Verifying Android hardware key attestation (W323 chunk 3).

The agent makes a key in the device's secure hardware with a challenge from us,
and sends the certificate chain Android gives it. The leaf carries an
extension, written by the secure hardware, saying how the device booted. This
module checks that chain and reads that extension. Pure: anchors, revocations
and the expected challenge are parameters.

📖 **Sources, not recollection** (all fetched 2026-10-03):

* **Roots:** `https://android.googleapis.com/attestation/root`, matching the PEMs
  on developer.android.com's key-attestation page. Google re-issued the RSA root
  several times **with one key**, so anchors are root *public keys* (SHA-256 of
  the SubjectPublicKeyInfo), not certificates.
* **Revocation:** `https://android.googleapis.com/attestation/status`; entries are
  keyed by certificate serial in **lowercase hex**.
* **Schema:** AOSP "Key and ID attestation". Extension OID
  1.3.6.1.4.1.11129.2.1.17. ``KeyDescription`` = (attestationVersion,
  attestationSecurityLevel, keyMintVersion, keyMintSecurityLevel,
  attestationChallenge, uniqueId, softwareEnforced, hardwareEnforced).
  ``RootOfTrust`` [704] = (verifiedBootKey, deviceLocked, verifiedBootState,
  verifiedBootHash). osPatchLevel [706] is YYYYMM. attestationApplicationId [709]
  is an OCTET STRING wrapping (package_infos SET OF (name, version),
  signature_digests SET OF OCTET STRING).

⚠️ **Certificate validity dates are not checked (W323 D-h).** Many devices put
placeholder dates on attestation leaves; what is checked is the signatures, the
root key and the revocation list.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from cryptography import x509
from cryptography.hazmat.primitives import serialization

#: SHA-256 of the SubjectPublicKeyInfo of each Google attestation root.
GOOGLE_ROOT_KEYS = frozenset({
    # RSA-4096 root, serial f92009e853b6b045, re-issued to 2026/2034/2036/2042.
    "feb2ea7551ee316ed4bb443c8293b884dbfdea40b603ee3e4f4a897e4580fbae",
    # EC P-384 "Key Attestation CA1", to 2035.
    "3ee44512a1af2beb39c889490c60ea3f82e43f5d5a5532f5ab9419f676cd07ec",
})

EXTENSION_OID = x509.ObjectIdentifier("1.3.6.1.4.1.11129.2.1.17")

SECURITY_LEVELS = {0: "software", 1: "tee", 2: "strongbox"}
BOOT_STATES = {0: "verified", 1: "self_signed", 2: "unverified", 3: "failed"}

_ROOT_OF_TRUST = 704
_OS_PATCH_LEVEL = 706
_APPLICATION_ID = 709


class AttestationError(ValueError):
    """The chain or its extension could not be read at all."""


# --------------------------------------------------------------------------- #
# A minimal DER reader: just enough for KeyDescription
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Tlv:
    cls: int          # 0 universal, 2 context-specific
    constructed: bool
    tag: int
    value: bytes


def _read(buf: bytes, i: int) -> tuple[Tlv, int]:
    try:
        first = buf[i]
        i += 1
        cls, constructed, tag = first >> 6, bool(first & 0x20), first & 0x1F
        if tag == 0x1F:  # high-tag-number form, e.g. [704]
            tag = 0
            while True:
                b = buf[i]
                i += 1
                tag = (tag << 7) | (b & 0x7F)
                if not b & 0x80:
                    break
        length = buf[i]
        i += 1
        if length & 0x80:
            count = length & 0x7F
            if count == 0 or count > 4:
                raise AttestationError("unsupported DER length")
            length = int.from_bytes(buf[i:i + count], "big")
            i += count
        if i + length > len(buf):
            raise AttestationError("DER value runs past its buffer")
        return Tlv(cls, constructed, tag, buf[i:i + length]), i + length
    except IndexError as exc:
        raise AttestationError("truncated DER") from exc


def _children(value: bytes) -> list[Tlv]:
    out, i = [], 0
    while i < len(value):
        tlv, i = _read(value, i)
        out.append(tlv)
    return out


def _int(tlv: Tlv) -> int:
    return int.from_bytes(tlv.value, "big", signed=True)


def _tagged(auth_list: Tlv) -> dict[int, Tlv]:
    """An AuthorizationList's [n] EXPLICIT entries, unwrapped, by tag number."""
    out: dict[int, Tlv] = {}
    for child in _children(auth_list.value):
        if child.cls == 2:
            inner = _children(child.value)
            if inner:
                out[child.tag] = inner[0]
    return out


# --------------------------------------------------------------------------- #
# The extension
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class KeyDescription:
    attestation_version: int
    security_level: int
    challenge: bytes
    device_locked: bool | None
    boot_state: int | None
    os_patch_level: int | None
    app_packages: tuple[str, ...]
    app_digests: tuple[str, ...]


def parse_key_description(der: bytes) -> KeyDescription:
    top, _ = _read(der, 0)
    fields = _children(top.value)
    if len(fields) < 8:
        raise AttestationError("KeyDescription has too few fields")
    software, hardware = _tagged(fields[6]), _tagged(fields[7])

    device_locked = boot_state = None
    root = hardware.get(_ROOT_OF_TRUST) or software.get(_ROOT_OF_TRUST)
    if root is not None:
        parts = _children(root.value)
        if len(parts) >= 3:
            device_locked = parts[1].value not in (b"", b"\x00")
            boot_state = _int(parts[2])

    patch = hardware.get(_OS_PATCH_LEVEL) or software.get(_OS_PATCH_LEVEL)

    packages: list[str] = []
    digests: list[str] = []
    app = software.get(_APPLICATION_ID) or hardware.get(_APPLICATION_ID)
    if app is not None:
        app_id, _ = _read(app.value, 0)
        sets = _children(app_id.value)
        if sets:
            for info in _children(sets[0].value):
                parts = _children(info.value)
                if parts:
                    packages.append(parts[0].value.decode("utf-8", "replace"))
        if len(sets) > 1:
            digests = [d.value.hex() for d in _children(sets[1].value)]

    return KeyDescription(
        attestation_version=_int(fields[0]),
        security_level=_int(fields[1]),
        challenge=fields[4].value,
        device_locked=device_locked,
        boot_state=boot_state,
        os_patch_level=_int(patch) if patch is not None else None,
        app_packages=tuple(packages),
        app_digests=tuple(digests),
    )


# --------------------------------------------------------------------------- #
# The verdict
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Verdict:
    #: True only when every check passed *and* revocation was checked.
    ok: bool
    #: What failed, in words an operator can act on. Empty when ok.
    problems: list[str] = field(default_factory=list)
    #: False when the revocation list wasn't available (W323 D-i).
    revocation_checked: bool = True
    #: What the hardware said, for the device page.
    facts: dict[str, Any] = field(default_factory=dict)


def _spki_sha256(cert: x509.Certificate) -> str:
    spki = cert.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return hashlib.sha256(spki).hexdigest()


def verify(
    chain_der: list[bytes],
    *,
    challenge: bytes,
    agent_package: str,
    anchors: frozenset[str] | None = None,
    revoked: set[str] | None = None,
    agent_digests: set[str] | None = None,
) -> Verdict:
    """Check a chain, leaf first, against everything W323 D-g requires.

    ``revoked`` is the set of revoked serials in lowercase hex, or None when the
    list couldn't be had. ``agent_digests`` are the SHA-256s of the agent's
    signing certificate, or None to skip that check.
    """
    anchors = GOOGLE_ROOT_KEYS if anchors is None else anchors
    problems: list[str] = []
    try:
        chain = [x509.load_der_x509_certificate(c) for c in chain_der]
    except ValueError as exc:
        return Verdict(False, [f"A certificate in the chain could not be read ({exc})"])
    if len(chain) < 2:
        return Verdict(False, ["The chain is too short to reach a root"])

    for child, parent in zip(chain, chain[1:]):
        try:
            child.verify_directly_issued_by(parent)
        except Exception:
            return Verdict(False, ["The certificate chain does not verify"])
    # ⚠️ Anchored by the last certificate's *key*, not by it being self-signed:
    # every link above was verified with that key, which is what a forger lacks.
    if _spki_sha256(chain[-1]) not in anchors:
        return Verdict(False, ["The chain does not end at a Google attestation root"])

    if revoked is not None:
        if any(format(c.serial_number, "x") in revoked for c in chain):
            problems.append("A certificate in the chain is revoked or suspended by Google")

    try:
        ext = chain[0].extensions.get_extension_for_oid(EXTENSION_OID)
    except x509.ExtensionNotFound:
        return Verdict(False, ["The key has no attestation record"])
    try:
        record = parse_key_description(ext.value.value)
    except AttestationError as exc:
        return Verdict(False, [f"The attestation record could not be read ({exc})"])

    facts = {
        "security_level": SECURITY_LEVELS.get(record.security_level, str(record.security_level)),
        "bootloader_locked": record.device_locked,
        "verified_boot": BOOT_STATES.get(record.boot_state, None) if record.boot_state is not None else None,
        "attestation_version": record.attestation_version,
    }
    if record.os_patch_level and record.os_patch_level > 190001:
        facts["attested_patch"] = f"{record.os_patch_level // 100:04d}-{record.os_patch_level % 100:02d}"

    if record.challenge != challenge:
        problems.append("The attestation answers a different challenge")
    if record.security_level not in (1, 2):
        problems.append("The key is not in secure hardware (software attestation)")
    if record.device_locked is not True:
        problems.append("The bootloader is unlocked")
    if record.boot_state != 0:
        state = facts["verified_boot"] or "not reported"
        problems.append(f"Verified boot is {state.replace('_', ' ')}, not verified")
    if agent_package not in record.app_packages:
        problems.append("The attested app is not the ATLAS agent")
    elif agent_digests is not None and not (set(record.app_digests) & agent_digests):
        problems.append("The attested app is not signed with the ATLAS key")

    checked = revoked is not None
    return Verdict(not problems and checked, problems, checked, facts)
