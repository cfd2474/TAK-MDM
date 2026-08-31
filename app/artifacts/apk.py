"""APK inspection: identity, SDK levels, and signing certificate.

Signature extraction tries **v2/v3 first, then v1**. That order is not cosmetic:
apps targeting modern SDK levels are routinely signed with v2/v3 only, with no
`META-INF` block at all, so a v1-only implementation would fail on exactly the
builds this fleet cares about.

The signing certificate's SHA-256 does double duty. It is the pin that catches an
update Android would reject on-device for a signature mismatch (D13), and
base64url-encoded it *is*
``android.app.extra.PROVISIONING_DEVICE_ADMIN_SIGNATURE_CHECKSUM`` — so uploading
the agent APK yields the value QR provisioning needs.
"""

from __future__ import annotations

import base64
import hashlib
import io
import struct
import zipfile
from dataclasses import dataclass

from cryptography.hazmat.primitives.serialization import Encoding, pkcs7

from app.artifacts.axml import AxmlError, parse_elements

_APK_SIG_BLOCK_MAGIC = b"APK Sig Block 42"
_SIG_SCHEME_V2_ID = 0x7109871A
_SIG_SCHEME_V3_ID = 0xF05368C0
_EOCD_SIGNATURE = b"PK\x05\x06"
_MANIFEST = "AndroidManifest.xml"


class ApkError(ValueError):
    """Raised when a file is not a usable APK."""


@dataclass(frozen=True)
class ApkInfo:
    package_name: str
    version_code: int
    version_name: str | None
    min_sdk: int | None
    target_sdk: int | None
    # Set on a split APK; None on a base APK.
    split_name: str | None
    signature_sha256: str | None
    signature_scheme: str | None

    @property
    def provisioning_checksum(self) -> str | None:
        """base64url, unpadded — the exact form Android's provisioning extras want."""
        if not self.signature_sha256:
            return None
        return (
            base64.urlsafe_b64encode(bytes.fromhex(self.signature_sha256))
            .decode()
            .rstrip("=")
        )


# --------------------------------------------------------------------------- #
# Manifest
# --------------------------------------------------------------------------- #


def _read_manifest(archive: zipfile.ZipFile) -> tuple[str, int, str | None, int | None, int | None, str | None]:
    try:
        raw = archive.read(_MANIFEST)
    except KeyError:
        raise ApkError("archive contains no AndroidManifest.xml") from None

    try:
        elements = parse_elements(raw)
    except AxmlError as exc:
        raise ApkError(f"could not decode AndroidManifest.xml: {exc}") from exc

    manifest = next((e for e in elements if e.name == "manifest"), None)
    if manifest is None:
        raise ApkError("AndroidManifest.xml has no <manifest> element")

    package_name = manifest.get_str("package")
    if not package_name:
        raise ApkError("manifest declares no package name")

    version_code = manifest.get_int("versionCode")
    if version_code is None:
        raise ApkError(f"{package_name} declares no versionCode")

    uses_sdk = next((e for e in elements if e.name == "uses-sdk"), None)
    min_sdk = uses_sdk.get_int("minSdkVersion") if uses_sdk else None
    target_sdk = uses_sdk.get_int("targetSdkVersion") if uses_sdk else None

    version_name = manifest.get_str("versionName")
    split_name = manifest.get_str("split")

    return package_name, version_code, version_name, min_sdk, target_sdk, split_name


# --------------------------------------------------------------------------- #
# Signing block (v2 / v3)
# --------------------------------------------------------------------------- #


def _find_eocd_offset(data: bytes) -> int:
    """Locate the End Of Central Directory record, scanning back over any comment."""
    start = max(0, len(data) - (22 + 0xFFFF))
    index = data.rfind(_EOCD_SIGNATURE, start)
    if index < 0:
        raise ApkError("no ZIP end-of-central-directory record")
    return index


def _length_prefixed_items(payload: bytes) -> list[bytes]:
    """Split a concatenation of uint32-length-prefixed elements."""
    items: list[bytes] = []
    position = 0
    while position + 4 <= len(payload):
        (length,) = struct.unpack_from("<I", payload, position)
        position += 4
        if length == 0 or position + length > len(payload):
            break
        items.append(payload[position : position + length])
        position += length
    return items


