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

"""Kiosk as its own category (W59).

Kiosk used to be one field on `APP_CATALOG`. What this file mostly pins is the
set of things the category **refuses**, because every one of them would otherwise
save cleanly, assign cleanly, report no error, and lock nothing — and a kiosk
wrongly believed to be in force is worse than a visibly absent one.
"""

from __future__ import annotations

import pytest

from app.policies.registry import PolicyTypeError, registry
from app.policies.specs.kiosk import KioskSpec

ATAK = "com.atakmap.app.civ"


def _spec(**kwargs) -> KioskSpec:
    """A single-app kiosk, which is what most of these rules are about.

    Pass `kiosk_package` explicitly to override it, or use `KioskSpec` directly
    for a multi-app kiosk, which deliberately has no single app.
    """
    kwargs.setdefault("kiosk_package", ATAK)
    return KioskSpec(**kwargs)


# --------------------------------------------------------------------------- #
# It exists, and it left App Management
# --------------------------------------------------------------------------- #


def test_kiosk_is_its_own_policy_type():
    assert registry.get("KIOSK") is not None


def test_app_management_no_longer_carries_the_kiosk_app():
    """Two places to set one thing is the problem this move solved."""
    from app.policies.specs.app_catalog import AppCatalogSpec

    assert "kiosk_package" not in AppCatalogSpec.model_fields

    with pytest.raises(PolicyTypeError):
        registry.validate_spec("APP_CATALOG", {"kiosk_package": ATAK})


def test_the_creator_offers_every_sub_topic_the_operator_asked_for():
    from app.policies.creator_catalog import CATALOG

    kiosk = next(c for c in CATALOG if c.key == "kiosk")

    assert kiosk.policy_type == "KIOSK"
    # The eight the operator asked for, plus two that the work turned up:
    #   * "permitted features" — the lock-task controls were mis-filed under
    #     "kiosk exit settings", and their Hexnode screenshot showed that name
    #     means the deliberate way *out* (W65);
    #   * "night mode" — the tint is drawn by the agent over every app, so it
    #     applies to a single-app kiosk too and cannot live under "launcher"
    #     (W68);
    #   * "peripheral settings" — W71 added the operator's list of what the *user*
    #     may change from the device, and the existing page (what the *device* is
    #     allowed to do) had to be renamed "peripheral restrictions", because two
    #     sub-pages of the same name are a coin toss every time.
    assert kiosk.subtopics == (
        "single app", "multi app", "background apps", "launcher",
        "permitted features", "peripheral restrictions", "peripheral settings",
        "kiosk exit settings", "night mode", "website kiosk settings",
        "kiosk screensaver",
    )


# --------------------------------------------------------------------------- #
# What works today
# --------------------------------------------------------------------------- #


def test_the_enforceable_sections_are_accepted():
    spec = _spec(
        background_packages=["com.google.android.inputmethod.latin"],
        keep_home_button=True,
        keep_recents_button=False,
        keep_power_menu=True,
        kiosk_allow_camera=False,
        kiosk_allow_bluetooth=True,
    )

    assert spec.kiosk_package == ATAK
    assert spec.background_packages == ["com.google.android.inputmethod.latin"]
    assert spec.keep_recents_button is False
    assert spec.kiosk_allow_camera is False


# --------------------------------------------------------------------------- #
# What is refused, and why
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "field, value",
    [
        ("website_kiosk_url", "https://example.test"),
        ("screensaver_file_id", "abc123"),
        ("screensaver_idle_seconds", 60),
    ],
)
def test_the_unbuilt_sections_are_refused_rather_than_silently_ignored(field, value):
    """⚠️ The ATLAS launcher shows a grid of apps and nothing else yet.

    It has no browser shell to hold a web page in and no idle surface to draw a
    screensaver on. Saving these against the day it does would hand an operator a
    policy that locks nothing and says so nowhere.

    Multi app left this list in W68 when the launcher was built, and the launcher
    wallpaper left it by being deleted — the Wallpaper policy already sets the
    device wallpaper, and the launcher's window is transparent so it shows
    through.
    """
    with pytest.raises(ValueError, match="not built yet"):
        _spec(**{field: value})


