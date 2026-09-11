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
import logging
import secrets
import uuid
from collections.abc import Sequence
from contextlib import suppress
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
from app.security.enrollment_qr import EnrollmentQrError, EnrollmentQrGuard
from app.security.token_vault import TokenVault
from app.services import device_identity
from app.services import effective_policy as eff

logger = logging.getLogger(__name__)

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


def resolve_token(
    session: Session, secret: str, *, qr_guard: EnrollmentQrGuard | None = None
) -> EnrollmentToken:
    """Look up a usable token by its secret, or raise.

    Lookup is by hash, so the stored value is useless to anyone reading the
    database. The error message is deliberately uniform: distinguishing "no such
    token" from "expired" would let an attacker probe which secrets exist.

    When `qr_guard` is supplied, a QR-derived secret (Chunk 14) is tried first —
    verifying it costs no database lookup, only recomputing a signature. Every
    legacy secret falls through unchanged: `secrets.token_urlsafe` never produces
    a "." character, so an ordinary token can never look like the four-part
    `{primary_id}.{nonce}.{issued}.{signature}` shape and this branch is a no-op
    for it. Existing tokens, scripts and tests are therefore unaffected whether or
    not a guard is passed.
    """
    if qr_guard is not None:
        primary_id: uuid.UUID | None = None
        with suppress(EnrollmentQrError):
            primary_id = qr_guard.verify(secret)
        if primary_id is not None:
            # The guard verified only the wrapper (signature, age). Whether the
            # primary itself is still usable — not revoked, not expired — is
            # re-checked here, on every use, which is what makes retiring a
            # primary invalidate every QR derived from it immediately rather than
            # only future ones.
            primary = session.get(EnrollmentToken, primary_id)
            if primary is None or not primary.is_usable(now=_utcnow()):
                raise EnrollmentError(
                    "enrollment token is invalid, expired, revoked, or used up"
                )
            return primary

    token = session.scalar(
        select(EnrollmentToken).where(EnrollmentToken.token_hash == _hash_secret(secret))
    )
    if token is None or not token.is_usable(now=_utcnow()):
        raise EnrollmentError("enrollment token is invalid, expired, revoked, or used up")
    return token


# A primary token is meant to be persistent, not merely long-lived — the operator's
# own word. Rather than make `expires_at` nullable and thread a None-handling branch
# through every `is_usable()` / `unusable_reason()` call site, it gets an expiry far
# enough out that reaching it is not a case worth designing for.
_PRIMARY_TOKEN_LIFETIME_HOURS = 24 * 365 * 50  # 50 years


def get_primary_token(session: Session) -> EnrollmentToken | None:
    """The one standing enrollment token, if one has been created."""
    return session.scalar(
        select(EnrollmentToken).where(
            EnrollmentToken.is_primary.is_(True),
            EnrollmentToken.revoked_at.is_(None),
        )
    )


def retire_and_create_primary(
    session: Session,
    *,
    name: str,
    group_ids: Sequence[uuid.UUID] = (),
    tag_ids: Sequence[uuid.UUID] = (),
    created_by: str | None = None,
    vault: TokenVault | None = None,
) -> EnrollmentToken:
    """Retire whichever primary token is live, and stand up a new one.

    One call for what the operator described as one action: "it can be retired and
    a new one made". The old primary is revoked and flushed *before* the new row is
    inserted — the database's partial unique index only allows one row with
    `is_primary AND revoked_at IS NULL` at a time, so creating the replacement
    first would violate the very guarantee this method exists to uphold.

    The new token's raw secret is not returned. Nothing needs it: the primary is
    never displayed or typed in by hand, only its QR-derived children are.
    """
    current = get_primary_token(session)
    if current is not None:
        revoke_token(session, current)

    issued = create_token(
        session,
        name=name,
        ttl_hours=_PRIMARY_TOKEN_LIFETIME_HOURS,
        group_ids=group_ids,
        tag_ids=tag_ids,
        created_by=created_by,
        vault=vault,
    )
    issued.token.is_primary = True
    session.flush()
    return issued.token


def mint_qr_secret(
    session: Session, guard: EnrollmentQrGuard
) -> tuple[EnrollmentToken, str]:
    """A fresh, 15-minute secret resolving to the active primary token.

    Refuses outright when there is no live primary, rather than minting a
    secret that is syntactically valid and will fail the moment a device
    presents it — that failure belongs here, where it can be worded for an
    operator, not on a tablet mid-provisioning.
    """
    primary = get_primary_token(session)
    if primary is None:
        raise EnrollmentError("no active enrollment token; create one first")
    return primary, guard.issue(primary.id)


