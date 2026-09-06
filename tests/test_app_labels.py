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

"""An unlabelled upload should be called what the device calls it (W51).

Chrome went into the library as `com.android.chrome`, which is the package
identity rather than the app's name. There are three shapes here and they resolve
differently, so all three are pinned against real builds:

* an **XAPK** states its name in `manifest.json` — Chrome, Butterfly, Messages;
* a **plain APK** only when its manifest inlines `android:label` — Survey123;
* otherwise the label is a resource reference, resolved through `resources.arsc`
  taking the default locale — Outlook, Gboard.

The third case was a *gap* when this file was written: W51 had no resource-table
reader, so those apps fell back to their package name. W53 built one, and these
tests were updated rather than deleted — the behaviour they pinned was correct
for the code that existed, and the record of it changing is worth keeping.
"""

from __future__ import annotations

import pathlib

import pytest

from app.artifacts.bundles import inspect
from tests.conftest import ADMIN_HEADERS

CHROME = pathlib.Path("Test Files/Google+Chrome_152.0.7977.82_APKPure.xapk")
BUTTERFLY = pathlib.Path("Test Files/butterfly-iq-2.49.0.xapk")
SURVEY123 = pathlib.Path("Test Files/ArcGIS+Survey123_3.25.32_APKPure.apk")
OUTLOOK = pathlib.Path("Test Files/Microsoft+Outlook_5.2606.0_APKPure.apk")
GBOARD = pathlib.Path(
    "Test Files/Gboard+-+the+Google+Keyboard_18.1.3.962075747-beta-arm64-v8a_APKPure.apk"
)


@pytest.mark.skipif(not CHROME.exists(), reason="the Chrome XAPK is not in this checkout")
def test_an_xapk_is_named_from_its_container_manifest():
    """The reported case. `manifest.json` carries the display name outright."""
    assert inspect(CHROME.read_bytes()).label == "Chrome"


@pytest.mark.skipif(not BUTTERFLY.exists(), reason="the Butterfly XAPK is not in this checkout")
def test_a_container_name_can_differ_from_anything_in_the_package_id():
    """`com.butterflynetinc.helios` would tell an operator nothing — the app is
    called Butterfly iQ, and nothing in the package id says so."""
    bundle = inspect(BUTTERFLY.read_bytes())

    assert bundle.package_name == "com.butterflynetinc.helios"
    assert bundle.label == "Butterfly iQ"


@pytest.mark.skipif(not SURVEY123.exists(), reason="the Survey123 APK is not in this checkout")
def test_a_plain_apk_is_named_from_a_literal_label():
    assert inspect(SURVEY123.read_bytes()).label == "Survey123"


@pytest.mark.skipif(not OUTLOOK.exists(), reason="the Outlook APK is not in this checkout")
def test_a_referenced_label_is_resolved_through_the_resource_table():
    """Outlook's label is `@0x7f15038b`, and W53 taught us to look it up.

    This test used to assert `label is None` — correct then, because nothing here
    could read `resources.arsc`. It now reads it, so the *right* answer changed.
    The guarantee the test existed to protect has not: a resource id must never
    reach an operator.
    """
    bundle = inspect(OUTLOOK.read_bytes())

    assert bundle.label == "Outlook"
    assert not (bundle.label or "").startswith("@0x")


@pytest.mark.skipif(not GBOARD.exists(), reason="the Gboard APK is not in this checkout")
def test_the_other_app_that_could_not_be_named_now_can():
    assert inspect(GBOARD.read_bytes()).label == "Gboard"


@pytest.mark.skipif(not OUTLOOK.exists(), reason="the Outlook APK is not in this checkout")
def test_a_label_is_taken_from_the_default_locale():
    """Outlook ships its name in **62** languages.

    Without preferring the default configuration, "the label" is whichever
    translation the resource table happens to list first — stable per build, and
    silently wrong for anyone reading the console.
    """
    import zipfile

    from app.artifacts import arsc

    with zipfile.ZipFile(OUTLOOK) as archive:
        table = arsc.parse(archive.read("resources.arsc"))

    values = table.values(0x7F15038B)

    assert len({v.language for v in values}) > 10
    assert values[0].is_default_locale


@pytest.mark.skipif(not CHROME.exists(), reason="the Chrome XAPK is not in this checkout")
def test_an_unlabelled_upload_takes_the_apps_own_name(client, db):
    """End to end: upload with no label and the library shows the app's name."""
    from app.db.models import AppPackage
    from sqlalchemy import select

    response = client.post(
        "/api/v1/packages",
        files={"file": ("chrome.xapk", CHROME.read_bytes(), "application/octet-stream")},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 201, response.text

    package = db.scalar(select(AppPackage).where(AppPackage.package_name == "com.android.chrome"))
    assert package.label == "Chrome"


@pytest.mark.skipif(not CHROME.exists(), reason="the Chrome XAPK is not in this checkout")
def test_an_operators_own_label_still_wins(client, db):
    """Deriving a name must never override a deliberate choice."""
    from app.db.models import AppPackage
    from sqlalchemy import select

    response = client.post(
        "/api/v1/packages",
        files={"file": ("chrome.xapk", CHROME.read_bytes(), "application/octet-stream")},
        data={"label": "Browser (locked build)"},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 201, response.text

    package = db.scalar(select(AppPackage).where(AppPackage.package_name == "com.android.chrome"))
    assert package.label == "Browser (locked build)"
