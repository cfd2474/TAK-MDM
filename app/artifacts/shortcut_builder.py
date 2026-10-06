"""Build and sign a web-shortcut app from the template (W336).

Copyright 2026 TAK-Solutions LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

The operator names a link, gives an address and an icon, and gets an app whose
only job is to open that address in the device's default browser. ATLAS then
deploys it like any other Library app, so it reaches every device, Samsung or
not, with no prompt.

**Nothing is compiled here.** `app/data/shortcut-template.apk` is built once from
`agent/shortcut-template` and this module only:

1. rewrites four strings in its binary manifest (package, label, URL, version
   name) and the versionCode, the way `aapt --rename-manifest-package` does;
2. replaces its one PNG, the icon image;
3. writes the zip again with stored entries 4-byte aligned (`zipalign -p 4`);
4. signs it with **APK Signature Scheme v2**, which is enough for minSdk 31.

So the server needs no Java and no Android tools. The tests check the output
with Google's own `apksigner` and `zipalign` where they are installed.

Format references: AOSP ``ResourceTypes.h`` (binary XML, string pools) and
https://source.android.com/docs/security/features/apksigning/v2 (the signing
block).
"""

from __future__ import annotations

import hashlib
import io
import re
import struct
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID

from app.security import keyfiles

TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "data" / "shortcut-template.apk"

#: The template's placeholders. A contract with agent/shortcut-template.
TEMPLATE_PACKAGE = "com.taksolutions.atlaslink.template"
LABEL_PLACEHOLDER = "__ATLAS_LINK_LABEL__"
URL_PLACEHOLDER = "__ATLAS_LINK_URL__"
VERSION_PLACEHOLDER = "__ATLAS_LINK_VERSION__"

#: Every built shortcut's package starts with this.
PACKAGE_PREFIX = "com.taksolutions.atlaslink.l"

MAX_LABEL = 50
MAX_URL = 2000

_RES_STRING_POOL = 0x0001
_RES_XML = 0x0003
_RES_XML_RESOURCE_MAP = 0x0180
_RES_XML_START_ELEMENT = 0x0102
_UTF8_FLAG = 1 << 8
_TYPE_INT_DEC = 0x10
_VERSION_CODE_ATTR = 0x0101021B

_V2_BLOCK_ID = 0x7109871A
_RSA_PKCS1_SHA256 = 0x0103
_CHUNK = 1024 * 1024
_EOCD_MAGIC = b"PK\x05\x06"


class ShortcutBuildError(ValueError):
    """A shortcut that cannot be built, said in a sentence for the operator."""


@dataclass(frozen=True)
class ShortcutSpec:
    package_name: str
    label: str
    url: str
    version_code: int
    version_name: str
    #: A square PNG, already cropped by the console.
    icon_png: bytes


def new_package_name() -> str:
    """A package for a new shortcut. Fixed for its life: edits update it."""
    return f"{PACKAGE_PREFIX}{uuid.uuid4().hex[:10]}"


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

_PACKAGE_RE = re.compile(r"^com\.taksolutions\.atlaslink\.l[0-9a-f]{10}$")


def validate(spec: ShortcutSpec) -> None:
    """Refuse anything the template or Android would reject, in plain words."""
    if not _PACKAGE_RE.match(spec.package_name):
        raise ShortcutBuildError("the shortcut's package name is not one ATLAS made")
    label = spec.label.strip()
    if not label or len(label) > MAX_LABEL:
        raise ShortcutBuildError(f"the name must be 1 to {MAX_LABEL} characters")
    validate_url(spec.url)
    if not 1 <= spec.version_code <= 2_100_000_000:
        raise ShortcutBuildError("the version code is out of range")
    png_size(spec.icon_png)


def validate_url(url: str) -> None:
    """An http(s) address, nothing else.

    ⚠️ Only http and https. The shortcut fires an ACTION_VIEW at whatever this
    is, and `intent:`, `file:` or `content:` addresses would make an icon on a
    managed device launch arbitrary components or read local files.
    """
    if not url or len(url) > MAX_URL:
        raise ShortcutBuildError(f"the address must be 1 to {MAX_URL} characters")
    if any(c.isspace() for c in url):
        raise ShortcutBuildError("the address must not contain spaces")
    if not re.match(r"^https?://[^/?#]+", url, re.IGNORECASE):
        raise ShortcutBuildError("the address must start with http:// or https:// and name a site")


