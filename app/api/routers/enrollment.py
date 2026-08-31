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

"""Enrollment token administration, and the device-facing enrollment endpoint."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import fetch_or_404, get_bundle_signer, get_ca, get_db, get_storage
from app.artifacts.storage import ArtifactStorage
from app.api.schemas import (
    EnrollmentTokenCreate,
    EnrollmentTokenCreated,
    EnrollmentTokenRead,
    EnrollRequest,
    EnrollResponse,
    ProvisioningRequest,
)
from app.config import Settings, get_settings
from app.db.models import AppPackage, EnrollmentToken, PartRole
from app.security.admin_auth import AdminIdentity, admin_required
from app.security.bundle import BundleSigner
from app.security.ca import CertificateAuthority, CertificateError
from app.services import provisioning
from app.services.enrollment import EnrollmentError, create_token, enroll_device, revoke_token

# Administrative: token lifecycle and provisioning payload rendering. Guarded by
# Authentik in main.py.
router = APIRouter(prefix="/api/v1", tags=["enrollment"])

# Device-facing and deliberately NOT behind admin auth. A tablet in its setup
# wizard cannot perform an interactive login: enrollment is authenticated by the
# token it carries, and the agent APK is verified by Android against the signature
# checksum. Keeping these on a separate router makes that boundary explicit rather
# than a per-endpoint detail someone can miss.
device_router = APIRouter(prefix="/api/v1", tags=["enrollment"])


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
    identity: AdminIdentity = Depends(admin_required),
) -> EnrollmentTokenCreated:
    """Create a token. The secret and provisioning payloads are returned once only."""
    issued = create_token(
        session,
        name=payload.name,
        ttl_hours=payload.ttl_hours or settings.enrollment_token_ttl_hours,
        max_uses=payload.max_uses,
        group_ids=payload.group_ids,
        tag_ids=payload.tag_ids,
        created_by=None if identity.is_anonymous else identity.username,
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


@device_router.get("/provisioning/agent.apk")
def download_agent_apk(
    session: Session = Depends(get_db),
    storage: ArtifactStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
) -> Response:
    """Serve the agent APK for Device Owner provisioning. **Unauthenticated.**

    It has to be: Android's setup wizard downloads this before the device has any
    identity, so mTLS is impossible here by definition. The exposure is limited to
    the agent binary itself, which every managed device gets anyway, and Android
    verifies it against `PROVISIONING_DEVICE_ADMIN_SIGNATURE_CHECKSUM` before
    installing — so a substituted APK is rejected by the device, not trusted.
    """
    package = session.scalar(
        select(AppPackage).where(AppPackage.package_name == settings.agent_package_name)
    )
    version = package.latest_version if package else None
    if version is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"no build of {settings.agent_package_name} has been uploaded",
        )

    base = next((f for f in version.files if f.role is PartRole.BASE), None)
    if base is None or not storage.exists(base.artifact_sha256):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "agent artifact is missing")

    return StreamingResponse(
        storage.open(base.artifact_sha256),
        media_type="application/vnd.android.package-archive",
        headers={
            "Content-Disposition": 'attachment; filename="agent.apk"',
            "Content-Length": str(storage.size(base.artifact_sha256)),
        },
    )


@device_router.post(
    "/enroll", response_model=EnrollResponse, status_code=status.HTTP_201_CREATED
)
def enroll(
    payload: EnrollRequest,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    ca: CertificateAuthority = Depends(get_ca),
    signer: BundleSigner = Depends(get_bundle_signer),
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
        bundle_signing_public_key=signer.public_key_base64(),
    )
