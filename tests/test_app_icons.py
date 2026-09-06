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

"""Launcher icons extracted from real APKs (W53).

Pinned against six builds spanning every shape the resolver has to survive:
shrunk and unshrunk resource tables, adaptive and legacy icons, XAPK containers
and bare APKs — and two apps whose icons are **vector drawables**, which must
yield nothing rather than something wrong.

The extension trap is the reason this file exists. Chrome's icon layers are
`res/ima` and `res/QtC`, with no extension at all, because resource shrinking
renames them; an earlier crawler filtered on `.png`/`.webp`, found nothing, and
concluded the icons were vectors. They were WEBP the whole time.
"""

from __future__ import annotations

import io
import pathlib
import zipfile

import pytest

from app.artifacts import arsc
from app.artifacts.app_icon import extract_icon
from app.artifacts.bundles import inspect
from tests.conftest import ADMIN_HEADERS

TEST_FILES = pathlib.Path("Test Files")

CHROME = TEST_FILES / "Google+Chrome_152.0.7977.82_APKPure.xapk"
MESSAGES = TEST_FILES / "Google+Messages_messages.android_20260827_01_RC02.phone_dynamic_APKPure.xapk"
BUTTERFLY = TEST_FILES / "butterfly-iq-2.49.0.xapk"
SURVEY123 = TEST_FILES / "ArcGIS+Survey123_3.25.32_APKPure.apk"
OUTLOOK = TEST_FILES / "Microsoft+Outlook_5.2606.0_APKPure.apk"
ATAK = TEST_FILES / "ATAK-5.8.0.4-174b425-civSmall-release.apk"

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _needs(path: pathlib.Path):
    return pytest.mark.skipif(not path.exists(), reason=f"{path.name} is not in this checkout")


def _icon(path: pathlib.Path):
    return inspect(path.read_bytes()).icon


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #


@_needs(CHROME)
def test_a_shrunk_adaptive_icon_resolves_to_its_raster_foreground():
    """The case that was wrongly declared impossible.

    Chrome's icon is adaptive XML whose foreground is a WEBP file named `res/ima`
    — no extension, because resource shrinking took it.
    """
    icon = _icon(CHROME)

    assert icon is not None
    assert icon.media_type == "image/webp"
    assert icon.adaptive is True
    assert len(icon.data) > 1000


@_needs(MESSAGES)
def test_an_adaptive_icon_may_have_a_png_foreground():
    icon = _icon(MESSAGES)

    assert icon is not None
    assert icon.media_type == "image/png"
    assert icon.adaptive is True
    assert icon.data.startswith(PNG_MAGIC)


@_needs(SURVEY123)
def test_a_legacy_icon_is_taken_whole():
    """Survey123's icon is a finished raster, not a layer on a 108dp canvas.

    Cropping it would eat the artwork — hence `adaptive` is False and the caller
    must not apply the ×1.5 centre crop.
    """
    icon = _icon(SURVEY123)

    assert icon is not None
    assert icon.adaptive is False
    assert icon.visible_fraction == 1.0


@_needs(ATAK)
def test_the_agents_own_ecosystem_resolves_too():
    icon = _icon(ATAK)

    assert icon is not None
    assert icon.media_type == "image/png"


# --------------------------------------------------------------------------- #
# Honest refusals
# --------------------------------------------------------------------------- #


@_needs(BUTTERFLY)
def test_a_vector_foreground_yields_nothing_rather_than_the_background():
    """Butterfly's foreground is a `<vector>` and its background a flat colour.

    Returning the background would be an icon-shaped blank — present, plausible,
    and useless. None sends the caller to its placeholder instead.
    """
    assert _icon(BUTTERFLY) is None


@_needs(OUTLOOK)
def test_a_deeply_nested_vector_foreground_also_yields_nothing():
    """`adaptive-icon → foreground → inset → layer-list → item → <vector>`.

    Depth is not the obstacle — the resolver walks all of it. The leaf is a vector
    drawable, and rasterising one needs Android's drawable pipeline.
    """
    assert _icon(OUTLOOK) is None


