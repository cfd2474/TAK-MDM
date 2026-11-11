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

"""RESTRICTIONS policy spec.

Every boolean here is phrased as an *allow* so that MOST_RESTRICTIVE is a plain
logical AND. Naming a field ``disallow_x`` would invert the meaning of the strategy
and is the kind of subtle trap that produces a permissive fleet by accident.

Field ``title`` / ``description`` / ``json_schema_extra`` drive the form-driven
editor (W10). ``ui_group`` buckets fields into sections; ``ui_true`` / ``ui_false``
are the words shown for an allow-boolean's two managed states.
"""

from __future__ import annotations

import enum
from typing import Annotated, Any

from pydantic import Field, model_validator

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy

_DENY_WINS = Merge(MergeStrategy.MOST_RESTRICTIVE)


def _allow(title: str, group: str, description: str = "", oem: str | None = None):
    """An allow-boolean field with its form metadata. `oem` (W466b): the vendor it
    needs ("Knox"), shown as "Samsung Knox only" on a live control."""
    extra = {"ui_group": group, "ui_true": "Allowed", "ui_false": "Blocked"}
    if oem:
        extra["ui_oem"] = oem
    return Field(default=None, title=title, description=description, json_schema_extra=extra)


class RadioMode(str, enum.Enum):
    """What a policy wants from Wi-Fi or Bluetooth (W364)."""

    ALLOW = "allow"
    BLOCK = "block"
    KEEP_ON = "keep_on"


class NfcMode(str, enum.Enum):
    """NFC has no "keep on": a Device Owner cannot turn NFC on without Knox
    (`NfcAdapter.enable` needs WRITE_SECURE_SETTINGS). Operator, 2026-10-09:
    leave it out until Knox works."""

    ALLOW = "allow"
    BLOCK = "block"


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


#: ⚠️ Higher rank wins for the radios and volumes (operator, W364), not most
#: restrictive: a "keep on" in a higher-ranked policy must beat a "block" below it.
_RANK_WINS = Merge(MergeStrategy.HIGHEST_RANK)

_RADIOS = "Radios"
_ROAMING = "Roaming"
_DEVICE = "Device controls"
_USB = "USB and storage"
_VOLUME = "Volume"


def _volume(title: str, description: str):
    """A forced volume: off means not managed, on holds the slider's level."""
    return Field(
        default=None,
        ge=0,
        le=100,
        title=title,
        description=description,
        json_schema_extra={"ui_group": _VOLUME, "ui_control": "percent_slider", "ui_unit": "%"},
    )


