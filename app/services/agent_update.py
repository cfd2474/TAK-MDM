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

So a build reaches the fleet in two stages. It is first a **candidate**, offered
only to devices explicitly flagged as canaries; an operator promotes it to
**current** once the canaries are demonstrably healthy on it. Promotion is a
deliberate act, never automatic — the point of a canary is that somebody looks.

Agent builds are ordinary ``AppPackageVersion`` rows for the agent's package, so
the upload history and the content-addressed artifact already exist. All this
module stores is which version is aimed at whom.
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
    PartRole,
)
from app.services import settings_store

#: Highest build offered to the whole fleet.
KEY_CURRENT = "agent.current_version_code"
#: Highest build offered to canaries only, ahead of the fleet.
KEY_CANDIDATE = "agent.candidate_version_code"


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
        return Decision(False, "no agent build is aimed at this device")

    if device_version_code is None:
        # An agent old enough not to report its versionCode is also too old to
        # consume the offer, so sending one would be noise. It needs one manual
        # update (or a policy push) to reach a build that speaks this protocol.
        return Decision(False, "device has not reported an agent versionCode")

    if target_version_code <= device_version_code:
        return Decision(False, "device is already at or above the target build")

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


def target_version_code(session: Session, device: Device) -> int | None:
    """The highest build this device is entitled to: the candidate if it is a
    canary, otherwise the fleet's current build."""
    current = _setting(session, KEY_CURRENT)
    if not device.is_agent_canary:
        return current
    candidate = _setting(session, KEY_CANDIDATE)
    if candidate is None:
        return current
    if current is None:
        return candidate
    return max(current, candidate)


def offer_for(
    session: Session, device: Device, *, package_name: str, settled: bool
) -> dict[str, Any] | None:
    """The agent build to hand this device on this check-in, or None."""
    target = target_version_code(session, device)
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
        return None  # aimed at a build that is no longer uploaded
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


def canary_health(session: Session, candidate: int | None) -> tuple[int, int]:
    """(canaries already on the candidate and compliant, total canaries).

    What an operator needs before promoting: not "did it install" but "is it
    still working". A build that installs and then fails to apply policy is
    exactly the one that must not reach the fleet.
    """
    canaries = list(session.scalars(select(Device).where(Device.is_agent_canary.is_(True))))
    if candidate is None:
        return 0, len(canaries)
    healthy = sum(
        1
        for d in canaries
        if d.agent_version_code == candidate
        and d.compliance_status is ComplianceStatus.COMPLIANT
    )
    return healthy, len(canaries)


def set_candidate(session: Session, version_code: int | None) -> None:
    _store(session, KEY_CANDIDATE, version_code)


def promote(session: Session) -> int | None:
    """Make the candidate the fleet's current build, and clear the candidate."""
    candidate = _setting(session, KEY_CANDIDATE)
    if candidate is None:
        return None
    _store(session, KEY_CURRENT, candidate)
    _store(session, KEY_CANDIDATE, None)
    return candidate


def withdraw_candidate(session: Session) -> None:
    _store(session, KEY_CANDIDATE, None)


def current(session: Session) -> int | None:
    return _setting(session, KEY_CURRENT)


def candidate(session: Session) -> int | None:
    return _setting(session, KEY_CANDIDATE)


# --------------------------------------------------------------------------- #


def _setting(session: Session, key: str) -> int | None:
    raw = settings_store.get(session, key, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _store(session: Session, key: str, value: int | None) -> None:
    settings_store.put(session, key, "" if value is None else str(value))


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
