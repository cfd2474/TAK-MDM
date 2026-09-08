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

"""The multi-app kiosk console control (W68).

⚠️ These test the **rendered page**, not the macro in isolation. The control is
several inputs whose names have to agree with `form_parse`, and the way that goes
wrong is a rename on one side only — which no unit test of either side alone
would notice.
"""

from __future__ import annotations

import pathlib

from fastapi.testclient import TestClient

from app.policies.form_parse import parse_form


def test_the_multi_app_control_renders_with_everything_it_needs(client: TestClient):
    body = client.get("/policies/new/single").text

    # The control itself, and the two names form_parse reads.
    assert "data-kiosk-apps" in body
    assert 'name="multi_app_packages__package_name"' in body
    assert 'name="multi_app_packages__favorite"' in body

    # Ordering, which *is* the arrangement of the home screen.
    assert "data-move-up" in body
    assert "data-move-down" in body

    # The preview, which is the only place the column count and the order have a
    # visible effect before the policy reaches a device.
    assert "data-kiosk-preview" in body
    assert 'data-field="launcher_columns"' in body

    # Night mode, whose choices are string-valued — the case that would have been
    # silently dropped by the old int-only enum parsing.
    assert 'name="kiosk_night_hue"' in body


def test_the_launcher_wallpaper_field_is_gone(client: TestClient):
    """The Wallpaper policy already sets the device wallpaper and the launcher's
    window is transparent, so a second field would be two policies writing one
    setting — and the loser would lose silently."""
    body = client.get("/policies/new/single").text
    assert "launcher_wallpaper_file_id" not in body


class _Form:
    """The multi-value mapping Starlette hands the parser."""

    def __init__(self, pairs: list[tuple[str, str]]):
        self._pairs = pairs

    def get(self, key: str, default=None):
        for k, v in self._pairs:
            if k == key:
                return v
        return default

    def getlist(self, key: str) -> list[str]:
        return [v for k, v in self._pairs if k == key]

    def __contains__(self, key: str) -> bool:
        return any(k == key for k, _ in self._pairs)

    def keys(self):
        return [k for k, _ in self._pairs]


def _parse(pairs: list[tuple[str, str]]) -> dict:
    return parse_form("KIOSK", _Form(pairs))


def test_row_order_becomes_app_order():
    spec = _parse(
        [
            ("multi_app_packages__package_name", "com.c"),
            ("multi_app_packages__activity", ""),
            ("multi_app_packages__package_name", "com.a"),
            ("multi_app_packages__activity", ""),
            ("multi_app_packages__package_name", "com.b"),
            ("multi_app_packages__activity", ""),
        ]
    )
    assert [a["package_name"] for a in spec["multi_app_packages"]] == [
        "com.c",
        "com.a",
        "com.b",
    ]


def test_a_favourite_is_matched_by_package_not_by_position():
    """⚠️ The bug this exists for. An unchecked checkbox does not submit at all,
    so three rows with only the last one ticked send **one** favourite value. Any
    positional pairing would put that favourite on the first app — and a wrong
    favourite looks deliberate rather than broken.
    """
    spec = _parse(
        [
            ("multi_app_packages__package_name", "com.first"),
            ("multi_app_packages__activity", ""),
            ("multi_app_packages__package_name", "com.second"),
            ("multi_app_packages__activity", ""),
            ("multi_app_packages__package_name", "com.third"),
            ("multi_app_packages__activity", ""),
            # Only the third row's box was ticked.
            ("multi_app_packages__favorite", "com.third"),
        ]
    )
    favourites = [a["package_name"] for a in spec["multi_app_packages"] if a.get("favorite")]
    assert favourites == ["com.third"]


def test_an_empty_row_is_dropped_without_shifting_the_activities():
    spec = _parse(
        [
            ("multi_app_packages__package_name", ""),
            ("multi_app_packages__activity", "ignored"),
            ("multi_app_packages__package_name", "com.real"),
            ("multi_app_packages__activity", "com.real.Main"),
        ]
    )
    assert spec["multi_app_packages"] == [
        {"package_name": "com.real", "activity": "com.real.Main"}
    ]


