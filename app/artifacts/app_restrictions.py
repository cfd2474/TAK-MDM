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

That is a resource reference, and the file it names is found **by content**: every
`res/**/*.xml` is parsed and the one whose root element is `<restrictions>` wins.
Not a workaround so much as the more reliable route — resource shrinking renames
these files, and ATAK 5.8.0.4 ships its schema as **`res/Kt.xml`**, which no
name-based lookup would ever have found.

**Titles, descriptions, and choice options are resolved through `resources.arsc`**
(W54). They arrive as references — `@0x7f0f1488` — and W49 shipped without a
reader for them, so the console showed raw keys like
`AdsSettingForIntrusiveAdsSites` and offered free text where the app had declared
exactly which values it accepts. Every title reference in all eight pinned
fixtures resolves: 231 of 231 for Chrome, 78 of 78 for Gboard.

⚠️ **A choice's `entries` and `entryValues` are two arrays read positionally
against each other** — labels and values, paired by index. Order is therefore
load-bearing all the way down into the resource reader, which is why bag members
are kept in declaration order and never sorted.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field

from app.artifacts import arsc
from app.artifacts.app_icon import read_table
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
#: `choice` and `multi_select` carry the app's own option list when it could be
#: read (W54) — Chrome's `AdsSettingForIntrusiveAdsSites` resolves to
#: "Allow ads on all sites" / "Do not allow ads on sites with intrusive ads",
#: sending 0 or 1. When the arrays cannot be resolved the control keeps its name
#: and falls back to free text, so the editor can still *say* the app defines the
#: valid values rather than implying anything is acceptable.
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
class RestrictionOption:
    """One entry of a choice's option list: what to show, and what to send."""

    label: str
    value: str


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
    #: The values the app declares for a choice / multi-select. Empty when the app
    #: declares none, or when they could not be resolved — the editor then falls
    #: back to free text rather than offering an empty list.
    options: tuple[RestrictionOption, ...] = ()

    @property
    def label(self) -> str:
        """What to show the operator — the app's title if it survived, else the key."""
        return self.title or self.key

    @property
    def has_options(self) -> bool:
        return bool(self.options)


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


def _text(element, name: str, table: "arsc.ResourceTable | None" = None) -> str | None:
    """An attribute as text, resolving a resource reference when one is given.

    Returns None rather than the reference when it cannot be resolved: showing
    `@0x7f0f1488` to an operator is worse than showing the key, which is at least
    the string they have to reason about.
    """
    value = _attr(element, name)
    if value is None:
        return None
    if _unresolved(value):
        if table is None:
            return None
        resolved = table.string(int(str(value)[1:], 16))
        return resolved or None
    text = str(value)
    return text or None


def _options(element, table: "arsc.ResourceTable | None") -> tuple[RestrictionOption, ...]:
    """The declared option list for a choice, as (label, value) pairs.

    `android:entries` holds what to show and `android:entryValues` what to send.
    They are separate arrays paired **by index**, so a mismatch in length means
    the pairing cannot be trusted — and a dropdown that sends the wrong value is
    far worse than a text box, so that case falls back to no options at all.
    """
    if table is None:
        return ()

    def read(name: str) -> list[str | None] | None:
        """The array behind an attribute. None when the app declares none.

        ⚠️ None and `[]` mean genuinely different things, and collapsing them is
        a silent wrong-value bug. `[]` here means the app *did* name an array that
        could not be read — falling back to "the labels are also the values" in
        that case sends the app the human-readable prose ("Allow ads on all
        sites") in place of the value it declared ("1"). The app then ignores it
        and uses its default, while the console shows the policy applied.
        """
        raw = _attr(element, name)
        if not _unresolved(raw):
            return None
        return table.array(int(str(raw)[1:], 16))

    labels = read("entries")
    values = read("entryValues")

    if values is None and labels is not None:
        # Genuinely labels-only: the app declared no separate value list, so each
        # label is its own value.
        values = labels
    if values is None or not values:
        return ()
    if labels is None or not labels:
        labels = values
    if len(labels) != len(values):
        # The pairing cannot be trusted, and a dropdown that sends the wrong value
        # is far worse than the text box the caller falls back to.
        return ()

    # Drop *pairs* where either side is unresolved, never a single side — that is
    # what keeps the remaining labels against their own values.
    return tuple(
        RestrictionOption(label=label, value=value)
        for label, value in zip(labels, values)
        if label is not None and value is not None
    )


def parse_restrictions_xml(
    data: bytes, table: "arsc.ResourceTable | None" = None
) -> list[RestrictionKey] | None:
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

        options: tuple[RestrictionOption, ...] = ()
        if restriction_type in (TYPE_CHOICE, TYPE_CHOICE_LEVEL, TYPE_MULTI_SELECT):
            options = _options(element, table)

        keys.append(
            RestrictionKey(
                key=key,
                restriction_type=restriction_type,
                title=_text(element, "title", table),
                description=_text(element, "description", table),
                default=default,
                control=_CONTROL.get(restriction_type, "str"),
                unsupported_reason=unsupported,
                options=options,
            )
        )
    return keys


def discover(
    data: bytes,
    package_name: str,
    table: "arsc.ResourceTable | None" = None,
) -> AppRestrictions:
    """Find the managed configuration an APK declares, if any.

    `table` lets a caller that has already parsed the resource table hand it over.
    Ingest has one — `inspect_apk` builds it for the icon and the label — and
    re-parsing Outlook's 39.6 MB table costs a further 1.2 s of GIL-held work per
    upload for a byte-identical result.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return AppRestrictions(package_name=package_name)

    with archive:
        return discover_in(archive, package_name, table)


def discover_in(
    archive: zipfile.ZipFile,
    package_name: str,
    table: "arsc.ResourceTable | None" = None,
) -> AppRestrictions:
    """As `discover`, against an archive the caller already has open.

    Exists so ingest can answer this question during the pass that is already
    holding the resource table, instead of re-opening the zip and re-parsing a
    table it just built and threw away.
    """
    # One parse, serving every title, description, and option list in the
    # document. None when unreadable — the keys are still worth having.
    if table is None:
        table = read_table(archive)

    for name in archive.namelist():
        # Only res/ XML: the manifest is binary XML too, and every other
        # entry is either code or an asset.
        if not (name.startswith("res/") and name.endswith(".xml")):
            continue
        try:
            found = parse_restrictions_xml(archive.read(name), table)
        except (KeyError, OSError):
            continue
        if found:
            return AppRestrictions(package_name=package_name, keys=found)

    return AppRestrictions(package_name=package_name)
