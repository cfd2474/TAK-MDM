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

"""Builds a policy names that some of its devices cannot install (W373).

Found on an Android 11 phone (2026-10-11): the policy pinned Chrome and Maps
builds downloaded for a newer device (minSdk 32), Android refused them
(`INSTALL_FAILED_OLDER_SDK`), and the device reported the failure on every
sync. ATLAS knows both numbers before anything is sent: each build's `min_sdk`
from its manifest, each device's `sdk_int` from its check-ins.

**A warning, never a refusal** (operator): other devices the policy reaches may
need exactly that build.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppPackageFile, Device

#: Every spec field that pins a build.
_PIN_KEYS = ("artifact_sha256", "kiosk_artifact_sha256")

#: API level to the Android version people know.
_ANDROID = {
    26: "8", 27: "8.1", 28: "9", 29: "10", 30: "11", 31: "12", 32: "12L",
    33: "13", 34: "14", 35: "15", 36: "16", 37: "17",
}


def android_name(sdk: int) -> str:
    return f"Android {_ANDROID.get(sdk, f'API {sdk}')}"


@dataclass(frozen=True)
class Misfit:
    """One pinned build and the devices that cannot install it."""

    package_name: str
    label: str
    version_code: int
    version_name: str | None
    min_sdk: int
    devices: tuple[Device, ...]

    @property
    def needs(self) -> str:
        return android_name(self.min_sdk)


def pinned_builds(spec: Any) -> set[str]:
    """Every build hash a policy's spec pins, wherever it sits."""
    return set(_walk(spec))


def _walk(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _PIN_KEYS and isinstance(value, str):
                yield value
            else:
                yield from _walk(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk(item)


def misfits(session: Session, specs: Iterable[Any], devices: Iterable[Device]) -> list[Misfit]:
    """Pinned builds whose minimum Android is above some of `devices`.

    A device that has not reported its API level is not counted: unknown is
    not "too old".
    """
    shas = set().union(*(pinned_builds(s) for s in specs)) if specs else set()
    devices = [d for d in devices if d.sdk_int is not None]
    if not shas or not devices:
        return []
    found: dict[int, Misfit] = {}
    for part in session.scalars(select(AppPackageFile).where(AppPackageFile.artifact_sha256.in_(shas))):
        version = part.version
        if version is None or version.min_sdk is None or version.id in found:
            continue
        behind = tuple(d for d in devices if d.sdk_int < version.min_sdk)
        if behind:
            package = version.package
            found[version.id] = Misfit(
                package_name=package.package_name,
                label=package.label or package.package_name,
                version_code=version.version_code,
                version_name=version.version_name,
                min_sdk=version.min_sdk,
                devices=behind,
            )
    return sorted(found.values(), key=lambda m: (m.label.lower(), m.version_code))
