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

"""How a data package reaches a device (W91, chunk B3).

⚠️ **There is no new delivery path, and that is the design.** A data package
resolves into an ordinary file entry carrying the settings that make it one —
the same move ATAK Config makes into `app_configs` (D92). The agent's existing
reconcile carries it unchanged, so nothing here needs the device to have learned
a new contract.

The settings are not offered to the operator, because every one of them has
exactly one correct value and getting any of them wrong is a repeated import.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from app.artifacts import mission_package as mp
from app.db.models import ManagedFile
from app.services import files as file_service
from tests.conftest import ADMIN_HEADERS


def _upload_package(client, name: str = "Ops Layer") -> str:
    response = client.post(
        "/content/data-package/upload",
        data={"name": name},
        files={"file": ("pkg.zip", mp.build(name, [("a.kml", b"<kml/>")]), "application/zip")},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )
    assert response.status_code in (302, 303), response.text
    return name


def _resolve(db, file_id: uuid.UUID, **overrides) -> dict:
    spec = {"data_packages": [{"file_id": str(file_id), **overrides}]}
    return file_service.resolve_files(db, {"FILES": spec})


def _entry(db, client, **overrides) -> dict:
    _upload_package(client)
    managed = db.scalar(select(ManagedFile))
    resolved = _resolve(db, managed.id, **overrides)
    assert len(resolved["required"]) == 1
    return resolved["required"][0]


# --------------------------------------------------------------------------- #
# The settings that make it a package
# --------------------------------------------------------------------------- #


def test_a_package_goes_to_the_directory_atak_watches(client, db):
    entry = _entry(db, client)

    assert entry["dest_path"] == "/sdcard/atak/tools/datapackage"
    assert entry["dest_path"] == file_service.DATA_PACKAGE_DEST


def test_the_destination_is_not_the_incoming_folder(client, db):
    """⚠️ `incoming/` is `// no watch` and swept by `DirectoryCleanup` after two
    hours, so a package left there is deleted having never been imported. The
    request originally named it; the source disagreed and won."""
    assert "incoming" not in _entry(db, client)["dest_path"]


def test_a_package_is_never_re_pushed(client, db):
    """⚠️ The single most important value here.

    `persist: false` makes the reconciler skip a package whose applied-content
    hash it already has — gone from disk or not. ATAK consumes the zip, so
    absence is success; re-pushing would make ATAK re-import on every sync.
    """
    assert _entry(db, client)["persist"] is False


def test_a_package_is_required_not_offered(client, db):
    """It is policy, not a marketplace item — the user does not opt in."""
    _upload_package(client)
    managed = db.scalar(select(ManagedFile))
    resolved = _resolve(db, managed.id)

    assert len(resolved["required"]) == 1
    assert resolved["available"] == []


def test_a_package_is_not_extracted_by_the_agent(client, db):
    """ATAK unpacks it, reading the manifest to decide where each file belongs.
    Unpacking it ourselves would scatter the contents and skip every rule the
    manifest carries."""
    assert _entry(db, client)["extract"] is False


def test_the_agent_is_told_it_is_a_package(client, db):
    """Only so the card can be honest — the delivery decision is `persist`, and
    nothing reads this flag to make it."""
    assert _entry(db, client)["data_package"] is True


def test_an_ordinary_file_is_not_flagged_as_a_package(client, db):
    _upload_package(client)
    managed = db.scalar(select(ManagedFile))
    resolved = file_service.resolve_files(
        db,
        {"FILES": {"entries": [{"file_id": str(managed.id), "dest_path": "/sdcard/atak"}]}},
    )
    assert resolved["required"][0]["data_package"] is False


def test_a_title_the_operator_set_is_carried(client, db):
    assert _entry(db, client, title="North sector")["title"] == "North sector"


def test_packages_and_ordinary_files_travel_together(client, db):
    """A policy may do both, and they must not shadow one another."""
    _upload_package(client, "Package")
    package = db.scalar(select(ManagedFile))
    client.post(
        "/content/upload",
        data={"name": "Plain file"},
        files={"file": ("a.txt", b"hello", "text/plain")},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )
    plain = db.scalar(select(ManagedFile).where(ManagedFile.name == "Plain file"))

    resolved = file_service.resolve_files(
        db,
        {
            "FILES": {
                "entries": [{"file_id": str(plain.id), "dest_path": "/sdcard/atak"}],
                "data_packages": [{"file_id": str(package.id)}],
            }
        },
    )

    by_name = {e["name"]: e for e in resolved["required"]}
    assert by_name["Package"]["data_package"] is True
    assert by_name["Package"]["persist"] is False
    assert by_name["Plain file"]["data_package"] is False
    assert by_name["Plain file"]["dest_path"] == "/sdcard/atak"


def test_a_deleted_package_is_reported_rather_than_dropped(client, db):
    """Same rule as an ordinary file: a broken policy should be visible on the
    device page, not silently do nothing."""
    resolved = _resolve(db, uuid.uuid4())

    assert resolved["required"][0]["available"] is False
    assert resolved["required"][0]["data_package"] is True


def test_a_policy_with_neither_resolves_to_nothing(db):
    assert file_service.resolve_files(db, {"FILES": {}}) == {"required": [], "available": []}
