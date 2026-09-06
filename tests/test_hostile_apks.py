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

"""Hostile and malformed resource tables (W53).

`resources.arsc` is attacker-chosen content: the entire point of this inspector is
to read files it does not trust. A pre-commit review found four ways to turn a tiny
upload into unbounded work or an unhandled 500, each reproduced against the real
code. These pin the fixes.

Every case is built byte by byte rather than mocked — a mock of a parser proves
nothing about the parser.
"""

from __future__ import annotations

import io
import pathlib
import struct
import time
import zipfile

import pytest

from app.artifacts import arsc
from app.artifacts.app_icon import extract_icon, read_table
from app.artifacts.axml import AxmlError, StringPool

RES_TABLE = 0x0002
RES_STRING_POOL = 0x0001
RES_TABLE_PACKAGE = 0x0200
RES_TABLE_TYPE = 0x0201

_CONFIG = struct.pack("<I", 28) + b"\x00" * 24
_TYPE_HEADER_SIZE = 20 + 28


def _string_pool(strings: list[str], *, declared_count: int | None = None) -> bytes:
    """A minimal UTF-16 ResStringPool chunk."""
    count = len(strings) if declared_count is None else declared_count
    offsets, blob = b"", b""
    for text in strings:
        offsets += struct.pack("<I", len(blob))
        blob += struct.pack("<H", len(text)) + text.encode("utf-16-le") + b"\x00\x00"
    header_size = 28
    strings_start = header_size + len(offsets)
    body = struct.pack("<IIIII", count, 0, 0, strings_start, 0) + offsets + blob
    return struct.pack("<HHI", RES_STRING_POOL, header_size, 8 + len(body)) + body


def _type_chunk(*, entry_count: int, index: bytes = b"", entries: bytes = b"") -> bytes:
    body = (
        bytes([1, 0, 0, 0])
        + struct.pack("<II", entry_count, _TYPE_HEADER_SIZE + len(index))
        + _CONFIG
        + index
        + entries
    )
    return struct.pack("<HHI", RES_TABLE_TYPE, _TYPE_HEADER_SIZE, 8 + len(body)) + body


def _package(type_chunks: bytes) -> bytes:
    header_size = 288
    body = struct.pack("<I", 0x7F) + b"\x00" * (header_size - 12) + type_chunks
    return struct.pack("<HHI", RES_TABLE_PACKAGE, header_size, 8 + len(body)) + body


def _table(package_chunk: bytes) -> bytes:
    body = struct.pack("<I", 1) + _string_pool(["res/x.png"]) + package_chunk
    return struct.pack("<HHI", RES_TABLE, 12, 12 + len(body)) + body


def _apk(arsc_bytes: bytes) -> zipfile.ZipFile:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("resources.arsc", arsc_bytes)
        archive.writestr("AndroidManifest.xml", b"\x03\x00\x08\x00short")
    return zipfile.ZipFile(io.BytesIO(buffer.getvalue()))


# --------------------------------------------------------------------------- #
# Unbounded work
# --------------------------------------------------------------------------- #


def test_a_huge_declared_entry_count_does_not_become_huge_work():
    """`entry_count` is an unchecked uint32, and the slot loop `continue`s past
    unreadable slots rather than stopping — so a declared count of four billion
    was four billion iterations over a few hundred bytes."""
    hostile = _table(_package(_type_chunk(entry_count=0xFFFFFFFF)))

    started = time.perf_counter()
    with pytest.raises(arsc.ArscError):
        arsc.parse(hostile)
    elapsed = time.perf_counter() - started

    assert elapsed < 5, f"a bogus entry_count still cost {elapsed:.1f}s"


def test_a_string_pool_cannot_decode_more_than_its_cap():
    """Many strings sharing one offset, whose declared length runs to the end of
    the buffer, cost count x len(data). Measured before the cap: a 2 MB table
    with 300 strings took 603 MB of heap."""
    filler = 1 << 20
    header_size = 28
    offsets = struct.pack("<I", 0) * 4000
    strings_start = header_size + len(offsets)
    # One string declaring far more length than it owns; every offset points at
    # it, so each decode runs to the end of the buffer.
    blob = struct.pack("<H", 0x7FFF) + b"A\x00" * filler
    body = struct.pack("<IIIII", 4000, 0, 0, strings_start, 0) + offsets + blob
    pool = struct.pack("<HHI", RES_STRING_POOL, header_size, 8 + len(body)) + body

    with pytest.raises(AxmlError, match="decodes to more than"):
        StringPool(pool, 0)


def test_a_declared_string_count_beyond_the_buffer_is_clamped():
    """`count` was read from a buffer it had already run off the end of."""
    pool = _string_pool(["a", "b"], declared_count=0xFFFFFF)

    # Clamped rather than rejected: a truncated pool is readable as far as it
    # goes, and refusing it outright would reject salvageable APKs.
    assert StringPool(pool, 0).get(0) == "a"


