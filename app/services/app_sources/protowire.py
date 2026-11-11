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

"""The protobuf wire format, by hand, for the few Play messages ATLAS uses (W435).

Decided in W435 chunk 1: about this much code, against a new dependency plus a
vendored `.proto`. The field numbers live with their callers in `play_details`
and are listed in `docs/GOOGLE_PLAY_DETAILS.md`.

⚠️ **Decoding is defensive, because the input is Google's.** A truncated or
malformed body raises :class:`WireError`, never an `IndexError` from deep inside a
loop, so a caller can turn it into one honest error.
"""

from __future__ import annotations

import struct


class WireError(ValueError):
    """The bytes are not a protobuf message this decoder can read."""


def _varint(n: int) -> bytes:
    n &= (1 << 64) - 1  # a negative int64 is ten bytes of two's complement
    out = bytearray()
    while True:
        low = n & 0x7F
        n >>= 7
        if n:
            out.append(low | 0x80)
        else:
            out.append(low)
            return bytes(out)


def varint(field: int, value: int | bool) -> bytes:
    """A varint field (int32, int64, bool)."""
    return _varint(field << 3) + _varint(int(value))


def string(field: int, value: str | bytes) -> bytes:
    """A length-delimited field: a string, bytes, or an encoded message."""
    data = value.encode("utf-8") if isinstance(value, str) else value
    return _varint((field << 3) | 2) + _varint(len(data)) + data


def _read_varint(buf: bytes, i: int) -> tuple[int, int]:
    shift = result = 0
    while True:
        if i >= len(buf) or shift > 63:
            raise WireError("truncated varint")
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, i
        shift += 7


def decode(buf: bytes) -> dict[int, list]:
    """One message level: field number → its values, in order.

    Varints and fixed-width values come back as ints, length-delimited fields as
    bytes (decode them again to read a nested message).
    """
    out: dict[int, list] = {}
    i = 0
    while i < len(buf):
        key, i = _read_varint(buf, i)
        field, wire_type = key >> 3, key & 7
        if wire_type == 0:
            value, i = _read_varint(buf, i)
        elif wire_type == 1:
            if i + 8 > len(buf):
                raise WireError("truncated fixed64")
            value = struct.unpack("<Q", buf[i:i + 8])[0]
            i += 8
        elif wire_type == 2:
            length, i = _read_varint(buf, i)
            if i + length > len(buf):
                raise WireError("truncated length-delimited field")
            value = buf[i:i + length]
            i += length
        elif wire_type == 5:
            if i + 4 > len(buf):
                raise WireError("truncated fixed32")
            value = struct.unpack("<I", buf[i:i + 4])[0]
            i += 4
        else:
            raise WireError(f"unsupported wire type {wire_type}")
        out.setdefault(field, []).append(value)
    return out


def first(buf: bytes | None, *fields: int):
    """Follow nested fields, taking the first value at each level; None if absent."""
    for field in fields:
        if not isinstance(buf, (bytes, bytearray)):
            return None
        values = decode(buf).get(field)
        buf = values[0] if values else None
    return buf


def text(value) -> str | None:
    """A length-delimited value as text, or None."""
    if not isinstance(value, (bytes, bytearray)) or not value:
        return None
    return value.decode("utf-8", errors="replace")
