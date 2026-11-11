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

"""SYSTEM_CONFIG policy spec — the Knox Configurations category (W322, W465 K2b).

⚠️ **The type is not called KNOX**, though the category is. Its section reaches
the agent's shared code, which is compiled into the AOSP artifact, and
`verifyAospHasNoKnox` fails a build whose dex holds the word (W226). The OS
update schedule in it is not Knox anyway.

The operator put fonts, the boot and shutdown animation, and OS updates here
"as these are part of the knox requirements". Read against the SDK 3.14
reference, they are three different things:

* **Fonts** (`display.Font`) are Knox only, and only fonts already on the device:
  📖 "Form Android version 4.2 onwards, this API will not support font apk
  installation". The list differs per device, so devices report theirs and the
  editor offers what they reported, beside a box to type a name.
* **The boot and shutdown animation** is 📖 deprecated in API level 38, in
  Samsung's `.qmg` format only. The agent's probe answered `SUCCESS (0)` on the
  SM-X520 (2026-11-10), so it is offered (K2b-4). 📖 Operators cannot make `.qmg`
  files with Samsung's tools: Samsung converts PNG frames sent through a Knox
  Admin Portal support ticket. Sound is OGG.
* **OS updates** need no Knox for the schedule: `setSystemUpdatePolicy` is
  standard Android for a Device Owner. The operator asked for both routes "in
  case samsung handles it differently", so the two Knox switches sit beside it
  and carry the "Samsung Knox only" mark; the schedule does not.
"""

from __future__ import annotations

import enum
import uuid
from typing import Annotated

from pydantic import Field, model_validator

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy

_FONTS = "Fonts"
_ANIMATION = "Boot/shutdown animation"
_UPDATES = "OS updates"
KNOX = "Knox"
_TIME = r"^([01][0-9]|2[0-3]):[0-5][0-9]$"


class OsUpdateMode(enum.IntEnum):
    """`SystemUpdatePolicy`'s three kinds. Mirrored by the agent."""

    AUTOMATIC = 1
    DAILY_WINDOW = 2
    POSTPONE_30_DAYS = 3


