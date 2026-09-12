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

"""Artifact storage, APK parsing, package ingestion, and device download."""

from __future__ import annotations

import hashlib
import io

import pytest
from fastapi.testclient import TestClient

from app.artifacts import axml
from app.artifacts.apk import ApkError, inspect_apk
from app.artifacts.bundles import PartRole, inspect, is_container
from app.artifacts.storage import ArtifactNotFound, LocalArtifactStorage
from tests.conftest import base_sha
from tests.apk_fixtures import (
    build_apk,
    build_manifest_axml,
    build_v1_signed_apk,
    build_xapk,
    make_signing_certificate,
)


# --------------------------------------------------------------------------- #
# Content-addressed storage
# --------------------------------------------------------------------------- #


def test_storage_addresses_by_content_hash(tmp_path):
    storage = LocalArtifactStorage(tmp_path)
    payload = b"hello artifact"

    digest, size = storage.put(io.BytesIO(payload))

    assert digest == hashlib.sha256(payload).hexdigest()
    assert size == len(payload)
    assert storage.open(digest).read() == payload


def test_identical_uploads_deduplicate(tmp_path):
    storage = LocalArtifactStorage(tmp_path)

    first, _ = storage.put(io.BytesIO(b"same bytes"))
    second, _ = storage.put(io.BytesIO(b"same bytes"))

    assert first == second
    stored = [p for p in tmp_path.rglob("*") if p.is_file()]
    assert len(stored) == 1


def test_storage_leaves_no_temp_files(tmp_path):
    storage = LocalArtifactStorage(tmp_path)
    storage.put(io.BytesIO(b"payload"))

    assert not [p for p in tmp_path.rglob(".incoming-*")]


def test_storage_rejects_a_non_digest_key(tmp_path):
    """Guards against path traversal if a caller passes user input straight through."""
    storage = LocalArtifactStorage(tmp_path)

    with pytest.raises(ValueError):
        storage.open("../../etc/passwd")
    assert storage.exists("../../etc/passwd") is False


def test_storage_range_read(tmp_path):
    storage = LocalArtifactStorage(tmp_path)
    digest, _ = storage.put(io.BytesIO(b"0123456789"))

    assert b"".join(storage.read_range(digest, 2, 5)) == b"2345"


def test_storage_delete(tmp_path):
    storage = LocalArtifactStorage(tmp_path)
    digest, _ = storage.put(io.BytesIO(b"payload"))

    assert storage.delete(digest) is True
    assert storage.delete(digest) is False
    with pytest.raises(ArtifactNotFound):
        storage.open(digest)


# --------------------------------------------------------------------------- #
# Binary XML
# --------------------------------------------------------------------------- #


def test_axml_decodes_utf8_string_pool():
    raw = build_manifest_axml("com.example.app", 42, "1.2.3", utf8=True)

    manifest = next(e for e in axml.parse_elements(raw) if e.name == "manifest")

    assert manifest.get_str("package") == "com.example.app"
    assert manifest.get_int("versionCode") == 42
    assert manifest.get_str("versionName") == "1.2.3"


def test_axml_decodes_utf16_string_pool():
    """aapt emits either encoding depending on version and content."""
    raw = build_manifest_axml("com.example.app", 7, utf8=False)

    manifest = next(e for e in axml.parse_elements(raw) if e.name == "manifest")
    assert manifest.get_str("package") == "com.example.app"
    assert manifest.get_int("versionCode") == 7


def test_axml_rejects_non_xml_buffer():
    with pytest.raises(axml.AxmlError):
        axml.parse_elements(b"PK\x03\x04 this is a zip, not binary xml")


# --------------------------------------------------------------------------- #
# APK inspection
# --------------------------------------------------------------------------- #


