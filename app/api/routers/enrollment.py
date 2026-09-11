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
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import (
    authenticated_device,
    fetch_or_404,
    get_bundle_signer,
    get_ca,
    get_db,
    get_enrollment_qr_guard,
    get_storage,
    get_token_vault,
)
from app.artifacts.storage import ArtifactStorage
from app.api.schemas import (
    BypassPinRequest,
    BypassPinResult,
    EnrollmentTokenCreate,
    EnrollmentTokenCreated,
    EnrollmentTokenRead,
    EnrollRequest,
    EnrollResponse,
    PrimaryEnrollmentQrIssued,
    PrimaryEnrollmentTokenCreate,
    ProvisioningRequest,
)
from app.config import Settings, get_settings
from app.db.models import AppPackage, Device, EnrollmentToken, PartRole
from app.security.admin_auth import AdminIdentity, admin_required
from app.security.bundle import BundleSigner
from app.security.enrollment_qr import EnrollmentQrGuard
from app.security.token_vault import TokenVault
from app.security.ca import CertificateAuthority, CertificateError
from app.services import bypass_pin
from app.services import packages as package_service
from app.services import provisioning
from app.services.enrollment import (
    EnrollmentError,
    create_token,
    enroll_device,
    get_primary_token,
    mint_qr_secret,
    resolve_token,
    retire_and_create_primary,
    revoke_token,
)

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
    settings: Settings,
    secret: str,
    wifi,
    declared_receivers: tuple[str, ...] | None = None,
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
            declared_receivers=declared_receivers,
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
    storage: ArtifactStorage = Depends(get_storage),
    vault: TokenVault = Depends(get_token_vault),
    identity: AdminIdentity = Depends(admin_required),
) -> EnrollmentTokenCreated:
    """Create a token, returning its secret and provisioning payloads.

    The secret is also sealed into the token so its QR can be re-displayed later;
    see `app/security/token_vault.py` for why that is a deliberate, bounded
    weakening of the original hash-only storage.
    """
    issued = create_token(
        session,
        name=payload.name,
        ttl_hours=payload.ttl_hours or settings.enrollment_token_ttl_hours,
        max_uses=payload.max_uses,
        group_ids=payload.group_ids,
        created_by=None if identity.is_anonymous else identity.username,
        vault=vault,
    )
    session.commit()

    return EnrollmentTokenCreated(
        token=EnrollmentTokenRead.model_validate(issued.token),
        secret=issued.secret,
        provisioning=_provisioning_bundle(
            settings,
            issued.secret,
            payload.wifi,
            package_service.declared_receivers(
                session, storage, settings.agent_package_name
            ),
        ),
    )


@router.get("/enrollment-tokens", response_model=list[EnrollmentTokenRead])
def list_enrollment_tokens(session: Session = Depends(get_db)) -> list[EnrollmentToken]:
    return list(
        session.scalars(select(EnrollmentToken).order_by(EnrollmentToken.created_at.desc()))
    )


# --------------------------------------------------------------------------- #
# The single persistent enrollment token (Chunk 14).
#
# Declared with literal path segments ("primary") ahead of any future
# `{token_id}` route on this prefix, so a UUID-shaped lookup can never be
# shadowed by — or shadow — these.
# --------------------------------------------------------------------------- #


@router.get(
    "/enrollment-tokens/primary", response_model=EnrollmentTokenRead | None
)
def get_primary_enrollment_token(
    session: Session = Depends(get_db),
) -> EnrollmentToken | None:
    """The active primary, or null if none has been created yet."""
    return get_primary_token(session)


@router.post("/enrollment-tokens/primary", response_model=EnrollmentTokenRead)
def create_primary_enrollment_token(
    payload: PrimaryEnrollmentTokenCreate,
    session: Session = Depends(get_db),
    vault: TokenVault = Depends(get_token_vault),
    identity: AdminIdentity = Depends(admin_required),
) -> EnrollmentToken:
    """Retire the current primary (if any) and create its replacement.

    Never returns a secret. Nothing needs one: the primary is never displayed or
    typed in by hand, only 15-minute QR derivatives of it are —
    `POST /enrollment-tokens/primary/qr`.
    """
    token = retire_and_create_primary(
        session,
        name=payload.name,
        group_ids=payload.group_ids,
        created_by=None if identity.is_anonymous else identity.username,
        vault=vault,
    )
    session.commit()
    return token


