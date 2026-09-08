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

"""What a device can run, and filling in what was never asked (W96, C2).

The other half of R19: knowing an APK is `armeabi-v7a` is useless until something
knows the tablet is not.
"""

from __future__ import annotations

import io
import zipfile

from sqlalchemy import select

from app.db.models import AppPackageVersion, Device
from app.services import packages as package_service
from tests.apk_fixtures import build_apk


# --------------------------------------------------------------------------- #
# The device reports itself
# --------------------------------------------------------------------------- #


def _device(db) -> Device:
    return db.scalar(select(Device))


def test_a_device_reports_what_it_can_run(client, db, enrolled, mtls_headers):
    headers = mtls_headers(enrolled()["certificate_pem"])

    response = client.post(
        "/api/v1/device/checkin",
        json={
            "state_version": 0,
            "supported_abis": ["arm64-v8a", "armeabi-v7a"],
            "sdk_int": 34,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text

    db.expire_all()
    stored = _device(db)
    assert stored.supported_abis == "arm64-v8a,armeabi-v7a"
    assert stored.sdk_int == 34


def test_the_order_the_device_gave_is_kept(client, db, enrolled, mtls_headers):
    """⚠️ `SUPPORTED_ABIS` is ranked, most-preferred first.

    Sorting it would throw away the device's own answer to "which of these suits
    you best", which is the question a future build choice has to ask.
    """
    headers = mtls_headers(enrolled()["certificate_pem"])

    client.post(
        "/api/v1/device/checkin",
        json={"state_version": 0, "supported_abis": ["arm64-v8a", "armeabi-v7a"]},
        headers=headers,
    )

    db.expire_all()
    assert _device(db).supported_abis.split(",")[0] == "arm64-v8a"


def test_an_older_agent_does_not_erase_what_is_known(client, db, enrolled, mtls_headers):
    """⚠️ Silence is not a report.

    An agent too old to send these fields must not blank a record a newer one
    filled in — the same rule `atak_version` already follows.
    """
    headers = mtls_headers(enrolled()["certificate_pem"])
    stored = _device(db)
    stored.supported_abis = "arm64-v8a"
    stored.sdk_int = 34
    db.commit()

    client.post("/api/v1/device/checkin", json={"state_version": 0}, headers=headers)

    db.expire_all()
    stored = _device(db)
    assert stored.supported_abis == "arm64-v8a"
    assert stored.sdk_int == 34


# --------------------------------------------------------------------------- #
# Backfilling the library
# --------------------------------------------------------------------------- #


def test_the_backfill_fills_only_what_was_never_scanned(db, artifact_storage):
    scanned = package_service.ingest(
        db, artifact_storage, build_apk("com.scanned", 1, "1.0")
    )
    legacy = package_service.ingest(
        db,
        artifact_storage,
        build_apk("com.legacy", 1, "1.0", extra_files={"lib/arm64-v8a/x.so": b"x"}),
    )
    legacy.version.abis = None
    db.commit()

    filled = package_service.backfill_abis(db, artifact_storage)
    db.commit()

    assert filled == 1
    assert db.get(AppPackageVersion, legacy.version.id).abis == "arm64-v8a"
    assert db.get(AppPackageVersion, scanned.version.id).abis == ""


def test_the_backfill_reads_every_part_not_just_the_base(db, artifact_storage):
    """⚠️ A split app keeps its native code in the splits.

    Reading only the base would write "" — "runs anywhere" — for the exact shape
    of app that caused R19.
    """
    from tests.apk_fixtures import make_signing_certificate

    certificate = make_signing_certificate()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr("com.split.apk", build_apk("com.split", 1, certificate_der=certificate))
        bundle.writestr(
            "config.arm64_v8a.apk",
            build_apk(
                "com.split",
                1,
                split="config.arm64_v8a",
                certificate_der=certificate,
                extra_files={"lib/arm64-v8a/libsplit.so": b"x"},
            ),
        )

    result = package_service.ingest(db, artifact_storage, buffer.getvalue())
    result.version.abis = None
    db.commit()

    package_service.backfill_abis(db, artifact_storage)
    db.commit()

    assert db.get(AppPackageVersion, result.version.id).abis == "arm64-v8a"


def test_a_version_whose_files_are_gone_stays_unscanned(db, artifact_storage):
    """⚠️ The one case where writing an answer would be a lie.

    "" means "carries no native code, installs anywhere". A version whose blobs
    have been deleted has told us nothing, and must keep saying *not scanned*.
    """
    result = package_service.ingest(db, artifact_storage, build_apk("com.gone", 1, "1.0"))
    result.version.abis = None
    for part in result.version.files:
        artifact_storage.delete(part.artifact_sha256)
    db.commit()

    filled = package_service.backfill_abis(db, artifact_storage)
    db.commit()

    assert filled == 0
    assert db.get(AppPackageVersion, result.version.id).abis is None
