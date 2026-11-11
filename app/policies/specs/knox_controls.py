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

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
_LOCK = "Lock screen"
_SOUND = "Sounds and vibration"
_KEYBOARD = "Keyboard"
_NOTIFY = "Notifications"
_UPDATES = "OS updates"
_KEYS = "Hardware keys"
_ACTION_NAME = r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$"

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


class LockScreenItem(str, enum.Enum):
    """`CustomDeviceManager.LOCK_SCREEN_*` (W466f). The agent turns names into
    Samsung's flags."""

    CLOCK = "CLOCK"
    DATE = "DATE"
    BATTERY_INFO = "BATTERY_INFO"
    CARRIER_INFO = "CARRIER_INFO"
    OWNER_INFO = "OWNER_INFO"
    SHORTCUT = "SHORTCUT"
    HELP_TEXT = "HELP_TEXT"
    NOTIFICATIONS = "NOTIFICATIONS"


class KeyboardMode(enum.IntEnum):
    """`CustomDeviceManager.KEYBOARD_MODE_*` (W466f)."""

    NORMAL = 0
    PREDICTION_OFF = 1
    SETTINGS_OFF = 2


class NotificationBlockMode(enum.IntEnum):
    """`ApplicationPolicy.NOTIFICATION_MODE_*` (W466f)."""

    BLOCK_ALL = 2
    BLOCK_TEXT = 3
    BLOCK_TEXT_AND_SOUND = 4


def _vibration(title: str, description: str):
    return Field(default=None, ge=0, le=5, title=title, description=description,
                 json_schema_extra={"ui_group": _SOUND, "ui_oem": KNOX})


class KnoxLockScreenFields(PolicySpec):
    """W466f. 📖 `SystemManager.setLockScreenHiddenItems`: "not all flags work on
    all devices"."""

    #: UNION: hiding more is the stricter choice, so every policy's items hide.
    lock_screen_hidden_items: Annotated[list[LockScreenItem] | None, Merge(MergeStrategy.UNION)] = Field(
        default=None,
        title="Hide on the lock screen",
        description=(
            "Ticked items are hidden on the lock screen. Removing one shows it again, "
            "but only if ATLAS hid it. ⚠️ Samsung: not every item works on every device."
        ),
        json_schema_extra={"ui_group": _LOCK, "ui_oem": KNOX, "ui_control": "enum_set",
                           "ui_choice_labels": {
                               "CLOCK": "Clock", "DATE": "Date", "BATTERY_INFO": "Battery information",
                               "CARRIER_INFO": "Carrier name", "OWNER_INFO": "Owner information",
                               "SHORTCUT": "App shortcuts", "HELP_TEXT": "Help text",
                               "NOTIFICATIONS": "Notifications"}},
    )


class KnoxSoundFields(PolicySpec):
    """W466f. 📖 `SystemManager.setVibrationIntensity(mode, 0–5)`."""

    vibration_call_level: Annotated[int | None, _RANK_WINS] = _vibration(
        "Call vibration", "0 (off) to 5 (strongest). Removing it puts back the device's level.")
    vibration_notification_level: Annotated[int | None, _RANK_WINS] = _vibration(
        "Notification vibration", "0 (off) to 5 (strongest). Removing it puts back the device's level.")
    vibration_system_level: Annotated[int | None, _RANK_WINS] = _vibration(
        "Touch feedback vibration", "0 (off) to 5 (strongest). Removing it puts back the device's level.")


class KnoxKeyboardFields(PolicySpec):
    """W466f. 📖 `SystemManager.setKeyboardMode`."""

    keyboard_mode: Annotated[KeyboardMode | None, _RANK_WINS] = Field(
        default=None,
        title="Samsung Keyboard",
        description=(
            "Normal; Predictive text off; or Settings off (the user cannot open the "
            "keyboard's settings). Removing it puts back the device's mode."
        ),
        json_schema_extra={"ui_group": _KEYBOARD, "ui_oem": KNOX, "ui_choice_labels": {
            "NORMAL": "Normal", "PREDICTION_OFF": "Predictive text off", "SETTINGS_OFF": "Settings off"}},
    )


class KnoxNotificationFields(PolicySpec):
    """W466f. 📖 `ApplicationPolicy.addPackagesToNotificationBlackList` and
    `setApplicationNotificationMode` (the mode applies to the listed apps; to
    confirm on hardware)."""

    notification_blocked_apps: Annotated[
        list[Annotated[str, Field(pattern=_PACKAGE)]] | None, Merge(MergeStrategy.UNION),
    ] = Field(
        default=None,
        title="Apps whose notifications are blocked",
        description=(
            "Pick from the library or type a package name. Removing an app unblocks "
            "it, but only if ATLAS blocked it."
        ),
        json_schema_extra={"ui_group": _NOTIFY, "ui_oem": KNOX, "ui_control": "package_list",
                           "ui_library_picker": True},
    )
    notification_block_mode: Annotated[NotificationBlockMode | None, _RANK_WINS] = Field(
        default=None,
        title="How they are blocked",
        description=(
            "Block all: no notification shows. Block text: it shows without its text. "
            "Block text and sound: also silent. Leave unset for Samsung's default."
        ),
        json_schema_extra={"ui_group": _NOTIFY, "ui_oem": KNOX, "ui_choice_labels": {
            "BLOCK_ALL": "Block all", "BLOCK_TEXT": "Block text",
            "BLOCK_TEXT_AND_SOUND": "Block text and sound"}},
    )