def png_size(data: bytes) -> tuple[int, int]:
    """The PNG's width and height, or ShortcutBuildError for anything else.

    The console crops to a square PNG; the server checks rather than trusts it.
    """
    if len(data) > 2 * 1024 * 1024:
        raise ShortcutBuildError("the icon is larger than 2 MB")
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise ShortcutBuildError("the icon must be a PNG image")
    width, height = struct.unpack(">II", data[16:24])
    if width != height:
        raise ShortcutBuildError("the icon must be square")
    if not 96 <= width <= 1024:
        raise ShortcutBuildError("the icon must be between 96 and 1024 pixels wide")
    return width, height


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #


def build(spec: ShortcutSpec, key: "SigningKey", template: bytes | None = None) -> bytes:
    """The signed APK for one shortcut."""
    validate(spec)
    template = template if template is not None else TEMPLATE_PATH.read_bytes()
    entries = _read_entries(template)

    manifest = rewrite_manifest(
        entries["AndroidManifest.xml"][1],
        {
            TEMPLATE_PACKAGE: spec.package_name,
            LABEL_PLACEHOLDER: spec.label.strip(),
            URL_PLACEHOLDER: spec.url,
            VERSION_PLACEHOLDER: spec.version_name,
        },
        spec.version_code,
    )
    entries["AndroidManifest.xml"] = (entries["AndroidManifest.xml"][0], manifest)

    pngs = [name for name in entries if name.endswith(".png")]
    if len(pngs) != 1:
        raise ShortcutBuildError(f"the template should hold one image, it holds {len(pngs)}")
    entries[pngs[0]] = (zipfile.ZIP_STORED, spec.icon_png)

    return sign_v2(_write_aligned(entries), key)


def _read_entries(apk: bytes) -> dict[str, tuple[int, bytes]]:
    """Each entry's compression and contents, in order, without META-INF.

    META-INF is a signature's home (v1) and build metadata; a rebuilt APK
    carries neither from the template.
    """
    out: dict[str, tuple[int, bytes]] = {}
    with zipfile.ZipFile(io.BytesIO(apk)) as archive:
        for info in archive.infolist():
            if info.filename.startswith("META-INF/"):
                continue
            out[info.filename] = (info.compress_type, archive.read(info))
    return out


def _write_aligned(entries: dict[str, tuple[int, bytes]]) -> bytes:
    """A zip with every stored entry's data on a 4-byte boundary.

    ⚠️ Required, not cosmetic: from targetSdk 30 Android refuses to install an
    APK whose `resources.arsc` is compressed or unaligned. The padding goes in
    the extra field zipalign itself uses (0xD935).

    Timestamps are fixed so the same input builds the same bytes.
    """
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        for name, (method, data) in entries.items():
            info = zipfile.ZipInfo(name, date_time=(1981, 1, 1, 1, 1, 2))
            info.compress_type = method
            if method == zipfile.ZIP_STORED:
                offset = out.tell() + 30 + len(name.encode("utf-8")) + 6
                pad = (-offset) % 4
                info.extra = struct.pack("<HHH", 0xD935, 2 + pad, 4) + b"\0" * pad
            archive.writestr(info, data)
    return out.getvalue()


# --------------------------------------------------------------------------- #
# Binary manifest
# --------------------------------------------------------------------------- #


def rewrite_manifest(data: bytes, replacements: dict[str, str], version_code: int) -> bytes:
    """Replace whole strings in the manifest's string pool, and the versionCode.

    Each placeholder must be in the pool exactly once, as a whole string, and the
    template's package must appear nowhere else (a provider authority or a
    permission named after it would silently keep the old name).
    """
    chunk_type, header_size, _ = struct.unpack_from("<HHI", data, 0)
    if chunk_type != _RES_XML:
        raise ShortcutBuildError("the template's manifest is not binary XML")
    strings, utf8, pool_size = _read_pool(data, header_size)

    for old in replacements:
        if strings.count(old) != 1:
            raise ShortcutBuildError(f"the template's manifest does not hold {old!r} exactly once")
    stray = [s for s in strings if TEMPLATE_PACKAGE in s and s != TEMPLATE_PACKAGE]
    if stray:
        raise ShortcutBuildError(f"the template names its package elsewhere: {stray}")

    new_pool = _encode_pool([replacements.get(s, s) for s in strings], utf8)
    rest = bytearray(data[header_size + pool_size:])
    _set_version_code(rest, strings, version_code)

    body = new_pool + bytes(rest)
    return struct.pack("<HHI", _RES_XML, header_size, header_size + len(body)) + \
        data[8:header_size] + body


