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

"""General Files in the policy editor (W91 B6).

Two concerns: uploading without leaving the policy, and keeping data packages
**out** of this picker — they have a sub-topic that fixes the destination ATAK
watches and delivers once, and offering them here would hand them a free-text
destination and a `persist` control instead.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.artifacts import mission_package as mp
from app.db.models import ManagedFile
from tests.conftest import ADMIN_HEADERS


def _upload_plain(client: TestClient, name: str = "Map source"):
    return client.post(
        "/policies/file/upload",
        data={"name": name},
        files={"file": ("source.xml", b"<map/>", "text/xml")},
        headers=ADMIN_HEADERS,
    )


def _upload_package(client: TestClient, name: str = "Ops Layer"):
    return client.post(
        "/content/data-package/upload",
        data={"name": name},
        files={"file": ("pkg.zip", mp.build(name, [("a.kml", b"<kml/>")]), "application/zip")},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )


def _general_files_panel(client: TestClient) -> str:
    body = client.get("/policies/new").text
    panel = body[body.index('data-page-panel="file_management:general-files"'):]
    return panel[: panel.index("</section>")]


# --------------------------------------------------------------------------- #
# Uploading from the policy
# --------------------------------------------------------------------------- #


def test_uploading_returns_an_id_rather_than_redirecting(client: TestClient, db):
    response = _upload_plain(client)

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Map source"
    assert db.scalar(select(ManagedFile)).id == uuid.UUID(response.json()["id"])


def test_an_uploaded_file_reaches_the_content_section(client: TestClient, db):
    """Unlike a wallpaper (W46, `in_library=False`): a file deployed to devices
    is fleet content, which is what the Content section is for."""
    _upload_plain(client)

    assert db.scalar(select(ManagedFile)).in_library is True
    assert "Map source" in client.get("/content").text


def test_an_empty_upload_is_refused_with_a_reason(client: TestClient, db):
    response = client.post(
        "/policies/file/upload",
        files={"file": ("empty.txt", b"", "text/plain")},
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 422
    assert "empty" in response.json()["error"]
    assert db.scalar(select(ManagedFile)) is None


def test_the_name_falls_back_to_the_filename(client: TestClient, db):
    client.post(
        "/policies/file/upload",
        data={"name": "   "},
        files={"file": ("dted-w125.zip", b"PK\x03\x04zip", "application/zip")},
        headers=ADMIN_HEADERS,
    )
    assert db.scalar(select(ManagedFile)).name == "dted-w125.zip"


# --------------------------------------------------------------------------- #
# ⚠️ Data packages are not offered here
# --------------------------------------------------------------------------- #


def test_a_data_package_is_absent_from_the_general_files_picker(client: TestClient):
    """⚠️ Offered here it would get a hand-typed destination and a `persist`
    control, and either one wrong is a package ATAK re-imports on every sync.

    The ATAK Data Packages sub-topic fixes both, which is the whole reason it
    exists as its own field.
    """
    _upload_package(client, "Ops Layer")
    _upload_plain(client, "Map source")

    panel = _general_files_panel(client)
    picker = panel[panel.index("<select"):]
    picker = picker[: picker.index("</select>")]

    assert "Map source" in picker
    assert "Ops Layer" not in picker


def test_a_package_already_on_a_policy_still_renders(client: TestClient, db):
    """⚠️ Filtering the list must not silently drop a file a policy already
    places. An older policy that put a package through General Files stays
    visible and editable rather than losing its selection on the next save.
    """
    _upload_package(client, "Legacy package")
    package = db.scalar(select(ManagedFile))

    created = client.post(
        "/api/v1/profiles",
        json={
            "name": "Legacy",
            "sections": {
                "file_management": {
                    "entries": [{"file_id": str(package.id), "dest_path": "/sdcard/atak"}]
                }
            },
        },
        headers=ADMIN_HEADERS,
    )
    assert created.status_code == 201, created.text

    body = client.get(f"/profiles/{created.json()['id']}").text
    panel = body[body.index('data-page-panel="file_management:general-files"'):]
    panel = panel[: panel.index("</section>")]

    assert "Legacy package" in panel
    assert "selected" in panel


def test_the_section_says_where_data_packages_belong(client: TestClient):
    """A picker that silently omits something teaches nothing. The absence needs
    to come with the reason and the place to go instead."""
    panel = _general_files_panel(client)

    assert "ATAK data packages do not belong here" in panel
    assert "ATAK Data Packages" in panel


def test_the_section_offers_an_upload(client: TestClient):
    panel = _general_files_panel(client)

    assert "data-file-upload-open" in panel
    assert "data-file-upload" in panel


def test_the_destination_field_has_no_placeholder(client: TestClient):
    """⚠️ A placeholder reads as a value the field already holds.

    An operator leaves it and saves; the spec then refuses the entry for having
    no destination. The guidance belongs in a tooltip, where it cannot be
    mistaken for content.
    """
    panel = _general_files_panel(client)

    assert 'placeholder="/sdcard/atak/imagery"' not in panel
    assert "Directory on the device" in panel


def test_the_destination_tooltip_carries_the_absolute_path_trap(client: TestClient):
    """`/atak/imagery` is how ATAK's own docs write it, and it resolves from the
    filesystem root where nothing is writable — the spec rejects it, so the hint
    should say why before someone types it."""
    panel = _general_files_panel(client)

    assert "/sdcard" in panel
    assert "filesystem root" in panel


# --------------------------------------------------------------------------- #
# ⚠️ A data package is refused, not merely discouraged
# --------------------------------------------------------------------------- #


def test_a_data_package_is_refused_by_the_general_upload(client: TestClient, db):
    """⚠️ The failure this prevents is total silence.

    Accepted as an ordinary file, a package goes wherever the destination says —
    where ATAK is not watching. No import, no error, nothing in any log. The
    steering note was not enough on its own: the operator who needs it is the one
    who did not read it.
    """
    response = client.post(
        "/policies/file/upload",
        files={"file": ("pkg.zip", mp.build("Ops", [("a.kml", b"<kml/>")]), "application/zip")},
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 422
    error = response.json()["error"]
    assert "MANIFEST/manifest.xml" in error
    assert "ATAK Data Packages" in error
    assert db.scalar(select(ManagedFile)) is None


def test_a_package_with_a_broken_manifest_is_refused_here_too(client: TestClient, db):
    """⚠️ ATAK's own test is a suffix match — `HasManifest` never parses the file.

    So a zip with a malformed manifest is still a data package in ATAK's eyes,
    and it was still built as one. Refusing it here sends the operator to the
    tool that can say what is actually wrong with it; this route could only say
    "accepted".
    """
    import io as _io
    import zipfile as _zipfile

    buffer = _io.BytesIO()
    with _zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("mydata/" + mp.MANIFEST_NAME, "<not even xml")

    response = client.post(
        "/policies/file/upload",
        files={"file": ("broken.zip", buffer.getvalue(), "application/zip")},
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 422
    assert db.scalar(select(ManagedFile)) is None


def test_an_ordinary_zip_is_still_accepted(client: TestClient, db):
    """The refusal keys on the manifest, not on being a zip. A DTED archive or a
    bundle of imagery is exactly what this section is for."""
    import io as _io
    import zipfile as _zipfile

    buffer = _io.BytesIO()
    with _zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("w125/n32.dt2", b"terrain")

    response = client.post(
        "/policies/file/upload",
        data={"name": "DTED w125"},
        files={"file": ("dted.zip", buffer.getvalue(), "application/zip")},
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200, response.text
    assert db.scalar(select(ManagedFile)).name == "DTED w125"


def test_the_section_says_a_package_will_be_refused(client: TestClient):
    panel = _general_files_panel(client)
    assert "refused" in panel
