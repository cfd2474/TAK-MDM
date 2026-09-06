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

import enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy

_PACKAGE_PATTERN = r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$"

#: What the launcher-dependent sections are waiting on.
LAUNCHER = "an ATLAS launcher"

_SINGLE = "Single app"
_MULTI = "Multi app"
_BACKGROUND = "Background apps"
_LAUNCHER = "Launcher"
_NIGHT = "Night mode"
_PERIPHERAL = "Peripheral settings"
_PERMITTED = "Permitted features"
_EXIT = "Kiosk exit settings"
_WEBSITE = "Website kiosk settings"
_SCREENSAVER = "Kiosk screensaver"


def _keeps(title: str, description: str = ""):
    """A lock-task feature: does the user keep this while locked in?

    ⚠️ Grouped under *Permitted features*, not *Kiosk exit settings*. These say
    what a locked-in user can still reach; leaving kiosk deliberately is a
    different question with its own section (W65).
    """
    return Field(
        default=None,
        title=title,
        description=description,
        json_schema_extra={
            "ui_group": _PERMITTED,
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


class LauncherOrientation(str, enum.Enum):
    AUTO = "auto"
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"


class NightHue(str, enum.Enum):
    RED = "red"
    AMBER = "amber"
    GREEN = "green"


class KioskApp(BaseModel):
    """One tile on the kiosk home screen.

    ⚠️ `favorite` is a property of the app, not a second list beside it. Two
    parallel lists could disagree — a favourite naming an app the kiosk does not
    permit — and the dock tile that produced would refuse to open, which reads to
    the user as a broken device rather than a bad policy.
    """

    model_config = ConfigDict(extra="forbid")

    package_name: str = Field(min_length=1, max_length=255)
    activity: str | None = Field(
        default=None,
        max_length=255,
        description="Leave empty to open the app normally.",
    )
    favorite: bool = False


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
        json_schema_extra={"ui_group": _SINGLE, "ui_control": "activity_choice"},
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
    # Permitted features — the lock-task features
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
    # Kiosk exit settings — the deliberate way out, on the device
    # ----------------------------------------------------------------------- #

    allow_manual_exit: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = Field(
        default=None,
        title="Allow manually exiting kiosk mode",
        description="Let someone standing at the device leave kiosk by tapping the "
        "screen a set number of times and entering the passcode below. Off means "
        "the only way out is to change the policy.",
        json_schema_extra={
            "ui_group": _EXIT,
            "ui_true": "Allowed",
            "ui_false": "Blocked",
        },
    )

    exit_password: Annotated[str | None, Merge(MergeStrategy.HIGHEST_RANK)] = Field(
        default=None,
        min_length=4,
        max_length=32,
        title="Kiosk exit passcode",
        description="⚠️ A gate, not a secret. It travels in the policy the device "
        "holds, so anyone with USB debugging can read it — it stops a user tapping "
        "their way out of a wall-mounted tablet, and stops nobody who is determined. "
        "Do not reuse a passcode that protects anything else.",
        json_schema_extra={"ui_group": _EXIT, "ui_control": "password"},
    )

    exit_tap_count: Annotated[int | None, Merge(MergeStrategy.MAX)] = Field(
        default=None,
        ge=3,
        le=20,
        title="Taps to show the passcode prompt",
        description="How many taps in the corner of the screen summon the prompt. "
        "Higher is harder to trigger by accident.",
        json_schema_extra={"ui_group": _EXIT, "ui_unit": "taps"},
    )

    reboot_tap_to_exit: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = Field(
        default=None,
        title="Reboot and tap to exit",
        description="Allow the same tap-and-passcode during the delay after a "
        "reboot, before the kiosk app relaunches. Useful when the kiosk app itself "
        "is what is misbehaving.",
        json_schema_extra={
            "ui_group": _EXIT,
            "ui_true": "Allowed",
            "ui_false": "Blocked",
        },
    )

    relaunch_after_reboot_seconds: Annotated[
        int | None, Merge(MergeStrategy.MIN)
    ] = Field(
        default=None,
        ge=0,
        le=300,
        title="Relaunch the kiosk app after a reboot",
        description="Seconds to wait after boot before locking the device again. "
        "Zero re-locks immediately. A short delay is what makes the reboot exit "
        "above usable at all.",
        json_schema_extra={"ui_group": _EXIT, "ui_unit": "seconds"},
    )

    auto_reenter_kiosk: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = Field(
        default=None,
        title="Re-enter kiosk automatically",
        description="After someone exits with the passcode, whether the device "
        "locks itself again at the next check-in. Off leaves it out of kiosk until "
        "it reboots or the policy changes — which is usually what an engineer at "
        "the device wants.",
        json_schema_extra={
            "ui_group": _EXIT,
            "ui_true": "Re-enter",
            "ui_false": "Stay out",
        },
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
    # Multi app — the ATLAS launcher (W68)
    # ----------------------------------------------------------------------- #

    multi_app_packages: Annotated[
        list[KioskApp] | None, Merge(MergeStrategy.MERGE_BY_KEY, key="package_name")
    ] = Field(
        default=None,
        title="Kiosk apps",
        description="The apps on the kiosk home screen, in the order they appear. "
        "The ATLAS launcher is installed automatically and the device is locked to "
        "it; only these apps can be opened.",
        json_schema_extra={"ui_group": _MULTI, "ui_control": "kiosk_apps"},
    )

    launcher_columns: Annotated[int | None, Merge(MergeStrategy.MIN)] = Field(
        default=None,
        ge=2,
        le=8,
        title="Grid columns",
        description="How many app tiles fit across the kiosk home screen.",
        json_schema_extra={"ui_group": _LAUNCHER, "ui_unit": "columns"},
    )
    launcher_show_search: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = Field(
        default=None,
        title="Show the search bar",
        description="Lets the user filter the grid by typing. The launcher hides it "
        "anyway below eight apps, where everything is already on screen.",
        json_schema_extra={"ui_group": _LAUNCHER, "ui_true": "Shown", "ui_false": "Hidden"},
    )
    launcher_show_clock: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = Field(
        default=None,
        title="Show the clock",
        description="A clock across the top of the kiosk home screen.",
        json_schema_extra={"ui_group": _LAUNCHER, "ui_true": "Shown", "ui_false": "Hidden"},
    )
    launcher_clock_zulu: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = Field(
        default=None,
        title="Zulu row",
        description="Add a Zulu (UTC) row beneath the local time. The local row is "
        "always shown and always 24-hour; this is the second line, not a choice "
        "between the two.",
        json_schema_extra={"ui_group": _LAUNCHER, "ui_true": "Shown", "ui_false": "Hidden"},
    )
    launcher_orientation: Annotated[
        LauncherOrientation | None, Merge(MergeStrategy.HIGHEST_RANK)
    ] = Field(
        default=None,
        title="Screen orientation",
        description="⚠️ Pins the kiosk home screen. Pinning every app as well needs "
        "the launcher to hold WRITE_SETTINGS, which only a person can grant at the "
        "device — without it the apps still rotate.",
        json_schema_extra={"ui_group": _LAUNCHER},
    )

    # ----------------------------------------------------------------------- #
    # Launcher — how the kiosk home screen looks
    #
    # ⚠️ There is no wallpaper field here. The Wallpaper policy already sets the
    # device wallpaper and the launcher's window is transparent, so it shows
    # through — a second field would be two policies writing one setting, and the
    # loser would lose silently.
    # ----------------------------------------------------------------------- #

    # ----------------------------------------------------------------------- #
    # Night mode — drawn by the agent, over every app
    # ----------------------------------------------------------------------- #

    kiosk_night_mode: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = Field(
        default=None,
        title="Night mode",
        description="Tint the whole screen to preserve dark adaptation. Drawn by the "
        "agent over every app, not only the kiosk home screen.",
        json_schema_extra={"ui_group": _NIGHT, "ui_true": "On", "ui_false": "Off"},
    )
    kiosk_night_hue: Annotated[
        NightHue | None, Merge(MergeStrategy.HIGHEST_RANK)
    ] = Field(
        default=None,
        title="Tint colour",
        description="Red preserves dark adaptation best; amber and green are easier "
        "to read by.",
        json_schema_extra={"ui_group": _NIGHT},
    )
    kiosk_night_level: Annotated[int | None, Merge(MergeStrategy.MAX)] = Field(
        default=None,
        ge=0,
        le=100,
        title="Tint strength",
        description="0 leaves the screen alone. 100 is as dark as the tint goes — "
        "which is deliberately short of opaque, so this can never blank a device.",
        json_schema_extra={"ui_group": _NIGHT, "ui_unit": "%"},
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
        """Reject the sections the ATLAS launcher does not implement **yet**.

        Saving them against the day it does would hand an operator a policy that
        saves, assigns, reports no error, and locks nothing — and a kiosk wrongly
        believed to be in force is worse than a visibly absent one.

        ⚠️ Multi app came off this list in W68, when the launcher was built, and
        the launcher wallpaper left it by being deleted — the Wallpaper policy
        already does that job and the launcher's window is transparent. Website
        kiosk and the screensaver are still here because they are still not built:
        the launcher shows a grid of installed apps, and neither a browser shell
        nor an idle surface exists.
        """
        blocked = [
            name
            for name in (
                "website_kiosk_url",
                "screensaver_file_id",
                "screensaver_idle_seconds",
            )
            if getattr(self, name) is not None
        ]
        if blocked:
            raise ValueError(
                f"{', '.join(blocked)} is not built yet. The ATLAS launcher (W68) "
                f"shows a grid of the apps you choose; it has no browser shell to "
                f"hold a web page in and no idle surface to draw a screensaver on. "
                f"Multi app, single app, background apps, exit settings and "
                f"peripheral settings all work today"
            )
        return self

    @model_validator(mode="after")
    def _launcher_settings_need_apps(self) -> "KioskSpec":
        """The launcher's own settings describe a home screen that must exist.

        Set without any apps they configure nothing, and an operator reading them
        back would reasonably believe this device has a kiosk home screen.
        """
        if self.multi_app_packages:
            return self
        dependent = [
            name
            for name in (
                "launcher_columns",
                "launcher_show_search",
                "launcher_show_clock",
                "launcher_clock_zulu",
                "launcher_orientation",
            )
            if getattr(self, name) is not None
        ]
        if dependent:
            raise ValueError(
                f"{', '.join(dependent)} only applies to a multi-app kiosk — add the "
                f"apps for the home screen, or clear these"
            )
        return self

    @model_validator(mode="after")
    def _one_tile_per_app(self) -> "KioskSpec":
        """Refuse the same app twice on one home screen.

        The launcher would draw one tile either way, so a second entry cannot take
        effect — and two identical rows in the console look like the ordering did
        not save.
        """
        seen: dict[str, int] = {}
        for app in self.multi_app_packages or []:
            seen[app.package_name] = seen.get(app.package_name, 0) + 1
        duplicates = sorted(name for name, count in seen.items() if count > 1)
        if duplicates:
            raise ValueError(
                f"{', '.join(duplicates)} appears more than once in the kiosk apps. "
                f"Each app gets one tile, so a second entry cannot take effect"
            )
        return self

    @model_validator(mode="after")
    def _night_settings_need_night_mode(self) -> "KioskSpec":
        """A tint colour and strength with the tint switched off configure nothing."""
        if self.kiosk_night_mode:
            return self
        dependent = [
            name
            for name in ("kiosk_night_hue", "kiosk_night_level")
            if getattr(self, name) is not None
        ]
        if dependent:
            raise ValueError(
                f"{', '.join(dependent)} only applies when night mode is on — turn "
                f"it on, or clear these"
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
    def _a_manual_exit_needs_a_passcode(self) -> "KioskSpec":
        """An exit gesture with no gate is a kiosk anyone can tap their way out of.

        Refused rather than defaulted: a policy that silently chose a passcode
        would be one nobody knows, and a policy that silently chose *none* would be
        a kiosk in name only.
        """
        if self.allow_manual_exit and not self.exit_password:
            raise ValueError(
                "allowing a manual exit needs an exit passcode — without one the "
                "tap gesture alone leaves kiosk, which is not a kiosk"
            )
        return self

    @model_validator(mode="after")
    def _exit_settings_need_a_manual_exit(self) -> "KioskSpec":
        """The tap count and the reboot exit describe how the manual exit behaves.

        With the exit switched off they describe nothing, and an operator reading
        them back would reasonably believe there is a way out of this device.
        """
        if self.allow_manual_exit:
            return self
        dependent = [
            name
            for name in ("exit_tap_count", "reboot_tap_to_exit", "auto_reenter_kiosk")
            if getattr(self, name) is not None
        ]
        if dependent:
            raise ValueError(
                f"{', '.join(dependent)} only apply when manually exiting kiosk is "
                f"allowed — turn that on, or clear these"
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
        locks nothing is the failure this whole category exists to make visible.

        ⚠️ There are **two** ways to have something to lock to (W68): a single
        kiosk app, or a list of apps, which locks the device to the ATLAS launcher
        showing them. Checking only `kiosk_package` here would have rejected every
        multi-app kiosk as unconfigured.
        """
        if self.kiosk_package or self.multi_app_packages:
            return self

        targets = ("kiosk_package", "multi_app_packages")
        configured = [
            name
            for name, value in self.model_dump(exclude_none=True).items()
            if name not in targets and value not in (None, [], {})
        ]
        if configured:
            raise ValueError(
                f"{', '.join(sorted(configured))} only apply while the device is "
                f"locked in kiosk, and nothing is set to lock to. Choose a kiosk "
                f"app, or add the apps for a multi-app kiosk, or clear these"
            )
        return self
