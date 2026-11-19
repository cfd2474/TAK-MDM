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

"""Knox Configurations › Data blocking (W465, moved here from Network data use by W468).

⚠️ **Watching works on every device; blocking works only with Knox.** There is
no AOSP Device Owner API to block Wi-Fi data, block mobile data, or cut one app
off the network (`NetworkPolicyManager.setUidPolicy` is `@hide` and
`@SystemApi`; the `DISALLOW_*` family governs only whether the *user* may change
a setting). See the Android reference §W43. The Knox firewall
(`net.firewall.Firewall`, KNOX.md §4.1) does it, and a device without Knox
**reports** that it does not, on the device page.

⚠️ **The usage-limit blocks count usage the way Network data use tracks it.**
Their period ends at that policy's reset time and day, and with tracking off
there is no reading to cross. The agent reads both sections together.

⚠️ **The ATLAS agent is never blocked.** The agent always adds an ALLOW rule for
itself (Samsung: "allow rules take precedence over deny rules"), so a block can
never cut a device off from the console that would lift it. Naming the agent in
a block is refused here, because it would say something that cannot happen.
"""

from __future__ import annotations

import enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.policies.specs.base import PolicySpec
from app.policies.specs.kiosk import ATLAS_CONSOLE_PACKAGE
from app.policies.specs.network_data_use import AppUsageRule, UsageRule
from app.policies.strategies import Merge, MergeStrategy

KNOX = "Knox"
_DEVICE = "Data blocking"
_APPS = "App data blocking"
_PACKAGE_PATTERN = r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$"
_TRACKING = " Usage is counted as Network data use tracks it, so tracking must be on there."


class BlockNetwork(enum.IntEnum):
    """Which network an app is always blocked on (W465). Mirrored by the agent."""

    WIFI = 1
    MOBILE = 2
    ALL = 3


class AppBlock(BaseModel):
    """One app blocked on a network whatever it has used (W465)."""

    model_config = ConfigDict(extra="forbid")

    package_name: str = Field(pattern=_PACKAGE_PATTERN)
    network: BlockNetwork = BlockNetwork.ALL


class KnoxDataBlockingFields(PolicySpec):
    block_wifi: Annotated[bool | None, Merge(MergeStrategy.MAX)] = Field(
        default=None,
        title="Block Wi-Fi data",
        description="Block every app's Wi-Fi data, except the always allowed apps below.",
        # ⚠️ MAX, not MOST_RESTRICTIVE. MOST_RESTRICTIVE is "every policy must
        # allow it", so a False beats a True — right for a switch that permits,
        # wrong for one that blocks. One policy blocking is a block (W465).
        json_schema_extra={"ui_group": _DEVICE, "ui_oem": KNOX,
                           "ui_true": "Blocked", "ui_false": "Not blocked"},
    )

    block_mobile: Annotated[bool | None, Merge(MergeStrategy.MAX)] = Field(
        default=None,
        title="Block mobile data",
        description="Block every app's mobile data, except the always allowed apps below.",
        json_schema_extra={"ui_group": _DEVICE, "ui_oem": KNOX,
                           "ui_true": "Blocked", "ui_false": "Not blocked"},
    )

    restrict_rules: Annotated[list[UsageRule] | None, Merge(MergeStrategy.UNION)] = Field(
        default=None,
        title="Data usage restrictions",
        description=(
            "Block that data for every app, except the always allowed apps, once the "
            "device's usage crosses a threshold. Checked at each check-in; the block "
            "lifts when the period resets." + _TRACKING
        ),
        json_schema_extra={"ui_group": _DEVICE, "ui_control": "usage_rules", "ui_oem": KNOX},
    )

    allowed_apps: Annotated[
        list[Annotated[str, Field(pattern=_PACKAGE_PATTERN)]] | None,
        Merge(MergeStrategy.UNION),
    ] = Field(
        default=None,
        title="Always allowed apps",
        description=(
            "Apps that keep their data when the device is blocked, for example ATAK "
            "on mobile data. The ATLAS agent is always allowed and need not be listed. "
            "An app here is never blocked, so it cannot also be in an app data block."
        ),
        json_schema_extra={"ui_group": _DEVICE, "ui_control": "package_list", "ui_oem": KNOX,
                           "ui_library_picker": True},
    )

    app_restrict_rules: Annotated[list[AppUsageRule] | None, Merge(MergeStrategy.UNION)] = Field(
        default=None,
        title="Per-app data usage restrictions",
        description=(
            "Block one app's data once its own usage crosses a threshold. Checked at "
            "each check-in; the block lifts when the period resets." + _TRACKING
        ),
        json_schema_extra={"ui_group": _APPS, "ui_control": "app_usage_rules", "ui_oem": KNOX},
    )

    app_block_rules: Annotated[list[AppBlock] | None, Merge(MergeStrategy.UNION)] = Field(
        default=None,
        title="Always blocked apps",
        description="Block one app on Wi-Fi, mobile data or both, whatever it has used.",
        json_schema_extra={"ui_group": _APPS, "ui_control": "app_blocks", "ui_oem": KNOX},
    )

    @model_validator(mode="after")
    def _blocks_say_only_what_can_happen(self) -> "KnoxDataBlockingFields":
        """Refuse a block the device would not carry out (W465).

        Two cases. The ATLAS agent always keeps its data, so a block naming it
        is a promise the device breaks. And an always allowed app wins over any
        block of the same app (Knox: allow beats deny), so naming one app in
        both says two things and only one of them happens.
        """
        blocked = {r.package_name for r in self.app_restrict_rules or []}
        blocked |= {r.package_name for r in self.app_block_rules or []}
        problems = []
        if ATLAS_CONSOLE_PACKAGE in blocked:
            problems.append(
                f"{ATLAS_CONSOLE_PACKAGE} is the ATLAS agent, which is never blocked: "
                f"blocking it would cut the device off from ATLAS"
            )
        both = sorted(blocked & set(self.allowed_apps or []))
        if both:
            problems.append(
                f"{', '.join(both)} cannot be both always allowed and blocked: "
                f"an always allowed app is never blocked"
            )
        if problems:
            raise ValueError("; ".join(problems))
        return self


#: What the W468 migration strips from stored NETWORK_DATA_USE specs.
MOVED_FROM = {"NETWORK_DATA_USE": tuple(KnoxDataBlockingFields.model_fields)}
