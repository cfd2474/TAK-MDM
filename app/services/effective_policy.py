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
    AppPackageFile,
    Assignment,
    AssignmentScope,
    Device,
    EffectivePolicyCache,
    Policy,
    PolicyVersion,
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
    """Every enabled assignment reaching this device, via device, group, or tag."""
    targets = [Assignment.device_id == device.id]
    group_ids = [g.id for g in device.groups]
    tag_ids = [t.id for t in device.tags]
    if group_ids:
        targets.append(Assignment.group_id.in_(group_ids))
    if tag_ids:
        targets.append(Assignment.tag_id.in_(tag_ids))

    rows = session.scalars(
        select(Assignment).where(Assignment.enabled.is_(True), or_(*targets))
    ).all()

    inputs: list[AssignmentInput] = []
    for assignment in rows:
        policy = assignment.policy
        if policy.archived_at is not None:
            continue  # archived policies stop applying without being deleted
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
    """
    catalog = values.get("APP_CATALOG") or {}
    required = catalog.get("required_apps") or []
    resolved: list[dict[str, Any]] = []

    for entry in required:
        package_name = entry.get("package_name")
        if not package_name:
            continue

        version = None
        pinned = entry.get("artifact_sha256")
        if pinned:
            # An explicitly pinned artifact wins over "latest satisfying the floor".
            pinned_file = session.scalar(
                select(AppPackageFile).where(AppPackageFile.artifact_sha256 == pinned).limit(1)
            )
            version = pinned_file.version if pinned_file else None
        if version is None:
            version = packages.resolve_for_policy(
                session, package_name, min_version_code=entry.get("min_version_code")
            )

        if version is None:
            resolved.append({"package_name": package_name, "available": False})
            continue

        resolved.append(
            {
                "package_name": package_name,
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


def refresh(session: Session, device: Device) -> dict[str, Any]:
    """Recompute, store, and bump ``state_version`` if the device-facing state moved.

    Returns the stored payload rather than the resolver's own object: the payload
    carries the resolved ``apps``, which the resolver knows nothing about.
    """
    effective = compute(session, device)
    payload = effective.as_dict()
    payload["apps"] = resolve_required_apps(session, payload["values"])
    payload["files"] = files.resolve_files(session, payload["values"])

    cache = session.get(EffectivePolicyCache, device.id)
    # A device that has never been computed starts from an empty desired state, not
    # from "unknown" — otherwise its first read would register as a change.
    previous = cache.payload if cache else {}
    previous_state = (
        previous.get("values", {}),
        previous.get("apps", []),
        previous.get("files", {"required": [], "available": []}),
    )

    # Resolved apps and files are compared too, not just policy values. Uploading a
    # new build of a required app, or replacing a managed file, changes what the
    # device must do without changing a single word of policy — comparing values
    # alone would leave the fleet on the old version indefinitely.
    if previous_state != (payload["values"], payload["apps"], payload["files"]):
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
    """Devices an assignment reaches, resolved through group/tag membership."""
    if assignment.scope is AssignmentScope.DEVICE:
        return {assignment.device_id} if assignment.device_id else set()

    if assignment.scope is AssignmentScope.GROUP:
        stmt = select(Device).where(Device.groups.any(id=assignment.group_id))
    else:
        stmt = select(Device).where(Device.tags.any(id=assignment.tag_id))
    return {d.id for d in session.scalars(stmt)}


def devices_affected_by_policy(session: Session, policy_id: uuid.UUID) -> set[uuid.UUID]:
    """Every device reached by any assignment of this policy."""
    assignments = session.scalars(
        select(Assignment).where(Assignment.policy_id == policy_id)
    ).all()
    affected: set[uuid.UUID] = set()
    for assignment in assignments:
        affected |= devices_targeted_by(session, assignment)
    return affected


def invalidate_for_assignment(session: Session, assignment: Assignment) -> None:
    invalidate(session, devices_targeted_by(session, assignment))


def invalidate_for_policy(session: Session, policy_id: uuid.UUID) -> None:
    invalidate(session, devices_affected_by_policy(session, policy_id))
