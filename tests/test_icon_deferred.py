"""The icon blob must not ride along on ordinary package queries (W53).

`desired_state` selects `AppPackage` on the **device check-in path**, once per
configured app per check-in. An eagerly-loaded `icon_data` would drag a blob
across that path that nothing on it reads — ours is 213 KB.
"""

from __future__ import annotations

import pathlib

import pytest
from sqlalchemy import select

from app.db.models import AppPackage
from tests.conftest import ADMIN_HEADERS

CHROME = pathlib.Path("Test Files/Google+Chrome_152.0.7977.82_APKPure.xapk")


@pytest.mark.skipif(not CHROME.exists(), reason="the Chrome XAPK is not in this checkout")
def test_selecting_a_package_does_not_load_the_icon_blob(client, db):
    client.post(
        "/api/v1/packages",
        files={"file": ("chrome.xapk", CHROME.read_bytes(), "application/octet-stream")},
        headers=ADMIN_HEADERS,
    )
    db.expire_all()

    package = db.scalar(select(AppPackage).where(AppPackage.package_name == "com.android.chrome"))

    # Deferred columns are absent from __dict__ until something touches them.
    assert "icon_data" not in package.__dict__, "the icon blob was loaded eagerly"
    # The presence flag *is* on the main row, which is what the list page reads.
    assert package.icon_media_type == "image/webp"

    assert package.icon_data  # explicit access still works
    assert "icon_data" in package.__dict__