class KnoxFirmwareFields(PolicySpec):
    """W466f. 📖 `RestrictionPolicy.allowFirmwareRecovery`. Joins the OS updates
    page (pages group by label)."""

    allow_firmware_recovery: Annotated[bool | None, _DENY_WINS] = _allow(
        "Firmware recovery", _UPDATES,
        "Blocked: the device cannot be reflashed with recovery tools such as Smart Switch "
        "emergency recovery.")


class HardKey(enum.IntEnum):
    """`KPCCManager.KEYCODE_*` (W469). Mirrored by the agent."""

    XCOVER = 1015
    TOP = 1079


class KeyPress(enum.IntEnum):
    """`CustomDeviceManager.KEY_ACTION_*` for `setHardKeyIntentBroadcast` (W469).

    ✅ W470 (operator, XCover6 Pro): the XCover key offers short and long press
    only; double press belongs to the side (power) key, which ATLAS does not map.
    """

    SHORT = 3
    LONG = 4


class KeyAction(str, enum.Enum):
    """What a mapped key does (W469)."""

    #: Knox tells the ATLAS agent, which opens the app.
    OPEN_APP = "open_app"
    #: Knox sends the app's own action name to it (push-to-talk apps that
    #: support Samsung's managed key mapping).
    SEND_TO_APP = "send_to_app"


class KeyMapping(BaseModel):
    """One key and press, and what it does (W469)."""

    model_config = ConfigDict(extra="forbid")

    key: HardKey
    press: KeyPress = KeyPress.SHORT
    action: KeyAction = KeyAction.OPEN_APP
    package_name: str = Field(pattern=_PACKAGE)
    intent_action: str | None = Field(default=None, pattern=_ACTION_NAME, max_length=200)
    release_action: str | None = Field(default=None, pattern=_ACTION_NAME, max_length=200)

    @model_validator(mode="after")
    def _says_one_thing(self) -> "KeyMapping":
        if self.action is KeyAction.SEND_TO_APP and not self.intent_action:
            raise ValueError("Send to app needs the app's action name")
        if self.action is KeyAction.OPEN_APP and (self.intent_action or self.release_action):
            raise ValueError("Open app takes no action names")
        if self.release_action and self.press is not KeyPress.SHORT:
            raise ValueError("a release action name only goes with a short press")
        return self


class KnoxHardwareKeyFields(PolicySpec):
    """W469. 📖 `SystemManager.setHardKeyIntentBroadcast` (Knox API 36)."""

    #: ⚠️ Highest rank wins, not a merge: two policies mapping the same key and
    #: press differently cannot both happen.
    hardware_key_mappings: Annotated[list[KeyMapping] | None, _RANK_WINS] = Field(
        default=None,
        title="Key mappings",
        description=(
            "What the XCover key and the top key do, by short or long press. "
            "Open app opens the app. Send to app sends the app's own action name, for "
            "push-to-talk apps that support Samsung's key mapping (the app's maker gives "
            "you the names). Removing a mapping gives the key back. ⚠️ Whether the key "
            "also keeps its own function is to be confirmed on hardware."
        ),
        json_schema_extra={"ui_group": _KEYS, "ui_oem": KNOX, "ui_control": "key_mappings"},
    )

    @model_validator(mode="after")
    def _one_mapping_per_key_and_press(self) -> "KnoxHardwareKeyFields":
        seen: set[tuple[int, int]] = set()
        for m in self.hardware_key_mappings or []:
            slot = (int(m.key), int(m.press))
            if slot in seen:
                raise ValueError(f"the {m.key.name.lower()} key's {m.press.name.lower()} press is mapped twice")
            seen.add(slot)
        return self


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


class NfcSamsungMode(str, enum.Enum):
    """What Knox does with NFC (W472)."""

    KEEP_ON = "keep_on"
    OFF_LOCKED = "off_locked"


class KnoxRadioFields(PolicySpec):
    """W466b. Airplane mode stayed in Restrictions: Android's own restriction."""

    #: W472. 📖 `NfcPolicy.startNFC` / `allowNFCStateChange`, deprecated in Knox
    #: API 38; ✅ the probe answered true on the XCover6 Pro.
    nfc_samsung_mode: Annotated[NfcSamsungMode | None, _RANK_WINS] = Field(
        default=None,
        title="NFC (Samsung)",
        description=(
            "Keep on: NFC is on and the user cannot turn it off. Off and locked: NFC is "
            "off and cannot be turned on, also on Samsung devices older than Android 15. "
            "On a Samsung device this takes the place of Restrictions › Radios › NFC. "
            "Removing it unlocks NFC and puts back what the device had. ⚠️ Samsung marks "
            "these calls deprecated; they work on current devices."
        ),
        json_schema_extra={"ui_group": _RADIOS, "ui_oem": KNOX, "ui_choice_labels": {
            "KEEP_ON": "Keep on", "OFF_LOCKED": "Off and locked"}},
    )

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
#: Fields added to these groups after the move (W472 NFC): never in another type.
_BORN_HERE = frozenset({"nfc_samsung_mode"})

MOVED_FROM = {
    "RESTRICTIONS": tuple(
        f for group in (KnoxRadioFields, KnoxRoamingFields, KnoxDeviceFields, KnoxUsbFields)
        for f in group.model_fields if f not in _BORN_HERE
    ),
    "APP_CATALOG": tuple(KnoxBatteryFields.model_fields),
}
#: ⚠️ W466f's fields were born here too (their own groups), so they are not in MOVED_FROM.