def test_a_multi_app_kiosk_is_accepted_now_that_the_launcher_exists():
    """The other half of the test above: W68 built the launcher, so the section it
    was blocking has to actually work — a refusal that outlived its reason would
    be indistinguishable from one that is still needed."""
    spec = KioskSpec(
        multi_app_packages=[
            {"package_name": "com.atakmap.app.civ", "favorite": True},
            {"package_name": "com.android.chrome"},
        ],
        launcher_columns=5,
    )
    assert [a.package_name for a in spec.multi_app_packages] == [
        "com.atakmap.app.civ",
        "com.android.chrome",
    ]
    assert spec.multi_app_packages[0].favorite is True
    assert spec.launcher_columns == 5


def test_a_multi_app_kiosk_needs_no_single_kiosk_app():
    """⚠️ The trap this guards. Every kiosk field is refused unless there is
    something to lock to, and that check knew only about `kiosk_package` — so
    before W68 amended it, a perfectly good multi-app kiosk was rejected as
    unconfigured."""
    spec = KioskSpec(
        multi_app_packages=[{"package_name": "com.a.b"}], keep_power_menu=False
    )
    assert spec.kiosk_package is None
    assert spec.keep_power_menu is False


def test_launcher_appearance_without_apps_is_refused():
    """Set with no apps they configure a home screen that does not exist, and an
    operator reading them back would believe this device has one."""
    with pytest.raises(ValueError, match="only applies to a multi-app kiosk"):
        KioskSpec(kiosk_package=ATAK, launcher_columns=4)


def test_the_same_app_cannot_hold_two_tiles():
    """The launcher draws one tile either way, so a second entry cannot take
    effect — and two identical rows look like the ordering did not save."""
    with pytest.raises(ValueError, match="more than once"):
        KioskSpec(
            multi_app_packages=[{"package_name": "com.a"}, {"package_name": "com.a"}]
        )


def test_night_settings_without_night_mode_are_refused():
    """A tint colour and strength with the tint switched off configure nothing."""
    with pytest.raises(ValueError, match="only applies when night mode is on"):
        _spec(kiosk_night_hue="red")


def test_notifications_cannot_be_asked_for_without_the_home_button():
    """Android rejects the combination outright, and from Android 14 a rejected
    feature set takes the package allowlist down with it — so the device would end
    up with no kiosk at all rather than a kiosk missing its notifications."""
    with pytest.raises(ValueError, match="home button"):
        _spec(keep_notifications=True, keep_home_button=False)


def test_kiosk_settings_without_a_kiosk_app_are_refused():
    """Everything else here describes how the kiosk behaves. With no app to lock
    to they describe nothing, and the policy would look configured while doing
    nothing at all."""
    with pytest.raises(ValueError, match="nothing is set to lock to"):
        KioskSpec(keep_power_menu=False, kiosk_allow_camera=False)


def test_an_empty_kiosk_policy_is_fine():
    """"No kiosk" has to remain expressible — it is how a device is released."""
    assert KioskSpec().kiosk_package is None


# --------------------------------------------------------------------------- #
# Merge behaviour
# --------------------------------------------------------------------------- #


def test_two_kiosk_apps_still_conflict_loudly():
    """There is no sane merge of two kiosk apps, so one has to lose visibly. The
    strategy came across with the field."""
    from app.policies.strategies import MergeStrategy

    field = KioskSpec.model_fields["kiosk_package"]
    merge = next(m for m in field.metadata if hasattr(m, "strategy"))

    assert merge.strategy is MergeStrategy.HIGHEST_RANK


def test_background_apps_accumulate_across_policies():
    """Two policies each adding a keyboard should end with both, not one — this is
    an allowlist, and dropping an entry breaks the user out of lock task."""
    from app.policies.strategies import MergeStrategy

    field = KioskSpec.model_fields["background_packages"]
    merge = next(m for m in field.metadata if hasattr(m, "strategy"))

    assert merge.strategy is MergeStrategy.UNION


# --------------------------------------------------------------------------- #
# Single app: pick an app, or an app with an activity (W61)
# --------------------------------------------------------------------------- #


