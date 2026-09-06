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
    return KioskSpec(kiosk_package=ATAK, **kwargs)


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
    assert kiosk.subtopics == (
        "single app", "multi app", "background apps", "launcher",
        "peripheral settings", "kiosk exit settings",
        "website kiosk settings", "kiosk screensaver",
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
        ("multi_app_packages", ["com.a.b"]),
        ("launcher_wallpaper_file_id", "abc123"),
        ("website_kiosk_url", "https://example.test"),
        ("screensaver_file_id", "abc123"),
        ("screensaver_idle_seconds", 60),
    ],
)
def test_the_launcher_sections_are_refused_rather_than_silently_ignored(field, value):
    """⚠️ The agent declares no `category.HOME` by design.

    There is no kiosk home screen to put a grid of apps, a wallpaper, a web view
    or a screensaver on. Saving these against the day there is one would hand an
    operator a policy that locks nothing and says so nowhere.
    """
    with pytest.raises(ValueError, match="launcher"):
        _spec(**{field: value})


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
    with pytest.raises(ValueError, match="no kiosk app is set"):
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
