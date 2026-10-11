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

"""Read the settings an ATAK build — or one of its plugins — exposes (W90).

Android declares a settings screen as XML under `res/`::

    <PreferenceScreen>
      <PreferenceCategory android:title="@string/network">
        <CheckBoxPreference android:key="atakControlBluetooth"
                            android:title="@string/bt_support"
                            android:defaultValue="false"/>
      </PreferenceCategory>
    </PreferenceScreen>

**Found by content, never by name.** ATAK 5.8.0.4 ships its 65 preference
documents as `res/-v.xml`, `res/0P.xml`, `res/1z.xml` — resource shrinking renamed
every one of them, so a lookup for `res/xml/*pref*.xml` finds nothing at all. The
same conclusion `app_restrictions` reached for `res/Kt.xml` (W49), and the reason
both modules walk `res/**/*.xml` and decide from the root element.

Titles, summaries, and dropdown options arrive as resource references
(`@0x7f0f1488`) and are resolved through `resources.arsc`, reusing the reader
`app_restrictions` and the icon path already share. Measured against the real
ATAK APK: 505 keys, **477 of 477** titles resolved, **46 of 47** option lists
resolved to genuine label→value pairs.

⚠️ **`entries` and `entryValues` are two arrays paired by index** — labels and
values. Order is load-bearing, and a length mismatch means the pairing cannot be
trusted, so the field falls back to free text. A dropdown that sends the wrong
value is far worse than a text box.

⚠️ **The widget class decides the stored type, not the value** (D93). An
`EditTextPreference` holding `"8089"` is a **String** on the device — that is what
`getString` expects and what a real EUD export contains. Reading it as an Integer
because it looks numeric puts an int where ATAK reads a string, which throws
inside ATAK rather than here.

⚠️ **Only what is declared in `res/` is visible.** A setting the app writes from
code, or keeps in its own store, cannot be discovered by any amount of scanning.
Callers must say so rather than present the list as complete.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field

from app.artifacts import arsc
from app.artifacts.app_icon import read_table
from app.artifacts.axml import parse_elements

#: The root element of a settings document.
#:
#: ⚠️ **Matched exactly here, unlike every other element, and that asymmetry is
#: deliberate.** Discovery decides whether a `res/` file is a settings document
#: at all, so a false positive costs a whole fictional screen; classification
#: decides what one row is, so a false negative costs one real setting. Strict
#: where a wrong yes is expensive, lenient where a wrong no is. Both real APKs
#: measured here — ATAK 5.8.0.4 and UAS Tool 13.0.6 — use the plain class at the
#: root while subclassing every widget beneath it.
_ROOT = "PreferenceScreen"

#: Groups fields under a heading. Carries no value of its own.
#:
#: ⚠️ **Matched on the suffix, like every other widget.** UAS Tool ships
#: `com.atakmap.android.gui.PanPreferenceCategory`; compared by exact name that
#: falls through to the unknown-widget branch and becomes a **free-text setting**.
#: It survived only because that one happens to declare no key — a category that
#: does declare one would have appeared as a configurable field named after a
#: heading.
_CATEGORY = "PreferenceCategory"

#: Java classes `PreferenceControl.loadSettings` switches on, verbatim. An entry
#: written with anything else is skipped by ATAK in silence.
CLASS_STRING = "class java.lang.String"
CLASS_BOOLEAN = "class java.lang.Boolean"
CLASS_INTEGER = "class java.lang.Integer"
CLASS_LONG = "class java.lang.Long"
CLASS_FLOAT = "class java.lang.Float"

#: Preference group ATAK-CIV keeps its own settings in, and the fallback for a
#: plugin that does not name one of its own.
DEFAULT_PREFERENCE_GROUP = "com.atakmap.app.civ_preferences"

#: A plugin's own SharedPreferences name, as it appears in the dex string pool:
#: three or more dotted segments ending in `_preferences`.
#:
#: ⚠️ **Case-sensitive, deliberately.** Matched case-insensitively this also hits
#: `android.intent.category.NOTIFICATION_PREFERENCES`, a platform constant every
#: app that posts a notification carries — which is exactly what ATAK's own scan
#: returned as its "plugin-specific preference group" before this was pinned
#: down. A SharedPreferences name is a package name, and those are lower case.
_GROUP_IN_DEX = re.compile(rb"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*){2,}_preferences")

#: Groups that are ATAK's own rather than a plugin's. A plugin declaring one of
#: these is using ATAK's store, which is the default anyway.
_ATAK_GROUPS = frozenset(
    {
        DEFAULT_PREFERENCE_GROUP,
        "com.atakmap.app_preferences",
        "com.atakmap.civ_preferences",
        "com.atakmap.fvey_preferences",
    }
)

#: Widget class *suffixes*, longest first, mapped to (control, java class).
#:
#: Matched on the suffix because ATAK subclasses every stock widget —
#: `com.atakmap.android.gui.PanCheckBoxPreference` is a `CheckBoxPreference` and
#: must be read as one. 155 of ATAK's 505 keys are `Pan`-prefixed checkboxes, so
#: an exact-name table would have found almost nothing.
#:
#: ⚠️ Order matters. `MultiSelectListPreference` ends in `ListPreference`, so the
#: longer suffix has to be tested first or every multi-select is read as a
#: single-choice dropdown.
_WIDGETS: tuple[tuple[str, str, str], ...] = (
    ("MultiSelectListPreference", "multi_select", CLASS_STRING),
    ("ListPreference", "select", CLASS_STRING),
    ("CheckBoxPreference", "bool", CLASS_BOOLEAN),
    ("SwitchPreference", "bool", CLASS_BOOLEAN),
    ("SwitchPreferenceCompat", "bool", CLASS_BOOLEAN),
    ("SeekBarPreference", "int", CLASS_INTEGER),
    ("EditTextPreference", "str", CLASS_STRING),
)

#: Widgets that store nothing — a row that opens a dialog or another screen.
#: ATAK has 114 of them ("Clear History", "Export Chat History"), and offering
#: them as settings would invite an operator to configure a button.
#:
#: ⚠️ **The last segment, exactly — not an `endswith`.** Every preference class
#: ends in "Preference", so a suffix test here swallows the custom widgets that
#: genuinely do store a value: ATAK's `SMSNumberPreference` and
#: `CredentialsPreference` both did. An unrecognised widget is better offered as
#: free text (one row too many, visible) than dropped (a setting that silently
#: cannot be configured).
_ACTION_ONLY = frozenset({"Preference", "PanPreference"})


@dataclass(frozen=True)
class PrefOption:
    """One entry of a dropdown: what to show, and what to store."""

    label: str
    value: str


@dataclass(frozen=True)
class PrefField:
    """One editable setting, as the app itself declares it."""

    key: str
    #: The widget's class name, kept verbatim for diagnosis.
    widget: str
    #: bool | int | str | select | multi_select
    control: str
    #: The `class` attribute a `.pref` entry for this key must carry.
    java_class: str
    title: str | None = None
    summary: str | None = None
    default: str | None = None
    options: tuple[PrefOption, ...] = ()

    @property
    def label(self) -> str:
        """What to show the operator — the app's own title, else the raw key."""
        return self.title or self.key

    @property
    def has_options(self) -> bool:
        return bool(self.options)


