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

"""A saved app configuration must survive being re-opened and re-saved (W54).

The bug this pins was silent and destructive. The editor rendered saved values as
``value="{{ config_values | tojson }}"`` — double-quoted — and Jinja's `tojson`
escapes ``<``, ``>``, ``&`` and ``'`` but **not** ``"``. JSON is made of double
quotes, so the attribute terminated at the first key and the browser read the
whole value as the single character ``{``.

Re-saving then submitted ``{``, `json.loads` raised, `form_parse` swallowed it and
dropped the row — and the next check-in called `setApplicationRestrictions` with
an empty Bundle, wiping that app's entire configuration off the fleet with no
error anywhere.

The pre-existing test only *rendered* the page and asserted substrings were
present, which the broken markup satisfies. Only a round trip catches it.
"""

from __future__ import annotations

import html.parser
import json

from jinja2 import Environment


class _Attributes(html.parser.HTMLParser):
    """What a browser would actually parse out of the rendered markup."""

    def __init__(self) -> None:
        super().__init__()
        self.by_name: dict[str, str | None] = {}

    def handle_starttag(self, tag, attrs):
        for key, value in attrs:
            self.by_name.setdefault(key, value)


def _attribute_value(markup: str, name: str) -> str | None:
    parser = _Attributes()
    parser.feed(markup)
    return parser.by_name.get(name)


def test_a_json_attribute_survives_html_parsing():
    """The core defect, isolated: `tojson` in a double-quoted attribute."""
    env = Environment(autoescape=True)
    values = {"ExtensionAllowedTypes": "extension", "HomepageLocation": "https://x.test"}

    broken = env.from_string('<input value="{{ v | tojson }}">').render(v=values)
    fixed = env.from_string("<input value='{{ v | tojson }}'>").render(v=values)

    assert _attribute_value(broken, "value") == "{", "the old markup should truncate"
    assert json.loads(_attribute_value(fixed, "value")) == values


def test_the_editor_renders_saved_config_a_browser_can_read_back():
    """Against the real template fragment, not a reconstruction."""
    import pathlib
    import re

    source = pathlib.Path("app/web/templates/_policy_form.html").read_text(encoding="utf-8")
    line = next(
        raw for raw in source.splitlines() if "__values" in raw and "tojson" in raw
    )

    env = Environment(autoescape=True)
    values = {"URLBlocklist": "example.com\nother.test", "AdsSetting": "2"}
    rendered = env.from_string(re.sub(r"\{\{ name \}\}", "app_configs", line)).render(
        config_values=values
    )

    parsed = _attribute_value(rendered, "value")

    assert parsed is not None
    assert json.loads(parsed) == values, "a browser could not read the saved values back"


def test_a_multi_select_value_with_quotes_still_round_trips():
    """Option values come from a third-party APK and may contain anything."""
    env = Environment(autoescape=True)
    values = {"Names": 'He said "hi"\nO\'Brien\n'}

    rendered = env.from_string("<input value='{{ v | tojson }}'>").render(v=values)

    assert json.loads(_attribute_value(rendered, "value")) == values


def test_a_multi_select_value_survives_the_server_side_form_parse():
    """Browser payload -> hidden input -> form -> parsed spec, unmangled.

    The wire format for a multi-select is newline-separated and newline-terminated
    (the terminator is what makes a single selection unambiguous to the agent).
    Anything that strips or normalises whitespace here would silently change what
    the device is told.
    """
    from starlette.datastructures import FormData

    from app.policies import form_parse

    sent = {"URLBlocklist": "Smith, John\n", "AdsSetting": "2"}

    form = FormData(
        [
            ("app_configs__package_name", "com.android.chrome"),
            ("app_configs__values", json.dumps(sent)),
        ]
    )
    spec = form_parse.parse_form("APP_CATALOG", form)

    configs = spec.get("app_configs")
    assert configs, "the row was dropped"
    assert configs[0]["values"] == sent
    assert configs[0]["values"]["URLBlocklist"].endswith("\n"), "the terminator was stripped"
