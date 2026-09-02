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

"""Which agent build a device should install, and whether it may install it now.

The mechanism is proven (see the Android reference: a Device Owner can replace
itself through ``PackageInstaller``, recovering in about four seconds). What this
module adds is **control**, because the failure mode is unusually bad: an agent
build that crashes on start takes remote management with it, and **there is no
rollback** — Android refuses a downgrade, so the only cure is another build with
a higher ``versionCode``.

The safeguard against that is *staging*, not fleet segmentation: a build is
proven on a separate development instance, and only a build that has already
been through it is ever uploaded here. So there is exactly one pointer,
``agent.current_version_code``, and publishing aims it at the whole fleet. This
server has no notion of an unproven build — if it is here, it is meant to run.

Per-device gates still apply, and they are about the device's own condition
rather than the build's: not offering an update to something already failing,
and not churning a build that crashes after one check-in.

Agent builds are ordinary ``AppPackageVersion`` rows for the agent's package, so
the upload history and the content-addressed artifact already exist. All this
module stores is which one is published.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    AppPackage,
    AppPackageVersion,
    ComplianceStatus,
    Device,
    EnrollmentState,
    PartRole,
)
from app.services import settings_store

#: The build published to the fleet. Unset means the channel is inert.
KEY_CURRENT = "agent.current_version_code"


@dataclass(frozen=True)
class Decision:
    offer: bool
    reason: str


def decide(
    *,
    target_version_code: int | None,
    device_version_code: int | None,
    compliance: ComplianceStatus,
    settled: bool,
) -> Decision:
    """Whether to offer ``target_version_code`` to this device right now.

    Pure, so the gate can be exercised without a device or a database. Each
    refusal names itself: "no update offered" is otherwise indistinguishable from
    a broken pipeline, and this is the one feature where a silent no-op is
    indistinguishable from a silent disaster.
    """
    if target_version_code is None:
        return Decision(False, "no agent build has been published")

    if device_version_code is None:
        # An agent old enough not to report its versionCode is also too old to
        # consume the offer, so sending one would be noise. It needs one manual
        # update (or a policy push) to reach a build that speaks this protocol.
        return Decision(False, "device has not reported an agent versionCode")

    if target_version_code <= device_version_code:
        return Decision(False, "device is already at or above the published build")

    if compliance in (ComplianceStatus.DEGRADED, ComplianceStatus.FAILED):
        # Never stack an agent swap on a device that is already failing to apply
        # what it has. Fix the policy failure first; the update will follow.
        return Decision(False, "device is not applying its policy cleanly")

    if not settled:
        # "Settled" means it has checked in at least twice on its current agent
        # build. Without this a crash-looping build that manages one check-in per
        # launch could be handed another update every time it restarts.
        return Decision(False, "waiting for a clean check-in on the current build")

    return Decision(True, "eligible")


def offer_for(
    session: Session, device: Device, *, package_name: str, settled: bool
) -> dict[str, Any] | None:
    """The agent build to hand this device on this check-in, or None."""
    target = current(session)
    decision = decide(
        target_version_code=target,
        device_version_code=device.agent_version_code,
        compliance=device.compliance_status,
        settled=settled,
    )
    if not decision.offer:
        return None

    version = _version(session, package_name, target)
    if version is None:
        return None  # published a build that is no longer uploaded
    base = next((f for f in version.files if f.role is PartRole.BASE), None)
    if base is None:
        return None

    return {
        "package_name": package_name,
        "version_code": version.version_code,
        "version_name": version.version_name,
        "sha256": base.artifact_sha256,
        "size_bytes": base.artifact.size_bytes if base.artifact else 0,
        "url": f"/api/v1/device/artifacts/{base.artifact_sha256}",
    }


def versions(session: Session, package_name: str) -> list[AppPackageVersion]:
    """Every uploaded build of the agent, newest first."""
    package = session.scalar(select(AppPackage).where(AppPackage.package_name == package_name))
    if package is None:
        return []
    return sorted(package.versions, key=lambda v: v.version_code, reverse=True)


@dataclass(frozen=True)
class Rollout:
    """How far the published build has actually reached.

    Reported instead of a progress bar because the interesting number is not
    "how many installed it" but "how many are healthy on it". A build that
    installs and then fails to apply policy is the one an operator has to catch,
    and it would show as 100% complete on any count of installs alone.
    """

    published: int | None
    on_published: int = 0
    behind: int = 0
    unreported: int = 0
    unhealthy: int = 0
    total: int = 0


def rollout(session: Session) -> Rollout:
    published = current(session)
    devices = list(
        session.scalars(
            select(Device).where(Device.enrollment_state == EnrollmentState.ENROLLED)
        )
    )

    on_published = behind = unreported = unhealthy = 0
    for device in devices:
        if device.compliance_status in (ComplianceStatus.DEGRADED, ComplianceStatus.FAILED):
            unhealthy += 1
        if device.agent_version_code is None:
            unreported += 1
        elif published is not None and device.agent_version_code < published:
            behind += 1
        elif device.agent_version_code == published:
            on_published += 1

    return Rollout(
        published=published,
        on_published=on_published,
        behind=behind,
        unreported=unreported,
        unhealthy=unhealthy,
        total=len(devices),
    )


def publish(session: Session, version_code: int | None, *, updated_by: str | None = None) -> None:
    """Aim the fleet at a build, or (with None) make the channel inert."""
    settings_store.put(
        session,
        KEY_CURRENT,
        "" if version_code is None else str(version_code),
        updated_by=updated_by,
    )


def current(session: Session) -> int | None:
    raw = settings_store.get(session, KEY_CURRENT, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        # A hand-edited setting should make the channel inert, not crash every
        # check-in in the fleet.
        return None


# --------------------------------------------------------------------------- #


def _version(
    session: Session, package_name: str, version_code: int | None
) -> AppPackageVersion | None:
    if version_code is None:
        return None
    return session.scalar(
        select(AppPackageVersion)
        .join(AppPackage, AppPackageVersion.package_id == AppPackage.id)
        .where(
            AppPackage.package_name == package_name,
            AppPackageVersion.version_code == version_code,
        )
    )
