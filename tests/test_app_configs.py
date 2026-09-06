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

"""Managed configuration discovery and the APP_CATALOG.app_configs field (W49).

Tested against **real shipping apps**, not only XML written to make the parser
pass. A fixture proves the code does what its author expected; a shipping APK
proves it does what Android actually produces.

Eight apps, because they fail differently:

* **Butterfly IQ** is the reference case — a third-party enterprise app, shipped
  as an XAPK, with an **integer** key and titles inlined as real strings.
* **ATAK** is the awkward one — schema at the obfuscated path `res/Kt.xml`, and
  every title an unresolvable `@string` reference.
* **Chrome** is the scale case — 231 keys across five types, a base part not
  named `base.apk`, and choice keys whose option lists are resource arrays we
  cannot read.
* **Gboard** is the structural case — it **nests** 43 keys inside a `bundle`,
  which a flat read reported as configurable keys in their own right.
* **Outlook** is the well-behaved case — 44 flat Intune-style keys with real
  titles, and the one that showed booleans arrive with 0/1 defaults.
* **Messages** is the many-splits case — 19 config splits carrying nothing, and
  defaults declared as a bare integer and as an empty string.
* **Survey123** is the textbook case — the canonical `res/xml/restrictions.xml`
  path with every title and default inlined. The only fixture where a name-based
  lookup would have worked, which is why it is worth keeping.
* **Field Maps** is its opposite twin — same vendor, obfuscated path, no titles
  at all, yet literal integer defaults.
"""

from __future__ import annotations

import json
import pathlib
import zipfile

import pytest
from starlette.datastructures import FormData

from app.artifacts import app_restrictions as ar
from app.policies import form_parse
from app.policies.form_schema import sub_pages
from app.policies.registry import PolicyTypeError, registry
from tests.conftest import ADMIN_HEADERS

ATAK = pathlib.Path("Test Files/ATAK-5.8.0.4-174b425-civSmall-release.apk")
BUTTERFLY = pathlib.Path("Test Files/butterfly-iq-2.49.0.xapk")
CHROME = pathlib.Path("Test Files/Google+Chrome_152.0.7977.82_APKPure.xapk")
OUTLOOK = pathlib.Path("Test Files/Microsoft+Outlook_5.2606.0_APKPure.apk")
FIELDMAPS = pathlib.Path("Test Files/ArcGIS+Field+Maps_26.2.2_APKPure.apk")
SURVEY123 = pathlib.Path("Test Files/ArcGIS+Survey123_3.25.32_APKPure.apk")
MESSAGES = pathlib.Path(
    "Test Files/Google+Messages_messages.android_20260827_01_RC02.phone_dynamic_APKPure.xapk"
)
GBOARD = pathlib.Path(
    "Test Files/Gboard+-+the+Google+Keyboard_18.1.3.962075747-beta-arm64-v8a_APKPure.apk"
)


def _butterfly_base() -> bytes:
    """Butterfly ships as an XAPK; the schema lives in the base part.

    Worth asserting rather than assuming — the server splits an XAPK into base +
    splits and only ever scans the base, so if a schema could hide in a split this
    whole feature would miss it for every multi-part app.
    """
    with zipfile.ZipFile(BUTTERFLY) as outer:
        return outer.read("base.apk")


# --------------------------------------------------------------------------- #
# Discovery
# --------------------------------------------------------------------------- #


def test_an_apk_with_no_restrictions_declares_none():
    empty = ar.discover(b"not even a zip", "com.example.app")
    assert empty.declares_any is False
    assert empty.keys == []


def test_a_non_restrictions_xml_is_not_mistaken_for_one():
    """Every res/ XML gets parsed, so the root-element check is what stops a
    layout or a drawable being read as a configuration schema."""
    assert ar.parse_restrictions_xml(b"\x00\x01 not binary xml") is None


