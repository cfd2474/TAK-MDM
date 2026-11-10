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

"""Whether a device's certificate has expired, as the console shows it (W419).

⚠️ **ATLAS never sees an expired device try.** The proxy refuses the
certificate before the request reaches the app (W417), so all the console could
say was that the device stopped checking in. What the server *does* know is
when each certificate it issued ends, and that is enough to say why.

A device's certificate is its **newest unrevoked** one: renewal leaves the old
certificate valid until it expires on its own, and reinstatement revokes the one
it replaced (W418).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import Device, DeviceCertificate, EnrollmentState
from app.services import disenroll, reinstatement


@dataclass(frozen=True)
class CertStatus:
    expires_at: datetime
    expired: bool
    #: The last moment the security code can restore it (W418).
    restorable_until: datetime

    def restorable(self, now: datetime) -> bool:
        return self.expired and now <= self.restorable_until


def _status(expires_at: datetime, now: datetime) -> CertStatus:
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return CertStatus(
        expires_at=expires_at,
        expired=now > expires_at,
        restorable_until=expires_at + reinstatement.GRACE,
    )


def for_devices(
    session: Session, device_ids: Iterable[uuid.UUID] | None = None, *, now: datetime | None = None
) -> dict[uuid.UUID, CertStatus]:
    """Each enrolled device's newest unrevoked certificate, in one query."""
    now = now or datetime.now(timezone.utc)
    query = (
        select(DeviceCertificate.device_id, func.max(DeviceCertificate.not_valid_after))
        .join(Device, Device.id == DeviceCertificate.device_id)
        .where(DeviceCertificate.revoked_at.is_(None))
        .where(Device.enrollment_state == EnrollmentState.ENROLLED)
        .group_by(DeviceCertificate.device_id)
    )
    if device_ids is not None:
        query = query.where(DeviceCertificate.device_id.in_(list(device_ids)))
    return {device_id: _status(expires, now) for device_id, expires in session.execute(query)}


def expired(session: Session, *, now: datetime | None = None) -> dict[uuid.UUID, CertStatus]:
    """Only the enrolled devices whose certificate has expired, for the fleet list."""
    return {k: v for k, v in for_devices(session, now=now).items() if v.expired}


def code_ruled_out(session: Session, device: Device) -> bool:
    """Breach mode or a pending disenrollment: the code won't bring it back (W418)."""
    return device.breach_engaged_at is not None or disenroll.pending(session, device) is not None
