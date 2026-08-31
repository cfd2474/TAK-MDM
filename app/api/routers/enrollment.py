"""Enrollment token administration, and the device-facing enrollment endpoint."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import fetch_or_404, get_ca, get_db
from app.api.schemas import (
    EnrollmentTokenCreate,
    EnrollmentTokenCreated,
    EnrollmentTokenRead,
    EnrollRequest,
    EnrollResponse,
    ProvisioningRequest,
)
from app.config import Settings, get_settings
from app.db.models import EnrollmentToken
from app.security.ca import CertificateAuthority, CertificateError
from app.services import provisioning
from app.services.enrollment import EnrollmentError, create_token, enroll_device, revoke_token

router = APIRouter(prefix="/api/v1", tags=["enrollment"])


def _provisioning_bundle(
    settings: Settings, secret: str, wifi
) -> dict[str, Any]:
    """QR and KME payloads. QR is best-effort: KME stays useful without a checksum."""
    bundle: dict[str, Any] = {"kme": provisioning.kme_payload(settings, secret)}
    try:
        bundle["qr"] = provisioning.qr_payload(
            settings,
            secret,
            wifi_ssid=wifi.ssid if wifi else None,
            wifi_password=wifi.password if wifi else None,
            wifi_security=wifi.security if wifi else "WPA",
        )
    except provisioning.ProvisioningError as exc:
        bundle["qr"] = None
        bundle["qr_unavailable_reason"] = str(exc)
    return bundle


@router.post(
    "/enrollment-tokens",
    response_model=EnrollmentTokenCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_enrollment_token(
    payload: EnrollmentTokenCreate,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> EnrollmentTokenCreated:
    """Create a token. The secret and provisioning payloads are returned once only."""
    issued = create_token(
        session,
        name=payload.name,
        ttl_hours=payload.ttl_hours or settings.enrollment_token_ttl_hours,
        max_uses=payload.max_uses,
        group_ids=payload.group_ids,
        tag_ids=payload.tag_ids,
    )
    session.commit()

    return EnrollmentTokenCreated(
        token=EnrollmentTokenRead.model_validate(issued.token),
        secret=issued.secret,
        provisioning=_provisioning_bundle(settings, issued.secret, payload.wifi),
    )


@router.get("/enrollment-tokens", response_model=list[EnrollmentTokenRead])
def list_enrollment_tokens(session: Session = Depends(get_db)) -> list[EnrollmentToken]:
    return list(
        session.scalars(select(EnrollmentToken).order_by(EnrollmentToken.created_at.desc()))
    )


@router.post("/enrollment-tokens/{token_id}/revoke", response_model=EnrollmentTokenRead)
def revoke_enrollment_token(
    token_id: uuid.UUID, session: Session = Depends(get_db)
) -> EnrollmentToken:
    token = fetch_or_404(session, EnrollmentToken, token_id, "enrollment token")
    revoke_token(session, token)
    session.commit()
    return token


@router.post("/provisioning/payloads")
def render_provisioning_payloads(
    payload: ProvisioningRequest,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Re-render payloads for a secret the operator still holds.

    The secret is verified against a live token so this cannot be used to mint a
    provisioning payload for an arbitrary string.
    """
    from app.services.enrollment import resolve_token

    try:
        resolve_token(session, payload.secret)
    except EnrollmentError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    return _provisioning_bundle(settings, payload.secret, payload.wifi)


@router.post("/enroll", response_model=EnrollResponse, status_code=status.HTTP_201_CREATED)
def enroll(
    payload: EnrollRequest,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    ca: CertificateAuthority = Depends(get_ca),
) -> EnrollResponse:
    """Device-facing. The enrollment token is the credential; no mTLS yet."""
    try:
        result = enroll_device(
            session,
            secret=payload.token,
            csr_pem=payload.csr_pem,
            serial_number=payload.serial_number,
            ca=ca,
            certificate_validity_days=settings.device_cert_validity_days,
            model=payload.model,
            imei=payload.imei,
            os_version=payload.os_version,
            agent_version=payload.agent_version,
        )
    except EnrollmentError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    except CertificateError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    session.commit()

    return EnrollResponse(
        device_id=result.device.id,
        certificate_pem=result.certificate_pem,
        ca_certificate_pem=result.ca_certificate_pem,
        not_valid_after=result.not_valid_after,
        state_version=result.device.state_version,
    )
