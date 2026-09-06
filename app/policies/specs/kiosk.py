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

"""Kiosk: lock a device to one app and decide what the user can still reach (W59).

Kiosk used to be a single field on `APP_CATALOG`. It is its own category now,
because "which apps are installed" and "what this device is allowed to be" are
different questions that happen to both mention an app.

**Read `docs/ANDROID_PLATFORM_REFERENCE.md` §7 before changing anything here.**
Every rule below is recorded there and most were learned on hardware.

What a Device Owner can actually do
-----------------------------------

`setLockTaskPackages` builds an allowlist; `setLockTaskFeatures` decides what the
user keeps. Both work today without the agent being a launcher, and single-app
kiosk is verified on `SM-X520`.

⚠️ **Four sections need the agent to *be* the launcher** — multi app, launcher,
website kiosk, screensaver. Without `category.HOME` there is no home screen to
put a grid of apps on, nothing to draw a screensaver over, and no browser shell to
point at a URL. The reference's design note is explicit that this is a rewrite,
not a feature flag. They are declared here so an operator can see the shape of
what is coming, and **refused at validation** rather than saved and silently
ignored — the same treatment the Knox-gated network fields get.

Peripheral settings are *temporal*, not a second copy
-----------------------------------------------------

The `RESTRICTIONS` policy already carries camera, Bluetooth, location and the
rest. These are not a duplicate set: they apply **while the device is locked in
kiosk**, and the standard restrictions resume when it leaves. A device bolted to a
wall wants different rules from the same device in someone's hand, and expressing
that as "two policies that disagree" would need the resolver to pick a winner for
a question that has no single answer.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, model_validator

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy

_PACKAGE_PATTERN = r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$"

#: What the launcher-dependent sections are waiting on.
LAUNCHER = "an ATLAS launcher"

_SINGLE = "Single app"
_MULTI = "Multi app"
_BACKGROUND = "Background apps"
_LAUNCHER = "Launcher"
_PERIPHERAL = "Peripheral settings"
_EXIT = "Kiosk exit settings"
_WEBSITE = "Website kiosk settings"
_SCREENSAVER = "Kiosk screensaver"


def _keeps(title: str, description: str = ""):
    """A lock-task feature: does the user keep this while locked in?"""
    return Field(
        default=None,
        title=title,
        description=description,
        json_schema_extra={
            "ui_group": _EXIT,
            "ui_true": "Available",
            "ui_false": "Blocked",
        },
    )


def _peripheral(title: str, description: str = ""):
    """A peripheral the kiosk allows or blocks *while locked*."""
    return Field(
        default=None,
        title=title,
        description=description,
        json_schema_extra={
            "ui_group": _PERIPHERAL,
            "ui_true": "Allowed",
            "ui_false": "Blocked",
        },
    )


class KioskSpec(PolicySpec):

    # ----------------------------------------------------------------------- #
    # Single app
    # ----------------------------------------------------------------------- #

    # No natural ordering between two kiosk apps — someone has to lose, loudly.
    kiosk_package: Annotated[str | None, Merge(MergeStrategy.HIGHEST_RANK)] = Field(
        default=None,
        pattern=_PACKAGE_PATTERN,
        title="Kiosk app",
        description="The app this device is locked to. Chosen from the apps "
        "uploaded to this server, the same way required apps are.",
        json_schema_extra={"ui_group": _SINGLE, "ui_control": "kiosk_app"},
    )

    kiosk_activity: Annotated[str | None, Merge(MergeStrategy.HIGHEST_RANK)] = Field(
        default=None,
        max_length=255,
        title="Activity class",
        description="Launch this screen instead of the app's normal entry point — "
        "for example com.example.app.KioskActivity. Leave blank to use whatever "
        "the app opens with.",
        json_schema_extra={"ui_group": _SINGLE, "ui_control": "str"},
    )

    kiosk_restrict_to_activity: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = Field(
        default=None,
        title="Restrict to this activity only",
        description="Block anything that is not the kiosk app from opening inside "
        "the locked task. ⚠️ It cannot stop the kiosk app moving between its own "
        "screens — Android has no per-activity lock, and an app in lock task may "
        "start its own activities freely.",
        json_schema_extra={
            "ui_group": _SINGLE,
            "ui_true": "Blocked",
            "ui_false": "Allowed",
        },
    )

    # ----------------------------------------------------------------------- #
    # Background apps
    # ----------------------------------------------------------------------- #

    background_packages: Annotated[list[str] | None, Merge(MergeStrategy.UNION)] = Field(
        default=None,
        title="Background apps",
        description="Apps permitted to run alongside the kiosk app — a keyboard, a "
        "VPN client, an app the kiosk app hands off to. They are added to the "
        "lock-task allowlist, so the device may enter them without breaking out of "
        "kiosk. This does not launch them.",
        json_schema_extra={"ui_group": _BACKGROUND, "ui_control": "package_list"},
    )

    # ----------------------------------------------------------------------- #
    # Kiosk exit settings — the lock-task features
    # ----------------------------------------------------------------------- #

    keep_home_button: Annotated[bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)] = _keeps(
        "Home button",
        "HOME is pointed at the kiosk app, so pressing it returns there rather "
        "than reaching the system launcher.",
    )
    keep_recents_button: Annotated[bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)] = _keeps(
        "Recents button", "The overview / recent-apps switcher."
    )
    keep_notifications: Annotated[bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)] = _keeps(
        "Notifications",
        "Shade and heads-up notifications. ⚠️ Android refuses this unless the home "
        "button is also available.",
    )
    keep_system_info: Annotated[bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)] = _keeps(
        "Status bar information", "Clock, battery and signal in the status bar."
    )
    keep_keyguard: Annotated[bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)] = _keeps(
        "Lock screen",
        "Leave off and the device does not present a keyguard while locked in — "
        "usually what a wall-mounted kiosk wants.",
    )
    keep_power_menu: Annotated[bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)] = _keeps(
        "Power menu",
        "⚠️ Blocking this removes the only on-device way to power off or restart. "
        "A device that then misbehaves in the field is recoverable by factory reset "
        "and little else.",
    )

    # ----------------------------------------------------------------------- #
    # Peripheral settings — while locked in kiosk only
    # ----------------------------------------------------------------------- #

    _PERIPHERAL_NOTE = "Applies only while the device is locked in kiosk."

    kiosk_allow_camera: Annotated[bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)] = _peripheral(
        "Camera", _PERIPHERAL_NOTE
    )
    kiosk_allow_bluetooth: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = _peripheral("Bluetooth", _PERIPHERAL_NOTE)
    kiosk_allow_wifi_config: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = _peripheral(
        "Change Wi-Fi settings",
        "Whether the user may join or edit networks. The device stays connected "
        "either way. " + _PERIPHERAL_NOTE,
    )
    kiosk_allow_volume_change: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = _peripheral("Change volume", _PERIPHERAL_NOTE)
    kiosk_allow_brightness_change: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = _peripheral("Change screen brightness", _PERIPHERAL_NOTE)
    kiosk_allow_screen_capture: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = _peripheral("Screen capture", _PERIPHERAL_NOTE)
    kiosk_allow_airplane_mode: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = _peripheral("Airplane mode", _PERIPHERAL_NOTE)

    # ----------------------------------------------------------------------- #
    # Declared, and refused until the agent is a launcher
    # ----------------------------------------------------------------------- #

    multi_app_packages: Annotated[list[str] | None, Merge(MergeStrategy.UNION)] = Field(
        default=None,
        title="Kiosk apps",
        description="Several apps presented on a kiosk home screen for the user to "
        "choose between.",
        json_schema_extra={
            "ui_group": _MULTI,
            "ui_control": "package_list",
            "ui_requires": LAUNCHER,
        },
    )
    launcher_wallpaper_file_id: Annotated[
        str | None, Merge(MergeStrategy.HIGHEST_RANK)
    ] = Field(
        default=None,
        title="Kiosk launcher wallpaper",
        description="Background for the kiosk home screen.",
        json_schema_extra={"ui_group": _LAUNCHER, "ui_requires": LAUNCHER},
    )
    website_kiosk_url: Annotated[str | None, Merge(MergeStrategy.HIGHEST_RANK)] = Field(
        default=None,
        title="Website",
        description="Lock the device to a single web page.",
        json_schema_extra={"ui_group": _WEBSITE, "ui_requires": LAUNCHER},
    )
    screensaver_file_id: Annotated[str | None, Merge(MergeStrategy.HIGHEST_RANK)] = Field(
        default=None,
        title="Screensaver media",
        description="Shown after the device has been idle for a while.",
        json_schema_extra={"ui_group": _SCREENSAVER, "ui_requires": LAUNCHER},
    )
    screensaver_idle_seconds: Annotated[int | None, Merge(MergeStrategy.MIN)] = Field(
        default=None,
        ge=10,
        le=3600,
        title="Show screensaver after",
        description="Seconds of inactivity before the screensaver appears.",
        json_schema_extra={"ui_group": _SCREENSAVER, "ui_requires": LAUNCHER},
    )

    # ----------------------------------------------------------------------- #
    # Validation
    # ----------------------------------------------------------------------- #

    @model_validator(mode="after")
    def _refuse_what_needs_a_launcher(self) -> "KioskSpec":
        """Reject the sections that cannot work without an ATLAS launcher.

        Saving them against the day one exists would hand an operator a policy
        that saves, assigns, reports no error, and locks nothing — and a kiosk
        wrongly believed to be in force is worse than a visibly absent one.
        """
        blocked = [
            name
            for name in (
                "multi_app_packages",
                "launcher_wallpaper_file_id",
                "website_kiosk_url",
                "screensaver_file_id",
                "screensaver_idle_seconds",
            )
            if getattr(self, name) is not None
        ]
        if blocked:
            raise ValueError(
                f"{', '.join(blocked)} needs {LAUNCHER}. The agent deliberately does "
                f"not declare category.HOME (see the Android platform reference §7), "
                f"so there is no kiosk home screen to place apps, wallpaper, a web "
                f"view or a screensaver on. Single app, background apps, exit "
                f"settings and peripheral settings all work today"
            )
        return self

    @model_validator(mode="after")
    def _notifications_need_the_home_button(self) -> "KioskSpec":
        """Android refuses `NOTIFICATIONS` without `HOME`, and says so at apply time.

        ⚠️ Caught here instead, because from Android 14 lock-task features and
        packages are a **single policy**: a rejected feature set takes the package
        allowlist down with it, leaving the device with no kiosk at all rather than
        a kiosk missing its notifications.
        """
        if self.keep_notifications and self.keep_home_button is False:
            raise ValueError(
                "notifications cannot be available while the home button is blocked "
                "— Android rejects the combination outright "
                "(IllegalArgumentException: Cannot use LOCK_TASK_FEATURE_NOTIFICATIONS "
                "without LOCK_TASK_FEATURE_HOME). Allow the home button, which is "
                "pointed at the kiosk app and does not let the user out"
            )
        return self

    @model_validator(mode="after")
    def _restricting_to_an_activity_needs_one(self) -> "KioskSpec":
        """"This activity only" says nothing without an activity to name."""
        if self.kiosk_restrict_to_activity and not self.kiosk_activity:
            raise ValueError(
                "restrict to this activity only needs an activity class — name the "
                "screen to lock to, or clear the restriction"
            )
        return self

    @model_validator(mode="after")
    def _kiosk_settings_need_a_kiosk_app(self) -> "KioskSpec":
        """Every other field here describes how the kiosk behaves. Without an app
        to lock to, they describe nothing — and a policy that looks configured but
        locks nothing is the failure this whole category exists to make visible."""
        if self.kiosk_package:
            return self

        configured = [
            name
            for name, value in self.model_dump(exclude_none=True).items()
            if name != "kiosk_package" and value not in (None, [], {})
        ]
        if configured:
            raise ValueError(
                f"{', '.join(sorted(configured))} only apply while the device is "
                f"locked in kiosk, and no kiosk app is set. Choose a kiosk app, or "
                f"clear these"
            )
        return self
