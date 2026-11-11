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

"""Knox Configurations' on/off controls and lists (W466b–d, moved here by W468).

Operator, 2026-11-11: *"anything knox related should live in this main
category, even if it relates to other categories."* These came from
Restrictions (Radios, Roaming, Device controls, USB and storage) and App
Management (battery optimization). Each group is its own small class, and
`KnoxSpec` is composed of them, so no one file holds every Knox field.

⚠️ **The field names did not change in the move.** The agent's switch keys,
the device's report and the device page labels all use them; only the policy
type that carries them did.

⚠️ Standard Android items stayed where they were (airplane mode, status bar,
add users, backup, force stop and clear data): they are not Knox.
"""

from __future__ import annotations

import enum
from typing import Annotated

from pydantic import Field

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy

KNOX = "Knox"
_DENY_WINS = Merge(MergeStrategy.MOST_RESTRICTIVE)
_RANK_WINS = Merge(MergeStrategy.HIGHEST_RANK)

_BATTERY = "Battery optimization"
_RADIOS = "Radios"
_ROAMING = "Roaming"
_DEVICE = "Device controls"
_USB = "USB and storage"
_DATE = "Date and time"

_PACKAGE = r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$"


def _allow(title: str, group: str, description: str = ""):
    """A Knox allow-boolean: Allowed / Blocked, merged so a block wins."""
    return Field(default=None, title=title, description=description, json_schema_extra={
        "ui_group": group, "ui_true": "Allowed", "ui_false": "Blocked", "ui_oem": KNOX})


class UsbClass(str, enum.Enum):
    """A USB device class Samsung Knox can let through (W466d). The values are
    Knox's own `RestrictionPolicy.USBInterface` names; the agent turns them into
    Samsung's bits, so the server never holds a bit value that could drift."""

    AUD = "AUD"
    CDC = "CDC"
    COM = "COM"
    HID = "HID"
    MAS = "MAS"
    MIS = "MIS"
    STI = "STI"
    VEN = "VEN"
    WIR = "WIR"


class TimeFormat(str, enum.Enum):
    """`DateTimePolicy.setTimeFormat`'s two values (W466e)."""

    H12 = "12"
    H24 = "24"


class KnoxDateTimeFields(PolicySpec):
    """W466e. 📖 `DateTimePolicy.setTimeFormat` is deprecated in API level 35;
    the probe on the SM-X520 (Android 16) answered true, so it still works.
    Android gives a Device Owner no way to set it."""

    time_format: Annotated[TimeFormat | None, _RANK_WINS] = Field(
        default=None,
        title="Time format",
        description=(
            "12-hour or 24-hour clock. ⚠️ Samsung marks this call deprecated: it "
            "works on current devices but may stop on a later Android. Removing it "
            "puts back the format the device had."
        ),
        json_schema_extra={"ui_group": _DATE, "ui_oem": KNOX,
                           "ui_choice_labels": {"H12": "12-hour", "H24": "24-hour"}},
    )


class KnoxBatteryFields(PolicySpec):
    battery_optimization_exceptions: Annotated[
        list[Annotated[str, Field(pattern=_PACKAGE)]] | None,
        Merge(MergeStrategy.UNION),
    ] = Field(
        default=None,
        title="Battery optimization exceptions",
        description=(
            "Apps Android never puts to sleep to save battery (Doze, app standby, power "
            "saving) — e.g. ATAK, so it keeps reporting in the background. Pick from the "
            "library or type a package name. An app not yet installed is added once it is."
        ),
        # W466a. Samsung's ApplicationPolicy; Android gives a Device Owner no way
        # to add an app to this list, only the user.
        json_schema_extra={"ui_group": _BATTERY, "ui_control": "package_list",
                           "ui_library_picker": True, "ui_oem": KNOX},
    )


class KnoxRadioFields(PolicySpec):
    """W466b. Airplane mode stayed in Restrictions: Android's own restriction."""

    allow_cellular_data: Annotated[bool | None, _DENY_WINS] = _allow(
        "Cellular data", _RADIOS,
        "Blocked: mobile data is turned off and cannot be turned on. ⚠️ A tablet with "
        "no Wi-Fi then has no way to reach ATLAS to lift it.")
    allow_bluetooth_discoverable: Annotated[bool | None, _DENY_WINS] = _allow(
        "Bluetooth discoverable", _RADIOS,
        "Blocked: other devices cannot find this one over Bluetooth; paired devices still work.")
    allow_tethering: Annotated[bool | None, _DENY_WINS] = _allow(
        "Hotspot and tethering", _RADIOS,
        "Blocked: the device cannot share its connection — Wi-Fi hotspot, USB or Bluetooth tethering.")
    allow_usb_tethering: Annotated[bool | None, _DENY_WINS] = _allow(
        "USB tethering", _RADIOS,
        "Blocked: the device cannot share its connection over USB. Other tethering is "
        "not affected.")