def test_the_kiosk_app_is_picked_from_uploaded_apps():
    """It rendered as a blank text box, which told an operator nothing about what
    to type or which apps were even available."""
    from app.policies.form_schema import form_fields

    field = next(f for f in form_fields("KIOSK") if f.name == "kiosk_package")

    assert field.control == "kiosk_app"


def test_an_activity_can_be_named_alongside_the_app():
    spec = _spec(kiosk_activity="com.atakmap.app.ATAKActivity")

    assert spec.kiosk_activity == "com.atakmap.app.ATAKActivity"
    assert spec.kiosk_restrict_to_activity is None


def test_restricting_to_an_activity_needs_an_activity_to_restrict_to():
    """"This activity only" says nothing without naming the activity."""
    with pytest.raises(ValueError, match="needs an activity class"):
        _spec(kiosk_restrict_to_activity=True)


def test_the_activity_fields_ride_with_the_app_in_the_form():
    """All three belong to the Single app sub-page, so they are edited together
    rather than scattered."""
    from app.policies.form_schema import form_fields

    groups = {
        f.name: f.group
        for f in form_fields("KIOSK")
        if f.name in ("kiosk_package", "kiosk_activity", "kiosk_restrict_to_activity")
    }

    assert set(groups.values()) == {"Single app"}


# --------------------------------------------------------------------------- #
# The activity dropdown (W62)
# --------------------------------------------------------------------------- #


ATAK_APK = "Test Files/ATAK-5.8.0.4-174b425-civSmall-release.apk"


def test_the_activity_field_is_a_dropdown_not_a_text_box():
    from app.policies.form_schema import form_fields

    field = next(f for f in form_fields("KIOSK") if f.name == "kiosk_activity")

    assert field.control == "activity_choice"


@pytest.mark.skipif(
    not __import__("pathlib").Path(ATAK_APK).exists(),
    reason="the ATAK APK is not in this checkout",
)
def test_activities_are_read_from_the_apk_with_launchers_marked(client, db, artifact_storage):
    """The names are facts about the build, so the operator picks rather than
    types a class from memory. ATAK's two launchers — Civ and Mil — are exactly
    the distinction that matters when locking a device to one of them.
    """
    import pathlib

    from app.services.packages import declared_activities
    from tests.conftest import ADMIN_HEADERS

    client.post(
        "/api/v1/packages",
        files={"file": ("atak.apk", pathlib.Path(ATAK_APK).read_bytes(), "application/octet-stream")},
        headers=ADMIN_HEADERS,
    )

    found = declared_activities(db, artifact_storage, "com.atakmap.app.civ")

    assert len(found) > 5
    launchers = [a["name"] for a in found if a["launcher"]]
    assert "com.atakmap.app.ATAKActivityCiv" in launchers
    # Launchers sort first: the screen a user would normally arrive at is almost
    # always the one a kiosk wants.
    assert found[0]["launcher"] is True


def test_an_unknown_package_yields_an_empty_list_rather_than_an_error(db, artifact_storage):
    """A dropdown with nothing in it is a true answer; a 500 is not."""
    from app.services.packages import declared_activities

    assert declared_activities(db, artifact_storage, "com.not.uploaded") == []


# --------------------------------------------------------------------------- #
# A kiosk app installs itself (W63)
# --------------------------------------------------------------------------- #


def test_a_kiosk_app_is_required_without_being_listed_twice():
    """Reported from hardware: "the app designated for kiosk mode not installed,
    not engaging". The policy was right; the device had nothing to lock to.

    Naming a kiosk app *is* an instruction to install it — asking an operator to
    also add it under required apps is a second step that exists only to be
    forgotten.
    """
    from app.services.effective_policy import resolve_required_apps

    class _NoPackages:
        def scalar(self, *_a, **_k):
            return None

    resolved = resolve_required_apps(
        _NoPackages(), {"KIOSK": {"kiosk_package": "com.atakmap.app.civ"}}
    )

    assert [entry["package_name"] for entry in resolved] == ["com.atakmap.app.civ"]
    # Nothing uploaded, so it reports why rather than being dropped.
    assert resolved[0]["available"] is False


