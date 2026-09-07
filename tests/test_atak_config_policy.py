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

"""The ATAK_CONFIG policy type, and how it reaches a device (W90, chunk A2).

The interesting half is not the spec — it is D92: ATAK_CONFIG has no applier of
its own and resolves into `APP_CATALOG.app_configs`, because both end at
`setApplicationRestrictions` **for the same package** and that call replaces the
app's whole Bundle. Most of what is asserted here is that the merge is additive,
deterministic, and cannot break a check-in.
"""

from __future__ import annotations

import pathlib

import pytest
from starlette.datastructures import FormData

from app.policies import form_parse
from app.policies.registry import PolicyTypeError, registry
from app.policies.resolver import resolve
from app.services import atak_config
from tests.test_resolver import make_assignment
from tests.apk_fixtures import (
    build_apk,
    build_preference_axml,
    build_restrictions_axml,
    pref_category,
    pref_field,
)

ATAK_PACKAGE = "com.atakmap.app.civ"
PLUGIN_PACKAGE = "com.atakmap.android.uastool.plugin"

UASTOOL = pathlib.Path(
    "Test Files/ATAK-Plugin-uastool-13.0.6-74628a10-5.8.0-civ-release.apk"
)


def _atak_apk(version_code: int = 1) -> bytes:
    """A stand-in ATAK: the package name that matters, plus real settings.

    A synthetic build is right here — these tests are about the merge, and the
    scanner is proved against the shipping APK in `test_atak_prefs.py`.
    """
    document = build_preference_axml(
        [
            pref_category(
                "Network",
                pref_field("EditTextPreference", "chatPort", title="Chat Port"),
                pref_field("CheckBoxPreference", "atakControlBluetooth", title="Bluetooth"),
            )
        ]
    )
    # Also declares the managed-configuration key the document travels in, as
    # the shipping build does — that is what lets the enrichment type it.
    return build_apk(
        ATAK_PACKAGE,
        version_code,
        extra_files={
            "res/-v.xml": document,
            "res/Kt.xml": build_restrictions_axml(
                [(atak_config.ENTERPRISE_PREFS_KEY, 6)]
            ),
        },
    )


def _plugin_apk(package_name: str = PLUGIN_PACKAGE) -> bytes:
    document = build_preference_axml(
        [
            pref_category(
                "MAVLink",
                pref_field("CheckBoxPreference", "uastool.pref_cot_broadcast", title="CoT"),
                pref_field("EditTextPreference", "uastool.mavlink.pref_platform_ip", title="IP"),
            )
        ]
    )
    return build_apk(package_name, 1, extra_files={"res/-v.xml": document})


def _ingest(db, storage, data: bytes):
    from app.services import packages as package_service

    result = package_service.ingest(db, storage, data)
    db.flush()
    return result


# --------------------------------------------------------------------------- #
# The spec
# --------------------------------------------------------------------------- #


def test_a_setting_and_a_plugin_configuration_validate():
    stored = registry.validate_spec(
        "ATAK_CONFIG",
        {
            "core_prefs": [{"key": "chatPort", "value": "17012"}],
            "plugin_prefs": [
                {"package_name": PLUGIN_PACKAGE, "values": {"uastool.pref_cot_broadcast": "true"}}
            ],
        },
    )
    assert stored["core_prefs"] == [{"key": "chatPort", "value": "17012"}]


def test_a_dotted_plugin_key_is_accepted():
    """Plugins own this namespace and use dots freely."""
    registry.validate_spec(
        "ATAK_CONFIG",
        {"core_prefs": [{"key": "uastool.mavlink.mirror.udp_remote_port", "value": "14550"}]},
    )


def test_the_same_setting_twice_in_one_policy_is_refused():
    """⚠️ Not a conflict the resolver can arbitrate — a `.pref` is applied in
    order, so the second entry silently replaces the first and the console shows
    both as applied."""
    with pytest.raises(PolicyTypeError) as raised:
        registry.validate_spec(
            "ATAK_CONFIG",
            {
                "core_prefs": [
                    {"key": "chatPort", "value": "17012"},
                    {"key": "chatPort", "value": "17013"},
                ]
            },
        )
    assert "chatPort" in str(raised.value)


