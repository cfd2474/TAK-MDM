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

"""Uploading and building ATAK data packages in the console (W91, chunk B2).

⚠️ **The point of every check here is that it happens at upload.** A zip ATAK
will not import fails on a tablet as *nothing happening at all* — no error, no
import, no trace in any log. The operator is standing in front of this form, so
this is the only place a refusal can actually reach them.
"""

from __future__ import annotations

import io
import uuid
import zipfile

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.artifacts import mission_package as mp
from app.db.models import ManagedFile
from tests.conftest import ADMIN_HEADERS

ZIP = "application/zip"


def _valid_package(name: str = "Ops Layer") -> bytes:
    return mp.build(name, [("overlay.kml", b"<kml/>"), ("notes.txt", b"hello")])


def _plain_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("overlay.kml", b"<kml/>")
    return buffer.getvalue()


def _upload(client: TestClient, data: bytes, *, name: str = "", filename: str = "pkg.zip"):
    return client.post(
        "/content/data-package/upload",
        data={"name": name},
        files={"file": (filename, data, ZIP)},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )


# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #


def test_a_valid_package_is_catalogued_and_flagged(client: TestClient, db):
    response = _upload(client, _valid_package())
    assert response.status_code in (302, 303), response.text

    managed = db.scalar(select(ManagedFile))
    assert managed is not None
    assert managed.is_data_package is True
    # The manifest's own name is the better default: it is what ATAK will call
    # the package, and two names for one thing is how confusion starts.
    assert managed.name == "Ops Layer"


def test_an_operators_name_beats_the_manifests(client: TestClient, db):
    _upload(client, _valid_package(), name="North sector overlay")
    assert db.scalar(select(ManagedFile)).name == "North sector overlay"


def test_a_zip_without_a_manifest_is_refused_and_nothing_is_catalogued(
    client: TestClient, db
):
    """⚠️ ATAK would take this — `PlainZipExtractor` — so the message says so.

    Refusing it is an ATLAS rule, and an operator told only "rejected" would go
    looking for a fault in a file that does not have one.
    """
    response = _upload(client, _plain_zip())

    assert response.status_code in (302, 303)
    assert "MANIFEST" in response.headers["location"]
    assert "plain+zip" in response.headers["location"].replace("%20", "+")
    assert db.scalar(select(ManagedFile)) is None


def test_a_file_that_is_not_a_zip_is_refused(client: TestClient, db):
    response = _upload(client, b"this is not a zip", filename="notes.txt")

    assert "not+a+readable+zip" in response.headers["location"].replace("%20", "+")
    assert db.scalar(select(ManagedFile)) is None


def test_a_manifest_of_the_wrong_version_is_refused(client: TestClient, db):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            mp.MANIFEST_NAME,
            '<?xml version="1.0"?><MissionPackageManifest version="1">'
            '<Configuration><Parameter name="uid" value="a"/>'
            '<Parameter name="name" value="b"/></Configuration>'
            "<Contents/></MissionPackageManifest>",
        )
    response = _upload(client, buffer.getvalue())

    assert "version" in response.headers["location"]
    assert db.scalar(select(ManagedFile)) is None


def test_an_empty_upload_is_refused(client: TestClient, db):
    response = _upload(client, b"")
    assert "empty" in response.headers["location"]
    assert db.scalar(select(ManagedFile)) is None


# --------------------------------------------------------------------------- #
# Create
# --------------------------------------------------------------------------- #


def _create(client: TestClient, name: str, files: list[tuple[str, bytes]], **extra):
    return client.post(
        "/content/data-package/create",
        data={"name": name, **extra},
        files=[("files", (n, payload, "application/octet-stream")) for n, payload in files],
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )


def test_a_built_package_is_catalogued_as_one(client: TestClient, db, artifact_storage):
    response = _create(client, "Recon set", [("a.kml", b"<kml/>"), ("b.txt", b"notes")])
    assert response.status_code in (302, 303), response.text

    managed = db.scalar(select(ManagedFile))
    assert managed.is_data_package is True
    assert managed.name == "Recon set"


def test_what_create_produces_is_what_upload_would_accept(
    client: TestClient, db, artifact_storage
):
    """⚠️ The property that keeps the two paths from drifting.

    If Create could emit something Upload refuses, the console would contradict
    itself and the difference would only show up on a device.
    """
    _create(client, "Recon set", [("a.kml", b"<kml/>")])
    managed = db.scalar(select(ManagedFile))

    with artifact_storage.open(managed.artifact_sha256) as handle:
        package = mp.inspect(handle.read())

    assert package.name == "Recon set"
    assert [c.zip_entry for c in package.contents] == ["a.kml"]
    assert package.missing == ()


def test_a_package_with_no_name_is_refused(client: TestClient, db):
    response = _create(client, "   ", [("a.kml", b"x")])
    assert "name" in response.headers["location"]
    assert db.scalar(select(ManagedFile)) is None


