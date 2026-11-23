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

"""Certificates TAK Server has revoked, which must never renew (W461).

A renewal makes a password for the certificate's CN, and TAK Server's
enrollment does not look at the certificate the device holds now. Without this
check a revoked certificate (a lost tablet) would renew into a valid one.

TAK Server records a revocation twice (`CertManagerAdminApi`): it sets
`revocation_date` in its `certificate` table, which is what its own login check
reads (`X509Authenticator`, with `x509checkRevocation`), and `revokeCert.sh`
adds the serial to the issuing CA's CRL. InfraTAK copies both here, since this
container can reach neither TAK Server's database nor its admin API:

* `revoked.txt`: `written=<ISO 8601 UTC>` on the first line, then one SHA-256
  fingerprint per line in TAK Server's form (upper case, colon-separated);
* `tak-crls.pem`: every CA's CRL, PEM.

⚠️ **Fail closed.** No list, an unreadable one, or one written more than
`MAX_AGE` ago refuses renewal: a gap in the copy must not be a way through.
InfraTAK writes it every few minutes. A CRL is believed only when its issuer is
the certificate's issuer and its signature verifies with that CA's key.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import serialization

#: InfraTAK refreshes every 5 minutes; an hour allows for a slow console.
MAX_AGE = timedelta(hours=1)

#: Far above any real list.
MAX_LINES = 200_000


class Unknown(Exception):
    """Revocation cannot be checked now. Renewal waits; it is never assumed fine."""


class Revoked(Exception):
    """TAK Server has revoked this certificate."""


def fingerprint(cert: x509.Certificate) -> str:
    """The SHA-256 of the DER, as TAK Server's `certificate.hash` holds it."""
    digest = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest().upper()
    return ":".join(digest[i:i + 2] for i in range(0, len(digest), 2))


@dataclass(frozen=True)
class Revocations:
    written: datetime
    fingerprints: frozenset[str]
    crls: tuple[x509.CertificateRevocationList, ...]

    def check(self, leaf: x509.Certificate, issuer: x509.Certificate, now: datetime) -> None:
        """Raise `Revoked` or `Unknown`; return when the certificate may renew."""
        if now - self.written > MAX_AGE:
            raise Unknown("the list of revoked certificates from TAK Server is out of date")
        if fingerprint(leaf) in self.fingerprints:
            raise Revoked("certificate revoked by TAK Server")
        for crl in self.crls:
            if crl.issuer != leaf.issuer:
                continue
            if not crl.is_signature_valid(issuer.public_key()):
                raise Unknown("the CRL for %s does not verify" % leaf.issuer.rfc4514_string())
            if crl.get_revoked_certificate_by_serial_number(leaf.serial_number) is not None:
                raise Revoked("certificate revoked by TAK Server")


def parse(revoked_text: str, crls_pem: str) -> Revocations:
    """Raise `Unknown` when the list is missing or malformed."""
    lines = [line.strip() for line in (revoked_text or "").splitlines()]
    if not lines or not lines[0].startswith("written="):
        raise Unknown("TAK Server's list of revoked certificates is not here yet")
    if len(lines) > MAX_LINES:
        raise Unknown("the list of revoked certificates is too long")
    try:
        written = datetime.fromisoformat(lines[0].removeprefix("written=").replace("Z", "+00:00"))
    except ValueError:
        raise Unknown("the list of revoked certificates has no valid time") from None
    if written.tzinfo is None:
        written = written.replace(tzinfo=timezone.utc)
    prints = frozenset(line.upper() for line in lines[1:] if line and not line.startswith("#"))
    crls: list[x509.CertificateRevocationList] = []
    for block in _pem_blocks(crls_pem or "", "X509 CRL"):
        try:
            crls.append(x509.load_pem_x509_crl(block.encode("ascii")))
        except ValueError:
            raise Unknown("a CRL from TAK Server is unreadable") from None
    return Revocations(written, prints, tuple(crls))


def _pem_blocks(text: str, label: str) -> list[str]:
    begin, end = "-----BEGIN %s-----" % label, "-----END %s-----" % label
    out, at = [], 0
    while (start := text.find(begin, at)) != -1:
        stop = text.find(end, start)
        if stop == -1:
            raise Unknown("a CRL from TAK Server is cut short")
        out.append(text[start:stop + len(end)] + "\n")
        at = stop + len(end)
    return out
