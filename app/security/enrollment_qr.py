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

"""Short-lived, stateless derivatives of the persistent enrollment token.

Chunk 14. The operator's model is one standing enrollment credential, retired and
replaced rather than multiplied — but its raw secret is never displayed. Every QR
the console shows instead carries a **signed, 15-minute derivative** of it, so a
leaked QR image (a photo, a screenshot left on a shared screen) is bounded by this
window rather than by the persistent token's own lifetime.

Deliberately stateless — no database row is created for "Generate QR", which is a
button an operator will press routinely for the life of the system. The pattern is
`app/security/csrf.py`'s, reused rather than re-invented: an HMAC-signed payload
carrying an id and an issue time, verified by recomputing the signature. Revocation
needs no cascade step here either, for the same reason CSRF tokens need none: the
enrollment endpoint re-validates the referenced token's own `is_usable()` at the
moment of use, not at mint time, so retiring the primary invalidates every QR
derived from it immediately — including one mid-scan.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import time
import uuid
from pathlib import Path
from app.security import keyfiles

logger = logging.getLogger(__name__)


class EnrollmentQrError(Exception):
    """Raised when a QR-derived secret fails verification. Carries a reason."""


class EnrollmentQrGuard:
    """Mints and verifies signed, time-boxed derivatives of a primary token."""

    def __init__(self, key: bytes, *, ttl_seconds: int):
        self._key = key
        self._ttl = ttl_seconds

    @classmethod
    def load_or_create(cls, pki_dir: Path, *, ttl_seconds: int) -> EnrollmentQrGuard:
        """Load the signing key, generating one on first use.

        Beside `ca.key`, `token_vault.key` and `csrf.key`, and no more dangerous
        than the CSRF key: losing it lets someone forge a QR-shaped secret, which is
        only useful for as long as a genuine primary token happens to exist and be
        unrevoked. Rotating it invalidates every QR currently in someone's camera
        roll — which, given the 15-minute window, is rarely more than a
        theoretical loss.
        """
        key_path = Path(pki_dir) / "enrollment_qr.key"
        if key_path.exists():
            return cls(key_path.read_bytes().strip(), ttl_seconds=ttl_seconds)

        key = base64.urlsafe_b64encode(secrets.token_bytes(32))
        keyfiles.write_private(key_path, key)
        logger.info("created enrollment QR signing key at %s", key_path)
        return cls(key, ttl_seconds=ttl_seconds)

    # ----------------------------------------------------------------------- #

    def issue(self, primary_id: uuid.UUID, *, now: float | None = None) -> str:
        """Mint a secret good for `ttl_seconds` that resolves to `primary_id`.

        The nonce adds no security property on its own — there is no server-side
        record to make it unpredictable against, and reuse within the window is
        intentional (the operator asked for unlimited enrolments per QR). It exists
        so two secrets minted for the same primary in the same second still differ,
        which avoids a "the QR looked identical to the last one" surprise and keeps
        this shaped like `csrf.py`'s token for the same underlying idea.
        """
        issued = int(now if now is not None else time.time())
        nonce = secrets.token_urlsafe(12)
        payload = f"{primary_id}.{nonce}.{issued}"
        return f"{payload}.{self._sign(payload)}"

    def verify(self, secret: str, *, now: float | None = None) -> uuid.UUID:
        """Return the primary token id this secret resolves to, or raise.

        Verifies only the **wrapper** — signature and age. The caller is still
        responsible for loading that id's `EnrollmentToken` row and checking
        `is_usable()`: a syntactically valid, unexpired QR secret for a primary that
        has since been revoked or has itself expired must not enrol a device.
        """
        parts = secret.split(".")
        if len(parts) != 4:
            raise EnrollmentQrError("not a QR-derived enrollment secret")

        primary_raw, nonce, issued_raw, signature = parts
        try:
            primary_id = uuid.UUID(primary_raw)
            issued = int(issued_raw)
        except ValueError as exc:
            raise EnrollmentQrError("malformed enrollment QR secret") from exc

        payload = f"{primary_raw}.{nonce}.{issued_raw}"
        expected = self._sign(payload)
        # Constant-time: a timing oracle here would let a signature be recovered
        # byte by byte, and unlike a CSRF token this one needs no session cookie
        # alongside it — the signature is the only thing standing between a copied
        # QR image and a live enrollment credential.
        if not hmac.compare_digest(expected, signature):
            raise EnrollmentQrError("enrollment QR secret has an invalid signature")

        age = (now if now is not None else time.time()) - issued
        if age > self._ttl:
            raise EnrollmentQrError("enrollment QR has expired; generate a new one")
        if age < -60:
            raise EnrollmentQrError("enrollment QR is not yet valid")

        return primary_id

    def _sign(self, payload: str) -> str:
        digest = hmac.new(self._key, payload.encode(), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")