def test_an_explicit_required_entry_keeps_its_own_version_pin():
    """An operator who pinned a build meant it. The kiosk default only covers the
    case where nobody said anything at all."""
    from app.services.effective_policy import resolve_required_apps

    class _NoPackages:
        def scalar(self, *_a, **_k):
            return None

    resolved = resolve_required_apps(
        _NoPackages(),
        {
            "KIOSK": {"kiosk_package": "com.atakmap.app.civ"},
            "APP_CATALOG": {
                "required_apps": [
                    {"package_name": "com.atakmap.app.civ", "min_version_code": 52400}
                ]
            },
        },
    )

    assert len(resolved) == 1, "the kiosk app was required twice"
    assert "52400" in resolved[0]["reason"], resolved[0]


def test_no_kiosk_app_adds_nothing():
    from app.services.effective_policy import resolve_required_apps

    class _NoPackages:
        def scalar(self, *_a, **_k):
            return None

    assert resolve_required_apps(_NoPackages(), {"KIOSK": {}}) == []
    assert resolve_required_apps(_NoPackages(), {}) == []


# --------------------------------------------------------------------------- #
# Kiosk exit settings (W65)
# --------------------------------------------------------------------------- #


def test_exit_settings_are_their_own_sub_page_and_the_lock_task_ones_moved():
    """⚠️ The lock-task features were mis-filed under "Kiosk exit settings".

    They say what a locked-in user can still *reach*; leaving kiosk deliberately
    is a different question, and the operator's screenshot is what made that
    plain. They now live under Permitted features.
    """
    from app.policies.form_schema import sub_pages

    pages = {p.label: [f.name for f in p.fields] for p in sub_pages("KIOSK")}

    assert "Permitted features" in pages
    assert "keep_home_button" in pages["Permitted features"]
    assert "keep_power_menu" in pages["Permitted features"]

    exit_fields = pages["Kiosk exit settings"]
    assert "allow_manual_exit" in exit_fields
    assert "exit_password" in exit_fields
    assert "exit_tap_count" in exit_fields
    assert "keep_home_button" not in exit_fields


def test_a_full_exit_configuration_is_accepted():
    spec = _spec(
        allow_manual_exit=True,
        exit_password="4242",
        exit_tap_count=10,
        reboot_tap_to_exit=True,
        relaunch_after_reboot_seconds=20,
        auto_reenter_kiosk=False,
    )

    assert spec.exit_tap_count == 10
    assert spec.relaunch_after_reboot_seconds == 20
    assert spec.auto_reenter_kiosk is False


def test_allowing_a_manual_exit_requires_a_passcode():
    """An exit gesture with no gate is a kiosk anyone can tap their way out of.

    Refused rather than defaulted: a chosen passcode would be one nobody knows,
    and no passcode would be a kiosk in name only.
    """
    with pytest.raises(ValueError, match="needs an exit passcode"):
        _spec(allow_manual_exit=True)


@pytest.mark.parametrize(
    "field, value",
    [("exit_tap_count", 10), ("reboot_tap_to_exit", True), ("auto_reenter_kiosk", True)],
)
def test_exit_details_without_a_manual_exit_are_refused(field, value):
    """Read back, they would tell an operator there is a way out of this device."""
    with pytest.raises(ValueError, match="only apply when manually exiting"):
        _spec(**{field: value})


def test_the_passcode_has_a_floor_but_is_not_pretending_to_be_a_secret():
    """Four characters is enough to stop idle tapping, which is all it is for —
    it travels in the policy the device holds and anyone with adb can read it."""
    with pytest.raises(ValueError):
        _spec(allow_manual_exit=True, exit_password="12")

    assert _spec(allow_manual_exit=True, exit_password="1234").exit_password == "1234"


def test_a_relaunch_delay_does_not_need_the_manual_exit():
    """It is useful on its own — an engineer wants a moment after a reboot before
    the device locks again, whether or not a passcode exit exists."""
    assert _spec(relaunch_after_reboot_seconds=30).relaunch_after_reboot_seconds == 30


# --------------------------------------------------------------------------- #
# Peripheral Settings — what the user may change on the device (W71)
# --------------------------------------------------------------------------- #


