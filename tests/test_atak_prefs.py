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

"""Reading ATAK's settings out of an APK, and writing the `.pref` it imports (W90).

Two halves, tested against two kinds of evidence:

* **The scanner** is proved against the **real ATAK APK** wherever the answer
  depends on how Android actually compiles resources — shrunk resource names,
  `@string` titles, `entries`/`entryValues` arrays, booleans stored as 0/1.
  Synthetic fixtures cannot lie about structure but they cannot corroborate any
  of that; only the shipping build can.
* **The generator** is proved byte-for-byte, because the bytes are the contract.
  `PreferenceControl.loadSettings` switches on the `class` attribute verbatim and
  parses numbers unguarded, so a wrong byte is not a cosmetic difference — it is
  a configuration that half-applies on a tablet and retries forever.
"""

from __future__ import annotations

import pathlib
import zipfile

import pytest

from app.artifacts import pref_screens as ps
from app.services import atak_pref
from tests.apk_fixtures import (
    build_apk,
    build_preference_axml,
    pref_category,
    pref_field,
)

ATAK = pathlib.Path("Test Files/ATAK-5.8.0.4-174b425-civSmall-release.apk")
UASTOOL = pathlib.Path(
    "Test Files/ATAK-Plugin-uastool-13.0.6-74628a10-5.8.0-civ-release.apk"
)

needs_atak = pytest.mark.skipif(
    not ATAK.exists(), reason="the ATAK APK is not in this checkout"
)
needs_uastool = pytest.mark.skipif(
    not UASTOOL.exists(), reason="the UAS Tool plugin APK is not in this checkout"
)


def _apk_with(*documents: bytes, package_name: str = "com.example.plugin", dex: bytes | None = None):
    """An APK carrying preference documents at obfuscated `res/` paths.

    Named the way resource shrinking names them, so no test can accidentally pass
    because of a path that looks like `res/xml/prefs.xml`.
    """
    extra = {f"res/{chr(ord('a') + i)}.xml": doc for i, doc in enumerate(documents)}
    if dex is not None:
        # classes2.dex, not classes.dex: `build_apk` already writes one, and two
        # zip entries under the same name is a malformed archive.
        extra["classes2.dex"] = dex
    return build_apk(package_name, 1, extra_files=extra)


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #


def test_nonsense_bytes_declare_nothing():
    schema = ps.discover(b"not even a zip", "com.example.plugin")
    assert schema.declares_any is False
    assert schema.field_count == 0


def test_a_layout_is_not_mistaken_for_a_settings_screen():
    """Every `res/` XML is parsed, so the root-element check is the only thing
    stopping a layout or a drawable being read as a settings document."""
    assert ps.parse_preference_xml(b"\x00\x01 not binary xml", "res/a.xml") is None


def test_a_screen_of_only_action_rows_is_not_a_settings_screen():
    """ATAK has 17 such screens — "Clear History", "Export Chat History".

    Surfacing them would invite an operator to configure a button, and a category
    that lists nothing but buttons reads as a broken scanner.
    """
    document = build_preference_axml(
        [
            pref_field("com.atakmap.android.gui.PanPreference", "clearHistory", title="Clear"),
            pref_field("Preference", "exportHistory", title="Export"),
        ]
    )
    assert ps.parse_preference_xml(document, "res/a.xml") is None


def test_fields_are_filed_under_the_category_they_are_nested_in():
    document = build_preference_axml(
        [
            pref_category(
                "Network",
                pref_field("EditTextPreference", "chatAddress", title="Chat Address"),
            ),
            pref_category(
                "Display",
                pref_field("CheckBoxPreference", "showGrid", title="Show Grid"),
            ),
        ]
    )
    screen = ps.parse_preference_xml(document, "res/a.xml")

    assert [section.title for section in screen.sections] == ["Network", "Display"]
    assert [f.key for f in screen.sections[0].fields] == ["chatAddress"]
    assert [f.key for f in screen.sections[1].fields] == ["showGrid"]