def test_apk_identity_is_read_from_the_manifest():
    info = inspect_apk(build_apk("com.atakmap.app", 52400, "5.2.0", 26, 34))

    assert info.package_name == "com.atakmap.app"
    assert info.version_code == 52400
    assert info.version_name == "5.2.0"
    assert info.min_sdk == 26
    assert info.target_sdk == 34
    assert info.split_name is None


def test_v2_signature_matches_the_signing_certificate():
    certificate = make_signing_certificate()

    info = inspect_apk(build_apk(certificate_der=certificate))

    assert info.signature_scheme == "v2"
    assert info.signature_sha256 == hashlib.sha256(certificate).hexdigest()


def test_v1_signature_is_used_when_no_signing_block_exists():
    """Modern APKs are often v2-only, but v1-only ones still exist."""
    apk, certificate = build_v1_signed_apk()

    info = inspect_apk(apk)

    assert info.signature_scheme == "v1"
    assert info.signature_sha256 == hashlib.sha256(certificate).hexdigest()


def test_provisioning_checksum_is_base64url_of_the_signature():
    """This value is exactly PROVISIONING_DEVICE_ADMIN_SIGNATURE_CHECKSUM."""
    import base64

    certificate = make_signing_certificate()
    info = inspect_apk(build_apk(certificate_der=certificate))

    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(certificate).digest()).decode().rstrip("=")
    )
    assert info.provisioning_checksum == expected
    assert "=" not in info.provisioning_checksum


def test_unsigned_apk_reports_no_signature():
    info = inspect_apk(build_apk(sign=False))

    assert info.signature_sha256 is None
    assert info.signature_scheme is None


def test_split_apk_is_recognised():
    info = inspect_apk(build_apk(split="config.arm64_v8a"))

    assert info.split_name == "config.arm64_v8a"


def test_non_zip_is_rejected():
    with pytest.raises(ApkError, match="ZIP"):
        inspect_apk(b"definitely not an apk")


def test_zip_without_a_manifest_is_rejected():
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("readme.txt", b"hello")

    with pytest.raises(ApkError):
        inspect_apk(buffer.getvalue())


# --------------------------------------------------------------------------- #
# Containers
# --------------------------------------------------------------------------- #


def test_xapk_is_detected_as_a_container():
    assert is_container(build_xapk()) is True
    assert is_container(build_apk()) is False


def test_xapk_unpacks_into_base_splits_and_obb():
    bundle = inspect(
        build_xapk(
            "com.atakmap.app",
            52400,
            splits=("config.arm64_v8a", "config.xxhdpi"),
            with_obb=True,
        )
    )

    roles = [part.role for part in bundle.parts]
    assert bundle.parts[0].role is PartRole.BASE  # base always first
    assert roles.count(PartRole.SPLIT) == 2
    assert roles.count(PartRole.OBB) == 1
    assert bundle.package_name == "com.atakmap.app"
    assert bundle.version_code == 52400


def test_container_without_manifest_json_still_works():
    """APKS files from bundletool carry no manifest.json."""
    bundle = inspect(build_xapk(include_manifest_json=False))

    assert bundle.parts[0].role is PartRole.BASE


def test_splits_are_classified_by_manifest_not_filename():
    """A renamed part must still be classified correctly."""
    import zipfile

    certificate = make_signing_certificate()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("zzz-first-alphabetically.apk", build_apk(certificate_der=certificate))
        archive.writestr(
            "aaa-looks-like-base.apk",
            build_apk(split="config.arm64_v8a", certificate_der=certificate),
        )

    bundle = inspect(buffer.getvalue())

    assert bundle.base.file_name == "zzz-first-alphabetically.apk"


def test_container_with_two_base_apks_is_rejected():
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("one.apk", build_apk("com.example.app", 1))
        archive.writestr("two.apk", build_apk("com.example.app", 1))

    with pytest.raises(ApkError, match="more than one base"):
        inspect(buffer.getvalue())


