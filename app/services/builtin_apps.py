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

"""The device's own apps, on a multi-app kiosk home screen (W374).

Operator, 2026-10-11: the standard Google apps should be placeable "without
them existing in the library", which also sidesteps a library build made for
a different Android (W373). A built-in tile names no build: ATLAS never
installs or requires it, and the agent switches it back on when the device has
it disabled. A library build still overrides - that is an ordinary tile.

What this module holds is the ready list the console offers, and the report of
devices that lack one. Any package may be a built-in tile ("Other built-in
app"); the list is a convenience, never a limit.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.db.models import Device

#: The standard Google apps, as (package, label), in the order the console
#: offers them. ⚠️ Samsung ships its own Phone, Contacts, Messages, Clock and
#: Calculator: on a Galaxy those tiles want "Other built-in app" with the
#: Samsung package, and the report below says which devices lack the Google one.
GOOGLE_SUITE: tuple[tuple[str, str], ...] = (
    ("com.android.chrome", "Chrome"),
    ("com.google.android.gm", "Gmail"),
    ("com.google.android.apps.maps", "Maps"),
    ("com.google.android.youtube", "YouTube"),
    ("com.google.android.apps.docs", "Drive"),
    ("com.google.android.calendar", "Calendar"),
    ("com.google.android.apps.photos", "Photos"),
    ("com.google.android.contacts", "Contacts"),
    ("com.google.android.dialer", "Phone"),
    ("com.google.android.apps.messaging", "Messages"),
    ("com.google.android.deskclock", "Clock"),
    ("com.google.android.calculator", "Calculator"),
    ("com.google.android.apps.nbu.files", "Files"),
    ("com.google.android.keep", "Keep"),
    # Meet took over Duo's package in 2022; the original Meet app is retired.
    ("com.google.android.apps.tachyon", "Meet"),
    ("com.google.android.googlequicksearchbox", "Google"),
)

_LABELS = dict(GOOGLE_SUITE)


def label(package: str) -> str:
    """The name the console shows: the suite's, else the package itself."""
    return _LABELS.get(package, package)


def builtin_tiles(spec: Any) -> list[str]:
    """Packages a kiosk spec places as built-in tiles, in tile order."""
    tiles = (spec or {}).get("multi_app_packages") if isinstance(spec, dict) else None
    return [
        t["package_name"] for t in tiles or []
        if isinstance(t, dict) and t.get("builtin") and t.get("package_name")
    ]


@dataclass(frozen=True)
class Lacking:
    """One built-in tile and the devices that reported not having it."""

    package_name: str
    devices: tuple[Device, ...]

    @property
    def label(self) -> str:
        return label(self.package_name)


def lacking(specs: Iterable[Any], devices: Iterable[Device]) -> list[Lacking]:
    """Built-in tiles that some of `devices` reported missing.

    ⚠️ Only what a device *said* (`Device.kiosk_missing`, agent 0.90.0+). A
    device that has not reported is not counted: an older agent cannot say,
    and "unknown" read as "missing" would have an operator chase apps that are
    there.
    """
    wanted: list[str] = []
    for spec in specs:
        wanted.extend(p for p in builtin_tiles(spec) if p not in wanted)
    devices = list(devices)
    found = []
    for package in wanted:
        without = tuple(d for d in devices if package in (d.kiosk_missing or ()))
        if without:
            found.append(Lacking(package, without))
    return found