def test_a_field_outside_every_category_is_not_filed_under_the_last_one():
    """⚠️ The bug this exists to catch.

    Tracking "the category seen most recently" and appending to it regardless of
    nesting files a trailing top-level field under a heading it is not part of —
    and the console then tells the operator that setting belongs to a section it
    does not.
    """
    document = build_preference_axml(
        [
            pref_category(
                "Network",
                pref_field("EditTextPreference", "chatAddress", title="Chat Address"),
            ),
            pref_field("CheckBoxPreference", "loose", title="Loose"),
        ],
        attributes={"title": "Screen"},
    )
    screen = ps.parse_preference_xml(document, "res/a.xml")

    network = next(s for s in screen.sections if s.title == "Network")
    assert [f.key for f in network.fields] == ["chatAddress"]
    assert "loose" in {f.key for section in screen.sections for f in section.fields}
    assert "loose" not in {f.key for f in network.fields}


def test_atak_widget_subclasses_are_read_as_the_widgets_they_extend():
    """155 of ATAK's 505 rows are `PanCheckBoxPreference`.

    Matched by exact class name, this scanner would find almost nothing in ATAK.
    """
    document = build_preference_axml(
        [
            pref_field("com.atakmap.android.gui.PanCheckBoxPreference", "a", title="A"),
            pref_field("com.atakmap.android.gui.PanEditTextPreference", "b", title="B"),
            pref_field("com.atakmap.android.gui.PanListPreference", "c", title="C"),
        ]
    )
    screen = ps.parse_preference_xml(document, "res/a.xml")
    by_key = {f.key: f for f in screen.fields}

    assert by_key["a"].control == "bool"
    assert by_key["a"].java_class == atak_pref.CLASS_BOOLEAN
    assert by_key["b"].control == "str"
    # ⚠️ Not an int, even for a port. A real EUD export stores it as a String and
    # ATAK reads it with getString; an Integer here throws inside ATAK.
    assert by_key["b"].java_class == atak_pref.CLASS_STRING
    # A list with no resolvable options falls back to free text rather than
    # offering an empty dropdown.
    assert by_key["c"].control == "str"


def test_a_multi_select_is_not_read_as_a_single_choice():
    """`MultiSelectListPreference` ends in `ListPreference`.

    Tested before the shorter suffix, every multi-select silently becomes a
    one-of dropdown.
    """
    document = build_preference_axml(
        [pref_field("MultiSelectListPreference", "tags", title="Tags", entries="x")]
    )
    screen = ps.parse_preference_xml(document, "res/a.xml")
    assert screen.fields[0].widget == "MultiSelectListPreference"


def test_an_unknown_widget_is_offered_as_text_rather_than_dropped():
    """ATAK's `SMSNumberPreference` and `CredentialsPreference` store real values.

    Classified by an `endswith("Preference")` deny-list they vanish, and a setting
    that silently cannot be configured is worse than one spare text box.
    """
    document = build_preference_axml(
        [pref_field("com.atakmap.android.gui.SMSNumberPreference", "sms_numbers", title="SMS")]
    )
    screen = ps.parse_preference_xml(document, "res/a.xml")

    assert [f.key for f in screen.fields] == ["sms_numbers"]
    assert screen.fields[0].control == "str"


def test_a_compiled_boolean_default_is_reported_in_the_control_s_own_words():
    """Binary XML stores a checkbox default as 0/1.

    Shown beside a True/False control that is a different vocabulary, and it is
    the app's own value being reported.
    """
    document = build_preference_axml(
        [
            pref_field("CheckBoxPreference", "on", title="On", defaultValue=True),
            pref_field("CheckBoxPreference", "off", title="Off", defaultValue=False),
        ]
    )
    screen = ps.parse_preference_xml(document, "res/a.xml")
    by_key = {f.key: f for f in screen.fields}

    assert by_key["on"].default == "true"
    assert by_key["off"].default == "false"


