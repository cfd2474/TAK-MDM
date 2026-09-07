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

"""The ATAK Config category in the console (W90, chunk A3).

The table itself is built in the browser — 293 settings is not something to
render through Jinja on every policy page — so what is asserted here is the
server's half of that contract: the schema the table is built from, the sub-page
rail it lives in, and, most importantly, **the hidden inputs that keep a saved
policy intact if the table never builds at all**.
"""

from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient

from tests.apk_fixtures import (
    build_apk,
    build_preference_axml,
    pref_category,
    pref_field,
)
from tests.conftest import ADMIN_HEADERS

ATAK_PACKAGE = "com.atakmap.app.civ"
PLUGIN_PACKAGE = "com.atakmap.android.uastool.plugin"

UASTOOL = pathlib.Path(
    "Test Files/ATAK-Plugin-uastool-13.0.6-74628a10-5.8.0-civ-release.apk"
)


def _atak_apk(package_name: str = ATAK_PACKAGE) -> bytes:
    document = build_preference_axml(
        [
            pref_category(
                "Network",
                pref_field("EditTextPreference", "chatPort", title="Chat Port"),
                pref_field(
                    "CheckBoxPreference", "atakControlBluetooth",
                    title="Bluetooth Support", defaultValue=True,
                ),
            )
        ]
    )
    return build_apk(package_name, 1, extra_files={"res/-v.xml": document})