def test_a_package_with_no_files_is_refused(client: TestClient, db):
    response = _create(client, "Empty", [])
    assert "at+least+one+file" in response.headers["location"].replace("%20", "+")
    assert db.scalar(select(ManagedFile)) is None


def test_an_empty_extra_file_row_is_ignored_not_an_error(client: TestClient, db):
    """A file input the operator added and left blank submits a zero-byte part.
    That is a row they changed their mind about, not a failure."""
    response = _create(client, "Recon", [("a.kml", b"<kml/>"), ("", b"")])

    assert response.status_code in (302, 303)
    assert db.scalar(select(ManagedFile)).is_data_package is True


def test_two_files_with_one_name_are_refused(client: TestClient, db):
    response = _create(client, "Clash", [("a.kml", b"1"), ("a.kml", b"2")])
    assert "more+than+once" in response.headers["location"].replace("%20", "+")
    assert db.scalar(select(ManagedFile)) is None


# --------------------------------------------------------------------------- #
# What the console then shows
# --------------------------------------------------------------------------- #


def test_the_content_page_shows_a_package_as_a_package(client: TestClient):
    _upload(client, _valid_package())
    body = client.get("/content").text

    assert "data package" in body
    assert "manifest name" in body
    assert "2 files" in body


def test_a_short_package_is_flagged_rather_than_refused(client: TestClient):
    """The manifest naming a file the zip lacks is legal — ATAK imports what is
    there — so it is a warning on the page, not a rejection at the door."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            mp.MANIFEST_NAME,
            '<?xml version="1.0"?><MissionPackageManifest version="2">'
            '<Configuration><Parameter name="uid" value="a"/>'
            '<Parameter name="name" value="Short"/></Configuration>'
            '<Contents><Content ignore="false" zipEntry="absent.kml"/></Contents>'
            "</MissionPackageManifest>",
        )
    _upload(client, buffer.getvalue())

    body = client.get("/content").text
    assert "absent.kml" in body
    assert "will import what is present" in body


def test_only_validated_packages_are_offered_to_a_policy(client: TestClient):
    """⚠️ The picker must not offer an arbitrary zip.

    ATAK would unpack one as a plain archive with none of the manifest's
    placement rules, and nothing in the console would say it had.
    """
    _upload(client, _valid_package("Real package"))
    client.post(
        "/content/upload",
        data={"name": "Just a zip"},
        files={"file": ("plain.zip", _plain_zip(), ZIP)},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )

    body = client.get("/policies/new").text
    picker = body[body.index("data-package-pick"):]
    picker = picker[: picker.index("</select>")]

    assert "Real package" in picker
    assert "Just a zip" not in picker


def test_the_editor_says_so_when_there_are_no_packages_yet(client: TestClient):
    body = client.get("/policies/new").text
    assert "No data packages in the library yet" in body


def test_the_data_package_subtopic_exists_beside_general_files(client: TestClient):
    body = client.get("/policies/new").text

    assert 'data-page="file_management:general-files"' in body
    assert 'data-page="file_management:atak-data-packages"' in body
    assert 'data-page="file_management:atak-dted"' in body


def test_dted_says_it_is_coming_rather_than_offering_a_form(client: TestClient):
    body = client.get("/policies/new").text
    panel = body[body.index('data-page-panel="file_management:atak-dted"'):]
    panel = panel[: panel.index("</section>")]

    assert "Not available yet." in panel
    assert "data_packages__file_id" not in panel


# --------------------------------------------------------------------------- #
# Upload and create from inside the policy editor (B4)
# --------------------------------------------------------------------------- #


def _policy_upload(client: TestClient, data: bytes, *, name: str = "", filename="pkg.zip"):
    return client.post(
        "/policies/data-package/upload",
        data={"name": name},
        files={"file": (filename, data, ZIP)},
        headers=ADMIN_HEADERS,
    )


def _policy_create(client: TestClient, name: str, files: list[tuple[str, bytes]]):
    return client.post(
        "/policies/data-package/create",
        data={"name": name},
        files=[("files", (n, p, "application/octet-stream")) for n, p in files],
        headers=ADMIN_HEADERS,
    )


def test_uploading_from_the_policy_returns_an_id_rather_than_redirecting(
    client: TestClient, db
):
    """⚠️ The policy is unsaved while this happens.

    A redirect would take every other category's changes with it, which is why
    W46's wallpaper upload answers the same way.
    """
    response = _policy_upload(client, _valid_package("Ops Layer"))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["name"] == "Ops Layer"
    assert db.scalar(select(ManagedFile)).id == uuid.UUID(body["id"])


def test_a_package_uploaded_from_a_policy_reaches_the_content_section(
    client: TestClient, db
):
    """The operator asked for these to be library content, unlike a wallpaper —
    a package is fleet content someone may reuse, not an asset private to one
    policy."""
    _policy_upload(client, _valid_package("Ops Layer"))

    managed = db.scalar(select(ManagedFile))
    assert managed.in_library is True
    assert managed.is_data_package is True
    assert "Ops Layer" in client.get("/content").text


def test_a_zip_without_a_manifest_is_refused_with_the_reason(client: TestClient, db):
    """⚠️ The check the operator asked to be sure of.

    The message is the validator's own: told only "rejected", an operator goes
    looking for a fault that may not be in their file.
    """
    response = _policy_upload(client, _plain_zip())

    assert response.status_code == 422
    assert "MANIFEST" in response.json()["error"]
    assert db.scalar(select(ManagedFile)) is None


def test_a_non_zip_is_refused_from_the_policy_too(client: TestClient, db):
    response = _policy_upload(client, b"not a zip", filename="notes.txt")

    assert response.status_code == 422
    assert "not a readable zip" in response.json()["error"]
    assert db.scalar(select(ManagedFile)) is None


def test_creating_from_the_policy_builds_and_returns_an_id(client: TestClient, db):
    response = _policy_create(client, "Recon set", [("a.kml", b"<kml/>")])

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Recon set"
    assert db.scalar(select(ManagedFile)).is_data_package is True


def test_a_package_built_in_the_policy_is_valid_to_the_same_validator(
    client: TestClient, db, artifact_storage
):
    """⚠️ Both routes must agree. Two definitions of "is this a data package"
    would mean the one an operator happened to hit decided whether their file was
    accepted."""
    _policy_create(client, "Recon set", [("a.kml", b"<kml/>")])
    managed = db.scalar(select(ManagedFile))

    with artifact_storage.open(managed.artifact_sha256) as handle:
        package = mp.inspect(handle.read())

    assert package.name == "Recon set"
    assert [c.zip_entry for c in package.contents] == ["a.kml"]


def test_creating_without_a_name_is_refused_with_a_reason(client: TestClient, db):
    response = _policy_create(client, "  ", [("a.kml", b"x")])

    assert response.status_code == 422
    assert "name" in response.json()["error"]
    assert db.scalar(select(ManagedFile)) is None


def test_creating_with_duplicate_names_is_refused(client: TestClient, db):
    response = _policy_create(client, "Clash", [("a.kml", b"1"), ("a.kml", b"2")])

    assert response.status_code == 422
    assert "more than once" in response.json()["error"]
    assert db.scalar(select(ManagedFile)) is None


def test_the_policy_page_offers_upload_and_create(client: TestClient):
    body = client.get("/policies/new").text
    panel = body[body.index('data-page-panel="file_management:atak-data-packages"'):]
    panel = panel[: panel.index("</section>")]

    assert "data-package-upload" in panel
    assert "data-package-create-open" in panel
    assert "MANIFEST/manifest.xml" in panel


def test_the_create_modal_is_on_the_page(client: TestClient):
    """⚠️ Mounted outside the sub-page panel and posted by script.

    HTML forbids a nested <form>, and this sits inside the policy's own — so the
    fields are collected with FormData rather than submitted.
    """
    body = client.get("/policies/new").text

    assert 'id="policy-package-create"' in body
    assert "data-ppkg-save" in body
    assert body.count('id="policy-package-create"') == 1


def test_the_upload_control_is_a_button_not_a_label(client: TestClient):
    """⚠️ `button.ghost` is the styled selector.

    A `<label class="ghost">` loses to `label`'s own rule — block, muted, 12.5px
    — so the first version rendered as grey clickable text that did not read as
    an action at all.
    """
    body = client.get("/policies/new").text
    panel = body[body.index('data-page-panel="file_management:atak-data-packages"'):]
    panel = panel[: panel.index("</section>")]

    assert '<button type="button" class="ghost" data-package-upload-open>' in panel
    assert 'class="ghost" style="margin:0; cursor:pointer"' not in panel


def test_the_check_modal_is_on_the_page(client: TestClient):
    body = client.get("/policies/new").text

    assert 'id="package-check"' in body
    assert body.count('id="package-check"') == 1
    for hook in ("data-check-progress", "data-check-error", "data-check-close"):
        assert hook in body, f"{hook} missing — the check modal would not render"


def test_the_upload_confirmation_says_what_was_accepted(client: TestClient):
    """Not merely that something was: the count is how an operator notices they
    uploaded the wrong package."""
    response = _policy_upload(client, _valid_package("Ops Layer"))

    assert response.json()["contents"] == 2


def test_a_created_package_reports_its_contents_too(client: TestClient):
    response = _policy_create(client, "Recon", [("a.kml", b"x"), ("b.txt", b"y")])
    assert response.json()["contents"] == 2
