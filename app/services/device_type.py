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

"""Smartphone or tablet, from the model the device reports (W310, W311).

Operator, 2026-10-02: "add a category to the devices: device type. it should be
smartphone or tablet, and be based on the device models."

**Two sources, in order:**

1. **The device catalogue** (W311), `app/data/device_catalog.json`: about 6,800
   phones and tablets from the top ten Android brands, keyed on `Build.MODEL`,
   which is exactly what the agent reports. It's generated from Google Play's
   supported-devices list by `scripts/build_device_catalog.py`, which records its
   source, date and rules. Rerun it to refresh; don't hand-edit it.
2. **Rules,** for a model the catalogue doesn't hold (a new release, another
   brand). Samsung encodes the form factor in the letter after `SM-`; other
   vendors are covered only where the name says so.

⚠️ **Never a guess.** A model neither source covers is unknown (None), never
forced into one bucket. The tempting fallback would be `has_telephony`, and it's
wrong: LTE tablets have a cellular radio, so it would call them phones.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

SMARTPHONE = "Smartphone"
TABLET = "Tablet"

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "device_catalog.json"

#: Samsung's form factor is the letter after "SM-": T, X and P are Galaxy Tab
#: lines; S, G, A, M, N, F, E, C and J are phones. Watches (R, L) and anything
#: else stay unknown. Matches the catalogue generator.
_SAMSUNG = re.compile(r"^SM-([A-Z])", re.IGNORECASE)
_SAMSUNG_TABLET = frozenset("TXP")
_SAMSUNG_PHONE = frozenset("SGAMNFECJ")

#: Names that say "tablet" outright, from any vendor: "Pixel Tablet", "Lenovo Tab
#: P12", "iPad"-style "Pad" names (Xiaomi Pad, OnePlus Pad).
_TABLET_WORDS = re.compile(r"\btablet\b|\btab\b|\bpad\b", re.IGNORECASE)


def _key(model: str | None) -> str:
    return " ".join((model or "").split()).upper()


@lru_cache(maxsize=1)
def catalog() -> dict:
    """The catalogue, loaded once. Empty, never an error, if the file is missing."""
    try:
        return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"devices": {}}


def lookup(model: str | None) -> dict | None:
    """The catalogue's entry for this `Build.MODEL` (brand, name, type), or None."""
    key = _key(model)
    return catalog().get("devices", {}).get(key) if key else None


def _by_rule(name: str) -> str | None:
    samsung = _SAMSUNG.match(name)
    if samsung:
        letter = samsung.group(1).upper()
        if letter in _SAMSUNG_TABLET:
            return TABLET
        if letter in _SAMSUNG_PHONE:
            return SMARTPHONE
        return None

    if _TABLET_WORDS.search(name):
        return TABLET
    # Google's phones are "Pixel <n>"; its tablet says so, and was caught above.
    if re.match(r"^pixel\b", name, re.IGNORECASE):
        return SMARTPHONE
    return None


def classify(model: str | None) -> str | None:
    """SMARTPHONE, TABLET, or None when neither the catalogue nor a rule covers it."""
    name = (model or "").strip()
    if not name:
        return None
    entry = lookup(name)
    if entry is not None:
        return entry["type"]
    return _by_rule(name)


def label(model: str | None) -> str:
    """For display: the type, or "Unknown"."""
    return classify(model) or "Unknown"