@pytest.mark.skipif(not ATAK.exists(), reason="the ATAK APK is not in this checkout")
def test_atak_declares_its_enterprise_configuration_keys():
    """The case the whole design turns on.

    ATAK ships its schema as `res/Kt.xml` — resource shrinking renamed it — so a
    name-based lookup finds nothing and an id-based one needs the .arsc parser we
    do not have. Content-based discovery finds it.
    """
    found = ar.discover(ATAK.read_bytes(), "com.atakmap.app.civ")

    assert found.declares_any
    keys = {k.key for k in found.keys}
    assert "enterpriseConfigurationDataPackage" in keys
    assert "enterpriseConfigurationPreferences" in keys
    # All six are TYPE_STRING, so all six render as text.
    assert {k.control for k in found.keys} == {"str"}


@pytest.mark.skipif(not ATAK.exists(), reason="the ATAK APK is not in this checkout")
def test_a_referenced_title_resolves_through_the_resource_table():
    """ATAK's titles are `@string` references.

    This test used to assert `title is None` — correct then, because W49 had no
    `resources.arsc` reader and the key was shown instead. W54 added one, so the
    *right* answer changed. What has not changed is the guarantee it existed to
    protect: a raw `@0x7f0f1488` must never reach an operator.
    """
    found = ar.discover(ATAK.read_bytes(), "com.atakmap.app.civ")

    entry = next(k for k in found.keys if k.key == "enterpriseConfigurationPreferences")
    assert entry.title
    assert not entry.title.startswith("@0x")
    assert not entry.label.startswith("@0x")


@pytest.mark.skipif(not ATAK.exists(), reason="the ATAK APK is not in this checkout")
def test_a_title_that_cannot_be_resolved_still_falls_back_to_the_key():
    """The fallback must survive its own success.

    Resolution is best-effort — an app may reference a string that is not in the
    table — and the label must then be the key, never the reference.
    """
    from app.artifacts.app_restrictions import RestrictionKey

    unresolved = RestrictionKey(key="someKey", restriction_type=ar.TYPE_STRING, title=None)

    assert unresolved.label == "someKey"


@pytest.mark.skipif(not BUTTERFLY.exists(), reason="the Butterfly XAPK is not in this checkout")
def test_butterfly_declares_its_enterprise_keys():
    """The reference case for this feature — a real third-party app, not ATAK.

    It covers two things ATAK's schema does not: an **integer** key, and titles
    the app inlined as literal strings rather than `@string` references.
    """
    found = ar.discover(_butterfly_base(), "com.butterflynetinc.helios")

    assert found.declares_any
    by_key = {k.key: k for k in found.keys}
    assert set(by_key) == {
        "ApprovedEnterpriseDeviceSecret",
        "ButterflyDomain",
        "InactivityTimeoutSeconds",
    }

    # An integer key must render as a number box, not a free-text field.
    assert by_key["InactivityTimeoutSeconds"].restriction_type == ar.TYPE_INTEGER
    assert by_key["InactivityTimeoutSeconds"].control == "int"
    assert by_key["ButterflyDomain"].control == "str"


@pytest.mark.skipif(not BUTTERFLY.exists(), reason="the Butterfly XAPK is not in this checkout")
def test_a_resolved_title_is_used_in_preference_to_the_key():
    """Butterfly inlined its titles, so the operator sees prose. The key-fallback
    only exists for apps like ATAK whose titles are unresolvable references —
    this proves the fallback is not masking a title that was there all along."""
    found = ar.discover(_butterfly_base(), "com.butterflynetinc.helios")
    entry = next(k for k in found.keys if k.key == "ButterflyDomain")

    assert entry.title == "Butterfly Enterprise Subdomain"
    assert entry.label == "Butterfly Enterprise Subdomain"


