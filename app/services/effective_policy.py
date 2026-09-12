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

"""Bridges the database to the pure resolver, and memoizes the result.

Everything ORM-shaped lives here so :mod:`app.policies.resolver` stays a pure
function over plain data.

Cache protocol:

* A write that could change any device's desired state calls :func:`invalidate`,
  which drops those devices' cache rows.
* The next read recomputes, and bumps ``Device.state_version`` **only if the
  resolved values actually changed**.

That second point matters more than it looks. ``state_version`` is what the Chunk 3
check-in protocol uses to decide whether to ship a new bundle, so bumping it on
every edit would wake the whole fleet over a renamed policy. Provenance is excluded
from the comparison deliberately: it is admin-facing detail, and a policy rename
changes provenance without changing anything the device should act on.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    AppPackage,
    AppPackageFile,
    AppPackageVersion,
    Assignment,
    AssignmentScope,
    Device,
    EffectivePolicyCache,
    Policy,
    PolicyVersion,
    ProfileAssignment,
)
from app.services import files, notifications, packages
from app.policies.registry import PolicyTypeError, registry
from app.policies.resolver import (
    AssignmentInput,
    EffectivePolicy,
    PolicySnapshot,
    diff_values,
    resolve,
)


def _snapshot(policy: Policy, version: PolicyVersion) -> PolicySnapshot:
    return PolicySnapshot(
        policy_id=str(policy.id),
        policy_name=policy.name,
        policy_type=policy.policy_type,
        version=version.version,
        spec=version.spec or {},
    )


def _effective_version(assignment: Assignment) -> PolicyVersion | None:
    """Pinned version if set, otherwise the policy's latest published version."""
    return assignment.pinned_version or assignment.policy.latest_version


def gather_assignments(session: Session, device: Device) -> list[AssignmentInput]:
    """Every enabled assignment reaching this device, directly or via a group."""
    targets = [Assignment.device_id == device.id]
    group_ids = [g.id for g in device.groups]
    if group_ids:
        targets.append(Assignment.group_id.in_(group_ids))

    rows = session.scalars(
        select(Assignment).where(Assignment.enabled.is_(True), or_(*targets))
    ).all()

    inputs: list[AssignmentInput] = []
    for assignment in rows:
        policy = assignment.policy
        if policy.archived_at is not None:
            continue  # archived policies stop applying without being deleted
        if policy.is_template:
            continue  # a template is a blueprint, never a live policy
        version = _effective_version(assignment)
        if version is None:
            continue  # a policy with no published version contributes nothing
        try:
            registry.get(policy.policy_type)
        except PolicyTypeError:
            continue  # unknown type, e.g. a rolled-back deployment: ignore, don't crash
        inputs.append(
            AssignmentInput(
                assignment_id=str(assignment.id),
                scope=assignment.scope.value,
                rank=assignment.rank,
                policy=_snapshot(policy, version),
            )
        )

    inputs.extend(_gather_profile_assignments(session, device, group_ids))
    return inputs


def _gather_profile_assignments(
    session: Session,
    device: Device,
    group_ids: list[uuid.UUID],
) -> list[AssignmentInput]:
    """Expand every profile assignment reaching this device into one input per
    section the profile owns, all at the profile assignment's rank and scope."""
    targets = [ProfileAssignment.device_id == device.id]
    if group_ids:
        targets.append(ProfileAssignment.group_id.in_(group_ids))

    rows = session.scalars(
        select(ProfileAssignment).where(
            ProfileAssignment.enabled.is_(True), or_(*targets)
        )
    ).all()

    inputs: list[AssignmentInput] = []
    for pa in rows:
        profile = pa.profile
        if profile.archived_at is not None:
            continue
        for section in profile.sections:
            if section.archived_at is not None:
                continue
            version = section.latest_version
            if version is None:
                continue
            try:
                registry.get(section.policy_type)
            except PolicyTypeError:
                continue
            inputs.append(
                AssignmentInput(
                    # Stable and unique per (profile assignment, section), so the
                    # resolver treats each section as its own contributor.
                    assignment_id=f"profile:{pa.id}:{section.id}",
                    scope=pa.scope.value,
                    rank=pa.rank,
                    policy=_snapshot(section, version),
                )
            )
    return inputs


