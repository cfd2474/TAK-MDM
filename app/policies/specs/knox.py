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
from app.policies.specs.knox_controls import (
    KnoxAppControlFields,
    KnoxBatteryFields,
    KnoxDateTimeFields,
    KnoxDeviceFields,
    KnoxFirmwareFields,
    KnoxHardwareKeyFields,
    KnoxKeyboardFields,
    KnoxLockScreenFields,
    KnoxLockStorageFields,
    KnoxNotificationFields,
    KnoxRadioSilenceFields,
    KnoxSoundFields,
    KnoxRadioFields,
    KnoxRoamingFields,
    KnoxUsbFields,
)
from app.policies.specs.knox_data_blocking import KnoxDataBlockingFields
from app.policies.specs.knox_domain_filter import KnoxDomainFilterFields
from app.policies.specs.knox_ip_rules import KnoxIpRuleFields
from app.policies.strategies import Merge, MergeStrategy

_FONTS = "Fonts"
_ANIMATION = "Boot/shutdown animation"
_POWER = "Power and USB"
_UPDATES = "OS updates"
KNOX = "Knox"
_TIME = r"^([01][0-9]|2[0-3]):[0-5][0-9]$"


class UsbConnectionType(enum.IntEnum):
    """Samsung's `CustomDeviceManager.USB_CONNECTION_TYPE_*` values (W466a)."""

    DEFAULT = 0
    MTP = 1
    PTP = 2
    MIDI = 3
    CHARGING_ONLY = 4


class KnoxCoreFields(PolicySpec):
    """The category's first pages: fonts, animation, power and USB, OS updates."""

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

    # --- Power and USB (W466a) -------------------------------------------- #

    auto_startup: Annotated[bool | None, Merge(MergeStrategy.HIGHEST_RANK)] = Field(
        default=None,
        title="Start up when USB power is connected",
        description=(
            "The device starts fully when power reaches its USB port, instead of only "
            "showing the charging screen — for tablets mounted in a vehicle or a case. "
            "Samsung: on every chipset from Android 13."
        ),
        json_schema_extra={"ui_group": _POWER, "ui_oem": KNOX, "ui_true": "On", "ui_false": "Off"},
    )

    auto_shutdown_on_usb_removal: Annotated[bool | None, Merge(MergeStrategy.HIGHEST_RANK)] = Field(
        default=None,
        title="Shut down when USB power is removed",
        description="The device turns off when its USB power is disconnected, e.g. when the vehicle stops.",
        json_schema_extra={"ui_group": _POWER, "ui_oem": KNOX, "ui_true": "On", "ui_false": "Off"},
    )

    usb_connection_type: Annotated[UsbConnectionType | None, Merge(MergeStrategy.HIGHEST_RANK)] = Field(
        default=None,
        title="USB connection type",
        description=(
            "What the device offers a computer it is plugged into. Charging only offers "
            "nothing but power. To forbid file transfer altogether, use Restrictions."
        ),
        json_schema_extra={"ui_group": _POWER, "ui_oem": KNOX, "ui_choice_labels": {
            "DEFAULT": "Device default", "MTP": "MTP (file transfer)", "PTP": "PTP (photo transfer)",
            "MIDI": "MIDI", "CHARGING_ONLY": "Charging only"}},
    )

    # --- OS updates ------------------------------------------------------- #
    # W481: the standard Android schedule moved to Restrictions › OS updates
    # (it is not Knox, and must work with Knox off). Samsung's own switches stay.

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
    def _the_schedule_says_one_thing(self) -> "KnoxCoreFields":
        """The animation's parts go together (the schedule's rules moved with it
        to Restrictions, W481)."""
        problems = []
        boot = (self.boot_animation_file_id, self.boot_loop_file_id)
        if (boot[0] is None) != (boot[1] is None):
            problems.append("the boot animation needs both the boot animation and the boot loop")
        if boot[0] is None and (self.boot_sound_file_id or self.boot_sound_delay_ms is not None):
            problems.append("a boot sound or its delay needs the boot animation")
        if self.shutdown_animation_file_id is None and self.shutdown_sound_file_id:
            problems.append("a shutdown sound needs the shutdown animation")
        if problems:
            raise ValueError("; ".join(problems))
        return self


class KnoxSpec(
    KnoxHardwareKeyFields,
    KnoxLockStorageFields,
    KnoxRadioSilenceFields,
    KnoxIpRuleFields,
    KnoxDomainFilterFields,
    KnoxDataBlockingFields,
    KnoxUsbFields,
    KnoxDeviceFields,
    KnoxRoamingFields,
    KnoxRadioFields,
    KnoxAppControlFields,
    KnoxBatteryFields,
    KnoxNotificationFields,
    KnoxKeyboardFields,
    KnoxSoundFields,
    KnoxLockScreenFields,
    KnoxDateTimeFields,
    KnoxFirmwareFields,
    KnoxCoreFields,
):
    """Knox Configurations (W468): every Knox item, one sub-page per group.

    ⚠️ **Bases are listed in reverse page order.** Pydantic collects fields from
    the last base first, so `KnoxCoreFields` (fonts ... OS updates) comes first
    in the editor and Data blocking last.
    """
