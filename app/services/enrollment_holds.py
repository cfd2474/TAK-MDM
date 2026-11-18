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

"""Re-enrollments held for the security code (W448, audit H1).

See :class:`app.db.models.EnrollmentHold`: the code approves, and a hold only
makes the wait visible and announced once.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import Device, EnrollmentHold

#: How long one held re-enrollment is announced as one (operator: 24 h).
LAPSES_AFTER = timedelta(hours=24)


def current(session: Session, device: Device, now: datetime) -> EnrollmentHold | None:
    """The hold still open for this device, if any."""
    return session.scalar(
        select(EnrollmentHold)
        .where(EnrollmentHold.device_id == device.id, EnrollmentHold.expires_at > now)
        .order_by(EnrollmentHold.created_at.desc())
    )


def open_or_reuse(session: Session, device: Device, reason: str,
                  now: datetime) -> tuple[EnrollmentHold, bool]:
    """The device's open hold, or a new one. True when it is new, and so to be announced."""
    hold = current(session, device, now)
    if hold is not None:
        return hold, False
    # Lapsed ones only clutter the device page's answer to "is it waiting?".
    session.execute(delete(EnrollmentHold).where(EnrollmentHold.device_id == device.id))
    hold = EnrollmentHold(device_id=device.id, created_at=now,
                          expires_at=now + LAPSES_AFTER, reason=reason)
    session.add(hold)
    session.flush()
    return hold, True


def clear(session: Session, device: Device) -> None:
    """The device enrolled: nothing is waiting any more."""
    session.execute(delete(EnrollmentHold).where(EnrollmentHold.device_id == device.id))
