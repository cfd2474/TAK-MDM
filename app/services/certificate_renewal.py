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

"""A device renews its own certificate, over the connection it already has (W174).

Before this, a certificate was issued once at enrolment and never again. When it
expired the tablet had to be factory reset and re-provisioned by hand — and the
same was true whenever the issuing intermediate expired, which is what made
rotating a CA a fleet-wide event rather than a maintenance task.

⚠️ **The key never changes.** The device's identity key is EC P-256 inside the
Android Keystore and cannot be exported; renewal asks for a new *certificate* over
the same key. That is what makes this safe to run unattended: there is no swap to
get half-done, and a failed renewal leaves the working certificate exactly where
it was.

⚠️ **The old certificate is not revoked.** The request asking for a new one is
authenticated *by the old one*, so revoking it on issue would cut the connection
carrying the reply — and a device that never received the answer would have
destroyed the credential it had. Old certificates expire; they are not withdrawn.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Device, DeviceCertificate
from app.security.ca import CertificateAuthority, CertificateError

logger = logging.getLogger(__name__)


class RenewalRefused(ValueError):
    """The request cannot be honoured. The device keeps the certificate it has."""


@dataclass(frozen=True)
class Renewal:
    certificate_pem: str
    ca_pem: str
    serial_hex: str
    not_valid_after: datetime


def _public_key_bytes(key) -> bytes:
    return key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def should_renew(
    not_valid_after: datetime, *, now: datetime | None = None, window_days: int
) -> bool:
    """Is this certificate close enough to expiry to be worth replacing?

    Expressed as *days remaining* rather than a fraction of life, so that changing
    the issued validity does not silently change when devices renew.

    ⚠️ Already expired counts as due. A device whose certificate has lapsed cannot
    authenticate to ask for a new one, so this can only be reached by one that is
    still inside its window — but a caller reasoning about a stored expiry should
    get the obvious answer rather than `False`.
    """
    moment = now or datetime.now(timezone.utc)
    if not_valid_after.tzinfo is None:
        not_valid_after = not_valid_after.replace(tzinfo=timezone.utc)
    return (not_valid_after - moment).total_seconds() <= window_days * 86400


def renew(
    session: Session,
    device: Device,
    presented: x509.Certificate,
    csr_pem: str,
    *,
    ca: CertificateAuthority,
    validity_days: int,
) -> Renewal:
    """Issue a fresh certificate for an already-authenticated device.

    ``presented`` is the certificate the caller authenticated with — the proof
    that this request comes from the device it claims to be.
    """
    try:
        csr = x509.load_pem_x509_csr(csr_pem.encode())
    except Exception as exc:
        raise RenewalRefused("the certificate request could not be read") from exc

    # Proof of possession: the request is signed by the key it names.
    if not csr.is_signature_valid:
        raise RenewalRefused("the certificate request is not correctly signed")

    # ⚠️ The same key, or nothing. The agent's own installer refuses a certificate
    # issued for a key it does not hold — so issuing one would produce a
    # certificate the device is obliged to throw away, and an operator watching a
    # device "fail to renew" with no error on either side.
    #
    # It is also the conservative reading of what renewal means: a new validity
    # window on an existing identity, not a new identity.
    if _public_key_bytes(csr.public_key()) != _public_key_bytes(presented.public_key()):
        raise RenewalRefused(
            "the certificate request is for a different key than the one this "
            "device authenticated with; renewal keeps the existing key"
        )

    try:
        issued = ca.sign_csr(
            csr_pem,
            device_id=device.id,
            serial_number=device.serial_number,
            validity_days=validity_days,
        )
    except CertificateError as exc:
        raise RenewalRefused(str(exc)) from exc

    session.add(
        DeviceCertificate(
            device_id=device.id,
            serial_hex=issued.serial_hex,
            not_valid_after=issued.not_valid_after,
        )
    )
    session.flush()

    logger.info(
        "device %s renewed its certificate: %s expires %s (previous %s remains "
        "valid until it expires)",
        device.serial_number,
        issued.serial_hex[:16],
        issued.not_valid_after.date(),
        format(presented.serial_number, "x")[:16],
    )

    return Renewal(
        certificate_pem=issued.to_pem(),
        # ⚠️ The whole trust bundle, not just the signing certificate. A device
        # that stored only its issuer would be unable to build a chain once that
        # intermediate retired.
        ca_pem=ca.trust_bundle_pem(),
        serial_hex=issued.serial_hex,
        not_valid_after=issued.not_valid_after,
    )


def active_certificates(session: Session, device_id) -> list[DeviceCertificate]:
    """Every unrevoked certificate on record for a device, newest first.

    More than one is normal during a renewal overlap and is not a fault.
    """
    return list(
        session.scalars(
            select(DeviceCertificate)
            .where(
                DeviceCertificate.device_id == device_id,
                DeviceCertificate.revoked_at.is_(None),
            )
            .order_by(DeviceCertificate.issued_at.desc())
        )
    )
