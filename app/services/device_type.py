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

"""Smartphone or tablet, from the model the device reports (W310).

Operator, 2026-10-02: "add a category to the devices: device type. it should be
smartphone or tablet, and be based on the device models."

⚠️ **Rules, not a guess.** A model this module has no rule for is reported as
unknown (None), never forced into one bucket. The tempting fallback would be
`has_telephony`, and it's wrong: LTE tablets have a cellular radio, so it would
call them phones. A new model family gets a rule here.

Samsung is the fleet today, and its model numbers encode the form factor in the
letter after `SM-`. Other vendors are covered only where the name says so.
"""

from __future__ import annotations

import re

SMARTPHONE = "Smartphone"
TABLET = "Tablet"

#: Samsung's form factor is the letter after "SM-": T, X and P are Galaxy Tab
#: lines; S, G, A, M, N, F and E are phones (Galaxy S, XCover and older S, A, M,
#: Note, Fold/Flip, and F/E-series). Watches (R) and anything else stay unknown.
_SAMSUNG = re.compile(r"^SM-([A-Z])", re.IGNORECASE)
_SAMSUNG_TABLET = frozenset("TXP")
_SAMSUNG_PHONE = frozenset("SGAMNFE")

#: Names that say "tablet" outright, from any vendor: "Pixel Tablet", "Lenovo Tab
#: P12", "iPad"-style "Pad" names (Xiaomi Pad, OnePlus Pad).
_TABLET_WORDS = re.compile(r"\btablet\b|\btab\b|\bpad\b", re.IGNORECASE)


def classify(model: str | None) -> str | None:
    """SMARTPHONE, TABLET, or None when no rule covers the model."""
    name = (model or "").strip()
    if not name:
        return None

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


def label(model: str | None) -> str:
    """For display: the type, or "Unknown"."""
    return classify(model) or "Unknown"
