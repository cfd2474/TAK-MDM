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

"""NETWORK_DATA_USE policy spec — watch the data, and (later) act on it.

Two sub-sections, matching how an operator thinks about this: what the *device*
uses, and what a *particular app* uses.

⚠️ **The watching half works today; the acting half does not exist in AOSP.**
Reading usage is unusually generous to us — `NetworkStatsManager` grants a Device
Owner access to every app's usage with no permission prompt at all. Enforcing a
limit is the opposite: there is no Device Owner API to block Wi-Fi data, block
mobile data, or cut one app off the network. The API Settings itself uses for
per-app metered-data policy (`NetworkPolicyManager.setUidPolicy`) is `@hide` and
`@SystemApi`, and the `DISALLOW_*` family governs only whether the *user* may
change a setting, not whether bytes flow. See the Android reference §W43.

So the blocking fields are declared here — the shape is known and Knox will fill
it in (KNOX.md §4.1, `net.firewall.Firewall`) — but they are marked
``ui_requires`` and **refused at validation**. Declaring them keeps one source of
truth for the form; refusing them keeps an operator from saving a restriction that
would quietly never happen. Inert-but-saved is the one outcome worth ruling out:
a limit believed to be in force is worse than no limit at all.
"""

from __future__ import annotations

import enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy

_USAGE = "Data usage restrictions"
_APP_WISE = "App-wise restrictions"

#: Shown on any control the platform cannot honour yet, and in the refusal below.
KNOX = "Knox"

_PACKAGE_PATTERN = r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$"


class NetworkRestriction(enum.IntEnum):
    NONE = 0
    BLOCK_WIFI = 1
    BLOCK_MOBILE = 2
    BLOCK_ALL = 3


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

    network_restriction: Annotated[
        NetworkRestriction | None, Merge(MergeStrategy.MAX)
    ] = Field(
        default=None,
        title="Network restrictions",
        description=(
            "Block Wi-Fi data, mobile data, or all connections. No AOSP Device "
            "Owner API can do this — the DISALLOW_* restrictions only stop the "
            "user changing settings, and the per-app policy API Settings uses is "
            "@hide/@SystemApi. Needs the Knox firewall."
        ),
        json_schema_extra={"ui_group": _USAGE, "ui_requires": KNOX},
    )

    restrict_rules: Annotated[
        list[UsageRule] | None, Merge(MergeStrategy.UNION)
    ] = Field(
        default=None,
        title="Data usage restrictions",
        description=(
            "Cut the device off when usage crosses a threshold. Same wall as the "
            "network restrictions above: notifying is possible today, enforcing is "
            "not."
        ),
        json_schema_extra={
            "ui_group": _USAGE,
            "ui_control": "usage_rules",
            "ui_requires": KNOX,
        },
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
            "Cut one app off the network, on its own or past a threshold. This is "
            "exactly what Knox's firewall does per package, and exactly what AOSP "
            "offers no route to at all."
        ),
        json_schema_extra={
            "ui_group": _APP_WISE,
            "ui_control": "app_usage_rules",
            "ui_requires": KNOX,
        },
    )

    @model_validator(mode="after")
    def _refuse_what_cannot_be_enforced(self) -> "NetworkDataUseSpec":
        """Reject a value for any field the device cannot act on.

        The alternative — storing it against the day Knox lands — would hand an
        operator a policy that saves, assigns, reports no error, and never
        restricts anything. A data cap wrongly believed to be in force is worse
        than a visibly absent one, so this fails loudly instead.
        """
        blocked = [
            name
            for name in ("network_restriction", "restrict_rules", "app_restrict_rules")
            if getattr(self, name) is not None
        ]
        if blocked:
            raise ValueError(
                f"{', '.join(blocked)} cannot be enforced by an AOSP Device Owner and "
                f"needs {KNOX} (see the Android platform reference). Data usage "
                f"tracking and notifications work today; blocking does not, so it is "
                f"refused here rather than saved and silently ignored on the device"
            )
        return self
