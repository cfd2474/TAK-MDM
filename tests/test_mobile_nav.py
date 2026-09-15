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

"""The console's navigation on a phone (W190).

The eight-section banner wraps to three rows on a narrow screen and takes most
of it before any content appears. Below a breakpoint — or on a touch-only
device at any width — it becomes a dismissable grid.

⚠️ **Two decisions here are load-bearing and neither is visible in a
screenshot**, so they are asserted rather than trusted:

* **Width *or* touch, never a user-agent string.** A UA string is the one
  signal that can be wrong about the thing it measures.
* **The toggle is a checkbox, not a button.** A button needs script to collapse
  the panel, `defer` runs after paint, and every page load on a phone would
  flicker a full-screen menu open before closing it.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

CSS = Path("app/web/static/atlas.css")
JS = Path("app/web/static/atlas.js")
BASE = Path("app/web/templates/base.html")

#: Every section the banner offers. The grid must offer the same ones — a menu
#: that silently drops a section is worse than no menu.
SECTIONS = [
    ("/enrollment", "Enroll"),
    ("/fleet", "Manage"),
    ("/policies", "Policies"),
    ("/apps", "Apps"),
    ("/content", "Content"),
    ("/reports", "Reports"),
    ("/admin", "Admin"),
    ("/guides", "Guides"),
]


def _css() -> str:
    return io.open(CSS, encoding="utf-8").read()


# --------------------------------------------------------------------------- #
# How "mobile" is decided
# --------------------------------------------------------------------------- #


def test_the_breakpoint_uses_width_or_touch_capability():
    """⚠️ `hover: none` is what keeps a touch *laptop* on the banner — it has a
    mouse, so it hovers. Width alone would miss a tablet; touch alone would miss
    a narrow desktop window."""
    css = _css()

    assert "@media (max-width: 720px), (hover: none) and (pointer: coarse)" in css


def test_no_user_agent_sniffing_anywhere():
    """⚠️ The one signal that can be wrong about what it measures.

    A UA string hands a 1024px tablet the phone menu, hands a 500px-wide desktop
    window a banner that does not fit, and knows nothing about a device released
    next year. If this ever fails, the fix is a media query, not a longer regex.
    """
    script = io.open(JS, encoding="utf-8").read()

    for needle in ("navigator.userAgent", "navigator.platform", "navigator.vendor"):
        assert needle not in script, f"{needle} is not how this decides"


def test_the_grid_and_toggle_cost_nothing_on_a_desktop():
    """Both are display:none outside the query, so a wide screen renders exactly
    what it did before."""
    css = _css()
    before = css.split("@media (max-width: 720px), (hover: none)")[0]

    assert ".nav-toggle { display: none; }" in before
    assert ".nav-grid { display: none; }" in before


# --------------------------------------------------------------------------- #
# Why a checkbox
# --------------------------------------------------------------------------- #


def test_the_menu_opens_without_script():
    """⚠️ The reason it is a checkbox rather than a button.

    The open state is a CSS sibling selector, so it is correct on the first
    frame. A button would need `atlas.js` to collapse a panel that starts open —
    and `defer` runs after paint, so every page load on a phone would flash the
    menu.
    """
    css = _css()

    assert ".nav-switch:checked ~ .nav-grid" in css
    assert "display: grid;" in css.split(".nav-switch:checked ~ .nav-grid")[1][:120]


def test_script_may_close_the_menu_but_never_open_it():
    """⚠️ If script could open it, the no-script path would be a lie.

    Everything in `atlas.js` here is enhancement: Escape, tapping outside, and
    keeping `aria-expanded` truthful. The only assignment that sets `checked`
    true is the keyboard toggle, which is replacing what a real button would
    have done for free.
    """
    script = io.open(JS, encoding="utf-8").read()
    block = script.split("Mobile navigation (W190)")[1].split("Confirm before submit")[0]

    assert "navSwitch.checked = false;" in block
    assert block.count("navSwitch.checked = true") == 0, (
        "script opens the menu; the CSS-only path must stay the way it opens"
    )


def test_the_toggle_is_reachable_by_keyboard():
    """A label is not a button: the browser gives it a click and nothing else."""
    markup = io.open(BASE, encoding="utf-8").read()
    script = io.open(JS, encoding="utf-8").read()

    assert 'tabindex="0"' in markup
    assert 'role="button"' in markup
    assert 'e.key === " " || e.key === "Enter"' in script


def test_what_a_screen_reader_is_told_is_kept_in_step():
    """⚠️ `aria-expanded` is the one thing CSS cannot update.

    Without this the control announces "collapsed" for the entire time it is
    open, which is worse than saying nothing at all.
    """
    script = io.open(JS, encoding="utf-8").read()

    assert 'setAttribute("aria-expanded"' in script
    assert 'navSwitch.addEventListener("change", syncNavState)' in script


# --------------------------------------------------------------------------- #
# What it renders
# --------------------------------------------------------------------------- #


def test_the_grid_offers_every_section_the_banner_does(client: TestClient):
    """⚠️ Two lists of the same sections is a drift risk, so it is checked.

    A menu that silently drops a section is worse than no menu: the page is
    still there, and the only way to reach it is a URL nobody has.
    """
    body = client.get("/fleet").text
    grid = body.split('class="nav-grid"')[1].split("</nav>")[0]

    for href, label in SECTIONS:
        assert f'href="{href}"' in grid, f"{label} is missing from the mobile menu"


def test_the_current_section_is_marked_in_the_grid(client: TestClient):
    """The same signal the banner gives, so the menu answers "where am I"."""
    body = client.get("/fleet").text
    grid = body.split('class="nav-grid"')[1].split("</nav>")[0]

    marked = re.findall(r'<a href="([^"]+)" class="on"', grid)
    assert marked == ["/fleet"], marked


@pytest.mark.parametrize("path", ["/fleet", "/policies", "/apps", "/admin"])
def test_every_page_carries_the_menu(client: TestClient, path):
    """It lives in `base.html`, so this is really a guard against a page that
    overrides the header block and loses it."""
    body = client.get(path).text

    assert 'id="nav-switch"' in body
    assert 'class="nav-grid"' in body