def test_every_screen_is_kept_not_only_the_first():
    """⚠️ The opposite of the managed-configuration scan, deliberately.

    An app has one restrictions document, so that scanner stops at the first hit.
    ATAK has 48 settings documents; stopping at the first would surface a handful
    of keys out of 293 and look like an app with barely any settings.
    """
    first = build_preference_axml([pref_field("CheckBoxPreference", "a", title="A")])
    second = build_preference_axml([pref_field("CheckBoxPreference", "b", title="B")])

    schema = ps.discover(_apk_with(first, second), "com.example.plugin")

    assert len(schema.screens) == 2
    assert {f.key for f in schema.fields} == {"a", "b"}


def test_the_label_falls_back_to_the_key_when_a_title_cannot_be_resolved():
    field = ps.PrefField(
        key="someKey", widget="CheckBoxPreference", control="bool",
        java_class=atak_pref.CLASS_BOOLEAN, title=None,
    )
    assert field.label == "someKey"


# --------------------------------------------------------------------------- #
# Where a plugin's values are stored
# --------------------------------------------------------------------------- #


def test_a_plugin_naming_no_store_of_its_own_writes_into_ataks():
    """A plugin runs inside ATAK's process, so ATAK's store is the common case."""
    document = build_preference_axml([pref_field("CheckBoxPreference", "a", title="A")])
    schema = ps.discover(_apk_with(document), "com.example.plugin")

    assert schema.preference_group == ps.DEFAULT_PREFERENCE_GROUP


def test_a_plugin_naming_exactly_one_store_of_its_own_uses_it():
    document = build_preference_axml([pref_field("CheckBoxPreference", "a", title="A")])
    dex = b"dex\n035\x00" + b"\x00" * 16 + b"com.example.plugin_preferences" + b"\x00" * 16

    schema = ps.discover(_apk_with(document, dex=dex), "com.example.plugin")

    assert schema.preference_group == "com.example.plugin_preferences"


def test_two_candidate_stores_are_ambiguous_and_fall_back():
    """A bundled library naming its own store is not the plugin's store.

    Picking one at random writes every value where nothing reads it, silently —
    so ambiguity resolves to ATAK's store, which is at least the common case.
    """
    document = build_preference_axml([pref_field("CheckBoxPreference", "a", title="A")])
    dex = (
        b"dex\n035\x00" + b"\x00" * 8
        + b"com.example.plugin_preferences" + b"\x00" * 8
        + b"com.vendor.sdk_preferences" + b"\x00" * 8
    )

    schema = ps.discover(_apk_with(document, dex=dex), "com.example.plugin")

    assert schema.preference_group == ps.DEFAULT_PREFERENCE_GROUP


def test_a_platform_constant_is_not_mistaken_for_a_preference_store():
    """⚠️ `android.intent.category.NOTIFICATION_PREFERENCES` matches the shape.

    Matched case-insensitively it wins outright, and every plugin that posts a
    notification gets its settings written into a store named after an intent
    category — which is what ATAK's own scan returned before this was pinned.
    """
    document = build_preference_axml([pref_field("CheckBoxPreference", "a", title="A")])
    dex = (
        b"dex\n035\x00" + b"\x00" * 8
        + b"android.intent.category.NOTIFICATION_PREFERENCES" + b"\x00" * 8
    )

    schema = ps.discover(_apk_with(document, dex=dex), "com.example.plugin")

    assert schema.preference_group == ps.DEFAULT_PREFERENCE_GROUP


# --------------------------------------------------------------------------- #
# The real ATAK build
# --------------------------------------------------------------------------- #


