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

"""The rail tick means "this page is configured" (W135).

Operator: ATAK Core Pref Config showed a green check on a policy nothing had
been entered into. The settings table renders one hidden `core_prefs__key` per
setting ATAK declares — 293 of them, all non-empty — and the client-side check
counted them as content the moment the table finished building.
"""

from __future__ import annotations

import pathlib

from fastapi.testclient import TestClient

from app.policies import form_schema
from tests.conftest import ADMIN_HEADERS


def _js() -> str:
    return pathlib.Path("app/web/static/atlas.js").read_text(encoding="utf-8")


def test_the_key_scaffolding_does_not_count_as_content():
    """⚠️ The bug. One hidden key input exists per *declared* setting, whether or
    not the operator has given it a value, so any page with a settings table
    ticked itself on load."""
    js = _js()

    body = js[js.index("function controls(scope)") :]
    body = body[: body.index("function hasContent")]

    assert "/__key$/.test(el.name)" in body


def test_the_value_half_still_counts():
    """⚠️ Nothing is lost by skipping keys: a key is always rendered beside its
    `__value`, and that is the half an operator fills in. Skipping both would
    make a configured page look empty."""
    js = _js()

    body = js[js.index("function controls(scope)") :]
    body = body[: body.index("function hasContent")]

    # The *filter*, not the prose: an earlier version asserted the absence of
    # the string "__value" and failed on the comment explaining why keys are
    # skipped. Only `__key` is excluded, and only at the end of a name.
    filters = [line for line in body.splitlines()
               if "return false" in line and "__" in line]
    assert any("__key$" in line for line in filters)
    assert not any("__value" in line for line in filters)


def test_a_fresh_policy_page_ticks_nothing(client: TestClient):
    """Server-side, the same claim: a policy with no spec has no managed pages,
    so every tick starts hidden."""
    body = client.get("/policies/new", headers=ADMIN_HEADERS).text

    assert 'class="rail-check" hidden' in body
    assert 'class="rail-check">' not in body


def test_an_empty_value_is_not_a_configured_page():
    """⚠️ Key presence is not configuration. A spec carrying `core_prefs: None`
    or `[]` — which `exclude_unset` keeps if it was ever passed explicitly —
    described a page an operator had not filled in."""
    assert form_schema.managed_group_slugs("ATAK_CONFIG", {}) == set()
    assert form_schema.managed_group_slugs("ATAK_CONFIG", {"core_prefs": None}) == set()
    assert form_schema.managed_group_slugs("ATAK_CONFIG", {"core_prefs": []}) == set()


def test_a_real_value_is_a_configured_page():
    """The other direction, so the fix cannot be "never tick anything"."""
    spec = {"core_prefs": [{"key": "chatPort", "value": "17012"}]}

    assert form_schema.managed_group_slugs("ATAK_CONFIG", spec) == {
        "atak-core-pref-config"
    }


def test_false_and_zero_are_values_not_emptiness():
    """⚠️ The trap in tightening this. `allow_camera: false` and a timeout of 0
    are deliberate settings; treating falsiness as unset would hide pages an
    operator had configured to turn something off."""
    managed = form_schema.managed_group_slugs(
        "RESTRICTIONS", {"allow_camera": False, "screen_timeout_seconds": 0}
    )

    assert managed