#: Prefixes the name of a token that exists only to scope a QR to one group, so
#: the Enroll page's token list reads as intended rather than as clutter.
GROUP_TOKEN_PREFIX = "Group: "


def token_for_group(
    session: Session, group: DeviceGroup, *, vault: TokenVault | None = None
) -> EnrollmentToken:
    """The standing enrollment token that places a device into `group` (W121).

    ⚠️ **Get-or-create, one per group** — not one per QR. A QR is already a
    short-lived signed derivative, so minting a fresh *token* each time would
    pile up rows that all do the same thing and each have to be revoked
    separately. One row per group is revocable on its own and reads clearly on
    the Enroll page.

    ⚠️ **Not a primary.** `uq_enrollment_token_one_live_primary` allows only one
    live primary, and this must not compete for that slot; it also must not
    become what the plain QR button resolves to. It is an ordinary token that
    nobody types in by hand — which is exactly what the QR guard already
    supports, because `resolve_token` verifies the signature, loads the id and
    checks `is_usable()` without ever asking whether the token is primary.

    Long-lived for the same reason the primary is: this is a standing
    credential an operator manages, not a one-shot.
    """
    name = f"{GROUP_TOKEN_PREFIX}{group.name}"
    existing = session.scalar(
        select(EnrollmentToken).where(
            EnrollmentToken.name == name, EnrollmentToken.revoked_at.is_(None)
        )
    )
    if existing is not None and existing.is_usable(now=_utcnow()):
        # ⚠️ Re-scoped on every use rather than trusted. A group renamed, or its
        # membership of this token edited by hand, would otherwise leave a QR
        # quietly enrolling into the wrong place — and a QR is a picture that
        # says nothing about what it does.
        if [g.id for g in existing.groups] != [group.id]:
            existing.groups = [group]
            session.flush()
        return existing

    issued = create_token(
        session,
        name=name,
        ttl_hours=_PRIMARY_TOKEN_LIFETIME_HOURS,
        group_ids=[group.id],
        created_by="group QR",
        vault=vault,
    )
    return issued.token


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
    identifiers: list[dict] | None = None,
    qr_guard: EnrollmentQrGuard | None = None,
) -> EnrollmentResult:
    """Enroll (or re-enroll) a device and issue it a client certificate.

    ``identifiers`` is every identity the device can report. Optional: an agent that
    sends only ``serial_number`` still enrolls exactly as before, which matters for a
    fleet whose devices may be dark for weeks and cannot all be upgraded first.
    """
    token = resolve_token(session, secret, qr_guard=qr_guard)

    # Match on any identifier this device has ever used, so a factory reset and
    # re-enrollment re-adopts the existing record (D24). Creating a second row would
    # orphan the device's history and silently drop the group membership that drives
    # its policy stack — and a wipe plus KME re-enroll is a routine event.
    #
    # A *set* rather than one string, because a device's reported identity does move:
    # when Build.getSerial() is refused the agent falls back to ANDROID_ID, which
    # Android changes on every factory reset. Single-key matching forked a new record
    # each time (R13).
    reported = device_identity.parse_reported(identifiers, serial_number=serial_number)
    resolution = device_identity.resolve(session, reported)

    device = resolution.device
    is_reenrollment = device is not None

    if device is None:
        device = Device(serial_number=serial_number)
        session.add(device)
        session.flush()

    device.model = model or device.model
    device.imei = imei or device.imei
    device.os_version = os_version or device.os_version
    device.agent_version = agent_version or device.agent_version
    device.enrollment_state = EnrollmentState.ENROLLED
    session.flush()

    device_identity.record(session, device, reported)
    # A record named after an ANDROID_ID fallback is wrong on the asset register and
    # meaningless to an operator. Once the hardware serial is known, show it.
    device_identity.promote_display_serial(session, device, reported)

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

    # After the re-enrollment reset, which clears compliance_detail — and ambiguity
    # is *most* likely on a re-enrollment, so setting it earlier would wipe the
    # warning in exactly the case that raises it.
    if resolution.is_ambiguous:
        # Two records matched, so the fleet already holds duplicates for what is
        # probably one device. Reported, never merged automatically: combining two
        # histories on a guess is not a decision to take as a side effect of a
        # check-in, and it cannot be undone.
        others = ", ".join(str(d.id) for d in resolution.ambiguous_with)
        logger.warning(
            "device %s enrolled with identifiers also held by: %s", device.id, others
        )
        device.compliance_detail = (
            f"identifiers also match other device record(s): {others}. "
            "Likely duplicates from an earlier identity change; merge them by hand."
        )

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
