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

"""Downloading a stored build back out of the library (W128).

⚠️ **A version is not always one file.** A split app is several — Chrome
arrives from Google Play as four — so the test that matters is the one proving
a multi-part build comes back whole. Serving only the base would hand over
something Android refuses with `INSTALL_FAILED_MISSING_SPLIT` while looking
like a perfectly good download.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from sqlalchemy import select

from fastapi.testclient import TestClient

from app.db.models import AppPackage, AppPackageVersion
from tests.apk_fixtures import build_apk, build_xapk
from tests.conftest import ADMIN_HEADERS


def _ingest(db, artifact_storage, data: bytes) -> AppPackageVersion:
    from app.services import packages as package_service

    result = package_service.ingest(db, artifact_storage, data)
    db.commit()
    return result.version


# --------------------------------------------------------------------------- #
# One file
# --------------------------------------------------------------------------- #


def test_a_single_apk_comes_back_byte_for_byte(client: TestClient, db, artifact_storage):
    apk = build_apk("org.example.one", 7)
    version = _ingest(db, artifact_storage, apk)

    response = client.get(f"/apps/versions/{version.id}/download", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.content == apk


def test_the_filename_names_the_package_and_build(client: TestClient, db, artifact_storage):
    """An operator ends up with several of these in a downloads folder."""
    version = _ingest(db, artifact_storage, build_apk("org.example.one", 7))

    response = client.get(f"/apps/versions/{version.id}/download", headers=ADMIN_HEADERS)

    assert 'filename="org.example.one-7.apk"' in response.headers["content-disposition"]


# --------------------------------------------------------------------------- #
# ⚠️ Several files
# --------------------------------------------------------------------------- #


def test_a_split_build_comes_back_whole(client: TestClient, db, artifact_storage):
    """⚠️ The test this feature exists for.

    Handing back only the base is the failure that looks like success: Android
    refuses it as `INSTALL_FAILED_MISSING_SPLIT`, and the file downloaded
    perfectly well.
    """
    xapk = build_xapk("org.example.split", 9, splits=("config.arm64_v8a", "config.en"))
    version = _ingest(db, artifact_storage, xapk)
    assert len(version.files) == 3

    response = client.get(f"/apps/versions/{version.id}/download", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    assert len(archive.namelist()) == 3
    assert 'filename="org.example.split-9.xapk"' in response.headers["content-disposition"]


def test_what_comes_out_can_be_uploaded_again(client: TestClient, db, artifact_storage):
    """⚠️ The round trip is the point of choosing the `.xapk` shape: it is what
    `inspect_bundle` already reads on the way in, so a downloaded build is not
    a dead end."""
    from app.services import packages as package_service

    xapk = build_xapk("org.example.split", 9, splits=("config.arm64_v8a",))
    version = _ingest(db, artifact_storage, xapk)

    downloaded = client.get(
        f"/apps/versions/{version.id}/download", headers=ADMIN_HEADERS
    ).content

    # ⚠️ Re-ingesting is *refused*, and that refusal is the proof: it names the
    # package and versionCode, which ingest can only know by opening the
    # archive and reading the manifest out of the base APK inside it. A
    # corrupt bundle fails with BadZipFile long before it gets here — which is
    # exactly how the truncating-BytesIO bug was caught.
    with pytest.raises(package_service.PackageError) as refused:
        package_service.ingest(db, artifact_storage, downloaded)
    db.rollback()

    assert "org.example.split" in str(refused.value)
    assert "9" in str(refused.value)


# --------------------------------------------------------------------------- #
# The console
# --------------------------------------------------------------------------- #


def test_each_app_row_offers_its_latest_build(client: TestClient, db, artifact_storage):
    version = _ingest(db, artifact_storage, build_apk("org.example.one", 7))

    body = client.get("/apps", headers=ADMIN_HEADERS).text

    assert f"/apps/versions/{version.id}/download" in body


def test_a_missing_version_is_a_404_not_a_500(client: TestClient):
    import uuid

    response = client.get(
        f"/apps/versions/{uuid.uuid4()}/download", headers=ADMIN_HEADERS
    )

    assert response.status_code == 404