def test_the_same_plugin_twice_in_one_policy_is_refused():
    with pytest.raises(PolicyTypeError):
        registry.validate_spec(
            "ATAK_CONFIG",
            {
                "plugin_prefs": [
                    {"package_name": PLUGIN_PACKAGE, "values": {"a": "1"}},
                    {"package_name": PLUGIN_PACKAGE, "values": {"b": "2"}},
                ]
            },
        )


def test_a_plugin_entry_with_no_settings_is_refused():
    """⚠️ It contributes nothing to the document but still occupies the merge
    slot for that package — so a higher-ranked policy's empty entry would
    suppress a lower-ranked one's real configuration, invisibly."""
    with pytest.raises(PolicyTypeError) as raised:
        registry.validate_spec(
            "ATAK_CONFIG", {"plugin_prefs": [{"package_name": PLUGIN_PACKAGE, "values": {}}]}
        )
    assert PLUGIN_PACKAGE in str(raised.value)


# --------------------------------------------------------------------------- #
# Stacking
# --------------------------------------------------------------------------- #


def test_two_policies_compose_setting_by_setting():
    """The whole point of the policy model (D1): a network baseline and a display
    baseline stack rather than one replacing the other."""
    network = make_assignment(
        "ATAK_CONFIG",
        {"core_prefs": [{"key": "chatPort", "value": "17012"}]},
        rank=10, scope="group", name="network baseline",
    )
    display = make_assignment(
        "ATAK_CONFIG",
        {"core_prefs": [{"key": "atakControlBluetooth", "value": "true"}]},
        rank=20, scope="group", name="display baseline",
    )

    resolved = resolve("dev-1", [network, display])
    settings = {e["key"] for e in resolved.values["ATAK_CONFIG"]["core_prefs"]}

    assert settings == {"chatPort", "atakControlBluetooth"}


def test_the_higher_ranked_policy_wins_the_same_setting():
    fleet = make_assignment(
        "ATAK_CONFIG",
        {"core_prefs": [{"key": "chatPort", "value": "17012"}]},
        rank=10, scope="group", name="fleet",
    )
    device = make_assignment(
        "ATAK_CONFIG",
        {"core_prefs": [{"key": "chatPort", "value": "18000"}]},
        rank=20, scope="device", name="this device",
    )

    resolved = resolve("dev-1", [fleet, device])

    assert resolved.values["ATAK_CONFIG"]["core_prefs"] == [
        {"key": "chatPort", "value": "18000"}
    ]
    # MERGE_BY_KEY records ownership per entry rather than one winner for the
    # whole field, so the losing value is reported as overridden and named —
    # which is what makes a stacked ATAK configuration explainable rather than
    # mysterious (D4).
    record = resolved.explain("ATAK_CONFIG", "core_prefs")
    assert [o["value"] for o in record["overridden"]] == [
        {"key": "chatPort", "value": "17012"}
    ]
    assert record["overridden"][0]["source"]["policy_name"] == "fleet"
    assert record["conflict"] is True


# --------------------------------------------------------------------------- #
# The form
# --------------------------------------------------------------------------- #


def test_a_blank_value_means_not_managed_rather_than_an_empty_setting():
    """⚠️ ATAK stores what it is given. A blank submitted as a value wipes a
    callsign or a server address instead of leaving it alone — and the console
    would show it as configured."""
    form = FormData(
        [
            ("core_prefs__key", "chatPort"), ("core_prefs__value", "17012"),
            ("core_prefs__key", "locationCallsign"), ("core_prefs__value", "   "),
        ]
    )
    parsed = form_parse.parse_form("ATAK_CONFIG", form)

    assert parsed["core_prefs"] == [{"key": "chatPort", "value": "17012"}]


def test_an_untouched_form_manages_nothing():
    assert form_parse.parse_form("ATAK_CONFIG", FormData([])) == {}


def test_a_plugin_row_round_trips_through_its_json_values():
    form = FormData(
        [
            ("plugin_prefs__package_name", PLUGIN_PACKAGE),
            ("plugin_prefs__values", '{"uastool.pref_cot_broadcast": "true"}'),
        ]
    )
    parsed = form_parse.parse_form("ATAK_CONFIG", form)

    assert parsed["plugin_prefs"] == [
        {"package_name": PLUGIN_PACKAGE, "values": {"uastool.pref_cot_broadcast": "true"}}
    ]


