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

"""Proof that a device holds a TAK client certificate's key (W458).

The plugin signs `atlas-renew-v1\\n<nonce>\\n<connect string>` with the private
key of that connection's certificate. This checks the nonce is one this process
issued and has not used, the signature is the certificate's, and the
certificate chains to the TAK root CA. The username is the certificate's CN:
TAK Server signs only a CSR whose CN equals the login name
(`CertManagerService.validateCSR`), so the CN *is* the user TAK Server checked.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from cryptography.x509.oid import NameOID

PREFIX = b"atlas-renew-v1"
NONCE_TTL_SECONDS = 15 * 60

#: A certificate this long past its end still renews. A device that was off for
#: a few weeks should not need a QR code; one gone for months should.
EXPIRED_GRACE = timedelta(days=30)

#: Deeper than any TAK chain (root → intermediate → client).
MAX_CHAIN = 5


class ProofError(Exception):
    """Why a proof was refused. The text is safe to log and to show."""


def message(nonce: str, connect_string: str) -> bytes:
    return b"\n".join((PREFIX, nonce.encode("utf-8"), connect_string.encode("utf-8")))


class Nonces:
    """Single-use challenges, valid for 15 minutes, bound to this process."""

    def __init__(self, secret: bytes | None = None, ttl: int = NONCE_TTL_SECONDS,
                 clock=time.time) -> None:
        self._secret = secret or os.urandom(32)
        self._ttl = ttl
        self._clock = clock
        self._used: dict[str, float] = {}

    def _mac(self, body: str) -> str:
        return hmac.new(self._secret, body.encode(), hashlib.sha256).hexdigest()[:32]

    def issue(self) -> str:
        body = "%d.%s" % (int(self._clock()), secrets.token_urlsafe(18))
        return "%s.%s" % (body, self._mac(body))

    def redeem(self, nonce: str) -> None:
        """Accept a nonce once. Raises ProofError otherwise."""
        now = self._clock()
        for used, at in list(self._used.items()):
            if now - at > self._ttl:
                del self._used[used]
        try:
            issued, rand, mac = nonce.split(".")
            issued_at = int(issued)
        except ValueError:
            raise ProofError("malformed challenge") from None
        if not hmac.compare_digest(mac, self._mac("%s.%s" % (issued, rand))):
            raise ProofError("challenge was not issued here (the container restarts with new ones)")
        if now - issued_at > self._ttl:
            raise ProofError("challenge expired")
        if nonce in self._used:
            raise ProofError("challenge already used")
        self._used[nonce] = now


def _load_one(pem: str) -> x509.Certificate:
    try:
        return x509.load_pem_x509_certificate(pem.encode("ascii"))
    except Exception:
        raise ProofError("certificate is not a PEM X.509 certificate") from None


def _is_ca(cert: x509.Certificate) -> bool:
    try:
        return bool(cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca)
    except x509.ExtensionNotFound:
        return False


def _issued_by(cert: x509.Certificate, issuer: x509.Certificate) -> bool:
    if cert.issuer != issuer.subject:
        return False
    try:
        cert.verify_directly_issued_by(issuer)
        return True
    except Exception:
        return False


def _verify_signature(cert: x509.Certificate, signature: bytes, data: bytes) -> None:
    key = cert.public_key()
    try:
        if isinstance(key, rsa.RSAPublicKey):
            key.verify(signature, data, padding.PKCS1v15(), hashes.SHA256())
        elif isinstance(key, ec.EllipticCurvePublicKey):
            key.verify(signature, data, ec.ECDSA(hashes.SHA256()))
        else:
            raise ProofError("unsupported key type")
    except InvalidSignature:
        raise ProofError("signature does not match the certificate") from None


def _username(cert: x509.Certificate) -> str:
    names = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    if len(names) != 1:
        raise ProofError("certificate must carry exactly one CN")
    name = str(names[0].value).strip()
    if not name or len(name) > 150 or any(ord(c) < 32 for c in name):
        raise ProofError("certificate CN is not a usable username")
    return name


@dataclass(frozen=True)
class Proven:
    """What a proof established. W461: the leaf and the CA that signed it,
    so its CRL can be checked against that CA's key."""

    username: str
    leaf: x509.Certificate
    issuer: x509.Certificate


def verify(*, certificate: str, chain: list[str], signature: str, nonce: str,
           connect_string: str, anchors_pem: str, now: datetime | None = None) -> str:
    """Return the username the proof establishes. Raises ProofError."""
    return prove(certificate=certificate, chain=chain, signature=signature, nonce=nonce,
                 connect_string=connect_string, anchors_pem=anchors_pem, now=now).username


def prove(*, certificate: str, chain: list[str], signature: str, nonce: str,
          connect_string: str, anchors_pem: str, now: datetime | None = None) -> Proven:
    """Check the proof. Raises ProofError.

    ⚠️ The nonce is redeemed by the caller *before* this runs, so a refused
    proof still spends it and cannot be retried with a different signature.
    """
    now = now or datetime.now(timezone.utc)
    leaf = _load_one(certificate)
    if _is_ca(leaf):
        raise ProofError("a CA certificate is not a client certificate")
    if leaf.not_valid_after_utc < now - EXPIRED_GRACE:
        raise ProofError("certificate expired more than %d days ago" % EXPIRED_GRACE.days)
    try:
        raw = base64.b64decode(signature, validate=True)
    except Exception:
        raise ProofError("signature is not base64") from None
    _verify_signature(leaf, raw, message(nonce, connect_string))

    try:
        anchors = x509.load_pem_x509_certificates(anchors_pem.encode("ascii"))
    except Exception:
        raise ProofError("the TAK root CA file is unreadable") from None
    pool = [_load_one(pem) for pem in chain[:MAX_CHAIN]]
    current, issuer = leaf, None
    for _ in range(MAX_CHAIN):
        anchor = next((a for a in anchors if _issued_by(current, a)), None)
        if anchor is not None:
            return Proven(_username(leaf), leaf, issuer or anchor)
        parent = next((c for c in pool if _is_ca(c) and _issued_by(current, c)), None)
        if parent is None:
            break
        issuer = issuer or parent
        current = parent
    raise ProofError("certificate does not chain to this TAK Server's root CA")
