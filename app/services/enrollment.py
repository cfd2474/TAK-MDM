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

"""Enrollment: token issuance, and turning a token plus a CSR into a known device."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ComplianceStatus,
    Device,
    DeviceCertificate,
    DeviceGroup,
    EnrollmentState,
    EnrollmentToken,
    Tag,
)
from app.security.ca import CertificateAuthority
from app.security.token_vault import TokenVault
from app.services import effective_policy as eff

_PREFIX_LENGTH = 8


class EnrollmentError(ValueError):
    """Raised when a token is unusable or an enrollment request is malformed."""


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class IssuedToken:
    token: EnrollmentToken
    # Returned exactly once. It is not recoverable from the stored hash.
    secret: str


def create_token(
    session: Session,
    *,
    name: str,
    ttl_hours: int,
    max_uses: int | None = None,
    group_ids: Sequence[uuid.UUID] = (),
    tag_ids: Sequence[uuid.UUID] = (),
    created_by: str | None = None,
    vault: TokenVault | None = None,
) -> IssuedToken:
    secret = secrets.token_urlsafe(32)

    token = EnrollmentToken(
        name=name,
        token_hash=_hash_secret(secret),
        # Sealed so the QR can be shown again later. Without a vault the token
        # still works; its QR simply cannot be re-displayed.
        token_ciphertext=vault.seal(secret) if vault else None,
        prefix=secret[:_PREFIX_LENGTH],
        expires_at=_utcnow() + timedelta(hours=ttl_hours),
        max_uses=max_uses,
        created_by=created_by,
    )
    if group_ids:
        token.groups = list(session.scalars(select(DeviceGroup).where(DeviceGroup.id.in_(group_ids))))
    if tag_ids:
        token.tags = list(session.scalars(select(Tag).where(Tag.id.in_(tag_ids))))

    session.add(token)
    session.flush()
    return IssuedToken(token=token, secret=secret)


def resolve_token(session: Session, secret: str) -> EnrollmentToken:
    """Look up a usable token by its secret, or raise.

    Lookup is by hash, so the stored value is useless to anyone reading the
    database. The error message is deliberately uniform: distinguishing "no such
    token" from "expired" would let an attacker probe which secrets exist.
    """
    token = session.scalar(
        select(EnrollmentToken).where(EnrollmentToken.token_hash == _hash_secret(secret))
    )
    if token is None or not token.is_usable(now=_utcnow()):
        raise EnrollmentError("enrollment token is invalid, expired, revoked, or used up")
    return token


def reveal_secret(token: EnrollmentToken, vault: TokenVault) -> str | None:
    """Recover a token's secret so its QR can be re-rendered, or None."""
    return vault.open(token.token_ciphertext)


def revoke_token(session: Session, token: EnrollmentToken) -> None:
    if token.revoked_at is None:
        token.revoked_at = _utcnow()
        session.flush()


@dataclass(frozen=True)
class EnrollmentResult:
    device: Device
    certificate_pem: str
    ca_certificate_pem: str
    not_valid_after: datetime


def enroll_device(
    session: Session,
    *,
    secret: str,
    csr_pem: str,
    serial_number: str,
    ca: CertificateAuthority,
    certificate_validity_days: int,
    model: str | None = None,
    imei: str | None = None,
    os_version: str | None = None,
    agent_version: str | None = None,
) -> EnrollmentResult:
    """Enroll (or re-enroll) a device and issue it a client certificate."""
    token = resolve_token(session, secret)

    # Match on serial so a factory reset and re-enrollment re-adopts the existing
    # record (D24). Creating a second row would orphan the device's history and
    # silently drop the group membership that drives its policy stack — and a wipe
    # plus KME re-enroll is a routine event, not an exception.
    device = session.scalar(select(Device).where(Device.serial_number == serial_number))
    is_reenrollment = device is not None

    if device is None:
        device = Device(serial_number=serial_number)
        session.add(device)

    device.model = model or device.model
    device.imei = imei or device.imei
    device.os_version = os_version or device.os_version
    device.agent_version = agent_version or device.agent_version
    device.enrollment_state = EnrollmentState.ENROLLED
    session.flush()

    if is_reenrollment:
        # The old key is gone with the wipe; leaving its certificate valid would
        # leave a usable identity outstanding.
        revoke_device_certificates(session, device, reason="re-enrollment")
        # A wiped device has definitively applied nothing, whatever it reported
        # before. Claiming otherwise would leave the console showing a compliance
        # verdict for a state that no longer exists on the hardware.
        device.acked_state_version = 0
        device.compliance_status = ComplianceStatus.UNKNOWN
        device.compliance_detail = None

    issued = ca.sign_csr(
        csr_pem,
        device_id=device.id,
        serial_number=serial_number,
        validity_days=certificate_validity_days,
    )
    session.add(
        DeviceCertificate(
            device_id=device.id,
            serial_hex=issued.serial_hex,
            not_valid_after=issued.not_valid_after,
        )
    )

    # Token scoping is additive: enrolling with a second token adds membership
    # rather than replacing it.
    existing_groups = {g.id for g in device.groups}
    device.groups.extend(g for g in token.groups if g.id not in existing_groups)
    existing_tags = {t.id for t in device.tags}
    device.tags.extend(t for t in token.tags if t.id not in existing_tags)

    token.use_count += 1
    session.flush()

    # Membership just changed, so the device's policy stack has too.
    eff.invalidate(session, [device.id])
    eff.refresh(session, device)

    return EnrollmentResult(
        device=device,
        certificate_pem=issued.to_pem(),
        ca_certificate_pem=ca.certificate_pem(),
        not_valid_after=issued.not_valid_after,
    )


def revoke_device_certificates(session: Session, device: Device, *, reason: str) -> int:
    """Revoke every live certificate for a device. Returns how many were revoked."""
    live = session.scalars(
        select(DeviceCertificate).where(
            DeviceCertificate.device_id == device.id,
            DeviceCertificate.revoked_at.is_(None),
        )
    ).all()
    now = _utcnow()
    for certificate in live:
        certificate.revoked_at = now
        certificate.revoked_reason = reason
    session.flush()
    return len(live)
