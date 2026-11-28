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

"""Minimal Android binary XML (AXML) reader.

An APK's ``AndroidManifest.xml`` is compiled binary XML, so the package name and
version cannot be read without decoding it. This implements only the subset needed
to pull manifest attributes — enough to identify a build, not a general XML decoder.

Written by hand rather than pulling in androguard: that is a large malware-analysis
framework, and this needs a few hundred lines of well-specified format handling.

Format reference: ``ResChunk_header`` and friends in AOSP
``libs/androidfw/include/androidfw/ResourceTypes.h``.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field, replace

# Chunk types
_RES_STRING_POOL = 0x0001
_RES_XML = 0x0003
_RES_XML_RESOURCE_MAP = 0x0180
_RES_XML_START_ELEMENT = 0x0102
_RES_XML_END_ELEMENT = 0x0103

# String pool flags
_UTF8_FLAG = 1 << 8

#: Ceiling on the characters one string pool may decode to. Outlook's is the
#: largest real one seen here at ~40 MB of table; this leaves generous room above
#: any legitimate build while refusing the quadratic blow-up a crafted pool can
#: otherwise ask for.
_MAX_POOL_BYTES = 64 * 1024 * 1024

# Res_value data types
_TYPE_REFERENCE = 0x01
_TYPE_STRING = 0x03
_TYPE_INT_DEC = 0x10
_TYPE_INT_HEX = 0x11
_TYPE_INT_BOOLEAN = 0x12

ANDROID_NAMESPACE = "http://schemas.android.com/apk/res/android"

# Well-known attribute resource ids, used when an APK's string pool carries empty
# attribute names — some build and obfuscation toolchains strip them, and then the
# resource id is the only way to tell which attribute you are looking at.
ATTRIBUTE_RESOURCE_IDS: dict[int, str] = {
    0x0101020C: "minSdkVersion",
    0x01010270: "targetSdkVersion",
    0x0101021B: "versionCode",
    0x0101021C: "versionName",
    0x01010001: "label",
    0x01010003: "name",
    0x01010572: "compileSdkVersion",
}


class AxmlError(ValueError):
    """Raised when a buffer is not valid Android binary XML."""


@dataclass
class AxmlElement:
    name: str
    attributes: dict[str, str | int] = field(default_factory=dict)
    #: Nesting level, root being 0.
    #:
    #: Load-bearing wherever a document's shape carries meaning rather than just
    #: its contents. A managed-configuration schema nests its keys inside a
    #: `bundle` restriction, and Gboard declares **one** top-level key with 124
    #: children — read flat, that looks like 125 configurable keys, and setting
    #: any child would write it where the app never reads (W49).
    depth: int = 0

    def get_int(self, key: str) -> int | None:
        value = self.attributes.get(key)
        return value if isinstance(value, int) else None

    def get_str(self, key: str) -> str | None:
        value = self.attributes.get(key)
        return value if isinstance(value, str) else None


class StringPool:
    """A `ResStringPool` chunk.

    Public because `resources.arsc` uses the identical chunk — the format is
    shared, so `app.artifacts.arsc` reuses this rather than carrying a second
    copy of the UTF-8/UTF-16 length quirks to drift out of step with.
    """

    def __init__(self, data: bytes, offset: int):
        try:
            self._build(data, offset)
        except (struct.error, IndexError) as exc:
            # ⚠️ This module's declared failure is `AxmlError`, and every caller
            # catches exactly that. `struct.error` is **not** a `ValueError` — its
            # MRO goes straight to `Exception` — so a truncated buffer used to
            # sail past `except AxmlError` in `_read_manifest` and surface as an
            # HTTP 500 on upload. A short manifest is a bad file, not a bug.
            raise AxmlError(f"malformed string pool: {exc}") from exc

    def _build(self, data: bytes, offset: int) -> None:
        chunk_type, header_size, chunk_size = struct.unpack_from("<HHI", data, offset)
        if chunk_type != _RES_STRING_POOL:
            raise AxmlError(f"expected a string pool, got chunk type {chunk_type:#x}")

        count, _style_count, flags, strings_start, _styles_start = struct.unpack_from(
            "<IIIII", data, offset + 8
        )
        self._utf8 = bool(flags & _UTF8_FLAG)
        self._strings: list[str] = []

        offsets_at = offset + header_size
        base = offset + strings_start

        # ⚠️ `count` is an unchecked uint32 from the file and every string is
        # decoded eagerly, so the pool is the cheapest place in this parser to ask
        # for absurd amounts of memory. Two independent bounds, because either
        # alone leaves a hole:
        #
        # * **count** is clamped to the offsets the chunk can actually hold. Left
        #   unclamped it is read from a buffer it has already run off the end of.
        # * **total decoded bytes** is capped. A UTF-16 entry may declare a length
        #   of up to 0x7FFFFFFF code units, and a Python slice *clamps* rather than
        #   failing — so every string can decode the entire remaining buffer, and
        #   N strings sharing one offset cost N × len(data). Measured before this
        #   bound: a 2 MB table with 300 strings took 603 MB of heap; scaled up it
        #   is an OOM kill of the only uvicorn worker, which drops every device
        #   check-in in flight.
        available = max(0, len(data) - offsets_at)
        count = min(count, available // 4)

        budget = _MAX_POOL_BYTES
        for index in range(count):
            (string_offset,) = struct.unpack_from("<I", data, offsets_at + index * 4)
            decoded = self._decode(data, base + string_offset)
            budget -= len(decoded)
            if budget < 0:
                raise AxmlError(
                    f"string pool decodes to more than {_MAX_POOL_BYTES} characters"
                )
            self._strings.append(decoded)

        self.chunk_size = chunk_size

    def _decode(self, data: bytes, position: int) -> str:
        # A clamped `count` can still point a slot at a wild offset, and every
        # length field below is attacker-chosen. An out-of-range string is empty,
        # not fatal — the rest of the pool may still be readable.
        if position < 0 or position >= len(data):
            return ""
        if self._utf8:
            # Two length fields: UTF-16 length then byte length, each 1-2 bytes.
            position, _ = self._read_utf8_length(data, position)
            position, byte_length = self._read_utf8_length(data, position)
            return data[position : position + byte_length].decode("utf-8", errors="replace")

        (length,) = struct.unpack_from("<H", data, position)
        position += 2
        if length & 0x8000:  # extended length: high word then low word
            (low,) = struct.unpack_from("<H", data, position)
            position += 2
            length = ((length & 0x7FFF) << 16) | low
        return data[position : position + length * 2].decode("utf-16-le", errors="replace")

    @staticmethod
    def _read_utf8_length(data: bytes, position: int) -> tuple[int, int]:
        length = data[position]
        position += 1
        if length & 0x80:
            length = ((length & 0x7F) << 8) | data[position]
            position += 1
        return position, length

    def get(self, index: int) -> str:
        if index < 0 or index >= len(self._strings):
            return ""
        return self._strings[index]


def parse_elements(data: bytes) -> list[AxmlElement]:
    """Decode every start element and its attributes, in document order.

    Raises `AxmlError` for anything unreadable — including a buffer that simply
    stops early. Callers catch that one type, so nothing here may escape as a
    `struct.error` or an `IndexError`.
    """
    try:
        return _parse_elements(data)
    except (struct.error, IndexError) as exc:
        raise AxmlError(f"malformed binary XML: {exc}") from exc


def _parse_elements(data: bytes) -> list[AxmlElement]:
    if len(data) < 8:
        raise AxmlError("buffer too small to be binary XML")

    chunk_type, header_size, _total = struct.unpack_from("<HHI", data, 0)
    if chunk_type != _RES_XML:
        raise AxmlError(f"not binary XML (chunk type {chunk_type:#x})")

    pool = StringPool(data, header_size)
    position = header_size + pool.chunk_size
    resource_ids: list[int] = []
    elements: list[AxmlElement] = []
    depth = 0

    while position + 8 <= len(data):
        chunk_type, chunk_header_size, chunk_size = struct.unpack_from("<HHI", data, position)
        if chunk_size <= 0:
            break

        if chunk_type == _RES_XML_RESOURCE_MAP:
            count = (chunk_size - chunk_header_size) // 4
            resource_ids = list(
                struct.unpack_from(f"<{count}I", data, position + chunk_header_size)
            )
        elif chunk_type == _RES_XML_START_ELEMENT:
            element = _parse_start_element(
                data, position + chunk_header_size, pool, resource_ids
            )
            elements.append(replace(element, depth=depth))
            depth += 1
        elif chunk_type == _RES_XML_END_ELEMENT:
            # Tracked only to keep `depth` honest. Without reading the end chunks
            # the document reads as a flat list, which silently loses any meaning
            # carried by nesting.
            depth -= 1

        position += chunk_size

    return elements


def _parse_start_element(
    data: bytes, offset: int, pool: StringPool, resource_ids: list[int]
) -> AxmlElement:
    _ns, name_index, attribute_start, attribute_size, attribute_count = struct.unpack_from(
        "<IIHHH", data, offset
    )
    element = AxmlElement(name=pool.get(name_index))

    attributes_at = offset + attribute_start
    for index in range(attribute_count):
        base = attributes_at + index * attribute_size
        attr_ns, attr_name_index, raw_value_index = struct.unpack_from("<III", data, base)
        _size, _res0, data_type, value = struct.unpack_from("<HBBI", data, base + 12)

        key = pool.get(attr_name_index)
        if not key and attr_name_index < len(resource_ids):
            key = ATTRIBUTE_RESOURCE_IDS.get(resource_ids[attr_name_index], "")
        if not key:
            continue

        # Namespaced attributes are stored under both "android:x" and "x". Callers
        # look up the bare name; the prefixed form is kept for disambiguation.
        parsed = _decode_value(pool, data_type, value, raw_value_index)
        if parsed is None:
            continue

        is_android_ns = attr_ns != 0xFFFFFFFF and pool.get(attr_ns) == ANDROID_NAMESPACE
        if is_android_ns:
            element.attributes.setdefault(f"android:{key}", parsed)
        element.attributes.setdefault(key, parsed)

    return element


def _decode_value(
    pool: StringPool, data_type: int, value: int, raw_value_index: int
) -> str | int | None:
    if data_type == _TYPE_STRING:
        return pool.get(value if value != 0xFFFFFFFF else raw_value_index)
    if data_type in (_TYPE_INT_DEC, _TYPE_INT_HEX):
        return value
    if data_type == _TYPE_INT_BOOLEAN:
        return 1 if value else 0
    if data_type == _TYPE_REFERENCE:
        # A resource reference, e.g. android:label="@string/app_name". The value
        # lives in resources.arsc, which we do not parse; report it symbolically
        # rather than pretending it is a literal.
        return f"@{value:#010x}"
    if raw_value_index != 0xFFFFFFFF:
        return pool.get(raw_value_index)
    return None
