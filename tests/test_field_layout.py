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

"""A label sits directly above its own field (W147).

⚠️ `.row` is `display:flex` with `flex: 1 1 320px` on its children, so a label
placed there as a *sibling* of its input gets a 320px track of its own. The
label then sits at the left of that track while the input begins wherever the
label's text ended — and the wider the panel, the further apart they drift,
until they read as two unrelated things.

The fix is structural, so this guards the structure: a label and its input
belong to the same block, and a row that lists fields rather than spreading them
across columns says so with `stacked`.
"""

from __future__ import annotations

import io
from html.parser import HTMLParser
from pathlib import Path

TEMPLATES = Path("app/web/templates")


class _RowLabels(HTMLParser):
    """Finds labels that are *direct children* of an un-stacked `.row`."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.offenders: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "label" and self.stack and self.stack[-1] == "row":
            self.offenders.append(attrs.get("for") or "(unnamed)")
        if tag in ("div", "form", "section", "fieldset", "p", "span", "td", "th"):
            classes = (attrs.get("class") or "").split()
            kind = "other"
            if "row" in classes and "stacked" not in classes:
                kind = "row"
            self.stack.append(kind)

    def handle_endtag(self, tag):
        if tag in ("div", "form", "section", "fieldset", "p", "span", "td", "th"):
            if self.stack:
                self.stack.pop()


def _offenders(path: Path) -> list[str]:
    parser = _RowLabels()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.offenders


def test_no_label_is_a_direct_child_of_a_spread_row():
    """⚠️ The exact defect: `<div class="row"><label>…</label><input>` puts the
    two in separate flex tracks, which is how they end up far apart."""
    found = {
        path.name: bad
        for path in sorted(TEMPLATES.glob("*.html"))
        if (bad := _offenders(path))
    }

    assert not found, (
        f"labels sitting beside their fields instead of above them: {found}. "
        f"Wrap each label and its input in a block, or mark the row `stacked`."
    )


def test_the_stacked_modifier_exists_and_collapses_the_gap():
    """⚠️ `gap: 0` is not cosmetic. `label` already carries a 12px top margin,
    and a 16px column gap on top of it double-spaces the list."""
    css = io.open("app/web/static/atlas.css", encoding="utf-8").read()

    assert ".row.stacked" in css
    assert "flex-direction: column" in css
    assert "gap: 0" in css


def test_name_and_description_forms_stack_their_fields():
    """The pages the operator named, plus the ones with the same shape."""
    expected = {
        "groups.html": "group-name",
        "storefront_detail.html": "sf-name",
        "manage.html": "groups-name",
        "policy_new.html": "name",
        "profile_editor.html": "name",
        "apps.html": "sf-new-name",
    }
    for filename, field in expected.items():
        text = (TEMPLATES / filename).read_text(encoding="utf-8")
        assert f'for="{field}"' in text, f"{filename}: {field} label went missing"
        assert not _offenders(TEMPLATES / filename), filename
