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

from app.artifacts.app_icon import AppIcon, extract_icon, read_table
from app.artifacts.arsc import ResourceTable
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
    # Fully-qualified names of every declared <receiver>. Used to verify that a
    # provisioning payload names a component the APK actually contains.
    receivers: tuple[str, ...] = ()
    # The exact ATAK build an ATAK plugin was compiled against, e.g.
    # "com.atakmap.app@5.5.0.CIV". None for anything that is not an ATAK plugin.
    plugin_api: str | None = None
    # The app's display name, when the manifest states it literally. None when it
    # is a resource reference, which is the common case (W51).
    label: str | None = None
    # The launcher icon, when one can be extracted. None for an app whose icon is
    # a vector drawable, which needs a renderer we do not have (W53).
    icon: AppIcon | None = None

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


def _read_manifest(
    archive: zipfile.ZipFile,
) -> tuple[
    str, int, str | None, int | None, int | None, str | None, tuple[str, ...],
    str | None, str | None,
]:
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

    # A manifest may name a receiver relatively (".admin.Foo") or absolutely.
    # Normalising here means callers compare like with like.
    receivers = tuple(
        _qualify(package_name, name)
        for element in elements
        if element.name == "receiver"
        for name in [element.get_str("name")]
        if name
    )

    # ATAK plugins declare the exact ATAK build they were compiled against:
    #     <meta-data android:name="plugin-api"
    #                android:value="com.atakmap.app@5.5.0.CIV"/>
    # A plugin only loads in that build, so this is a compatibility key, not a
    # version — and it is in the APK, so it works for a hand-uploaded plugin as
    # well as one pulled from the TAK.gov catalog (D45).
    plugin_api = next(
        (
            element.get_str("value")
            for element in elements
            if element.name == "meta-data" and element.get_str("name") == "plugin-api"
        ),
        None,
    )

    # The app's own display name — what the launcher shows on the device.
    #
    # Returned exactly as the manifest states it, which is usually a resource
    # reference (`@0x7f15038b`) because most apps put their name in strings.xml.
    # Resolving that needs `resources.arsc`, and the caller holds it — so the
    # reference is passed up rather than discarded here (W53).
    application = next((e for e in elements if e.name == "application"), None)
    label = application.get_str("label") if application else None

    return (
        package_name, version_code, version_name, min_sdk, target_sdk,
        split_name, receivers, plugin_api, label,
    )


def _resolve_label(label: str | None, table: ResourceTable | None) -> str | None:
    """Turn a manifest label into a display name.

    A literal label is already the answer. A resource reference is looked up in
    the table, taking the **default locale** — the app's name is translated, and
    an operator's console should not show whichever translation happened to be
    listed first.

    Returns None rather than the reference when it cannot be resolved: showing
    `@0x7f15038b` to an operator is worse than showing the package name, and
    guessing "Outlook" from the package id would be a fabrication that happens to
    be right, which is worse still.
    """
    if not label:
        return None
    if not label.startswith("@0x"):
        return label
    if table is None:
        return None
    try:
        resource_id = int(label[1:], 16)
    except ValueError:
        return None
    resolved = table.string(resource_id)
    if not resolved or resolved.startswith("@0x") or resolved.startswith("res/"):
        # A `res/...` value means the reference landed on a *file* resource rather
        # than a string — a mislabelled table, not a name.
        return None
    return resolved


def _qualify(package_name: str, class_name: str) -> str:
    """Expand a manifest class reference to its fully-qualified form."""
    if class_name.startswith("."):
        return f"{package_name}{class_name}"
    if "." not in class_name:
        return f"{package_name}.{class_name}"
    return class_name


def component_class(component: str) -> str:
    """Fully-qualify a ``package/class`` component name.

    Android's shorthand expands a leading dot against the *package*, so
    ``org.x/.admin.Foo`` means ``org.x.admin.Foo`` — the trap that made a
    provisioning payload point at a class that did not exist.
    """
    package_name, _, class_name = component.partition("/")
    return _qualify(package_name, class_name) if class_name else component


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
        (
            package_name, version_code, version_name, min_sdk, target_sdk,
            split_name, receivers, plugin_api, label,
        ) = _read_manifest(archive)
        signature_sha256, scheme = extract_signature(data, archive)

        # Inside the `with`: reading a closed archive raises, and the helpers below
        # turn any read failure into a silent None — the same trap that made
        # `_container_label` dead code in W51.
        #
        # Skipped for a split, which is not an app: it has no launcher entry and no
        # name of its own, and a `config.*` split ships a resource table big enough
        # that parsing one per split is real work for a guaranteed None.
        icon = None
        if split_name is None:
            # One parse, two questions. Outlook's table is 39.6 MB.
            table = read_table(archive)
            icon = extract_icon(archive, table)
            label = _resolve_label(label, table)
        else:
            label = None

    return ApkInfo(
        package_name=package_name,
        version_code=version_code,
        version_name=version_name,
        min_sdk=min_sdk,
        target_sdk=target_sdk,
        split_name=split_name,
        signature_sha256=signature_sha256,
        signature_scheme=scheme,
        receivers=receivers,
        plugin_api=plugin_api,
        label=label,
        icon=icon,
    )


def is_apk(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return _MANIFEST in archive.namelist()
    except zipfile.BadZipFile:
        return False
