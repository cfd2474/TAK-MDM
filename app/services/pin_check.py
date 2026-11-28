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

"""Pins that give some device models another model's parts (W519).

Operator: a policy "pinned to a specific build from the old system (that may have
been extracted from another device) ... should be able to make the correction, or
notify the user that a policy needs to be edited due to the new change."

Before W519 a Google Play build was downloaded as **one** profile, and a build
taken from a device carries that device's parts. Either holds the parts of one
model: one screen density, one CPU type, some languages. Such a pin still works
after W519 exactly as before (`model_builds` falls back to every part), so
nothing breaks on update. This module says where it is **not right**: a pinned
build with config splits that no record says Play served to a model this policy
reaches.

**The correction.** A fleet download of the same versionCode adds the missing
models' parts to that same build and records them, so the finding clears with no
policy edit. When Play serves a newer version now, the pinned version can no
longer be fetched, and the policy has to be edited to pick the new build. A pin
is never moved silently (R17: a pin is absolute).

Only models with a captured Google Play profile are named: those are the ones a
fleet download can fetch for. A device of any other model gets every part, as it
always has.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppPackageFile, AppPackageVersion, Device, PartRole, PlayDeviceProfile
from app.services import build_compat, model_builds, play_profiles


@dataclass(frozen=True)
class ModelGap:
    """One model a pinned build was not served to, and its devices."""

    model_key: str
    label: str
    devices: tuple[Device, ...]


@dataclass(frozen=True)
class PinFinding:
    """A pinned build that some models reached by the policy got no parts for."""

    package_name: str
    label: str
    version_code: int
    version_name: str | None
    #: The profile or source it came from, for the operator: "Galaxy S25",
    #: "uploaded".
    origin: str
    gaps: tuple[ModelGap, ...]

    @property
    def device_count(self) -> int:
        return sum(len(g.devices) for g in self.gaps)


def _has_config_splits(version: AppPackageVersion) -> bool:
    return any(f.role.value == "split" and f.split_name for f in version.files)


def _covered(session: Session, version: AppPackageVersion, device: Device,
             recorded: bool) -> bool:
    """True when this device gets parts Play served to its own model."""
    if model_builds.served(session, version, device.model) is not None:
        return True
    if model_builds.sibling(session, version, device) is not version:
        return True
    # A build from before W519 downloaded as this very model.
    return not recorded and model_builds.downloaded_for(version, device.model)


def findings(session: Session, specs: Iterable[Any], devices: Iterable[Device]) -> list[PinFinding]:
    """The pinned builds in `specs` that give some of `devices` another model's parts."""
    specs = list(specs)
    shas = set().union(*(build_compat.pinned_builds(s) for s in specs)) if specs else set()
    profiled = set(session.scalars(select(PlayDeviceProfile.model_key)))
    devices = [d for d in devices if d.model and play_profiles.model_key(d.model) in profiled]
    if not shas or not devices:
        return []
    found: dict[Any, PinFinding] = {}
    for part in session.scalars(select(AppPackageFile).where(AppPackageFile.artifact_sha256.in_(shas))):
        version = part.version
        if version is None or version.id in found or not _has_config_splits(version):
            continue
        recorded = bool(model_builds.served_to(session, version))
        by_model: dict[str, list[Device]] = {}
        for device in devices:
            if not _covered(session, version, device, recorded):
                by_model.setdefault(play_profiles.model_key(device.model), []).append(device)
        if not by_model:
            continue
        package = version.package
        found[version.id] = PinFinding(
            package_name=package.package_name,
            label=package.label or package.package_name,
            version_code=version.version_code,
            version_name=version.version_name,
            origin=version.downloaded_as or version.source or "uploaded",
            gaps=tuple(
                ModelGap(key, model_builds.model_label(found_devices[0].model), tuple(found_devices))
                for key, found_devices in sorted(by_model.items())
            ),
        )
    return sorted(found.values(), key=lambda f: (f.label.lower(), f.version_code))


@dataclass(frozen=True)
class PolicyNotice:
    """A policy with pins that give some of its devices another model's parts."""

    policy_id: Any
    name: str
    findings: tuple[PinFinding, ...]


def policies_needing_edit(session: Session) -> list[PolicyNotice]:
    """Every policy with a finding, for the notice on the Apps page.

    Cheap first: only policies pinning a build with config splits are looked at
    further, so a library of universal APKs costs one query.
    """
    from app.db.models import Policy
    from app.services import effective_policy as eff

    specs = {
        policy.id: (policy, policy.latest_version.spec)
        for policy in session.scalars(select(Policy))
        if policy.latest_version is not None
    }
    pinned = {pid: build_compat.pinned_builds(spec) for pid, (_, spec) in specs.items()}
    every = set().union(*pinned.values()) if pinned else set()
    if not every:
        return []
    with_splits = select(AppPackageFile.version_id).where(AppPackageFile.role == PartRole.SPLIT)
    split_builds = set(session.scalars(
        select(AppPackageFile.artifact_sha256)
        .where(AppPackageFile.artifact_sha256.in_(every), AppPackageFile.version_id.in_(with_splits))
    ))
    out = []
    for pid, shas in pinned.items():
        if not shas & split_builds:
            continue
        policy, spec = specs[pid]
        ids = eff.devices_affected_by_policy(session, pid)
        devices = list(session.scalars(select(Device).where(Device.id.in_(ids)))) if ids else []
        found = findings(session, [spec], devices)
        if found:
            out.append(PolicyNotice(pid, policy.name, tuple(found)))
    return sorted(out, key=lambda n: n.name.lower())
