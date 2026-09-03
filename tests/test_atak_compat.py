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

"""Whether a plugin matches the ATAK it will sit beside.

The failure this prevents is quiet: a plugin built for the wrong ATAK installs
successfully and then never appears, which reads as an MDM fault and is not one.

The rules are as much about **not** warning as about warning. A check that fires
on every ordinary app is one an operator learns to ignore, and then it protects
nothing.
"""

from __future__ import annotations

import uuid

import pytest

from app.services import atak_compat
from app.services import packages as package_service
from tests.apk_fixtures import build_apk, make_signing_certificate


# --------------------------------------------------------------------------- #
# Reading the two version strings
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "plugin_api,expected",
    [
        ("com.atakmap.app@5.5.0.CIV", "5.5.0"),
        ("com.atakmap.app@5.8.0.CIV", "5.8.0"),
        ("com.atakmap.app@5.8.0.MIL", "5.8.0"),  # flavour is not the version
        ("com.atakmap.app@5.8.0", "5.8.0"),
        (None, None),
        ("", None),
        ("nonsense", None),
    ],
)
def test_a_plugins_target_is_read_from_its_plugin_api(plugin_api, expected):
    assert atak_compat.plugin_target(plugin_api) == expected


@pytest.mark.parametrize(
    "version_name,expected",
    [
        # ATAK carries a fourth component and build metadata; a plugin targets
        # three. Comparing raw strings would call every pairing a mismatch.
        ("5.8.0.4 (174b425)[playstore]", "5.8.0"),
        ("5.5.0.1", "5.5.0"),
        ("5.8.0", "5.8.0"),
        (None, None),
        ("", None),
        ("weird", None),
    ],
)
def test_ataks_line_ignores_its_build_metadata(version_name, expected):
    assert atak_compat.atak_line(version_name) == expected


def test_the_two_forms_agree_for_the_same_release():
    """The whole check rests on this pairing being comparable."""
    assert atak_compat.atak_line("5.8.0.4 (174b425)[playstore]") == atak_compat.plugin_target(
        "com.atakmap.app@5.8.0.CIV"
    )


@pytest.mark.parametrize(
    "package_name,expected",
    [
        ("com.atakmap.app", True),
        ("com.atakmap.app.civ", True),
        ("com.atakmap.android.uastool.plugin", False),
        ("com.example.thing", False),
        (None, False),
    ],
)
def test_atak_itself_is_recognised(package_name, expected):
    assert atak_compat.is_atak(package_name) is expected


# --------------------------------------------------------------------------- #
# When to warn
# --------------------------------------------------------------------------- #


def test_a_plugin_for_another_atak_line_is_flagged():
    found = atak_compat.check(
        atak_version="5.8.0",
        plugins={"com.atakmap.android.uastool.plugin": "com.atakmap.app@5.5.0.CIV"},
    )

    assert len(found) == 1
    assert found[0].plugin_target == "5.5.0"
    assert found[0].atak_version == "5.8.0"


def test_a_matching_plugin_is_silent():
    assert atak_compat.check(
        atak_version="5.8.0",
        plugins={"com.plugin": "com.atakmap.app@5.8.0.CIV"},
    ) == []


def test_the_flavour_does_not_make_a_mismatch():
    """CIV and MIL of the same release share a plugin API."""
    assert atak_compat.check(
        atak_version="5.8.0",
        plugins={"com.plugin": "com.atakmap.app@5.8.0.MIL"},
    ) == []


# --------------------------------------------------------------------------- #
# When to stay quiet — the half that keeps the warning worth reading
# --------------------------------------------------------------------------- #


def test_an_ordinary_app_is_never_flagged():
    """Most packages are not ATAK plugins and have no plugin-api at all."""
    assert atak_compat.check(atak_version="5.8.0", plugins={"com.example.app": None}) == []


def test_nothing_is_claimed_when_the_atak_version_is_unknown():
    """No ATAK in the policy and none reported by the device: there is nothing to
    compare against, and guessing would be worse than silence."""
    assert atak_compat.check(
        atak_version=None,
        plugins={"com.plugin": "com.atakmap.app@5.5.0.CIV"},
    ) == []


def test_an_unparseable_plugin_api_is_ignored_rather_than_guessed():
    assert atak_compat.check(
        atak_version="5.8.0", plugins={"com.plugin": "something-else-entirely"}
    ) == []


