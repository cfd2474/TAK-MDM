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

"""A device in the wrong hands (W193).

Engaging breach mode stops every ordinary policy reaching one device and puts
the breach profile in their place: the library blocked, a passcode the operator
knows, a breach wallpaper and lock note, location every minute, and the named
directories emptied.

⚠️ **Breach deliberately stops short of a wipe.** A wiped device stops reporting
where it is, which is the one thing still worth having from a tablet somebody
else is holding. Making it useless and making it silent are different goals and
this mode picks the first. The wipe, when it is wanted, is `disenroll`.

⚠️ **Nothing is unassigned, disabled or deleted**, and that is the whole design.
:func:`app.services.effective_policy.gather_assignments` asks this module and
returns the breach profile's sections instead of the device's own. Two
alternatives were considered and are worse:

* *Deleting* the device's assignments loses what was there, so nothing can be
  put back and nothing can be audited.
* *Disabling* them — ``Assignment.enabled`` exists and would work — is fine for
  a device-scoped row and catastrophic for a **group-scoped** one: disabling the
  group's assignment to breach one device breaches every device in that group,
  and nothing in the console would say so.

Because no row is touched, :func:`clear` restores every policy exactly, rank and
pinned versions included.

⚠️ **Clearing is not resecuring, and the console must not imply that it is.** A
device that has been in breach has lost its apps and the contents of those
directories; the operator's doctrine is that it is factory wiped and
reprovisioned before it is trusted again. :func:`clear` exists for the misclick.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppPackage, Device, PolicyProfile

log = logging.getLogger(__name__)

#: The reserved profile's name.
#:
#: ⚠️ Looked up by name because it has no other stable handle — it is created on
#: first use rather than by a migration, so there is no id to hard-code. The name
#: is therefore reserved: `profiles.create_profile` must refuse it, or an
#: operator could build an ordinary profile that silently becomes the one every
#: breached device receives.
PROFILE_NAME = "Breach mode"


def is_engaged(device: Device) -> bool:
    """Is this device in breach mode right now?"""
    return device.breach_engaged_at is not None


def profile(session: Session) -> PolicyProfile | None:
    """The reserved breach profile, or None if it has never been configured.

    None is a real answer, not a failure: a deployment that has never opened
    Admin → Breach mode has no breach configuration, and a device breached
    against nothing would receive an empty policy — every ordinary policy gone
    and nothing in its place, which is worse than not breaching at all. Callers
    that act on it must check.
    """
    return session.scalar(
        select(PolicyProfile).where(PolicyProfile.name == PROFILE_NAME)
    )


#: What a freshly created breach profile does, before anyone edits it.
#:
#: ⚠️ **Defaults that are useful on their own.** An operator who never opens
#: Admin → Breach mode still gets a device reporting its position every minute
#: with a note on the lock screen — which is most of the value — rather than a
#: button that turns out to have done nothing. What it deliberately does *not*
#: default to is a passcode: inventing one would mean a device locked with a
#: value nobody chose and nobody was shown.
#: ⚠️ **Two different defaults, and the asymmetry is deliberate.** `BreachSpec`
#: defaults `purge_paths` to *absent*, so no ordinary device ever carries a
#: destructive instruction. The reserved profile defaults it to the directories
#: an operator asked breach mode to empty, so pressing the button does what the
#: page says it does without anyone having configured it first.
DEFAULT_SECTIONS: dict[str, dict] = {
    "breach": {
        "purge_paths": [
            "/sdcard/Download",
            "/sdcard/Documents",
            "/sdcard/atak",
            "/sdcard/DCIM",
            "/sdcard/Pictures",
        ]
    },
    "tracking_fencing": {"reporting_interval_minutes": 1},
    "customizations": {
        "lock_screen_message": (
            "This device has been reported lost or stolen and is being tracked. "
            "Please return it to its owner."
        )
    },
}


def blocklist(session: Session) -> list[str]:
    """Every app and plugin in the library, minus the two that must survive.

    ⚠️ **Computed live, never cached.** A stored copy is a thing that can be
    stale, and the ways it goes stale — an upload through any of the four
    routers that touch the library, an import, a storefront change — are too
    many to hook reliably. Anything on screen therefore shows the library as it
    is now, and the only writer of the stored copy is :func:`regenerate`, called
    at the one moment the answer has to be frozen.

    ⚠️ **The agent and the launcher come out.** The agent already refuses to
    suppress itself, by name and with a reason, so including it would only add
    an error to every check-in of a device that is already in trouble. The
    launcher has no such self-defence and matters just as much: blocked on a
    kiosk device there is nothing left on screen to reach, including anything
    that could report where the device is.
    """
    from app.config import get_settings
    from app.services.effective_policy import ATLAS_LAUNCHER_PACKAGE

    survives = {get_settings().agent_package_name, ATLAS_LAUNCHER_PACKAGE}
    names = session.scalars(
        select(AppPackage.package_name).order_by(AppPackage.package_name)
    )
    return [name for name in names if name not in survives]


def regenerate(session: Session, profile_: PolicyProfile | None = None) -> list[str]:
    """Freeze the current library into the breach profile's blocklist.

    Returns what was written. Called when the profile is created, and again at
    the moment a device is breached — **not** on every library change.

    ⚠️ **Engage time is the authoritative moment, and it is sufficient.** A
    breached device's policy requires no apps at all, so nothing new can install
    on it; the library as it stands when the button is pressed is exactly the
    set that can be present on that device. Regenerating on every upload would
    mean hooks in four routers, kept correct for ever, to maintain a value that
    is already correct everywhere it is read.
    """
    from app.services import profiles as profile_service

    reserved = profile_ or profile(session)
    if reserved is None:
        return []
    names = blocklist(session)
    profile_service.upsert_section(
        session, reserved, "app_management", {"blocked_packages": names}
    )
    return names


def ensure(session: Session, created_by: str | None = None) -> PolicyProfile:
    """The reserved breach profile, created with :data:`DEFAULT_SECTIONS` if new.

    Created on first use rather than by a migration, so a deployment that never
    touches breach mode carries no policy for it at all — and so the defaults can
    change in a release without a data migration arguing with an operator's
    edits.
    """
    from app.services import profiles as profile_service

    existing = profile(session)
    if existing is not None:
        return existing
    created = profile_service.create_profile(
        session,
        name=PROFILE_NAME,
        description=(
            "Applied to a device reported lost or stolen. Replaces every other "
            "policy on that device."
        ),
        sections=dict(DEFAULT_SECTIONS),
        created_by=created_by,
        reserved=True,
    )
    # ⚠️ **No `regenerate` here, and a mutation sweep is why.** Removing it
    # changed nothing any test or page could see, because the stored blocklist
    # has exactly one reader — a breached device — and `engage` writes it
    # immediately before there is one. The tab shows the *live* library, not
    # this copy. A second writer would only be a second thing to keep correct.
    log.info("created the reserved %r profile", PROFILE_NAME)
    return created


def engage(session: Session, device: Device, by: str | None = None) -> None:
    """Put this device into breach mode, and wake it.

    ⚠️ ``breach_confirmed_at`` is cleared here rather than left alone. Re-engaging
    a device that had confirmed a previous breach must not show the old
    confirmation against the new one — during an incident that reads as "the
    device has already done it" when nothing has reached it yet.
    """
    from app.services import effective_policy as eff

    # ⚠️ Before the flag is set, so the device's very first breach payload
    # already carries the current library rather than whatever was frozen the
    # last time anybody was breached.
    regenerate(session)

    device.breach_engaged_at = datetime.now(timezone.utc)
    device.breach_engaged_by = by
    device.breach_confirmed_at = None
    eff.invalidate(session, [device.id])
    log.warning(
        "breach mode engaged on %s by %s", device.serial_number, by or "an operator"
    )
    from app.services import alerts

    alerts.note_event(
        session,
        "device_breached",
        device,
        f"{device.serial_number} — engaged by {by or 'an operator'}",
    )


def clear(session: Session, device: Device) -> None:
    """Take this device out of breach mode.

    Every policy it had comes back exactly as it was, because none of them were
    touched. ⚠️ Its apps and the emptied directories do not.
    """
    from app.services import effective_policy as eff

    device.breach_engaged_at = None
    device.breach_engaged_by = None
    device.breach_confirmed_at = None
    eff.invalidate(session, [device.id])
    log.warning("breach mode cleared on %s", device.serial_number)


def confirm(session: Session, device: Device) -> bool:
    """Record that the device has reported the breach state applied.

    Returns whether this was the first confirmation, so a caller can log it once
    rather than on every check-in for the rest of the device's life.
    """
    if not is_engaged(device) or device.breach_confirmed_at is not None:
        return False
    device.breach_confirmed_at = datetime.now(timezone.utc)
    log.warning("breach mode confirmed applied on %s", device.serial_number)
    return True
