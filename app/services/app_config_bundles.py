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

"""Bundle-type keys in App configurations, on their way to a device (W357).

A bundle's value travels as a JSON object string under the bundle's key - Gboard's
`preferences` holding `{"enable_number_row": "true"}` - and the device is told each
setting's declared type in `bundle_types`, so it can build the nested Bundle the
app reads with `getBundle`.

⚠️ **An agent older than MIN_AGENT cannot.** Before 0.82.5 the agent rejects a
bundle as an error, which marks the device DEGRADED - and a DEGRADED device is
refused agent updates, so it could never receive the agent that fixes it. The
bundle is therefore left out of that device's desired state, and the device page
says what is waiting (`withheld`).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts.app_restrictions import TYPE_BUNDLE
from app.artifacts.storage import ArtifactStorage
from app.db.models import AppPackage, AppPackageVersion, Device
from app.services import agent_versions
from app.services import packages as package_service

#: The first agent that builds a nested Bundle from `bundle_types`.
MIN_AGENT = (0, 82, 5)


def supported(agent_version: str | None) -> bool:
    """Only a known, new-enough agent is sent a bundle."""
    return agent_versions.at_least(agent_version, MIN_AGENT) is True


def bundle_keys(values: dict[str, Any], declared: dict[str, int]) -> list[str]:
    """The configured keys that are bundles in the deployed build."""
    return sorted(key for key in values if declared.get(key) == TYPE_BUNDLE)


def newest_version(session: Session, package_name: str) -> AppPackageVersion | None:
    package = session.scalar(select(AppPackage).where(AppPackage.package_name == package_name))
    return package_service.newest(session, package) if package is not None else None


def withheld(
    session: Session, storage: ArtifactStorage, device: Device, configs: list[dict[str, Any]]
) -> list[tuple[str, str]]:
    """`(package, bundle key)` configured for this device but held back for its agent."""
    if supported(device.agent_version):
        return []
    held: list[tuple[str, str]] = []
    for entry in configs:
        package_name = entry.get("package_name") or ""
        version = newest_version(session, package_name)
        if version is None:
            continue
        declared = package_service.declared_config(session, version, storage)
        held += [(package_name, key) for key in bundle_keys(entry.get("values") or {}, declared)]
    return held
