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

"""Turn an ATAK_CONFIG policy into something a device can apply (W90).

⚠️ **ATAK_CONFIG has no applier of its own, by design (D92).** It resolves into
the `app_configs` channel the agent already has: the generated `.pref` document
becomes the value of ATAK's `enterpriseConfigurationPreferences` key, and the
existing `setApplicationRestrictions` path carries it. No new agent code, no new
agent release, and one fewer place for the device to disagree with the console.

⚠️ **That merge has to happen here and nowhere else.** ATAK Config and an
operator-authored App-Management configuration for `com.atakmap.app.civ` both end
at `setApplicationRestrictions` **for the same package**, and that call replaces
the app's whole Bundle. Two independent writers means whichever ran last wins and
the other silently vanishes. Merged at one deterministic point on the server, the
collision cannot occur.

⚠️ **Nothing here may raise into a check-in.** `desired_state.build` runs on the
device's request, so a policy this module cannot render must degrade to "no ATAK
configuration" with a warning, never to a failed check-in. The operator is told in
the console, where they can act; the tablet is not punished for it.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts import pref_screens
from app.artifacts.storage import ArtifactStorage
from app.db.models import AppPackage, AppPackageVersion, PartRole
from app.services import atak_compat, atak_pref
from app.services import packages as package_service

#: ATAK's managed-configuration key that carries a `.pref` document, verbatim.
#: Declared by the shipping build; see the platform reference §10a.
ENTERPRISE_PREFS_KEY = "enterpriseConfigurationPreferences"

#: Scans keyed by the base APK's content hash.
#:
#: ⚠️ Caches the **result**, never the APK bytes — ATAK's is 112 MB and UAS
#: Tool's 395 MB, and pinning those is how an earlier cache cost more than a
#: gigabyte. A scan result is a few hundred small frozen objects, and a build is
#: immutable at its hash so it cannot go stale. Bounded, because an operator's
#: plugin shelf is not.
_SCANS: OrderedDict[str, pref_screens.PrefSchema] = OrderedDict()
_SCAN_LIMIT = 24


@dataclass
class Rendered:
    """What an ATAK_CONFIG policy amounts to, plus anything the operator should know."""

    document: str = ""
    #: The ATAK package the document is addressed to, when one could be chosen.
    package_name: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def deliverable(self) -> bool:
        return bool(self.document and self.package_name)


def _base_sha(version: AppPackageVersion) -> str | None:
    base = next((f for f in version.files if f.role is PartRole.BASE), None)
    return base.artifact_sha256 if base else None


def schema_for(
    session: Session, storage: ArtifactStorage, package: AppPackage
) -> pref_screens.PrefSchema | None:
    """The settings a package's latest published build declares, memoised.

    Scanned from the APK rather than kept in a column, so it cannot drift from
    the build it describes (D91) — the same trade `declared_config` makes for
    managed configuration.
    """
    version = package_service.latest_published(session, package)
    if version is None:
        return None
    sha = _base_sha(version)
    if sha is None:
        return None

    cached = _SCANS.get(sha)
    if cached is not None:
        _SCANS.move_to_end(sha)
        return cached

    try:
        with storage.open(sha) as handle:
            data = handle.read()
    except (FileNotFoundError, OSError):
        return None

    schema = pref_screens.discover(data, package.package_name)
    _SCANS[sha] = schema
    if len(_SCANS) > _SCAN_LIMIT:
        _SCANS.popitem(last=False)
    return schema


def atak_packages(session: Session) -> list[AppPackage]:
    """Every ATAK build in the library, by package name."""
    return [
        package
        for package in session.scalars(select(AppPackage).order_by(AppPackage.package_name))
        if atak_compat.is_atak(package.package_name)
    ]


def _target_package(session: Session, policy: dict[str, Any]) -> tuple[AppPackage | None, str | None]:
    """Which ATAK build this policy's settings are addressed to.

    ⚠️ **A device can hold only one ATAK**, but a library can hold several — CIV
    and MIL, or two lines for a mixed fleet. Guessing between them would push a
    configuration at whichever sorted first, so the question is answered from the
    policy itself where it can be, and refused where it cannot.
    """
    available = atak_packages(session)
    if not available:
        return None, (
            "No ATAK build is in the app library, so its settings cannot be read "
            "or delivered. Upload the ATAK build this policy targets."
        )

    required = {
        entry.get("package_name")
        for entry in ((policy.get("APP_CATALOG") or {}).get("required_apps") or [])
    }
    named = [p for p in available if p.package_name in required]
    if len(named) == 1:
        return named[0], None
    if len(available) == 1:
        return available[0], None

    names = ", ".join(p.package_name for p in available)
    return None, (
        f"The library holds more than one ATAK build ({names}) and this policy "
        f"does not require one of them, so there is no way to tell which its "
        f"settings are for. Add the ATAK build to this policy's required apps."
    )


def _plugin_types(
    session: Session, storage: ArtifactStorage, package_name: str
) -> tuple[dict[str, str], str | None, str | None]:
    """(key → java class, preference group, warning) for one plugin.

    A plugin that is not in the library cannot be scanned. Its settings are still
    sent — the operator chose them, and they were readable when they did — but
    every value is carried as a **String**, which is the only class whose value
    cannot fail to parse. The warning says so, because a boolean silently
    delivered as a string reads as false to the plugin.
    """
    package = session.scalar(
        select(AppPackage).where(AppPackage.package_name == package_name)
    )
    schema = schema_for(session, storage, package) if package is not None else None
    if schema is None:
        return {}, None, (
            f"{package_name} is not in the app library, so its settings cannot be "
            f"typed and are all being sent as text. Upload the plugin build to fix "
            f"this."
        )
    return schema.types(), schema.preference_group, None


def render(
    session: Session, storage: ArtifactStorage, policy: dict[str, Any]
) -> Rendered:
    """Build the `.pref` document a resolved policy calls for.

    Groups are emitted ATAK's first, then the rest by name, and keys within a
    group in sorted order — so an unchanged policy always produces identical
    bytes and the device's MD5 dedupe makes a re-push a genuine no-op.
    """
    spec = policy.get("ATAK_CONFIG") or {}
    core = spec.get("core_prefs") or []
    plugins = spec.get("plugin_prefs") or []
    if not core and not plugins:
        return Rendered()

    package, problem = _target_package(session, policy)
    if package is None:
        return Rendered(warnings=[problem] if problem else [])

    schema = schema_for(session, storage, package)
    if schema is None:
        return Rendered(
            warnings=[
                f"{package.package_name} has no published build to read settings "
                f"from, so this configuration cannot be delivered."
            ]
        )

    warnings: list[str] = []
    # Grouped by SharedPreferences name: a plugin runs inside ATAK's process and
    # usually writes into ATAK's own store, so most of these collapse into one
    # block rather than one per plugin.
    grouped: dict[str, dict[str, str]] = {}
    types: dict[str, str] = dict(schema.types())

    if core:
        grouped.setdefault(schema.preference_group, {}).update(
            {entry["key"]: entry["value"] for entry in core}
        )

    for entry in plugins:
        package_name = entry.get("package_name")
        values = entry.get("values") or {}
        if not package_name or not values:
            continue
        plugin_types, group, warning = _plugin_types(session, storage, package_name)
        if warning:
            warnings.append(warning)
        # ⚠️ `setdefault`, not `update`: ATAK's own class for a key wins over a
        # plugin's. They collide only when both declare the same key in the same
        # store, and ATAK is the process that owns it.
        for key, java_class in plugin_types.items():
            types.setdefault(key, java_class)
        grouped.setdefault(group or schema.preference_group, {}).update(values)

    ordered = sorted(
        grouped.items(),
        key=lambda item: (item[0] != schema.preference_group, item[0]),
    )
    groups = [
        (name, atak_pref.entries_from(values, types)) for name, values in ordered
    ]

    try:
        document = atak_pref.build(groups)
    except atak_pref.PrefError as exc:
        # Never raised onward: this runs inside a device's check-in.
        return Rendered(warnings=warnings + [str(exc)])

    return Rendered(
        document=document, package_name=package.package_name, warnings=warnings
    )


def merge_into_policy(
    session: Session, storage: ArtifactStorage, policy: dict[str, Any]
) -> dict[str, Any]:
    """Fold an ATAK_CONFIG policy into the ATAK package's managed configuration.

    ⚠️ **Additive, never replacing.** An operator may have set ATAK's other
    enterprise keys — the five data-package slots — through App Management, and
    those must survive. Only `enterpriseConfigurationPreferences` is written,
    and only when this policy has something to say.

    ⚠️ **This policy wins that one key**, and says so. Setting the same key by
    hand in App Management is asking for the same thing twice in two places; the
    generated document is the one that matches what the ATAK Config editor shows,
    so the hand-typed value loses rather than silently overwriting a whole
    category's settings.
    """
    rendered = render(session, storage, policy)
    if not rendered.deliverable:
        return policy

    catalog = dict(policy.get("APP_CATALOG") or {})
    configs = [dict(entry) for entry in (catalog.get("app_configs") or [])]

    for entry in configs:
        if entry.get("package_name") == rendered.package_name:
            values = dict(entry.get("values") or {})
            values[ENTERPRISE_PREFS_KEY] = rendered.document
            entry["values"] = values
            break
    else:
        configs.append(
            {
                "package_name": rendered.package_name,
                "values": {ENTERPRISE_PREFS_KEY: rendered.document},
            }
        )

    catalog["app_configs"] = configs
    return {**policy, "APP_CATALOG": catalog}
