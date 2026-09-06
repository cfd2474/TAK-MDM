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

"""Minimal `resources.arsc` reader.

A compiled manifest states almost nothing directly. `android:icon` and
`android:label` are **resource references** — `@0x7f0903f4` — and the value behind
one lives in `resources.arsc`. Without this, an APK can be identified but not
described: no display name for Outlook or Gboard, no icon for anything (W53).

Scope is deliberately narrow. This resolves a resource id to its values, one per
configuration; it does not model packages, locales, styles, or attribute
bags. That is enough for "which file is this app's icon" and "what is this app
called", which are the two questions the library actually asks.

Format reference: `ResTable_header`, `ResTable_package`, `ResTable_type` and
`ResTable_entry` in AOSP `libs/androidfw/include/androidfw/ResourceTypes.h`.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from app.artifacts.axml import AxmlError, StringPool

# Chunk types
_RES_TABLE = 0x0002
_RES_TABLE_PACKAGE = 0x0200
_RES_TABLE_TYPE = 0x0201

# ResTable_type flags
_FLAG_SPARSE = 0x01
_FLAG_OFFSET16 = 0x02

# ResTable_entry flags
_ENTRY_COMPLEX = 0x0001

# Res_value data types we care about
TYPE_REFERENCE = 0x01
TYPE_STRING = 0x03

#: A `ResTable_config` is variable-length — it grew over Android releases and its
#: leading `size` says how much of it is actually present — but the fields below
#: are at fixed offsets from its start:
#:
#:     uint32 size          @0
#:     uint16 mcc, mnc      @4, @6
#:     char   language[2]   @8      char country[2]  @10
#:     uint8  orientation   @12     uint8 touchscreen @13    uint16 density @14
#:
#: ⚠️ Density is at **14**. Reading it at 12 picks up `orientation|touchscreen`,
#: which is zero for practically every resource — so every entry looks
#: density-less, the "best density first" ordering quietly does nothing, and the
#: only thing still choosing between candidates is the file-size tiebreak. That
#: bug was in the first draft of this file and the icons resolved anyway, which is
#: exactly why it survived.
_CONFIG_SIZE_OFFSET = 0
_CONFIG_LANGUAGE_OFFSET = 8
_CONFIG_DENSITY_OFFSET = 14

#: Bytes of `ResTable_config` that must be present before a field can be read.
_CONFIG_MIN_FOR_LOCALE = 12
_CONFIG_MIN_FOR_DENSITY = 16

#: Densities that are not a dpi value. `ANY` beats every real density when picking
#: the best match, which is exactly wrong for icons — a density-independent entry
#: is usually the adaptive-icon XML, and we want the largest *raster* underneath
#: it. Ranked below real densities for that reason.
_DENSITY_ANY = 0xFFFE
_DENSITY_NONE = 0x0000


class ArscError(ValueError):
    """Raised when a buffer is not a usable resource table."""


@dataclass(frozen=True)
class ResourceValue:
    """One configuration's value for a resource id."""

    #: dpi, or one of the pseudo-densities. 0 when the entry is not density-scoped.
    density: int
    #: Two-letter language code, or "" for the **default** configuration — the one
    #: Android falls back to when the device's locale does not match, and the one
    #: an operator expects to see in a console.
    language: str
    data_type: int
    #: Set when `data_type` is TYPE_STRING — for a `drawable`/`mipmap` this is the
    #: archive path of the file, e.g. `res/ima`.
    string: str | None
    #: The raw 32-bit datum. For TYPE_REFERENCE this is the resource id pointed at.
    value: int

    @property
    def is_file(self) -> bool:
        return self.data_type == TYPE_STRING and bool(self.string)

    @property
    def is_reference(self) -> bool:
        return self.data_type == TYPE_REFERENCE and self.value != 0

    @property
    def is_default_locale(self) -> bool:
        return not self.language

    @property
    def sort_key(self) -> tuple[int, int, int]:
        """Best-first ordering.

        The default locale comes first: a resource exists once per translation,
        and without this the "first" value for an app's name is whichever
        translation the table happens to list first — Outlook carries 86 of them.
        Then real densities descending, with the density-independent entries last,
        because for an icon those are the adaptive-icon XML and the raster
        underneath is what is wanted.
        """
        pseudo = self.density in (_DENSITY_ANY, _DENSITY_NONE)
        return (0 if self.is_default_locale else 1, 1 if pseudo else 0, -self.density)


