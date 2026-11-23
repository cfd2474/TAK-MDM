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

"""What a published policy version changed, in words for the audit log (W421).

⚠️ **Setting names, and only the values that cannot be a secret.** A spec
carries TAK Server passwords, Wi-Fi keys and kiosk exit PINs, and the audit log
is shown to every administrator and exported to CSV. So:

* a yes/no setting shows both values (`camera_disabled: off → on`);
* a number shows both values unless its name looks like a secret;
* everything else, text and lists included, says only that it changed.

A string is never shown, whatever its name: whether a field is sensitive is a
judgement a name cannot make reliably, and a missed one leaks the password.
"""

from __future__ import annotations

import re
from typing import Any

#: Names that may hold a secret even as a number (a PIN, a key code).
_SECRETISH = re.compile(r"pass|pin|secret|key|token|code|cred", re.I)

_MISSING = object()


def _shown(name: str, value: Any) -> str | None:
    """The value as the log may show it, or None when it must not be shown."""
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, (int, float)) and not _SECRETISH.search(name):
        return str(value)
    return None


def field_changes(old: dict | None, new: dict | None) -> list[str]:
    """One phrase per top-level setting that differs, in a stable order."""
    old, new = old or {}, new or {}
    phrases = []
    for name in sorted(set(old) | set(new)):
        before, after = old.get(name, _MISSING), new.get(name, _MISSING)
        if before == after:
            continue
        if before is _MISSING:
            phrases.append(f"{name} set" + _arrow(name, None, after))
        elif after is _MISSING:
            phrases.append(f"{name} cleared")
        else:
            phrases.append(f"{name} changed" + _arrow(name, before, after))
    return phrases


def _arrow(name: str, before: Any, after: Any) -> str:
    shown_after = _shown(name, after)
    if shown_after is None:
        return ""
    if before is None:
        return f": {shown_after}"
    shown_before = _shown(name, before)
    return f": {shown_before} → {shown_after}" if shown_before is not None else ""


def sections_of(profile) -> dict[str, tuple[int, dict]]:
    """Each section of a composite policy as (version, spec), keyed by category."""
    return {
        section.profile_section: (section.latest_version.version, section.latest_version.spec)
        for section in profile.sections
        if section.profile_section and section.latest_version is not None
    }


def sections_summary(before: dict[str, tuple[int, dict]], after: dict[str, tuple[int, dict]],
                     label=lambda key: key) -> str:
    """What one save of the composite editor did, section by section."""
    parts = []
    for key in sorted(set(before) | set(after), key=lambda k: label(k)):
        old, new = before.get(key), after.get(key)
        if old == new:
            continue
        if old is None:
            parts.append(f"{label(key)} added (v{new[0]}): {summarize(None, new[1])}")
        elif new is None:
            parts.append(f"{label(key)} removed")
        elif old[0] != new[0]:
            parts.append(f"{label(key)} v{old[0]} → v{new[0]}: {summarize(old[1], new[1])}")
    return " | ".join(parts) if parts else "nothing changed"


def summarize(old: dict | None, new: dict | None, *, limit: int = 12) -> str:
    """The changes as one line, at most `limit` of them named."""
    phrases = field_changes(old, new)
    if not phrases:
        return "no setting changed"
    named = "; ".join(phrases[:limit])
    more = len(phrases) - limit
    return named + (f"; and {more} more" if more > 0 else "")
