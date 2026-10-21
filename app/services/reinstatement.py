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

"""Bring back a device whose certificate expired, with the security code (W418).

A device offline past its certificate's expiry is refused at the proxy (W417),
and renewal is authenticated by the certificate being renewed, so until now it
needed a factory reset. This lets it back in, on three proofs together:

* **who it was:** its expired certificate, issued by this ATLAS, for a device on
  record;
* **that it is that phone:** a certificate request signed by the same key, which
  lives in the phone's Keystore and cannot be copied off it;
* **that a person with authority is holding it:** the security code from the
  Admin page (the provisioning bypass code), typed on the phone.

⚠️ **Order matters.** The key is checked before the device's state and before
the code. Certificates are not secret (they cross every TLS handshake), so
without that order anyone holding a copy of an expired certificate could probe
a device's status or spend its code attempts. With it, only the phone itself
can.

⚠️ **Never for a device the operator has given up on** (operator, 2026-10-21):
retired, certificate revoked, **breach mode engaged**, or a **disenrollment not
yet acknowledged by the phone**. Those refusals tell the phone only that it
cannot be restored this way; the reason goes to the server log.

⚠️ **Not past 180 days** of expiry: beyond that it is re-provisioned, as before.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from cryptography import x509
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Device, DeviceCertificate, EnrollmentState
from app.security.ca import CertificateAuthority, CertificateError
from app.services import alerts, bypass_pin, certificate_renewal, disenroll

logger = logging.getLogger(__name__)

#: How long after expiry the code still works.
GRACE = timedelta(days=180)

#: The alert event (`alert_rules.EVENTS`).
EVENT = "device_reinstated"

#: What a phone is told when its state rules it out. One message for all of
#: them: a phone in breach mode is presumed to be in the wrong hands.
NOT_ELIGIBLE = (
    "This device can't be restored with the security code. Ask an ATLAS "
    "administrator; it may need to be set up again."
)


def _now() -> datetime:
    """The clock, one place, so a test can move it past an expiry."""
    return datetime.now(timezone.utc)


class Refused(Exception):
    """The request cannot be honoured. `message` is for the phone."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


@dataclass
class Outcome:
    accepted: bool
    attempts_remaining: int
    renewal: certificate_renewal.Renewal | None = None


def blocked_reason(session: Session, device: Device, record: DeviceCertificate) -> str | None:
    """Why this device may not be reinstated, or None. For the log, not the phone."""
    if device.enrollment_state is not EnrollmentState.ENROLLED:
        return f"device is {device.enrollment_state.value}"
    if record.revoked_at is not None:
        return "its certificate was revoked"
    if device.breach_engaged_at is not None:
        return "breach mode is engaged"
    if disenroll.pending(session, device) is not None:
        return "a disenrollment is pending that the phone has not acknowledged"
    return None


def reinstate(
    session: Session,
    ca: CertificateAuthority,
    *,
    certificate_pem: str,
    csr_pem: str,
    pin: str,
    validity_days: int,
    now: datetime | None = None,
) -> Outcome:
    """Check everything, then issue a fresh certificate. Raises `Refused`."""
    now = now or _now()

    try:
        certificate = x509.load_pem_x509_certificate(certificate_pem.encode())
    except Exception as exc:
        raise Refused(400, "The certificate could not be read.") from exc
    try:
        ca.verify(certificate, allow_expired_leaf=True)
        device_id = CertificateAuthority.device_id_from(certificate)
    except CertificateError as exc:
        raise Refused(401, "This certificate was not issued by this ATLAS.") from exc

    expired_at = certificate.not_valid_after_utc
    if now <= expired_at:
        raise Refused(409, "This certificate has not expired; it renews on its own.")
    if now - expired_at > GRACE:
        raise Refused(
            403,
            "This device's certificate expired more than 180 days ago. Ask an "
            "ATLAS administrator to set the device up again.",
        )

    record = session.scalar(
        select(DeviceCertificate).where(
            DeviceCertificate.serial_hex == format(certificate.serial_number, "x")
        )
    )
    device = session.get(Device, device_id)
    if record is None or device is None or record.device_id != device.id:
        raise Refused(401, "This certificate is not known to this ATLAS.")

    # The phone itself, before anything about its state or the code.
    try:
        csr = x509.load_pem_x509_csr(csr_pem.encode())
    except Exception as exc:
        raise Refused(400, "The certificate request could not be read.") from exc
    if not csr.is_signature_valid or (
        certificate_renewal.public_key_bytes(csr.public_key())
        != certificate_renewal.public_key_bytes(certificate.public_key())
    ):
        raise Refused(403, "The request was not made by the device this certificate belongs to.")

    reason = blocked_reason(session, device, record)
    if reason is not None:
        logger.warning("reinstatement refused for %s: %s", device.serial_number, reason)
        raise Refused(403, NOT_ELIGIBLE)

    if not bypass_pin.verify(session, device, pin, label=f"device {device.serial_number} (reinstate)"):
        return Outcome(False, bypass_pin.attempts_remaining(device))

    try:
        renewal = certificate_renewal.renew(
            session, device, certificate, csr_pem, ca=ca, validity_days=validity_days
        )
    except certificate_renewal.RenewalRefused as exc:
        raise Refused(400, str(exc)) from exc

    # The expired certificate is spent: it brought the device back once.
    record.revoked_at = now
    record.revoked_reason = "reinstated with the security code"
    session.flush()
    logger.warning(
        "device %s reinstated with the security code (certificate expired %s)",
        device.serial_number, expired_at.date(),
    )
    alerts.record_event(
        session, EVENT, device,
        detail=f"certificate had expired {expired_at:%Y-%m-%d}", now=now,
    )
    return Outcome(True, bypass_pin.attempts_remaining(device), renewal)
