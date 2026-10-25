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

"""Read an exported ATAK `.pref` for ATAK Core Pref Config (W428).

Operator: import a `.pref` "parsed into the appropriate fields", every value
listed with a checkbox. Asked and answered: only **ATAK's declared settings**
are imported. A real export is ~1,800 entries and 3-5x the 64 KB that
managed configuration can carry, and most of it is ATAK's internal state (map
position, dismissed hints, tool state), so everything else is listed as "not
an ATAK setting" and left out.

Every entry comes back as exactly one of:

* **setting** — declared by this ATAK build, in its own preference group, with
  a value of the declared type: imported, ticked;
* **stripped** — a problem entry (`atak_pref_hygiene`), with the reason;
* **invalid** — declared, but its type or value would break ATAK's parser;
* **other** — anything else.

⚠️ **The file is untrusted XML.** The standard parser fetches no external
entities, and a document declaring a DOCTYPE or ENTITY at all is refused, so
an entity-expansion bomb never reaches it. Its size is capped.

⚠️ **A stripped entry's value is never returned.** Tokens and passwords must
not travel back to a browser to be shown in a table.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass

from app.artifacts.pref_screens import PrefSchema
from app.services import atak_pref, atak_pref_hygiene

#: A real export is ~300 KB; ten times that is not a preference file.
MAX_IMPORT_BYTES = 4 * 1024 * 1024

SETTING, STRIPPED, INVALID, OTHER = "setting", "stripped", "invalid", "other"

_DECLARATION = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY)", re.I)
#: A shown value is cut here; the full one is what is imported.
_SHOWN = 300


class ImportError_(ValueError):
    """The file cannot be read as an ATAK preference file; the message says why."""


@dataclass(frozen=True)
class Entry:
    group: str
    key: str
    java_class: str
    status: str
    #: The value to import (settings) or show (other, invalid); None when stripped.
    value: str | None = None
    #: ATAK's own title for a setting.
    label: str | None = None
    reason: str | None = None

    def as_json(self) -> dict:
        out = {k: v for k, v in asdict(self).items() if v is not None}
        if self.status != SETTING and self.value is not None and len(self.value) > _SHOWN:
            out["value"] = self.value[:_SHOWN] + "…"
        return out


def decode_text(value: str) -> str:
    """Undo `atak_pref.encode_text`: the five `\\uXXXX` escapes ATAK writes."""
    return (
        value.replace("\\u0022", '"')
        .replace("\\u0027", "'")
        .replace("\\u003c", "<")
        .replace("\\u003e", ">")
        .replace("\\u0026", "&")
    )


def _entries(data: bytes):
    if len(data) > MAX_IMPORT_BYTES:
        raise ImportError_(f"the file is {len(data):,} bytes; a preference file is far smaller")
    # ⚠️ First: in UTF-16 the check below would read past a declaration.
    # ATAK writes UTF-8, which never contains a NUL byte.
    if b"\x00" in data:
        raise ImportError_("the file is not UTF-8 text, which is how ATAK writes preference files")
    if _DECLARATION.search(data):
        raise ImportError_("the file declares a DOCTYPE or entities, which a preference file never does")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ImportError_(f"the file is not readable XML ({exc})") from None
    if root.tag != "preferences":
        raise ImportError_("the file is not an ATAK preference file (no <preferences> element)")
    for preference in root.findall("preference"):
        group = preference.get("name") or ""
        for element in preference.findall("entry"):
            yield group, element.get("key") or "", element.get("class") or "", decode_text(element.text or "")


def read(data: bytes, schema: PrefSchema | None) -> list[Entry]:
    """Every entry in the file, judged against the ATAK build's declared settings."""
    declared = {f.key: f for f in schema.fields} if schema else {}
    group_of_settings = schema.preference_group if schema else None
    out: list[Entry] = []
    for group, key, java_class, value in _entries(data):
        rule = atak_pref_hygiene.problem(group, key)
        if rule is not None:
            out.append(Entry(group, key, java_class, STRIPPED, reason=rule.reason, label=rule.name))
            continue
        field = declared.get(key) if group == group_of_settings else None
        if field is None:
            out.append(Entry(group, key, java_class, OTHER, value=value,
                             reason="not a setting this ATAK build declares"))
            continue
        if java_class != field.java_class:
            out.append(Entry(group, key, java_class, INVALID, value=value, label=field.label,
                             reason=f"ATAK declares this as {field.java_class.split('.')[-1]}, "
                                    f"the file has {java_class.split('.')[-1] or 'no type'}"))
            continue
        try:
            normalised = atak_pref.normalise(atak_pref.PrefEntry(key, value, java_class))
        except atak_pref.PrefError as exc:
            out.append(Entry(group, key, java_class, INVALID, value=value, label=field.label, reason=str(exc)))
            continue
        out.append(Entry(group, key, java_class, SETTING, value=normalised, label=field.label))
    return out


def summary(entries: list[Entry]) -> dict[str, int]:
    counts = {SETTING: 0, STRIPPED: 0, INVALID: 0, OTHER: 0}
    for entry in entries:
        counts[entry.status] += 1
    return counts
