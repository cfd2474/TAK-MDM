"""Shared FastAPI dependencies."""

from __future__ import annotations

import uuid
from functools import lru_cache
from urllib.parse import unquote

from cryptography import x509
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.base import get_session
from app.db.models import Device, DeviceCertificate, EnrollmentState
from app.security.ca import CertificateAuthority, CertificateError


def get_db(session: Session = Depends(get_session)) -> Session:
    return session


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
        # nginx's $ssl_client_escaped_cert is URL-encoded; a raw PEM passes through
        # unquote unchanged.
        certificate = x509.load_pem_x509_certificate(unquote(raw).encode())
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
