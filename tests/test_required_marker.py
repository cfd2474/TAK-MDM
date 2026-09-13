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

"""Every mandatory field is marked, project-wide (W146).

The asterisk itself is added in the browser from the `required` attribute, so
what is worth guarding here is the thing that would silently stop it working: a
mandatory control with no label to put a mark beside, or a field the server
demands that the page never marks as required at all.

⚠️ Keyed on `required` rather than a hand-maintained list. The attribute is
already what the browser enforces and what the route's `Form(...)` signature
mirrors; a third statement of the same fact is the one that goes stale.
"""

from __future__ import annotations

import ast
import io
import re
from pathlib import Path

TEMPLATES = Path("app/web/templates")

#: ⚠️ Controls that are mandatory and have no visible label to mark.
#:
#: Each is a single-purpose *toolbar* form — a file picker or one text box
#: beside its submit button — where the panel heading above is the field's name
#: and the control carries `aria-label`. There is no per-field label, so there
#: is nowhere to put an asterisk. Listed rather than ignored so that a *new*
#: unlabelled required field fails this test instead of joining them quietly.
UNLABELLED = {
    ("admin.html", "name"),        # Custom attributes: "Attribute name"
    ("apps.html", "file"),         # Upload a package
    ("content.html", "file"),      # Upload a file / upload a package
    ("content.html", "files"),     # rows under the `data-required` "Files" label
    ("policies.html", "name"),     # clone-a-policy row: "New policy name"
    ("policy_detail.html", "name"),
}

CONTROL = re.compile(r"<(input|select|textarea)\b([^>]*?)>", re.S)


def _required_controls():
    for path in sorted(TEMPLATES.glob("*.html")):
        text = path.read_text(encoding="utf-8")
        label_fors = set(re.findall(r'<label[^>]*\bfor="([^"]+)"', text))
        for tag, attrs in CONTROL.findall(text):
            if not re.search(r"(?:^|\s)required(?:\s|=|/|$)", attrs):
                continue
            if 'type="hidden"' in attrs:
                continue
            name = (re.search(r'name="([^"]+)"', attrs) or [None, ""])[1]
            ident = (re.search(r'id="([^"]+)"', attrs) or [None, ""])[1]
            yield path.name, name, ident, ident in label_fors


def test_every_required_field_has_something_to_mark():
    """⚠️ A required control with no label gets no asterisk — silently. This is
    the only way that failure becomes visible without opening a browser."""
    orphans = [
        (page, name)
        for page, name, ident, labelled in _required_controls()
        if not labelled and (page, name) not in UNLABELLED
    ]

    assert not orphans, (
        f"required fields with no label to mark: {sorted(set(orphans))}. Give the "
        f"control an id and a <label for=...>, or add it to UNLABELLED with a "
        f"reason."
    )


def test_the_marker_is_driven_by_the_required_attribute():
    js = io.open("app/web/static/atlas.js", encoding="utf-8").read()

    assert '"[required]"' in js
    assert "req-star" in js


def test_the_marker_runs_before_anything_else_can_throw():
    """⚠️ Position is load-bearing, not tidiness.

    A top-level throw anywhere in this file stops every later block from
    evaluating. The marker sat last and a missing search control on the Apps
    page took it out completely — so it runs first, where only its own failure
    can stop it.
    """
    js = io.open("app/web/static/atlas.js", encoding="utf-8").read()

    assert js.index("req-star") < js.index("/* --- Modal")


def test_the_marker_is_red_and_not_only_red():
    """Colour alone is not a distinction for a red-green colourblind reader, so
    the mark is also a glyph optional fields do not have, and it is announced."""
    css = io.open("app/web/static/atlas.css", encoding="utf-8").read()
    js = io.open("app/web/static/atlas.js", encoding="utf-8").read()

    assert ".req-star" in css and "var(--bad" in css
    assert 'setAttribute("aria-label", "required")' in js


# --------------------------------------------------------------------------- #
# ⚠️ The other half: a field the server demands but the page never marks
# --------------------------------------------------------------------------- #


def test_no_form_field_is_mandatory_only_on_the_server():
    """A field the route requires and the page does not is one the operator can
    submit empty, learning about it from an error page instead of an asterisk.

    `policy_type` is exempt: it is a `<select>` with no empty option, so the
    browser always submits one and there is nothing for an operator to fill in.
    """
    exempt = {("/policies", "policy_type")}

    source = io.open("app/web/routes.py", encoding="utf-8").read()
    tree = ast.parse(source)
    mandatory: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        path = None
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call) and dec.args and isinstance(dec.args[0], ast.Constant):
                path = dec.args[0].value
        if not path or not node.args.defaults:
            continue
        named = node.args.args[-len(node.args.defaults):]
        for arg, default in zip(named, node.args.defaults):
            if not isinstance(default, ast.Call):
                continue
            func = default.func
            if getattr(func, "id", getattr(func, "attr", "")) != "Form":
                continue
            has_default = any(k.arg == "default" for k in default.keywords)
            ellipsis = (
                default.args
                and isinstance(default.args[0], ast.Constant)
                and default.args[0].value is Ellipsis
            )
            if ellipsis or (not default.args and not has_default):
                mandatory.add((path, arg.arg))

    form_re = re.compile(r'<form\b[^>]*action="([^"]+)"[^>]*>(.*?)</form>', re.S)
    unmarked = []
    for template in sorted(TEMPLATES.glob("*.html")):
        text = template.read_text(encoding="utf-8")
        for action, body in form_re.findall(text):
            base = action.split("?")[0]
            for tag, attrs in CONTROL.findall(body):
                name = (re.search(r'name="([^"]+)"', attrs) or [None, ""])[1]
                if (base, name) not in mandatory or (base, name) in exempt:
                    continue
                if 'type="hidden"' in attrs:
                    continue
                if not re.search(r"(?:^|\s)required(?:\s|=|/|$)", attrs):
                    unmarked.append((template.name, base, name))

    assert not unmarked, (
        f"mandatory on the server but not marked required in the page: {unmarked}"
    )