class KnoxSpec(PolicySpec):
    # --- Fonts ------------------------------------------------------------ #

    font_name: Annotated[str | None, Merge(MergeStrategy.HIGHEST_RANK)] = Field(
        default=None,
        min_length=1,
        max_length=128,
        title="Font",
        description=(
            "The font the device uses everywhere. Only fonts already on the device "
            "can be chosen; a device without this font keeps its own and says so. "
            "Pick one that devices reported (each shows the devices that have it), "
            "or type its name."
        ),
        json_schema_extra={"ui_group": _FONTS, "ui_control": "font_name", "ui_oem": KNOX},
    )

    font_size_percent: Annotated[int | None, Merge(MergeStrategy.HIGHEST_RANK)] = Field(
        default=None,
        ge=50,
        le=200,
        title="Font size",
        description=(
            "100% is the normal size. Each device uses the nearest size it supports."
        ),
        json_schema_extra={"ui_group": _FONTS, "ui_unit": "%", "ui_oem": KNOX},
    )

    # --- Boot/shutdown animation (K2b-4) ------------------------------------ #

    boot_animation_file_id: Annotated[uuid.UUID | None, Merge(MergeStrategy.HIGHEST_RANK)] = Field(
        default=None,
        title="Boot animation",
        description=(
            "Plays once when the device starts; the device names it bootup.qmg. Needs the "
            "boot loop too. Make one in Content > Boot/shutdown animations."
        ),
        json_schema_extra={"ui_group": _ANIMATION, "ui_control": "animation_pick",
                           "ui_animation_role": "boot", "ui_oem": KNOX},
    )

    boot_loop_file_id: Annotated[uuid.UUID | None, Merge(MergeStrategy.HIGHEST_RANK)] = Field(
        default=None,
        title="Boot loop",
        description=(
            "Repeats after the boot animation until the device is ready; the device names "
            "it bootloop.qmg. Choosing a boot animation picks its loop."
        ),
        json_schema_extra={"ui_group": _ANIMATION, "ui_control": "animation_pick",
                           "ui_animation_role": "bootloop", "ui_oem": KNOX},
    )

    boot_sound_file_id: Annotated[uuid.UUID | None, Merge(MergeStrategy.HIGHEST_RANK)] = Field(
        default=None,
        title="Boot sound",
        description="Optional. An OGG file, played with the boot animation. Without one, the device uses a silent sound (Samsung requires a sound).",
        json_schema_extra={"ui_group": _ANIMATION, "ui_control": "animation_file", "ui_oem": KNOX},
    )

    boot_sound_delay_ms: Annotated[int | None, Merge(MergeStrategy.HIGHEST_RANK)] = Field(
        default=None,
        ge=0,
        le=60000,
        title="Boot sound delay",
        description="How long after the animation starts the sound plays. 0 is at once.",
        json_schema_extra={"ui_group": _ANIMATION, "ui_unit": "ms", "ui_oem": KNOX},
    )

    shutdown_animation_file_id: Annotated[uuid.UUID | None, Merge(MergeStrategy.HIGHEST_RANK)] = Field(
        default=None,
        title="Shutdown animation",
        description=(
            "Plays when the device shuts down; the device names it shutdown.qmg. Make one "
            "in Content > Boot/shutdown animations."
        ),
        json_schema_extra={"ui_group": _ANIMATION, "ui_control": "animation_pick",
                           "ui_animation_role": "shutdown", "ui_oem": KNOX},
    )

    shutdown_sound_file_id: Annotated[uuid.UUID | None, Merge(MergeStrategy.HIGHEST_RANK)] = Field(
        default=None,
        title="Shutdown sound",
        description="Optional. An OGG file, played with the shutdown animation. Without one, the device uses a silent sound (Samsung requires a sound).",
        json_schema_extra={"ui_group": _ANIMATION, "ui_control": "animation_file", "ui_oem": KNOX},
    )

    # --- OS updates ------------------------------------------------------- #

    os_update_mode: Annotated[OsUpdateMode | None, Merge(MergeStrategy.HIGHEST_RANK)] = Field(
        default=None,
        title="When to install OS updates",
        description=(
            "Automatic installs an update as soon as it is ready. Daily window installs "
            "it only between the two times below. Postpone holds it for up to 30 days. "
            "Standard Android: works on every device, Samsung included."
        ),
        json_schema_extra={"ui_group": _UPDATES},
    )

    os_update_window_start: Annotated[str | None, Merge(MergeStrategy.HIGHEST_RANK)] = Field(
        default=None,
        pattern=_TIME,
        title="Daily window starts",
        description="24-hour device time, e.g. 01:00. Only with Daily window.",
        json_schema_extra={"ui_group": _UPDATES},
    )

    os_update_window_end: Annotated[str | None, Merge(MergeStrategy.HIGHEST_RANK)] = Field(
        default=None,
        pattern=_TIME,
        title="Daily window ends",
        description="24-hour device time, e.g. 04:00. May be past midnight.",
        json_schema_extra={"ui_group": _UPDATES},
    )

    block_os_updates: Annotated[bool | None, Merge(MergeStrategy.MAX)] = Field(
        default=None,
        title="Block OS updates",
        description=(
            "Samsung's own switch: every over-the-air OS upgrade fails, whoever "
            "starts it. The user may still see that an update exists."
        ),
        # MAX: one policy blocking is a block, as for the data blocks (W465).
        json_schema_extra={"ui_group": _UPDATES, "ui_oem": KNOX,
                           "ui_true": "Blocked", "ui_false": "Not blocked"},
    )

    firmware_auto_update: Annotated[bool | None, Merge(MergeStrategy.HIGHEST_RANK)] = Field(
        default=None,
        title="Download OS updates automatically",
        description="Samsung's own Settings option to check for and download updates by itself.",
        json_schema_extra={"ui_group": _UPDATES, "ui_oem": KNOX,
                           "ui_true": "On", "ui_false": "Off"},
    )

    @model_validator(mode="after")
    def _the_schedule_says_one_thing(self) -> "KnoxSpec":
        """A window needs both ends and only goes with Daily window; and an
        install schedule beside "Block OS updates" would never be used."""
        window = (self.os_update_window_start, self.os_update_window_end)
        problems = []
        if self.os_update_mode is OsUpdateMode.DAILY_WINDOW:
            if None in window:
                problems.append("Daily window needs a start and an end time")
            elif window[0] == window[1]:
                problems.append("the daily window must not start and end at the same time")
        elif any(window):
            problems.append("a daily window start or end is only used with Daily window")
        boot = (self.boot_animation_file_id, self.boot_loop_file_id)
        if (boot[0] is None) != (boot[1] is None):
            problems.append("the boot animation needs both the boot animation and the boot loop")
        if boot[0] is None and (self.boot_sound_file_id or self.boot_sound_delay_ms is not None):
            problems.append("a boot sound or its delay needs the boot animation")
        if self.shutdown_animation_file_id is None and self.shutdown_sound_file_id:
            problems.append("a shutdown sound needs the shutdown animation")
        if self.block_os_updates and self.os_update_mode is not None:
            problems.append(
                "Block OS updates stops every update, so an install schedule would never be used"
            )
        if problems:
            raise ValueError("; ".join(problems))
        return self