@pytest.mark.skipif(not BUTTERFLY.exists(), reason="the Butterfly XAPK is not in this checkout")
def test_only_the_base_part_of_an_xapk_carries_the_schema():
    """The server scans the base part alone. If a split could carry a schema, every
    multi-part app would silently appear to declare nothing."""
    with zipfile.ZipFile(BUTTERFLY) as outer:
        splits = [n for n in outer.namelist() if n.endswith(".apk") and n != "base.apk"]
        assert splits, "the fixture should actually be multi-part"
        for name in splits:
            found = ar.discover(outer.read(name), "com.butterflynetinc.helios")
            assert not found.declares_any, f"{name} unexpectedly declares a schema"


@pytest.mark.skipif(not CHROME.exists(), reason="the Chrome XAPK is not in this checkout")
def test_chrome_declares_its_whole_enterprise_policy_schema():
    """The scale case: Chrome ships 231 keys across five types.

    Also the case where the base part is **not** called `base.apk` — this XAPK
    names it `com.android.chrome.apk` — which is why discovery runs on whichever
    part the server recorded as BASE rather than on a filename convention.
    """
    with zipfile.ZipFile(CHROME) as outer:
        found = ar.discover(outer.read("com.android.chrome.apk"), "com.android.chrome")

    assert len(found.keys) > 200
    by_key = {k.key: k for k in found.keys}
    assert "CloudManagementEnrollmentToken" in by_key
    assert by_key["CloudManagementEnrollmentToken"].control == "str"
    # Booleans must not degrade to text, or 93 keys become free-typing.
    assert by_key["AdditionalDnsQueryTypesEnabled"].control == "bool"


@pytest.mark.skipif(not CHROME.exists(), reason="the Chrome XAPK is not in this checkout")
def test_a_choice_key_offers_the_options_the_app_declares():
    """`entries` / `entryValues` are resource arrays, and W49 could not read one —
    so the console offered a text box and hoped the operator typed an accepted
    value. Both arrays resolve now, paired by index: the label is what the app
    calls the option, the value is what goes to the device.
    """
    with zipfile.ZipFile(CHROME) as outer:
        found = ar.discover(outer.read("com.android.chrome.apk"), "com.android.chrome")

    entry = next(k for k in found.keys if k.key == "AdsSettingForIntrusiveAdsSites")

    assert entry.restriction_type == ar.TYPE_CHOICE
    assert entry.control == "choice"
    assert entry.default == "1"
    assert entry.has_options
    assert [o.value for o in entry.options] == ["1", "2"]
    assert entry.options[0].label == "Allow ads on all sites"
    assert entry.options[1].label == "Do not allow ads on sites with intrusive ads"
    # The pairing is index-based, so a silent off-by-one would still "work". The
    # app's own declared default being one of the offered values is independent
    # evidence that labels and values line up.
    assert entry.default in [o.value for o in entry.options]


@pytest.mark.skipif(not CHROME.exists(), reason="the Chrome XAPK is not in this checkout")
def test_a_boolean_key_is_not_given_a_dropdown_it_does_not_need():
    """Chrome declares `entries` on 93 of its **boolean** keys.

    Those already render as a true/false control, and turning them into dropdowns
    of the app's prose would replace a precise control with a vaguer one.
    """
    with zipfile.ZipFile(CHROME) as outer:
        found = ar.discover(outer.read("com.android.chrome.apk"), "com.android.chrome")

    booleans = [k for k in found.keys if k.restriction_type == ar.TYPE_BOOLEAN]

    assert booleans, "precondition: Chrome declares boolean keys"
    assert not any(k.has_options for k in booleans)


@pytest.mark.skipif(not GBOARD.exists(), reason="the Gboard APK is not in this checkout")
def test_options_resolve_for_a_second_app_with_a_different_value_vocabulary():
    """Chrome's choice values are integers; Gboard's are strings. Both are just
    "what the app said", and neither may be coerced into the other's shape."""
    found = ar.discover(GBOARD.read_bytes(), "com.google.android.inputmethod.latin")

    entry = next(k for k in found.keys if k.key == "config_default_keyboard_height")

    assert entry.has_options
    assert entry.options[0].value == "keyboard_height_33_mm"
    assert "33 mm" in entry.options[0].label


