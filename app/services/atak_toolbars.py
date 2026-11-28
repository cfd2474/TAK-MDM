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

"""ATAK's custom toolbars, which it calls loadouts (W430).

Operator: "bring in a pref that has custom toolbars … extracts the toolbar(s)
and lists them by name. User can then choose to remove unwanted toolbars, or
rename them."

📖 From ATAK's own source (`LoadoutManager`, `LoadoutItemModel`, ATAK-CIV
`main`, read 2026-10-25):

* each toolbar is one preference, `loadout_entry_key_<uid>`, a **string set**
  of `name=value` strings: `version=2`, `uid`, `title`, `buttons`, and
  optionally `hidden` and `sortOrder`;
* ATAK finds them by that prefix (`readLoadouts`) and takes one added or
  changed while running (`onSharedPreferenceChanged`), so there is no list
  of toolbars to keep alongside;
* `fromStringSet` ignores a set of fewer than 3 members, or one without a uid
  and a title;
* `selected_loadout_key` is the uid of the toolbar in use;
  `default_loadout_key` is the uid of ATAK's built-in "Default".

A toolbar is held in a policy as its uid, its title and its other members
verbatim: a rename changes the title, and nothing else is ATLAS's to edit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import NamedTuple

from app.services import atak_pref_import

KEY_PREFIX = "loadout_entry_key_"
SELECTED_KEY = "selected_loadout_key"
#: W431: the overflow menu's layout (`LoadoutToolsDropDown.PREF_TOOLS_LAYOUT`):
#: "grid" (tiles, ATAK's default) or "list". ATAK applies a change while running.
LAYOUT_KEY = "loadout_tools_layout"
LAYOUTS = ("grid", "list")
DEFAULT_UID = "default_loadout_key"

#: Members ATLAS writes itself, from the policy's uid and title.
_OWN = ("uid=", "title=")
#: A plugin's tool, as `buttons` and `sortOrder` name it.
_PLUGIN_TOOL = re.compile(r"plugin://([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+)/")


def key_for(uid: str) -> str:
    return KEY_PREFIX + uid


def members_for(uid: str, title: str, others) -> list[str]:
    """Every member of a toolbar's set: ATLAS's uid and title, then the rest."""
    return [f"uid={uid}", f"title={title}"] + [m for m in others if not m.startswith(_OWN)]


def plugins_used(members) -> list[str]:
    """The packages of the plugin tools a toolbar holds, sorted."""
    return sorted({found for member in members for found in _PLUGIN_TOOL.findall(member)})


@dataclass(frozen=True)
class Found:
    uid: str
    title: str
    #: Every member other than uid and title, verbatim.
    members: tuple[str, ...]
    #: ATAK's built-in "Default".
    builtin: bool
    plugins: tuple[str, ...]

    def as_json(self) -> dict:
        return {"uid": self.uid, "title": self.title, "members": list(self.members),
                "builtin": self.builtin, "plugins": list(self.plugins)}


class Read(NamedTuple):
    toolbars: list[Found]
    #: The uid the file had in use.
    selected: str | None
    #: W431: the overflow menu layout it had, "grid" or "list".
    layout: str | None


def read(data: bytes) -> Read:
    """The toolbars in an exported `.pref`, the uid it had in use, and its
    overflow menu layout.

    Raises `atak_pref_import.ImportError_` for a file that isn't one; the
    checks are the same as for an import of settings.
    """
    found: list[Found] = []
    selected = layout = None
    for _group, key, _class, value, members in atak_pref_import.raw_entries(data):
        if key == SELECTED_KEY:
            selected = value.strip() or None
            continue
        if key == LAYOUT_KEY:
            # Anything else ATAK reads as its default, grid; carried only if it is one of the two.
            layout = value.strip() if value.strip() in LAYOUTS else None
            continue
        if not key.startswith(KEY_PREFIX):
            continue
        fields = dict(m.split("=", 1) for m in members if "=" in m)
        uid, title = (fields.get("uid") or "").strip(), (fields.get("title") or "").strip()
        # As ATAK: fewer than 3 members, or no uid or title, is not a toolbar.
        if len(members) < 3 or not uid or not title:
            continue
        # One holding characters a preference file can't carry could never be sent.
        if any(atak_pref_import.UNCARRIED in m for m in members):
            continue
        others = tuple(m for m in members if not m.startswith(_OWN))
        found.append(Found(uid, title, others, uid == DEFAULT_UID, tuple(plugins_used(others))))
    return Read(found, selected, layout)