def test_a_plugin_row_with_unreadable_values_is_dropped_not_guessed():
    form = FormData(
        [("plugin_prefs__package_name", PLUGIN_PACKAGE), ("plugin_prefs__values", "{")]
    )
    assert form_parse.parse_form("ATAK_CONFIG", form) == {}


# --------------------------------------------------------------------------- #
# Rendering, against a library
# --------------------------------------------------------------------------- #


def test_settings_become_a_document_addressed_to_the_atak_build(db, artifact_storage):
    _ingest(db, artifact_storage, _atak_apk())

    rendered = atak_config.render(
        db,
        artifact_storage,
        {"ATAK_CONFIG": {"core_prefs": [{"key": "chatPort", "value": "17012"}]}},
    )

    assert rendered.deliverable
    assert rendered.package_name == ATAK_PACKAGE
    assert '<entry key="chatPort" class="class java.lang.String">17012</entry>' in rendered.document
    assert 'name="com.atakmap.app.civ_preferences"' in rendered.document


def test_the_type_comes_from_the_build_being_deployed(db, artifact_storage):
    """D91: a checkbox is a Boolean because ATAK's own widget says so, not
    because the value looks like one."""
    _ingest(db, artifact_storage, _atak_apk())

    rendered = atak_config.render(
        db,
        artifact_storage,
        {"ATAK_CONFIG": {"core_prefs": [{"key": "atakControlBluetooth", "value": "true"}]}},
    )

    assert (
        '<entry key="atakControlBluetooth" class="class java.lang.Boolean">true</entry>'
        in rendered.document
    )


def test_a_plugin_s_settings_join_ataks_own_document(db, artifact_storage):
    """A plugin runs inside ATAK's process and writes into ATAK's store, so one
    document carries both — which is why there is no per-plugin delivery."""
    _ingest(db, artifact_storage, _atak_apk())
    _ingest(db, artifact_storage, _plugin_apk())

    rendered = atak_config.render(
        db,
        artifact_storage,
        {
            "ATAK_CONFIG": {
                "core_prefs": [{"key": "chatPort", "value": "17012"}],
                "plugin_prefs": [
                    {
                        "package_name": PLUGIN_PACKAGE,
                        "values": {"uastool.pref_cot_broadcast": "true"},
                    }
                ],
            }
        },
    )

    assert rendered.document.count("<preference ") == 1
    assert "chatPort" in rendered.document
    assert (
        '<entry key="uastool.pref_cot_broadcast" class="class java.lang.Boolean">true</entry>'
        in rendered.document
    )


def test_an_unscannable_plugin_is_still_sent_but_said_out_loud(db, artifact_storage):
    """Its settings were readable when the operator chose them. Sending them as
    text is the only class that cannot fail to parse — but a boolean delivered as
    text reads as false to the plugin, so it cannot pass silently."""
    _ingest(db, artifact_storage, _atak_apk())

    rendered = atak_config.render(
        db,
        artifact_storage,
        {
            "ATAK_CONFIG": {
                "plugin_prefs": [
                    {"package_name": "com.gone.plugin", "values": {"k": "true"}}
                ]
            }
        },
    )

    assert rendered.deliverable
    assert '<entry key="k" class="class java.lang.String">true</entry>' in rendered.document
    assert any("com.gone.plugin" in w for w in rendered.warnings)


def test_no_atak_in_the_library_is_a_warning_not_a_crash(db, artifact_storage):
    rendered = atak_config.render(
        db, artifact_storage,
        {"ATAK_CONFIG": {"core_prefs": [{"key": "chatPort", "value": "17012"}]}},
    )

    assert not rendered.deliverable
    assert rendered.warnings
    assert "app library" in rendered.warnings[0]