@pytest.mark.skipif(not GBOARD.exists(), reason="the Gboard APK is not in this checkout")
def test_gboard_nested_keys_are_not_offered_as_top_level_configuration():
    """The regression guard for a real bug this app found.

    Gboard nests 43 keys inside a `preferences` bundle. Read flat — which is what
    the AXML reader did before it tracked depth — they look like 43 more
    configurable keys. Setting one would write it to the top of the Bundle, where
    Gboard never reads: no error, no effect, nothing to see in the console.
    """
    found = ar.discover(GBOARD.read_bytes(), "com.google.android.inputmethod.latin")
    by_key = {k.key: k for k in found.keys}

    assert len(found.keys) == 82, "only the top-level keys are configurable"
    # `preferences` is the bundle itself, and is top-level.
    assert "preferences" in by_key
    # Its children are not keys in their own right.
    for nested in ("config_theme", "enable_key_border", "enable_number_row"):
        assert nested not in by_key, f"{nested} is nested inside the preferences bundle"


@pytest.mark.skipif(not GBOARD.exists(), reason="the Gboard APK is not in this checkout")
def test_gboards_bundle_key_is_flagged_rather_than_offered_as_text():
    """The first real app to exercise the unsupported-type path. A flat editor
    cannot express a nested Bundle, and offering a text box would produce a value
    the app cannot read."""
    found = ar.discover(GBOARD.read_bytes(), "com.google.android.inputmethod.latin")
    entry = next(k for k in found.keys if k.key == "preferences")

    assert entry.restriction_type == ar.TYPE_BUNDLE
    assert entry.unsupported_reason is not None
    assert "bundle" in entry.unsupported_reason


def test_nesting_is_visible_to_the_parser_at_all():
    """Guards the AXML change underneath: without depth, every document reads as
    a flat list and any meaning carried by structure is silently lost."""
    from app.artifacts import axml

    if not GBOARD.exists():
        pytest.skip("the Gboard APK is not in this checkout")

    with zipfile.ZipFile(GBOARD) as z:
        elements = axml.parse_elements(z.read("res/Ktm.xml"))

    assert elements[0].depth == 0  # <restrictions>
    assert any(e.depth == 1 for e in elements)
    assert any(e.depth == 2 for e in elements), "the fixture should actually nest"


@pytest.mark.skipif(not OUTLOOK.exists(), reason="the Outlook APK is not in this checkout")
def test_outlook_declares_a_flat_intune_style_schema():
    """The well-behaved case, and the one closest to a normal enterprise rollout:
    44 flat keys, titles the app inlined, no nesting and no bundles."""
    found = ar.discover(OUTLOOK.read_bytes(), "com.microsoft.office.outlook")
    by_key = {k.key: k for k in found.keys}

    assert len(found.keys) == 44
    assert "com.microsoft.outlook.EmailProfile.EmailAddress" in by_key
    assert by_key["com.microsoft.outlook.EmailProfile.EmailAddress"].control == "str"
    assert not any(k.unsupported_reason for k in found.keys)


@pytest.mark.skipif(not OUTLOOK.exists(), reason="the Outlook APK is not in this checkout")
def test_a_boolean_default_is_reported_in_the_controls_own_language():
    """Binary XML stores booleans as 0/1, so Outlook's default arrives as "0".
    Reported as false, because it sits beside a True/False control and it is the
    app's own value being shown — 0 there reads like a different setting."""
    found = ar.discover(OUTLOOK.read_bytes(), "com.microsoft.office.outlook")
    entry = next(
        k for k in found.keys
        if k.key == "com.microsoft.outlook.Mail.BlockExternalImagesEnabled"
    )

    assert entry.control == "bool"
    assert entry.default == "false"


