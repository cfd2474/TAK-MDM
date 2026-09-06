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

"""Discover the managed configuration an APK declares (W49).

An app advertises its configurable keys with::

    <meta-data android:name="android.content.APP_RESTRICTIONS"
               android:resource="@xml/app_restrictions"/>

⚠️ **That is a resource reference, and we cannot resolve one.** `axml` reads
binary XML but not `resources.arsc`, so the reference arrives as `@0x7f120001`
and the file it names is unknown. Writing an `.arsc` parser robust enough for
every APK an operator might upload is a large piece of work for one lookup.

**So the file is found by content instead:** every `res/**/*.xml` is parsed and
the one whose root element is `<restrictions>` wins. This is not a workaround so
much as the more reliable route — resource shrinking renames these files, and
ATAK 5.8.0.4 ships its schema as **`res/Kt.xml`**, which no name-based lookup
would ever have found.

⚠️ **Titles and descriptions stay unresolved** for the same reason, arriving as
`@0x7f0f1488`. The key is shown instead: it is the string the operator actually
has to reason about, and a fabricated label would be worse than an honest one.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field

from app.artifacts.axml import parse_elements

#: `RestrictionEntry` type constants, from the Android SDK source.
TYPE_NULL = 0
TYPE_BOOLEAN = 1
TYPE_CHOICE = 2
TYPE_CHOICE_LEVEL = 3
TYPE_MULTI_SELECT = 4
TYPE_INTEGER = 5
TYPE_STRING = 6
TYPE_BUNDLE = 7
TYPE_BUNDLE_ARRAY = 8

#: How each maps onto a console control. Anything absent falls back to text,
#: which every restriction value can be expressed as.
#:
#: ⚠️ `choice` and `multi_select` are **not** rendered as dropdowns, because the
#: options cannot be read. An app declares them as `android:entries` /
#: `android:entryValues` pointing at resource arrays, and those are references —
#: Chrome's `AdsSettingForIntrusiveAdsSites` carries `entries=@0x7f040008`. They
#: get their own control name anyway so the editor can *say* the app defines the
#: valid values, rather than showing a text box that implies anything is
#: acceptable. `defaultValue` is usually a literal and is shown as the clue it is.
_CONTROL = {
    TYPE_BOOLEAN: "bool",
    TYPE_INTEGER: "int",
    TYPE_STRING: "str",
    TYPE_CHOICE: "choice",
    TYPE_MULTI_SELECT: "multi_select",
}

#: Nested structures. Android supports them; a flat key/value form does not, and
#: pretending otherwise would produce a Bundle the app cannot read.
_UNSUPPORTED = {TYPE_BUNDLE, TYPE_BUNDLE_ARRAY}


def _unresolved(value: object) -> bool:
    """True for a value the AXML reader could only report symbolically."""
    return isinstance(value, str) and value.startswith("@0x")


@dataclass(frozen=True)
class RestrictionKey:
    key: str
    restriction_type: int
    #: The app's own title, or None when it is a resource we cannot resolve.
    title: str | None = None
    description: str | None = None
    default: str | None = None
    control: str = "str"
    #: Set when Android supports the type but this console cannot edit it.
    unsupported_reason: str | None = None

    @property
    def label(self) -> str:
        """What to show the operator — the app's title if it survived, else the key."""
        return self.title or self.key


@dataclass(frozen=True)
class AppRestrictions:
    package_name: str
    keys: list[RestrictionKey] = field(default_factory=list)

    @property
    def declares_any(self) -> bool:
        return bool(self.keys)


def _attr(element, name: str) -> object | None:
    """Read an attribute, tolerating the namespaced and bare spellings.

    The AXML reader surfaces both `android:key` and `key`; which one is present
    varies with how the app was built, so neither can be assumed.
    """
    for candidate in (f"android:{name}", name):
        if candidate in element.attributes:
            return element.attributes[candidate]
    return None


def _text(element, name: str) -> str | None:
    value = _attr(element, name)
    if value is None or _unresolved(value):
        return None
    text = str(value)
    return text or None


def parse_restrictions_xml(data: bytes) -> list[RestrictionKey] | None:
    """Read one binary XML file, returning its keys if it is a restrictions doc."""
    try:
        elements = parse_elements(data)
    except Exception:  # noqa: BLE001 — a res/ entry may be any bytes at all
        # Broad on purpose: this walks every XML resource in a stranger's APK,
        # and a malformed one must be skipped rather than fail the whole scan.
        return None

    if not elements or elements[0].name != "restrictions":
        return None

    keys: list[RestrictionKey] = []
    for element in elements[1:]:
        if element.name != "restriction":
            continue
        # ⚠️ Top level only. A `bundle` restriction nests its own `<restriction>`
        # children, and read flat they look like configurable keys in their own
        # right — Gboard declares 82 real keys and 43 nested inside a bundle.
        # Setting a nested key at the top of the Bundle writes it where the app
        # never reads: no error, no effect, and nothing to see in the console.
        if element.depth != 1:
            continue
        key = _text(element, "key")
        if not key:
            # A restriction with no readable key cannot be configured or sent.
            continue

        raw_type = _attr(element, "restrictionType")
        restriction_type = raw_type if isinstance(raw_type, int) else TYPE_STRING

        unsupported = None
        if restriction_type in _UNSUPPORTED:
            unsupported = (
                "this key is a bundle, which Android supports but this editor "
                "cannot express as a flat value"
            )

        default = _text(element, "defaultValue")
        if restriction_type == TYPE_BOOLEAN and default in ("0", "1"):
            # Binary XML stores a boolean as 0/1, so Outlook's
            # `BlockExternalImagesEnabled` arrives with default "0". Shown beside a
            # True/False control that reads as a different vocabulary, and it is the
            # app's own value being reported — so speak the control's language.
            default = "true" if default == "1" else "false"

        keys.append(
            RestrictionKey(
                key=key,
                restriction_type=restriction_type,
                title=_text(element, "title"),
                description=_text(element, "description"),
                default=default,
                control=_CONTROL.get(restriction_type, "str"),
                unsupported_reason=unsupported,
            )
        )
    return keys


def discover(data: bytes, package_name: str) -> AppRestrictions:
    """Find the managed configuration an APK declares, if any."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return AppRestrictions(package_name=package_name)

    with archive:
        for name in archive.namelist():
            # Only res/ XML: the manifest is binary XML too, and every other
            # entry is either code or an asset.
            if not (name.startswith("res/") and name.endswith(".xml")):
                continue
            try:
                found = parse_restrictions_xml(archive.read(name))
            except (KeyError, OSError):
                continue
            if found:
                return AppRestrictions(package_name=package_name, keys=found)

    return AppRestrictions(package_name=package_name)
