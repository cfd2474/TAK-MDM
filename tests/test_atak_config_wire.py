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

"""What an ATAK Config policy actually puts on the wire (W90, chunk A4).

The last untested seam. A2 proved `render` and `merge_into_policy` by calling
them; nothing proved that a policy an operator **assigns** survives effective-
policy resolution and arrives in the signed document a device downloads. Those
are different questions, and the gap between them is where a feature works in
every unit test and reaches no tablet.

⚠️ **This is as far as it can be proven without hardware.** `SM-X520` has been
dark since 2026-09-04. Everything below is the server's half; the runbook in
`PROJECT_STATE.md` is the other half.
"""

from __future__ import annotations

import pathlib

import pytest
from sqlalchemy import select

from app.db.models import Device
from app.services import atak_config, desired_state
from tests.apk_fixtures import (
    build_apk,
    build_preference_axml,
    build_restrictions_axml,
    pref_category,
    pref_field,
)
from tests.conftest import ADMIN_HEADERS

ATAK_PACKAGE = "com.atakmap.app.civ"
ATAK = pathlib.Path("Test Files/ATAK-5.8.0.4-174b425-civSmall-release.apk")


def _atak_apk() -> bytes:
    """A stand-in ATAK carrying both halves of the real contract.

    Its settings screen, and the managed-configuration schema that declares the
    key those settings travel in — because this test is about the two meeting.
    """
    return build_apk(
        ATAK_PACKAGE,
        1,
        extra_files={
            "res/-v.xml": build_preference_axml(
                [
                    pref_category(
                        "Network",
                        pref_field("EditTextPreference", "chatPort", title="Chat Port"),
                        pref_field(
                            "CheckBoxPreference", "atakControlBluetooth", title="Bluetooth"
                        ),
                    )
                ]
            ),
            "res/Kt.xml": build_restrictions_axml(
                [(atak_config.ENTERPRISE_PREFS_KEY, 6)]
            ),
        },
    )