@_needs(OUTLOOK)
def test_a_refusal_is_not_an_error():
    """An app with no extractable icon must still inspect cleanly."""
    bundle = inspect(OUTLOOK.read_bytes())

    assert bundle.package_name
    assert bundle.icon is None


# --------------------------------------------------------------------------- #
# The resource table underneath
# --------------------------------------------------------------------------- #


@_needs(CHROME)
def test_the_resource_table_reads_a_shrunk_package():
    with zipfile.ZipFile(CHROME) as container:
        base = container.read("com.android.chrome.apk")
    with zipfile.ZipFile(io.BytesIO(base)) as apk:
        table = arsc.parse(apk.read("resources.arsc"))

    assert len(table) > 1000


@_needs(SURVEY123)
def test_a_string_resource_resolves_through_the_table():
    """The lookup that unlocks display names for apps whose label is a reference."""
    with zipfile.ZipFile(SURVEY123) as apk:
        table = arsc.parse(apk.read("resources.arsc"))

    resolved = [table.string(rid) for rid in list(table._entries)[:200]]  # noqa: SLF001

    assert any(isinstance(value, str) and value for value in resolved)


def test_a_buffer_that_is_not_a_resource_table_is_rejected():
    with pytest.raises(arsc.ArscError):
        arsc.parse(b"not a resource table at all")


def test_an_empty_buffer_is_rejected():
    with pytest.raises(arsc.ArscError):
        arsc.parse(b"")


# --------------------------------------------------------------------------- #
# Persistence and serving
# --------------------------------------------------------------------------- #