@pytest.mark.skipif(not MESSAGES.exists(), reason="the Messages XAPK is not in this checkout")
def test_messages_schema_lives_in_the_base_among_nineteen_splits():
    """The many-splits case: 19 config splits (languages, density, abi) and the
    schema in none of them. Scanning the base part is what makes that free."""
    with zipfile.ZipFile(MESSAGES) as outer:
        base = "com.google.android.apps.messaging.apk"
        splits = [n for n in outer.namelist() if n.endswith(".apk") and n != base]
        assert len(splits) > 15, "the fixture should be heavily split"

        found = ar.discover(outer.read(base), "com.google.android.apps.messaging")
        assert {k.key for k in found.keys} == {"disable_rcs", "messages_archival"}

        for name in splits:
            assert not ar.discover(
                outer.read(name), "com.google.android.apps.messaging"
            ).declares_any, f"{name} unexpectedly declares a schema"


@pytest.mark.skipif(not MESSAGES.exists(), reason="the Messages XAPK is not in this checkout")
def test_defaults_are_read_in_their_declared_form():
    """`disable_rcs` declares `defaultValue=0` as an **integer**, not the string
    "0", and `messages_archival` declares an empty one. Both are easy to mishandle:
    the first should read as a boolean, the second as "no default" rather than as
    an empty string an operator might mistake for a value."""
    with zipfile.ZipFile(MESSAGES) as outer:
        found = ar.discover(
            outer.read("com.google.android.apps.messaging.apk"),
            "com.google.android.apps.messaging",
        )
    by_key = {k.key: k for k in found.keys}

    assert by_key["disable_rcs"].control == "bool"
    assert by_key["disable_rcs"].default == "false"
    assert by_key["messages_archival"].default is None


@pytest.mark.skipif(not SURVEY123.exists(), reason="the Survey123 APK is not in this checkout")
def test_survey123_uses_the_canonical_schema_path():
    """The textbook case, and the one that keeps the design honest.

    Survey123 ships its schema at the conventional `res/xml/restrictions.xml`,
    with every title and default inlined. It is the only fixture where a
    name-based lookup would have worked — which is exactly why it is worth
    pinning: content-based discovery has to handle the tidy layout too, not just
    the obfuscated ones it was built for.
    """
    from app.artifacts import axml

    with zipfile.ZipFile(SURVEY123) as z:
        assert "res/xml/restrictions.xml" in z.namelist()
        elements = axml.parse_elements(z.read("res/xml/restrictions.xml"))
        assert elements[0].name == "restrictions"

    found = ar.discover(SURVEY123.read_bytes(), "com.esri.survey123")
    by_key = {k.key: k for k in found.keys}

    assert len(found.keys) == 10
    assert by_key["portalURL"].title == "Portal URL"
    assert by_key["portalURL"].default == "https://www.arcgis.com"
    assert by_key["requireSignIn"].control == "bool"
    assert by_key["requireSignIn"].default == "false"
    assert by_key["delaySignIn"].control == "int"


@pytest.mark.skipif(not FIELDMAPS.exists(), reason="the Field Maps APK is not in this checkout")
def test_fieldmaps_titles_resolve_from_an_obfuscated_schema():
    """The same vendor, the opposite build treatment: Field Maps ships at the
    obfuscated `res/Kt.xml` with every title a reference.

    This asserted `all(title is None)` under W49 — the honest answer when nothing
    could resolve one. All 11 resolve now, which is the whole point of W54; the
    literal integer defaults that were "the useful half" are still there.
    """
    found = ar.discover(FIELDMAPS.read_bytes(), "com.esri.fieldmaps")
    by_key = {k.key: k for k in found.keys}

    assert len(found.keys) == 11
    assert all(k.title for k in found.keys), "Field Maps titles no longer resolve"
    assert not any(k.label.startswith("@0x") for k in found.keys)
    assert by_key["locationSharingUploadLKLFrequency"].control == "int"
    assert by_key["locationSharingUploadLKLFrequency"].default == "60"