def test_the_same_app_chosen_twice_is_one_row():
    spec = _parse(
        [
            ("multi_app_packages__package_name", "com.a"),
            ("multi_app_packages__activity", ""),
            ("multi_app_packages__package_name", "com.a"),
            ("multi_app_packages__activity", ""),
        ]
    )
    assert len(spec["multi_app_packages"]) == 1


def test_a_string_valued_enum_survives_the_form():
    """⚠️ Every enum reaching this form used to be an IntEnum, so the parser
    coerced with `int()`. W68's night hue and orientation are string-valued, and
    that coercion would have returned None and dropped the operator's choice in
    silence."""
    spec = _parse([("kiosk_night_mode", "true"), ("kiosk_night_hue", "amber")])
    assert spec["kiosk_night_hue"] == "amber"


def test_an_int_valued_enum_still_parses_as_an_int():
    """The other half: PASSWORD's quality is an IntEnum and must not become a
    string, or the spec would refuse it."""
    spec = parse_form("PASSWORD", _Form([("quality", "3")]))
    assert spec["quality"] == 3


# --------------------------------------------------------------------------- #
# The dock, the activity picker, and where the section sits (W95)
# --------------------------------------------------------------------------- #


def test_four_dock_apps_survive_the_whole_server_round_trip(client: TestClient):
    """⚠️ Written after a dock that showed one app out of four.

    Every layer here was innocent — the loss was a `match_parent` width in the
    launcher's tile layout, which put tiles two, three and four off-screen. This
    pins the half that can be tested in Python, so a future regression can be told
    apart from that one without a device.
    """
    fields = []
    packages = ("com.first", "com.second", "com.third", "com.fourth")
    for package in packages:
        fields.append(("multi_app_packages__package_name", package))
        fields.append(("multi_app_packages__activity", ""))
        fields.append(("multi_app_packages__favorite", package))

    spec = _parse(fields)
    docked = [a["package_name"] for a in spec["multi_app_packages"] if a.get("favorite")]
    assert docked == list(packages), "every ticked row is a dock app"


def test_the_activity_is_a_dropdown_fed_by_the_chosen_app(client: TestClient):
    """The operator should not have to know an activity class by heart — it is a
    fact about the build, and the console can already read it."""
    body = client.get("/policies/new/single").text
    assert 'name="multi_app_packages__activity"' in body
    assert "data-kiosk-activity" in body
    # The same endpoint the single-app kiosk uses, rather than a second source
    # that could disagree with it.
    assert "/policies/app-activities" in client.get("/static/atlas.js").text


def test_a_saved_activity_is_still_an_option_before_the_fetch_lands(client: TestClient):
    """⚠️ Otherwise opening a policy and saving it would silently drop the
    activity: a select can only submit an option it actually holds."""
    fields = [
        ("multi_app_packages__package_name", "com.example.app"),
        ("multi_app_packages__activity", "com.example.app.KioskActivity"),
    ]
    assert _parse(fields)["multi_app_packages"][0]["activity"] == (
        "com.example.app.KioskActivity"
    )


def test_an_activity_still_pairs_with_its_own_row(client: TestClient):
    """⚠️ `form_parse` pairs activities to packages **by index**, so the control
    has to submit even when empty. A select always does; that is why it replaced
    the text box rather than a checkbox-like control."""
    spec = _parse(
        [
            ("multi_app_packages__package_name", "com.first"),
            ("multi_app_packages__activity", ""),
            ("multi_app_packages__package_name", "com.second"),
            ("multi_app_packages__activity", "com.second.Main"),
        ]
    )
    rows = {a["package_name"]: a.get("activity") for a in spec["multi_app_packages"]}
    assert rows == {"com.first": None, "com.second": "com.second.Main"}


def test_multi_app_sits_directly_below_single_app():
    """⚠️ Sub-topic order *is* field declaration order — `grouped_fields` buckets
    by `ui_group` in first-seen order. The two kiosk modes are the same choice and
    had four unrelated sections between them."""
    from app.policies.form_schema import sub_pages

    labels = [page.label for page in sub_pages("KIOSK")]
    assert labels[:2] == ["Single app", "Multi app"]
