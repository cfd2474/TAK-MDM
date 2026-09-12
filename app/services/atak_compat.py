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

"""Does this plugin match the ATAK it will sit next to?

An ATAK plugin only loads in the ATAK build it was compiled against. The plugin
declares that build in its manifest (`plugin-api`, e.g.
`com.atakmap.app@5.5.0.CIV`), and a mismatch is not a crash — the plugin installs
and simply never appears in ATAK, which looks like an MDM failure and is not one.

Three rules, all deliberate:

* **Warn, never forbid.** The operator may have a reason, and a plugin that ATAK
  will not load costs a puzzled user, not a broken device.
* **The warning goes on the plugin.** ATAK is the fixed point everything else is
  built against; telling someone their ATAK is wrong because a plugin disagrees
  inverts cause and effect.
* **Silence when unknown.** A missing `plugin-api`, or an ATAK version nobody has
  reported, produces no warning at all. A compatibility check that cries wolf on
  every ordinary app is one an operator learns to ignore, and then it is worth
  less than nothing.

Pure functions over strings — no session, no device — so the rules can be argued
with in tests rather than through a policy form.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: `com.atakmap.app@5.5.0.CIV` -> ("5.5.0", "CIV")
_PLUGIN_API = re.compile(r"@(?P<version>\d+(?:\.\d+)*)(?:\.(?P<flavour>[A-Za-z]+))?\s*$")

#: ATAK's own versionName, e.g. `5.8.0.4 (174b425)[playstore]`.
_ATAK_VERSION = re.compile(r"^\s*(?P<version>\d+(?:\.\d+)*)")

#: Package names ATAK itself ships under. A plugin is anything else.
ATAK_PACKAGE_PREFIX = "com.atakmap.app"


def is_atak(package_name: str | None) -> bool:
    return bool(package_name) and package_name.startswith(ATAK_PACKAGE_PREFIX)


def plugin_target(plugin_api: str | None) -> str | None:
    """The ATAK version a plugin targets, from its `plugin-api` value."""
    if not plugin_api:
        return None
    match = _PLUGIN_API.search(plugin_api)
    return match.group("version") if match else None


def atak_line(version_name: str | None) -> str | None:
    """The ATAK line a build belongs to, as major.minor.patch.

    ATAK's versionName carries a fourth component and build metadata
    (`5.8.0.4 (174b425)[playstore]`), while a plugin targets `5.8.0`. Comparing
    the raw strings would report every pairing as a mismatch.
    """
    if not version_name:
        return None
    match = _ATAK_VERSION.match(version_name)
    if not match:
        return None
    parts = match.group("version").split(".")
    if len(parts) < 2:
        return None
    return ".".join(parts[:3])


#: The flavour that loads anywhere (operator, W141): *"for now, lets assume a
#: civ plugin is compatible with mil version"*. Every other flavour must match
#: the ATAK it sits next to.
UNIVERSAL_FLAVOUR = "CIV"


def plugin_flavour(plugin_api: str | None) -> str | None:
    """The ATAK flavour a plugin targets — `CIV`, `MIL`, `GOV` — or None.

    ⚠️ **Already in the string the version came from.** `_PLUGIN_API` has
    captured this group since it was written and nothing read it, so the second
    dimension of the check needs no new column and no second source of truth:
    the plugin states its flavour in its own manifest, beside the version.
    """
    if not plugin_api:
        return None
    match = _PLUGIN_API.search(plugin_api)
    flavour = match.group("flavour") if match else None
    return flavour.upper() if flavour else None


def atak_flavour(package_name: str | None) -> str | None:
    """ATAK's flavour, from its package name — `com.atakmap.app.civ` → `CIV`.

    ⚠️ **A bare `com.atakmap.app` yields None, and that stays silent.** This
    project has seen `com.atakmap.app` and `com.atakmap.app.civ` on real
    hardware and no MIL package name at all, so the suffix is read where it
    exists and nothing is assumed where it does not — the same rule the version
    check already follows. A flavour warning invented from a guess would be
    worse than no warning.
    """
    if not is_atak(package_name):
        return None
    suffix = package_name[len(ATAK_PACKAGE_PREFIX):].lstrip(".")
    return suffix.upper() if suffix else None


def flavours_agree(plugin: str | None, atak: str | None) -> bool:
    """Whether a plugin's flavour can sit next to this ATAK's.

    | plugin | ATAK | verdict |
    |---|---|---|
    | CIV | anything | ✅ the universal donor, for now |
    | MIL | MIL | ✅ |
    | MIL | CIV | ⚠️ mismatch |
    | either unknown | | ✅ silence |

    ⏳ **GOV is not specified.** `tak_gov.py` knows three products and the
    operator named two, so everything that is not CIV must match exactly. It is
    a warning either way, so being wrong here costs a sentence rather than an
    install.
    """
    if plugin is None or atak is None:
        return True
    if plugin == UNIVERSAL_FLAVOUR:
        return True
    return plugin == atak


@dataclass(frozen=True)
class Mismatch:
    package_name: str
    plugin_target: str
    atak_version: str
    #: Where the ATAK version came from — "policy" or "device".
    source: str
    #: Set when the *flavour* is what disagrees (W141), e.g. a MIL plugin beside
    #: CIV ATAK. None when the versions are what disagree.
    plugin_flavour: str | None = None
    atak_flavour: str | None = None

    @property
    def message(self) -> str:
        seen = (
            "the policy installs ATAK"
            if self.source == "policy"
            else "the device has ATAK"
        )
        if self.plugin_flavour and self.atak_flavour:
            return (
                f"built for ATAK {self.plugin_flavour}, but {seen} "
                f"{self.atak_flavour}. A {self.plugin_flavour} plugin is not "
                f"compatible with {self.atak_flavour}, so this one may not "
                "appear once installed."
            )
        return (
            f"built for ATAK {self.plugin_target}, but {seen} {self.atak_version}. "
            "ATAK loads only plugins built for its own version, so this one will "
            "install and then not appear."
        )


def check(
    *,
    atak_version: str | None,
    plugins: dict[str, str | None],
    source: str = "policy",
    atak_package: str | None = None,
) -> list[Mismatch]:
    """Plugins that will not load beside this ATAK, on either dimension.

    ``plugins`` maps package name to its raw ``plugin_api`` value. Entries with no
    target, and the case where the ATAK version is unknown, yield nothing — see the
    module docstring on silence.

    ⚠️ **Two dimensions, one at a time** (W141). A version disagreement is
    reported as a version disagreement; a flavour disagreement — a MIL plugin
    beside CIV ATAK — is reported as that. Reporting both at once would produce
    a sentence naming four things, when the operator only needs the first reason
    it will not load.

    ``atak_package`` is optional, and without it only the version is checked.
    That is the honest degradation: flavour comes from ATAK's package name, and
    a caller that does not know the package does not know the flavour.
    """
    if not atak_version:
        return []

    wanted_flavour = atak_flavour(atak_package)
    mismatches = []
    for package_name, plugin_api in sorted(plugins.items()):
        target = plugin_target(plugin_api)
        if target is None:
            continue
        if target != atak_version:
            mismatches.append(
                Mismatch(
                    package_name=package_name,
                    plugin_target=target,
                    atak_version=atak_version,
                    source=source,
                )
            )
            continue

        theirs = plugin_flavour(plugin_api)
        if not flavours_agree(theirs, wanted_flavour):
            mismatches.append(
                Mismatch(
                    package_name=package_name,
                    plugin_target=target,
                    atak_version=atak_version,
                    source=source,
                    plugin_flavour=theirs,
                    atak_flavour=wanted_flavour,
                )
            )
    return mismatches


def for_device(session, device) -> list[Mismatch]:
    """Plugins assigned to this device that its real ATAK will not load.

    Reads the device's **resolved** apps rather than the raw policies, so it
    reflects what will actually be installed after floors and pins are applied.
    Returns nothing when the device has never reported an ATAK version — that is
    an unknown, not a clean bill of health, and the caller says so.
    """
    from sqlalchemy import select

    from app.db.models import AppPackage, AppPackageVersion
    from app.services import effective_policy as eff

    line = atak_line(device.atak_version)
    if not line:
        return []

    resolved = (eff.get_effective(session, device) or {}).get("apps") or []
    wanted = {
        entry["package_name"]: entry.get("version_code")
        for entry in resolved
        if entry.get("available") and not is_atak(entry.get("package_name"))
    }
    if not wanted:
        return []

    rows = session.execute(
        select(AppPackage.package_name, AppPackageVersion.version_code, AppPackageVersion.plugin_api)
        .join(AppPackageVersion, AppPackageVersion.package_id == AppPackage.id)
        .where(AppPackage.package_name.in_(wanted))
    )
    plugins = {
        name: plugin_api
        for name, version_code, plugin_api in rows
        if wanted.get(name) == version_code
    }
    # The device reports its ATAK package name alongside the version, so the
    # flavour check has both halves here without guessing (W141).
    return check(
        atak_version=line,
        plugins=plugins,
        source="device",
        atak_package=device.atak_package,
    )


# --------------------------------------------------------------------------- #
# Which section an app belongs in (W141)
#
# ⚠️ These need the library, which is why they are here and not on the spec.
# `is_atak` above is a package-name test and holds on every path into a policy;
# "is a plugin" means *this app declares a plugin-api*, which is a column — so
# the rule can only be enforced where a session exists, and the callers below
# are the complete list of places a policy spec is written.
# --------------------------------------------------------------------------- #


#: A build imported from here is a plugin whatever its manifest says — the
#: catalogue is a plugin catalogue (operator, W141).
TPC_SOURCE = "tak.gov"


def plugin_packages(session) -> set[str]:
    """Package names the library knows to be ATAK plugins.

    Two ways of knowing, and both are needed:

    * the build **declares a `plugin-api`**, read from the APK or XAPK at upload;
    * the build **came from TAK.gov**, whose catalogue is plugins and nothing
      else — *"any plugin that comes from the tpc repo is obviously a plugin"*.

    ⚠️ **Any build, not the newest.** `plugin_api` is NULL on anything uploaded
    before the column existed, and `backfill_plugin_api` fills those in
    afterwards — asking only the newest build would call a plugin an ordinary
    app for as long as its latest upload happened to predate the scan. The same
    reasoning applies to provenance: one TPC import is enough, forever.
    """
    from sqlalchemy import or_, select

    from app.db.models import AppPackage, AppPackageVersion

    rows = session.scalars(
        select(AppPackage.package_name)
        .join(AppPackageVersion, AppPackageVersion.package_id == AppPackage.id)
        .where(
            or_(
                AppPackageVersion.plugin_api.is_not(None),
                AppPackageVersion.source == TPC_SOURCE,
            )
        )
    )
    return set(rows)


def misplaced_plugins(session, spec: dict | None) -> list[str]:
    """Plugins sitting in required apps or the allowlist, which is the wrong section.

    Returns the offending package names, sorted, or an empty list. The caller
    decides how to complain, because a form and an API want different words for
    the same refusal.
    """
    if not spec:
        return []

    plugins = plugin_packages(session)
    if not plugins:
        return []

    named = {
        entry.get("package_name")
        for entry in (spec.get("required_apps") or [])
        if isinstance(entry, dict)
    } | set(spec.get("allowed_packages") or [])

    return sorted(name for name in named if name in plugins)


def refusal_for(names: list[str]) -> str:
    """One sentence naming the section to use instead."""
    listed = ", ".join(names)
    plural = "is an ATAK plugin" if len(names) == 1 else "are ATAK plugins"
    return (
        f"{listed} {plural} and belongs in ATAK Core and Plugins, not in "
        "required apps or the allowlist. That section checks a plugin against "
        "the ATAK build it will sit next to, which this one cannot do."
    )