def test_several_mismatches_come_back_in_a_stable_order():
    found = atak_compat.check(
        atak_version="5.8.0",
        plugins={
            "com.z.plugin": "com.atakmap.app@5.5.0.CIV",
            "com.a.plugin": "com.atakmap.app@5.4.0.CIV",
            "com.m.plugin": "com.atakmap.app@5.8.0.CIV",  # fine
        },
    )
    assert [m.package_name for m in found] == ["com.a.plugin", "com.z.plugin"]


# --------------------------------------------------------------------------- #
# What the operator reads
# --------------------------------------------------------------------------- #


def test_the_message_says_what_will_happen_not_just_that_it_is_wrong():
    message = atak_compat.check(
        atak_version="5.8.0", plugins={"com.plugin": "com.atakmap.app@5.5.0.CIV"}
    )[0].message

    assert "5.5.0" in message and "5.8.0" in message
    # The symptom is the useful part: it installs, then silently does not appear.
    assert "not appear" in message


def test_the_message_distinguishes_a_policy_from_a_device():
    """"the policy installs ATAK 5.8.0" and "the device has ATAK 5.8.0" are
    different claims, and only one of them is evidence."""
    plugins = {"com.plugin": "com.atakmap.app@5.5.0.CIV"}

    from_policy = atak_compat.check(atak_version="5.8.0", plugins=plugins)[0].message
    from_device = atak_compat.check(
        atak_version="5.8.0", plugins=plugins, source="device"
    )[0].message

    assert "the policy installs" in from_policy
    assert "the device has" in from_device


# --------------------------------------------------------------------------- #
# Reading it off a real APK, and what it does to publishing
# --------------------------------------------------------------------------- #


def test_plugin_api_is_captured_at_upload(db, artifact_storage):
    apk = build_apk("com.plugin", 1, "1.0", plugin_api="com.atakmap.app@5.5.0.CIV")
    result = package_service.ingest(db, artifact_storage, apk)
    db.flush()

    assert result.version.plugin_api == "com.atakmap.app@5.5.0.CIV"


def test_an_app_with_no_plugin_api_records_none(db, artifact_storage):
    result = package_service.ingest(db, artifact_storage, build_apk("com.example", 1))
    db.flush()

    assert result.version.plugin_api is None


def test_builds_for_different_atak_lines_are_not_ranked_against_each_other(
    db, artifact_storage
):
    """The live case: UAS Tool for ATAK 5.8.0 carries a *lower* versionCode than the
    5.5.0 build. Ranking them would publish whichever number was bigger."""
    cert = make_signing_certificate()
    package_service.ingest(
        db,
        artifact_storage,
        build_apk("com.plugin", 1787086923, "13.0.6", certificate_der=cert,
                  plugin_api="com.atakmap.app@5.5.0.CIV"),
    )
    other_line = package_service.ingest(
        db,
        artifact_storage,
        build_apk("com.plugin", 1787086761, "13.0.6", certificate_der=cert,
                  plugin_api="com.atakmap.app@5.8.0.CIV"),
    )
    db.flush()

    assert other_line.version.published is False


def test_a_higher_build_on_the_same_line_still_publishes(db, artifact_storage):
    """Within one ATAK line the sequence is real and must keep working."""
    cert = make_signing_certificate()
    package_service.ingest(
        db, artifact_storage,
        build_apk("com.plugin", 100, certificate_der=cert, plugin_api="com.atakmap.app@5.5.0.CIV"),
    )
    newer = package_service.ingest(
        db, artifact_storage,
        build_apk("com.plugin", 200, certificate_der=cert, plugin_api="com.atakmap.app@5.5.0.CIV"),
    )
    db.flush()

    assert newer.version.published is True


def test_backfill_reads_plugin_api_from_stored_artifacts(db, artifact_storage):
    """Versions uploaded before the column existed."""
    result = package_service.ingest(
        db, artifact_storage,
        build_apk("com.plugin", 1, plugin_api="com.atakmap.app@5.5.0.CIV"),
    )
    db.flush()
    result.version.plugin_api = None
    db.flush()

    assert package_service.backfill_plugin_api(db, artifact_storage) == 1
    assert result.version.plugin_api == "com.atakmap.app@5.5.0.CIV"


# --------------------------------------------------------------------------- #
# Truth B: what the device actually has
# --------------------------------------------------------------------------- #


def assign_apps(client, make_policy, assign, device_id, required):
    policy = make_policy("Apps", "APP_CATALOG", {"required_apps": required})
    assign(policy["id"], device_id)


