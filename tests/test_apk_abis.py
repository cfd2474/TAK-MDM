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

"""Which architectures a build can install on (W96, R19).

⚠️ **The failure this guards against is permanent and silent-ish.** An APK whose
native code does not match the device fails with
`INSTALL_FAILED_NO_MATCHING_ABIS`, retries on every reconcile, and never succeeds.
It shows only as a DEGRADED device with a cryptic string — and if the app happens
to be preinstalled, as it was for Chrome, the home screen looks perfectly fine.

Reading it at upload is the cheap moment: the operator is holding the file.
"""

from __future__ import annotations

import io
import pathlib
import zipfile

import pytest
from fastapi.testclient import TestClient

from sqlalchemy import select

from app.artifacts.apk import inspect_apk, native_abis
from app.db.models import AppPackageVersion
from app.services import packages as package_service
from tests.apk_fixtures import build_apk, make_signing_certificate

FILES = pathlib.Path("Test Files")


def _abis(name: str) -> tuple[str, ...]:
    return inspect_apk((FILES / name).read_bytes()).abis


def _zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for entry, payload in entries.items():
            archive.writestr(entry, payload)
    return buffer.getvalue()


def _abis_of_zip(data: bytes) -> tuple[str, ...]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return native_abis(data, archive)


# --------------------------------------------------------------------------- #
# The rule
# --------------------------------------------------------------------------- #


def test_a_build_with_no_native_code_runs_anywhere():
    assert _abis_of_zip(_zip({"classes.dex": b"x"})) == ()


def test_the_architectures_are_read_from_lib():
    data = _zip(
        {
            "lib/arm64-v8a/libtak.so": b"x",
            "lib/armeabi-v7a/libtak.so": b"x",
            "classes.dex": b"x",
        }
    )
    assert _abis_of_zip(data) == ("arm64-v8a", "armeabi-v7a")


def test_an_empty_lib_directory_entry_is_not_an_architecture():
    """A directory entry carries no code; only a file under it does."""
    assert _abis_of_zip(_zip({"lib/arm64-v8a/": b""})) == ()


# --------------------------------------------------------------------------- #
# ⚠️ The two traps, both found in the operator's own files
# --------------------------------------------------------------------------- #


def test_a_bundle_keeps_its_native_code_in_the_splits():
    """⚠️ A scan that stopped at the root would call this universal.

    Which is the opposite of true, and would wave through the one build that
    cannot install — the exact shape of R19.
    """
    split = _zip({"lib/armeabi-v7a/libchrome.so": b"x"})
    bundle = _zip({"base.apk": _zip({"classes.dex": b"x"}), "split.apk": split})

    assert _abis_of_zip(bundle) == ("armeabi-v7a",)


def test_apks_shipped_as_assets_are_not_this_app_s_architecture():
    """⚠️ `ATAK-Plugin-uastool` ships `assets/apks/DJI/ATAKGo.apk`.

    Those are payloads it hands to something else, not code this install runs.
    Counting them would misreport every ATAK plugin bundling a drone SDK.
    """
    payload = _zip({"lib/x86/libdji.so": b"x"})
    apk = _zip({"classes.dex": b"x", "assets/apks/DJI/ATAKGo.apk": payload})

    assert _abis_of_zip(apk) == ()


def test_an_unreadable_split_is_not_reported_as_universal():
    """⚠️ Empty means "runs anywhere", so it must never mean "I could not tell".

    Saying nothing about the unreadable part is safe; calling the app universal
    because of it is the failure this whole file exists to prevent.
    """
    bundle = _zip({"base.apk": b"this is not a zip", "split.apk": _zip({"lib/arm64-v8a/a.so": b"x"})})

    assert _abis_of_zip(bundle) == ("arm64-v8a",)


# --------------------------------------------------------------------------- #
# The operator's real files, with known answers
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(not FILES.exists(), reason="the sample APKs are not in this checkout")
@pytest.mark.parametrize(
    "name, expected",
    [
        ("ATAK-5.8.0.4-174b425-civSmall-release.apk", ("arm64-v8a",)),
        # ⚠️ Not a mistake: this one really carries no native code, and is the
        # example of a build that installs on anything.
        ("GoTAK-Launcher-1.2.0.apk", ()),
        (
            "Microsoft+Outlook_5.2606.0_APKPure.apk",
            ("arm64-v8a", "armeabi-v7a", "x86", "x86_64"),
        ),
        ("ArcGIS+Field+Maps_26.2.2_APKPure.apk", ("arm64-v8a", "armeabi-v7a")),
        # Its own code, with the assets/apks/ payloads ignored.
        (
            "ATAK-Plugin-uastool-13.0.6-74628a10-5.8.0-civ-release.apk",
            ("arm64-v8a", "armeabi-v7a"),
        ),
    ],
)
def test_real_builds_report_what_they_carry(name, expected):
    if not (FILES / name).exists():
        pytest.skip(f"{name} is not in this checkout")
    assert _abis(name) == expected


