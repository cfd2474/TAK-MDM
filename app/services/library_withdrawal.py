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

"""What a library deletion does to the policies that name it (W367).

Operator, 2026-10-10: *"when app is removed from library and exists in policy,
remove policy line item for associated removed app"*, and for one build: *"if a
policy enforces that specific version of the app, have it revert to the newest
remaining release."*

- **Deleting an app** removes it from every policy field that names a library
  build: required apps, ATAK Core and plugins, app configurations, multi-app
  kiosk tiles, plugin auto-load and plugin settings.
- **Deleting one build** re-pins every policy that pinned it to the newest
  build left (for a plugin, the newest left for the same ATAK version). The
  last build going is the app leaving the library.

Each changed policy gets a new version through the same path a save takes, so
every check a save runs still runs. If any policy would be refused, the whole
deletion is refused and nothing changes.

⚠️ **This deliberately reverses W192's stance.** `WithdrawnAppPlan.kt` refused
to let a library deletion reach devices: an entry with no build still counted
as required. The operator chose otherwise (2026-10-10): the entry now leaves the
policy, and a device with "Uninstall if withdrawn" recorded uninstalls the app.
The agent is unchanged; the safety is the confirmation, which names the
policies and the uninstall before anything happens.

⚠️ **Left alone on purpose:** blocked, allowed and background package lists,
data-usage app rules, and compliance `suspend_apps`. They name packages that
need not be in the library (W323 keeps a suspended app that left it).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts.storage import ArtifactStorage
from app.db.models import (
    AppPackage,
    AppPackageVersion,
    PartRole,
    Policy,
    PolicyProfile,
    PolicyVersion,
)
from app.policies.registry import PolicyTypeError, registry
from app.services import atak_compat, reserved_packages
from app.services import packages as package_service
from app.services import profiles as profile_service

APP_CATALOG = "APP_CATALOG"
KIOSK = "KIOSK"
ATAK_CONFIG = "ATAK_CONFIG"

#: Fields holding rows of `{package_name, artifact_sha256, ...}`: a deleted app's
#: row goes, and a deleted build's pin moves.
_PINNED_ROWS = {
    APP_CATALOG: ("required_apps", "atak_plugins"),
    KIOSK: ("multi_app_packages",),
}
#: Fields holding rows keyed by package with no build: a deleted app's row goes.
_KEYED_ROWS = {
    APP_CATALOG: ("app_configs",),
    ATAK_CONFIG: ("plugin_prefs",),
}
#: Plain package-name lists that need the library: a deleted app's name goes.
_NAME_LISTS = {
    ATAK_CONFIG: ("auto_load_plugins",),
}


class WithdrawalError(Exception):
    """A policy cannot drop or re-pin the app; nothing was changed."""


# --------------------------------------------------------------------------- #
# Pure edits of one stored spec
# --------------------------------------------------------------------------- #


def strip(policy_type: str, spec: dict[str, Any], package: str) -> dict[str, Any]:
    """`spec` with `package` taken out of every field that names a library build.

    Raises WithdrawalError where taking it out would change what the policy *is*
    rather than what it lists: the app a single-app kiosk is locked to, or the
    last app on a multi-app kiosk's home screen. Either would quietly unlock
    the kiosk on every device.
    """
    out = copy.deepcopy(spec)
    for field in _PINNED_ROWS.get(policy_type, ()) + _KEYED_ROWS.get(policy_type, ()):
        rows = out.get(field)
        if not rows:
            continue
        kept = [r for r in rows if r.get("package_name") != package]
        if field == "multi_app_packages" and len(kept) != len(rows):
            if not [r for r in kept if not reserved_packages.is_reserved(r.get("package_name"))]:
                raise WithdrawalError(
                    f"it is the last app on the multi-app kiosk's home screen, and "
                    f"removing it would take the kiosk off every device. Add "
                    f"another app to the kiosk, or change the kiosk, first"
                )
        _put_list(out, field, kept)
    for field in _NAME_LISTS.get(policy_type, ()):
        names = out.get(field)
        if names:
            _put_list(out, field, [n for n in names if n != package])
    if policy_type == APP_CATALOG and (out.get("atak_core") or {}).get("package_name") == package:
        out.pop("atak_core")
    if policy_type == KIOSK and out.get("kiosk_package") == package:
        raise WithdrawalError(
            "it is the app the single-app kiosk is locked to, and removing it "
            "would take the kiosk off every device. Choose another kiosk app first"
        )
    return out


def repin(
    policy_type: str, spec: dict[str, Any], package: str, old_sha: str, new_sha: str
) -> dict[str, Any]:
    """`spec` with every pin of `package` on `old_sha` moved to `new_sha`."""
    out = copy.deepcopy(spec)
    for field in _PINNED_ROWS.get(policy_type, ()):
        for row in out.get(field) or []:
            if row.get("package_name") == package and row.get("artifact_sha256") == old_sha:
                row["artifact_sha256"] = new_sha
    core = out.get("atak_core") if policy_type == APP_CATALOG else None
    if core and core.get("package_name") == package and core.get("artifact_sha256") == old_sha:
        core["artifact_sha256"] = new_sha
    if (
        policy_type == KIOSK
        and out.get("kiosk_package") == package
        and out.get("kiosk_artifact_sha256") == old_sha
    ):
        out["kiosk_artifact_sha256"] = new_sha
    return out


def _put_list(spec: dict[str, Any], field: str, items: list) -> None:
    # An emptied list leaves the field absent, which is what saving the form
    # without those rows stores.
    if items:
        spec[field] = items
    else:
        spec.pop(field, None)


# --------------------------------------------------------------------------- #
# Which build replaces a deleted one
# --------------------------------------------------------------------------- #


def base_sha(version: AppPackageVersion) -> str | None:
    """The base APK's digest: what a policy pin names."""
    for f in version.files:
        if f.role is PartRole.BASE:
            return f.artifact_sha256
    return None


