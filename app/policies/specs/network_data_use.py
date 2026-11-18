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

⚠️ **Blocking is not here any more (W468).** It needs Knox, and the operator
asked for every Knox item to live in Knox Configurations, so the blocks are
Knox Configurations › Data blocking (`knox_data_blocking`). They still count
usage the way this policy tracks it: its reset time and day, and only while
tracking is on. A device with no tracking has no reading to cross.
"""

from __future__ import annotations

import enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy

_USAGE = "Data usage restrictions"
_APP_WISE = "App-wise restrictions"

_PACKAGE_PATTERN = r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$"


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

    # --- App-wise restrictions --------------------------------------------- #

    app_notify_rules: Annotated[
        list[AppUsageRule] | None, Merge(MergeStrategy.UNION)
    ] = Field(
        default=None,
        title="Per-app data usage notifications",
        description=(
            "Warn when one app's own usage crosses a threshold. Per-app usage is "
            "readable on every device."
        ),
        json_schema_extra={"ui_group": _APP_WISE, "ui_control": "app_usage_rules"},
    )
