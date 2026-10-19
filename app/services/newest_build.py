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

""""Always the newest build": the newest build a device can run (W394).

Operator: required apps "have option for each app to keep to latest release ...
without the user having to constantly change the release in the policy itself",
and, asked which build: **the newest each device can run**.

⚠️ **Not W139 coming back.** W139 removed *automatic* selection because an entry
with no build named nearly installed Chrome across a fleet. This runs only for
an entry an operator explicitly set to "Always the newest build" in the policy
editor; an entry naming nothing still installs nothing.

A build fits a device when:
- its `min_sdk` is at or below the device's Android level;
- it carries native code for one of the device's CPU types, or none at all;
- for an ATAK plugin (a build declaring a `plugin-api`), it was built for the
  ATAK line the device will run: that line exactly first, then the newest
  older line ATAK still loads, never a newer one (ATAK refuses those).
A fact the device has not reported excludes nothing: a device that never said
its Android level is not refused every build.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppPackage, AppPackageVersion, Device
from app.services import atak_compat


@dataclass(frozen=True)
class Choice:
    version: AppPackageVersion | None
    #: Why nothing was chosen, for the device page; "" when something was.
    reason: str = ""


def _abis(text: str | None) -> set[str]:
    return {a.strip() for a in (text or "").split(",") if a.strip()}


def _runs_on(version: AppPackageVersion, device: Device | None) -> bool:
    if device is None:
        return True
    if device.sdk_int and version.min_sdk and version.min_sdk > device.sdk_int:
        return False
    carried, supported = _abis(version.abis), _abis(device.supported_abis)
    if carried and supported and not carried & supported:
        return False
    return True


def choose(
    session: Session,
    package_name: str,
    *,
    device: Device | None = None,
    atak_version: str | None = None,
) -> Choice:
    """The newest build of `package_name` this device can run.

    :param atak_version: the ATAK the device will run (the policy's ATAK Core
        build, else what the device reports), for choosing a plugin's build.
    """
    builds = sorted(
        session.scalars(
            select(AppPackageVersion)
            .join(AppPackage, AppPackage.id == AppPackageVersion.package_id)
            .where(AppPackage.package_name == package_name)
        ),
        key=lambda v: v.version_code,
        reverse=True,
    )
    builds = [v for v in builds if any(f.role.value == "base" for f in v.files)]
    if not builds:
        return Choice(None, "nothing uploaded for it")

    runnable = [v for v in builds if _runs_on(v, device)]
    if not runnable:
        return Choice(None, "set to the newest build, but no build of it runs on this device "
                            "(each needs a newer Android or another CPU type)")

    line = atak_compat.atak_line(atak_version) or atak_version
    if line:
        exact, older = [], []
        for v in runnable:
            target = atak_compat.plugin_target(v.plugin_api)
            if not target:
                continue
            fit = atak_compat.level(target, line)
            if fit is None:
                exact.append(v)
            elif fit == atak_compat.NOTE:
                older.append(v)
        plugins = [v for v in runnable if atak_compat.plugin_target(v.plugin_api)]
        if plugins:
            if exact or older:
                return Choice((exact or older)[0])
            return Choice(None, f"set to the newest build, but no build of it is for ATAK {line} "
                                "or an older ATAK it loads")
    return Choice(runnable[0])