@needs_atak
def test_ataks_settings_are_found_despite_shrunk_resource_names():
    """The case the whole design turns on.

    ATAK's 65 preference documents ship as `res/-v.xml`, `res/0P.xml`,
    `res/1z.xml`. No name-based lookup finds any of them.
    """
    schema = ps.discover(ATAK.read_bytes(), "com.atakmap.app.civ")

    assert schema.declares_any
    assert schema.field_count > 250
    assert {f.key for f in schema.fields} >= {
        "atakControlBluetooth", "chatAddress", "chatPort", "enableToast",
    }
    assert not any(source.startswith("res/xml/") for source in (s.source for s in schema.screens))


@needs_atak
def test_ataks_titles_resolve_through_the_resource_table():
    """A raw `@0x7f0f1488` must never reach an operator."""
    schema = ps.discover(ATAK.read_bytes(), "com.atakmap.app.civ")

    titled = [f for f in schema.fields if f.title]
    assert len(titled) > 250
    assert not any(f.label.startswith("@0x") for f in schema.fields)

    bluetooth = next(f for f in schema.fields if f.key == "atakControlBluetooth")
    assert bluetooth.title == "Bluetooth Support"


@needs_atak
def test_ataks_dropdowns_carry_their_real_values_not_their_labels():
    """⚠️ Labels and values are two arrays paired by index.

    Storing the label would put "Let's Encrypt and DigiCert Only" where ATAK
    expects `BAKED_IN` — the app ignores it, falls back to its default, and the
    console shows the setting applied.
    """
    schema = ps.discover(ATAK.read_bytes(), "com.atakmap.app.civ")

    trust = next(f for f in schema.fields if f.key == "auth_flow_trust_model")
    assert trust.control == "select"
    assert {o.value for o in trust.options} == {
        "BAKED_IN", "PRECONFIGURED", "SYSTEM", "TRUST_ALL",
    }
    assert any(o.label.startswith("Let's Encrypt") for o in trust.options)


@needs_atak
def test_ataks_own_preference_group_is_detected():
    schema = ps.discover(ATAK.read_bytes(), "com.atakmap.app.civ")
    assert schema.preference_group == "com.atakmap.app.civ_preferences"


@needs_atak
def test_a_port_in_atak_is_stored_as_a_string():
    """The trap D93 exists for: `chatPort` defaults to 17012 and is a String.

    Typed as an Integer because it looks numeric, ATAK's `getString` throws.
    """
    schema = ps.discover(ATAK.read_bytes(), "com.atakmap.app.civ")

    port = next(f for f in schema.fields if f.key == "chatPort")
    assert port.java_class == atak_pref.CLASS_STRING
    assert port.default == "17012"


@needs_atak
def test_scanning_atak_twice_yields_the_same_document():
    """The generated `.pref` is de-duplicated on the device by MD5.

    A scan that reorders between runs produces different bytes for an unchanged
    policy, and every device reloads its whole ATAK configuration for nothing.
    """
    data = ATAK.read_bytes()
    assert ps.discover(data, "com.atakmap.app.civ").types() == (
        ps.discover(data, "com.atakmap.app.civ").types()
    )


@needs_atak
def test_atak_declares_the_key_this_configuration_travels_in():
    """The delivery contract, asserted where a future ATAK release would break it.

    Losing `enterpriseConfigurationPreferences` would leave every generated
    document with nowhere to go, and nothing else in this feature would fail.
    """
    from app.artifacts import app_restrictions

    with zipfile.ZipFile(ATAK) as archive:
        declared = app_restrictions.discover_in(archive, "com.atakmap.app.civ")

    assert "enterpriseConfigurationPreferences" in {k.key for k in declared.keys}


# --------------------------------------------------------------------------- #
# The generated document
# --------------------------------------------------------------------------- #


