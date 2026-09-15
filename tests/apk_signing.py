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

"""Which certificate signed an APK, without needing the Android SDK.

⚠️ **`apksigner` cannot be used here.** CI is `ubuntu-latest` with Python and no
Android SDK, and a guard that only runs on the one workstation with build-tools
installed is not a guard — it is a habit. So the signing block is parsed
directly.

⚠️ **There is no `META-INF/*.RSA` to read.** These APKs are signed with v2/v3
only, so the old JAR-signature path finds nothing and a naive implementation
reports "unsigned" for a perfectly signed file. The certificate lives in the APK
Signing Block, between the last entry and the central directory.

Verified against `apksigner verify --print-certs`: both produce
`2094bccc054c681f46d8c812378c07657cf339dd7d4e80b546026b77aff2c644` for the v1.32.0
artifacts.
"""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path

#: Sits immediately before the central directory when a signing block is present.
MAGIC = b"APK Sig Block 42"

#: The two block ids that carry signer certificates. v3 is preferred when both
#: are present: it is the one a modern device actually verifies, and the one
#: that carries a rotation lineage if there ever is one.
SCHEME_V2 = 0x7109871A
SCHEME_V3 = 0xF05368C0


class NotSigned(Exception):
    """The file carries no APK Signing Block this can read."""


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def signer_certificate_der(path: Path | str) -> bytes:
    """The DER of the first signer's certificate."""
    raw = Path(path).read_bytes()

    eocd = raw.rfind(b"PK\x05\x06")
    if eocd < 0:
        raise NotSigned(f"{path} is not a zip")
    central_directory = struct.unpack_from("<I", raw, eocd + 16)[0]

    if raw[central_directory - 16:central_directory] != MAGIC:
        raise NotSigned(
            f"{path} has no APK Signing Block — it may be unsigned, or signed "
            f"with the v1 JAR scheme only"
        )
    size = struct.unpack_from("<Q", raw, central_directory - 24)[0]
    block = raw[central_directory - size - 8 + 8: central_directory - 24]

    blocks: dict[int, bytes] = {}
    at = 0
    while at < len(block):
        (pair_length,) = struct.unpack_from("<Q", block, at)
        (pair_id,) = struct.unpack_from("<I", block, at + 8)
        blocks[pair_id] = block[at + 12: at + 8 + pair_length]
        at += 8 + pair_length

    value = blocks.get(SCHEME_V3) or blocks.get(SCHEME_V2)
    if value is None:
        raise NotSigned(
            f"{path} has a signing block but no v2/v3 signer "
            f"(ids present: {[hex(k) for k in blocks]})"
        )

    # signers → signer → signed-data → [digests, certificates] → first cert.
    # Every level is a uint32 length followed by that many bytes.
    offset = 4 + 4 + 4          # signers, first signer, signed-data
    offset += 4 + _u32(value, offset)   # skip the digests sequence
    offset += 4                          # into the certificates sequence
    length = _u32(value, offset)
    offset += 4
    return value[offset: offset + length]


def signer_sha256(path: Path | str) -> str:
    """The signing certificate's SHA-256, lowercase hex.

    The same value `apksigner verify --print-certs` prints, and the same one the
    Play Console shows for an upload or app signing key — so the three can be
    compared by eye.
    """
    return hashlib.sha256(signer_certificate_der(path)).hexdigest()