def test_container_mixing_packages_is_rejected():
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("base.apk", build_apk("com.example.app", 1))
        archive.writestr("other.apk", build_apk("com.other.app", 1, split="config.x86"))

    with pytest.raises(ApkError, match="belongs to"):
        inspect(buffer.getvalue())


def test_bare_split_apk_upload_is_rejected():
    with pytest.raises(ApkError, match="split APK"):
        inspect(build_apk(split="config.arm64_v8a"))


# --------------------------------------------------------------------------- #
# Upload API
# --------------------------------------------------------------------------- #


def upload(client: TestClient, data: bytes, filename: str = "app.apk", **form) -> dict:
    return client.post(
        "/api/v1/packages",
        files={"file": (filename, data, "application/octet-stream")},
        data=form,
    ).json()


def test_upload_records_identity_read_from_the_file(client: TestClient):
    body = upload(client, build_apk("com.atakmap.app", 52400, "5.2.0"), label="ATAK")

    assert body["package"]["package_name"] == "com.atakmap.app"
    assert body["version"]["version_code"] == 52400
    assert body["version"]["version_name"] == "5.2.0"
    assert body["package"]["signature_scheme"] == "v2"


def test_upload_returns_the_provisioning_checksum(client: TestClient):
    """Closes the Chunk 2 gap: QR payloads were blocked on this value."""
    body = upload(client, build_apk("com.taksolutions.atlasmdm", 1))

    assert body["provisioning_checksum"]
    assert len(body["provisioning_checksum"]) > 20


def test_upload_stores_every_part_of_a_container(client: TestClient):
    body = upload(
        client,
        build_xapk("com.atakmap.app", 52400, splits=("config.arm64_v8a",), with_obb=True),
        filename="atak.xapk",
    )

    roles = sorted(f["role"] for f in body["version"]["files"])
    assert roles == ["base", "obb", "split"]
    assert all(len(f["artifact_sha256"]) == 64 for f in body["version"]["files"])


def test_signature_mismatch_is_rejected_at_upload(client: TestClient):
    """Android would reject this on device; fail here where the error is legible."""
    first = make_signing_certificate("Original")
    second = make_signing_certificate("Different Key")

    upload(client, build_apk("com.example.app", 1, certificate_der=first))
    response = client.post(
        "/api/v1/packages",
        files={
            "file": (
                "app.apk",
                build_apk("com.example.app", 2, certificate_der=second),
                "application/octet-stream",
            )
        },
    )

    assert response.status_code == 422
    assert "signing certificate" in response.json()["detail"]


def test_same_signature_allows_a_new_version(client: TestClient):
    certificate = make_signing_certificate()

    upload(client, build_apk("com.example.app", 1, certificate_der=certificate))
    body = upload(client, build_apk("com.example.app", 2, certificate_der=certificate))

    assert body["version"]["version_code"] == 2
    assert len(body["package"]["versions"]) == 2


def test_duplicate_version_code_is_rejected(client: TestClient):
    certificate = make_signing_certificate()
    upload(client, build_apk("com.example.app", 5, certificate_der=certificate))

    response = client.post(
        "/api/v1/packages",
        files={
            "file": (
                "app.apk",
                build_apk("com.example.app", 5, certificate_der=certificate),
                "application/octet-stream",
            )
        },
    )

    assert response.status_code == 422
    assert "already uploaded" in response.json()["detail"]


def test_low_target_sdk_is_rejected(client: TestClient):
    """Android 16 blocks installs below API 24 — catch it before it reaches a device."""
    response = client.post(
        "/api/v1/packages",
        files={
            "file": (
                "old.apk",
                build_apk("com.old.app", 1, target_sdk=21),
                "application/octet-stream",
            )
        },
    )

    assert response.status_code == 422
    assert "API 24" in response.json()["detail"]


def test_unsigned_upload_is_rejected(client: TestClient):
    response = client.post(
        "/api/v1/packages",
        files={"file": ("u.apk", build_apk(sign=False), "application/octet-stream")},
    )

    assert response.status_code == 422
    assert "signing certificate" in response.json()["detail"]