@_needs(CHROME)
def test_an_upload_stores_the_icon(client, db):
    """End to end: upload, and the row carries the bytes the device would draw."""
    from sqlalchemy import select

    from app.db.models import AppPackage

    response = client.post(
        "/api/v1/packages",
        files={"file": ("chrome.xapk", CHROME.read_bytes(), "application/octet-stream")},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 201, response.text

    package = db.scalar(select(AppPackage).where(AppPackage.package_name == "com.android.chrome"))

    assert package.icon_media_type == "image/webp"
    assert package.icon_adaptive is True
    assert package.icon_data


@_needs(CHROME)
def test_the_icon_endpoint_serves_the_stored_bytes(client, db):
    from sqlalchemy import select

    from app.db.models import AppPackage

    client.post(
        "/api/v1/packages",
        files={"file": ("chrome.xapk", CHROME.read_bytes(), "application/octet-stream")},
        headers=ADMIN_HEADERS,
    )
    package = db.scalar(select(AppPackage).where(AppPackage.package_name == "com.android.chrome"))

    response = client.get(f"/api/v1/packages/{package.id}/icon", headers=ADMIN_HEADERS)

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/webp"
    assert response.content == package.icon_data
    # A shared cache must not hold a response from behind the admin guard.
    assert "private" in response.headers["cache-control"]


@_needs(OUTLOOK)
def test_an_app_without_an_icon_returns_404_rather_than_an_empty_body(client, db):
    """The page falls back to a monogram, so the honest answer is "no icon" —
    not zero bytes with an image content type, which renders as a broken image."""
    from sqlalchemy import select

    from app.db.models import AppPackage

    client.post(
        "/api/v1/packages",
        files={"file": ("outlook.apk", OUTLOOK.read_bytes(), "application/octet-stream")},
        headers=ADMIN_HEADERS,
    )
    package = db.scalar(
        select(AppPackage).where(AppPackage.package_name == "com.microsoft.office.outlook")
    )
    assert package.icon_data is None

    response = client.get(f"/api/v1/packages/{package.id}/icon", headers=ADMIN_HEADERS)

    assert response.status_code == 404


@_needs(CHROME)
@_needs(OUTLOOK)
def test_a_build_with_an_unreadable_icon_does_not_erase_a_good_one(db):
    """Re-uploading must not blank an icon that was already found.

    `_apply_icon` returning early on None is the whole guard, and without it any
    app that later ships a vector icon would lose the one it had.
    """
    from app.artifacts.bundles import inspect
    from app.db.models import AppPackage
    from app.services.packages import _apply_icon

    package = AppPackage(package_name="com.example.app")
    _apply_icon(package, inspect(CHROME.read_bytes()))
    assert package.icon_data

    _apply_icon(package, inspect(OUTLOOK.read_bytes()))  # yields no icon

    assert package.icon_data, "an unreadable icon blanked a good one"


# --------------------------------------------------------------------------- #
# The backfill is actually wired
# --------------------------------------------------------------------------- #


@_needs(SURVEY123)
def test_startup_backfills_names_and_icons(client, db):
    """The defect this pins is *absence of a caller*, not a wrong result.

    `backfill_labels` was written for W51 and never invoked from anywhere — so a
    library uploaded before names could be read stayed named by its package id
    forever, and nothing failed to say so. A test that calls the function
    directly would have passed throughout. This one starts the app.
    """
    import threading

    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.db.models import AppPackage
    from app.main import app

    client.post(
        "/api/v1/packages",
        files={"file": ("survey.apk", SURVEY123.read_bytes(), "application/octet-stream")},
        headers=ADMIN_HEADERS,
    )
    package = db.scalar(select(AppPackage).where(AppPackage.package_name == "com.esri.survey123"))
    assert package.icon_data, "precondition: the upload stored an icon"

    # Wind it back to how a pre-W51/W53 row looks on disk.
    package.label = None
    package.icon_data = None
    package.icon_media_type = None
    db.commit()

    # Start the app, rather than calling the backfill — the bug was that *nothing*
    # called it, so a test that calls it itself would have passed all along. The
    # overrides installed by the `client` fixture are still in place, so this
    # reaches the test database.
    with TestClient(app):
        started = [t for t in threading.enumerate() if t.name == "catalog-backfill"]
        assert started, "starting the app did not start the catalog backfill"
        for thread in started:
            thread.join(timeout=60)

    db.expire_all()

    restored = db.scalar(select(AppPackage).where(AppPackage.package_name == "com.esri.survey123"))
    assert restored.label == "Survey123"
    assert restored.icon_data


@_needs(OUTLOOK)
def test_the_backfill_converges_for_an_app_whose_icon_cannot_be_extracted(
    client, db, artifact_storage
):
    """Outlook's icon is a vector drawable, so `icon_media_type` stays NULL — and
    the backfill selects on exactly that.

    Without a record of the attempt the pass never converges: the 172 MB base APK
    is re-read and its 39.6 MB resource table re-parsed at every server start,
    forever, to produce nothing. Measured at 1.4s and 356 MB of heap per attempt.
    """
    from sqlalchemy import select

    from app.db.models import AppPackage
    from app.services.packages import backfill_labels

    client.post(
        "/api/v1/packages",
        files={"file": ("outlook.apk", OUTLOOK.read_bytes(), "application/octet-stream")},
        headers=ADMIN_HEADERS,
    )
    package = db.scalar(
        select(AppPackage).where(AppPackage.package_name == "com.microsoft.office.outlook")
    )
    assert package.icon_media_type is None, "precondition: no icon is extractable"

    # Wind back to a pre-W53 row: never inspected.
    package.icon_source_version_id = None
    db.commit()

    backfill_labels(db, artifact_storage)
    db.commit()

    package = db.scalar(
        select(AppPackage).where(AppPackage.package_name == "com.microsoft.office.outlook")
    )
    assert package.icon_source_version_id is not None, "the attempt was not recorded"
    assert package.icon_media_type is None, "an icon was invented for a vector-only app"

    # The second pass must not re-read the APK. Timing is the observable: a real
    # re-read of this fixture cannot finish in a few milliseconds.
    import time

    started = time.perf_counter()
    backfill_labels(db, artifact_storage)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.3, f"the backfill re-read a 172 MB APK it had already tried ({elapsed:.2f}s)"
