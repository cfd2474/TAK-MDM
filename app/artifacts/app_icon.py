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

"""Pull an app's launcher icon out of its APK (W53).

`android:icon` on `<application>` is a resource reference. Resolving it lands on
one of two shapes:

* a **legacy raster** — the finished icon, use it as-is; or
* an **adaptive icon**, which is XML naming a background and a foreground layer,
  each of which may itself be a raster or a vector drawable.

Only the raster cases are extractable. Rasterising a `VectorDrawable` means
implementing Android's drawable pipeline — path data, gradients, clip paths,
insets — so an app whose foreground is a vector yields **nothing**, and the caller
shows its placeholder. Returning a wrong-but-present image would be worse than an
honest gap.

⚠️ **Never identify an image by its file extension here.** Resource shrinking
renames `res/drawable-xxxhdpi/ic_launcher.webp` to `res/ima` — no extension at
all. An earlier attempt filtered on `.png`/`.webp`, found nothing, and concluded
the icons were vectors; they were WEBP the whole time. Magic bytes only.
"""

from __future__ import annotations

import struct
import zipfile
from dataclasses import dataclass

from app.artifacts import arsc
from app.artifacts.axml import AxmlError, AxmlElement, parse_elements

_MANIFEST = "AndroidManifest.xml"
_RESOURCE_TABLE = "resources.arsc"

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_AXML_MAGIC = b"\x03\x00\x08\x00"

#: Everything a malformed resource table can throw. An unreadable table is a
#: normal outcome for this module — the caller falls back to a placeholder — so
#: none of these may reach the request handler.
_UNREADABLE = (
    KeyError,
    ValueError,
    IndexError,
    struct.error,
    MemoryError,
    zipfile.BadZipFile,
    arsc.ArscError,
)

#: An adaptive icon is drawn on a 108dp canvas of which only the centre 72dp is
#: guaranteed visible — the rest is bleed for the launcher's mask and parallax.
#: Displaying the whole canvas makes every icon look shrunken and off-centre.
ADAPTIVE_VISIBLE_FRACTION = 72 / 108

#: Depth guard for following references. Outlook nests `inset → layer-list → item`
#: before reaching a leaf, so this is not generous.
_MAX_DEPTH = 6

#: Total resource lookups one icon may cost.
#:
#: ⚠️ A depth bound alone does **not** bound work. `table.values()` returns one
#: entry per declared configuration, so a resource declaring N references costs
#: N branches per level and N**depth overall — a 511-byte APK can ask for more
#: work than there is time to do it in. The visited set below kills cycles; this
#: kills fan-out, which a visited set does not.
_MAX_LOOKUPS = 4096

#: Refuse an implausibly large "icon". The real ones here are 1.5–15 KB; anything
#: past this is a resource that is not a launcher icon, and it is about to be
#: stored on a row and sent to a browser on every page load.
MAX_ICON_BYTES = 1_048_576

#: Layers in the order worth trying. The foreground carries the artwork; the
#: background is usually a flat colour and on its own says nothing about the app.
#: `monochrome` is a themed-icon silhouette — never a substitute for the real one.
_LAYER_ORDER = ("foreground", "background")


@dataclass(frozen=True)
class AppIcon:
    """A launcher icon exactly as it is stored in the APK."""

    data: bytes
    media_type: str
    #: True when the bytes came from an adaptive icon's layer, and therefore need
    #: the ×1.5 centre crop before they look like the icon the device draws.
    adaptive: bool

    @property
    def visible_fraction(self) -> float:
        return ADAPTIVE_VISIBLE_FRACTION if self.adaptive else 1.0