def test_the_document_matches_a_real_eud_export_byte_for_byte():
    """The bytes are the contract, CRLF included."""
    document = atak_pref.build(
        [
            (
                "com.atakmap.app.civ_preferences",
                [
                    atak_pref.PrefEntry("friendly_visible", "true", atak_pref.CLASS_BOOLEAN),
                    atak_pref.PrefEntry("hostileUpdateDelay", "0", atak_pref.CLASS_STRING),
                ],
            )
        ]
    )

    assert document == (
        "<?xml version='1.0' standalone='yes'?>\r\n"
        "<preferences>\r\n"
        '<preference version="1" name="com.atakmap.app.civ_preferences">\r\n'
        '<entry key="friendly_visible" class="class java.lang.Boolean">true</entry>\r\n'
        '<entry key="hostileUpdateDelay" class="class java.lang.String">0</entry>\r\n'
        "</preference>\r\n"
        "</preferences>\r\n"
    )


def test_no_connection_groups_are_written():
    """⚠️ A real export writes empty `cot_*` blocks; this generator writes none.

    They are out of scope, and a `<preference>` element ATAK does not see is one
    it cannot act on — the safe direction when what it might act on is the
    operator's TAK server connection.
    """
    document = atak_pref.build(
        [("com.atakmap.app.civ_preferences", [atak_pref.PrefEntry("a", "b")])]
    )
    assert "cot_streams" not in document
    assert "cot_inputs" not in document


def test_an_empty_configuration_produces_no_document_at_all():
    assert atak_pref.build([("com.atakmap.app.civ_preferences", [])]) == ""
    assert atak_pref.build([]) == ""


def test_values_are_escaped_the_way_atak_decodes_them():
    """⚠️ ATAK reverses five `\\uXXXX` sequences, not XML entities.

    Writing `&amp;` leaves the app holding those five literal characters.
    """
    document = atak_pref.build(
        [("g", [atak_pref.PrefEntry("k", 'a & b < c > d "e" \'f\'')])]
    )

    assert "\\u0026" in document
    assert "\\u003c" in document
    assert "\\u0022" in document
    assert "&amp;" not in document


def test_a_key_going_into_an_attribute_is_escaped_as_xml():
    """An attribute is read by a real XML parser on ATAK's side, unlike the text."""
    document = atak_pref.build([("g", [atak_pref.PrefEntry('a"b', "v")])])
    assert 'key="a\\u0022b"' in document


def test_a_non_numeric_value_for_a_numeric_key_is_refused_here():
    """⚠️ The failure this prevents is invisible from the device.

    `Integer.parseInt` is called unguarded and there is no per-entry try, so the
    exception discards every entry after it — while the ones before it have
    already been applied, and the MD5 marking the document ingested is written
    *after* the parse. The result is a half-applied configuration retried on
    every restrictions-changed broadcast, forever.
    """
    with pytest.raises(atak_pref.PrefError) as raised:
        atak_pref.build([("g", [atak_pref.PrefEntry("n", "lots", atak_pref.CLASS_INTEGER)])])

    assert "n" in str(raised.value)
    assert "whole-number" in str(raised.value)


def test_a_non_boolean_value_for_a_boolean_key_is_refused_rather_than_coerced():
    """`Boolean.parseBoolean` reads anything that is not "true" as false.

    Left alone, "yes" applies as **false** with no error anywhere — the one
    failure mode worse than a crash.
    """
    with pytest.raises(atak_pref.PrefError):
        atak_pref.build([("g", [atak_pref.PrefEntry("b", "maybe", atak_pref.CLASS_BOOLEAN)])])


def test_boolean_spellings_an_operator_might_type_are_normalised():
    document = atak_pref.build(
        [
            (
                "g",
                [
                    atak_pref.PrefEntry("a", "Yes", atak_pref.CLASS_BOOLEAN),
                    atak_pref.PrefEntry("b", "OFF", atak_pref.CLASS_BOOLEAN),
                ],
            )
        ]
    )
    assert ">true</entry>" in document
    assert ">false</entry>" in document


def test_a_control_character_is_refused_before_it_reaches_the_parser():
    """XML 1.0 cannot carry one, so the document fails to parse as a whole."""
    with pytest.raises(atak_pref.PrefError):
        atak_pref.build([("g", [atak_pref.PrefEntry("k", "a\x07b")])])