def compute(session: Session, device: Device) -> EffectivePolicy:
    """Resolve without touching the cache."""
    return resolve(str(device.id), gather_assignments(session, device))


def resolve_required_apps(
    session: Session, values: Mapping[str, Any]
) -> list[dict[str, Any]]:
    """Turn ``APP_CATALOG.required_apps`` into concrete, downloadable files.

    The policy states intent ("com.atakmap.app, at least version 52400"); this
    resolves it against the uploaded catalog into the exact artifacts the agent
    should fetch and verify.

    Apps with nothing uploaded yet are reported with ``available: false`` rather
    than omitted — an app that is required but missing is a fact the operator needs
    to see, not an absence to be silently tidied away.

    ⚠️ **A kiosk app is required by definition** (W63). Naming one in a KIOSK
    policy is an instruction to lock the device to it, which cannot mean anything
    unless it is installed — and asking an operator to also list it under required
    apps is a second step that exists only to be forgotten. Reported on hardware
    as *"the app designated for kiosk mode not installed, not engaging"*: the
    policy was correct, the device simply had nothing to lock to.

    Added here rather than in the applier so it inherits the whole install
    pipeline — version resolution, artifact hashes, the downgrade rules — instead
    of growing a second, thinner one beside it.
    """
    catalog = values.get("APP_CATALOG") or {}
    required = list(catalog.get("required_apps") or [])

    kiosk = values.get("KIOSK") or {}

    def _require(package_name: str) -> None:
        # No version constraint: an explicit `required_apps` entry for the same app
        # keeps its own pin or floor, because an operator who pinned a build meant
        # it. This only covers the case where nobody said anything at all.
        if package_name and not any(
            entry.get("package_name") == package_name for entry in required
        ):
            required.append({"package_name": package_name})

    if kiosk.get("kiosk_package"):
        _require(kiosk["kiosk_package"])

    # ⚠️ A multi-app kiosk needs **three** kinds of app present, and missing any of
    # them looks like a broken launcher rather than a missing install (W68):
    #   * the ATLAS launcher, or there is nothing to lock the device to;
    #   * every app on the home screen, or its tile is silently dropped;
    #   * nothing else — this list is also what lock task permits.
    multi_app = kiosk.get("multi_app_packages") or []
    if multi_app:
        _require(ATLAS_LAUNCHER_PACKAGE)
        for entry in multi_app:
            _require((entry or {}).get("package_name") or "")

    resolved: list[dict[str, Any]] = []

    for entry in required:
        package_name = entry.get("package_name")
        if not package_name:
            continue

        pinned = entry.get("artifact_sha256")
        if pinned:
            # A pin is **absolute**, and joined to the package it hangs off.
            #
            # Absolute because falling back to the floor would resolve to the
            # *newest* build — the exact opposite of what pinning an older version
            # asks for, and silently (R17). Pinning is how an operator holds a
            # fleet back; a pin that cannot be honoured has to fail loudly, not
            # quietly do the reverse.
            #
            # Joined because matching on the sha alone would happily return
            # another app's version and hand it to the agent under this
            # package_name (R18) — the device would install the wrong app and then
            # never converge, because the named one is still missing.
            version = session.scalar(
                select(AppPackageVersion)
                .join(AppPackageFile, AppPackageFile.version_id == AppPackageVersion.id)
                .join(AppPackage, AppPackage.id == AppPackageVersion.package_id)
                .where(
                    AppPackageFile.artifact_sha256 == pinned,
                    AppPackage.package_name == package_name,
                )
                .limit(1)
            )
            unavailable_reason = (
                f"pinned to artifact {pinned[:12]}…, which is not in the library "
                f"for {package_name}"
            )
        else:
            # ⚠️ Always None now (W139). An entry that names no build is
            # incomplete, not a request for whichever build is newest — see
            # `resolve_for_policy` for why "newest" was the dangerous reading.
            version = packages.resolve_for_policy(
                session, package_name, min_version_code=entry.get("min_version_code")
            )
            # ⚠️ Two different failures, kept apart. "Nothing uploaded" and "you
            # never picked a build" look identical from here and are fixed in
            # completely different places — one is an upload, the other is an
            # edit. Collapsing them is the R17/R18 mistake again: a reason that
            # covers every case tells an operator nothing.
            unavailable_reason = (
                "no version chosen — edit the policy and pick the build to install"
                if packages.has_builds(session, package_name)
                else "nothing uploaded for it"
            )

        if version is None:
            # The reason travels with the failure. Both the agent and the console
            # used to assume "nothing uploaded", which is now only one of three
            # ways this can happen and the least alarming of them.
            resolved.append(
                {
                    "package_name": package_name,
                    "available": False,
                    "reason": unavailable_reason,
                }
            )
            continue

        resolved.append(
            {
                "package_name": package_name,
                # Name and icon travel with the entry because the device cannot
                # look them up: `PackageManager` knows nothing about an app that is
                # not installed yet, which is precisely when the Apps screen needs
                # to show one (W57).
                "label": version.package.label if version.package else None,
                "icon_url": _icon_url(version),
                "available": True,
                "version_code": version.version_code,
                "version_name": version.version_name,
                "auto_update": entry.get("auto_update", True),
                "files": [
                    {
                        "role": file.role.value,
                        "file_name": file.file_name,
                        "split_name": file.split_name,
                        "sha256": file.artifact_sha256,
                        "size_bytes": file.artifact.size_bytes if file.artifact else None,
                        "url": f"/api/v1/device/artifacts/{file.artifact_sha256}",
                    }
                    for file in sorted(version.files, key=lambda f: (f.role.value, f.file_name))
                ],
            }
        )

    return sorted(resolved, key=lambda item: item["package_name"])


