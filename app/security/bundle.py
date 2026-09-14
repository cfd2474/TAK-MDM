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

"""Ed25519 signing for desired-state bundles.

The signature is independent of TLS, which buys two things. A device can verify a
bundle it did not receive over a live connection to this server — so a LAN relay or
a sneakernetted file becomes a delivery path later without redesigning anything
(D9). And a compromised proxy cannot silently rewrite policy in flight.

Signing is over **canonical JSON**: sorted keys, no insignificant whitespace, UTF-8.
Python's dict ordering would otherwise make the same document serialize differently
between processes and the signature would fail to verify for no visible reason. The
agent must canonicalize identically before checking.

The signing key is separate from the device CA key on purpose: different job,
different blast radius, different rotation cadence. Rotating the bundle key
re-signs bundles; rotating the CA key invalidates every device identity.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from app.security import keyfiles


def canonical_json(payload: Any) -> bytes:
    """Deterministic serialization. Must match the agent's implementation exactly."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


class BundleSigner:
    """Signs desired-state documents and exposes the public key for verification."""

    def __init__(self, private_key: ed25519.Ed25519PrivateKey):
        self._private_key = private_key

    @classmethod
    def load_or_create(cls, pki_dir: Path) -> BundleSigner:
        key_path = pki_dir / "bundle_signing.key"

        if key_path.exists():
            private_key = serialization.load_pem_private_key(
                key_path.read_bytes(), password=None
            )
            if not isinstance(private_key, ed25519.Ed25519PrivateKey):
                raise ValueError(f"{key_path} is not an Ed25519 private key")
            return cls(private_key)

        private_key = ed25519.Ed25519PrivateKey.generate()
        keyfiles.write_private(
            key_path,
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ),
        )
        return cls(private_key)

    def public_key_base64(self) -> str:
        """Raw 32-byte Ed25519 public key, base64. What the agent pins at enrollment."""
        raw = self._private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return base64.b64encode(raw).decode()

    def sign(self, payload: Any) -> str:
        return base64.b64encode(self._private_key.sign(canonical_json(payload))).decode()

    def verify(self, payload: Any, signature_b64: str) -> bool:
        """Round-trip check, used by tests and by any local verification tooling."""
        try:
            self._private_key.public_key().verify(
                base64.b64decode(signature_b64), canonical_json(payload)
            )
        except Exception:
            return False
        return True