def test_a_bundle_key_is_reported_as_unsupported_rather_than_silently_dropped():
    """Android supports nested bundles; a flat key/value editor cannot express
    one. Saying so beats offering a text box that produces the wrong Bundle."""
    entry = ar.RestrictionKey(key="profile", restriction_type=ar.TYPE_BUNDLE)
    assert ar.TYPE_BUNDLE in ar._UNSUPPORTED
    assert entry.key == "profile"


# --------------------------------------------------------------------------- #
# The spec field
# --------------------------------------------------------------------------- #


def test_app_configs_round_trips():
    spec = registry.validate_spec(
        "APP_CATALOG",
        {
            "app_configs": [
                {
                    "package_name": "com.atakmap.app.civ",
                    "values": {"enterpriseConfigurationPreferences": "prefs.pref"},
                }
            ]
        },
    )
    assert spec["app_configs"][0]["values"]["enterpriseConfigurationPreferences"] == "prefs.pref"


def test_a_bad_package_name_is_refused():
    with pytest.raises(PolicyTypeError):
        registry.validate_spec(
            "APP_CATALOG",
            {"app_configs": [{"package_name": "not a package", "values": {"a": "b"}}]},
        )


def test_it_lands_on_its_own_sub_page():
    pages = {p.slug: [f.name for f in p.fields] for p in sub_pages("APP_CATALOG")}
    assert pages["app-configurations"] == ["app_configs"]


# --------------------------------------------------------------------------- #
# The form
# --------------------------------------------------------------------------- #


def test_the_form_parses_a_saved_configuration():
    parsed = form_parse.parse_form(
        "APP_CATALOG",
        FormData(
            [
                ("app_configs__package_name", "com.atakmap.app.civ"),
                ("app_configs__values", json.dumps({"enterpriseConfigurationPreferences": "x.pref"})),
            ]
        ),
    )
    assert parsed["app_configs"] == [
        {
            "package_name": "com.atakmap.app.civ",
            "values": {"enterpriseConfigurationPreferences": "x.pref"},
        }
    ]


def test_a_configuration_with_no_values_is_dropped():
    """An empty Bundle is a real instruction to an app — roughly "forget your
    settings" — and never what leaving the form blank was meant to say."""
    parsed = form_parse.parse_form(
        "APP_CATALOG",
        FormData(
            [
                ("app_configs__package_name", "com.atakmap.app.civ"),
                ("app_configs__values", "{}"),
            ]
        ),
    )
    assert "app_configs" not in parsed


def test_malformed_json_is_skipped_rather_than_crashing_the_save():
    """The values ride in a hidden input, so they are operator-supplied like any
    other field and must not be trusted to parse."""
    parsed = form_parse.parse_form(
        "APP_CATALOG",
        FormData(
            [
                ("app_configs__package_name", "com.atakmap.app.civ"),
                ("app_configs__values", "{not json"),
            ]
        ),
    )
    assert "app_configs" not in parsed


def test_a_saved_configuration_renders_back_into_the_editor(client):
    """The regression guard for a 500 that reached the operator.

    Every other test here exercises parsing and validation, which is why this got
    through: nothing rendered a *saved* app_configs row. The template read
    `entry.values`, and Jinja resolves attributes before items — so on a dict that
    finds the built-in `.values` **method**, and `tojson` blew up serialising it.
    The key being named "values" is the entire trap.
    """
    created = client.post(
        "/api/v1/profiles",
        json={
            "name": "Chrome downgrade with config",
            "sections": {
                "app_management": {
                    "app_configs": [
                        {
                            "package_name": "com.android.chrome",
                            "values": {"CloudManagementEnrollmentToken": "abc123"},
                        }
                    ]
                }
            },
        },
        headers=ADMIN_HEADERS,
    )
    assert created.status_code == 201, created.text
    profile_id = created.json()["id"]

    page = client.get(f"/profiles/{profile_id}", headers=ADMIN_HEADERS)

    assert page.status_code == 200, "the editor must render a saved configuration"
    assert "com.android.chrome" in page.text
    # The values ride in a hidden input as JSON; a bound method would have 500'd.
    assert "CloudManagementEnrollmentToken" in page.text
    assert "1 key" in page.text


