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

"""The menu bar's proportions (W148).

Sizes an operator asked for by ratio rather than by pixel, so the ratios are
what is recorded: the logo twice as tall, the bar's type half again as large.
Written down because "50% larger" is unrecoverable from a stylesheet six months
later — 19.5px reads as an arbitrary number unless something says it is 13×1.5.
"""

from __future__ import annotations

import io
import re
import struct

CSS = "app/web/static/atlas.css"


def _rule(selector: str) -> str:
    """The body of one rule.

    ⚠️ Anchored at the start of a line. Searching for `.pill {` anywhere finds
    `header .who .pill {` first, and the test then reads the scoped rule while
    believing it is looking at the shared one.
    """
    css = io.open(CSS, encoding="utf-8").read()
    start = css.index(chr(10) + selector) + 1
    return css[start : css.index("}", start)]


def test_the_logo_is_twice_as_tall():
    assert "height: 92px;" in _rule("header .brand .brand-logo {")


def test_the_logo_keeps_its_proportions():
    """⚠️ `width: auto` is the whole of it. Setting both dimensions would
    stretch a 560x153 banner into something subtly wrong that nobody can name."""
    rule = _rule("header .brand .brand-logo {")

    assert "width: auto;" in rule
    assert not re.search(r"width:\s*\d", rule)


def test_the_small_screen_logo_scaled_with_it():
    """It exists so the bar does not eat a phone screen; it has to move too, or
    the two sizes stop meaning the same thing."""
    css = io.open(CSS, encoding="utf-8").read()

    assert "header .brand .brand-logo { height: 68px; }" in css


def test_the_bar_font_is_half_again_as_large():
    assert "font-size: 19.5px" in _rule("header nav a {")      # 13 x 1.5
    assert "font-size: 18.75px" in _rule("header .who {")      # 12.5 x 1.5


def test_the_identity_pill_scales_only_inside_the_bar():
    """⚠️ Scoped on purpose: `.pill` is used throughout the console and only the
    menu bar was asked to grow."""
    css = io.open(CSS, encoding="utf-8").read()

    assert "header .who .pill { font-size: 18px;" in css
    assert "font-size: 12px" in _rule(".pill {")


def test_the_bar_floor_rose_with_the_logo():
    """⚠️ A 92px logo inside a 52px floor made the header jump as the image
    loaded. The floor is the logo box: 92 + 5 + 5."""
    assert "min-height: 102px;" in _rule("header {")


def test_the_bar_wraps_rather_than_overflowing():
    """⚠️ The logo is a *banner*, so doubling its height doubles its width —
    168px to 337px — and the wider type pushes the row further still. On a
    narrow window the bar has to fall onto a second line instead of clipping
    the navigation or forcing the page sideways."""
    rule = _rule("header {")
    banner = io.open("app/web/static/atlas-logo.png", "rb").read()
    width, height = struct.unpack(">II", banner[16:24])

    assert "flex-wrap: wrap;" in rule
    # The number in the comment above is only true for this artwork.
    assert round(92 * width / height) == 337
