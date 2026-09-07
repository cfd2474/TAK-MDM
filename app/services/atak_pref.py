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

"""Write the `.pref` document ATAK imports (W90).

The format is not ours; it is what `PreferenceControl.loadSettings` parses and
what a real EUD export contains, down to the CRLF line endings::

    <?xml version='1.0' standalone='yes'?>
    <preferences>
    <preference version="1" name="com.atakmap.app.civ_preferences">
    <entry key="filesharingEnabled" class="class java.lang.Boolean">true</entry>
    </preference>
    </preferences>

Delivered through ATAK's own managed-configuration key
`enterpriseConfigurationPreferences`, as **plain text** — the data-package slots
beside it are base64, this one is not.

⚠️ **One bad value abandons every entry after it.** `loadSettings` switches on
the `class` attribute and calls `Integer.parseInt` / `Float.parseFloat`
unguarded: there is no per-entry try, so a `NumberFormatException` unwinds the
whole document. The entries before it have already been `apply()`d, and the MD5
that marks the document as ingested is written *after* the parse — so a
half-applied configuration is retried on every restrictions-changed broadcast,
forever, with nothing logged on this side. Every value is therefore validated
against its declared class **here**, where the operator can be told, rather than
discovered as a partial config on a tablet.

⚠️ **Connection groups are omitted, not emitted empty.** A real export writes
empty `cot_inputs` / `cot_outputs` / `cot_streams` blocks; this generator writes
none at all. They are out of scope (W90), and a `<preference>` element ATAK does
not see is one it cannot act on — which is the safe direction when the thing it
might act on is the operator's TAK server connection.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from app.artifacts.pref_screens import (
    CLASS_BOOLEAN,
    CLASS_FLOAT,
    CLASS_INTEGER,
    CLASS_LONG,
    CLASS_STRING,
)

#: `setApplicationRestrictions` carries the document across a Binder transaction,
#: which is capped at 1 MB shared by everything in flight. ATAK's own key
#: description names 64 KB as the working limit, and that is the number to refuse
#: at: past it the failure is a `TransactionTooLargeException` on the device,
#: which surfaces as a configuration that simply never arrives.
MAX_PREF_BYTES = 64 * 1024

_HEADER = "<?xml version='1.0' standalone='yes'?>\r\n<preferences>\r\n"
_FOOTER = "</preferences>\r\n"

#: The document's own version attribute, as ATAK writes it. Not ours to choose.
_PREFERENCE_VERSION = "1"

#: XML 1.0 forbids most control characters outright — a document containing one
#: is not merely ugly, it fails to parse, which by the note above discards every
#: entry after it.
_ALLOWED_CONTROL = {"\t", "\n", "\r"}


class PrefError(ValueError):
    """A `.pref` document that could not be built, in words an operator can act on."""


@dataclass(frozen=True)
class PrefEntry:
    """One key, its value as the operator typed it, and the class ATAK stores it as."""

    key: str
    value: str
    java_class: str = CLASS_STRING


def encode_text(value: str) -> str:
    """Escape the way `PreferenceControl.decode` un-escapes.

    ATAK does not read XML entities back out of a value — it reverses exactly
    these five `\\uXXXX` sequences. Emitting `&amp;` instead would leave the app
    holding the literal five characters.
    """
    return (
        value.replace('"', "\\u0022")
        .replace("'", "\\u0027")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def _escape_attr(value: str) -> str:
    """Escape a value going into an XML attribute.

    Attributes are read by a real XML parser on ATAK's side, so these are genuine
    entities — unlike element text, which ATAK decodes itself.
    """
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _reject_control_chars(where: str, value: str) -> None:
    for char in value:
        if char < " " and char not in _ALLOWED_CONTROL:
            raise PrefError(
                f"{where} contains a control character (0x{ord(char):02x}) that XML "
                f"cannot carry, so ATAK would fail to parse the whole document"
            )


def normalise(entry: PrefEntry) -> str:
    """The value as ATAK will store it, refusing anything its parser would throw on.

    Booleans are normalised rather than rejected: `Boolean.parseBoolean` treats
    everything that is not "true" as false, so "yes" would arrive as **false**
    with no error anywhere. Making that an error instead is the only way the
    operator finds out.
    """
    raw = entry.value.strip()
    if entry.java_class == CLASS_BOOLEAN:
        lowered = raw.lower()
        if lowered in ("true", "1", "yes", "on"):
            return "true"
        if lowered in ("false", "0", "no", "off"):
            return "false"
        raise PrefError(
            f"{entry.key} is a true/false setting but the policy has {entry.value!r}. "
            f"ATAK reads anything that is not \"true\" as false, so this would apply "
            f"silently as false."
        )
    if entry.java_class in (CLASS_INTEGER, CLASS_LONG):
        try:
            return str(int(raw, 10))
        except ValueError:
            raise PrefError(
                f"{entry.key} is a whole-number setting but the policy has "
                f"{entry.value!r}. ATAK parses it unguarded, and the failure "
                f"discards every setting after it in the document."
            ) from None
    if entry.java_class == CLASS_FLOAT:
        try:
            float(raw)
        except ValueError:
            raise PrefError(
                f"{entry.key} is a decimal setting but the policy has {entry.value!r}. "
                f"ATAK parses it unguarded, and the failure discards every setting "
                f"after it in the document."
            ) from None
        return raw
    return entry.value


def _render_entry(entry: PrefEntry) -> str:
    _reject_control_chars(f"the key {entry.key!r}", entry.key)
    _reject_control_chars(f"the value of {entry.key!r}", entry.value)
    value = normalise(entry)
    return (
        f'<entry key="{_escape_attr(encode_text(entry.key))}" '
        f'class="{entry.java_class}">{encode_text(value)}</entry>\r\n'
    )


def build(groups: Sequence[tuple[str, Sequence[PrefEntry]]]) -> str:
    """Render one `.pref` document from preference groups, in the order given.

    Order is the caller's and is preserved: the document is part of a signed
    bundle and is de-duplicated on the device by MD5, so a stable byte-for-byte
    result is what makes a re-push a genuine no-op rather than a reload.

    An empty group is dropped rather than written — see the module note on why an
    empty `<preference>` block is not a harmless one.
    """
    body = "".join(
        f'<preference version="{_PREFERENCE_VERSION}" name="{_escape_attr(name)}">\r\n'
        + "".join(_render_entry(entry) for entry in entries)
        + "</preference>\r\n"
        for name, entries in groups
        if entries
    )
    if not body:
        return ""

    document = _HEADER + body + _FOOTER
    encoded = len(document.encode("utf-8"))
    if encoded > MAX_PREF_BYTES:
        raise PrefError(
            f"the ATAK configuration is {encoded:,} bytes and the limit is "
            f"{MAX_PREF_BYTES:,} — Android cannot carry a larger one to the app. "
            f"Split it across policies, or manage fewer settings."
        )
    return document


def entries_from(
    values: Mapping[str, str], types: Mapping[str, str]
) -> list[PrefEntry]:
    """Pair an operator's values with the classes the APK declared for them.

    Keys are emitted in sorted order so the same policy always produces the same
    bytes — a dict's insertion order survives a JSON round trip but not an edit,
    and a document that differs only in ordering would re-apply on the device for
    no reason.

    A key with no declared class is carried as a **String**, which is what an
    unknown ATAK preference almost always is, and is the only class whose value
    cannot fail to parse.
    """
    return [
        PrefEntry(key=key, value=values[key], java_class=types.get(key, CLASS_STRING))
        for key in sorted(values)
    ]


def group_names(groups: Iterable[tuple[str, Sequence[PrefEntry]]]) -> list[str]:
    """The groups that would actually be written, for reporting to an operator."""
    return [name for name, entries in groups if entries]
