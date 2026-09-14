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

"""The unsaved-changes guard warns about edits, not about loading (W155).

Saving a policy and then navigating away warned about unsaved changes that did
not exist. The cause was not the guard: the ATAK settings table replaces its
fallback inputs once a schema fetch resolves, and it announced that by firing a
synthetic `input` so the rail would recount its completion ticks. That event
bubbles to the form, and the guard cannot tell a synthetic `input` from a
keystroke — so every visit to a page carrying `[data-atak-prefs]` became dirty
on load, with nobody having typed anything.

⚠️ `event.isTrusted` is not the fix. Three other sites dispatch `input` after
adding a row on the operator's behalf, and those *are* edits — filtering
untrusted events would have silently stopped warning about real unsaved work,
which is the worse failure of the two.

Reproduced against the real rendered page in jsdom before and after: with the
old dispatch the guard prompts on a page nobody touched; with `atlas:recount` it
does not, while a genuine keystroke and a script-added row both still warn.
"""

from __future__ import annotations

import io
import re

from fastapi.testclient import TestClient

JS = "app/web/static/atlas.js"


def _source() -> str:
    return io.open(JS, encoding="utf-8").read()


def test_the_load_time_recount_is_not_an_input_event():
    """⚠️ The actual bug, in one assertion."""
    source = _source()
    start = source.index("[data-atak-prefs]")
    block = source[start : start + 4000]

    assert 'dispatchEvent(new Event("atlas:recount"' in block
    assert 'dispatchEvent(new Event("input"' not in block


def test_the_rail_still_recounts():
    """⚠️ Renaming the event without teaching the rail about it would trade a
    false warning for a completion tick that never updates — and a rail that
    under-reports is worse, because it is not obviously wrong."""
    source = _source()

    assert 'panelsRoot.addEventListener("atlas:recount", refresh)' in source
    assert 'panelsRoot.addEventListener("input", refresh)' in source


def test_a_submit_still_clears_the_flag():
    source = _source()

    assert 'form.addEventListener("submit", function () { dirty = false; })' in source


def test_edits_made_on_the_operators_behalf_still_count():
    """The three sites that add a row when a button is pressed keep firing
    `input`: the form genuinely differs from what was saved."""
    source = _source()
    adds = re.findall(r'set\.dispatchEvent\(new Event\("input", \{ bubbles: true \}\)\)', source)

    assert len(adds) == 3, f"expected the three row-adding sites, found {len(adds)}"


def test_the_creator_page_carries_the_host_that_triggered_it(client: TestClient):
    """⚠️ Why this showed up on the policy creator at all: that page renders
    every policy type's form, so the ATAK settings host is present even when the
    operator is editing something else entirely."""
    body = client.get("/policies/new?policy_type=APP_CATALOG").text

    assert "data-atak-prefs" in body
    assert "data-policy-form" in body
