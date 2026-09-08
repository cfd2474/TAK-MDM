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

"""ATAK terrain archives (W93).

⚠️ **The failure this guards against is invisible on the device.** ATAK unpacks
DTED flat into one directory — `FileSystemUtils.unzip(zip, dtedDir, true)` in
`ElevationDownloader` — so an archive whose cells sit inside a folder extracts
perfectly, writes every file, and shows no terrain. Nothing appears in any log.
The layout has to be caught at upload or not at all.
"""

from __future__ import annotations

import io
import pathlib
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.artifacts import dted
from app.db.models import ManagedFile
from app.services import files as file_service
from tests.conftest import ADMIN_HEADERS

SAMPLE = pathlib.Path("Test Files/DTED.zip")


def _zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def _terrain(**extra) -> bytes:
    entries = {"w115/n32.dt2": b"terrain", "w116/n33.dt2": b"terrain"}
    entries.update(extra)
    return _zip(entries)


# --------------------------------------------------------------------------- #
# Recognising it
# --------------------------------------------------------------------------- #


def test_a_cell_archive_is_read():
    archive = dted.inspect(_terrain())

    assert archive.cells == ("w115", "w116")
    assert archive.file_count == 2
    assert archive.levels == frozenset({2})


def test_every_dted_level_atak_knows_is_accepted():
    """`Dt2ElevationData` declares .dt0 through .dt3, at 1000 m down to 10 m."""
    archive = dted.inspect(
        _zip(
            {
                "w115/n32.dt0": b"a",
                "w115/n33.dt1": b"b",
                "w116/n34.dt2": b"c",
                "w117/n35.dt3": b"d",
            }
        )
    )
    assert archive.levels == frozenset({0, 1, 2, 3})


def test_eastern_cells_are_accepted_too():
    """The sample is western, but e007 is as valid a cell as w115."""
    assert dted.inspect(_zip({"e007/n51.dt2": b"x"})).cells == ("e007",)


def test_macos_pollution_is_ignored():
    """⚠️ The operator's own sample is full of it.

    `__MACOSX/` plus an AppleDouble `._n33.dt2` beside every real file — 226 zip
    entries for 68 pieces of terrain. Counted as content, a cell holding nothing
    but stubs would read as real.
    """
    archive = dted.inspect(
        _terrain(
            **{
                "__MACOSX/._w115": b"junk",
                "__MACOSX/w115/._n32.dt2": b"junk",
                "w115/._n32.dt2": b"junk",
                ".DS_Store": b"junk",
            }
        )
    )

    assert archive.file_count == 2, "AppleDouble stubs are not terrain"
    assert archive.cells == ("w115", "w116")


# --------------------------------------------------------------------------- #
# ⚠️ The wrapped archive
# --------------------------------------------------------------------------- #


def test_a_wrapped_archive_is_refused_with_the_reason():
    """⚠️ What right-clicking a DTED folder in Windows produces.

    It extracts flawlessly into `DTED/DTED/w115/…`, where ATAK never looks. The
    message has to say what to re-zip, because nothing on the device will.
    """
    with pytest.raises(dted.DtedError) as raised:
        dted.inspect(_zip({"DTED/w115/n32.dt2": b"terrain"}))

    message = str(raised.value)
    assert "DTED" in message
    assert "top of the zip" in message
    assert "silently" in message


def test_a_zip_with_no_cells_is_refused():
    with pytest.raises(dted.DtedError) as raised:
        dted.inspect(_zip({"notes.txt": b"hello"}))
    assert "no DTED cells" in str(raised.value)


def test_a_zip_of_only_junk_is_refused():
    with pytest.raises(dted.DtedError) as raised:
        dted.inspect(_zip({"__MACOSX/._x": b"junk"}))
    assert "archiver metadata" in str(raised.value)


def test_something_that_is_not_a_zip_is_refused():
    with pytest.raises(dted.DtedError) as raised:
        dted.inspect(b"not a zip")
    assert "not a readable zip" in str(raised.value)