def _upload(client: TestClient, data: bytes) -> None:
    response = client.post(
        "/api/v1/packages",
        files={"file": ("app.apk", data, "application/vnd.android.package-archive")},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code in (200, 201), response.text


def _make_profile(client: TestClient, name: str, sections: dict) -> str:
    response = client.post(
        "/api/v1/profiles", json={"name": name, "sections": sections}, headers=ADMIN_HEADERS
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


# --------------------------------------------------------------------------- #
# The rail
# --------------------------------------------------------------------------- #


def test_the_category_offers_its_three_subtopics_in_order(client: TestClient):
    """Plugin behavior first, as the operator asked, then the two that work."""
    body = client.get("/policies/new").text

    assert 'data-page="atak_config:plugin-behavior"' in body
    assert 'data-page="atak_config:atak-core-pref-config"' in body
    assert 'data-page="atak_config:plugin-pref-config"' in body
    assert body.index('data-page="atak_config:plugin-behavior"') < body.index(
        'data-page="atak_config:atak-core-pref-config"'
    )


def test_plugin_behavior_says_it_is_coming_rather_than_offering_a_form(client: TestClient):
    """⚠️ D94's whole point: a stub sub-topic inside a *working* category.

    Hidden instead, an operator looking for plugin behaviour would conclude it
    was forgotten rather than that it is coming.
    """
    body = client.get("/policies/new").text
    panel = body[body.index('data-page-panel="atak_config:plugin-behavior"'):]
    panel = panel[: panel.index("</section>")]

    assert "Not available yet." in panel
    assert "core_prefs__key" not in panel


def test_the_working_subtopics_are_real_forms(client: TestClient):
    body = client.get("/policies/new").text
    panel = body[body.index('data-page-panel="atak_config:atak-core-pref-config"'):]
    panel = panel[: panel.index("</section>")]

    assert "Not available yet." not in panel
    assert "data-atak-prefs" in panel


def test_a_saved_category_marks_the_rail(client: TestClient):
    pid = _make_profile(
        client,
        "ATAK baseline",
        {"atak_config": {"core_prefs": [{"key": "chatPort", "value": "17012"}]}},
    )
    body = client.get(f"/profiles/{pid}").text

    link = body[body.index('data-page="atak_config:atak-core-pref-config"'):]
    assert 'class="rail-check" >' in link[: link.index("</a>")]


# --------------------------------------------------------------------------- #
# ⚠️ The fallback inputs
# --------------------------------------------------------------------------- #


def test_a_saved_policys_settings_are_in_the_page_before_any_script_runs(
    client: TestClient,
):
    """⚠️ The failure this prevents is silent and total.

    The table is built in the browser from a fetched schema. If that fetch fails
    — the ATAK build was deleted, the request 500s — and the settings existed
    only inside the table, the form would submit nothing for this field and
    saving would **wipe the whole category** with no error anywhere.

    So the server renders them as hidden inputs, and the script removes those
    only once it has built the table from them.
    """
    pid = _make_profile(
        client,
        "ATAK baseline",
        {
            "atak_config": {
                "core_prefs": [
                    {"key": "chatPort", "value": "17012"},
                    {"key": "atakControlBluetooth", "value": "true"},
                ]
            }
        },
    )
    body = client.get(f"/profiles/{pid}").text

    assert '<input type="hidden" name="core_prefs__key" value="chatPort">' in body
    assert '<input type="hidden" name="core_prefs__value" value="17012">' in body
    assert '<input type="hidden" name="core_prefs__key" value="atakControlBluetooth">' in body


def test_the_keys_and_values_are_rendered_in_matching_order(client: TestClient):
    """They submit as two parallel lists paired **by index**, so a page that
    emitted them out of step would apply each value to the wrong setting."""
    pid = _make_profile(
        client,
        "Ordered",
        {
            "atak_config": {
                "core_prefs": [
                    {"key": "aaa", "value": "first"},
                    {"key": "zzz", "value": "second"},
                ]
            }
        },
    )
    body = client.get(f"/profiles/{pid}").text
    block = body[body.index('name="core_prefs__key" value="aaa"'):]

    assert block.index('value="first"') < block.index('name="core_prefs__key" value="zzz"')
    assert block.index('name="core_prefs__key" value="zzz"') < block.index('value="second"')


def test_a_saved_plugin_configuration_survives_a_reload(client: TestClient):
    pid = _make_profile(
        client,
        "Plugin baseline",
        {
            "atak_config": {
                "plugin_prefs": [
                    {
                        "package_name": PLUGIN_PACKAGE,
                        "values": {"uastool.pref_cot_broadcast": "true"},
                    }
                ]
            }
        },
    )
    body = client.get(f"/profiles/{pid}").text

    assert f'name="plugin_prefs__package_name" value="{PLUGIN_PACKAGE}"' in body
    # ⚠️ Single-quoted, because `tojson` escapes `'` but not `"` — see the note on
    # `_app_configs`, where the double-quoted form truncated the value to `{` and
    # wiped an app's configuration on re-save.
    assert "name=\"plugin_prefs__values\" value='{" in body


# --------------------------------------------------------------------------- #
# The schema endpoint
# --------------------------------------------------------------------------- #


def test_the_core_schema_comes_from_the_uploaded_atak_build(client: TestClient):
    _upload(client, _atak_apk())

    payload = client.get("/policies/pref-schema", headers=ADMIN_HEADERS).json()

    assert payload["package_name"] == ATAK_PACKAGE
    assert payload["preference_group"] == "com.atakmap.app.civ_preferences"
    keys = {f["key"] for s in payload["sections"] for f in s["fields"]}
    assert keys == {"chatPort", "atakControlBluetooth"}
    assert payload["warnings"] == []


def test_a_checkbox_arrives_as_a_control_the_table_can_render(client: TestClient):
    _upload(client, _atak_apk())

    payload = client.get("/policies/pref-schema", headers=ADMIN_HEADERS).json()
    field = next(
        f for s in payload["sections"] for f in s["fields"] if f["key"] == "atakControlBluetooth"
    )

    assert field["control"] == "bool"
    assert field["label"] == "Bluetooth Support"
    # In the control's own vocabulary, not binary XML's 1/0.
    assert field["default"] == "true"


def test_no_atak_uploaded_is_a_warning_the_operator_can_read(client: TestClient):
    """⚠️ Not a 404. "Upload an ATAK build" is an ordinary state, and answering
    it with an error status puts the explanation in a console nobody has open."""
    response = client.get("/policies/pref-schema", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    payload = response.json()
    assert payload["sections"] == []
    assert "app library" in payload["warnings"][0]


def test_two_atak_builds_are_reported_as_ambiguous_not_guessed(client: TestClient):
    _upload(client, _atak_apk())
    _upload(client, _atak_apk("com.atakmap.app.mil"))

    payload = client.get("/policies/pref-schema", headers=ADMIN_HEADERS).json()

    assert payload["sections"] == []
    assert "more than one ATAK build" in payload["warnings"][0]


def test_a_plugins_schema_is_asked_for_by_package(client: TestClient):
    _upload(client, _atak_apk())
    plugin = build_apk(
        "com.example.plugin",
        1,
        extra_files={
            "res/-v.xml": build_preference_axml(
                [
                    pref_category(
                        "MAVLink",
                        pref_field("CheckBoxPreference", "plug.broadcast", title="Broadcast"),
                    )
                ]
            )
        },
    )
    _upload(client, plugin)

    payload = client.get(
        "/policies/pref-schema", params={"package": "com.example.plugin"}, headers=ADMIN_HEADERS
    ).json()

    assert payload["package_name"] == "com.example.plugin"
    assert payload["sections"][0]["title"] == "MAVLink"
    assert payload["sections"][0]["fields"][0]["key"] == "plug.broadcast"


def test_an_app_declaring_nothing_says_so_rather_than_looking_broken(client: TestClient):
    """⚠️ Only what is declared in `res/xml` can be read. An app that keeps its
    settings in code is not a failure of this console, and the operator should
    not go hunting for one."""
    _upload(client, build_apk("com.plain.app", 1))

    payload = client.get(
        "/policies/pref-schema", params={"package": "com.plain.app"}, headers=ADMIN_HEADERS
    ).json()

    assert payload["sections"] == []
    assert "res/xml" in payload["warnings"][0]


def test_an_unknown_package_is_a_404(client: TestClient):
    """Unlike the states above, this one genuinely is a bad request — the picker
    only ever offers apps that exist."""
    response = client.get(
        "/policies/pref-schema", params={"package": "com.nope"}, headers=ADMIN_HEADERS
    )
    assert response.status_code == 404


@pytest.mark.skipif(
    not UASTOOL.exists(), reason="the UAS Tool plugin APK is not in this checkout"
)
def test_a_real_plugin_fills_several_pages(client: TestClient):
    """158 settings at 50 a page is four pages — the reason this is a table."""
    _upload(client, UASTOOL.read_bytes())

    payload = client.get(
        "/policies/pref-schema", params={"package": PLUGIN_PACKAGE}, headers=ADMIN_HEADERS
    ).json()

    fields = [f for s in payload["sections"] for f in s["fields"]]
    assert len(fields) > 150
    titles = {s["title"] for s in payload["sections"]}
    assert "General" not in titles
    assert "DJI v5 Settings" in titles


# --------------------------------------------------------------------------- #
# The contract between the page and the script
# --------------------------------------------------------------------------- #

#: Every hook `atlas.js` looks for when it builds the settings table.
#:
#: ⚠️ A coupling test, deliberately. The table is built in the browser, so a
#: renamed or mistyped data attribute breaks it **silently** — the fetch
#: succeeds, `querySelector` returns null, and the operator sees a panel that
#: never finishes loading with nothing in any log. Nothing else in this suite can
#: see that, because nothing else runs the script.
_TABLE_HOOKS = (
    "data-prefs-status",
    "data-prefs-table",
    "data-prefs-body",
    "data-prefs-filter",
    "data-prefs-count",
    "data-prefs-pager",
    "data-prefs-page",
    "data-prefs-prev",
    "data-prefs-next",
)


def test_the_core_panel_carries_every_hook_the_script_looks_for(client: TestClient):
    body = client.get("/policies/new").text
    panel = body[body.index('data-page-panel="atak_config:atak-core-pref-config"'):]
    panel = panel[: panel.index("</section>")]

    assert 'data-prefs-field="core_prefs"' in panel
    assert "data-prefs-fallback" in panel
    for hook in _TABLE_HOOKS:
        assert hook in panel, f"{hook} is missing — the table would never render"


def test_the_plugin_panel_carries_the_picker_the_script_drives(client: TestClient):
    body = client.get("/policies/new").text
    panel = body[body.index('data-page-panel="atak_config:plugin-pref-config"'):]
    panel = panel[: panel.index("</section>")]

    for hook in (
        "data-plugin-prefs",
        'id="plugin-prefs-frame"',
        "data-plugin-prefs-package",
        "data-plugin-prefs-host",
        "data-plugin-prefs-save",
        "data-plugin-prefs-add",
    ):
        assert hook in panel, f"{hook} is missing — the picker would not open"


def test_the_script_builds_its_modal_table_with_the_same_hooks():
    """The plugin picker's table is assembled in the script rather than by Jinja,
    so it has its own copy of the markup — which is exactly the sort of thing
    that drifts from the server-rendered one."""
    script = pathlib.Path("app/web/static/atlas.js").read_text(encoding="utf-8")
    shell = script[script.index("function shell()"):]
    shell = shell[: shell.index("function load(")]

    for hook in _TABLE_HOOKS:
        assert hook in shell, f"{hook} is missing from the picker's table"


def test_a_plugin_build_is_marked_as_one_in_the_picker(client: TestClient):
    """⚠️ Jinja resolves a missing attribute to Undefined, which is falsy.

    `plugin_api` lives on the *version*, not the package, so reading it off the
    package raised nothing at all — the marker simply never appeared, on a
    library made almost entirely of plugins. Nothing failed, nothing logged.
    """
    _upload(client, build_apk("com.example.plug", 1, plugin_api="com.atakmap.app@5.8.0.CIV"))
    _upload(client, build_apk("com.example.ordinary", 1))

    body = client.get("/policies/new").text
    picker = body[body.index("data-plugin-prefs-package"):]
    picker = picker[: picker.index("</select>")]

    plugin = picker[picker.index("com.example.plug"):]
    assert 'data-plugin="1"' in plugin[: plugin.index("</option>")]

    ordinary = picker[picker.index("com.example.ordinary"):]
    assert 'data-plugin="1"' not in ordinary[: ordinary.index("</option>")]


def test_the_picker_does_not_claim_unmarked_apps_are_not_plugins(client: TestClient):
    """A build uploaded before `plugin_api` was recorded has it NULL — which is
    every plugin in the dev library. The copy has to admit that, or the operator
    reads an unmarked plugin as the wrong app."""
    body = client.get("/policies/new").text
    assert "not necessarily not a plugin" in body


# --------------------------------------------------------------------------- #
# Warnings the operator would otherwise never see
# --------------------------------------------------------------------------- #


def test_a_policy_that_cannot_be_delivered_says_so_on_the_page(client: TestClient):
    """⚠️ The console is the *only* place this can be said.

    The same check runs again at check-in, inside the device's own request, where
    it may only degrade to "no ATAK configuration" — a device must not fail to
    check in because a policy is wrong. So a warning that does not reach this
    page reaches nobody, and the policy silently does nothing forever.
    """
    pid = _make_profile(
        client,
        "No ATAK uploaded",
        {"atak_config": {"core_prefs": [{"key": "chatPort", "value": "17012"}]}},
    )

    body = client.get(f"/profiles/{pid}").text

    assert "No ATAK build is in the app library" in body


def test_a_value_its_type_cannot_hold_is_flagged_before_publishing(client: TestClient):
    """A true/false setting holding "maybe" would apply as **false** on the
    device with no error anywhere — `Boolean.parseBoolean` reads anything that is
    not "true" as false."""
    _upload(client, _atak_apk())
    pid = _make_profile(
        client,
        "Bad value",
        {"atak_config": {"core_prefs": [{"key": "atakControlBluetooth", "value": "maybe"}]}},
    )

    body = client.get(f"/profiles/{pid}").text

    assert "atakControlBluetooth" in body
    assert "true/false setting" in body


def test_a_healthy_policy_is_not_nagged_about(client: TestClient):
    """A warning that appears on correct policies is one an operator learns to
    ignore, and then it is worth less than nothing."""
    _upload(client, _atak_apk())
    pid = _make_profile(
        client,
        "Fine",
        {"atak_config": {"core_prefs": [{"key": "chatPort", "value": "17012"}]}},
    )

    body = client.get(f"/profiles/{pid}").text

    assert "No ATAK build is in the app library" not in body
    assert "true/false setting" not in body