@pytest.mark.skipif(
    not (FILES / "Google+Chrome_152.0.7977.82_APKPure.xapk").exists(),
    reason="the Chrome bundle is not in this checkout",
)
def test_the_chrome_bundle_is_32_bit_which_is_the_whole_of_r19():
    """⚠️ This is the build that broke the SM-X520.

    `com.android.chrome.apk` inside the bundle carries `armeabi-v7a` only. The
    tablet is 64-bit-only, so the native libraries cannot be extracted —
    `res=-113`. Had this been read at upload, nobody would have deployed it.
    """
    data = (FILES / "Google+Chrome_152.0.7977.82_APKPure.xapk").read_bytes()

    assert _abis_of_zip(data) == ("armeabi-v7a",)


# --------------------------------------------------------------------------- #
# Recorded at ingest, and readable in the console
# --------------------------------------------------------------------------- #


def test_ingest_records_what_the_build_carries(db, artifact_storage):
    result = package_service.ingest(
        db,
        artifact_storage,
        build_apk("com.probe", 1, "1.0", extra_files={"lib/arm64-v8a/libx.so": b"x"}),
    )
    assert result.version.abis == "arm64-v8a"


def test_a_universal_build_is_recorded_as_empty_not_null(db, artifact_storage):
    """⚠️ The distinction the whole column turns on.

    Empty is an answer — scanned, carries no native code, installs anywhere. NULL
    means nothing looked. A build uploaded before W96 must not read as universal.
    """
    result = package_service.ingest(db, artifact_storage, build_apk("com.plain", 1, "1.0"))

    assert result.version.abis == ""
    assert result.version.abis is not None


def test_a_split_app_reports_the_architecture_of_its_splits(db, artifact_storage):
    """⚠️ The base of a split app often carries no native code at all.

    Reading only the base would report the whole app as universal while the split
    holding the code is one architecture — R19's exact shape.

    The bundle is assembled here rather than with `build_xapk`, whose splits are
    named `config.arm64_v8a` but carry no `lib/` at all. Using it would have
    passed against a base-only read and proved nothing.
    """
    certificate = make_signing_certificate()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        bundle.writestr(
            "com.split.apk", build_apk("com.split", 4, certificate_der=certificate)
        )
        bundle.writestr(
            "config.arm64_v8a.apk",
            build_apk(
                "com.split",
                4,
                split="config.arm64_v8a",
                certificate_der=certificate,
                extra_files={"lib/arm64-v8a/libsplit.so": b"x"},
            ),
        )

    result = package_service.ingest(db, artifact_storage, buffer.getvalue())

    assert result.version.abis == "arm64-v8a"


def test_the_console_distinguishes_universal_from_unscanned(
    client: TestClient, db, artifact_storage
):
    """Three states on the page, because two would have to lie about one of them.

    The version table only renders for the package named in `?versions=`, which is
    how the console expands one row.
    """
    plain = package_service.ingest(db, artifact_storage, build_apk("com.plain", 1, "1.0"))
    armed = package_service.ingest(
        db,
        artifact_storage,
        build_apk("com.armed", 1, "1.0", extra_files={"lib/arm64-v8a/libx.so": b"x"}),
    )
    db.commit()

    armed_page = client.get(f"/apps?versions={armed.version.package_id}").text
    assert "Architecture" in armed_page
    assert "arm64-v8a" in armed_page

    plain_page = client.get(f"/apps?versions={plain.version.package_id}").text
    assert ">any<" in plain_page


def test_a_build_uploaded_before_the_scan_says_so(client: TestClient, db, artifact_storage):
    """⚠️ The migration leaves every existing row NULL on purpose.

    An arm64-only APK uploaded last month must not be presented as running
    anywhere — that is the claim that left a tablet degraded.
    """
    result = package_service.ingest(db, artifact_storage, build_apk("com.legacy", 1, "1.0"))
    result.version.abis = None
    db.commit()

    body = client.get(f"/apps?versions={result.version.package_id}").text

    assert "not scanned" in body
    assert ">any<" not in body
