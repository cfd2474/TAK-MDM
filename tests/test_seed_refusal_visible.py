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

"""A refused APK is visible in the console, not only in `docker logs` (W188).

⚠️ **Found on a real deployment, not by reading code.** ATLAS was installed,
the agent signing key changed between the install and the update, and the
seeder correctly refused the new APKs — Android would reject an update signed
by a different key. Correct behaviour, and the operator could not have known:
the console reported the old agent as current, showed no error, and every
device would have gone on being offered a build the release no longer ships.

The refusal is **re-derived on each render** rather than recorded when the
seeder ran. A stored warning outlives its cause — fix the problem and the
message stays until something clears it, which is its own kind of lie.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.services import packages as package_service
from tests.conftest import ADMIN_HEADERS

AGENT_APK = Path("dist/atlas-agent.apk")


def _as_if_the_key_changed(db):
    """Put the library in the state a signing-key change actually leaves.

    ⚠️ The first version of this helper only rewrote the stored signature and
    asserted a refusal. It got none, correctly: the *version* row from the
    upload was still there, and a version already in the library is not refused
    no matter what the package-level signature says. The real state is a package
    known under the **old** key whose **new** versionCode was never loaded — so
    the version has to go too.
    """
    from app.db.models import AppPackage, AppPackageVersion
    from sqlalchemy import delete, select

    stored = db.scalar(
        select(AppPackage).where(AppPackage.package_name == "com.taksolutions.atlasmdm")
    )
    db.execute(delete(AppPackageVersion).where(AppPackageVersion.package_id == stored.id))
    stored.signature_sha256 = "0" * 64
    db.commit()


@pytest.fixture
def seed(tmp_path, settings):
    """A seed directory the test controls, pointed at by settings."""
    directory = tmp_path / "seed"
    directory.mkdir()
    settings.seed_dir = directory
    return directory


def test_nothing_is_reported_when_the_library_matches(client: TestClient, db, seed):
    """The normal case must be silent.

    ⚠️ A warning that shows routinely is one an operator learns to scroll past,
    which would cost exactly the signal this exists to give.
    """
    shutil.copy(AGENT_APK, seed / "atlas-agent.apk")
    client.post(
        "/api/v1/packages",
        files={"file": ("atlas-agent.apk", AGENT_APK.read_bytes(), "application/vnd.android.package-archive")},
        headers=ADMIN_HEADERS,
    )

    assert package_service.shipped_but_refused(db, seed) == []


def test_a_signing_key_change_is_reported_with_what_to_do(client: TestClient, db, seed):
    """⚠️ The case that actually happened.

    The stored package carries one certificate, the shipped APK another, and
    Android will not treat the second as an update to the first.
    """
    shutil.copy(AGENT_APK, seed / "atlas-agent.apk")
    client.post(
        "/api/v1/packages",
        files={"file": ("atlas-agent.apk", AGENT_APK.read_bytes(), "application/vnd.android.package-archive")},
        headers=ADMIN_HEADERS,
    )

    _as_if_the_key_changed(db)

    refused = package_service.shipped_but_refused(db, seed)

    assert len(refused) == 1, refused
    assert refused[0].package_name == "com.taksolutions.atlasmdm"
    assert "signing certificate differs" in refused[0].reason
    # ⚠️ The remedy, and it differs by whether a fleet exists. A message that
    # only says "refused" leaves an operator with a problem and no next step.
    assert "delete this package" in refused[0].reason
    assert "signing lineage" in refused[0].reason


def test_a_package_the_library_has_never_seen_is_not_a_refusal(db, seed):
    """Nothing stored means nothing refused — the next seed simply loads it.

    ⚠️ Reporting this would fire on every fresh install, before the seeder has
    run even once.
    """
    shutil.copy(AGENT_APK, seed / "atlas-agent.apk")

    assert package_service.shipped_but_refused(db, seed) == []


def test_a_missing_seed_directory_is_not_an_error(db, tmp_path):
    """A deployment that mounts no `dist/` renders its admin page as usual."""
    assert package_service.shipped_but_refused(db, tmp_path / "nope") == []


@pytest.mark.parametrize("empty", ["", None])
def test_an_unset_seed_directory_does_not_scan_the_working_directory(db, empty):
    """⚠️ `Path("")` is `.`, not "nowhere".

    Without the guard an unset setting would glob the process's working
    directory for APKs and compare whatever it found against the library —
    reporting refusals for files that have nothing to do with this release.
    """
    assert package_service.shipped_but_refused(db, empty) == []


def test_rubbish_in_the_seed_directory_cannot_break_the_page(db, seed):
    """⚠️ This runs while rendering the admin console.

    A malformed APK must not be able to take the page down — that would turn a
    warning about a stale agent into an outage, which is a strictly worse
    trade than the problem it reports.
    """
    (seed / "broken.apk").write_bytes(b"not an apk at all")

    assert package_service.shipped_but_refused(db, seed) == []


def test_the_console_shows_it(client: TestClient, db, seed):
    """End to end: the operator sees it without reading a log."""
    shutil.copy(AGENT_APK, seed / "atlas-agent.apk")
    client.post(
        "/api/v1/packages",
        files={"file": ("atlas-agent.apk", AGENT_APK.read_bytes(), "application/vnd.android.package-archive")},
        headers=ADMIN_HEADERS,
    )
    _as_if_the_key_changed(db)

    body = client.get("/admin", headers=ADMIN_HEADERS).text

    assert "atlas-agent.apk is not in the library" in body
    assert "signing certificate differs" in body