def test_empty_upload_is_rejected(client: TestClient):
    response = client.post(
        "/api/v1/packages", files={"file": ("e.apk", b"", "application/octet-stream")}
    )
    assert response.status_code == 422


def test_deleting_a_version_reclaims_its_artifacts(client: TestClient, artifact_storage):
    certificate = make_signing_certificate()
    body = upload(client, build_apk("com.example.app", 1, certificate_der=certificate))
    digest = body["version"]["files"][0]["artifact_sha256"]
    assert artifact_storage.exists(digest)

    client.delete(
        f"/api/v1/packages/{body['package']['id']}/versions/{body['version']['id']}"
    )

    assert artifact_storage.exists(digest) is False


def test_shared_artifacts_survive_a_version_delete(client: TestClient, artifact_storage):
    """Content addressing lets versions share unchanged parts.

    Splits carry their own versionCode so they differ between builds, but OBB asset
    payloads routinely do not change — which is exactly where deduplication pays,
    since they are the largest files in the bundle.
    """
    certificate = make_signing_certificate()
    first = upload(
        client,
        build_xapk("com.example.app", 1, certificate_der=certificate, with_obb=True),
        filename="a.xapk",
    )
    second = upload(
        client,
        build_xapk("com.example.app", 2, certificate_der=certificate, with_obb=True),
        filename="b.xapk",
    )

    shared = {f["artifact_sha256"] for f in first["version"]["files"]} & {
        f["artifact_sha256"] for f in second["version"]["files"]
    }
    assert shared, "an unchanged OBB should deduplicate across versions"

    client.delete(
        f"/api/v1/packages/{first['package']['id']}/versions/{first['version']['id']}"
    )

    for digest in shared:
        assert artifact_storage.exists(digest), "still referenced by the other version"


# --------------------------------------------------------------------------- #
# Device download
# --------------------------------------------------------------------------- #


def test_device_downloads_an_artifact(client: TestClient, enrolled, mtls_headers):
    body = upload(client, build_apk("com.example.app", 1))
    digest = body["version"]["files"][0]["artifact_sha256"]
    device = enrolled()

    response = client.get(
        f"/api/v1/device/artifacts/{digest}",
        headers=mtls_headers(device["certificate_pem"]),
    )

    assert response.status_code == 200
    assert hashlib.sha256(response.content).hexdigest() == digest
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["x-content-sha256"] == digest


def test_download_requires_enrollment(client: TestClient):
    body = upload(client, build_apk("com.example.app", 1))
    digest = body["version"]["files"][0]["artifact_sha256"]

    assert client.get(f"/api/v1/device/artifacts/{digest}").status_code == 401


def test_range_request_returns_partial_content(client: TestClient, enrolled, mtls_headers):
    body = upload(client, build_apk("com.example.app", 1))
    digest = body["version"]["files"][0]["artifact_sha256"]
    device = enrolled()
    headers = mtls_headers(device["certificate_pem"])

    full = client.get(f"/api/v1/device/artifacts/{digest}", headers=headers).content
    partial = client.get(
        f"/api/v1/device/artifacts/{digest}", headers={**headers, "Range": "bytes=10-19"}
    )

    assert partial.status_code == 206
    assert partial.content == full[10:20]
    assert partial.headers["content-range"] == f"bytes 10-19/{len(full)}"


def test_resuming_a_download_yields_the_whole_file(
    client: TestClient, enrolled, mtls_headers
):
    """The interrupted-transfer case these links actually produce."""
    body = upload(client, build_apk("com.example.app", 1))
    digest = body["version"]["files"][0]["artifact_sha256"]
    device = enrolled()
    headers = mtls_headers(device["certificate_pem"])

    full = client.get(f"/api/v1/device/artifacts/{digest}", headers=headers).content
    cut = len(full) // 3

    head = client.get(
        f"/api/v1/device/artifacts/{digest}",
        headers={**headers, "Range": f"bytes=0-{cut - 1}"},
    ).content
    tail = client.get(
        f"/api/v1/device/artifacts/{digest}", headers={**headers, "Range": f"bytes={cut}-"}
    ).content

    assert head + tail == full
    assert hashlib.sha256(head + tail).hexdigest() == digest