@dataclass(frozen=True)
class PrefSection:
    """A `PreferenceCategory` and the fields under it."""

    title: str
    fields: tuple[PrefField, ...] = ()


@dataclass(frozen=True)
class PrefScreen:
    """One settings document."""

    #: The `res/` path it was found at. Meaningless to an operator after resource
    #: shrinking, but the only handle there is when two screens collide.
    source: str
    title: str | None
    sections: tuple[PrefSection, ...] = ()

    @property
    def fields(self) -> tuple[PrefField, ...]:
        return tuple(f for section in self.sections for f in section.fields)


@dataclass(frozen=True)
class PrefSchema:
    """Every setting one APK declares, and where its values are stored."""

    package_name: str
    #: The SharedPreferences group a generated `.pref` must write into.
    preference_group: str = DEFAULT_PREFERENCE_GROUP
    screens: tuple[PrefScreen, ...] = ()

    @property
    def declares_any(self) -> bool:
        return any(screen.fields for screen in self.screens)

    @property
    def fields(self) -> tuple[PrefField, ...]:
        return tuple(f for screen in self.screens for f in screen.fields)

    @property
    def field_count(self) -> int:
        return len(self.fields)

    def types(self) -> dict[str, str]:
        """`{key: java class}` — what a generator needs and nothing more.

        Later screens lose to earlier ones on a duplicate key. Duplicates are real
        (ATAK declares a handful across screens) and always agree on type, so the
        choice is arbitrary rather than lossy; picking deterministically is what
        matters, so the same APK always yields the same document.
        """
        types: dict[str, str] = {}
        for field_ in self.fields:
            types.setdefault(field_.key, field_.java_class)
        return types


# --------------------------------------------------------------------------- #
# Attribute reading
# --------------------------------------------------------------------------- #


def _unresolved(value: object) -> bool:
    """True for a value the AXML reader could only report symbolically."""
    return isinstance(value, str) and value.startswith("@0x")