def test_a_document_too_large_for_the_binder_transaction_is_refused():
    entries = [atak_pref.PrefEntry(f"key{i:05d}", "x" * 200) for i in range(500)]
    with pytest.raises(atak_pref.PrefError) as raised:
        atak_pref.build([("g", entries)])

    assert "limit" in str(raised.value)


def test_keys_are_emitted_in_a_stable_order():
    """A document that differs only in ordering re-applies on the device for
    nothing — the MD5 dedupe is byte-based."""
    first = atak_pref.entries_from({"b": "1", "a": "2"}, {})
    second = atak_pref.entries_from({"a": "2", "b": "1"}, {})

    assert [e.key for e in first] == [e.key for e in second] == ["a", "b"]


def test_a_key_with_no_declared_class_is_carried_as_a_string():
    """String is the only class whose value cannot fail to parse."""
    entries = atak_pref.entries_from({"unknown": "42"}, {})
    assert entries[0].java_class == atak_pref.CLASS_STRING


@needs_atak
def test_a_scanned_atak_configuration_round_trips_into_a_document():
    """The two halves meeting: scanned classes, generated bytes."""
    schema = ps.discover(ATAK.read_bytes(), "com.atakmap.app.civ")
    types = schema.types()

    document = atak_pref.build(
        [
            (
                schema.preference_group,
                atak_pref.entries_from(
                    {"atakControlBluetooth": "true", "chatPort": "17012"}, types
                ),
            )
        ]
    )

    assert '<entry key="atakControlBluetooth" class="class java.lang.Boolean">true</entry>' in document
    assert '<entry key="chatPort" class="class java.lang.String">17012</entry>' in document
    assert len(document.encode("utf-8")) < atak_pref.MAX_PREF_BYTES


# --------------------------------------------------------------------------- #
# Categories: two idioms that disagree about the same shape
# --------------------------------------------------------------------------- #


def test_a_category_subclass_is_a_heading_not_a_setting():
    """⚠️ UAS Tool ships `com.atakmap.android.gui.PanPreferenceCategory`.

    Compared by exact class name it falls through to the unknown-widget branch
    and becomes a **free-text setting named after a heading** — which is exactly
    what happened to its "AR OVERLAY" and "OBJECT DETECTION" rows, both of which
    carry a key.
    """
    document = build_preference_axml(
        [
            (
                "com.atakmap.android.gui.PanPreferenceCategory",
                {"title": "AR Overlay", "key": "uastool.pref_aroverlay_category"},
                [],
            ),
            pref_field("CheckBoxPreference", "real", title="Real"),
        ]
    )
    screen = ps.parse_preference_xml(document, "res/a.xml")

    assert [f.key for f in screen.fields] == ["real"]
    assert screen.sections[0].title == "AR Overlay"


def test_a_category_used_as_a_separator_still_claims_the_fields_after_it():
    """⚠️ The idiom that cost UAS Tool every one of its headings.

    Android documents a category as the *parent* of its fields and ATAK writes
    them that way — but UAS Tool's categories are **empty elements**, with the
    fields following them as siblings at the same depth. Read only as nesting,
    all 158 of its settings land under one heading and all 30 real headings are
    thrown away.
    """
    document = build_preference_axml(
        [
            ("PreferenceCategory", {"title": "Trillium/Orion Settings"}, []),
            pref_field("EditTextPreference", "uastool.trillium.pref_platform_ip", title="IP"),
            ("PreferenceCategory", {"title": "Indago Settings"}, []),
            pref_field("EditTextPreference", "uastool.indago.pref_src_ip", title="IP"),
        ]
    )
    screen = ps.parse_preference_xml(document, "res/a.xml")

    assert [s.title for s in screen.sections] == [
        "Trillium/Orion Settings", "Indago Settings",
    ]
    assert [f.key for f in screen.sections[0].fields] == ["uastool.trillium.pref_platform_ip"]
    assert [f.key for f in screen.sections[1].fields] == ["uastool.indago.pref_src_ip"]