def replacement(version: AppPackageVersion) -> AppPackageVersion | None:
    """The newest other build of the same app, or None if it is the last.

    ⚠️ A plugin keeps its ATAK version when it can. ATAK refuses a plugin built
    for a newer ATAK, so "newest" alone would move a 5.6 policy onto a 5.8 build
    that never loads. Only when no build for that ATAK is left does it fall back
    to the newest of any, which the editor then flags as a mismatch.
    """
    others = [
        v for v in version.package.versions if v is not version and base_sha(v) is not None
    ]
    if not others:
        return None
    target = atak_compat.plugin_target(version.plugin_api)
    same_line = [v for v in others if target and atak_compat.plugin_target(v.plugin_api) == target]
    return max(same_line or others, key=lambda v: v.version_code)


# --------------------------------------------------------------------------- #
# Policies, and who they belong to
# --------------------------------------------------------------------------- #

_TYPES = (APP_CATALOG, KIOSK, ATAK_CONFIG)


@dataclass(frozen=True)
class Use:
    """One policy a deletion would change, named the way the console names it."""

    policy: Policy
    label: str


def _label(session: Session, policy: Policy) -> str:
    if policy.profile_id is None:
        return policy.name
    profile = session.get(PolicyProfile, policy.profile_id)
    return profile.name if profile is not None else policy.name


def _candidates(session: Session) -> Iterable[tuple[Policy, dict[str, Any]]]:
    for policy in session.scalars(select(Policy).where(Policy.policy_type.in_(_TYPES))):
        latest = policy.latest_version
        if latest is not None and latest.spec:
            yield policy, latest.spec


def _changes(policy_type: str, spec: dict, edit) -> bool:
    try:
        return edit(policy_type, spec) != spec
    except WithdrawalError:
        return True  # it names the app, and would be refused


def naming(session: Session, package: str) -> list[Use]:
    """Every policy whose latest version names `package` where a deletion reaches."""
    return _uses(session, lambda t, s: strip(t, s, package))


def pinning(session: Session, package: str, sha: str) -> list[Use]:
    """Every policy whose latest version pins `package` to the build `sha`."""
    return _uses(session, lambda t, s: repin(t, s, package, sha, "0" * 64))


def _uses(session: Session, edit) -> list[Use]:
    found = [
        Use(policy, _label(session, policy))
        for policy, spec in _candidates(session)
        if _changes(policy.policy_type, spec, edit)
    ]
    return sorted(found, key=lambda u: u.label.lower())


def mentions(policy_type: str, spec: dict[str, Any]) -> set[tuple[str, str | None]]:
    """Every (package, pinned build or None) this spec names where a deletion reaches."""
    found: set[tuple[str, str | None]] = set()
    for field in _PINNED_ROWS.get(policy_type, ()):
        for row in spec.get(field) or []:
            found.add((row.get("package_name"), row.get("artifact_sha256")))
    for field in _KEYED_ROWS.get(policy_type, ()):
        for row in spec.get(field) or []:
            found.add((row.get("package_name"), None))
    for field in _NAME_LISTS.get(policy_type, ()):
        for name in spec.get(field) or []:
            found.add((name, None))
    core = spec.get("atak_core") if policy_type == APP_CATALOG else None
    if core:
        found.add((core.get("package_name"), core.get("artifact_sha256")))
    if policy_type == KIOSK and spec.get("kiosk_package"):
        found.add((spec["kiosk_package"], spec.get("kiosk_artifact_sha256")))
    return found


