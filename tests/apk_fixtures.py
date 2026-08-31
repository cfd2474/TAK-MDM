"""Synthetic APK construction for tests.

Builds genuine binary structures — a real AXML string pool and element tree, a real
APK Signing Block v2 with a real X.509 certificate — rather than mocking the
parsers. A parser tested only against its own mock proves nothing; these fixtures
fail the same way a malformed APK from the field would.
"""

from __future__ import annotations

import datetime as dt
import io
import struct
import zipfile

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ANDROID_NS = "http://schemas.android.com/apk/res/android"

_TYPE_STRING = 0x03
_TYPE_INT_DEC = 0x10

_APK_SIG_BLOCK_MAGIC = b"APK Sig Block 42"
_SIG_SCHEME_V2_ID = 0x7109871A


# --------------------------------------------------------------------------- #
# Binary XML encoder
# --------------------------------------------------------------------------- #


def _encode_string_pool(strings: list[str], utf8: bool = True) -> bytes:
    offsets: list[int] = []
    blob = bytearray()

    for value in strings:
        offsets.append(len(blob))
        if utf8:
            encoded = value.encode("utf-8")
            blob.append(len(value))  # UTF-16 length
            blob.append(len(encoded))  # byte length
            blob += encoded
            blob.append(0)
        else:
            encoded = value.encode("utf-16-le")
            blob += struct.pack("<H", len(value))
            blob += encoded
            blob += b"\x00\x00"

    while len(blob) % 4:
        blob.append(0)

    header_size = 28
    strings_start = header_size + 4 * len(strings)
    chunk_size = strings_start + len(blob)
    flags = 0x100 if utf8 else 0

    chunk = struct.pack("<HHI", 0x0001, header_size, chunk_size)
    chunk += struct.pack("<IIIII", len(strings), 0, flags, strings_start, 0)
    chunk += b"".join(struct.pack("<I", offset) for offset in offsets)
    chunk += bytes(blob)
    return chunk


def _encode_start_element(
    name_index: int, attributes: list[tuple[int, int, int, int]]
) -> bytes:
    """attributes: (ns_index, name_index, data_type, value)."""
    header_size = 16
    size = header_size + 20 + 20 * len(attributes)

    chunk = struct.pack("<HHI", 0x0102, header_size, size)
    chunk += struct.pack("<II", 1, 0xFFFFFFFF)  # lineNumber, comment
    chunk += struct.pack("<II", 0xFFFFFFFF, name_index)  # ns, name
    chunk += struct.pack("<HHHHHH", 20, 20, len(attributes), 0, 0, 0)

    for ns_index, attr_name_index, data_type, value in attributes:
        raw_value = value if data_type == _TYPE_STRING else 0xFFFFFFFF
        chunk += struct.pack("<III", ns_index, attr_name_index, raw_value)
        chunk += struct.pack("<HBBI", 8, 0, data_type, value)

    return chunk


def _encode_end_element(name_index: int) -> bytes:
    chunk = struct.pack("<HHI", 0x0103, 16, 24)
    chunk += struct.pack("<II", 1, 0xFFFFFFFF)
    chunk += struct.pack("<II", 0xFFFFFFFF, name_index)
    return chunk


def build_manifest_axml(
    package_name: str,
    version_code: int,
    version_name: str = "1.0",
    min_sdk: int = 26,
    target_sdk: int = 34,
    split: str | None = None,
    utf8: bool = True,
) -> bytes:
    """Compile a minimal AndroidManifest.xml to binary XML."""
    strings = [
        ANDROID_NS,          # 0
        "manifest",          # 1
        "package",           # 2
        "versionCode",       # 3
        "versionName",       # 4
        "uses-sdk",          # 5
        "minSdkVersion",     # 6
        "targetSdkVersion",  # 7
        package_name,        # 8
        version_name,        # 9
        "split",             # 10
    ]
    if split:
        strings.append(split)  # 11

    manifest_attributes = [
        (0xFFFFFFFF, 2, _TYPE_STRING, 8),
        (0, 3, _TYPE_INT_DEC, version_code),
        (0, 4, _TYPE_STRING, 9),
    ]
    if split:
        manifest_attributes.append((0xFFFFFFFF, 10, _TYPE_STRING, 11))

    body = _encode_string_pool(strings, utf8=utf8)
    body += _encode_start_element(1, manifest_attributes)
    body += _encode_start_element(
        5, [(0, 6, _TYPE_INT_DEC, min_sdk), (0, 7, _TYPE_INT_DEC, target_sdk)]
    )
    body += _encode_end_element(5)
    body += _encode_end_element(1)

    return struct.pack("<HHI", 0x0003, 8, 8 + len(body)) + body


# --------------------------------------------------------------------------- #
# Signing
# --------------------------------------------------------------------------- #


