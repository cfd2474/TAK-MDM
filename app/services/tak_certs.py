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

"""TAK Server certificates uploaded for an ATAK_CONFIG connection (W365).

A connection that authenticates with certificates needs two PKCS#12 files: the
CA **truststore** (certificates only, as TAK Server's `truststore-*.p12`) and the
**client** certificate (a key and its certificate chain). Both are opened with
their passwords at upload, so a wrong password or the wrong kind of file is
refused in the console rather than discovered as a connection that never comes
up on a tablet.

⚠️ **TAK's own truststores use legacy PKCS#12 encryption** (RC2/3DES). The
`openssl` CLI needs `-legacy` to read one; `cryptography` reads it as is
(checked 2026-10-09 against a real `truststore-INTERMEDIATE-CA-01.p12`).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import datetime

from cryptography.hazmat.primitives.serialization import pkcs12
from sqlalchemy.orm import Session

from app.artifacts.storage import ArtifactStorage
from app.db.models import Artifact

#: ATAK's data-package slot carries at most 64 KB once base64'd (platform
#: reference §10a). A real `.p12` is a few KB; anything near this is not one.
MAX_P12_BYTES = 32 * 1024

TRUSTSTORE = "truststore"
CLIENT = "client"

MEDIA_TYPE = "application/x-pkcs12"


class CertError(ValueError):
    """An uploaded file that cannot serve as the certificate asked for."""


@dataclass(frozen=True)
class P12Info:
    """What an operator needs to see to know they uploaded the right file."""

    kind: str
    #: The client certificate's subject, or the first CA's for a truststore.
    subject: str
    issuer: str
    #: The earliest expiry among the certificates that matter: the client
    #: certificate itself, or every CA in a truststore.
    not_after: datetime
    certificate_count: int

    def describe(self) -> str:
        return f"{self.subject}, expires {self.not_after:%Y-%m-%d}"


def inspect(data: bytes, password: str, *, expect: str) -> P12Info:
    """Open a `.p12` with its password and check it is the kind expected.

    :param expect: :data:`TRUSTSTORE` or :data:`CLIENT`.
    :raises CertError: with a sentence the console can show as is.
    """
    if expect not in (TRUSTSTORE, CLIENT):
        raise ValueError(f"unknown certificate kind {expect!r}")
    if not data:
        raise CertError("the file is empty")
    if len(data) > MAX_P12_BYTES:
        raise CertError(
            f"the file is {len(data) // 1024} KB; a TAK certificate file is a few KB"
        )
    try:
        bundle = pkcs12.load_pkcs12(data, (password or "").encode("utf-8") or None)
    except ValueError:
        raise CertError(
            "the password does not open this file, or it is not a .p12 certificate file"
        ) from None

    extra = [entry.certificate for entry in bundle.additional_certs]
    if expect == CLIENT:
        if bundle.key is None or bundle.cert is None:
            raise CertError(
                "this file holds no private key, so it is not a client certificate. "
                "Is it the CA truststore?"
            )
        cert = bundle.cert.certificate
        return P12Info(
            kind=CLIENT,
            subject=cert.subject.rfc4514_string(),
            issuer=cert.issuer.rfc4514_string(),
            not_after=cert.not_valid_after_utc,
            certificate_count=1 + len(extra),
        )

    if bundle.key is not None:
        raise CertError(
            "this file holds a private key, so it is a client certificate, not the "
            "CA truststore"
        )
    cas = ([bundle.cert.certificate] if bundle.cert is not None else []) + extra
    if not cas:
        raise CertError("this file holds no certificates")
    first = cas[0]
    return P12Info(
        kind=TRUSTSTORE,
        subject=first.subject.rfc4514_string(),
        issuer=first.issuer.rfc4514_string(),
        not_after=min(cert.not_valid_after_utc for cert in cas),
        certificate_count=len(cas),
    )


def ingest(
    session: Session, storage: ArtifactStorage, data: bytes, password: str, *, expect: str
) -> tuple[str, P12Info]:
    """Check an uploaded `.p12` and store it. Returns ``(sha256, info)``.

    Stored content-addressed like every other blob, but **not** in the file
    library: a certificate chosen inside one policy is not a fleet asset, and
    listing it in Content would invite deploying it as a plain file.
    """
    info = inspect(data, password, expect=expect)
    digest, size = storage.put(io.BytesIO(data))
    if session.get(Artifact, digest) is None:
        session.add(Artifact(sha256=digest, size_bytes=size, media_type=MEDIA_TYPE))
        session.flush()
    return digest, info

