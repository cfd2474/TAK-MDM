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

"""PASSWORD policy spec."""

from __future__ import annotations

import enum
from typing import Annotated

from pydantic import Field

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy


class PasswordQuality(enum.IntEnum):
    """Ordered so that MAX means 'the strictest requirement anyone asked for'."""

    NONE = 0
    SOMETHING = 1
    NUMERIC = 2
    NUMERIC_COMPLEX = 3
    ALPHABETIC = 4
    ALPHANUMERIC = 5
    COMPLEX = 6


_STRENGTH = "Strength"
_LOCKOUT = "Lockout & expiry"


class PasswordSpec(PolicySpec):
    quality: Annotated[
        PasswordQuality | None,
        Merge(MergeStrategy.MAX, note="Integer-ordered; MAX selects the strictest."),
    ] = Field(
        default=None,
        title="Password quality",
        description="Minimum complexity class the passcode must meet.",
        json_schema_extra={"ui_group": _STRENGTH},
    )

    min_length: Annotated[int | None, Merge(MergeStrategy.MAX)] = Field(
        default=None, ge=0, le=16, title="Minimum length",
        json_schema_extra={"ui_group": _STRENGTH},
    )
    # Any of these three forces the passcode to "Complex" quality on the device
    # (the granular DPM setters require PASSWORD_QUALITY_COMPLEX or they throw),
    # regardless of what `quality` is set to.
    min_letters: Annotated[int | None, Merge(MergeStrategy.MAX)] = Field(
        default=None, ge=0, le=16, title="Minimum letters",
        description="At least this many letters. Forces a complex passcode.",
        json_schema_extra={"ui_group": _STRENGTH},
    )
    min_digits: Annotated[int | None, Merge(MergeStrategy.MAX)] = Field(
        default=None, ge=0, le=16, title="Minimum digits",
        description="At least this many digits. Forces a complex passcode.",
        json_schema_extra={"ui_group": _STRENGTH},
    )
    min_symbols: Annotated[int | None, Merge(MergeStrategy.MAX)] = Field(
        default=None, ge=0, le=16, title="Minimum symbols",
        description="At least this many symbols. Forces a complex passcode.",
        json_schema_extra={"ui_group": _STRENGTH},
    )
    history_length: Annotated[int | None, Merge(MergeStrategy.MAX)] = Field(
        default=None, ge=0, le=50, title="Password history",
        description="How many previous passcodes cannot be reused.",
        json_schema_extra={"ui_group": _STRENGTH},
    )

    # Lower is stricter for these three, hence MIN.
    expiration_days: Annotated[int | None, Merge(MergeStrategy.MIN)] = Field(
        default=None, ge=1, le=730, title="Expiry",
        description="Days before the passcode must be changed (1–730).",
        json_schema_extra={"ui_group": _LOCKOUT, "ui_unit": "days"},
    )
    max_failed_attempts_before_wipe: Annotated[int | None, Merge(MergeStrategy.MIN)] = Field(
        default=None, ge=1, le=100, title="Failed attempts before wipe",
        json_schema_extra={"ui_group": _LOCKOUT},
    )
    lock_timeout_seconds: Annotated[int | None, Merge(MergeStrategy.MIN)] = Field(
        default=None, ge=15, le=86_400, title="Auto-lock timeout",
        description="Seconds of inactivity before the device locks (15–86400).",
        json_schema_extra={"ui_group": _LOCKOUT, "ui_unit": "seconds"},
    )
