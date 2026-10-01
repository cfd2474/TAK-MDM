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

"""The ATLAS ATAK plugin, delivered with ATAK and never chosen (W300).

Operator, 2026-09-30: *"it will automatically install on any device that
receives an ATAK install policy. it will receive the most recent build of the
appropriate matching version (5.5, 5.6, 5.7, 5.8). We will maintain copies of
the plugin for each of those versions in the library."*

So the plugin is an ATLAS system app like the launcher: shipped in `dist/`,
seeded into the library, reserved from every picker, and added to a device's
required apps by ATLAS itself. What decides *which* build is the ATAK the
policy installs -- never the device's report, which is absent until ATAK is
already there, and never the highest versionCode: the R+1 build for 5.6 sorts
above the R build for 5.8 (`docs/ATLAS-PLUGIN-CONTRACT.md`).

⚠️ **Selection is "the highest line at or below the ATAK's, then the newest
build of it".** Where the library holds the exact line that is the exact line,
which is what the operator asked for. Below it is the fallback the platform
allows: ATAK loads a plugin built for an *older* ATAK from 4.10.0 on, and
refuses one built for a newer ATAK (platform reference, "ATAK plugins: older
builds load in newer ATAK"). A line above the ATAK's is therefore never chosen.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppPackage, AppPackageFile, AppPackageVersion, PartRole
from app.services import atak_compat

#: The plugin's package. Must match the plugin repository's manifest -- the
#: contract in `docs/ATLAS-PLUGIN-CONTRACT.md` fixes it.
PACKAGE = "com.taksolutions.atlasmdm.atak"

#: The plugin's development build. It shares the production entry class, and
#: ATAK caches plugins by class name, so with both installed only one runs. It
#: never belongs in a deployment's library.
DEV_PACKAGE = f"{PACKAGE}.dev"

#: The ATAK preference that keeps a plugin switched on. ATAK writes it false
#: when a plugin is updated while ATAK runs, and keeps it false (platform
#: reference §10), so ATLAS asserts it true on every device it installs to.
SHOULD_LOAD_KEY = f"shouldLoad-{PACKAGE}"


def _line(version: str | None) -> tuple[int, ...] | None:
    if not version:
        return None
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return None


def _atak_entry(values: Mapping[str, Any]) -> dict[str, Any] | None:
    """The ATAK the policy installs: ATAK Core, else an ATAK required app."""
    catalog = values.get("APP_CATALOG") or {}
    core = catalog.get("atak_core")
    if core and atak_compat.is_atak(core.get("package_name")):
        return core
    return next(
        (
            entry
            for entry in (catalog.get("required_apps") or [])
            if atak_compat.is_atak((entry or {}).get("package_name"))
        ),
        None,
    )


def atak_line_for(session: Session, values: Mapping[str, Any]) -> str | None:
    """The ATAK line (`5.8.0`) of the build this policy installs, or None.

    Only a pinned build counts: since W139 an entry that names no build
    installs nothing, so there is no ATAK to pair a plugin with.
    """
    entry = _atak_entry(values)
    pinned = (entry or {}).get("artifact_sha256")
    if not pinned:
        return None
    version = session.scalar(
        select(AppPackageVersion)
        .join(AppPackageFile, AppPackageFile.version_id == AppPackageVersion.id)
        .join(AppPackage, AppPackage.id == AppPackageVersion.package_id)
        .where(
            AppPackageFile.artifact_sha256 == pinned,
            AppPackage.package_name == entry["package_name"],
        )
        .limit(1)
    )
    return atak_compat.atak_line(version.version_name) if version is not None else None


def builds(session: Session) -> list[AppPackageVersion]:
    """Every plugin build in the library."""
    package = session.scalar(select(AppPackage).where(AppPackage.package_name == PACKAGE))
    return list(package.versions) if package is not None else []


def build_line(version: AppPackageVersion) -> tuple[int, ...] | None:
    """The ATAK line a plugin build targets, from its `plugin-api`."""
    return _line(atak_compat.plugin_target(version.plugin_api))


def select_build(session: Session, atak_line: str | None) -> AppPackageVersion | None:
    """The build a device on ``atak_line`` should run, or None if none fits."""
    target = _line(atak_line)
    if target is None:
        return None
    fitting = [
        (line, version.version_code, version)
        for version in builds(session)
        if (line := build_line(version)) is not None and line <= target
    ]
    if not fitting:
        return None
    return max(fitting, key=lambda item: (item[0], item[1]))[2]


def is_line_newest(session: Session, version: AppPackageVersion) -> bool:
    """Whether this is the newest build of its ATAK line -- the one in use."""
    line = build_line(version)
    return all(
        other.version_code <= version.version_code
        for other in builds(session)
        if build_line(other) == line
    )


def required_entry(session: Session, values: Mapping[str, Any]) -> dict[str, Any] | None:
    """The required-app entry ATLAS adds for this policy, or None.

    None when the policy installs no ATAK, and also when the library holds no
    build that fits it: a device is then simply not given the plugin, rather
    than shown a required app that can never install.
    """
    version = select_build(session, atak_line_for(session, values))
    if version is None:
        return None
    base = next((f for f in version.files if f.role is PartRole.BASE), None)
    if base is None:
        return None
    return {"package_name": PACKAGE, "artifact_sha256": base.artifact_sha256}