def test_looks_like_dted_says_yes_to_a_wrapped_one():
    """⚠️ Laxer than `inspect`, on purpose — the same split as `has_manifest`.

    It answers "was this meant to be DTED", so General Files can refuse it and
    name the sub-topic that will explain the real problem. Calling it "not
    terrain" would send the operator hunting for the wrong fault.
    """
    wrapped = _zip({"DTED/w115/n32.dt2": b"terrain"})

    assert dted.looks_like_dted(wrapped) is True
    with pytest.raises(dted.DtedError):
        dted.inspect(wrapped)


def test_looks_like_dted_says_no_to_an_ordinary_zip():
    assert dted.looks_like_dted(_zip({"imagery/map.xml": b"x"})) is False


# --------------------------------------------------------------------------- #
# Delivery
# --------------------------------------------------------------------------- #


def _upload(client: TestClient, data: bytes, name: str = "Terrain"):
    return client.post(
        "/policies/dted/upload",
        data={"name": name},
        files={"file": ("dted.zip", data, "application/zip")},
        headers=ADMIN_HEADERS,
    )


def test_an_archive_uploads_and_reports_what_it_holds(client: TestClient, db):
    """Eleven cells is a different thing from one, and the count is how someone
    notices they grabbed the wrong archive."""
    response = _upload(client, _terrain())

    assert response.status_code == 200, response.text
    assert response.json()["summary"] == "2 cells, 2 files (DTED2)"
    assert db.scalar(select(ManagedFile)).name == "Terrain"


def test_a_wrapped_archive_is_refused_at_upload(client: TestClient, db):
    response = _upload(client, _zip({"DTED/w115/n32.dt2": b"terrain"}))

    assert response.status_code == 422
    assert "top of the zip" in response.json()["error"]
    assert db.scalar(select(ManagedFile)) is None


def test_terrain_unpacks_into_ataks_dted_directory(client: TestClient, db):
    _upload(client, _terrain())
    managed = db.scalar(select(ManagedFile))

    resolved = file_service.resolve_files(
        db, {"FILES": {"dted_archives": [{"file_id": str(managed.id)}]}}
    )
    entry = resolved["required"][0]

    assert entry["dest_path"] == "/sdcard/atak/DTED"
    assert entry["extract"] is True
    assert entry["extract_to"] == "/sdcard/atak/DTED"
    assert entry["dted"] is True


def test_terrain_persists_unlike_a_data_package(client: TestClient, db):
    """⚠️ The two ATAK file types look alike and behave oppositely.

    A package must never be re-sent — re-writing it makes ATAK import again.
    Terrain is read off the disk forever and nothing re-imports it, so a cell the
    user deleted should come back.
    """
    _upload(client, _terrain())
    managed = db.scalar(select(ManagedFile))

    resolved = file_service.resolve_files(
        db, {"FILES": {"dted_archives": [{"file_id": str(managed.id)}]}}
    )
    assert resolved["required"][0]["persist"] is True


def test_general_files_refuses_terrain_and_names_the_sub_topic(client: TestClient, db):
    response = client.post(
        "/policies/file/upload",
        files={"file": ("dted.zip", _terrain(), "application/zip")},
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 422
    assert "ATAK DTED" in response.json()["error"]
    assert db.scalar(select(ManagedFile)) is None


def test_the_dted_subtopic_is_a_real_form_now(client: TestClient):
    body = client.get("/policies/new").text
    panel = body[body.index('data-page-panel="file_management:atak-dted"'):]
    panel = panel[: panel.index("</section>")]

    assert "Not available yet." not in panel
    assert "data-dted-upload-open" in panel


# --------------------------------------------------------------------------- #
# The operator's own archive
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(not SAMPLE.exists(), reason="the DTED sample is not in this checkout")
def test_the_real_sample_is_recognised():
    """693 MB and 226 entries, of which only 68 are terrain — the rest is macOS
    metadata. Read from the zip's central directory alone, so the size costs
    nothing to inspect."""
    data = SAMPLE.read_bytes()
    archive = dted.inspect(data)

    assert archive.cell_count == 11
    assert archive.cells[0] == "w115"
    assert archive.cells[-1] == "w125"
    assert archive.file_count == 68
    assert archive.levels == frozenset({2})
    assert dted.looks_like_dted(data) is True
