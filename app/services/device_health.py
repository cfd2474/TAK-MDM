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

"""Telling a device that never arrived from one that is merely away (W81).

⚠️ **This deliberately does not delete anything.** Deleting a device record on
failure was the obvious answer and is the wrong one:

* *"Failing"* and *"offline"* are the same thing from here. A tablet on a boat for
  three weeks looks exactly like a broken one, and those are the devices this MDM
  exists for.
* The record carries the policy stack. Deleting it turns a device that would have
  come back configured into one an operator has to set up again.
* It is not needed. Re-enrolment matches on a *set* of identifiers and readopts
  the existing record — `test_reenrollment_readopts_the_device_and_revokes_the_old_certificate`
  pins that a wipe-and-reprovision keeps the same `device_id`, keeps group
  membership, and revokes the old certificate on the way through.

What was actually missing is the *signal*: a device that enrolled and then never
checked in at all is in a state nobody has to guess about, and the console said
only "never" — which is equally true of one enrolled ten seconds ago.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db.models import Device, EnrollmentState

#: How long after enrolling a device may reasonably not have checked in.
#:
#: ⚠️ Generous on purpose. A healthy device checks in within seconds — the agent
#: syncs immediately after provisioning — so anything past this is not slow, it is
#: stuck. Set tight enough to be useful and loose enough that a first sync racing
#: a flaky network is never called a failure.
STALLED_AFTER = timedelta(minutes=10)


def enrollment_stalled(device: Device, *, now: datetime | None = None) -> bool:
    """True when this device enrolled, then never checked in.

    ⚠️ **Never checked in**, not "has not checked in lately". A device that has
    ever reported is a device whose identity works; its silence is a network or
    power question and none of this applies to it.
    """
    if device.enrollment_state is not EnrollmentState.ENROLLED:
        return False
    if device.last_checkin_at is not None:
        return False
    if device.created_at is None:
        return False

    moment = now or datetime.now(timezone.utc)
    created = device.created_at
    if created.tzinfo is None:
        # Stored naive on some backends; treat it as what it is rather than
        # letting the subtraction raise and hide the whole signal.
        created = created.replace(tzinfo=timezone.utc)
    return moment - created > STALLED_AFTER


def stalled_reason() -> str:
    """What an operator should check, in the order worth checking it.

    Written here rather than in the template because it is knowledge about how
    this fails, not about how a page looks — and because both causes have now
    actually happened.
    """
    return (
        "This device enrolled but has never checked in. Its identity may be "
        "unusable — enrolling twice at once produced a certificate that does not "
        "match the device's key (fixed in agent 0.42.1) — or it cannot reach the "
        "server URL it was provisioned with. A factory reset and re-provision "
        "recovers it, and keeps this record: re-enrolment readopts the device."
    )