def test_the_flat_idiom_does_not_leak_into_a_nested_document():
    """The other half of the same decision.

    Once a field has appeared *inside* a category the document is nested, and a
    later same-depth field has genuinely left it. Treating that one as flat would
    file a trailing top-level setting under a heading it is not part of.
    """
    document = build_preference_axml(
        [
            pref_category("Network", pref_field("EditTextPreference", "inside", title="In")),
            pref_field("CheckBoxPreference", "after", title="After"),
        ]
    )
    screen = ps.parse_preference_xml(document, "res/a.xml")

    network = next(s for s in screen.sections if s.title == "Network")
    assert [f.key for f in network.fields] == ["inside"]
    assert "after" not in {f.key for f in network.fields}


# --------------------------------------------------------------------------- #
# The real UAS Tool plugin
# --------------------------------------------------------------------------- #


@needs_uastool
def test_a_real_plugin_s_settings_are_found():
    """The plugin half of the feature, against a shipping plugin rather than a
    fixture — 395 MB, resource names shrunk exactly as ATAK's are."""
    schema = ps.discover(UASTOOL.read_bytes(), "com.atakmap.android.uastool.plugin")

    assert schema.declares_any
    assert schema.field_count > 150
    keys = {f.key for f in schema.fields}
    assert "uastool.mavlink.pref_platform_ip" in keys
    assert "uastool.pref_cot_broadcast" in keys


@needs_uastool
def test_a_real_plugin_writes_into_ataks_own_store():
    """The assumption D92 rests on, checked against a real plugin.

    A plugin runs inside ATAK's process, so its settings land in ATAK's
    SharedPreferences — which is what lets one generated document carry ATAK's
    settings and its plugins' together.
    """
    schema = ps.discover(UASTOOL.read_bytes(), "com.atakmap.android.uastool.plugin")
    assert schema.preference_group == ps.DEFAULT_PREFERENCE_GROUP


@needs_uastool
def test_a_real_plugin_s_headings_survive():
    """⚠️ Every one of these was lost before the flat-category idiom was handled.

    30 headings became 23 copies of "General", and an operator looking for the
    MAVLink platform's settings had no way to find them among 158 rows.
    """
    schema = ps.discover(UASTOOL.read_bytes(), "com.atakmap.android.uastool.plugin")
    titles = {section.title for screen in schema.screens for section in screen.sections}

    assert "General" not in titles
    assert {"DJI v5 Settings", "Indago Settings", "Trillium/Orion Settings"} <= titles


@needs_uastool
def test_a_real_plugin_s_dropdowns_carry_their_real_values():
    """UAS Tool's bitrate list stores "900" behind the label "900kbps"."""
    schema = ps.discover(UASTOOL.read_bytes(), "com.atakmap.android.uastool.plugin")

    bitrate = next(
        f for f in schema.fields if f.key == "uastool.pref_video_record_bitrate"
    )
    assert bitrate.control == "select"
    assert ("900kbps", "900") in {(o.label, o.value) for o in bitrate.options}


@needs_uastool
def test_a_real_plugin_s_configuration_round_trips_into_a_document():
    schema = ps.discover(UASTOOL.read_bytes(), "com.atakmap.android.uastool.plugin")

    document = atak_pref.build(
        [
            (
                schema.preference_group,
                atak_pref.entries_from(
                    {
                        "uastool.pref_cot_broadcast": "true",
                        "uastool.pref_video_record_bitrate": "900",
                    },
                    schema.types(),
                ),
            )
        ]
    )

    assert (
        '<entry key="uastool.pref_cot_broadcast" class="class java.lang.Boolean">true</entry>'
        in document
    )
    assert (
        '<entry key="uastool.pref_video_record_bitrate" class="class java.lang.String">900</entry>'
        in document
    )