def test_a_device_reports_its_atak_at_checkin(client, db, enrolled, mtls_headers):
    session = enrolled()
    headers = mtls_headers(session["certificate_pem"])

    client.post(
        "/api/v1/device/checkin",
        json={
            "state_version": 0,
            "atak_package": "com.atakmap.app.civ",
            "atak_version": "5.8.0.4 (174b425)[playstore]",
        },
        headers=headers,
    )

    db.expire_all()
    from app.db.models import Device

    device = db.get(Device, uuid.UUID(session["device_id"]))
    assert device.atak_version == "5.8.0.4 (174b425)[playstore]"
    assert device.atak_package == "com.atakmap.app.civ"


def test_an_agent_too_old_to_report_does_not_erase_what_is_known(
    client, db, enrolled, mtls_headers
):
    """Absent is not "no ATAK": an older agent sends nothing, and overwriting on
    every check-in would wipe a good record and silently stop the warnings."""
    session = enrolled()
    headers = mtls_headers(session["certificate_pem"])
    client.post(
        "/api/v1/device/checkin",
        json={"state_version": 0, "atak_package": "com.atakmap.app.civ",
              "atak_version": "5.8.0.4"},
        headers=headers,
    )
    client.post("/api/v1/device/checkin", json={"state_version": 0}, headers=headers)

    db.expire_all()
    from app.db.models import Device

    assert db.get(Device, uuid.UUID(session["device_id"])).atak_version == "5.8.0.4"


def test_a_plugin_for_another_atak_is_flagged_against_the_device(
    client, db, artifact_storage, enrolled, make_policy, assign
):
    """The operator's example: UAS Tool built for 5.5.0, ATAK 5.8.0 installed."""
    session = enrolled()
    package_service.ingest(
        db, artifact_storage,
        build_apk("com.plugin", 1, plugin_api="com.atakmap.app@5.5.0.CIV"),
    )
    db.commit()
    assign_apps(client, make_policy, assign, session["device_id"],
                [{"package_name": "com.plugin"}])
    db.commit()

    from app.db.models import Device

    device = db.get(Device, uuid.UUID(session["device_id"]))
    device.atak_version = "5.8.0.4 (174b425)[playstore]"
    db.commit()

    found = atak_compat.for_device(db, device)
    assert [m.package_name for m in found] == ["com.plugin"]
    assert found[0].source == "device"


def test_a_matching_plugin_raises_nothing_against_the_device(
    client, db, artifact_storage, enrolled, make_policy, assign
):
    session = enrolled()
    package_service.ingest(
        db, artifact_storage,
        build_apk("com.plugin", 1, plugin_api="com.atakmap.app@5.8.0.CIV"),
    )
    db.commit()
    assign_apps(client, make_policy, assign, session["device_id"],
                [{"package_name": "com.plugin"}])
    db.commit()

    from app.db.models import Device

    device = db.get(Device, uuid.UUID(session["device_id"]))
    device.atak_version = "5.8.0.4"
    db.commit()

    assert atak_compat.for_device(db, device) == []


def test_a_device_that_has_not_reported_atak_claims_nothing(
    client, db, artifact_storage, enrolled, make_policy, assign
):
    """Unknown is not a clean bill of health, and must not read as one."""
    session = enrolled()
    package_service.ingest(
        db, artifact_storage,
        build_apk("com.plugin", 1, plugin_api="com.atakmap.app@5.5.0.CIV"),
    )
    db.commit()
    assign_apps(client, make_policy, assign, session["device_id"],
                [{"package_name": "com.plugin"}])
    db.commit()

    from app.db.models import Device

    assert atak_compat.for_device(db, db.get(Device, uuid.UUID(session["device_id"]))) == []


def test_the_device_page_shows_the_mismatch_and_names_the_atak(
    client, db, artifact_storage, enrolled, make_policy, assign
):
    session = enrolled()
    package_service.ingest(
        db, artifact_storage,
        build_apk("com.plugin", 1, plugin_api="com.atakmap.app@5.5.0.CIV"),
    )
    db.commit()
    assign_apps(client, make_policy, assign, session["device_id"],
                [{"package_name": "com.plugin"}])
    from app.db.models import Device

    db.get(Device, uuid.UUID(session["device_id"])).atak_version = "5.8.0.4 (174b425)[playstore]"
    db.commit()

    from tests.conftest import ADMIN_HEADERS

    body = client.get(f"/devices/{session['device_id']}", headers=ADMIN_HEADERS).text
    text = " ".join(body.split())

    assert "This device reports ATAK" in text
    assert "built for ATAK 5.5.0" in text
    assert "the device has ATAK 5.8.0" in text
