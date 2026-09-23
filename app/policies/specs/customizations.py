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

"""CUSTOMIZATIONS policy spec — the operator's own words, shown on the device.

Three pieces of text the fleet's owner can put in front of whoever is holding the
device, each landing somewhere different in the OS (Android reference §W42):

* **Disabled setting message** — `setShortSupportMessage`. Appears at the moment
  a user taps something this MDM has turned off, which is the one moment they are
  most likely to think the device is broken. "Contact ops on channel 3" there is
  worth more than the same sentence anywhere else.
* **Admin app custom description** — `setLongSupportMessage`. Appears on the
  device-administrators screen, i.e. when someone goes looking for what this app
  is and why it has control.
* **Lock screen message** — `setDeviceOwnerLockScreenInfo`. Appears without anyone
  going looking, which makes it the right place for ownership and return-if-found
  text, and the wrong place for anything sensitive.

Every field is `HIGHEST_RANK`: two stacked policies cannot both have their say in
one sentence, so a clash is settled by rank rather than by concatenating text
nobody wrote. Length caps mirror the platform's documented truncation points, so
an over-long message is refused in the console instead of being silently cut on
the device.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy

_SUPPORT = "Support message"
_LOCK_SCREEN = "Lock screen"


class CustomizationsSpec(PolicySpec):
    disabled_setting_message: Annotated[
        str | None, Merge(MergeStrategy.HIGHEST_RANK)
    ] = Field(
        default=None,
        max_length=200,
        title="Disabled setting message",
        description=(
            "Shown when the user opens a setting this MDM has disabled. Name a way "
            "to get help — that screen is where someone decides the device is "
            "broken. Android truncates past 200 characters."
        ),
        json_schema_extra={"ui_group": _SUPPORT, "ui_control": "text"},
    )

    admin_app_description: Annotated[
        str | None, Merge(MergeStrategy.HIGHEST_RANK)
    ] = Field(
        default=None,
        max_length=20_000,
        title="Admin app custom description",
        description=(
            "Shown on the device-administrators settings screen, where someone "
            "looking into what this app is will find it. Say who manages the "
            "device and why."
        ),
        json_schema_extra={"ui_group": _SUPPORT, "ui_control": "text"},
    )

    lock_screen_message: Annotated[
        str | None, Merge(MergeStrategy.HIGHEST_RANK)
    ] = Field(
        default=None,
        max_length=200,
        title="Lock screen message",
        description=(
            "Shown on the lock screen, before anyone unlocks the device — good for "
            "ownership or return-if-found text, bad for anything sensitive. While "
            "this is set the user cannot change the lock screen owner info "
            "themselves; clearing it hands that back to them. "
            "Write {device} anywhere in the text and each device substitutes its "
            "own name — or its serial, if it has not been named — so one policy "
            "labels a whole fleet. The same token works in the support messages."
        ),
        json_schema_extra={"ui_group": _LOCK_SCREEN, "ui_control": "text"},
    )
