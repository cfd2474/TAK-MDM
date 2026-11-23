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

"""A kiosk's ATLAS store needs a store chosen in the same policy (W398).

Operator, 2026-10-14: *"allow atlas store must have a matching atlas store
approved on the same policy"*. The kiosk's approved apps **are** that store's
apps, read live, so a kiosk switch with no store behind it would offer nothing
and, worse, read as configured.

⚠️ **The same policy, strictly** — the reading `fence_rules` takes for a
geofence and its Password section, for the same reason: a store chosen in
another policy reaches the device too, but can be unassigned on its own and
leave the kiosk pointing at nothing. Enforced at the same four points: creating
a profile, saving a section, removing the App Management section, and the
standalone policy API (which has no sibling, so it refuses).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

KIOSK_KEY = "kiosk"
CATALOG_KEY = "app_management"


def violation(kiosk: Mapping[str, Any] | None, catalog: Mapping[str, Any] | None) -> str | None:
    """Why this pair cannot be saved, or None."""
    if not (kiosk or {}).get("multi_app_store"):
        return None
    if (catalog or {}).get("storefront_id"):
        return None
    return (
        "Allow the ATLAS store needs an ATLAS store chosen in this same policy: its "
        "apps are the ones the kiosk user may install. Choose one in App Management "
        "› App catalog, or turn the kiosk's store off."
    )


def check_sections(sections: Mapping[str, Mapping[str, Any]]) -> str | None:
    """The rule over a whole set of profile sections, keyed by catalog key."""
    return violation(sections.get(KIOSK_KEY), sections.get(CATALOG_KEY))


def blocks_catalog_removal(kiosk: Mapping[str, Any] | None) -> str | None:
    """Refusal when removing App Management would leave the kiosk's store empty."""
    if not (kiosk or {}).get("multi_app_store"):
        return None
    return (
        "this policy's kiosk allows the ATLAS store, which uses the store chosen in "
        "App Management, so App Management cannot be removed while it does. Turn "
        "Allow the ATLAS store off in Kiosk first."
    )