def _media_type(blob: bytes) -> str | None:
    """Identify an image by magic bytes. Extensions are not trustworthy here."""
    if blob.startswith(_PNG_MAGIC):
        return "image/png"
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return "image/webp"
    if blob[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    return None


def _is_binary_xml(blob: bytes) -> bool:
    return blob[:4] == _AXML_MAGIC


def _references(element: AxmlElement) -> list[int]:
    """Resource ids referenced by an element's attributes."""
    found = []
    for value in element.attributes.values():
        if isinstance(value, str) and value.startswith("@0x"):
            try:
                found.append(int(value[1:], 16))
            except ValueError:
                continue
    return found


def _layer_references(elements: list[AxmlElement]) -> list[int]:
    """Resource ids named by a drawable XML, most promising first.

    An `<adaptive-icon>` is read layer by layer so the foreground is tried before
    the background. Anything else — `<layer-list>`, `<inset>`, `<selector>` — is
    read in document order, which is the order the layers stack.
    """
    if not elements:
        return []

    if elements[0].name == "adaptive-icon":
        ordered: list[int] = []
        for layer_name in _LAYER_ORDER:
            layer = next((e for e in elements if e.name == layer_name), None)
            if layer is None:
                continue
            # The drawable may be an attribute of the layer, or the layer may wrap
            # child elements that carry it — Outlook's foreground does the latter.
            ordered.extend(_references(layer))
            ordered.extend(
                ref
                for child in elements
                if child.depth > layer.depth and _within(elements, child, layer)
                for ref in _references(child)
            )
        return ordered

    return [ref for element in elements for ref in _references(element)]


def _within(elements: list[AxmlElement], child: AxmlElement, layer: AxmlElement) -> bool:
    """True when `child` sits inside `layer` in document order.

    Depth alone is not enough: a `<background>` and a `<foreground>` are siblings,
    so their children are at the same depth and would otherwise be indistinguishable.
    """
    start = elements.index(layer)
    for element in elements[start + 1 :]:
        if element is child:
            return True
        if element.depth <= layer.depth:
            return False  # left the layer
    return False


class _Budget:
    """Shared work counter for one icon resolution.

    A depth limit bounds how *deep* the search goes, not how *wide*. Both are
    needed: without this, a resource declaring many references costs
    branches**depth lookups, and the table it comes from is attacker-supplied.
    """

    __slots__ = ("remaining",)

    def __init__(self, limit: int) -> None:
        self.remaining = limit

    def spend(self) -> bool:
        self.remaining -= 1
        return self.remaining > 0


def _resolve(
    archive: zipfile.ZipFile,
    table: arsc.ResourceTable,
    resource_id: int,
    depth: int = 0,
    adaptive: bool = False,
    visited: frozenset[int] | None = None,
    budget: _Budget | None = None,
) -> AppIcon | None:
    """Follow a resource id down to a raster, or return None."""
    if depth > _MAX_DEPTH:
        return None

    budget = _Budget(_MAX_LOOKUPS) if budget is None else budget
    if not budget.spend():
        return None

    # `visited` is per-path, not global: a legitimate table reaches the same
    # drawable down two layers, and a global set would make the second lookup
    # miss. What must never happen is a resource reaching *itself*.
    visited = frozenset() if visited is None else visited
    if resource_id in visited:
        return None
    visited = visited | {resource_id}

    best: AppIcon | None = None

    for value in table.values(resource_id):
        if value.is_reference:
            found = _resolve(
                archive, table, value.value, depth + 1, adaptive, visited, budget
            )
            if found is not None:
                return found
            continue

        if not value.is_file or value.string is None:
            continue

        try:
            blob = archive.read(value.string)
        except (KeyError, ValueError, zipfile.BadZipFile):
            continue

        media_type = _media_type(blob)
        if media_type is not None:
            if len(blob) > MAX_ICON_BYTES:
                continue
            candidate = AppIcon(data=blob, media_type=media_type, adaptive=adaptive)
            # Configurations are already ordered best-density-first, but a table
            # may declare several at one density; the larger file is the better
            # artwork.
            if best is None or len(blob) > len(best.data):
                best = candidate
            continue

        if not _is_binary_xml(blob):
            continue

        try:
            elements = parse_elements(blob)
        except AxmlError:
            continue

        if elements and elements[0].name == "vector":
            # A vector drawable. Nothing to extract without a renderer.
            continue

        # Anything reached from inside an adaptive icon is a layer on the 108dp
        # canvas, and stays flagged as such however deep the nesting goes.
        nested_adaptive = adaptive or (bool(elements) and elements[0].name == "adaptive-icon")
        for reference in _layer_references(elements):
            found = _resolve(
                archive, table, reference, depth + 1, nested_adaptive, visited, budget
            )
            if found is not None:
                return found

    return best


def read_table(archive: zipfile.ZipFile) -> arsc.ResourceTable | None:
    """Parse an APK's resource table, or None when it has none we can read.

    Exposed so a caller that asks the table more than one question parses it
    **once**. Outlook's is 39.6 MB and costs a second to read; the label and the
    icon are two questions about the same file, and answering them from separate
    parses would both double that and let the two answers disagree.
    """
    try:
        return arsc.parse(archive.read(_RESOURCE_TABLE))
    except _UNREADABLE:
        # ⚠️ `struct.error` is **not** a `ValueError` — its MRO goes straight to
        # `Exception` — and a short string pool raises `IndexError`. Catching only
        # (KeyError, ValueError, ArscError) let a truncated or repacked table
        # escape as an HTTP 500 from the upload endpoint, and abort the whole
        # startup backfill on the first bad package. `MemoryError` is here for the
        # same reason: a hostile table can ask for more than there is.
        return None


def extract_icon(
    archive: zipfile.ZipFile, table: arsc.ResourceTable | None = None
) -> AppIcon | None:
    """The launcher icon for an open APK, or None when it cannot be extracted.

    None is a normal outcome, not an error: a vector-only icon is common and the
    caller is expected to fall back to a placeholder.
    """
    if table is None:
        table = read_table(archive)
    if table is None:
        return None

    try:
        elements = parse_elements(archive.read(_MANIFEST))
    except (KeyError, ValueError, AxmlError):
        return None

    application = next((e for e in elements if e.name == "application"), None)
    if application is None:
        return None

    # `roundIcon` is a fallback, not a preference: it is the same artwork masked
    # for circular launchers, and some apps declare it without declaring `icon`.
    for attribute in ("icon", "roundIcon"):
        reference = application.attributes.get(attribute)
        if not isinstance(reference, str) or not reference.startswith("@0x"):
            continue
        try:
            resource_id = int(reference[1:], 16)
        except ValueError:
            continue
        icon = _resolve(archive, table, resource_id)
        if icon is not None:
            return icon

    return None