class ResourceTable:
    """Resource id → the values declared for it, across configurations."""

    def __init__(self, entries: dict[int, list[ResourceValue]]):
        self._entries = entries

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, resource_id: int) -> bool:
        return resource_id in self._entries

    def values(self, resource_id: int) -> list[ResourceValue]:
        """Every declared value, best configuration first."""
        return sorted(self._entries.get(resource_id, []), key=lambda v: v.sort_key)

    def string(self, resource_id: int, _depth: int = 0) -> str | None:
        """Resolve a resource id to a string, following references.

        The depth guard is not paranoia about malice; aliases legitimately chain,
        and a resource table produced by a tool we have never seen is not
        obliged to be acyclic.
        """
        if _depth > 4:
            return None
        for value in self.values(resource_id):
            if value.data_type == TYPE_STRING and value.string is not None:
                return value.string
            if value.is_reference:
                resolved = self.string(value.value, _depth + 1)
                if resolved is not None:
                    return resolved
        return None


def parse(data: bytes) -> ResourceTable:
    """Decode a `resources.arsc` buffer."""
    if len(data) < 12:
        raise ArscError("buffer is too short to be a resource table")

    chunk_type, header_size, _size = struct.unpack_from("<HHI", data, 0)
    if chunk_type != _RES_TABLE:
        raise ArscError(f"not a resource table (chunk type {chunk_type:#x})")

    try:
        # The table's own string pool holds every string *value*, including the
        # archive paths of file-backed resources.
        pool = StringPool(data, header_size)
    except AxmlError as exc:
        raise ArscError(f"could not read the value string pool: {exc}") from exc

    entries: dict[int, list[ResourceValue]] = {}
    position = header_size + pool.chunk_size

    while position + 8 <= len(data):
        chunk_type, chunk_header_size, chunk_size = struct.unpack_from("<HHI", data, position)
        # A zero size would spin forever; a size running past the buffer is a
        # malformed table, not a chunk we can read part of.
        if chunk_size < 8 or position + chunk_size > len(data):
            break
        if chunk_type == _RES_TABLE_PACKAGE:
            _read_package(data, position, chunk_header_size, chunk_size, pool, entries)
        position += chunk_size

    if not entries:
        raise ArscError("resource table declares no entries")
    return ResourceTable(entries)


def _read_package(
    data: bytes,
    offset: int,
    header_size: int,
    size: int,
    pool: StringPool,
    entries: dict[int, list[ResourceValue]],
) -> None:
    # The outer loop guarantees only 8 bytes; this reads 12.
    if offset + 12 > len(data):
        return
    (package_id,) = struct.unpack_from("<I", data, offset + 8)

    # The package's own type- and key-name pools sit between the header and the
    # type chunks. They are skipped rather than parsed: a resource is addressed
    # here by numeric id, never by name, so the names are dead weight.
    position = offset + header_size
    # `size` is declared by the file. Clamped, so a package claiming to be larger
    # than the buffer cannot walk the loop past the end of it.
    end = min(offset + size, len(data))

    while position + 8 <= end:
        chunk_type, chunk_header_size, chunk_size = struct.unpack_from("<HHI", data, position)
        if chunk_size < 8 or position + chunk_size > end:
            break
        if chunk_type == _RES_TABLE_TYPE:
            _read_type(data, position, chunk_header_size, chunk_size, package_id, pool, entries)
        position += chunk_size