def _attr(element, name: str) -> object | None:
    """Read an attribute, tolerating the namespaced and bare spellings.

    Which one appears varies with how the app was built, so neither can be
    assumed — the same tolerance `app_restrictions._attr` needs.
    """
    for candidate in (f"android:{name}", name):
        if candidate in element.attributes:
            return element.attributes[candidate]
    return None


def _text(element, name: str, table: "arsc.ResourceTable | None") -> str | None:
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
        return table.string(int(str(value)[1:], 16)) or None
    if isinstance(value, bool):
        # A compiled boolean default arrives as a real bool. Speak the control's
        # vocabulary rather than Python's `True`.
        return "true" if value else "false"
    text = str(value)
    return text or None


def _options(element, table: "arsc.ResourceTable | None") -> tuple[PrefOption, ...]:
    """The declared dropdown options, as (label, value) pairs.

    `android:entries` holds what to show and `android:entryValues` what to store,
    two arrays paired **by index**. A length mismatch means the pairing cannot be
    trusted, and a dropdown that stores the wrong value is worse than free text —
    so that case yields nothing and the caller falls back.
    """
    if table is None:
        return ()

    def read(name: str) -> list[str | None] | None:
        """The array behind an attribute. None when the app declares none.

        ⚠️ None and `[]` are different answers and collapsing them is a
        wrong-value bug: `[]` means an array *was* named but could not be read,
        and falling back to "labels are also values" there stores the prose
        ("Decimal Degrees" is fine, but "Let's Encrypt and DigiCert Only" is not
        `BAKED_IN`) where the app expects its own token.
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
        return ()

    # Drop *pairs* where either side is unresolved, never a single side — that is
    # what keeps the remaining labels against their own values.
    return tuple(
        PrefOption(label=label, value=value)
        for label, value in zip(labels, values)
        if label is not None and value is not None
    )


def is_category(widget: str) -> bool:
    """True for a heading — `PreferenceCategory` or any app's subclass of it."""
    return widget == _CATEGORY or widget.endswith(_CATEGORY)


def _classify(widget: str) -> tuple[str, str] | None:
    """(control, java class) for a widget class name, or None if it stores nothing."""
    for suffix, control, java_class in _WIDGETS:
        if widget == suffix or widget.endswith(suffix):
            return control, java_class
    if is_category(widget) or widget == _ROOT or widget.endswith(_ROOT):
        return None
    if widget.rsplit(".", 1)[-1] in _ACTION_ONLY:
        return None
    # An unrecognised widget still declares a key, and every preference value can
    # be expressed as a string. Offering it as free text beats hiding a setting
    # the app really does read.
    return "str", CLASS_STRING


# --------------------------------------------------------------------------- #
# Document parsing
# --------------------------------------------------------------------------- #


@dataclass
class _Section:
    """A category being filled, and how this document expresses membership.

    ⚠️ **Both idioms are real, and they disagree about the same shape.** Android
    documents a category as the *parent* of its fields, and ATAK's own screens are
    written that way. UAS Tool's are not: its categories are **empty elements used
    as separators**, with the fields that follow them as *siblings* at the same
    depth. Reading only the nested form put all 160 of its settings under one
    heading and threw every real heading away; reading only the flat form files a
    trailing top-level field under a category it has already left.

    Decided per category, by what the document has shown so far: once a field has
    appeared *inside* it, this is a nested document and a same-depth field belongs
    to nobody. Until then a same-depth field is the flat idiom — which is the
    better reading, because an empty category means nothing on its own.
    """

    title: str
    depth: int
    fields: list[PrefField] = field(default_factory=list)
    _nested: bool = False

    def claims(self, field_depth: int) -> bool:
        if field_depth > self.depth:
            self._nested = True
            return True
        return field_depth == self.depth and not self._nested


