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

import logging
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
    PolicyProfile,
    PolicyVersion,
    ProfileAssignment,
    Storefront,
)
from app.services import breach, deployment, files, notifications, packages
from app.services import profiles
from app.services import locations as location_service
from app.services import knox_license
from app.policies.registry import PolicyTypeError, registry
from app.policies.specs.kiosk import ATLAS_CONSOLE_PACKAGE
from app.policies.resolver import (
    AssignmentInput,
    EffectivePolicy,
    PolicySnapshot,
    diff_values,
    resolve,
)


log = logging.getLogger(__name__)

#: The policy type that only breach mode may deliver. Named here rather than
#: imported from `app.services.breach`, which imports this module back.
BREACH_TYPE = "BREACH"


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


def gather_assignments(
    session: Session, device: Device, now: datetime | None = None
) -> list[AssignmentInput]:
    """Every enabled assignment reaching this device, directly or via a group.

    ``now`` decides which scheduled policies count as in force. Callers that
    also record a cache horizon pass the same instant to both, so a policy
    cannot fall between them — see :func:`refresh`.
    """
    now = now if now is not None else datetime.now(timezone.utc)

    if breach.is_engaged(device):
        # ⚠️ A device in breach receives the breach profile and nothing else
        # (W193). Asked here, before anything is gathered, because "replaced"
        # rather than "stacked on top of" is what makes the mode work at all:
        # the agent refuses to block a package that is also required, reporting
        # it as contradictory policy, so a breach stacked over the ordinary
        # policies would report every app instead of removing it.
        return _breach_assignments(session)

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
        if not deployment.is_live(policy, now):
            # Built, targeted, and deliberately not in force yet (W191). Asked
            # here rather than filtered in the query above so that "live" has
            # exactly one definition — see `app.services.deployment`.
            continue
        if policy.policy_type == BREACH_TYPE:
            # ⚠️ **The safety net, and it should never fire** (W193). Breach
            # mode is not offered in either policy creator, so there is no way
            # through the console to build one — but the API takes a policy_type
            # by name, and a `BREACH` policy assigned to a group would empty
            # those directories on every device in it with no breach engaged,
            # no confirmation and no button pressed.
            #
            # Refusing at the resolver rather than at the API is deliberate:
            # this is the one place every route, import and restore passes
            # through, so it cannot be got around by finding another door.
            log.warning(
                "ignoring %r: a BREACH policy reaches devices only through "
                "breach mode, never by assignment",
                policy.name,
            )
            continue
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

    inputs.extend(_gather_profile_assignments(session, device, group_ids, now))
    return inputs


def _breach_assignments(session: Session) -> list[AssignmentInput]:
    """Every section of the reserved breach profile, as the device's whole policy.

    ⚠️ **An unconfigured breach profile yields nothing, and that is deliberate
    rather than an oversight to fix later.** It cannot be quietly substituted
    with something safer: the only alternatives are to fall back to the device's
    ordinary policies, which means the operator pressed the button and nothing
    happened, or to invent a policy nobody wrote. Both are worse than an empty
    answer, and the button refuses to engage without a configured profile
    precisely so this is never reached.

    Rank is nominal. Nothing else is in the resolve, so there is nothing to
    outrank — the sections stack only against each other, exactly as they do for
    any profile assigned normally.
    """
    reserved = breach.profile(session)
    if reserved is None:
        return []

    inputs: list[AssignmentInput] = []
    for section in reserved.sections:
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
                assignment_id=f"breach:{section.id}",
                scope=AssignmentScope.DEVICE.value,
                rank=0,
                policy=_snapshot(section, version),
            )
        )
    return inputs