def _read_type(
    data: bytes,
    offset: int,
    header_size: int,
    size: int,
    package_id: int,
    pool: StringPool,
    entries: dict[int, list[ResourceValue]],
) -> None:
    # Fixed header is 20 bytes up to and including the config; the caller has only
    # guaranteed 8.
    if offset + 20 > len(data):
        return
    type_id = data[offset + 8]
    flags = data[offset + 9]
    entry_count, entries_start = struct.unpack_from("<II", data, offset + 12)

    # ⚠️ `entry_count` is an unchecked uint32 straight out of the file, and the
    # loop below `continue`s past unreadable slots rather than stopping — so a
    # declared count of 4 billion is 4 billion iterations of real work in a file
    # that may be a few hundred bytes long. Clamp it to what the index could
    # possibly hold: each slot costs 2 bytes in the offset-16 encoding and 4
    # otherwise, and the index cannot extend past the chunk.
    index_bytes = max(0, min(offset + size, len(data)) - (offset + header_size))
    slot_width = 2 if flags & _FLAG_OFFSET16 else 4
    entry_count = min(entry_count, index_bytes // slot_width)

    # `ResTable_config` begins right after the fixed header fields.
    config_at = offset + 20
    density, language = _read_config(data, config_at)

    sparse = bool(flags & _FLAG_SPARSE)
    offset16 = bool(flags & _FLAG_OFFSET16)
    index_at = offset + header_size

    for slot in range(entry_count):
        located = _entry_offset(data, index_at, slot, sparse=sparse, offset16=offset16)
        if located is None:
            continue
        entry_index, entry_offset = located

        at = offset + entries_start + entry_offset
        if at + 8 > len(data):
            continue

        entry_size, entry_flags = struct.unpack_from("<HH", data, at)
        if entry_flags & _ENTRY_COMPLEX:
            # A bag (style, array, attr). It has no single value, and nothing here
            # asks a question a bag could answer.
            continue

        value_at = at + entry_size
        if value_at + 8 > len(data):
            continue
        data_type = data[value_at + 3]
        (datum,) = struct.unpack_from("<I", data, value_at + 4)

        resource_id = (package_id << 24) | (type_id << 16) | entry_index
        entries.setdefault(resource_id, []).append(
            ResourceValue(
                density=density,
                language=language,
                data_type=data_type,
                string=pool.get(datum) if data_type == TYPE_STRING else None,
                value=datum,
            )
        )


def _read_config(data: bytes, offset: int) -> tuple[int, str]:
    """Density and language from a `ResTable_config`.

    Its leading `size` is authoritative: an older or trimmed config simply stops,
    and reading past it would interpret whatever follows in the chunk as screen
    metrics.
    """
    if offset + 4 > len(data):
        return 0, ""
    (size,) = struct.unpack_from("<I", data, offset + _CONFIG_SIZE_OFFSET)

    density = 0
    if size >= _CONFIG_MIN_FOR_DENSITY and offset + _CONFIG_DENSITY_OFFSET + 2 <= len(data):
        (density,) = struct.unpack_from("<H", data, offset + _CONFIG_DENSITY_OFFSET)

    language = ""
    if size >= _CONFIG_MIN_FOR_LOCALE and offset + _CONFIG_LANGUAGE_OFFSET + 2 <= len(data):
        raw = data[offset + _CONFIG_LANGUAGE_OFFSET : offset + _CONFIG_LANGUAGE_OFFSET + 2]
        # Zero bytes mean "any language" — the default configuration. A high bit
        # marks a packed three-letter code, which is still a specific locale and
        # so is simply "not default"; the exact code is of no use here.
        if raw != b"\x00\x00":
            language = raw.decode("ascii", errors="replace") if not raw[0] & 0x80 else "???"

    return density, language


def _entry_offset(
    data: bytes, index_at: int, slot: int, *, sparse: bool, offset16: bool
) -> tuple[int, int] | None:
    """Locate one entry in a type chunk's index, in whichever encoding it uses.

    Three encodings, all in the wild. The **sparse** one stores `(index, offset)`
    pairs, so a slot's position in the index says nothing about which resource it
    is — reading it as dense silently shifts every id. The **offset-16** one
    stores a 16-bit offset in units of 4 bytes; treating those units as bytes
    lands a quarter of the way into the table.
    """
    if sparse:
        if index_at + slot * 4 + 4 > len(data):
            return None
        entry_index, packed = struct.unpack_from("<HH", data, index_at + slot * 4)
        return entry_index, packed * 4

    if offset16:
        if index_at + slot * 2 + 2 > len(data):
            return None
        (packed,) = struct.unpack_from("<H", data, index_at + slot * 2)
        if packed == 0xFFFF:  # no entry in this configuration
            return None
        return slot, packed * 4

    if index_at + slot * 4 + 4 > len(data):
        return None
    (entry_offset,) = struct.unpack_from("<I", data, index_at + slot * 4)
    if entry_offset == 0xFFFFFFFF:
        return None
    return slot, entry_offset