def test_suffix_range_returns_the_tail(client: TestClient, enrolled, mtls_headers):
    body = upload(client, build_apk("com.example.app", 1))
    digest = body["version"]["files"][0]["artifact_sha256"]
    device = enrolled()
    headers = mtls_headers(device["certificate_pem"])

    full = client.get(f"/api/v1/device/artifacts/{digest}", headers=headers).content
    tail = client.get(
        f"/api/v1/device/artifacts/{digest}", headers={**headers, "Range": "bytes=-16"}
    )

    assert tail.status_code == 206
    assert tail.content == full[-16:]


def test_unsatisfiable_range_is_416(client: TestClient, enrolled, mtls_headers):
    body = upload(client, build_apk("com.example.app", 1))
    digest = body["version"]["files"][0]["artifact_sha256"]
    device = enrolled()

    response = client.get(
        f"/api/v1/device/artifacts/{digest}",
        headers={**mtls_headers(device["certificate_pem"]), "Range": "bytes=99999999-"},
    )

    assert response.status_code == 416


def test_unknown_artifact_is_404(client: TestClient, enrolled, mtls_headers):
    device = enrolled()

    response = client.get(
        f"/api/v1/device/artifacts/{'ab' * 32}",
        headers=mtls_headers(device["certificate_pem"]),
    )

    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Desired-state integration
# --------------------------------------------------------------------------- #


def require_app(client: TestClient, device_id: str, package_name: str, **entry) -> None:
    policy = client.post(
        "/api/v1/policies",
        json={
            "name": f"Require {package_name}",
            "policy_type": "APP_CATALOG",
            "spec": {"required_apps": [{"package_name": package_name, **entry}]},
        },
    ).json()
    client.post(
        "/api/v1/assignments",
        json={
            "policy_id": policy["id"],
            "scope": "device",
            "target_id": device_id,
            "rank": 1,
        },
    )


def test_required_app_resolves_to_downloadable_files(client: TestClient, enrolled):
    """⚠️ Was written with `com.atakmap.app`, which required apps now refuse
    (W141). The package was never the point — splits and their download URLs
    are — so it is an ordinary app, and ATAK's own path is tested where the
    ATAK section is."""
    device = enrolled()
    uploaded = upload(
        client,
        build_xapk("com.example.split", 52400, splits=("config.arm64_v8a",)),
        filename="a.xapk",
    )
    require_app(
        client, device["device_id"], "com.example.split",
        artifact_sha256=base_sha(uploaded),
    )

    state = client.get(f"/api/v1/devices/{device['device_id']}/desired-state").json()
    app = state["desired_state"]["apps"][0]

    assert app["available"] is True
    assert app["version_code"] == 52400
    assert {f["role"] for f in app["files"]} == {"base", "split"}
    assert all(f["url"].startswith("/api/v1/device/artifacts/") for f in app["files"])
    assert all(f["size_bytes"] > 0 for f in app["files"])


def test_required_app_with_nothing_uploaded_is_flagged(client: TestClient, enrolled):
    """A required-but-missing app is a fact to surface, not an absence to tidy away."""
    device = enrolled()
    require_app(client, device["device_id"], "com.notyet.uploaded")

    state = client.get(f"/api/v1/devices/{device['device_id']}/desired-state").json()

    assert state["desired_state"]["apps"] == [
        {
            "package_name": "com.notyet.uploaded",
            "available": False,
            # The reason travels with the failure: an unresolvable pin and an
            # unsatisfied floor are also `available: false`, and reading all three
            # as "nothing uploaded" is wrong for two of them (R17/R18).
            "reason": "nothing uploaded for it",
        }
    ]