def _upload(client, data: bytes) -> None:
    response = client.post(
        "/api/v1/packages",
        files={"file": ("app.apk", data, "application/vnd.android.package-archive")},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code in (200, 201), response.text


def _assigned_profile(client, sections: dict, device_id: str) -> str:
    created = client.post(
        "/api/v1/profiles",
        json={"name": "ATAK baseline", "sections": sections},
        headers=ADMIN_HEADERS,
    )
    assert created.status_code == 201, created.text
    pid = created.json()["id"]

    targeted = client.put(
        f"/api/v1/profiles/{pid}/targets",
        json={"device_ids": [device_id]},
        headers=ADMIN_HEADERS,
    )
    assert targeted.status_code in (200, 201), targeted.text
    return pid


@pytest.fixture
def configured(client, db, make_device, artifact_storage):
    """A device with a real ATAK build and an assigned ATAK Config policy."""
    make_device()
    _upload(client, _atak_apk())
    device = db.scalar(select(Device))
    _assigned_profile(
        client,
        {
            "atak_config": {
                "core_prefs": [
                    {"key": "chatPort", "value": "17012"},
                    {"key": "atakControlBluetooth", "value": "true"},
                ]
            }
        },
        str(device.id),
    )
    return device


def _atak_entry(state: dict) -> dict:
    configs = state["policy"]["APP_CATALOG"]["app_configs"]
    return next(e for e in configs if e["package_name"] == ATAK_PACKAGE)


# --------------------------------------------------------------------------- #
# It reaches the wire
# --------------------------------------------------------------------------- #


def test_an_assigned_policy_puts_the_document_in_the_devices_desired_state(
    configured, db, artifact_storage
):
    """The question no unit test answers: does an *assigned* policy get there.

    Everything between — the resolver, the profile's sections, the merge — is
    exercised here for the first time as one path.
    """
    state = desired_state.build(db, configured, artifact_storage)

    document = _atak_entry(state)["values"][atak_config.ENTERPRISE_PREFS_KEY]
    assert document.startswith("<?xml version='1.0' standalone='yes'?>\r\n")
    assert '<entry key="chatPort" class="class java.lang.String">17012</entry>' in document
    assert (
        '<entry key="atakControlBluetooth" class="class java.lang.Boolean">true</entry>'
        in document
    )


def test_the_agent_is_told_the_type_it_needs_to_send_a_string(
    configured, db, artifact_storage
):
    """⚠️ The shape `PolicyApplier.applyAppConfigs` actually reads.

    It looks up `types[key]` and coerces; with no type it has to guess, and a
    guess here is a Bundle value the app cannot read. 6 is
    `RestrictionEntry.TYPE_STRING`, from ATAK's own declaration — which is why
    the merge runs before the type enrichment.
    """
    state = desired_state.build(db, configured, artifact_storage)
    entry = _atak_entry(state)

    assert entry["types"][atak_config.ENTERPRISE_PREFS_KEY] == 6


def test_no_atak_config_appears_when_the_policy_carries_none(
    client, db, make_device, artifact_storage
):
    """The negative that gives the positive its meaning: nothing is pushed at an
    app just because it is in the library."""
    make_device()
    _upload(client, _atak_apk())
    device = db.scalar(select(Device))

    state = desired_state.build(db, device, artifact_storage)

    configs = (state["policy"].get("APP_CATALOG") or {}).get("app_configs") or []
    assert not any(
        atak_config.ENTERPRISE_PREFS_KEY in (e.get("values") or {}) for e in configs
    )


def test_the_document_survives_signing(configured, db, artifact_storage, signer):
    """It travels inside the Ed25519-signed bundle (D9), so it has to be part of
    what is signed — not attached beside it."""
    bundle = desired_state.build_signed(db, configured, signer, artifact_storage)

    document = _atak_entry(bundle["desired_state"])["values"][
        atak_config.ENTERPRISE_PREFS_KEY
    ]
    assert "chatPort" in document
    assert signer.verify(bundle["desired_state"], bundle["signature"])


def test_the_same_policy_builds_the_same_bytes(configured, db, artifact_storage):
    """⚠️ ATAK de-duplicates by MD5 of the document.

    Bytes that differ run by run mean every check-in reloads ATAK's entire
    configuration — and `loadSettings` is not free, nor is it silent on the
    device. Stability here is what makes a re-push a genuine no-op.
    """
    first = _atak_entry(desired_state.build(db, configured, artifact_storage))
    second = _atak_entry(desired_state.build(db, configured, artifact_storage))

    assert (
        first["values"][atak_config.ENTERPRISE_PREFS_KEY]
        == second["values"][atak_config.ENTERPRISE_PREFS_KEY]
    )


def test_an_operators_own_atak_config_still_survives_on_the_wire(
    client, db, make_device, artifact_storage
):
    """⚠️ D92 end to end.

    The collision is only interesting once both halves are real policy: an
    App-Management configuration for ATAK and an ATAK Config policy, resolved
    together, arriving in one Bundle. `setApplicationRestrictions` replaces the
    whole thing, so losing either here is losing it on the device.
    """
    make_device()
    _upload(client, _atak_apk())
    device = db.scalar(select(Device))
    _assigned_profile(
        client,
        {
            "app_management": {
                "app_configs": [
                    {
                        "package_name": ATAK_PACKAGE,
                        "values": {"enterpriseConfigurationDataPackage": "BASE64=="},
                    }
                ]
            },
            "atak_config": {"core_prefs": [{"key": "chatPort", "value": "17012"}]},
        },
        str(device.id),
    )

    state = desired_state.build(db, device, artifact_storage)
    values = _atak_entry(state)["values"]

    assert values["enterpriseConfigurationDataPackage"] == "BASE64=="
    assert "chatPort" in values[atak_config.ENTERPRISE_PREFS_KEY]


def test_a_check_in_still_succeeds_when_the_configuration_cannot_be_built(
    client, db, make_device, artifact_storage
):
    """⚠️ The rule the whole service is written around.

    `build` runs inside the device's own request. A policy that cannot be
    expressed — here a true/false setting holding "maybe" — must cost the ATAK
    configuration and nothing else. A raised exception would turn one bad value
    into a device that cannot check in at all.
    """
    make_device()
    _upload(client, _atak_apk())
    device = db.scalar(select(Device))
    _assigned_profile(
        client,
        {"atak_config": {"core_prefs": [{"key": "atakControlBluetooth", "value": "maybe"}]}},
        str(device.id),
    )

    state = desired_state.build(db, device, artifact_storage)

    assert state["schema_version"] == desired_state.DESIRED_STATE_SCHEMA_VERSION
    configs = (state["policy"].get("APP_CATALOG") or {}).get("app_configs") or []
    assert not any(
        atak_config.ENTERPRISE_PREFS_KEY in (e.get("values") or {}) for e in configs
    )


# --------------------------------------------------------------------------- #
# Against the shipping ATAK build
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(not ATAK.exists(), reason="the ATAK APK is not in this checkout")
def test_the_real_atak_build_delivers_a_document_within_ataks_own_limit(
    client, db, make_device, artifact_storage
):
    """The bytes a tablet would really be handed, from the build it would really
    be running — and comfortably under the 64 KB ATAK's own key description
    names as the ceiling."""
    make_device()
    _upload(client, ATAK.read_bytes())
    device = db.scalar(select(Device))
    _assigned_profile(
        client,
        {
            "atak_config": {
                "core_prefs": [
                    {"key": "chatPort", "value": "17012"},
                    {"key": "atakControlBluetooth", "value": "true"},
                    {"key": "auth_flow_trust_model", "value": "PRECONFIGURED"},
                ]
            }
        },
        str(device.id),
    )

    state = desired_state.build(db, device, artifact_storage)
    document = _atak_entry(state)["values"][atak_config.ENTERPRISE_PREFS_KEY]

    # Typed from the real build's own widget classes, not from how the values look.
    assert '<entry key="chatPort" class="class java.lang.String">17012</entry>' in document
    assert (
        '<entry key="atakControlBluetooth" class="class java.lang.Boolean">true</entry>'
        in document
    )
    assert (
        '<entry key="auth_flow_trust_model" class="class java.lang.String">PRECONFIGURED</entry>'
        in document
    )
    assert 'name="com.atakmap.app.civ_preferences"' in document
    assert len(document.encode("utf-8")) < 64 * 1024
