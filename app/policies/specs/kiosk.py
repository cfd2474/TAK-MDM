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
import re
from typing import Annotated, ClassVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy

_PACKAGE_PATTERN = r"^[A-Za-z][A-Za-z0-9_]*(\.[A-Za-z][A-Za-z0-9_]*)+$"

#: The ATLAS console — the agent's own package, and always a tile on a multi-app
#: kiosk home screen (W197).
#:
#: ⚠️ **Named here rather than read from settings**, though
#: `settings.agent_package_name` holds the same string. A spec must validate to
#: the same answer wherever it is loaded: a policy saved on one instance and
#: resolved on another would otherwise disagree about its own contents, and the
#: disagreement would be a tile that opens nothing. `test_kiosk_console_tile`
#: asserts the two are equal, so they cannot drift quietly.
ATLAS_CONSOLE_PACKAGE = "com.taksolutions.atlasmdm"

#: W380: the agent's own Device Settings and Power tiles, as the agent names
#: them (`PolicyApplier.DEVICE_SETTINGS_ACTIVITY`, `POWER_TILE_ACTIVITY`): fully
#: qualified, because the launcher starts them across a package boundary. The
#: agent adds a tile only when the policy has none with this package and
#: activity, so one stored here is drawn where the operator placed it.
DEVICE_SETTINGS_ACTIVITY = "com.taksolutions.atlasmdm.ui.DeviceSettingsActivity"
POWER_TILE_ACTIVITY = "com.taksolutions.atlasmdm.ui.PowerTileActivity"
SYSTEM_TILES = {DEVICE_SETTINGS_ACTIVITY: "Device Settings", POWER_TILE_ACTIVITY: "Power"}


def tile_identity(tile: dict) -> str:
    """Which tile a stored kiosk entry is (W380): its package, except the
    agent's Device Settings and Power tiles, which are the package *and* that
    activity. Shared by the merge and `KioskApp.identity`, so they agree."""
    package, activity = tile.get("package_name"), tile.get("activity")
    if package == ATLAS_CONSOLE_PACKAGE and activity in SYSTEM_TILES:
        return f"{package}/{activity}"
    return package

#: What the launcher-dependent sections are waiting on.
LAUNCHER = "an ATLAS launcher"

_SINGLE = "Single app"
_MULTI = "Multi app"
_BACKGROUND = "Background apps"
_LAUNCHER = "Launcher"
_NIGHT = "Night mode"
_DEVICE_SETTINGS = "Peripheral Settings"
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
    """A restriction with **no** control the user could be shown.

    ⚠️ What is left after W79 merged the rest into `_user_setting`. Camera,
    screen capture and airplane mode cannot be offered as controls at all - no
    app can toggle airplane mode, and a camera or screen-capture switch on a
    kiosk is a lockdown decision rather than a user preference - so these stay
    Allowed/Blocked and simply have no row on the device.
    """
    """A peripheral the kiosk allows or blocks *while locked*."""
    return Field(
        default=None,
        title=title,
        description=description,
        json_schema_extra={
            "ui_group": _DEVICE_SETTINGS,
            "ui_true": "Allowed",
            "ui_false": "Blocked",
        },
    )


def _power_setting(title: str, description: str):
    """The power menu, whose two states read as Active and Hidden.

    ⚠️ Separate from `_user_setting` only for its labels. "User can change" is
    wrong here: the user is not changing a setting, they are being given a way to
    turn the device off. Same tri-state underneath — unset still means the field
    takes no part in a merge.
    """
    return Field(
        default=None,
        title=title,
        description=description,
        json_schema_extra={
            # W380: beside the designer, where the Power tile it adds is placed.
            "ui_group": _MULTI,
            "ui_true": "Active",
            "ui_false": "Hidden",
        },
    )