class KnoxRoamingFields(PolicySpec):
    """W466b, Samsung `RoamingPolicy`."""

    allow_data_roaming: Annotated[bool | None, _DENY_WINS] = _allow(
        "Data while roaming", _ROAMING, "Mobile data on another operator's network.")
    allow_roaming_push: Annotated[bool | None, _DENY_WINS] = _allow(
        "WAP push while roaming", _ROAMING, "Operator push messages while roaming.")
    allow_roaming_sync: Annotated[bool | None, _DENY_WINS] = _allow(
        "Data sync while roaming", _ROAMING, "Apps syncing their accounts automatically while roaming.")
    allow_roaming_voice_calls: Annotated[bool | None, _DENY_WINS] = _allow(
        "Voice calls while roaming", _ROAMING, "Making and receiving calls while roaming.")


class KnoxDeviceFields(PolicySpec):
    """W466c, Samsung `RestrictionPolicy`. The standard Android device controls
    stayed in Restrictions › Device controls."""

    allow_power_off: Annotated[bool | None, _DENY_WINS] = _allow(
        "Power off", _DEVICE,
        "Blocked: the power menu cannot turn the device off. Restart still works, and "
        "so does a forced restart with the buttons.")
    allow_microphone: Annotated[bool | None, _DENY_WINS] = _allow(
        "Microphone", _DEVICE,
        "Blocked: no app can record sound, and calls have no audio from this device. "
        "⚠️ Push-to-talk in ATAK stops working.")
    allow_settings_changes: Annotated[bool | None, _DENY_WINS] = _allow(
        "Settings changes", _DEVICE,
        "Blocked: the user cannot change anything in the Settings app. ATLAS can still "
        "apply policy.")
    allow_clipboard: Annotated[bool | None, _DENY_WINS] = _allow(
        "Clipboard", _DEVICE, "Blocked: copy and paste do not work.")
    allow_share_list: Annotated[bool | None, _DENY_WINS] = _allow(
        "Share menu", _DEVICE, "Blocked: the Share menu (send to another app) does not open.")
    allow_smart_clip: Annotated[bool | None, _DENY_WINS] = _allow(
        "Smart select", _DEVICE, "Blocked: Samsung's Smart select (S Pen screen clipping) does not work.")


class KnoxUsbFields(PolicySpec):
    """W466d, Samsung `RestrictionPolicy`."""

    allow_usb_host_storage: Annotated[bool | None, _DENY_WINS] = _allow(
        "USB host (OTG)", _USB,
        "Blocked: nothing plugged into the device's USB port works — drives, card "
        "readers, keyboards, adapters. Charging still works. Samsung blocks all USB "
        "host use here, not only storage.")
    allow_sd_card_write: Annotated[bool | None, _DENY_WINS] = _allow(
        "SD card write", _USB,
        "Blocked: the SD card is read-only. ⚠️ An SD card the device has encrypted "
        "may ignore this on older Samsung software.")
    #: ⚠️ Higher rank wins, not a merge: Samsung blocks every class *not* listed,
    #: so an intersection of two policies could block every USB device.
    usb_allowed_classes: Annotated[list[UsbClass] | None, _RANK_WINS] = Field(
        default=None,
        title="Allowed USB devices",
        description=(
            "When set, only these kinds of USB device work; every other kind is "
            "blocked. USB hubs are always allowed. A device that is several kinds at "
            "once (a headset with buttons, say) needs each of its kinds ticked. Has no "
            "effect while USB host is Blocked."
        ),
        json_schema_extra={"ui_group": _USB, "ui_oem": KNOX, "ui_control": "enum_set",
                           "ui_choice_labels": {
                               "AUD": "Audio", "CDC": "Network and modem (CDC)",
                               "COM": "Communications (COM)", "HID": "Keyboard, mouse, game pad (HID)",
                               "MAS": "Storage", "MIS": "Miscellaneous", "STI": "Camera (still image)",
                               "VEN": "Vendor-specific", "WIR": "Wireless adapter (Bluetooth)"}},
    )


#: Every field this module adds to Knox Configurations, by the policy type it
#: came from — what the W468 migration strips from stored specs there.
MOVED_FROM = {
    "RESTRICTIONS": (
        *KnoxRadioFields.model_fields, *KnoxRoamingFields.model_fields,
        *KnoxDeviceFields.model_fields, *KnoxUsbFields.model_fields,
    ),
    "APP_CATALOG": tuple(KnoxBatteryFields.model_fields),
}