def test_two_atak_builds_with_nothing_to_choose_between_them_is_refused(db, artifact_storage):
    """⚠️ A device holds one ATAK; a library can hold CIV and MIL. Guessing
    would push a configuration at whichever sorted first."""
    _ingest(db, artifact_storage, _atak_apk())
    _ingest(db, artifact_storage, build_apk("com.atakmap.app.mil", 1))

    rendered = atak_config.render(
        db, artifact_storage,
        {"ATAK_CONFIG": {"core_prefs": [{"key": "chatPort", "value": "17012"}]}},
    )

    assert not rendered.deliverable
    assert "more than one ATAK build" in rendered.warnings[0]


def test_the_policys_own_required_app_settles_which_atak(db, artifact_storage):
    _ingest(db, artifact_storage, _atak_apk())
    _ingest(db, artifact_storage, build_apk("com.atakmap.app.mil", 1))

    rendered = atak_config.render(
        db,
        artifact_storage,
        {
            "APP_CATALOG": {"required_apps": [{"package_name": ATAK_PACKAGE}]},
            "ATAK_CONFIG": {"core_prefs": [{"key": "chatPort", "value": "17012"}]},
        },
    )

    assert rendered.package_name == ATAK_PACKAGE


def test_a_value_its_type_cannot_hold_never_reaches_a_check_in(db, artifact_storage):
    """⚠️ `render` runs inside the device's own request. A policy it cannot
    express must degrade to "no ATAK configuration" with a warning, never to a
    failed check-in — the tablet is not at fault."""
    _ingest(db, artifact_storage, _atak_apk())

    rendered = atak_config.render(
        db,
        artifact_storage,
        {"ATAK_CONFIG": {"core_prefs": [{"key": "atakControlBluetooth", "value": "maybe"}]}},
    )

    assert not rendered.deliverable
    assert rendered.warnings


def test_the_same_policy_renders_identical_bytes(db, artifact_storage):
    """The device de-duplicates by MD5, so unstable ordering would make every
    check-in reload ATAK's whole configuration for nothing."""
    _ingest(db, artifact_storage, _atak_apk())
    policy = {
        "ATAK_CONFIG": {
            "core_prefs": [
                {"key": "chatPort", "value": "17012"},
                {"key": "atakControlBluetooth", "value": "true"},
            ]
        }
    }
    reversed_policy = {
        "ATAK_CONFIG": {"core_prefs": list(reversed(policy["ATAK_CONFIG"]["core_prefs"]))}
    }

    assert (
        atak_config.render(db, artifact_storage, policy).document
        == atak_config.render(db, artifact_storage, reversed_policy).document
    )


# --------------------------------------------------------------------------- #
# D92: the merge into managed configuration
# --------------------------------------------------------------------------- #


def test_the_document_arrives_as_ataks_own_enterprise_key(db, artifact_storage):
    _ingest(db, artifact_storage, _atak_apk())

    merged = atak_config.merge_into_policy(
        db, artifact_storage,
        {"ATAK_CONFIG": {"core_prefs": [{"key": "chatPort", "value": "17012"}]}},
    )

    entry = next(
        e for e in merged["APP_CATALOG"]["app_configs"] if e["package_name"] == ATAK_PACKAGE
    )
    assert "chatPort" in entry["values"][atak_config.ENTERPRISE_PREFS_KEY]


def test_an_operators_own_atak_configuration_survives_the_merge(db, artifact_storage):
    """⚠️ The collision D92 exists to prevent.

    `setApplicationRestrictions` replaces the app's **whole** Bundle. An operator
    who set a data-package slot by hand must not lose it because a policy also
    carries ATAK settings — and before this merge existed, whichever writer ran
    last would have wiped the other.
    """
    _ingest(db, artifact_storage, _atak_apk())

    merged = atak_config.merge_into_policy(
        db,
        artifact_storage,
        {
            "APP_CATALOG": {
                "app_configs": [
                    {
                        "package_name": ATAK_PACKAGE,
                        "values": {"enterpriseConfigurationDataPackage": "BASE64=="},
                    }
                ]
            },
            "ATAK_CONFIG": {"core_prefs": [{"key": "chatPort", "value": "17012"}]},
        },
    )

    entry = next(
        e for e in merged["APP_CATALOG"]["app_configs"] if e["package_name"] == ATAK_PACKAGE
    )
    assert entry["values"]["enterpriseConfigurationDataPackage"] == "BASE64=="
    assert atak_config.ENTERPRISE_PREFS_KEY in entry["values"]