def _user_setting(title: str, description: str, restriction: str | None = None):
    """A control the **user** may change from the kiosk's Device Settings screen.

    ⚠️ Different in kind from `_peripheral` above, which says what the device is
    *allowed* to do. This says what appears on a screen. The two can contradict —
    a volume slider on a device holding `DISALLOW_ADJUST_VOLUME` is a control that
    cannot move — and `_a_control_must_be_able_to_move` refuses that pairing.

    Default off: a kiosk shows nothing the operator did not ask for.
    """
    extra: dict[str, object] = {
        # W380: beside the designer, where the Device Settings tile these add is
        # placed. ⚠️ The "Blocked" choices still lock a single-app kiosk too.
        "ui_group": _MULTI,
        "ui_true": "User can change",
        # ⚠️ "Blocked", not "Hidden", where a `UserManager` restriction backs the
        # control. There the false case does not merely omit a row - it forbids
        # the device to change the thing at all, including by hardware key, and
        # an operator who read "Hidden" would be surprised by a volume rocker
        # that stopped working.
        "ui_false": "Blocked" if restriction else "Hidden",
    }
    if restriction:
        extra["enforced_by"] = restriction
    return Field(
        default=None,
        title=title,
        description=description,
        json_schema_extra=extra,
    )


class LauncherOrientation(str, enum.Enum):
    AUTO = "auto"
    PORTRAIT = "portrait"
    LANDSCAPE = "landscape"


class LauncherDeviceType(str, enum.Enum):
    """What the kiosk home screen is designed for (W371). Decides the grid sizes
    the designer offers; the launcher fits whatever grid it is given."""

    PHONE = "phone"
    TABLET = "tablet"


