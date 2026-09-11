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


def test_a_held_version_is_named_and_not_flagged_as_a_fault(
    client: TestClient, db, artifact_storage
):
    """⚠️ The bug the operator hit, twice over.

    `none published` alone is true of an empty package and of one holding a
    freshly imported build, and it was rendered in warning orange — so a
    successful import was reported as a fault. Imports never publish by design
    (`repo_import`: publishing aims every device asking for "latest" at a
    build), which makes "held" the normal outcome, not an exception.
    """
    package = _held(db, artifact_storage)

    body = client.get("/apps", headers=ADMIN_HEADERS).text
    row = body[body.index(package.package_name) :][:1200]

    assert "held" in row and "42" in row
    assert "pill warn" not in row


def test_a_package_with_nothing_in_it_is_still_a_warning(
    client: TestClient, db, artifact_storage
):
    """⚠️ The distinction the fix rests on. Softening *both* cases would hide a
    package that really has nothing to install."""
    from app.db.models import AppPackage

    package = AppPackage(package_name="org.example.empty", label="Empty")
    db.add(package)
    db.commit()

    body = client.get("/apps", headers=ADMIN_HEADERS).text
    row = body[body.index("org.example.empty") :][:1200]

    assert "nothing uploaded" in row


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


# --------------------------------------------------------------------------- #
# ⚠️ A source that cannot enumerate versions should not offer a picker (W125)
# --------------------------------------------------------------------------- #


def test_google_play_search_says_it_cannot_pick_a_version(client: TestClient):
    """The flag the client needs, sent explicitly rather than inferred.

    Play returns one placeholder with no code, name or architecture, so a
    version picker there asks the operator to choose from a single blank row.
    """
    routes = pathlib.Path("app/web/routes.py").read_text(encoding="utf-8")

    play = routes[routes.index('"source_label": "Google Play"') :][:800]
    assert '"picks_version": False' in play


def test_the_other_sources_declare_that_they_can(client: TestClient):
    """⚠️ Stated, not omitted. If the key were absent for enumerating sources,
    a new one would silently lose its version picker the day it was added."""
    routes = pathlib.Path("app/web/routes.py").read_text(encoding="utf-8")

    assert routes.count('"picks_version"') == 2
    assert '"picks_version": True' in routes


def test_the_search_row_imports_directly_when_it_cannot_pick(client: TestClient):
    js = pathlib.Path("app/web/static/atlas.js").read_text(encoding="utf-8")

    assert "app.picks_version === false" in js
    assert "importLatest(app)" in js


def test_the_direct_import_still_asks_the_server_for_the_version(client: TestClient):
    """⚠️ It does not fabricate one. The placeholder carries the download URL
    the import endpoint needs, and inventing that on the client would put a
    server-side URL scheme into the browser."""
    js = pathlib.Path("app/web/static/atlas.js").read_text(encoding="utf-8")

    body = js[js.index("function importLatest(") :]
    body = body[: body.index("function openVersions(")]

    assert "/apps/repo/versions?source=" in body
    assert "startImport(app, versions[0])" in body


# --------------------------------------------------------------------------- #
# ⚠️ One import, one success message (W126)
# --------------------------------------------------------------------------- #


def _js() -> str:
    return pathlib.Path("app/web/static/atlas.js").read_text(encoding="utf-8")


def test_both_importers_announce_success_the_same_way():
    """⚠️ The same outcome looked like two different things.

    The tak.gov plugin importer finishes with "Imported" and "<pkg> is in the
    local library". The repo/Play one announced the *hold* instead, so an
    operator coming from the Play tab saw a caveat where the plugin tab showed
    a confirmation — for identical behaviour, since every import is held.
    """
    js = _js()

    assert js.count('" is in the local library."') == 2
    assert js.count('"Imported"') >= 2


def test_the_hold_is_explained_where_it_is_acted_on_not_in_the_receipt():
    """Holding is the normal result of every import, so it belongs on the page
    where an operator publishes — which W125 made say so — rather than in the
    line confirming the download worked."""
    js = _js()
    apps = pathlib.Path("app/web/templates/apps.html").read_text(encoding="utf-8")

    assert "imported and <strong>held</strong>" not in js
    assert "held — publish to deploy" in apps


def test_the_progress_bar_survives_the_success():
    """⚠️ The plugin importer leaves the bar full; this one replaced the whole
    body, so the bar vanished at the moment it should have read 100%."""
    js = _js()

    watch = js[js.index("function watch(jobId)") :]
    watch = watch[: watch.index("}, 1000);")]

    assert 'bar.style.width = "100%"' in watch
    assert "modalBody.innerHTML" not in watch.split('job.state === "failed"')[0]


def test_the_app_name_is_set_as_text_not_interpolated():
    """⚠️ It arrives from a third-party search result. Interpolating it into
    innerHTML would put whatever the source called the app into the DOM."""
    js = _js()

    start = js.index("function startImport(")
    body = js[start : js.index("function watch(", start)]

    assert '"<p data-repo-headline></p>"' in body
    assert "headline]\").textContent" in body or "textContent =" in body
