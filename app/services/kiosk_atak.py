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

"""ATAK and its plugins inside the multi-app kiosk (W407 C2c).

Operator: "i want a section where we can specify the atak version (which does
get a tile) and its plugins (which dont) ... since plugins still need to be
specified as installed per multi-app kiosk, it makes sense to have them here
instead of a separate tab." Then chose to *move* the ATAK and plugin pickers
into the kiosk while multi-app is on.

⚠️ **One set of data.** The kiosk edits the policy's own
`APP_CATALOG.atak_core` and `atak_plugins`; it has no copy. ATAK's tile in
`multi_app_packages` carries only its cell and dock, and its build comes from
`atak_core` (the resolver skips a tile whose app is already required).

This module settles a policy saved before that, whose kiosk placed ATAK as an
ordinary tile with a build of its own. Pure: it reads two specs and returns
what the editor should show, and the next save stores it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.atak_compat import is_atak


@dataclass(frozen=True)
class KioskAtak:
    #: App Management's spec as the editor should render it: `atak_core`
    #: filled from the old tile when it was empty. A new dict; never the input.
    catalog_spec: dict[str, Any]
    #: The ATAK tile the kiosk saved, if any: its cell and dock.
    tile: dict[str, Any] | None
    #: Said beside the ATAK row when the two named different builds.
    notice: str | None


def atak_tile(kiosk_spec: dict[str, Any] | None) -> dict[str, Any] | None:
    """The kiosk's ATAK tile: a library app (not built-in) named like ATAK."""
    for tile in (kiosk_spec or {}).get("multi_app_packages") or []:
        if isinstance(tile, dict) and not tile.get("builtin") and is_atak(tile.get("package_name")):
            return tile
    return None


def adopt(catalog_spec: dict[str, Any] | None, kiosk_spec: dict[str, Any] | None) -> KioskAtak:
    """Reconcile an older kiosk's ATAK tile with App Management's ATAK Core.

    * ATAK Core empty, tile pinned to a build: that build becomes ATAK Core,
      so the policy keeps installing what it did.
    * Both name a build and they differ: ATAK Core wins, since it is what the
      device already gets (an explicit entry beats a tile), and the page says so.
    """
    catalog = dict(catalog_spec or {})
    tile = atak_tile(kiosk_spec)
    if tile is None:
        return KioskAtak(catalog, None, None)
    core = catalog.get("atak_core") or None
    pinned = tile.get("artifact_sha256")
    if core is None:
        if pinned:
            catalog["atak_core"] = {"package_name": tile["package_name"], "artifact_sha256": pinned}
        return KioskAtak(catalog, tile, None)
    # An "always newest" ATAK Core pins no build, so it differs from any pin.
    differs = core.get("package_name") != tile["package_name"] or bool(
        pinned and core.get("artifact_sha256") != pinned
    )
    notice = (
        "This kiosk's ATAK tile named a build of its own. ATAK below is the one "
        "devices install, so its build is kept; the tile now only places ATAK."
        if differs else None
    )
    return KioskAtak(catalog, tile, notice)