def test_a_self_referencing_resource_terminates():
    """A resource whose value is a reference to itself.

    Depth alone bounded this; fan-out across configurations did not, and the
    resolver kept no visited set.
    """
    entry = (
        struct.pack("<HH", 8, 0)
        + struct.pack("<I", 0)
        + bytes([0, 0, 0, 0x01])
        + struct.pack("<I", 0x7F010000)
    )
    hostile = _table(
        _package(_type_chunk(entry_count=1, index=struct.pack("<I", 0), entries=entry))
    )
    table = arsc.parse(hostile)

    started = time.perf_counter()
    with _apk(hostile) as archive:
        extract_icon(archive, table)
    elapsed = time.perf_counter() - started

    assert elapsed < 5, f"a self-reference cost {elapsed:.1f}s"


# --------------------------------------------------------------------------- #
# Malformed input must not escape as a 500
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "corrupt",
    [
        pytest.param(b"", id="empty"),
        pytest.param(b"\x02\x00\x0c\x00", id="header-only"),
        pytest.param(struct.pack("<HHI", RES_TABLE, 12, 0xFFFFFFFF), id="size-past-buffer"),
        pytest.param(struct.pack("<HHI", RES_TABLE, 12, 12) + b"\x01", id="truncated-pool"),
        pytest.param(struct.pack("<HHI", RES_TABLE, 12, 13) + b"\x00" * 200, id="empty-package"),
    ],
)
def test_a_malformed_table_is_unreadable_rather_than_fatal(corrupt):
    """`struct.error` is **not** a `ValueError`, and a short pool raises
    `IndexError`. Catching only (KeyError, ValueError, ArscError) let both escape
    — an HTTP 500 from the upload endpoint, and an aborted startup backfill that
    discarded every row it had already filled."""
    with _apk(corrupt) as archive:
        assert read_table(archive) is None
        assert extract_icon(archive) is None


def test_a_truncated_real_table_is_unreadable_rather_than_fatal():
    """The reviewer's own reproduction: a real APK's table, cut short."""
    survey = pathlib.Path("Test Files/ArcGIS+Survey123_3.25.32_APKPure.apk")
    if not survey.exists():
        pytest.skip("the Survey123 APK is not in this checkout")

    with zipfile.ZipFile(survey) as real:
        table = real.read("resources.arsc")

    for cut in (200, 5000, len(table) // 2):
        with _apk(table[:cut]) as archive:
            assert read_table(archive) is None, f"a {cut}-byte table was not refused"


def test_an_upload_of_a_hostile_apk_is_refused_not_a_500(client):
    """End to end through the real endpoint: the honest answer is a 4xx."""
    from tests.conftest import ADMIN_HEADERS

    hostile = _table(_package(_type_chunk(entry_count=0xFFFFFFFF)))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("resources.arsc", hostile)
        archive.writestr("AndroidManifest.xml", b"\x03\x00\x08\x00nonsense")

    response = client.post(
        "/api/v1/packages",
        files={"file": ("hostile.apk", buffer.getvalue(), "application/octet-stream")},
        headers=ADMIN_HEADERS,
    )

    assert response.status_code < 500, f"hostile upload produced {response.status_code}"


# --------------------------------------------------------------------------- #
# Bag (resource array) parsing — W54
# --------------------------------------------------------------------------- #


def _bag_entry(count: int) -> bytes:
    """A ResTable_map_entry declaring `count` members, with none following."""
    return struct.pack("<HH", 16, 0x0001) + struct.pack("<I", 0) + struct.pack("<II", 0, count)


def test_many_slots_pointing_at_one_bag_do_not_multiply_the_work():
    """The clamp on slot *count* does not clamp bag *work*.

    Nothing requires index slots to name distinct entries. A chunk whose every
    slot holds offset 0 aims all of them at a single entry declaring the maximum
    member count, so the cost is slots x members — a few KB of file asking for
    gigabytes. Each entry offset is now read at most once per chunk.
    """
    slots = 4000
    index = struct.pack("<H", 0) * slots  # offset16: every slot -> offset 0
    body = (
        bytes([1, 0x02, 0, 0])  # type 1, FLAG_OFFSET16
        + struct.pack("<II", slots, _TYPE_HEADER_SIZE + len(index))
        + _CONFIG
        + index
        + _bag_entry(count=0xFFFFFFFF)
    )
    chunk = struct.pack("<HHI", RES_TABLE_TYPE, _TYPE_HEADER_SIZE, 8 + len(body)) + body
    hostile = _table(_package(chunk))

    started = time.perf_counter()
    try:
        arsc.parse(hostile)
    except arsc.ArscError:
        pass
    elapsed = time.perf_counter() - started

    assert elapsed < 5, f"duplicated slots still cost {elapsed:.1f}s"


def test_a_bag_declaring_more_members_than_exist_is_clamped():
    index = struct.pack("<I", 0)
    body = (
        bytes([1, 0, 0, 0])
        + struct.pack("<II", 1, _TYPE_HEADER_SIZE + len(index))
        + _CONFIG
        + index
        + _bag_entry(count=0xFFFFFFFF)
    )
    chunk = struct.pack("<HHI", RES_TABLE_TYPE, _TYPE_HEADER_SIZE, 8 + len(body)) + body

    started = time.perf_counter()
    try:
        arsc.parse(_table(_package(chunk)))
    except arsc.ArscError:
        pass
    elapsed = time.perf_counter() - started

    assert elapsed < 5, f"a bogus member count cost {elapsed:.1f}s"