def _extract_signing_block(data: bytes) -> dict[int, bytes]:
    """Return the APK Signing Block's id-value pairs, or an empty mapping."""
    eocd = _find_eocd_offset(data)
    (central_directory_offset,) = struct.unpack_from("<I", data, eocd + 16)

    if central_directory_offset < 24:
        return {}
    magic_at = central_directory_offset - len(_APK_SIG_BLOCK_MAGIC)
    if data[magic_at:central_directory_offset] != _APK_SIG_BLOCK_MAGIC:
        return {}  # v1-only APK: no signing block present

    (block_size,) = struct.unpack_from("<Q", data, central_directory_offset - 24)
    block_start = central_directory_offset - block_size - 8
    if block_start < 0:
        raise ApkError("APK signing block size is out of range")

    # Skip the leading size field; stop before the trailing size + magic.
    body = data[block_start + 8 : central_directory_offset - 24]

    pairs: dict[int, bytes] = {}
    position = 0
    while position + 12 <= len(body):
        (pair_length,) = struct.unpack_from("<Q", body, position)
        position += 8
        if pair_length < 4 or position + pair_length > len(body):
            break
        (pair_id,) = struct.unpack_from("<I", body, position)
        # pair_length covers the 4-byte id plus the value.
        pairs[pair_id] = body[position + 4 : position + pair_length]
        position += pair_length
    return pairs


def _certificate_from_scheme_block(block: bytes) -> bytes | None:
    """Pull the first signer's leading certificate out of a v2/v3 scheme block.

    Nesting, per the APK Signature Scheme v2 spec::

        block   := sequence of signers
        signer  := signed_data | signatures | public_key
        signed_data := digests | certificates | attributes

    The certificates live inside *signed_data*, not beside it — descending one
    level too few lands on the signatures sequence and yields garbage.
    """
    outer = _length_prefixed_items(block)
    if not outer:
        return None

    for signer in _length_prefixed_items(outer[0]):
        sections = _length_prefixed_items(signer)
        if not sections:
            continue
        signed_data = _length_prefixed_items(sections[0])
        if len(signed_data) < 2:
            continue
        certificates = _length_prefixed_items(signed_data[1])
        if certificates:
            return certificates[0]
    return None


def _signature_from_v1(archive: zipfile.ZipFile) -> bytes | None:
    """Fall back to the JAR-style PKCS#7 block in META-INF."""
    candidates = [
        name
        for name in archive.namelist()
        if name.upper().startswith("META-INF/")
        and name.upper().endswith((".RSA", ".DSA", ".EC"))
    ]
    for name in sorted(candidates):
        try:
            certificates = pkcs7.load_der_pkcs7_certificates(archive.read(name))
        except Exception:
            continue
        if certificates:
            return certificates[0].public_bytes(encoding=Encoding.DER)
    return None


def extract_signature(data: bytes, archive: zipfile.ZipFile) -> tuple[str | None, str | None]:
    """Return ``(sha256_hex_of_signing_cert, scheme)``."""
    pairs = _extract_signing_block(data)

    for scheme_id, label in ((_SIG_SCHEME_V3_ID, "v3"), (_SIG_SCHEME_V2_ID, "v2")):
        block = pairs.get(scheme_id)
        if not block:
            continue
        certificate = _certificate_from_scheme_block(block)
        if certificate:
            return hashlib.sha256(certificate).hexdigest(), label

    certificate = _signature_from_v1(archive)
    if certificate:
        return hashlib.sha256(certificate).hexdigest(), "v1"

    return None, None


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def inspect_apk(data: bytes) -> ApkInfo:
    """Identify an APK from its bytes."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ApkError("not a valid ZIP archive") from exc

    with archive:
        package_name, version_code, version_name, min_sdk, target_sdk, split_name = (
            _read_manifest(archive)
        )
        signature_sha256, scheme = extract_signature(data, archive)

    return ApkInfo(
        package_name=package_name,
        version_code=version_code,
        version_name=version_name,
        min_sdk=min_sdk,
        target_sdk=target_sdk,
        split_name=split_name,
        signature_sha256=signature_sha256,
        signature_scheme=scheme,
    )


def is_apk(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return _MANIFEST in archive.namelist()
    except zipfile.BadZipFile:
        return False