def _icon_url(version: AppPackageVersion | None) -> str | None:
    """Where the device can fetch this app's icon, or None when there is none.

    Reads `icon_media_type` — a small column on the package row — rather than the
    icon itself. Touching `icon_data` here would drag a blob into every check-in
    for every configured app, which is the regression the column was deferred to
    avoid (W53).
    """
    package = version.package if version is not None else None
    if package is None or not package.icon_media_type:
        return None
    return f"/api/v1/device/apps/{package.package_name}/icon"


#: The ATLAS launcher (W68). A separate APK, required only by a multi-app kiosk.
#: Must match `PolicyApplier.LAUNCHER_PACKAGE` in the agent — the two are one
#: contract expressed in two languages, and a typo here is a kiosk that never
#: locks.
ATLAS_LAUNCHER_PACKAGE = "com.taksolutions.atlaslauncher"


def resolve_store_apps(
    session: Session, required: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """The ATLAS store, resolved to concrete downloads the device can offer (W56).

    Store membership is **server-wide curation, not policy**: an operator moves a
    package into the store and every enrolled device may offer it. So this takes
    no policy values — unlike `resolve_required_apps`, there is nothing per-device
    to resolve against.

    ⚠️ An offer is not an order. These are apps a user *may* install; the agent
    must never install one on its own. The shape matches a required app so the
    agent can reuse one download path, and `required` is what keeps the two from
    colliding.

    Apps with nothing publishable are **omitted**, not reported unavailable — the
    opposite of the required path. A required app with no build is a broken policy
    an operator must see; a store app with no build is simply not on the shelf, and
    listing something a user cannot install would be worse than a shorter list.
    """
    already_required = {
        entry.get("package_name") for entry in (required or []) if entry.get("package_name")
    }

    offered: list[dict[str, Any]] = []
    for package in session.scalars(
        select(AppPackage).where(AppPackage.store_listed.is_(True))
    ):
        # Required wins. Offering a user the choice to install something policy is
        # already installing is a contradiction the console cannot resolve for them.
        if package.package_name in already_required:
            continue

        # ⚠️ **The newest build, and here the difference is deliberate** (W139).
        # A required app is installed *for* someone, so the policy has to say
        # which build and an unanswered question is a broken policy. A store app
        # is installed *by* someone from a shelf, and there is no policy to carry
        # the answer — so the shelf offers the current build, the same way any
        # app store does.
        version = packages.newest(session, package)
        if version is None:
            continue

        offered.append(
            {
                "package_name": package.package_name,
                "label": package.label,
                "icon_url": _icon_url(version),
                "available": True,
                "version_code": version.version_code,
                "version_name": version.version_name,
                "files": [
                    {
                        "role": file.role.value,
                        "file_name": file.file_name,
                        "split_name": file.split_name,
                        "sha256": file.artifact_sha256,
                        "size_bytes": file.artifact.size_bytes if file.artifact else None,
                        "url": f"/api/v1/device/artifacts/{file.artifact_sha256}",
                    }
                    for file in sorted(version.files, key=lambda f: (f.role.value, f.file_name))
                ],
            }
        )

    return sorted(offered, key=lambda item: item["package_name"])


def refresh(session: Session, device: Device) -> dict[str, Any]:
    """Recompute, store, and bump ``state_version`` if the device-facing state moved.

    Returns the stored payload rather than the resolver's own object: the payload
    carries the resolved ``apps``, which the resolver knows nothing about.
    """
    effective = compute(session, device)
    payload = effective.as_dict()
    payload["apps"] = resolve_required_apps(session, payload["values"])
    # The store is server-wide curation, so it takes no policy values — but it is
    # given the required list so an app that is both required and listed stays
    # required rather than being offered as an optional install as well (W56).
    payload["store"] = resolve_store_apps(session, payload["apps"])
    payload["files"] = files.resolve_files(session, payload["values"])
    payload["wallpaper"] = files.resolve_wallpaper(session, payload["values"])

    cache = session.get(EffectivePolicyCache, device.id)
    # A device that has never been computed starts from an empty desired state, not
    # from "unknown" — otherwise its first read would register as a change.
    previous = cache.payload if cache else {}
    previous_state = (
        previous.get("values", {}),
        previous.get("apps", []),
        previous.get("store", []),
        previous.get("files", {"required": [], "available": []}),
        previous.get("wallpaper", {}),
    )

    # Resolved apps and files are compared too, not just policy values. Uploading a
    # new build of a required app, or replacing a managed file, changes what the
    # device must do without changing a single word of policy — comparing values
    # alone would leave the fleet on the old version indefinitely.
    if previous_state != (
        payload["values"],
        payload["apps"],
        payload["store"],
        payload["files"],
        payload["wallpaper"],
    ):
        device.state_version += 1

    if cache is None:
        cache = EffectivePolicyCache(device_id=device.id, payload=payload, state_version=0)
        session.add(cache)
    cache.payload = payload
    cache.state_version = device.state_version
    cache.stale = False
    cache.computed_at = datetime.now(timezone.utc)

    session.flush()
    return payload


def get_effective(session: Session, device: Device) -> dict[str, Any]:
    """Cached effective policy, recomputing only when the row is missing or stale."""
    cache = session.get(EffectivePolicyCache, device.id)
    if cache is not None and not cache.stale:
        return cache.payload
    return refresh(session, device)


def preview(
    session: Session,
    device: Device,
    *,
    add: Sequence[AssignmentInput] = (),
    remove_assignment_ids: Iterable[uuid.UUID | str] = (),
) -> dict[str, Any]:
    """Resolve a hypothetical assignment set without writing anything.

    This is the guard rail in front of a change that could hit hundreds of devices:
    it answers "what actually moves?" before anything is persisted.
    """
    current = compute(session, device)

    removed = {str(i) for i in remove_assignment_ids}
    proposed_inputs = [
        a for a in gather_assignments(session, device) if a.assignment_id not in removed
    ]
    proposed_inputs.extend(add)
    proposed = resolve(str(device.id), proposed_inputs)

    # Compared as dicts, not as dataclasses: Conflict holds lists and dicts, so it is
    # not hashable and cannot go in a set.
    existing_conflicts = [c.as_dict() for c in current.conflicts]

    return {
        "device_id": str(device.id),
        "current": current.as_dict(),
        "proposed": proposed.as_dict(),
        "diff": diff_values(current.values, proposed.values),
        "new_conflicts": [
            c.as_dict() for c in proposed.conflicts if c.as_dict() not in existing_conflicts
        ],
    }


# --------------------------------------------------------------------------- #
# Invalidation
# --------------------------------------------------------------------------- #


def invalidate(session: Session, device_ids: Iterable[uuid.UUID]) -> None:
    """Mark cache rows stale so the next read recomputes, and wake those devices.

    Deliberately not a delete: the stored payload is the baseline ``refresh`` needs
    to tell a real change from a cosmetic one.

    The wake is queued here rather than in each caller so that no write path can
    invalidate without also telling the affected devices (F3). It fires after the
    transaction commits.
    """
    ids = set(device_ids)
    if not ids:
        return
    for cache in session.scalars(
        select(EffectivePolicyCache).where(EffectivePolicyCache.device_id.in_(ids))
    ):
        cache.stale = True
    session.flush()
    notifications.schedule_wake(session, ids)


def request_checkin(session: Session, device_ids: set[uuid.UUID]) -> set[uuid.UUID]:
    """Make these devices check in now, without any policy having changed.

    Marks their cache stale (so the long-poll's pending check has a reason to
    release) and rings the doorbell. The ensuing recompute finds nothing moved
    and does not bump ``state_version``, so the check-in is a harmless no-op that
    just refreshes ``last_checkin_at``. Returns the subset currently parked.
    """
    invalidate(session, device_ids)
    return notifications.parked(set(device_ids))


def invalidate_all(session: Session) -> None:
    """Mark every device's cache stale.

    Used when the app catalog changes. Working out exactly which devices reference a
    package would mean re-resolving every stacked policy; at this fleet size a blanket
    flag is cheaper and cannot miss one. It costs nothing spurious either — the
    recompute only bumps ``state_version`` for devices whose resolved state actually
    moved.
    """
    caches = list(session.scalars(select(EffectivePolicyCache)))
    for cache in caches:
        cache.stale = True
    session.flush()
    # Wakes the whole fleet. At this size that is a burst of small check-ins, and
    # only devices whose resolved state actually moved receive a bundle.
    notifications.schedule_wake(session, {cache.device_id for cache in caches})


def devices_targeted_by(session: Session, assignment: Assignment) -> set[uuid.UUID]:
    """Devices an assignment reaches, resolved through group membership."""
    if assignment.scope is AssignmentScope.DEVICE:
        return {assignment.device_id} if assignment.device_id else set()

    if assignment.scope is AssignmentScope.GROUP:
        stmt = select(Device).where(Device.groups.any(id=assignment.group_id))
    return {d.id for d in session.scalars(stmt)}


def devices_targeted_by_profile_assignment(
    session: Session, pa: ProfileAssignment
) -> set[uuid.UUID]:
    if pa.scope is AssignmentScope.DEVICE:
        return {pa.device_id} if pa.device_id else set()
    if pa.scope is AssignmentScope.GROUP:
        stmt = select(Device).where(Device.groups.any(id=pa.group_id))
    return {d.id for d in session.scalars(stmt)}


def devices_affected_by_profile(session: Session, profile_id: uuid.UUID) -> set[uuid.UUID]:
    """Every device reached by any assignment of this profile."""
    affected: set[uuid.UUID] = set()
    for pa in session.scalars(
        select(ProfileAssignment).where(ProfileAssignment.profile_id == profile_id)
    ):
        affected |= devices_targeted_by_profile_assignment(session, pa)
    return affected


def devices_affected_by_policy(session: Session, policy_id: uuid.UUID) -> set[uuid.UUID]:
    """Every device reached by any assignment of this policy — directly, or (for a
    profile section) through an assignment of its profile."""
    assignments = session.scalars(
        select(Assignment).where(Assignment.policy_id == policy_id)
    ).all()
    affected: set[uuid.UUID] = set()
    for assignment in assignments:
        affected |= devices_targeted_by(session, assignment)

    policy = session.get(Policy, policy_id)
    if policy is not None and policy.profile_id is not None:
        affected |= devices_affected_by_profile(session, policy.profile_id)
    return affected


def invalidate_for_assignment(session: Session, assignment: Assignment) -> None:
    invalidate(session, devices_targeted_by(session, assignment))


def invalidate_for_policy(session: Session, policy_id: uuid.UUID) -> None:
    invalidate(session, devices_affected_by_policy(session, policy_id))


def invalidate_for_profile(session: Session, profile_id: uuid.UUID) -> None:
    invalidate(session, devices_affected_by_profile(session, profile_id))
