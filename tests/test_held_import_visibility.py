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

"""A held import has to look imported (W124).

Operator imported Chrome from Google Play. It worked — four splits, version
`152.0.7977.82` — and the console said `none published`, which is *also* what a
package with nothing in it says. Nothing on the row distinguished "imported and
waiting" from "not there", so a successful import read as a failure.
"""

from __future__ import annotations

import inspect
import pathlib

from sqlalchemy import select

from fastapi.testclient import TestClient

from app.db.models import AppPackage
from tests.apk_fixtures import build_apk
from tests.conftest import ADMIN_HEADERS


def _held(db, artifact_storage, package: str = "org.example.held", code: int = 42):
    """Ingest a version and leave it unpublished, as a repo import does."""
    from app.services import packages as package_service

    # publish=False is the repo-import path: stored, eligible for nothing
    # until an operator publishes it.
    package_service.ingest(db, artifact_storage, build_apk(package, code), publish=False)
    db.commit()
    return db.scalar(select(AppPackage).where(AppPackage.package_name == package))


def test_a_held_version_is_named_on_the_apps_page(
    client: TestClient, db, artifact_storage
):
    """⚠️ The bug the operator hit. `none published` alone is true of an empty
    package and of one holding a freshly imported build."""
    package = _held(db, artifact_storage)

    body = client.get("/apps", headers=ADMIN_HEADERS).text
    row = body[body.index(package.package_name) :][:1200]

    assert "none published" in row
    assert "42" in row and "held" in row


def test_a_single_held_version_still_links_to_the_library(
    client: TestClient, db, artifact_storage
):
    """⚠️ The link was shown only when a package had **more than one** version,
    so the first import of anything had no way through to it at all."""
    package = _held(db, artifact_storage)

    body = client.get("/apps", headers=ADMIN_HEADERS).text

    assert f"?versions={package.id}" in body
    assert "1 version in the library" in body


# --------------------------------------------------------------------------- #
# ⚠️ Why the progress line said "null"
# --------------------------------------------------------------------------- #


def test_google_play_states_no_version_code_before_download():
    """The fact the console has to cope with, rather than a fault to fix.

    Play cannot enumerate versions: the source returns one placeholder and both
    the code and the name are read from the file once it arrives. Interpolating
    that placeholder is what produced *"Importing Google Chrome null…"*.
    """
    from app.services.app_sources import googleplay

    source = inspect.getsource(googleplay.GooglePlaySource.versions)

    assert "version_code=None" in source
    assert "version_name=LATEST" in source


def test_the_import_progress_does_not_interpolate_a_missing_version():
    """⚠️ Guards the specific rendering, since the placeholder above is
    permanent — any future source without a version code would print `null`
    again through the same line."""
    js = pathlib.Path("app/web/static/atlas.js").read_text(encoding="utf-8")

    body = js[js.index("function startImport(") :]
    body = body[: body.index("\n  function ")]

    assert '"Importing " + app.name + " " + version.version_code' not in body
    assert "version.version_code || version.version_name" in body