def parse_preference_xml(
    data: bytes, source: str, table: "arsc.ResourceTable | None" = None
) -> PrefScreen | None:
    """Read one binary XML file, returning its screen if it is a settings document."""
    try:
        elements = parse_elements(data)
    except Exception:  # noqa: BLE001 — a res/ entry may be any bytes at all
        # Broad on purpose: this walks every XML resource in a stranger's APK, and
        # a malformed one must be skipped rather than fail the whole scan.
        return None

    if not elements or elements[0].name != _ROOT:
        return None

    screen_title = _text(elements[0], "title", table)

    # Fields declared before any category, and fields under each one. ATAK has
    # both — 98 categories, and a handful of screens that are a flat list.
    loose: list[PrefField] = []
    sections: list[_Section] = []

    for element in elements[1:]:
        if is_category(element.name):
            title = _text(element, "title", table) or _text(element, "key", table) or "General"
            sections.append(_Section(title=title, depth=element.depth))
            continue

        key = _text(element, "key", table)
        if not key:
            # A row with no key stores nothing — a header, a spacer, or a link.
            continue
        classified = _classify(element.name)
        if classified is None:
            continue
        control, java_class = classified

        options = _options(element, table) if control in ("select", "multi_select") else ()
        if control in ("select", "multi_select") and not options:
            # The app declares a fixed list this reader could not resolve. Free
            # text is the honest fallback; an empty dropdown offers a choice of
            # nothing and reads as a bug in the console.
            control = "str"

        default = _text(element, "defaultValue", table)
        if control == "bool" and default in ("0", "1"):
            # ⚠️ Binary XML stores a boolean as 0/1, so every one of ATAK's 160
            # checkboxes arrives with default "1" or "0" — shown beside a
            # True/False control that reads as a different vocabulary, and it is
            # the app's own value being reported. Speak the control's language.
            default = "true" if default == "1" else "false"

        field_ = PrefField(
            key=key,
            widget=element.name,
            control=control,
            java_class=java_class,
            title=_text(element, "title", table),
            summary=_text(element, "summary", table),
            default=default,
            options=options,
        )

        if sections and sections[-1].claims(element.depth):
            sections[-1].fields.append(field_)
        else:
            loose.append(field_)

    if not loose and not any(section.fields for section in sections):
        return None

    built: list[PrefSection] = []
    if loose:
        built.append(PrefSection(title=screen_title or "General", fields=tuple(loose)))
    built.extend(
        PrefSection(title=section.title, fields=tuple(section.fields))
        for section in sections
        if section.fields
    )
    return PrefScreen(source=source, title=screen_title, sections=tuple(built))


# --------------------------------------------------------------------------- #
# Where a plugin's values are stored
# --------------------------------------------------------------------------- #


def detect_preference_group(archive: zipfile.ZipFile) -> str:
    """The SharedPreferences group this APK's settings belong to.

    A plugin runs inside ATAK's process, so its settings usually land in ATAK's
    own store — which is why the default is not a guess but the common case. A
    plugin that keeps its own store names it in code, and the name survives into
    the dex string pool.

    Exactly one plugin-specific candidate is accepted. Two or more is genuinely
    ambiguous — a library the plugin bundles names its own — and picking one at
    random would write every value into a store nothing reads, silently.
    """
    candidates: set[str] = set()
    for name in archive.namelist():
        if not name.endswith(".dex"):
            continue
        try:
            data = archive.read(name)
        except (KeyError, OSError, zipfile.BadZipFile):
            continue
        for match in _GROUP_IN_DEX.finditer(data):
            candidates.add(match.group(0).decode("utf-8", errors="ignore"))

    specific = sorted(c for c in candidates if c not in _ATAK_GROUPS)
    if len(specific) == 1:
        return specific[0]
    return DEFAULT_PREFERENCE_GROUP


# --------------------------------------------------------------------------- #
# Entry points
# --------------------------------------------------------------------------- #


def discover(
    data: bytes, package_name: str, table: "arsc.ResourceTable | None" = None
) -> PrefSchema:
    """Find the settings an APK declares, if any."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return PrefSchema(package_name=package_name)

    with archive:
        return discover_in(archive, package_name, table)


def discover_in(
    archive: zipfile.ZipFile,
    package_name: str,
    table: "arsc.ResourceTable | None" = None,
) -> PrefSchema:
    """As `discover`, against an archive the caller already has open.

    `table` lets a caller that already parsed the resource table hand it over —
    the same courtesy `app_restrictions.discover_in` offers, and for the same
    reason: re-parsing a large table costs seconds of GIL-held work for a
    byte-identical result.

    ⚠️ **Every matching screen is kept, not the first.** ATAK declares 65 of them
    and each is a different settings page; stopping at the first — which is what
    the managed-configuration scan does, because an app has only one restrictions
    document — would surface a handful of keys out of 505 and look like the app
    barely has settings.
    """
    if table is None:
        table = read_table(archive)

    screens: list[PrefScreen] = []
    for name in sorted(archive.namelist()):
        # Only res/ XML: the manifest is binary XML too, and every other entry is
        # either code or an asset.
        if not (name.startswith("res/") and name.endswith(".xml")):
            continue
        try:
            screen = parse_preference_xml(archive.read(name), name, table)
        except (KeyError, OSError):
            continue
        if screen is not None:
            screens.append(screen)

    return PrefSchema(
        package_name=package_name,
        preference_group=detect_preference_group(archive),
        screens=tuple(screens),
    )