def _gather_profile_assignments(
    session: Session,
    device: Device,
    group_ids: list[uuid.UUID],
    now: datetime,
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
        if not deployment.is_live(profile, now):
            continue  # pending deployment, or scheduled for later (W191)
        # ⚠️ The profile decides, never the section. A section's own pending
        # columns are left unset by every path that creates one, and consulting
        # them anyway would let a single tab of a live profile sit out — which
        # looks exactly like a merge that lost a policy.
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


def compute(
    session: Session, device: Device, now: datetime | None = None
) -> EffectivePolicy:
    """Resolve without touching the cache."""
    return resolve(str(device.id), gather_assignments(session, device, now))


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
    # ⚠️ All three fields, not just `required_apps` (W141). ATAK Core and the
    # plugins are ordinary required apps sorted into their own section, and a
    # resolver that read only this field would install everything except ATAK.
    required = _everything_required(values)

    kiosk = values.get("KIOSK") or {}

    def _require(package_name: str, artifact_sha256: str | None = None) -> None:
        """Add a kiosk app to the required set, naming the build to install.

        ⚠️ **The build is not optional, and the comment that used to sit here
        said the opposite** (W196). It read "no version constraint … this only
        covers the case where nobody said anything at all", which described the
        behaviour W139 deleted: an unpinned entry used to resolve to the newest
        published build. Since W139 it resolves to *nothing*, so every kiosk app
        auto-required here has silently failed to install ever since, and the
        device reported the kiosk having nothing to lock to.

        ⚠️ An explicit `required_apps` entry for the same app still wins,
        which is the one part of that comment that was true: an operator who
        pinned a build meant it.
        """
        if not package_name:
            return
        if package_name == ATLAS_CONSOLE_PACKAGE:
            # ⚠️ **The agent is never a required app** (W197). It is the Device
            # Owner: installed by definition, and its builds come down the
            # agent-update channel, which stages them. Requiring it here would
            # put a second system in charge of the same APK — and since W196 an
            # entry naming no build reports "no version chosen", so an operator
            # who placed the console tile saw their own console listed as a
            # broken required app.
            return
        if any(entry.get("package_name") == package_name for entry in required):
            return
        entry: dict[str, Any] = {"package_name": package_name}
        if artifact_sha256:
            entry["artifact_sha256"] = artifact_sha256
        required.append(entry)

    if kiosk.get("kiosk_package"):
        _require(kiosk["kiosk_package"], kiosk.get("kiosk_artifact_sha256"))

    # ⚠️ A multi-app kiosk needs **three** kinds of app present, and missing any of
    # them looks like a broken launcher rather than a missing install (W68):
    #   * the ATLAS launcher, or there is nothing to lock the device to;
    #   * every app on the home screen, or its tile is silently dropped;
    #   * nothing else — this list is also what lock task permits.
    multi_app = kiosk.get("multi_app_packages") or []
    if multi_app:
        # ⚠️ **The launcher is the one app ATLAS still chooses a build for**,
        # and it is a deliberate exception to W139 rather than an oversight.
        # `dist/atlas-launcher.apk` is shipped by ATLAS and loaded by
        # `seed-packages`: there is no "which build did they mean" to get wrong.
        # Asking an operator to pick a build for ATLAS's own launcher is a step
        # they cannot reason about and will forget, and forgetting it means a
        # multi-app kiosk that silently does not engage. See
        # `packages.newest_base_sha` for the full argument.
        _require(
            ATLAS_LAUNCHER_PACKAGE,
            packages.newest_base_sha(session, ATLAS_LAUNCHER_PACKAGE),
        )
        for tile in multi_app:
            tile = tile or {}
            _require(tile.get("package_name") or "", tile.get("artifact_sha256"))

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
                # ⚠️ Carried on the *available* entries only. The device records
                # it when it installs, and an entry with no build is an entry
                # nothing will install — putting the flag on the unavailable
                # branch would suggest the agent might act on it there.
                "remove_when_no_longer_required": entry.get(
                    "remove_when_no_longer_required", False
                ),
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


def _everything_required(values: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Required apps, ATAK Core and the plugins, as one list (W141).

    ⚠️ **ATAK and its plugins were always ordinary required apps.** They were
    split into their own section so a version mismatch could be talked about,
    not because they install differently — so they are folded back together
    here and the agent is told nothing new.

    Order is deliberate: ATAK Core first, then its plugins, then everything
    else. Nothing downstream depends on it, but a desired state read by a human
    at three in the morning should put the thing everything else is built
    against at the top.
    """
    catalog = (values or {}).get("APP_CATALOG", {})
    core = catalog.get("atak_core")
    return (
        ([core] if core else [])
        + (catalog.get("atak_plugins") or [])
        + (catalog.get("required_apps") or [])
    )


def resolve_store_apps(
    session: Session,
    required: list[dict[str, Any]] | None = None,
    values: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """The ATLAS store, resolved to concrete downloads the device can offer (W56).

    ⚠️ **Policy decides the shelf now** (W140). This used to read
    `AppPackage.store_listed` and take no policy values at all, because store
    membership was server-wide curation and every enrolled device saw the same
    apps. A policy names a `Storefront` instead, so two devices can be offered
    different shelves — and a device whose policies name none is offered
    nothing, which is the honest reading of "no store was assigned".

    ⚠️ An offer is not an order. These are apps a user *may* install; the agent
    must never install one on its own. The shape matches a required app so the
    agent can reuse one download path, and `required` is what keeps the two from
    colliding.

    Apps whose build has left the library are **omitted**, not reported
    unavailable — the opposite of the required path. A required app with no build
    is a broken policy an operator must see; a shelf entry that cannot be
    installed is simply not on the shelf, and listing something a user cannot
    install would be worse than a shorter list.
    """
    storefront_id = (values or {}).get("APP_CATALOG", {}).get("storefront_id")
    if not storefront_id:
        return []
    try:
        storefront = session.get(Storefront, uuid.UUID(str(storefront_id)))
    except ValueError:
        storefront = None
    if storefront is None:
        # A storefront deleted out from under a policy. Empty rather than an
        # error: the device loses an offer, not a configuration, and nothing it
        # has already installed is touched.
        return []

    already_required = {
        entry.get("package_name") for entry in (required or []) if entry.get("package_name")
    }

    offered: list[dict[str, Any]] = []
    for item in storefront.items:
        package = item.package
        # Required wins. Offering a user the choice to install something policy is
        # already installing is a contradiction the console cannot resolve for them.
        if package is None or package.package_name in already_required:
            continue

        # ⚠️ **The build the storefront names**, not the newest. The comment that
        # stood here said a shelf should offer the current build because "there
        # is no policy to carry the answer" — true when the shelf was
        # server-wide, and obsolete the moment a policy started naming it.
        version = item.version
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


#: What the provenance row says when a value came from Admin rather than a policy.
_ADMIN_DEFAULT_SOURCE = "Admin \u2192 Location"


def apply_location_default(session: Session, payload: dict[str, Any]) -> None:
    """Fill in the reporting interval when no policy set one. Mutates ``payload``.

    ⚠️ **Absent and 0 are different answers, and the whole feature is that
    distinction.** A device no tracking policy reaches has *no opinion* about its
    interval, and gets the fleet default — that is what "enrolled devices report
    by default" means. A device whose policy says 0 has been deliberately switched
    off and must stay off: overwriting that with the default would make it
    impossible to exempt a device from tracking at all, which is the one thing an
    operator needs when a device goes somewhere that should not be logged.

    So this only ever writes into a gap. Any resolved value, 0 included, is left
    exactly as the resolver produced it.

    Applied to the payload rather than declared as the spec's ``default``, because
    a spec default is baked into a policy version the moment it is published —
    changing the admin setting afterwards would move new policies and leave old
    ones on the old number, with nothing on the page to explain the difference.
    Here it resolves at read time, so one setting moves the whole fleet at its next
    check-in, and already-deployed agents need no change: they receive an ordinary
    interval and cannot tell it came from Admin.
    """
    values = payload.setdefault("values", {})
    section = values.get("TRACKING_FENCING") or {}
    if section.get(location_service.INTERVAL_FIELD) is not None:
        return

    minutes = location_service.default_interval_minutes(session)
    if minutes <= 0:
        # An operator who set the default to 0 asked for no default reporting.
        # Leaving the field absent is not the same as writing 0: absent is already
        # what the agent reads as off, and it keeps the console's Effective policy
        # table from showing a row that neither a policy nor a setting asserts.
        return

    section = dict(section)
    section[location_service.INTERVAL_FIELD] = minutes
    values["TRACKING_FENCING"] = section

    # Explained on the device page like anything else. A number with no source in
    # the provenance table reads as a bug in the resolver.
    provenance = payload.setdefault("provenance", {})
    entry = dict(provenance.get("TRACKING_FENCING") or {})
    entry[location_service.INTERVAL_FIELD] = {
        "value": minutes,
        "strategy": "admin default",
        "source": {"policy_name": _ADMIN_DEFAULT_SOURCE},
        "contributors": [],
        "overridden": [],
        "conflict": False,
    }
    provenance["TRACKING_FENCING"] = entry


def apply_knox_license(session: Session, payload: dict[str, Any]) -> None:
    """Record *that* a Knox licence is configured. Mutates ``payload``.

    ⚠️ **The key itself is deliberately absent**, and this is the one place
    that decision is enforced. This payload is cached as plain JSON in
    `effective_policy_cache`, one row per device, and rendered on the Effective
    policy page. The key is sealed in `app_setting` precisely so a database copy
    does not carry it; writing it here would put a plaintext copy of it in that
    same database for every enrolled tablet. `knox_license.bundle_block` puts the
    real key into the outgoing signed bundle instead, where it is assembled per
    response and never stored.

    What *is* here is a fingerprint, and it has to be: `refresh` decides whether
    to bump ``state_version`` by comparing this payload against the cached one.
    A licence key changed in Admin moves nothing else in the document, so without
    a token that follows it, the new key would reach only those devices whose
    state happened to change for some unrelated reason.

    Not a spec default, for the same reason as `apply_location_default`: resolved
    at read time, so one setting moves the whole fleet at its next check-in.
    """
    payload[knox_license.PAYLOAD_KEY] = knox_license.marker(session)


def refresh(session: Session, device: Device) -> dict[str, Any]:
    """Recompute, store, and bump ``state_version`` if the device-facing state moved.

    Returns the stored payload rather than the resolver's own object: the payload
    carries the resolved ``apps``, which the resolver knows nothing about.
    """
    # ⚠️ **One instant, used for both the resolve and the horizon.** Reading
    # the clock twice opens a window — microseconds wide, and permanent — in
    # which a policy is "not yet live" to the resolver and "already past" to the
    # horizon query, so it is left out of the payload *and* out of the reason to
    # recompute. The cache would then serve a policy-free answer until something
    # unrelated invalidated it.
    now = datetime.now(timezone.utc)
    effective = compute(session, device, now)
    payload = effective.as_dict()
    apply_location_default(session, payload)
    apply_knox_license(session, payload)
    payload["apps"] = resolve_required_apps(session, payload["values"])
    # Given the required list so an app that is both required and on the shelf
    # stays required rather than being offered as an optional install as well
    # (W56), and the values because the shelf itself is now policy (W140).
    payload["store"] = resolve_store_apps(session, payload["apps"], payload["values"])
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
        # ⚠️ The Knox licence marker, and it has to be compared like the rest.
        # A licence key changed in Admin moves nothing else in this document, so
        # leaving it out would mean the new key reached only the devices whose
        # state happened to change for some unrelated reason. `.get` with the
        # unset marker as the default, not `{}`: a cache row written before this
        # feature existed must not read as "a key was configured and has now
        # gone", which would bump every device in the fleet on the deploy.
        previous.get(knox_license.PAYLOAD_KEY, knox_license.unset_marker()),
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
        payload[knox_license.PAYLOAD_KEY],
    ):
        device.state_version += 1

    if cache is None:
        cache = EffectivePolicyCache(device_id=device.id, payload=payload, state_version=0)
        session.add(cache)
    cache.payload = payload
    cache.state_version = device.state_version
    cache.stale = False
    cache.computed_at = now
    # When this answer stops being true by the calendar alone (W191). NULL means
    # nothing is scheduled, so only a write can change what this device should do.
    cache.next_transition_at = deployment.next_transition(session, now=now)

    session.flush()
    return payload


def get_effective(session: Session, device: Device) -> dict[str, Any]:
    """Cached effective policy, recomputing when it is missing, stale, or expired.

    ⚠️ **Expiry is the third condition and it is not like the other two.**
    Missing and stale are both consequences of a write. A scheduled deployment is
    not a write — the row sat untouched while a clock passed a date — so without
    the horizon this returns a payload that was correct when it was computed and
    is now wrong, forever, for a device that never asks a different question.
    """
    cache = session.get(EffectivePolicyCache, device.id)
    if cache is not None and not cache.stale and not expired(cache):
        return cache.payload
    return refresh(session, device)


def expired(cache: EffectivePolicyCache, now: datetime | None = None) -> bool:
    """Has a scheduled deployment come due since this payload was computed?"""
    if cache.next_transition_at is None:
        return False
    return cache.next_transition_at <= (now or datetime.now(timezone.utc))


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

    # Both sides carry the fleet default, so that "current" here means the same
    # thing as the device's own effective policy page. The diff is computed from
    # the resolver's values instead, which is what keeps the default out of it: it
    # is identical on both sides and is not what the operator is being asked to
    # approve.
    current_payload = current.as_dict()
    proposed_payload = proposed.as_dict()
    apply_location_default(session, current_payload)
    apply_location_default(session, proposed_payload)

    return {
        "device_id": str(device.id),
        "current": current_payload,
        "proposed": proposed_payload,
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
        affected |= _devices_in_breach_if_reserved(session, policy.profile_id)
    return affected


def _devices_in_breach_if_reserved(
    session: Session, profile_id: uuid.UUID
) -> set[uuid.UUID]:
    """Devices reached by a change to the **breach** profile (W193).

    ⚠️ **Found by a mutation sweep, and it was a real hole.** The breach profile
    has no assignments — it reaches a device through that device's breach flag,
    which is the entire design — so every "who does this policy affect" answer
    built from assignment rows came back empty. Editing the breach passcode, or
    archiving a section, changed what a breached device *should* have and told
    nobody: the resolver was right and was never asked again.

    The device page and the check-in both read the cache, so the symptom is a
    tablet in breach quietly keeping the previous breach policy for ever.
    """
    reserved = session.get(PolicyProfile, profile_id)
    if reserved is None or reserved.name not in profiles.RESERVED_NAMES:
        return set()
    return set(
        session.scalars(
            select(Device.id).where(Device.breach_engaged_at.is_not(None))
        )
    )


def invalidate_for_assignment(session: Session, assignment: Assignment) -> None:
    invalidate(session, devices_targeted_by(session, assignment))


def invalidate_for_policy(session: Session, policy_id: uuid.UUID) -> None:
    invalidate(session, devices_affected_by_policy(session, policy_id))


def invalidate_for_profile(session: Session, profile_id: uuid.UUID) -> None:
    invalidate(session, devices_affected_by_profile(session, profile_id))