def _read_pool(data: bytes, offset: int) -> tuple[list[str], bool, int]:
    chunk_type, _, size = struct.unpack_from("<HHI", data, offset)
    if chunk_type != _RES_STRING_POOL:
        raise ShortcutBuildError("the template's manifest has no string pool")
    count, styles, flags, strings_start, _ = struct.unpack_from("<IIIII", data, offset + 8)
    if styles:
        raise ShortcutBuildError("the template's manifest has styled strings")
    utf8 = bool(flags & _UTF8_FLAG)
    strings = []
    for i in range(count):
        (rel,) = struct.unpack_from("<I", data, offset + 28 + 4 * i)
        strings.append(_decode(data, offset + strings_start + rel, utf8))
    return strings, utf8, size


def _decode(data: bytes, pos: int, utf8: bool) -> str:
    if utf8:
        pos, _ = _utf8_len(data, pos)
        pos, nbytes = _utf8_len(data, pos)
        return data[pos:pos + nbytes].decode("utf-8")
    (n,) = struct.unpack_from("<H", data, pos)
    pos += 2
    if n & 0x8000:
        (low,) = struct.unpack_from("<H", data, pos)
        pos += 2
        n = ((n & 0x7FFF) << 16) | low
    return data[pos:pos + 2 * n].decode("utf-16-le")


def _utf8_len(data: bytes, pos: int) -> tuple[int, int]:
    n = data[pos]
    pos += 1
    if n & 0x80:
        n = ((n & 0x7F) << 8) | data[pos]
        pos += 1
    return pos, n


def _encode_pool(strings: list[str], utf8: bool) -> bytes:
    blobs = []
    for s in strings:
        if utf8:
            raw = s.encode("utf-8")
            units = len(s.encode("utf-16-le")) // 2
            if units > 0x7FFF or len(raw) > 0x7FFF:
                raise ShortcutBuildError("a string is too long for the manifest")
            blobs.append(_len8(units) + _len8(len(raw)) + raw + b"\0")
        else:
            raw = s.encode("utf-16-le")
            units = len(raw) // 2
            if units > 0x7FFF:
                raise ShortcutBuildError("a string is too long for the manifest")
            blobs.append(struct.pack("<H", units) + raw + b"\0\0")
    offsets, cursor = [], 0
    for blob in blobs:
        offsets.append(cursor)
        cursor += len(blob)
    data = b"".join(blobs)
    data += b"\0" * ((-len(data)) % 4)
    header_size = 28
    strings_start = header_size + 4 * len(strings)
    size = strings_start + len(data)
    header = struct.pack("<HHIIIIII", _RES_STRING_POOL, header_size, size, len(strings), 0,
                         _UTF8_FLAG if utf8 else 0, strings_start, 0)
    return header + b"".join(struct.pack("<I", o) for o in offsets) + data


def _len8(n: int) -> bytes:
    return bytes([n]) if n < 0x80 else bytes([0x80 | (n >> 8), n & 0xFF])


def _set_version_code(chunks: bytearray, strings: list[str], version_code: int) -> None:
    """Set `android:versionCode` on the root `<manifest>` element, in place."""
    resource_ids: list[int] = []
    pos = 0
    while pos + 8 <= len(chunks):
        kind, header, size = struct.unpack_from("<HHI", chunks, pos)
        if kind == _RES_XML_RESOURCE_MAP:
            resource_ids = list(struct.unpack_from(f"<{(size - header) // 4}I", chunks, pos + header))
        elif kind == _RES_XML_START_ELEMENT:
            _ns, name, attr_start, attr_size, attr_count = struct.unpack_from(
                "<IIHHH", chunks, pos + header)
            if strings[name] == "manifest":
                for i in range(attr_count):
                    at = pos + header + attr_start + i * attr_size
                    (attr_name,) = struct.unpack_from("<I", chunks, at + 4)
                    if attr_name < len(resource_ids) and resource_ids[attr_name] == _VERSION_CODE_ATTR:
                        if chunks[at + 15] != _TYPE_INT_DEC:
                            raise ShortcutBuildError("the template's versionCode is not an integer")
                        struct.pack_into("<I", chunks, at + 16, version_code)
                        return
                raise ShortcutBuildError("the template's manifest has no versionCode")
        pos += size
    raise ShortcutBuildError("the template has no <manifest> element")