def test_several_apps_can_be_configured_in_one_policy():
    parsed = form_parse.parse_form(
        "APP_CATALOG",
        FormData(
            [
                ("app_configs__package_name", "com.atakmap.app.civ"),
                ("app_configs__values", json.dumps({"a": "1"})),
                ("app_configs__package_name", "com.example.other"),
                ("app_configs__values", json.dumps({"b": "2"})),
            ]
        ),
    )
    assert [row["package_name"] for row in parsed["app_configs"]] == [
        "com.atakmap.app.civ",
        "com.example.other",
    ]


# --------------------------------------------------------------------------- #
# Option pairing — the silent-wrong-value cases (W54)
# --------------------------------------------------------------------------- #


class _FakeTable:
    """A resource table with exactly the arrays a test wants."""

    def __init__(self, arrays):
        self._arrays = arrays

    def string(self, resource_id, _depth=0):
        return None

    def has_array(self, resource_id):
        return resource_id in self._arrays

    def array(self, resource_id):
        return list(self._arrays.get(resource_id, []))


def _choice_element(entries="@0x7f040001", entry_values="@0x7f040002"):
    from app.artifacts.axml import AxmlElement

    attributes = {"android:key": "K", "android:restrictionType": ar.TYPE_CHOICE}
    if entries is not None:
        attributes["android:entries"] = entries
    if entry_values is not None:
        attributes["android:entryValues"] = entry_values
    return AxmlElement(name="restriction", attributes=attributes, depth=1)


def test_an_unresolvable_member_drops_its_pair_rather_than_shifting_the_rest():
    """The silent-wrong-value case.

    If a member is dropped instead of held in place, every later label slides up
    against the wrong value. Both sides still have equal length, so a length check
    passes — and the device is sent a value the operator never chose.
    """
    table = _FakeTable({
        0x7F040001: ["Low", "Medium", "High"],
        0x7F040002: ["1", None, "3"],       # the middle value will not resolve
    })

    options = ar._options(_choice_element(), table)

    assert [(o.label, o.value) for o in options] == [("Low", "1"), ("High", "3")]


def test_equal_length_drops_on_both_sides_do_not_misalign():
    """Both arrays lose one member, at different indexes.

    Lengths match afterwards, so a length guard alone sees nothing wrong.
    """
    table = _FakeTable({
        0x7F040001: [None, "Medium", "High"],
        0x7F040002: ["1", "2", None],
    })

    options = ar._options(_choice_element(), table)

    assert [(o.label, o.value) for o in options] == [("Medium", "2")]


def test_an_unreadable_value_array_is_not_replaced_by_the_labels():
    """`entryValues` declared but unresolvable must NOT fall back to the labels.

    Doing so sends the app the human-readable prose in place of the value it
    declared — the app ignores it, uses its default, and the console reports the
    policy applied. "Not declared" and "declared but unreadable" are different
    facts and must not collapse into one.
    """
    table = _FakeTable({0x7F040001: ["Allow ads on all sites", "Block them"]})

    options = ar._options(_choice_element(), table)

    assert options == (), "prose was offered as the value to send"


def test_an_app_declaring_only_labels_still_gets_a_dropdown():
    """The legitimate labels-only case must keep working."""
    table = _FakeTable({0x7F040001: ["us-east-1", "eu-west-1"]})

    options = ar._options(_choice_element(entry_values=None), table)

    assert [(o.label, o.value) for o in options] == [
        ("us-east-1", "us-east-1"),
        ("eu-west-1", "eu-west-1"),
    ]


def test_mismatched_lengths_refuse_rather_than_guess():
    table = _FakeTable({
        0x7F040001: ["Low", "Medium", "High"],
        0x7F040002: ["1", "2"],
    })

    assert ar._options(_choice_element(), table) == ()
