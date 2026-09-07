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

"""Guidance lives beside a field, not inside it (W92).

⚠️ **A placeholder reads as a value the field already holds.** An operator leaves
it and saves; a required field then rejects the entry the hint existed to help
them fill. `tests/test_wallpaper.py` records the first time this bit — an
enrolment placeholder of "TAK-Field" was kept as if it were a real SSID — and
W92 generalised that fix to the whole console.

⚠️ **A source-level rule, deliberately.** Checking rendered pages would only
cover the handful a test happens to fetch, and the next placeholder would arrive
in whichever template nobody asserts against.
"""

from __future__ import annotations

import pathlib
import re

TEMPLATES = pathlib.Path("app/web/templates")
SCRIPT = pathlib.Path("app/web/static/atlas.js")

#: Placeholders that stay, because they are the field's **state** rather than a
#: hint about what to type. Blank genuinely means unmanaged in the tri-state
#: design (W10), so the text describes what is true and cannot be mistaken for
#: something the operator meant to save.
STATE = ("not managed", "not set", "••••")

_PLACEHOLDER = re.compile(r'placeholder="([^"]*)"')


def _placeholders(text: str) -> list[str]:
    return [m.group(1) for m in _PLACEHOLDER.finditer(text)]


def test_no_template_hints_from_inside_a_field():
    offenders: list[str] = []
    for template in sorted(TEMPLATES.glob("*.html")):
        for value in _placeholders(template.read_text(encoding="utf-8")):
            if not any(keep in value for keep in STATE):
                offenders.append(f"{template.name}: {value!r}")

    assert not offenders, (
        "these placeholders should be field tips instead — a hint inside the box "
        "reads as a value the field already holds:\n  " + "\n  ".join(offenders)
    )


def test_the_state_placeholders_are_still_there():
    """The other half of the rule. "not managed" carries meaning a tip cannot:
    it describes the field as it stands, and removing it would leave a blank box
    saying nothing about the tri-state it represents."""
    form = (TEMPLATES / "_policy_form.html").read_text(encoding="utf-8")

    assert 'placeholder="not managed"' in form
    assert 'placeholder="not set"' in form


def test_the_script_does_not_reintroduce_hints():
    """⚠️ Rows built at runtime count too. A rule that holds only in Jinja decays
    the moment the console adds a row from script."""
    script = SCRIPT.read_text(encoding="utf-8")
    offenders = [
        line.strip()
        for line in script.splitlines()
        if "placeholder" in line
        and "//" not in line.split("placeholder")[0]
        and not any(keep in line for keep in STATE)
        and "default" not in line
    ]

    assert not offenders, "script-built fields should carry a tip:\n  " + "\n  ".join(offenders)


def test_the_tip_class_exists():
    css = pathlib.Path("app/web/static/atlas.css").read_text(encoding="utf-8")

    assert ".field-tip" in css
    # One *definition*, not three: the console should not grow a second idiom the
    # next time someone needs to explain a field. Anchored to the line start so a
    # scoped refinement — `.rs-row .field-tip`, which makes a tip take the full
    # width inside a wrapping row — is not counted as a rival definition.
    assert len(re.findall(r"^\.field-tip \{", css, re.M)) == 1


def test_a_tip_macro_is_available_to_templates():
    macros = (TEMPLATES / "_macros.html").read_text(encoding="utf-8")
    assert "macro tip(" in macros