#: W371 (operator, 2026-10-11): the grids "within reason" of each device type,
#: as (columns, rows) ranges and the designer's starting grid.
GRID_LIMITS: dict[LauncherDeviceType, dict[str, tuple[int, int]]] = {
    LauncherDeviceType.PHONE: {"columns": (3, 5), "rows": (4, 7), "default": (4, 5)},
    LauncherDeviceType.TABLET: {"columns": (4, 8), "rows": (3, 6), "default": (6, 4)},
}
#: Pages an operator may add.
MAX_PAGES = 5
#: Apps the dock holds (W376, operator: 4). One row along the bottom of every
#: page; the launcher spreads them evenly across it.
MAX_DOCK = 4


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
    #: Which build to install (W196).
    #:
    #: ⚠️ **Without this a multi-app kiosk cannot engage at all.** Every tile
    #: is auto-required (W68), and since W139 a required entry naming no build
    #: resolves to "no version chosen" rather than to the newest one — so the
    #: apps never installed and the device reported the launcher having nothing
    #: to show.
    artifact_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    #: The device's own app, not a library build (W374): never installed or
    #: required, and switched back on by the agent if the device has it
    #: disabled. A library build overrides by being an ordinary tile instead.
    builtin: bool = False
    activity: str | None = Field(
        default=None,
        max_length=255,
        description="Leave empty to open the app normally.",
    )
    favorite: bool = False
    #: Where the tile sits on the designed grid (W371): 0-based page, row and
    #: column, shown 1-based in the console. All three or none. None means "the
    #: first free cell", which is how an older policy, the auto-added console
    #: tile and a tile clashing with another policy's are all placed.
    page: int | None = Field(default=None, ge=0, le=MAX_PAGES - 1)
    row: int | None = Field(default=None, ge=0, le=7)
    column: int | None = Field(default=None, ge=0, le=7)

    @model_validator(mode="after")
    def _builtin_names_no_build(self) -> "KioskApp":
        """A tile is the device's own app or a library build, never both: the
        agent would be told to install over the app it was told to keep."""
        if self.builtin and self.artifact_sha256:
            raise ValueError(
                f"{self.package_name} is a built-in tile, which uses the app already on "
                f"the device, so it names no build. Choose a library build instead, or "
                f"keep it built-in"
            )
        if self.builtin and self.package_name == ATLAS_CONSOLE_PACKAGE:
            raise ValueError("the ATLAS console tile is always the shipped build, not a built-in app")
        # Typed by hand ("Other built-in app"), unlike a library app picked from a list.
        if self.builtin and not re.fullmatch(_PACKAGE_PATTERN, self.package_name):
            raise ValueError(
                f"{self.package_name!r} is not a package name: it looks like com.example.app"
            )
        return self

    @model_validator(mode="after")
    def _a_position_is_all_three(self) -> "KioskApp":
        given = [v is not None for v in (self.page, self.row, self.column)]
        if any(given) and not all(given):
            raise ValueError(
                f"{self.package_name}: a tile's position needs its page, row and column together"
            )
        if all(given) and self.favorite:
            raise ValueError(
                f"{self.package_name} is in the dock, which sits below the grid on every "
                f"page, so it has no place on the grid as well"
            )
        return self

    @property
    def placed(self) -> bool:
        return self.page is not None

    @property
    def system_tile(self) -> str | None:
        """W380: the agent's Device Settings or Power activity, when this is one.
        Read from `identity`, so the rule lives in `tile_identity` alone."""
        return self.activity if self.identity != self.package_name else None

    @property
    def identity(self) -> str:
        """Which tile this is: an app is one tile per package, except the
        agent's, whose console and Device Settings and Power tiles are three
        (W380). Any other activity on the agent's package is the console."""
        return tile_identity({"package_name": self.package_name, "activity": self.activity})


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

    kiosk_artifact_sha256: Annotated[
        str | None, Merge(MergeStrategy.HIGHEST_RANK)
    ] = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
        title="Kiosk app build",
        description="Which build of the kiosk app to install. Required: since "
        "W139 nothing is chosen on your behalf, and a kiosk app with no build "
        "named cannot be installed, so the device has nothing to lock to.",
        json_schema_extra={"ui_group": _SINGLE, "ui_control": "kiosk_app_version"},
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
    # Multi app — the ATLAS launcher (W68)
    #
    # ⚠️ Declared here because **field order is sub-topic order** (W95).
    # `grouped_fields` buckets by `ui_group` in first-seen order, so where a field
    # sits in this class is where its section sits in the console. Multi app used
    # to be four unrelated sub-topics below Single app; the two kiosk modes are the
    # same choice and belong next to each other.
    # ----------------------------------------------------------------------- #

    multi_app_packages: Annotated[
        list[KioskApp] | None,
        # W380: by tile identity, or stacked policies would collapse the
        # console, Device Settings and Power tiles (one package) into one.
        Merge(MergeStrategy.MERGE_BY_KEY, key="package_name", identity=tile_identity)
    ] = Field(
        default=None,
        title="Kiosk apps",
        description="The apps on the kiosk home screen, in the order they appear. "
        "The ATLAS launcher is installed automatically and the device is locked to "
        "it; only these apps can be opened. The ATLAS console is always in the "
        "list and cannot be removed — in a multi-app kiosk the launcher is the "
        "only way to anything, and the person standing at a misbehaving tablet "
        "needs a route to sync, permissions and the device's own state. Move it "
        "where you want it, or dock it. A list holding nothing but the console is "
        "not a multi-app kiosk, and saves nothing. A tile can also be one of the "
        "device's own apps (Chrome, Gmail, Maps and the rest), with no library "
        "build: it is never installed, only switched on if the device has it "
        "disabled.",
        json_schema_extra={"ui_group": _MULTI, "ui_control": "kiosk_apps"},
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
    kiosk_allow_screen_capture: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = _peripheral("Screen capture", _PERIPHERAL_NOTE)
    kiosk_allow_airplane_mode: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = _peripheral("Airplane mode", _PERIPHERAL_NOTE)

    # ----------------------------------------------------------------------- #
    # Peripheral Settings — what the user may change on the device (W71)
    #
    # ⚠️ These need the ATLAS launcher, because the way to them is a Device
    # Settings tile on its home screen. A single-app kiosk has no home screen, so
    # the section is refused there rather than saved and ignored.
    # ----------------------------------------------------------------------- #

    device_setting_night_mode: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = _user_setting(
        "Night mode",
        "Let the user turn the night tint on and off and set its strength.",
    )
    device_setting_brightness: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = _user_setting(
        "Screen brightness",
        "Let the user set screen brightness, and turn automatic brightness on or off.",
        restriction="allow_brightness_change",
    )
    device_setting_screen_timeout: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = _user_setting(
        "Screen timeout",
        "Let the user choose how long the screen stays on.",
    )
    device_setting_volume: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = _user_setting(
        "Volume",
        "Let the user set media and notification volume.",
        restriction="allow_volume_change",
    )
    device_setting_flashlight: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = _user_setting(
        "Flashlight",
        "Let the user turn the torch on and off.",
    )
    device_setting_power: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = _power_setting(
        "Power off",
        "⚠️ Show a Power off row that raises Android's power menu. Needs the ATLAS "
        "power menu switched on in the device's accessibility settings — which "
        "**cannot be done from a locked device**, so grant it before the kiosk "
        "policy is assigned. Without it the row explains itself rather than "
        "working.",
    )
    device_setting_bluetooth: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = _user_setting(
        "Bluetooth",
        "Let the user turn Bluetooth on and off.",
        restriction="allow_bluetooth",
    )
    device_setting_radios_off: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = _user_setting(
        "Radios off",
        "⚠️ One switch that turns Wi-Fi and Bluetooth off together. This is **not** "
        "airplane mode and does not touch the cellular radio — no app can set "
        "airplane mode, because it needs a permission no Device Owner can grant "
        "itself. A device on mobile data stays connected.",
    )
    device_setting_wifi: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = _user_setting(
        "Wi-Fi",
        "⚠️ Let the user turn Wi-Fi on and off. Android blocks this for ordinary "
        "apps and permits it for a Device Owner; if the device refuses, the control "
        "says so rather than failing quietly.",
        restriction="allow_wifi_config",
    )

    launcher_columns: Annotated[int | None, Merge(MergeStrategy.MIN)] = Field(
        default=None,
        ge=2,
        le=8,
        title="Grid columns",
        description="How many app tiles fit across the kiosk home screen.",
        json_schema_extra={"ui_group": _LAUNCHER, "ui_unit": "columns", "ui_owned_by": "multi_app_packages"},
    )
    # W371: a designed grid of pages. ⚠️ All four grid fields (columns too)
    # are `ui_owned_by` the kiosk apps control: the layout designer beside the
    # apps renders and parses them, so the generic form leaves them out and
    # no second input can share their names. ⚠️ Rows merge to the smallest and pages to
    # the largest across policies (columns already merge to the smallest), so a
    # merged grid always fits on the device; a tile that no longer fits, or
    # clashes with another policy's, takes the first free cell.
    launcher_device_type: Annotated[
        LauncherDeviceType | None, Merge(MergeStrategy.HIGHEST_RANK)
    ] = Field(
        default=None,
        title="Designed for",
        description="Phone or tablet: decides the grid sizes on offer. Phone: 3 to 5 "
        "columns and 4 to 7 rows. Tablet: 4 to 8 columns and 3 to 6 rows.",
        json_schema_extra={"ui_group": _LAUNCHER, "ui_owned_by": "multi_app_packages"},
    )
    launcher_rows: Annotated[int | None, Merge(MergeStrategy.MIN)] = Field(
        default=None,
        ge=3,
        le=7,
        title="Grid rows",
        description="How many rows of app tiles fit down one page.",
        json_schema_extra={"ui_group": _LAUNCHER, "ui_unit": "rows", "ui_owned_by": "multi_app_packages"},
    )
    launcher_pages: Annotated[int | None, Merge(MergeStrategy.MAX)] = Field(
        default=None,
        ge=1,
        le=MAX_PAGES,
        title="Pages",
        description="Home screen pages the user swipes between. Every page needs at "
        "least one app.",
        json_schema_extra={"ui_group": _LAUNCHER, "ui_unit": "pages", "ui_owned_by": "multi_app_packages"},
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
    def _the_power_menu_needs_global_actions(self) -> "KioskSpec":
        """Refuse a Power off row on a kiosk that suppresses the power menu.

        ⚠️ `keep_power_menu` maps to `LOCK_TASK_FEATURE_GLOBAL_ACTIONS`, and with
        it off the platform suppresses the dialog this row raises. The row would
        be tapped, the accessibility action would report success, and nothing
        would appear — the most confusing failure available, because every part
        of it looks like it worked.
        """
        if self.device_setting_power and self.keep_power_menu is False:
            raise ValueError(
                "device_setting_power needs keep_power_menu allowed. With the "
                "power menu suppressed by lock task, the row is tapped, the action "
                "reports success, and no dialog appears"
            )
        return self

    # ----------------------------------------------------------------------- #
    # ⚠️ **The order of the next four validators is load-bearing** (W197).
    #
    # Pydantic runs `mode="after"` validators in the order they are defined, and
    # two of these read `multi_app_packages` to decide whether this is a
    # multi-app kiosk at all. So the list has to be *final* before they look:
    #
    #   1. `_one_tile_per_app`            refuses a duplicate — against what the
    #                                     operator submitted, not a list we widened
    #   2. `_the_console_is_always_a_tile` settles what the list actually is
    #   2'. `_system_tiles_follow_their_switches` adds or drops the agent's
    #       Device Settings and Power tiles (W380)
    #   2a. `_the_dock_holds_four`         counts the settled list's dock (W376)
    #   2a'. `_a_kiosk_is_always_designed`  gives an undesigned one a Phone grid (W377)
    #   2b. `_the_layout_fits_the_grid`   places the settled list (W371)
    #   3. `_device_settings_need_a_launcher`  read the settled list
    #   4. `_launcher_settings_need_apps`
    #
    # Out of order, a policy whose only tile was the console would pass step 3
    # and then have its list taken away by step 2, leaving Device Settings shown
    # on a kiosk with no home screen to show them on.
    # ----------------------------------------------------------------------- #

    @model_validator(mode="after")
    def _one_tile_per_app(self) -> "KioskSpec":
        """Refuse the same app twice on one home screen.

        The launcher would draw one tile either way, so a second entry cannot take
        effect — and two identical rows in the console look like the ordering did
        not save.
        """
        # W380: by identity, so the console and the agent's Device Settings and
        # Power tiles (one package) are three tiles, not a duplicate.
        seen: dict[str, int] = {}
        for app in self.multi_app_packages or []:
            seen[app.identity] = seen.get(app.identity, 0) + 1
        duplicates = sorted(name for name, count in seen.items() if count > 1)
        if duplicates:
            raise ValueError(
                f"{', '.join(duplicates)} appears more than once in the kiosk apps. "
                f"Each app gets one tile, so a second entry cannot take effect"
            )
        return self

    @model_validator(mode="after")
    def _the_console_is_always_a_tile(self) -> "KioskSpec":
        """A multi-app kiosk always carries the ATLAS console (W197).

        In a multi-app kiosk the launcher is the only way to anything, so without
        this tile there is no route from the device to sync, permissions or its
        own state — and the person standing at a misbehaving tablet is exactly
        who needs one.

        ⚠️ **The agent has always appended it** (`LauncherConfigPlan.withAgent`,
        W70), so this changes no device behaviour. What it changes is that the
        list an operator reads now says so. Previously the only way to place the
        tile was to know it existed and type it in, which the field description
        explained in a sentence nobody had reason to read.

        ⚠️ **Appended if absent, left exactly where it is if present.** An
        operator who has placed it has said where they want it, and a validator
        that re-sorted on save would move a tile under them. It is the same rule
        the agent already follows, which is why old and new agents agree.

        ⚠️ Here rather than in the form, because a form that prefills is a
        form that can be edited out. The API, an import and a tampered submission
        all reach this.

        ⚠️ **A list holding nothing but the console is no list at all.** The
        form renders this row on every kiosk page, so an untouched policy would
        otherwise save itself as a one-tile multi-app kiosk. See the ordering
        note above: this has to be settled before anything reads the list.

        Runs after :meth:`_one_tile_per_app` on purpose: an operator's duplicate
        is refused against what they submitted, not against a list this widened.
        """
        # ⚠️ One rule, not two. There was an `if not apps: return self` guard
        # above this, and a mutation sweep showed removing it changed nothing a
        # test could see — because the check below already answers for an empty
        # list, a missing one and a console-only one alike. It was a second way
        # of saying the same thing, and the two could have drifted.
        apps = self.multi_app_packages or []
        if not any(app.package_name != ATLAS_CONSOLE_PACKAGE for app in apps):
            # ⚠️ **A console on its own is not a home screen**, and this is the
            # trap the console form sets. The row is rendered on every kiosk
            # page, including a brand-new one nobody has touched, and it submits
            # its package like any other — so without this line *every* policy
            # saved with the Kiosk section open would quietly become a multi-app
            # kiosk with one tile, install the launcher, and lock the device to a
            # home screen the operator never asked for.
            #
            # Unset rather than emptied: `to_stored` uses `exclude_unset`, and a
            # field that says nothing is the honest record of an operator who
            # named nothing. An explicit `null` — or an explicit `[]` — would read
            # as a decision.
            self.multi_app_packages = None
            self.model_fields_set.discard("multi_app_packages")
            return self
        for app in apps:
            # W380: the agent's Device Settings and Power tiles are not the console.
            if app.package_name == ATLAS_CONSOLE_PACKAGE and not app.system_tile:
                # ⚠️ **The console tile carries no activity, and this is not
                # tidiness.** The agent recognises its own console tile as *this
                # package with no activity* (`LauncherConfigPlan.withAgent`) —
                # keyed that way because the Device Settings and Power tiles are
                # the same package with one (W71). A console tile naming an
                # activity therefore looks like a different tile, `withAgent`
                # finds no console, and the device ends up with two.
                #
                # Unreachable through the console, which submits an empty hidden
                # field. Reachable through the API, which is the point.
                app.activity = None
                # Unset, not null: `to_stored` excludes what was never set, and
                # an explicit `null` in a stored spec reads as a decision rather
                # than as an absence.
                app.model_fields_set.discard("activity")
                return self
        self.multi_app_packages = apps + [KioskApp(package_name=ATLAS_CONSOLE_PACKAGE)]
        return self

    @model_validator(mode="after")
    def _system_tiles_follow_their_switches(self) -> "KioskSpec":
        """W380: the Device Settings and Power tiles are on the home screen
        exactly when the policy offers them, as the agent decides
        (`DeviceSettingsPlan.offersAnything` / `OFFER_POWER`): Device Settings
        when any user control is switched on, Power when Power off is.

        Added unplaced when missing, so the designer and the layout give them
        a cell; removed when no longer offered, so a stale tile never opens a
        screen with nothing on it. ⚠️ After the console is settled (2), before
        the dock is counted (2a): a docked system tile counts like any other.
        """
        apps = self.multi_app_packages
        if not apps:
            return self
        offered = {
            DEVICE_SETTINGS_ACTIVITY: any(
                getattr(self, name) is True for name in type(self).model_fields if name.startswith("device_setting_")
            ),
            POWER_TILE_ACTIVITY: self.device_setting_power is True,
        }
        kept = [app for app in apps if not app.system_tile or offered[app.system_tile]]
        present = {app.system_tile for app in kept}
        for activity in SYSTEM_TILES:
            if offered[activity] and activity not in present:
                kept.append(KioskApp(package_name=ATLAS_CONSOLE_PACKAGE, activity=activity))
        self.multi_app_packages = kept
        return self

    @model_validator(mode="after")
    def _the_dock_holds_four(self) -> "KioskSpec":
        """The dock is one row of at most :data:`MAX_DOCK` apps (W376).

        ⚠️ After the console tile is settled, because an operator may dock the
        console itself and it counts like any other tile.
        """
        docked = [app.package_name for app in self.multi_app_packages or [] if app.favorite]
        if len(docked) > MAX_DOCK:
            raise ValueError(
                f"the dock holds {MAX_DOCK} apps, and {len(docked)} are docked "
                f"({', '.join(docked)}): move some onto the home screen"
            )
        return self

    @model_validator(mode="after")
    def _a_kiosk_is_always_designed(self) -> "KioskSpec":
        """W377: the scrolling grid is retired, so a multi-app kiosk with no
        device type is designed for a phone (operator, 2026-10-12).

        Whatever the policy said is kept where a phone allows it: its columns
        and rows are clamped to the phone's range, the defaults fill the rest,
        and it gets as many pages as its undocked apps need.

        ⚠️ Before `_the_layout_fits_the_grid`, which then places the tiles. A
        kiosk too big for :data:`MAX_PAGES` phone pages is refused there, as an
        overfull designed grid always was.
        """
        apps = self.multi_app_packages
        if not apps or self.launcher_device_type is not None:
            return self
        limits = GRID_LIMITS[LauncherDeviceType.PHONE]
        default_columns, default_rows = limits["default"]

        def clamp(value: int | None, name: str, default: int) -> int:
            low, high = limits[name]
            return default if value is None else max(low, min(high, value))

        columns = clamp(self.launcher_columns, "columns", default_columns)
        rows = clamp(self.launcher_rows, "rows", default_rows)
        undocked = sum(1 for app in apps if not app.favorite)
        pages = self.launcher_pages or max(1, -(-undocked // (columns * rows)))
        self.launcher_device_type = LauncherDeviceType.PHONE
        self.launcher_columns, self.launcher_rows = columns, rows
        # Assigned, so marked set: the stored spec says what the device draws.
        self.launcher_pages = min(pages, MAX_PAGES)
        return self

    @model_validator(mode="after")
    def _the_layout_fits_the_grid(self) -> "KioskSpec":
        """A designed grid (W371): sizes within reason for the device type, every
        position inside it and taken once, and every page used.

        ⚠️ **After the console tile is settled** (see the ordering note above):
        the console is appended without a position and placed here like any
        other unplaced tile.

        Tiles with no position take the first free cell, page by page and row
        by row, and the positions are stored, so what the console shows is what
        the device draws. Dock tiles stay off the grid.
        """
        apps = self.multi_app_packages
        if not apps:
            return self
        # W377: no undesigned kiosk reaches here; `_a_kiosk_is_always_designed`
        # gave it a Phone grid. A device type without rows is still refused.
        if self.launcher_device_type is None or self.launcher_rows is None or self.launcher_columns is None:
            raise ValueError(
                "a designed grid needs all of: what it is designed for, its columns and its rows"
            )
        limits = GRID_LIMITS[self.launcher_device_type]
        kind = self.launcher_device_type.value
        for name, value in (("columns", self.launcher_columns), ("rows", self.launcher_rows)):
            low, high = limits[name]
            if not low <= value <= high:
                raise ValueError(f"a {kind} grid has {low} to {high} {name}, not {value}")
        pages, rows, columns = self.launcher_pages or 1, self.launcher_rows, self.launcher_columns
        plural = "" if pages == 1 else "s"

        taken: dict[tuple[int, int, int], str] = {}
        for app in apps:
            if not app.placed:
                continue
            if app.page >= pages or app.row >= rows or app.column >= columns:
                raise ValueError(
                    f"{app.package_name} is placed at page {app.page + 1}, row {app.row + 1}, "
                    f"column {app.column + 1}, outside the {columns} by {rows} grid of "
                    f"{pages} page{plural}"
                )
            cell = (app.page, app.row, app.column)
            if cell in taken:
                raise ValueError(
                    f"{taken[cell]} and {app.package_name} are both placed at page "
                    f"{app.page + 1}, row {app.row + 1}, column {app.column + 1}"
                )
            taken[cell] = app.package_name

        unplaced = [app for app in apps if not app.placed and not app.favorite]
        free = [
            (p, r, c)
            for p in range(pages) for r in range(rows) for c in range(columns)
            if (p, r, c) not in taken
        ]
        if len(unplaced) > len(free):
            raise ValueError(
                f"{len(taken) + len(unplaced)} apps do not fit {pages} page{plural} of "
                f"{columns} by {rows}: add a page, or more rows or columns"
            )
        for app, (page, row, column) in zip(unplaced, free):
            app.page, app.row, app.column = page, row, column
            taken[(page, row, column)] = app.package_name

        empty = [p + 1 for p in range(pages) if not any(cell[0] == p for cell in taken)]
        if empty:
            raise ValueError(
                f"page {', '.join(map(str, empty))} has no apps: place an app there, or "
                f"use fewer pages"
            )
        return self

    @model_validator(mode="after")
    def _device_settings_need_a_launcher(self) -> "KioskSpec":
        """The way to these is a tile on the kiosk home screen.

        A single-app kiosk has no home screen, so the section would save, assign,
        report no error, and never appear.
        """
        if self.multi_app_packages:
            return self
        # ⚠️ Only **showing** a control needs a launcher (W79). Turning one off is
        # either a restriction the OS enforces everywhere or simply no row, and
        # neither wants a home screen — refusing those would have taken away a
        # single-app kiosk's ability to block Bluetooth, Wi-Fi, volume or
        # brightness at all, which it could do before the two pages merged.
        shown = sorted(
            name
            for name in type(self).model_fields
            if name.startswith("device_setting_") and getattr(self, name) is True
        )
        if shown:
            raise ValueError(
                f"{', '.join(shown)} needs a multi-app kiosk. Showing a control means "
                f"a Device Settings tile on the ATLAS launcher's home screen, and a "
                f"single-app kiosk has no home screen to put it on. Setting them to "
                f"blocked or hidden needs no launcher"
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
                "launcher_device_type",
                "launcher_rows",
                "launcher_pages",
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