# --------------------------------------------------------------------------- #
# Signing
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SigningKey:
    private_key: rsa.RSAPrivateKey
    certificate: x509.Certificate

    @property
    def certificate_sha256(self) -> str:
        return hashlib.sha256(self.certificate.public_bytes(serialization.Encoding.DER)).hexdigest()


def load_or_create_key(directory: Path, *, common_name: str = "ATLAS Web Shortcuts") -> SigningKey:
    """This box's shortcut signing key, made on first use.

    ⚠️ **Not the agent's key, and kept with the box's PKI.** Every shortcut this
    box builds is signed with it, and Android accepts an update only from the
    same key: lose it and existing shortcuts cannot be updated, only removed and
    deployed again.
    """
    key_path = directory / "shortcut-signing.key"
    cert_path = directory / "shortcut-signing.crt"
    if key_path.exists() and cert_path.exists():
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        return SigningKey(key, cert)

    if key_path.exists():
        # The certificate was lost but the key survived: make the certificate
        # again from the same key, which keeps every shortcut updatable.
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    else:
        key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        # Owner-only from the first instant, through the project's one helper.
        keyfiles.write_private(key_path, key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption()))
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "ATLAS"),
    ])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365 * 30))
        .sign(key, hashes.SHA256())
    )
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return SigningKey(key, cert)


def sign_v2(apk: bytes, key: SigningKey) -> bytes:
    """Insert an APK Signature Scheme v2 block.

    Per the spec: the digest covers the entries, the central directory, and the
    end-of-central-directory record with its directory offset pointing where the
    signing block will start, which is where the directory starts now.
    """
    eocd = apk.rfind(_EOCD_MAGIC)
    if eocd < 0 or len(apk) - eocd != 22:
        raise ShortcutBuildError("the rebuilt APK has an unexpected end record")
    cd_size, cd_offset = struct.unpack_from("<II", apk, eocd + 12)
    entries, central, end = apk[:cd_offset], apk[cd_offset:cd_offset + cd_size], apk[eocd:]

    digest = _top_digest([entries, central, end])
    cert_der = key.certificate.public_bytes(serialization.Encoding.DER)
    signed_data = (
        _lp(_lp(struct.pack("<I", _RSA_PKCS1_SHA256) + _lp(digest)))  # digests
        + _lp(_lp(cert_der))                                          # certificates
        + _lp(b"")                                                    # attributes
    )
    signature = key.private_key.sign(signed_data, padding.PKCS1v15(), hashes.SHA256())
    public_key = key.private_key.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    signer = (
        _lp(signed_data)
        + _lp(_lp(struct.pack("<I", _RSA_PKCS1_SHA256) + _lp(signature)))
        + _lp(public_key)
    )
    value = _lp(_lp(signer))

    pair = struct.pack("<Q", 4 + len(value)) + struct.pack("<I", _V2_BLOCK_ID) + value
    block_size = len(pair) + 8 + 16
    block = struct.pack("<Q", block_size) + pair + struct.pack("<Q", block_size) + b"APK Sig Block 42"

    new_end = bytearray(end)
    struct.pack_into("<I", new_end, 16, cd_offset + len(block))
    return entries + block + central + bytes(new_end)


def _lp(data: bytes) -> bytes:
    return struct.pack("<I", len(data)) + data


def _top_digest(sections: list[bytes]) -> bytes:
    chunk_digests = []
    for section in sections:
        for start in range(0, len(section), _CHUNK):
            piece = section[start:start + _CHUNK]
            chunk_digests.append(
                hashlib.sha256(b"\xa5" + struct.pack("<I", len(piece)) + piece).digest())
    return hashlib.sha256(
        b"\x5a" + struct.pack("<I", len(chunk_digests)) + b"".join(chunk_digests)).digest()
