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

"""Uploading a wallpaper from inside the policy editor (W46).

The behaviour worth pinning is the boundary: such a file must be a perfectly
ordinary managed file to everything downstream — the resolver, the artifact store,
the device — while being absent from every listing that means "the Content
library". Getting half of that right is the bug: filter too little and wallpapers
turn up as deployable content, filter too much and a saved policy shows a uuid
where its picture's name should be.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.models import ManagedFile
from tests.conftest import ADMIN_HEADERS
from tests.test_wallpaper import PNG


def _upload(client: TestClient, name: str = "field.png") -> dict:
    response = client.post(
        "/policies/image",
        files={"file": (name, PNG, "image/png")},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_an_uploaded_image_comes_back_with_an_id(client: TestClient):
    body = _upload(client)
    assert body["id"]
    # Named from the filename without its extension, so the operator sees
    # "field" rather than a uuid wherever the policy summarises itself.
    assert body["name"] == "field"


def test_the_upload_is_a_real_managed_file(db, client: TestClient):
    """It has to be: `resolve_wallpaper` looks the id up as one, and that path is
    hardware-proven. The only difference is that it is not library content."""
    body = _upload(client)

    managed = db.get(ManagedFile, __import__("uuid").UUID(body["id"]))
    assert managed is not None
    assert managed.media_type == "image/png"
    assert managed.artifact_sha256  # content-addressed like any other upload
    assert managed.in_library is False


def test_it_does_not_appear_in_the_content_library(client: TestClient):
    body = _upload(client)

    listing = client.get("/api/v1/files", headers=ADMIN_HEADERS)
    assert listing.status_code == 200
    assert body["id"] not in [row["id"] for row in listing.json()]


def test_a_content_upload_still_appears(db, client: TestClient):
    """The filter must not swallow the library itself."""
    response = client.post(
        "/api/v1/files",
        files={"file": ("map.png", PNG, "image/png")},
        data={"name": "Map"},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 201, response.text
    uploaded = response.json()["id"]

    listing = client.get("/api/v1/files", headers=ADMIN_HEADERS)
    assert uploaded in [row["id"] for row in listing.json()]


def test_a_non_image_is_refused_here_rather_than_on_the_device(client: TestClient):
    """A wallpaper that is not an image fails on the device as a generic apply
    error with nothing to act on. Refuse it where the operator can see why."""
    response = client.post(
        "/policies/image",
        files={"file": ("notes.txt", b"not a picture", "text/plain")},
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 422
    assert "image" in response.json()["error"]


def test_an_empty_upload_is_refused(client: TestClient):
    response = client.post(
        "/policies/image",
        files={"file": ("empty.png", b"", "image/png")},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 422


def test_the_uploaded_image_resolves_for_a_device(db, client: TestClient):
    """The whole point: a policy-editor upload must reach a device exactly as a
    Content upload would."""
    from app.services import files as file_service

    body = _upload(client)
    resolved = file_service.resolve_wallpaper(
        db, {"WALLPAPER": {"tablet_file_id": body["id"]}}
    )

    assert resolved["tablet"]["available"] is True
    assert resolved["tablet"]["sha256"]