class RestrictionsSpec(PolicySpec):
    allow_camera: Annotated[bool | None, _DENY_WINS] = _allow(
        "Camera", "Device functionality"
    )
    allow_screen_capture: Annotated[bool | None, _DENY_WINS] = _allow(
        "Screen capture", "Device functionality"
    )
    allow_safe_mode: Annotated[bool | None, _DENY_WINS] = _allow(
        "Safe mode", "Device functionality",
        "Booting into safe mode disables device-admin apps.",
    )
    allow_factory_reset: Annotated[bool | None, _DENY_WINS] = _allow(
        "Factory reset", "Device functionality"
    )
    allow_developer_options: Annotated[bool | None, _DENY_WINS] = _allow(
        "Developer options", "Device functionality",
        "Also gates USB/wireless debugging.",
    )
    allow_install_unknown_sources: Annotated[bool | None, _DENY_WINS] = _allow(
        "Install from unknown sources", "Device functionality"
    )

    allow_outgoing_calls: Annotated[bool | None, _DENY_WINS] = _allow(
        "Outgoing calls", "Network & communication"
    )
    allow_location_services: Annotated[bool | None, _DENY_WINS] = _allow(
        "Location services", "Network & communication"
    )
    allow_usb_file_transfer: Annotated[bool | None, _DENY_WINS] = _allow(
        "USB file transfer", "Network & communication",
        "MTP/PTP access to device storage over USB.",
    )

    allow_credential_configuration: Annotated[bool | None, _DENY_WINS] = _allow(
        "Credential configuration", "Network & communication",
        "Whether the user may manage certificates in Settings. ⚠️ It blocks the "
        "whole credentials screen, so the user cannot add or remove their "
        "own certificates either — not just ones an administrator placed.",
    )

    # ----------------------------------------------------------------------- #
    # Radios (W364)
    # ----------------------------------------------------------------------- #

    wifi_mode: Annotated[RadioMode | None, _RANK_WINS] = Field(
        default=None,
        title="Wi-Fi",
        description=(
            "Allow: the user may turn Wi-Fi on and off. Block: Wi-Fi is turned off "
            "and cannot be turned on. Keep on: Wi-Fi is turned on and cannot be "
            "turned off. Block and Keep on also stop airplane mode changing Wi-Fi. "
            "If policies disagree, the higher-ranked one wins. ⚠️ Block cuts off a "
            "device that has no other connection (a Wi-Fi-only tablet, or a phone "
            "without a SIM): it can no longer reach ATLAS, so it never receives the "
            "policy that lifts the block, and it has to be factory reset."
        ),
        json_schema_extra={"ui_group": _RADIOS},
    )
    bluetooth_mode: Annotated[RadioMode | None, _RANK_WINS] = Field(
        default=None,
        title="Bluetooth",
        description=(
            "Allow: the user may turn Bluetooth on and off. Block: Bluetooth is "
            "turned off and cannot be used. Keep on: Bluetooth is turned on, and "
            "turned straight back on if someone turns it off. If policies disagree, "
            "the higher-ranked one wins."
        ),
        json_schema_extra={"ui_group": _RADIOS},
    )
    nfc_mode: Annotated[NfcMode | None, _RANK_WINS] = Field(
        default=None,
        title="NFC",
        description=(
            "Allow: the user may turn NFC on and off. Block: NFC is turned off and "
            "cannot be turned on. ⚠️ Block needs Android 15 or later; an older "
            "device reports that it could not apply it. A device without NFC "
            "ignores it. When Block is lifted, Samsung devices turn NFC back on by "
            "themselves. Keeping NFC on needs Samsung Knox and is not offered yet."
        ),
        json_schema_extra={"ui_group": _RADIOS},
    )

    # W466b: the rest of WatchTower's radio items. Knox only, except airplane
    # mode (Knox's `allowAirplaneMode` is deprecated; Android's
    # DISALLOW_AIRPLANE_MODE does it on every device).
    allow_cellular_data: Annotated[bool | None, _DENY_WINS] = _allow(
        "Cellular data", _RADIOS,
        "Blocked: mobile data is turned off and cannot be turned on. ⚠️ A tablet with "
        "no Wi-Fi then has no way to reach ATLAS to lift it.", oem="Knox")
    allow_bluetooth_discoverable: Annotated[bool | None, _DENY_WINS] = _allow(
        "Bluetooth discoverable", _RADIOS,
        "Blocked: other devices cannot find this one over Bluetooth; paired devices still work.",
        oem="Knox")
    allow_tethering: Annotated[bool | None, _DENY_WINS] = _allow(
        "Hotspot and tethering", _RADIOS,
        "Blocked: the device cannot share its connection — Wi-Fi hotspot, USB or Bluetooth tethering.",
        oem="Knox")
    allow_usb_tethering: Annotated[bool | None, _DENY_WINS] = _allow(
        "USB tethering", _RADIOS,
        "Blocked: the device cannot share its connection over USB. Other tethering is "
        "not affected.", oem="Knox")
    allow_airplane_mode: Annotated[bool | None, _DENY_WINS] = _allow(
        "Airplane mode", _RADIOS,
        "Blocked: the user cannot turn airplane mode on or off. Standard Android, so "
        "it works on every device.")

    # ----------------------------------------------------------------------- #
    # Roaming (W466b, Samsung Knox `RoamingPolicy`)
    # ----------------------------------------------------------------------- #

    allow_data_roaming: Annotated[bool | None, _DENY_WINS] = _allow(
        "Data while roaming", _ROAMING, "Mobile data on another operator's network.", oem="Knox")
    allow_roaming_push: Annotated[bool | None, _DENY_WINS] = _allow(
        "WAP push while roaming", _ROAMING, "Operator push messages while roaming.", oem="Knox")
    allow_roaming_sync: Annotated[bool | None, _DENY_WINS] = _allow(
        "Data sync while roaming", _ROAMING, "Apps syncing their accounts automatically while roaming.",
        oem="Knox")
    allow_roaming_voice_calls: Annotated[bool | None, _DENY_WINS] = _allow(
        "Voice calls while roaming", _ROAMING, "Making and receiving calls while roaming.", oem="Knox")

    # ----------------------------------------------------------------------- #
    # Device controls (W466c). Knox `RestrictionPolicy`, and standard Android
    # where Knox's own call is deprecated.
    # ----------------------------------------------------------------------- #

    allow_power_off: Annotated[bool | None, _DENY_WINS] = _allow(
        "Power off", _DEVICE,
        "Blocked: the power menu cannot turn the device off. Restart still works, and "
        "so does a forced restart with the buttons.", oem="Knox")
    allow_microphone: Annotated[bool | None, _DENY_WINS] = _allow(
        "Microphone", _DEVICE,
        "Blocked: no app can record sound, and calls have no audio from this device. "
        "⚠️ Push-to-talk in ATAK stops working.", oem="Knox")
    allow_settings_changes: Annotated[bool | None, _DENY_WINS] = _allow(
        "Settings changes", _DEVICE,
        "Blocked: the user cannot change anything in the Settings app. ATLAS can still "
        "apply policy.", oem="Knox")
    allow_clipboard: Annotated[bool | None, _DENY_WINS] = _allow(
        "Clipboard", _DEVICE, "Blocked: copy and paste do not work.", oem="Knox")
    allow_share_list: Annotated[bool | None, _DENY_WINS] = _allow(
        "Share menu", _DEVICE,
        "Blocked: the Share menu (send to another app) does not open.", oem="Knox")
    allow_smart_clip: Annotated[bool | None, _DENY_WINS] = _allow(
        "Smart select", _DEVICE,
        "Blocked: Samsung's Smart select (S Pen screen clipping) does not work.", oem="Knox")
    allow_status_bar: Annotated[bool | None, _DENY_WINS] = _allow(
        "Status bar expansion", _DEVICE,
        "Blocked: the user cannot pull down notifications or quick settings. Standard "
        "Android, so it works on every device.")
    allow_add_users: Annotated[bool | None, _DENY_WINS] = _allow(
        "Add users", _DEVICE,
        "Blocked: no new user or guest can be added. Standard Android.")
    allow_backup: Annotated[bool | None, _DENY_WINS] = _allow(
        "Backup", _DEVICE,
        "Allowed: the device may back up to the user's Google account. A managed "
        "device starts with backup off. Standard Android.")
    allow_apps_control: Annotated[bool | None, _DENY_WINS] = _allow(
        "Force stop and clear data", _DEVICE,
        "Blocked: in App info, Force stop, Clear data and Uninstall are refused for "
        "every app. Standard Android. The web filter also blocks this while it runs.")

    # ----------------------------------------------------------------------- #
    # USB and storage (W466d, Samsung Knox `RestrictionPolicy`)
    # ----------------------------------------------------------------------- #

    allow_usb_host_storage: Annotated[bool | None, _DENY_WINS] = _allow(
        "USB host (OTG)", _USB,
        "Blocked: nothing plugged into the device's USB port works — drives, card "
        "readers, keyboards, adapters. Charging still works. Samsung blocks all USB "
        "host use here, not only storage.", oem="Knox")
    allow_sd_card_write: Annotated[bool | None, _DENY_WINS] = _allow(
        "SD card write", _USB,
        "Blocked: the SD card is read-only. ⚠️ An SD card the device has encrypted "
        "may ignore this on older Samsung software.", oem="Knox")
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
        json_schema_extra={"ui_group": _USB, "ui_oem": "Knox", "ui_control": "enum_set",
                           "ui_choice_labels": {
                               "AUD": "Audio", "CDC": "Network and modem (CDC)",
                               "COM": "Communications (COM)", "HID": "Keyboard, mouse, game pad (HID)",
                               "MAS": "Storage", "MIS": "Miscellaneous", "STI": "Camera (still image)",
                               "VEN": "Vendor-specific", "WIR": "Wireless adapter (Bluetooth)"}},
    )

    # ----------------------------------------------------------------------- #
    # Volume (W364)
    # ----------------------------------------------------------------------- #

    ringer_volume_percent: Annotated[int | None, _RANK_WINS] = _volume(
        "Ringer volume",
        "Hold the ringer at this level. A change on the device is put back within "
        "seconds, including a switch to vibrate or silent.",
    )
    media_volume_percent: Annotated[int | None, _RANK_WINS] = _volume(
        "Media volume",
        "Hold media volume (music, video, ATAK audio) at this level. A change on the "
        "device is put back within seconds.",
    )
    alarm_volume_percent: Annotated[int | None, _RANK_WINS] = _volume(
        "Alarms volume",
        "Hold alarm and alert volume at this level. A change on the device is put "
        "back within seconds.",
    )

    @model_validator(mode="before")
    @classmethod
    def _bluetooth_was_a_switch(cls, data: Any) -> Any:
        """Read the pre-W364 `allow_bluetooth` switch as `bluetooth_mode`.

        ⚠️ Specs are `extra="forbid"`, so without this any old JSON (an import, a
        template file) carrying the switch would stop validating. Stored versions
        are rewritten by migration `p8r0t2v4x6z8`; this covers anything else.
        """
        if isinstance(data, dict) and "allow_bluetooth" in data:
            data = dict(data)
            legacy = data.pop("allow_bluetooth")
            if data.get("bluetooth_mode") is None and legacy is not None:
                data["bluetooth_mode"] = "allow" if legacy else "block"
        return data

    screen_timeout_seconds: Annotated[int | None, Merge(MergeStrategy.MIN)] = Field(
        default=None,
        ge=15,
        le=3_600,
        title="Screen timeout",
        description="Seconds of inactivity before the screen locks (15–3600).",
        json_schema_extra={"ui_group": "Display", "ui_unit": "seconds"},
    )
