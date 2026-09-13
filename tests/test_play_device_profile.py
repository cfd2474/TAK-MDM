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

"""Device profile is picked from a list, not typed (W152).

⚠️ Play serves a build matched to the profile. A 32-bit profile makes it hand
back an armeabi-v7a APK — a perfectly valid APK that is the wrong binary for an
arm64 tablet, and nothing downstream calls that an error. A free-text box asked
an operator to know 23 codenames and get the architecture right by memory.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.services import google_play_link as gpl


def _panel(html: str) -> str:
    start = html.index('data-tab-panel="googleplay"')
    return html[start : html.index("tab-panel", start + 10)]


# --------------------------------------------------------------------------- #
# The list itself
# --------------------------------------------------------------------------- #


def test_the_default_is_one_of_the_offered_profiles():
    """⚠️ Otherwise the form opens with nothing selected and the first entry —
    whatever it happens to be — is what gets submitted."""
    assert gpl.DEFAULT_DEVICE in {p for p, _, _ in gpl.DEVICE_PROFILES}


def test_the_default_is_64_bit():
    """The fleet is arm64; a 32-bit default would quietly fetch wrong builds."""
    abi = next(a for p, _, a in gpl.DEVICE_PROFILES if p == gpl.DEFAULT_DEVICE)

    assert abi == "arm64-v8a"


def test_profiles_are_unique_and_complete():
    names = [p for p, _, _ in gpl.DEVICE_PROFILES]

    assert len(names) == len(set(names))
    assert len(names) == 23, "gpapi's device.properties carried 23 profiles"


def test_every_profile_has_a_model_and_an_abi():
    for profile, model, abi in gpl.DEVICE_PROFILES:
        assert profile and model and abi, profile


def test_grouping_is_by_architecture_and_puts_64_bit_first():
    groups = gpl.profiles_by_architecture()

    assert groups[0][0].startswith("64-bit")
    # Every profile appears exactly once across the groups.
    flat = [p for _, rows in groups for p, _, _ in rows]
    assert sorted(flat) == sorted(p for p, _, _ in gpl.DEVICE_PROFILES)


def test_each_group_holds_only_its_own_architecture():
    for name, rows in gpl.profiles_by_architecture():
        for profile, _, abi in rows:
            if name.startswith("64-bit"):
                assert abi == "arm64-v8a", profile
            elif name.startswith("32-bit"):
                assert abi.startswith("armeabi"), profile


# --------------------------------------------------------------------------- #
# The form
# --------------------------------------------------------------------------- #


def test_the_field_is_a_dropdown_not_a_text_box(client: TestClient):
    panel = _panel(client.get("/admin").text)

    assert '<select id="gp-device"' in panel
    assert 'type="text" id="gp-device"' not in panel


def test_every_profile_is_offered(client: TestClient):
    panel = _panel(client.get("/admin").text)

    for profile, _, _ in gpl.DEVICE_PROFILES:
        assert f'value="{profile}"' in panel, profile


def test_the_default_is_preselected(client: TestClient):
    panel = _panel(client.get("/admin").text)
    option = re.search(
        r'<option value="%s"[^>]*>' % re.escape(gpl.DEFAULT_DEVICE), panel
    )

    assert option and "selected" in option.group(0)


def test_the_architecture_is_visible_on_every_option(client: TestClient):
    """⚠️ The codename alone says nothing. `rm_5_pro` being 32-bit is the whole
    decision, and it is not recoverable from the name."""
    panel = _panel(client.get("/admin").text)

    assert panel.count("arm64-v8a") >= 18
    assert "armeabi-v7a" in panel


# --------------------------------------------------------------------------- #
# ⚠️ The list is a convenience, not a gate
# --------------------------------------------------------------------------- #


def test_a_profile_outside_the_list_is_still_accepted(db, token_vault):
    """If gpapi gains a profile before this list does, that should cost an
    operator a dropdown entry — never the ability to link an account."""
    import subprocess

    class _Apkeep:
        def __call__(self, *a, **k):
            return subprocess.CompletedProcess(
                args=[], stdout="Suceeded. AAS token: aas_et/AK\n", stderr="", returncode=0
            )

    link = gpl.link_account(
        db, token_vault, email="ops@example.com",
        oauth_token="oauth2_4/" + "x" * 20,
        device_profile="some_future_pixel", runner=_Apkeep(),
    )

    assert link.device_profile == "some_future_pixel"
