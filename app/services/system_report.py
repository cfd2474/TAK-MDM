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

"""What devices say about their OS updates and fonts (W465 K2b).

The agent reports, at every check-in: a pending OS update (standard Android),
the fonts and font sizes the device has and which are active (Knox), Samsung's
two OS update switches (Knox), and the answer to the boot animation probe.

Two readers: the device page (`view`), and the SYSTEM_CONFIG policy editor's font picker
(`reported_fonts`), which can only offer fonts some device has said it has.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Device


#: W466a: Samsung's USB connection type codes, as the device page says them.
_USB = {0: "device default", 1: "MTP (file transfer)", 2: "PTP (photo transfer)", 3: "MIDI",
        4: "charging only", 5: "tethering"}


#: W466b: how the device page names a Knox switch.
SWITCH_LABELS = {
    "allow_cellular_data": "cellular data", "allow_bluetooth_discoverable": "Bluetooth discoverable",
    "allow_tethering": "hotspot and tethering", "allow_usb_tethering": "USB tethering",
    "allow_data_roaming": "data while roaming", "allow_roaming_push": "WAP push while roaming",
    "allow_roaming_sync": "data sync while roaming", "allow_roaming_voice_calls": "voice calls while roaming",
    # W466c
    "allow_power_off": "power off", "allow_microphone": "microphone",
    "allow_settings_changes": "Settings changes", "allow_clipboard": "clipboard",
    "allow_share_list": "Share menu", "allow_smart_clip": "Smart select",
    # W466d
    "allow_usb_host_storage": "USB host (OTG)", "allow_sd_card_write": "SD card write",
    # W466f
    "allow_firmware_recovery": "firmware recovery",
    # W473
    "allow_power_saving_mode": "power saving mode", "allow_data_saver": "Data Saver",
    "allow_dont_keep_activities": "Don't keep activities", "allow_background_process_limit": "background process limit",
}


@dataclass(frozen=True)
class View:
    pending_update_since: datetime | None
    active_font: str | None
    active_font_size: float | None
    ota_allowed: bool | None
    firmware_auto_update: bool | None
    boot_animation_probe: str | None
    boot_animation: str | None
    shutdown_animation: str | None
    auto_startup: bool | None
    auto_shutdown_on_usb_removal: bool | None
    usb_connection_type: str | None
    battery_exceptions: tuple[str, ...]
    time_format_probe: str | None
    #: W472: the NFC probe's answer, verbatim (not shown on the page, W474).
    nfc_probe: str | None
    #: W474: NFC as Knox reads it back, e.g. "on, locked".
    nfc_samsung: str | None
    #: W466b: the Knox switches that are blocked on the device, by label.
    blocked_switches: tuple[str, ...]
    #: W466d: the only USB device classes Knox lets through; None: no list.
    usb_allowed_classes: str | None
    reported_at: datetime | None


def view(report: dict | None, reported_at: datetime | None) -> View | None:
    """None when the device never reported (an older agent)."""
    if not report:
        return None
    millis = report.get("pending_update_since")
    pending = None
    if isinstance(millis, (int, float)) and millis > 0:
        try:
            pending = datetime.fromtimestamp(millis / 1000, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            pending = None
    return View(
        pending_update_since=pending,
        active_font=report.get("active_font") or None,
        active_font_size=report.get("active_font_size"),
        ota_allowed=report.get("ota_allowed"),
        firmware_auto_update=report.get("firmware_auto_update"),
        boot_animation_probe=report.get("boot_animation_probe") or None,
        boot_animation=report.get("boot_animation") or None,
        shutdown_animation=report.get("shutdown_animation") or None,
        auto_startup=report.get("auto_startup"),
        auto_shutdown_on_usb_removal=report.get("auto_shutdown_on_usb_removal"),
        usb_connection_type=_USB.get(report.get("usb_connection_type")),
        battery_exceptions=tuple(report.get("battery_exceptions") or ()),
        time_format_probe=report.get("time_format_probe") or None,
        nfc_probe=report.get("nfc_probe") or None,
        nfc_samsung=report.get("nfc_samsung") or None,
        blocked_switches=tuple(
            SWITCH_LABELS.get(key, key) for key, allowed in sorted((report.get("switches") or {}).items())
            if allowed is False),
        usb_allowed_classes=_usb_classes(report.get("usb_allowed_classes")),
        reported_at=reported_at,
    )


def _usb_classes(names: object) -> str | None:
    """W466d: "Audio, Storage" for the device page; None when no list is set."""
    if not isinstance(names, list):
        return None
    from app.policies.specs.knox_controls import UsbClass

    labels = {"AUD": "audio", "CDC": "network and modem", "COM": "communications", "HID": "HID",
              "MAS": "storage", "MIS": "miscellaneous", "STI": "camera", "VEN": "vendor-specific",
              "WIR": "wireless adapter"}
    known = [labels[n] for n in names if n in UsbClass.__members__]
    return ", ".join(known) if known else "hubs only"


def device_label(device: Device) -> str:
    """How the console names a device: its name with the serial, or the serial."""
    return f"{device.name} ({device.serial_number})" if device.name else device.serial_number


def reported_fonts(session: Session) -> list[dict]:
    """Every font any device reported, each once, with the devices that have it.

    Sorted by font name, and each font's devices by label. Operator,
    2026-11-10: "show next to each font name, the device(s) that reported it".
    """
    fonts: dict[str, set[str]] = {}
    for device in session.scalars(select(Device).where(Device.system_report.is_not(None))):
        for name in (device.system_report or {}).get("fonts") or []:
            if isinstance(name, str) and name.strip():
                fonts.setdefault(name.strip(), set()).add(device_label(device))
    return [
        {"name": name, "devices": sorted(devices, key=str.lower)}
        for name, devices in sorted(fonts.items(), key=lambda item: item[0].lower())
    ]