def test_a_hand_typed_prefs_key_loses_to_the_generated_one(db, artifact_storage):
    """Asking for the same thing twice in two places. The generated document is
    the one that matches what the ATAK Config editor shows."""
    _ingest(db, artifact_storage, _atak_apk())

    merged = atak_config.merge_into_policy(
        db,
        artifact_storage,
        {
            "APP_CATALOG": {
                "app_configs": [
                    {
                        "package_name": ATAK_PACKAGE,
                        "values": {atak_config.ENTERPRISE_PREFS_KEY: "typed by hand"},
                    }
                ]
            },
            "ATAK_CONFIG": {"core_prefs": [{"key": "chatPort", "value": "17012"}]},
        },
    )

    entry = next(
        e for e in merged["APP_CATALOG"]["app_configs"] if e["package_name"] == ATAK_PACKAGE
    )
    assert entry["values"][atak_config.ENTERPRISE_PREFS_KEY] != "typed by hand"


def test_another_apps_configuration_is_untouched(db, artifact_storage):
    _ingest(db, artifact_storage, _atak_apk())

    merged = atak_config.merge_into_policy(
        db,
        artifact_storage,
        {
            "APP_CATALOG": {
                "app_configs": [{"package_name": "com.other.app", "values": {"k": "v"}}]
            },
            "ATAK_CONFIG": {"core_prefs": [{"key": "chatPort", "value": "17012"}]},
        },
    )

    other = next(
        e for e in merged["APP_CATALOG"]["app_configs"] if e["package_name"] == "com.other.app"
    )
    assert other["values"] == {"k": "v"}


def test_a_policy_without_atak_settings_is_returned_unchanged(db, artifact_storage):
    policy = {"APP_CATALOG": {"required_apps": [{"package_name": "com.other.app"}]}}
    assert atak_config.merge_into_policy(db, artifact_storage, policy) == policy


def test_the_device_is_told_the_key_s_declared_type(db, artifact_storage):
    """⚠️ This is what the merge ordering buys.

    ATAK declares `enterpriseConfigurationPreferences` itself, so running the
    merge *before* the type enrichment gives the generated document its declared
    type with no second place that has to know what that type is. Reverse the two
    and `types` comes back empty — the agent then guesses, and a guess here is a
    configuration the app cannot read.
    """
    from app.services import desired_state

    _ingest(db, artifact_storage, _atak_apk())
    policy = desired_state._with_declared_types(
        db,
        artifact_storage,
        atak_config.merge_into_policy(
            db, artifact_storage,
            {"ATAK_CONFIG": {"core_prefs": [{"key": "chatPort", "value": "17012"}]}},
        ),
    )

    entry = next(
        e for e in policy["APP_CATALOG"]["app_configs"] if e["package_name"] == ATAK_PACKAGE
    )
    # 6 is RestrictionEntry.TYPE_STRING, from ATAK's own schema.
    assert entry["types"] == {atak_config.ENTERPRISE_PREFS_KEY: 6}


# --------------------------------------------------------------------------- #
# The real plugin, end to end
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(
    not UASTOOL.exists(), reason="the UAS Tool plugin APK is not in this checkout"
)
def test_a_real_plugin_configuration_reaches_the_managed_configuration(db, artifact_storage):
    _ingest(db, artifact_storage, _atak_apk())
    _ingest(db, artifact_storage, UASTOOL.read_bytes())

    merged = atak_config.merge_into_policy(
        db,
        artifact_storage,
        {
            "ATAK_CONFIG": {
                "plugin_prefs": [
                    {
                        "package_name": PLUGIN_PACKAGE,
                        "values": {
                            "uastool.pref_cot_broadcast": "true",
                            "uastool.pref_video_record_bitrate": "900",
                        },
                    }
                ]
            }
        },
    )

    entry = next(
        e for e in merged["APP_CATALOG"]["app_configs"] if e["package_name"] == ATAK_PACKAGE
    )
    document = entry["values"][atak_config.ENTERPRISE_PREFS_KEY]
    assert (
        '<entry key="uastool.pref_cot_broadcast" class="class java.lang.Boolean">true</entry>'
        in document
    )
