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

"""NETWORK_DATA_USE policy spec — watch the data, and block it on Samsung.

Two sub-sections, matching how an operator thinks about this: what the *device*
uses, and what a *particular app* uses.

⚠️ **Watching works on every device; blocking works only with Knox.** Reading
usage is unusually generous to us — `NetworkStatsManager` grants a Device Owner
access to every app's usage with no permission prompt at all. Enforcing a limit
is the opposite: there is no AOSP Device Owner API to block Wi-Fi data, block
mobile data, or cut one app off the network. The API Settings itself uses for
per-app metered-data policy (`NetworkPolicyManager.setUidPolicy`) is `@hide` and
`@SystemApi`, and the `DISALLOW_*` family governs only whether the *user* may
change a setting, not whether bytes flow. See the Android reference §W43.

So the blocking fields are carried out by the Knox firewall
(`net.firewall.Firewall`, KNOX.md §4.1), and marked ``ui_oem`` (W465). They used
to be refused at validation, because no device could enforce them. Now a Knox
device enforces them, and a device without Knox **reports** that it does not, on
the device page — so the policy saves, and an operator still never believes in a
block that is not there.

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
from app.policies.strategies import Merge, MergeStrategy

_USAGE = "Data usage restrictions"
_APP_WISE = "App-wise restrictions"

#: The OEM the blocking controls need. Shown beside each of them (W465).
KNOX = "Knox"

_PACKAGE_PATTERN = r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$"


class BlockNetwork(enum.IntEnum):
    """Which network an app is always blocked on (W465). Mirrored by the agent."""

    WIFI = 1
    MOBILE = 2
    ALL = 3


class UsagePeriod(enum.IntEnum):
    DAILY = 0
    WEEKLY = 1
    MONTHLY = 2


class UsageMetric(enum.IntEnum):
    MOBILE_DATA = 0
    WIFI_DATA = 1
    TOTAL_DATA = 2


class UsageRule(BaseModel):
    """One "when <metric> over <period> exceeds <n> MB" line."""

    model_config = ConfigDict(extra="forbid")

    period: UsagePeriod = UsagePeriod.MONTHLY
    metric: UsageMetric = UsageMetric.MOBILE_DATA
    # No upper bound: a 4 TB threshold is silly, not wrong, and inventing a
    # ceiling here would be this project deciding how big someone's plan may be.
    threshold_mb: int = Field(ge=1)


class AppUsageRule(UsageRule):
    """The same line, scoped to one app."""

    package_name: str = Field(pattern=_PACKAGE_PATTERN)


class AppBlock(BaseModel):
    """One app blocked on a network whatever it has used (W465)."""

    model_config = ConfigDict(extra="forbid")

    package_name: str = Field(pattern=_PACKAGE_PATTERN)
    network: BlockNetwork = BlockNetwork.ALL


class NetworkDataUseSpec(PolicySpec):
    # --- Data usage restrictions ------------------------------------------- #

    track_usage: Annotated[bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)] = Field(
        default=None,
        title="Enable data usage tracking",
        description=(
            "Record how much data the device and each app use, and report it back. "
            "A Device Owner may read this without asking the user for anything."
        ),
        json_schema_extra={"ui_group": _USAGE, "ui_true": "Tracked", "ui_false": "Not tracked"},
    )

    notify_rules: Annotated[
        list[UsageRule] | None, Merge(MergeStrategy.UNION)
    ] = Field(
        default=None,
        title="Data usage notifications",
        description=(
            "Tell the device user when usage crosses a threshold. Every stacked "
            "policy's thresholds apply, so a narrower policy adds a warning rather "
            "than replacing one."
        ),
        json_schema_extra={"ui_group": _USAGE, "ui_control": "usage_rules"},
    )

    reset_daily_at: Annotated[str | None, Merge(MergeStrategy.HIGHEST_RANK)] = Field(
        default=None,
        pattern=r"^([01][0-9]|2[0-3]):[0-5][0-9]$",
        title="Reset daily counters at",
        description="24-hour local time, e.g. 00:00. Leave unset to reset at midnight.",
        json_schema_extra={"ui_group": _USAGE},
    )

    reset_monthly_on_day: Annotated[int | None, Merge(MergeStrategy.HIGHEST_RANK)] = Field(
        default=None,
        ge=1,
        le=28,
        title="Reset monthly counters on day",
        description=(
            "Day of the month the billing period restarts. Capped at 28 so the "
            "cycle exists in February — a 31st that silently skips short months "
            "is a counter that never resets."
        ),
        json_schema_extra={"ui_group": _USAGE},
    )

    block_wifi: Annotated[bool | None, Merge(MergeStrategy.MAX)] = Field(
        default=None,
        title="Block Wi-Fi data",
        description=(
            "Block every app's Wi-Fi data, except the always allowed apps below. "
            "No AOSP Device Owner API can do this: the DISALLOW_* restrictions only "
            "stop the user changing settings. Done with the Knox firewall."
        ),
        # ⚠️ MAX, not MOST_RESTRICTIVE. MOST_RESTRICTIVE is "every policy must
        # allow it", so a False beats a True — right for a switch that permits,
        # wrong for one that blocks. One policy blocking is a block (W465).
        json_schema_extra={"ui_group": _USAGE, "ui_oem": KNOX,
                           "ui_true": "Blocked", "ui_false": "Not blocked"},
    )

    block_mobile: Annotated[bool | None, Merge(MergeStrategy.MAX)] = Field(
        default=None,
        title="Block mobile data",
        description=(
            "Block every app's mobile data, except the always allowed apps below. "
            "Done with the Knox firewall."
        ),
        json_schema_extra={"ui_group": _USAGE, "ui_oem": KNOX,
                           "ui_true": "Blocked", "ui_false": "Not blocked"},
    )

    restrict_rules: Annotated[
        list[UsageRule] | None, Merge(MergeStrategy.UNION)
    ] = Field(
        default=None,
        title="Data usage restrictions",
        description=(
            "Block that data for every app, except the always allowed apps, once the "
            "device's usage crosses a threshold. Checked at each check-in; the block "
            "lifts when the period resets. Done with the Knox firewall."
        ),
        json_schema_extra={
            "ui_group": _USAGE,
            "ui_control": "usage_rules",
            "ui_oem": KNOX,
        },
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
            "An app here is never blocked, so it cannot also be in an app-wise block."
        ),
        json_schema_extra={"ui_group": _USAGE, "ui_control": "package_list", "ui_oem": KNOX},
    )

    # --- App-wise restrictions --------------------------------------------- #

    app_notify_rules: Annotated[
        list[AppUsageRule] | None, Merge(MergeStrategy.UNION)
    ] = Field(
        default=None,
        title="Per-app data usage notifications",
        description=(
            "Warn when one app's own usage crosses a threshold. Per-app usage is "
            "readable today, so these work; the restrictions below do not."
        ),
        json_schema_extra={"ui_group": _APP_WISE, "ui_control": "app_usage_rules"},
    )

    app_restrict_rules: Annotated[
        list[AppUsageRule] | None, Merge(MergeStrategy.UNION)
    ] = Field(
        default=None,
        title="Per-app data usage restrictions",
        description=(
            "Block one app's data once its own usage crosses a threshold. Checked at "
            "each check-in; the block lifts when the period resets. Done with the "
            "Knox firewall, per package."
        ),
        json_schema_extra={
            "ui_group": _APP_WISE,
            "ui_control": "app_usage_rules",
            "ui_oem": KNOX,
        },
    )

    app_block_rules: Annotated[
        list[AppBlock] | None, Merge(MergeStrategy.UNION)
    ] = Field(
        default=None,
        title="Always blocked apps",
        description=(
            "Block one app on Wi-Fi, mobile data or both, whatever it has used. "
            "Done with the Knox firewall, per package."
        ),
        json_schema_extra={"ui_group": _APP_WISE, "ui_control": "app_blocks", "ui_oem": KNOX},
    )

    @model_validator(mode="after")
    def _blocks_say_only_what_can_happen(self) -> "NetworkDataUseSpec":
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
