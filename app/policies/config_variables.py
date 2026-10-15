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

"""Device variables in configuration values (W370).

One shared policy, a different value on every device: `callsign =
${device.name}` gives each tracker its own name. Substituted per device, never
when the policy is saved.

**The syntax, and nothing more:** ``${device.<field>}`` for the fields in
`DEVICE_VARIABLES`, and ``${attribute.<Name>}`` for an operator-defined custom
attribute, its name exactly as defined (spaces allowed). Anything else
starting ``${`` is an error: no fallbacks, no expressions, no escape for a
literal ``${`` (the customer spec asks for none to be invented ad hoc).

**A missing value is never papered over.** No name set, an attribute left
blank, a value unusable: `render` returns no text and says which variables
were missing, and the caller leaves that one setting out. The literal
``${…}``, an empty string, or a made-up stand-in never reach a device.

**JSON stays JSON.** A value that is a JSON object or array (AndroidTAKTracker's
`serversJson`) with every variable inside a quoted string gets each value
JSON-escaped, so a name with a quote in it cannot break the document. Every
other byte of the template is kept as written. Anywhere else the value is
inserted as is; the consumer escapes for its own format (ATAK's `.pref`
writer does).

⚠️ **Pure, and the only implementation.** Delivery and the console's preview
both call `render`, so a preview cannot show what a device will not get.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass

DEVICE = "device"
ATTRIBUTE = "attribute"


@dataclass(frozen=True)
class Variable:
    name: str
    label: str
    description: str
    example: str


#: The device fields a template may name: only data ATLAS really holds.
DEVICE_VARIABLES: tuple[Variable, ...] = (
    Variable(
        "device.name", "Device name",
        "The name set on the device's page. Missing until a name is set.", "PATROL-22",
    ),
    Variable(
        "device.id", "ATLAS device ID",
        "ATLAS's own identifier for the device. Unique and never changes, but long.",
        "1066ef88-fd76-4bc8-8e7a-eaa4ff2e93bd",
    ),
    Variable(
        "device.serial", "Serial number",
        "The hardware serial. Missing when Android does not reveal it.", "R5GL40MMHRN",
    ),
    Variable(
        "device.model", "Model",
        "The model the device reports. Missing until its first check-in.", "SM-X520",
    ),
)
DEVICE_FIELDS = frozenset(v.name for v in DEVICE_VARIABLES)

#: Longest value one variable may contribute, and longest rendered result.
MAX_VALUE = 256
MAX_RESULT = 65536

_REFERENCE = re.compile(r"\$\{([^{}$\r\n]*)\}")
_DEVICE_FIELD = re.compile(r"[a-z_]+")


class TemplateError(ValueError):
    """A template that cannot be rendered, said in words an operator can act on."""


def has_variables(text: str) -> bool:
    return "${" in text


def references(text: str) -> list[str]:
    """Every variable `text` names, in order, repeats kept. Raises on a malformed one."""
    found: list[str] = []
    position = 0
    while (start := text.find("${", position)) != -1:
        match = _REFERENCE.match(text, start)
        if match is None:
            raise TemplateError(
                f"{text[start:start + 24]!r}… starts a variable but never closes it. "
                "Write it as ${device.name} or ${attribute.Unit}"
            )
        found.append(_check_name(match.group(1)))
        position = match.end()
    return found


def _check_name(name: str) -> str:
    namespace, dot, field = name.partition(".")
    if namespace == DEVICE and dot and _DEVICE_FIELD.fullmatch(field):
        if name not in DEVICE_FIELDS:
            known = ", ".join(sorted(DEVICE_FIELDS))
            raise TemplateError(f"${{{name}}} is not a device variable. Available: {known}")
        return name
    if namespace == ATTRIBUTE and dot and field.strip() == field and field:
        return name
    raise TemplateError(
        f"${{{name}}} is not a variable. Use ${{device.<field>}} or ${{attribute.<Name>}}"
    )


def check_setting(key: str, value: str) -> str:
    """`value` if every variable in it is well formed; ValueError naming `key` if not.

    For the policy specs' validators, so a malformed or unknown `${…}` is
    refused on every path that saves a policy.
    """
    try:
        references(value)
    except TemplateError as exc:
        raise ValueError(f"{key}: {exc}") from exc
    return value


def problems(text: str, attributes: frozenset[str] | set[str]) -> list[str]:
    """What is wrong with a template, given the custom attributes that exist.

    For the editor, before saving. Empty when it is fine.
    """
    try:
        names = references(text)
    except TemplateError as exc:
        return [str(exc)]
    return [
        f"${{{name}}}: no custom attribute is called {name.partition('.')[2]!r}"
        for name in dict.fromkeys(names)
        if name.startswith(f"{ATTRIBUTE}.") and name.partition(".")[2] not in attributes
    ]


@dataclass(frozen=True)
class Rendered:
    #: The value for this device, or None when it must be left out.
    text: str | None
    #: Variables with no usable value on this device; empty when `text` is set.
    missing: tuple[str, ...] = ()
    #: Set when the template itself is broken (and `text` is None).
    error: str | None = None


def usable(value: str | None) -> str | None:
    """A device or operator value fit to substitute, or None (missing)."""
    if value is None or value == "" or len(value) > MAX_VALUE:
        return None
    if any(unicodedata.category(ch) == "Cc" for ch in value):
        return None
    return value


def render(text: str, values: Mapping[str, str | None]) -> Rendered:
    """`text` with every variable replaced from `values` (name → value or None)."""
    if not has_variables(text):
        return Rendered(text)
    try:
        names = references(text)
    except TemplateError as exc:
        return Rendered(None, error=str(exc))
    resolved = {name: usable(values.get(name)) for name in names}
    missing = tuple(name for name in dict.fromkeys(names) if resolved[name] is None)
    if missing:
        return Rendered(None, missing=missing)
    encode = _json_string if _variables_inside_json_strings(text) else _as_is
    out = _REFERENCE.sub(lambda m: encode(resolved[m.group(1)]), text)
    if len(out) > MAX_RESULT:
        return Rendered(None, error=f"the value would be {len(out)} characters, over {MAX_RESULT}")
    return Rendered(out)


def _as_is(value: str) -> str:
    return value


def _json_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)[1:-1]


#: Stands in for each variable while checking whether the template is JSON.
#: Letters and digits: valid inside a JSON string, invalid anywhere else in
#: JSON. So a template that still parses with it in place has every variable
#: inside a string.
_SENTINEL = "ATLASVARIABLE7Q3"


def _variables_inside_json_strings(text: str) -> bool:
    """Whether `text` is a JSON object or array with every variable in a string."""
    try:
        document = json.loads(_REFERENCE.sub(_SENTINEL, text))
    except ValueError:
        return False
    return isinstance(document, (dict, list))
