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

"""The certificate authorities of this InfraTAK's own TAK Server (W460).

A device can hold TAK connections to any number of servers, and the plugin
reports each connection's client-certificate issuer. Only the CAs of the TAK
Server this InfraTAK runs are ATLAS's business: the TAK Server CAs list, the
Retire step and certificate renewal look at those and leave the rest alone.

InfraTAK writes the TAK Server's public CA certificates (root and every
intermediate, retired ones included) to `settings.tak_ca_file`. A CA counts only
if it chains to a self-signed root in the same file, so a stray certificate in
the bundle claims nothing.

⚠️ **Match by CA, never by address.** A connection to this TAK Server can name
it by its domain, a custom domain, an IP or the optional proxy in front of
8089; its certificate chains to the same root whichever.

⚠️ **No file is "unknown", not "none".** A box whose InfraTAK predates W460 has
no file. `load` then returns None and callers keep the old behaviour (every
CA), with the page saying the list may include other servers' CAs.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from cryptography import x509
from cryptography.exceptions import InvalidSignature

from app.config import get_settings

log = logging.getLogger(__name__)

#: Far above any real bundle (a CA certificate is about 1-2 KB).
MAX_BYTES = 1024 * 1024


@dataclass(frozen=True)
class ServerCas:
    """The subjects (RFC 4514, as `tak_certs` writes them) of the CAs that
    chain to this TAK Server's root."""

    issuers: frozenset[str]

    def owns(self, issuer: str | None) -> bool:
        return bool(issuer) and issuer in self.issuers


_cache: dict[str, tuple[tuple[int, int], ServerCas | None]] = {}


def load(path: str | None = None) -> ServerCas | None:
    """The CAs in the file, or None when there is no usable file."""
    path = path or get_settings().tak_ca_file
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = (st.st_mtime_ns, st.st_size)
    hit = _cache.get(path)
    if hit and hit[0] == key:
        return hit[1]
    result = _read(path, st.st_size)
    _cache[path] = (key, result)
    return result


def _read(path: str, size: int) -> ServerCas | None:
    if size > MAX_BYTES:
        log.warning("TAK Server CA file %s is %d bytes, over %d: ignored", path, size, MAX_BYTES)
        return None
    try:
        with open(path, "rb") as handle:
            certs = x509.load_pem_x509_certificates(handle.read())
    except (OSError, ValueError) as exc:
        log.warning("TAK Server CA file %s could not be read: %s", path, type(exc).__name__)
        return None
    issuers = chained_subjects(certs)
    if not issuers:
        log.warning("TAK Server CA file %s has no CA that chains to a self-signed root: ignored", path)
        return None
    return ServerCas(frozenset(issuers))


def _is_ca(cert: x509.Certificate) -> bool:
    try:
        return cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    except x509.ExtensionNotFound:
        return False


def _issued_by(cert: x509.Certificate, parent: x509.Certificate) -> bool:
    if cert.issuer != parent.subject:
        return False
    try:
        cert.verify_directly_issued_by(parent)
    except (ValueError, TypeError, InvalidSignature):
        return False
    return True


def chained_subjects(certs: list[x509.Certificate]) -> set[str]:
    """Subjects of the CA certificates that chain to a self-signed root among
    `certs`, the roots included."""
    cas = [c for c in certs if _is_ca(c)]
    trusted = [c for c in cas if _issued_by(c, c)]
    pending = [c for c in cas if c not in trusted]
    grew = True
    while pending and grew:
        grew = False
        for cert in list(pending):
            if any(_issued_by(cert, parent) for parent in trusted):
                trusted.append(cert)
                pending.remove(cert)
                grew = True
    return {c.subject.rfc4514_string() for c in trusted}