def _multi(**kwargs) -> KioskSpec:
    """A multi-app kiosk, which is what the Device Settings tile needs."""
    kwargs.setdefault("multi_app_packages", [{"package_name": ATAK}])
    return KioskSpec(**kwargs)


def test_nothing_is_offered_to_the_user_by_default():
    """A kiosk shows nothing the operator did not ask for. The alternative —
    every control appearing unless switched off — puts settings on locked devices
    whose operator never considered the question."""
    spec = _multi()
    offered = [
        name for name in KioskSpec.model_fields
        if name.startswith("device_setting_") and getattr(spec, name)
    ]
    assert offered == []


def test_a_control_the_device_is_forbidden_to_change_is_refused():
    """⚠️ The contradiction is invisible on the device: the slider is drawn, the
    user drags it, and Android silently refuses because the restriction is in
    force. That reads as a broken tablet, and each console page looks correct on
    its own."""
    with pytest.raises(ValueError, match="needs kiosk_allow_volume_change"):
        _multi(device_setting_volume=True, kiosk_allow_volume_change=False)


def test_a_control_whose_permission_is_allowed_is_fine():
    """The other half — the validator must not refuse the normal case."""
    spec = _multi(device_setting_volume=True, kiosk_allow_volume_change=True)
    assert spec.device_setting_volume is True


def test_a_control_with_no_matching_restriction_is_unconstrained():
    """Night mode, screen timeout and the flashlight have no peripheral
    restriction to contradict, so nothing gates them."""
    spec = _multi(device_setting_night_mode=True, device_setting_flashlight=True)
    assert spec.device_setting_night_mode is True


def test_device_settings_need_a_multi_app_kiosk():
    """The way to them is a tile on the launcher's home screen, and a single-app
    kiosk has no home screen to put it on — so the section would save, assign,
    report no error and never appear."""
    with pytest.raises(ValueError, match="needs a multi-app kiosk"):
        KioskSpec(kiosk_package=ATAK, device_setting_night_mode=True)


# --------------------------------------------------------------------------- #
# Bluetooth and Radios off (W72)
# --------------------------------------------------------------------------- #


def test_bluetooth_control_needs_bluetooth_allowed():
    """Same rule as volume and brightness: a control the device is forbidden to
    act on is drawn, tapped, and silently ignored."""
    with pytest.raises(ValueError, match="needs kiosk_allow_bluetooth"):
        _multi(device_setting_bluetooth=True, kiosk_allow_bluetooth=False)


def test_radios_off_needs_both_radios_allowed():
    """⚠️ The one control that touches two restrictions, which the single-permission
    map cannot express. Half-working is the worst outcome: the user taps once
    expecting to go quiet, one radio stays up, and nothing says which."""
    with pytest.raises(ValueError, match="kiosk_allow_wifi_config"):
        _multi(device_setting_radios_off=True, kiosk_allow_wifi_config=False)
    with pytest.raises(ValueError, match="kiosk_allow_bluetooth"):
        _multi(device_setting_radios_off=True, kiosk_allow_bluetooth=False)


def test_radios_off_names_both_when_both_are_blocked():
    """The message has to name both, or the operator fixes one and hits the same
    refusal again."""
    with pytest.raises(ValueError, match="wifi_config and kiosk_allow_bluetooth"):
        _multi(
            device_setting_radios_off=True,
            kiosk_allow_wifi_config=False,
            kiosk_allow_bluetooth=False,
        )


def test_radios_off_is_accepted_when_both_radios_are_allowed():
    spec = _multi(
        device_setting_radios_off=True,
        kiosk_allow_wifi_config=True,
        kiosk_allow_bluetooth=True,
    )
    assert spec.device_setting_radios_off is True


def test_radios_off_is_not_airplane_mode_and_says_so():
    """⚠️ An operator who believed this silenced a device that was still on
    cellular would be worse off than with no control at all, so the field itself
    has to say what it does not do."""
    field = KioskSpec.model_fields["device_setting_radios_off"]
    assert "not" in field.description.lower()
    assert "airplane" in field.description.lower()
    assert "cellular" in field.description.lower()