@dataclass
class Index:
    """For the Apps page: which policies each app, and each build, reaches."""

    by_package: dict[str, list[str]]
    by_build: dict[tuple[str, str], list[str]]


def index(session: Session) -> Index:
    """One pass over every policy, for every delete confirmation on a page."""
    by_package: dict[str, set[str]] = {}
    by_build: dict[tuple[str, str], set[str]] = {}
    for policy, spec in _candidates(session):
        label = _label(session, policy)
        for package, sha in mentions(policy.policy_type, spec):
            by_package.setdefault(package, set()).add(label)
            if sha:
                by_build.setdefault((package, sha), set()).add(label)
    order = lambda names: sorted(names, key=str.lower)  # noqa: E731
    return Index(
        {k: order(v) for k, v in by_package.items()},
        {k: order(v) for k, v in by_build.items()},
    )


def labels(uses: list[Use]) -> list[str]:
    """Distinct names for a message: a policy's sections share its name."""
    return sorted({u.label for u in uses}, key=str.lower)


# --------------------------------------------------------------------------- #
# Publishing
# --------------------------------------------------------------------------- #


def _publish(session: Session, use: Use, spec: dict[str, Any], by: str | None) -> None:
    """A new version of `use.policy` holding `spec`, the way a save stores it.

    ⚠️ Effective policy is not invalidated here, policy by policy: a deletion
    changes the library itself, so every caller invalidates everything once it
    is done (`eff.invalidate_all`), as the package delete always has.
    """
    policy = use.policy
    try:
        if policy.profile_id is not None:
            profile = session.get(PolicyProfile, policy.profile_id)
            if spec:
                profile_service.upsert_section(
                    session, profile, policy.profile_section, spec, published_by=by
                )
            else:
                profile_service.remove_section(session, profile, policy.profile_section)
            return
        validated = registry.validate_spec(policy.policy_type, spec)
    except (profile_service.ProfileError, PolicyTypeError) as exc:
        raise WithdrawalError(f"{use.label} would be refused: {exc}") from exc
    latest = policy.latest_version
    session.add(
        PolicyVersion(
            policy_id=policy.id,
            version=(latest.version + 1) if latest else 1,
            spec=validated,
            published_by=by,
        )
    )
    session.flush()


def _apply(session: Session, edit, by: str | None) -> list[str]:
    uses: list[tuple[Use, dict]] = []
    for policy, spec in list(_candidates(session)):
        use = Use(policy, _label(session, policy))
        try:
            changed = edit(policy.policy_type, spec)
        except WithdrawalError as exc:
            raise WithdrawalError(f"{use.label}: {exc}") from exc
        if changed != spec:
            uses.append((use, changed))
    for use, changed in uses:
        _publish(session, use, changed, by)
    return labels([u for u, _ in uses])


def delete_package(
    session: Session, storage: ArtifactStorage, package: AppPackage, *, by: str | None = None
) -> list[str]:
    """Take the app out of every policy, then out of the library.

    Returns the names of the policies changed. Raises WithdrawalError (nothing
    changed) or PackageError (ATLAS's own apps, untouched here: W286).
    """
    if reserved_packages.is_reserved(package.package_name):
        package_service.delete_package(session, storage, package)  # raises
        return []
    name = package.package_name
    changed = _apply(session, lambda t, s: strip(t, s, name), by)
    package_service.delete_package(session, storage, package)
    return changed


def delete_version(
    session: Session, storage: ArtifactStorage, version: AppPackageVersion, *, by: str | None = None
) -> list[str]:
    """Re-pin every policy on this build, then delete it.

    The last build going is the app leaving the library: its entries are
    removed instead, as `delete_package` does.
    """
    package = version.package
    if reserved_packages.is_reserved(package.package_name):
        package_service.delete_version(session, storage, version)
        return []
    name, old = package.package_name, base_sha(version)
    successor = replacement(version)
    if successor is None:
        changed = _apply(session, lambda t, s: strip(t, s, name), by)
    elif old is not None:
        new = base_sha(successor)
        changed = _apply(session, lambda t, s: repin(t, s, name, old, new), by)
    else:
        changed = []
    package_service.delete_version(session, storage, version)
    return changed