@router.post("/enrollment-tokens/primary/qr", response_model=PrimaryEnrollmentQrIssued)
def issue_primary_enrollment_qr(
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
    storage: ArtifactStorage = Depends(get_storage),
    guard: EnrollmentQrGuard = Depends(get_enrollment_qr_guard),
) -> PrimaryEnrollmentQrIssued:
    """Mint a fresh, time-boxed secret and its provisioning payloads.

    No database row is created — see `app/security/enrollment_qr.py`. This can be
    called as often as an operator wants without the enrollment-token table
    growing; only the primary itself, created once per retire-and-replace, is
    ever a row.
    """
    try:
        primary, secret = mint_qr_secret(session, guard)
    except EnrollmentError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc

    return PrimaryEnrollmentQrIssued(
        token=EnrollmentTokenRead.model_validate(primary),
        secret=secret,
        expires_at=datetime.now(timezone.utc)
        + timedelta(seconds=settings.enrollment_qr_ttl_seconds),
        provisioning=_provisioning_bundle(
            settings,
            secret,
            wifi=None,
            declared_receivers=package_service.declared_receivers(
                session, storage, settings.agent_package_name
            ),
        ),
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
    guard: EnrollmentQrGuard = Depends(get_enrollment_qr_guard),
) -> dict[str, Any]:
    """Re-render payloads for a secret the operator still holds.

    The secret is verified against a live token so this cannot be used to mint a
    provisioning payload for an arbitrary string. Accepts a QR-derived secret as
    well as an ordinary one, so adding Wi-Fi to an already-generated QR does not
    need a second one minted.
    """
    try:
        resolve_token(session, payload.secret, qr_guard=guard)
    except EnrollmentError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    return _provisioning_bundle(settings, payload.secret, payload.wifi)


@device_router.post("/provisioning/bypass-pin", response_model=BypassPinResult)
def check_bypass_pin(
    payload: BypassPinRequest,
    session: Session = Depends(get_db),
    guard: EnrollmentQrGuard = Depends(get_enrollment_qr_guard),
) -> BypassPinResult:
    """Answer whether a typed PIN matches this install's provisioning bypass code.

    ⚠️ **Token-authenticated, not open.** The PIN is six digits, so an endpoint
    anyone could call would be an oracle a script exhausts in minutes. Requiring
    a live enrollment token limits guessing to whoever an admin already trusted
    to provision a device — the same credential, and the same audience, as
    enrollment itself.

    ⚠️ **The device is told only yes or no**, never the PIN. That is the whole
    reason this is a round trip rather than a value shipped in the provisioning
    extras: a six-digit secret inside a QR code that gets photographed is not a
    secret. `attempts_remaining` is returned so the operator can be told they are
    running out rather than discovering a dead token by surprise.

    A `200` with `accepted: false` rather than a `401`: the caller is a setup
    wizard on a tablet, and the interesting distinction for it is "wrong code"
    versus "could not reach the server", which an HTTP error muddles.
    """
    try:
        token = resolve_token(session, payload.secret, qr_guard=guard)
    except EnrollmentError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc

    accepted = bypass_pin.verify(
        session, token, payload.pin, label=f"token {token.prefix}"
    )
    session.commit()
    return BypassPinResult(
        accepted=accepted,
        attempts_remaining=bypass_pin.attempts_remaining(token),
    )


@device_router.post("/device/bypass-pin", response_model=BypassPinResult)
def check_bypass_pin_enrolled(
    payload: BypassPinRequest,
    session: Session = Depends(get_db),
    device: Device = Depends(authenticated_device),
) -> BypassPinResult:
    """The same check, for a device that has already enrolled.

    ⚠️ **Two endpoints because the credential changes mid-provisioning**, which
    the first version of this feature missed. The enrollment token is destroyed
    the moment enrolment succeeds — deliberately — and the permission screen is
    normally reached *after* that, so the token-authenticated endpoint had no
    credential to offer and the operator was told the code could not be checked.

    Here the client certificate is the credential, and the attempt counter lives
    on the device rather than on a token that no longer exists. `secret` is
    ignored: mTLS already established who is asking.
    """
    accepted = bypass_pin.verify(
        session, device, payload.pin, label=f"device {device.serial_number}"
    )
    session.commit()
    return BypassPinResult(
        accepted=accepted,
        attempts_remaining=bypass_pin.attempts_remaining(device),
    )


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
    qr_guard: EnrollmentQrGuard = Depends(get_enrollment_qr_guard),
) -> EnrollResponse:
    """Device-facing. The enrollment token is the credential; no mTLS yet.

    ``payload.token`` may be an ordinary token's secret or a 15-minute QR-derived
    one (Chunk 14) — `enroll_device` tries the latter first and falls through to
    the former, so this endpoint's contract is unchanged for every existing caller.
    """
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
            identifiers=[i.model_dump() for i in payload.identifiers],
            qr_guard=qr_guard,
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
