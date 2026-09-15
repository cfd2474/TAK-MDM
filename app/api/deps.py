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

"""Shared FastAPI dependencies."""

from __future__ import annotations

import uuid
from functools import lru_cache
import base64
from urllib.parse import unquote

from cryptography import x509
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.base import get_session
from app.db.models import Device, DeviceCertificate, EnrollmentState
from app.artifacts.storage import ArtifactStorage, LocalArtifactStorage
from app.security.bundle import BundleSigner
from app.security.ca import CertificateAuthority, CertificateError
from app.security.enrollment_qr import EnrollmentQrGuard
from app.security.token_vault import TokenVault


def get_db(request: Request, session: Session = Depends(get_session)) -> Session:
    """The request's session, and a pointer to it on the request.

    ⚠️ The pointer exists for `_render`, which needs one read (the console's
    display timezone, W163) but is a plain function called from a hundred routes
    rather than a dependency that could ask for a session of its own. Opening a
    second session there instead looked simpler and was wrong twice over: it
    doubles the connection a page holds, and it bypasses `get_session`'s test
    override, so every rendered page in the suite went looking for the real
    Postgres.

    This wrapper is the right place because it is never itself overridden —
    `get_session` is what a test substitutes — so the pointer is correct in both
    worlds.
    """
    request.state.db = session
    return session


def get_session_factory():
    """A callable that opens a *new* session, for work that outlives the request.

    Background work cannot borrow the request's session — it is closed when the
    response is sent. This is a dependency rather than a direct import of
    ``SessionLocal`` so a test can substitute its own factory; importing it
    directly is how a background task ends up talking to the real database in the
    middle of a test run.
    """
    from app.db.base import SessionLocal

    return SessionLocal


@lru_cache
def _certificate_authority(pki_dir: str, common_name: str, validity_days: int):
    from pathlib import Path

    return CertificateAuthority.load_or_create(
        Path(pki_dir), common_name=common_name, validity_days=validity_days
    )


def get_ca(settings: Settings = Depends(get_settings)) -> CertificateAuthority:
    """The device CA. Overridable in tests so they never touch the real PKI dir."""
    return _certificate_authority(
        str(settings.pki_dir), settings.ca_common_name, settings.ca_validity_days
    )


@lru_cache
def _bundle_signer(pki_dir: str) -> BundleSigner:
    from pathlib import Path

    return BundleSigner.load_or_create(Path(pki_dir))


def get_bundle_signer(settings: Settings = Depends(get_settings)) -> BundleSigner:
    """Signs desired-state bundles. Overridable in tests."""
    return _bundle_signer(str(settings.pki_dir))


@lru_cache
def _token_vault(pki_dir: str) -> TokenVault:
    from pathlib import Path

    return TokenVault.load_or_create(Path(pki_dir))


def get_token_vault(settings: Settings = Depends(get_settings)) -> TokenVault:
    """Seals and recovers enrollment token secrets."""
    return _token_vault(str(settings.pki_dir))


@lru_cache
def _enrollment_qr_guard(pki_dir: str, ttl_seconds: int) -> EnrollmentQrGuard:
    from pathlib import Path

    return EnrollmentQrGuard.load_or_create(Path(pki_dir), ttl_seconds=ttl_seconds)


def get_enrollment_qr_guard(
    settings: Settings = Depends(get_settings),
) -> EnrollmentQrGuard:
    """Mints and verifies the 15-minute secrets shown as enrollment QR codes."""
    return _enrollment_qr_guard(str(settings.pki_dir), settings.enrollment_qr_ttl_seconds)


@lru_cache
def _artifact_storage(artifact_dir: str) -> LocalArtifactStorage:
    from pathlib import Path

    return LocalArtifactStorage(Path(artifact_dir))


def get_storage(settings: Settings = Depends(get_settings)) -> ArtifactStorage:
    """Content-addressed blob store. Overridable in tests and swappable for S3."""
    return _artifact_storage(str(settings.artifact_dir))


def require_device(device_id: uuid.UUID, session: Session = Depends(get_db)) -> Device:
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"device {device_id} not found")
    return device


def fetch_or_404(session: Session, model: type, entity_id: uuid.UUID, label: str):
    entity = session.get(model, entity_id)
    if entity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} {entity_id} not found")
    return entity


def _load_client_certificate(raw: str) -> x509.Certificate:
    """The verified client certificate, in whichever shape the proxy sends it.

    Three encodings, because two different proxies front this application and a
    header is all they have in common (W143):

    * **URL-encoded PEM** — nginx's `$ssl_client_escaped_cert`, the standalone
      deployment.
    * **Raw PEM** — passes through `unquote` unchanged, so it always worked.
    * **base64 DER on one line** — Caddy's
      `{http.request.tls.client.certificate_der_base64}`, which is what an
      InfraTAK module gets.

    ⚠️ **Caddy's PEM placeholder is not usable and that is why this exists.**
    `{...certificate_pem}` contains real newlines, and a header value cannot;
    the DER form is the single-line one. Accepting it here costs a few lines and
    saves inventing an encoding for the Caddyfile to perform.

    ⚠️ **Shape only — this decides nothing about trust.** The caller still
    verifies issuer, signature, validity and revocation, and the proxy is still
    what proves the caller holds the private key.
    """
    text = unquote(raw).strip()
    if "BEGIN CERTIFICATE" in text:
        return x509.load_pem_x509_certificate(text.encode())

    # Whitespace is stripped rather than rejected: a proxy that folds a long
    # header is doing something legal, and the payload survives it intact.
    der = base64.b64decode("".join(text.split()), validate=True)
    return x509.load_der_x509_certificate(der)


def presented_certificate(
    request: Request, settings: Settings = Depends(get_settings)
) -> x509.Certificate:
    """The client certificate this request authenticated with.

    ⚠️ **Use only alongside `authenticated_device`**, never instead of it. This
    re-reads the same header without verifying anything — issuer, signature,
    validity and revocation are `authenticated_device`'s job, and a route that
    took this on its own would be trusting a string.

    It exists for certificate renewal (W174), which has to compare the requested
    public key against the one the caller is already using.
    """
    raw = request.headers.get(settings.client_cert_header)
    if not raw:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "no client certificate presented"
        )
    try:
        return _load_client_certificate(raw)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "client certificate is malformed"
        ) from exc


def authenticated_device(
    request: Request,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    ca: CertificateAuthority = Depends(get_ca),
) -> Device:
    """Identify the calling device from its mTLS client certificate.

    The TLS handshake happens at the reverse proxy, which is what actually proves
    the caller holds the private key; the proxy forwards the verified certificate
    in a header. **That proxy must strip this header from inbound requests, and the
    app must never be exposed directly** — otherwise anyone could present a copied
    certificate they do not hold the key for.

    Given that, everything the app *can* independently check, it does: issuer,
    signature, validity window, and revocation.
    """
    raw = request.headers.get(settings.client_cert_header)
    if not raw:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "no client certificate presented"
        )

    try:
        certificate = _load_client_certificate(raw)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "client certificate is malformed"
        ) from exc

    try:
        ca.verify(certificate)
        device_id = CertificateAuthority.device_id_from(certificate)
    except CertificateError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    record = session.scalar(
        select(DeviceCertificate).where(
            DeviceCertificate.serial_hex == format(certificate.serial_number, "x")
        )
    )
    if record is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "certificate is not known")
    if record.revoked_at is not None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "certificate has been revoked")

    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "device no longer exists")
    if device.enrollment_state is not EnrollmentState.ENROLLED:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, f"device is {device.enrollment_state.value}, not enrolled"
        )

    return device
