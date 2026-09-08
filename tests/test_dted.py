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
# ⚠️ The nested archive (W94)
# --------------------------------------------------------------------------- #


def test_a_nested_archive_is_repacked_rather_than_refused():
    """⚠️ What right-clicking a DTED folder in Windows produces.

    W93 refused this with an explanation. That was the wrong end of the problem:
    it is the *common* form, and re-zipping it by hand is work the server can
    just do. The cells are moved to the top instead.
    """
    layout = dted.plan(_zip({"DTED/w115/n32.dt2": b"t", "DTED/w116/n33.dt2": b"t"}))

    assert layout.needs_repack is True
    assert layout.wrappers == ("DTED",)
    assert [destination for _, destination in layout.moves] == [
        "w115/n32.dt2",
        "w116/n33.dt2",
    ]
    assert layout.archive.cells == ("w115", "w116")


def test_cells_are_found_however_deep_they_are_buried():
    layout = dted.plan(_zip({"a/b/c/w115/n32.dt2": b"t"}))

    assert layout.moves == (("a/b/c/w115/n32.dt2", "w115/n32.dt2"),)
    assert layout.wrappers == ("a",)


def test_an_already_flat_archive_is_left_completely_alone():
    """⚠️ The reason `needs_repack` exists at all.

    Recompressing is the expensive half — 34 MB/s against 423 MB/s to inflate —
    and rewriting a correct archive would also mean handing back a file that is
    not the one the operator uploaded, for no gain.
    """
    assert dted.plan(_terrain()).needs_repack is False


def test_the_repack_moves_the_cells_and_keeps_the_bytes():
    nested = _zip({"DTED/w115/n32.dt2": b"terrain", "DTED/w116/n33.dt2": b"more"})
    out = io.BytesIO()

    dted.repack(io.BytesIO(nested), out, dted.plan(nested))

    with zipfile.ZipFile(out) as repacked:
        assert repacked.namelist() == ["w115/n32.dt2", "w116/n33.dt2"]
        assert repacked.read("w115/n32.dt2") == b"terrain"
        assert repacked.read("w116/n33.dt2") == b"more"


def test_the_repack_drops_archiver_junk():
    """The agent's `isArchiverJunk` refuses to write it anyway, so carrying it
    would only add bytes to every download."""
    nested = _zip({"DTED/w115/n32.dt2": b"t", "__MACOSX/DTED/._w115": b"junk"})
    out = io.BytesIO()

    dted.repack(io.BytesIO(nested), out, dted.plan(nested))

    with zipfile.ZipFile(out) as repacked:
        assert repacked.namelist() == ["w115/n32.dt2"]


def test_files_that_are_not_terrain_are_carried_unchanged():
    """⚠️ Deleting an operator's bytes uninvited is worse than a stray file.

    ATAK reads only the cells, so a readme in the DTED directory costs nothing —
    but discarding it silently would be a surprise nobody asked for.
    """
    layout = dted.plan(_zip({"DTED/w115/n32.dt2": b"t", "DTED/readme.txt": b"hi"}))

    assert ("DTED/readme.txt", "DTED/readme.txt") in layout.moves
    assert layout.carried == 1


def test_two_files_claiming_one_cell_path_are_refused():
    """⚠️ Flattening can collide, and picking a winner would discard terrain.

    The only case where W94 still says no to something that holds real cells.
    """
    with pytest.raises(dted.DtedError) as raised:
        dted.plan(_zip({"one/w115/n32.dt2": b"a", "two/w115/n32.dt2": b"b"}))

    message = str(raised.value)
    assert "one/w115/n32.dt2" in message
    assert "two/w115/n32.dt2" in message


def test_the_layout_is_decided_from_names_alone():
    """`plan_layout` takes a list of strings, so the decision is testable without
    building a zip — the expensive part is the repack, not the thinking."""
    layout = dted.plan_layout(["Terrain/w115/n32.dt2", "Terrain/w115/n33.dt2"])

    assert layout.archive.file_count == 2
    assert layout.needs_repack is True


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


def test_looks_like_dted_says_yes_to_a_nested_one():
    """⚠️ Why General Files must not judge terrain by whether it is well-formed.

    It answers "was this meant to be DTED", so General Files can refuse it and
    name the sub-topic that handles it. Since W94 the nested archive is not even
    broken — the DTED tool will repack it — which makes sending it there more
    important, not less.
    """
    nested = _zip({"DTED/w115/n32.dt2": b"terrain"})

    assert dted.looks_like_dted(nested) is True
    assert dted.inspect(nested).cells == ("w115",)


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


def test_a_nested_archive_uploads_and_reports_the_repack(client: TestClient, db):
    """⚠️ The operator is told their file was rewritten.

    What comes back is not the archive they uploaded. Saying nothing would leave
    the next person comparing checksums with no explanation.
    """
    response = _upload(client, _zip({"DTED/w115/n32.dt2": b"terrain"}))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["repacked"] is True
    assert "'DTED'" in body["note"]
    assert db.scalar(select(ManagedFile)) is not None


def test_what_is_stored_for_a_nested_upload_is_the_flattened_archive(
    client: TestClient, db, artifact_storage
):
    """⚠️ The whole point of repacking on the server rather than the device.

    The invariant is that what ATLAS stores is what lands on disk, so the agent
    needs no update and every fielded device is already correct.
    """
    _upload(client, _zip({"DTED/w115/n32.dt2": b"terrain"}))
    managed = db.scalar(select(ManagedFile))

    with artifact_storage.open(managed.artifact_sha256) as handle:
        with zipfile.ZipFile(io.BytesIO(handle.read())) as stored:
            assert stored.namelist() == ["w115/n32.dt2"]


def test_a_flat_upload_is_stored_byte_for_byte(client: TestClient, db, artifact_storage):
    original = _terrain()
    _upload(client, original)
    managed = db.scalar(select(ManagedFile))

    with artifact_storage.open(managed.artifact_sha256) as handle:
        assert handle.read() == original


def test_a_zip_with_no_cells_at_all_is_still_refused_at_upload(client: TestClient, db):
    response = _upload(client, _zip({"notes.txt": b"hello"}))

    assert response.status_code == 422
    assert "no DTED cells" in response.json()["error"]
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
    assert dted.plan(data).needs_repack is False, "the sample is already flat"


@pytest.mark.skipif(not SAMPLE.exists(), reason="the DTED sample is not in this checkout")
def test_the_real_sample_would_be_flattened_if_someone_had_wrapped_it():
    """⚠️ Planning is separated from repacking so this costs nothing.

    Building a nested 726 MB zip to test the decision would take a minute of
    recompression. The decision is made from names alone, so the real names can
    be run through it with a folder in front of them.
    """
    with zipfile.ZipFile(SAMPLE) as archive:
        names = archive.namelist()

    layout = dted.plan_layout([f"Terrain Data/{name}" for name in names])

    assert layout.needs_repack is True
    assert layout.wrappers == ("Terrain Data",)
    assert layout.archive.cell_count == 11
    assert layout.archive.file_count == 68
    assert all(
        destination.count("/") == 1
        for _, destination in layout.moves
        if destination.endswith(".dt2")
    )