def make_signing_pair(common_name: str = "Test Signer"):
    """A self-signed certificate and its key, standing in for an app signing identity."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = dt.datetime.now(dt.timezone.utc)

    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    return certificate, key


def make_signing_certificate(common_name: str = "Test Signer") -> bytes:
    certificate, _ = make_signing_pair(common_name)
    return certificate.public_bytes(serialization.Encoding.DER)


def build_v1_signed_apk(
    package_name: str = "com.legacy.app", version_code: int = 1
) -> tuple[bytes, bytes]:
    """An APK signed the old JAR way: a PKCS#7 block in META-INF, no signing block.

    Returns ``(apk_bytes, certificate_der)``. Exists because v1-only APKs still turn
    up, and the fallback path deserves a real test rather than a mocked one.
    """
    from cryptography.hazmat.primitives.serialization import pkcs7

    certificate, key = make_signing_pair("Legacy Signer")
    signature_block = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(b"Signature-Version: 1.0\r\n")
        .add_signer(certificate, key, hashes.SHA256())
        .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.DetachedSignature])
    )

    apk = build_apk(
        package_name,
        version_code,
        sign=False,
        extra_files={
            "META-INF/MANIFEST.MF": b"Manifest-Version: 1.0\r\n",
            "META-INF/CERT.SF": b"Signature-Version: 1.0\r\n",
            "META-INF/CERT.RSA": signature_block,
        },
    )
    return apk, certificate.public_bytes(serialization.Encoding.DER)


def _length_prefixed(payload: bytes) -> bytes:
    return struct.pack("<I", len(payload)) + payload


def _build_v2_block(certificate_der: bytes) -> bytes:
    """Nest a certificate the way APK Signature Scheme v2 specifies.

    block := seq(signers); signer := signed_data | signatures | public_key;
    signed_data := digests | certificates | attributes
    """
    digests = _length_prefixed(struct.pack("<I", 0x0103) + _length_prefixed(b"\x00" * 32))
    certificates = _length_prefixed(certificate_der)
    attributes = b""

    signed_data = (
        _length_prefixed(digests)
        + _length_prefixed(certificates)
        + _length_prefixed(attributes)
    )
    signer = (
        _length_prefixed(signed_data)
        + _length_prefixed(b"\x00" * 8)   # signatures (not verified here)
        + _length_prefixed(b"\x00" * 8)   # public key
    )
    return _length_prefixed(_length_prefixed(signer))


def _insert_signing_block(zip_bytes: bytes, certificate_der: bytes) -> bytes:
    """Splice an APK Signing Block between the entries and the central directory."""
    eocd = zip_bytes.rfind(b"PK\x05\x06")
    if eocd < 0:
        raise ValueError("no EOCD in generated zip")
    (cd_offset,) = struct.unpack_from("<I", zip_bytes, eocd + 16)

    value = _build_v2_block(certificate_der)
    pair = struct.pack("<Q", len(value) + 4) + struct.pack("<I", _SIG_SCHEME_V2_ID) + value

    # size_of_block covers the pairs, the trailing size field, and the magic.
    block_size = len(pair) + 8 + 16
    block = (
        struct.pack("<Q", block_size)
        + pair
        + struct.pack("<Q", block_size)
        + _APK_SIG_BLOCK_MAGIC
    )

    patched = bytearray(zip_bytes[:cd_offset] + block + zip_bytes[cd_offset:])
    new_eocd = eocd + len(block)
    struct.pack_into("<I", patched, new_eocd + 16, cd_offset + len(block))
    return bytes(patched)


# --------------------------------------------------------------------------- #
# APK / XAPK
# --------------------------------------------------------------------------- #


def build_apk(
    package_name: str = "com.example.app",
    version_code: int = 1,
    version_name: str = "1.0",
    min_sdk: int = 26,
    target_sdk: int = 34,
    split: str | None = None,
    certificate_der: bytes | None = None,
    sign: bool = True,
    extra_files: dict[str, bytes] | None = None,
    utf8_strings: bool = True,
) -> bytes:
    manifest = build_manifest_axml(
        package_name, version_code, version_name, min_sdk, target_sdk, split, utf8_strings
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("AndroidManifest.xml", manifest)
        archive.writestr("classes.dex", b"dex\n035\x00" + b"\x00" * 64)
        for name, payload in (extra_files or {}).items():
            archive.writestr(name, payload)

    data = buffer.getvalue()
    if not sign:
        return data
    return _insert_signing_block(data, certificate_der or make_signing_certificate())


def build_xapk(
    package_name: str = "com.example.app",
    version_code: int = 1,
    splits: tuple[str, ...] = ("config.arm64_v8a",),
    certificate_der: bytes | None = None,
    with_obb: bool = False,
    include_manifest_json: bool = True,
) -> bytes:
    certificate_der = certificate_der or make_signing_certificate()

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        if include_manifest_json:
            archive.writestr(
                "manifest.json",
                f'{{"package_name":"{package_name}","version_code":"{version_code}"}}',
            )
        archive.writestr(
            f"{package_name}.apk",
            build_apk(
                package_name, version_code, certificate_der=certificate_der
            ),
        )
        for split in splits:
            archive.writestr(
                f"{split}.apk",
                build_apk(
                    package_name,
                    version_code,
                    split=split,
                    certificate_der=certificate_der,
                ),
            )
        if with_obb:
            archive.writestr(f"Android/obb/{package_name}/main.1.{package_name}.obb", b"OBB" * 100)

    return buffer.getvalue()