def test_a_floor_alone_chooses_nothing(client: TestClient, enrolled):
    """⚠️ This used to read `test_min_version_code_floor_is_honoured`, and the
    behaviour it asserted is deliberately gone (W139).

    A floor is an *automatic selection* — "newest at or above 5" — and the
    operator asked for automatic selection to go away: a policy names the build
    it installs. The field is still accepted so stored specs validate, and it
    now selects nothing, which the device is told in as many words.
    """
    device = enrolled()
    certificate = make_signing_certificate()
    upload(client, build_apk("com.example.app", 1, certificate_der=certificate))
    upload(client, build_apk("com.example.app", 9, certificate_der=certificate))
    require_app(client, device["device_id"], "com.example.app", min_version_code=5)

    state = client.get(f"/api/v1/devices/{device['device_id']}/desired-state").json()
    app = state["desired_state"]["apps"][0]

    assert app["available"] is False
    assert "no version chosen" in app["reason"]


def test_an_older_build_can_be_pinned_over_a_newer_one(client: TestClient, enrolled):
    """The point of the whole change: three builds exist and the policy picks,
    including backwards. Nothing about build 9 being newer matters."""
    device = enrolled()
    certificate = make_signing_certificate()
    first = upload(client, build_apk("com.example.app", 1, certificate_der=certificate))
    upload(client, build_apk("com.example.app", 9, certificate_der=certificate))
    require_app(
        client, device["device_id"], "com.example.app",
        artifact_sha256=base_sha(first),
    )

    state = client.get(f"/api/v1/devices/{device['device_id']}/desired-state").json()

    assert state["desired_state"]["apps"][0]["version_code"] == 1


def test_uploading_a_new_build_moves_no_device(
    client: TestClient, enrolled, mtls_headers
):
    """⚠️ The inverse of what this test used to assert, and the reason the
    `published` flag could be deleted (W139).

    An upload used to change what a device must do — that is what the flag, the
    three-way publish question and the "never walk a fleet backwards" rule all
    existed to manage. A policy now names its build, so adding another one to
    the library is invisible to every device until someone chooses it.
    """
    device = enrolled()
    headers = mtls_headers(device["certificate_pem"])
    certificate = make_signing_certificate()
    first = upload(client, build_apk("com.example.app", 1, certificate_der=certificate))
    require_app(
        client, device["device_id"], "com.example.app",
        artifact_sha256=base_sha(first),
    )

    before = client.post(
        "/api/v1/device/checkin", json={"state_version": 0}, headers=headers
    ).json()

    upload(client, build_apk("com.example.app", 2, certificate_der=certificate))

    after = client.post(
        "/api/v1/device/checkin",
        json={"state_version": before["state_version"]},
        headers=headers,
    ).json()

    assert after["state_version"] == before["state_version"]
    state = client.get(f"/api/v1/devices/{device['device_id']}/desired-state").json()
    assert state["desired_state"]["apps"][0]["version_code"] == 1


def test_unrelated_upload_does_not_bump_state_version(
    client: TestClient, enrolled, mtls_headers
):
    """Invalidation is fleet-wide, but a recompute only bumps if something moved."""
    device = enrolled()
    headers = mtls_headers(device["certificate_pem"])
    upload(client, build_apk("com.example.app", 1))
    require_app(client, device["device_id"], "com.example.app")

    before = client.post(
        "/api/v1/device/checkin", json={"state_version": 0}, headers=headers
    ).json()

    upload(client, build_apk("com.something.else", 1))

    after = client.post(
        "/api/v1/device/checkin",
        json={"state_version": before["state_version"]},
        headers=headers,
    ).json()

    assert after["state_version"] == before["state_version"]
    assert after["desired_state"] is None
