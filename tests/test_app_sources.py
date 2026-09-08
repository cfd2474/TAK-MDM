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

"""Fetching apps from a third-party repository (W97).

⚠️ **No test here touches the network.** The index is served from a stub
transport, so the suite stays deterministic and offline — and, more usefully, so
the failure cases can be *arranged*: a tampered index, a download that does not
match its published digest, a listing that names the wrong package. Those are the
paths worth having tests for, and none of them can be produced by asking the real
repository nicely.
"""

from __future__ import annotations

import hashlib
import json

import httpx
import pytest

from app.db.models import AppPackage, AppPackageVersion, Device
from app.services import repo_import
from app.services.app_sources.base import SourceError, SourceVersion
from app.services.app_sources.fdroid import FDroidSource
from tests.apk_fixtures import build_apk, make_signing_certificate

REPO = "https://f-droid.example/repo"


def _index(apk: bytes, *, package="org.example.app", code=42, native=None) -> dict:
    return {
        "repo": {"address": REPO},
        "packages": {
            package: {
                "metadata": {
                    "name": {"en-US": "Example App"},
                    "summary": {"en-US": "Does a thing"},
                },
                "versions": {
                    "abc": {
                        "file": {
                            "name": f"/{package}_{code}.apk",
                            "sha256": hashlib.sha256(apk).hexdigest(),
                            "size": len(apk),
                        },
                        "manifest": {
                            "versionCode": code,
                            "versionName": "1.0",
                            "nativecode": native,
                            "usesSdk": {"minSdkVersion": 24, "targetSdkVersion": 34},
                            "signer": {"sha256": ["deadbeef" * 8]},
                        },
                    }
                },
            }
        },
    }


def _source(tmp_path, index: dict, apk: bytes, *, corrupt_index=False, corrupt_apk=False):
    """An F-Droid source wired to a stub repository."""
    body = json.dumps(index).encode()
    served = body + (b" " if corrupt_index else b"")
    entry = {
        "index": {
            "name": "/index-v2.json",
            # Always the digest of the *honest* body: corrupting the served bytes
            # is how a tampered mirror is simulated.
            "sha256": hashlib.sha256(body).hexdigest(),
            "size": len(body),
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("entry.json"):
            return httpx.Response(200, json=entry)
        if path.endswith("index-v2.json"):
            return httpx.Response(200, content=served)
        if path.endswith(".apk"):
            return httpx.Response(200, content=apk + (b"x" if corrupt_apk else b""))
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    return FDroidSource(tmp_path / "cache", client=client, repo=REPO)


# --------------------------------------------------------------------------- #
# The index, and refusing to trust one that does not match
# --------------------------------------------------------------------------- #


def test_an_app_can_be_found_by_name_or_package(tmp_path):
    apk = build_apk("org.example.app", 42)
    source = _source(tmp_path, _index(apk), apk)

    assert source.search("example")[0].package_name == "org.example.app"
    assert source.search("org.example.app")[0].name == "Example App"
    assert source.search("nothing-like-this") == []


def test_a_tampered_index_is_refused_and_never_cached(tmp_path):
    """⚠️ The index is what every other hash is checked against.

    Accepting one that does not match `entry.json` would quietly validate every
    download made afterwards, so it is refused and not written to the cache.
    """
    apk = build_apk("org.example.app", 42)
    source = _source(tmp_path, _index(apk), apk, corrupt_index=True)

    with pytest.raises(SourceError) as raised:
        source.search("example")

    assert "does not match the digest" in str(raised.value)
    assert not (tmp_path / "cache" / "fdroid-index-v2.json").exists()


def test_the_index_is_not_refetched_while_its_digest_is_unchanged(tmp_path):
    apk = build_apk("org.example.app", 42)
    source = _source(tmp_path, _index(apk), apk)

    source.search("example")
    first = (tmp_path / "cache" / "fdroid-index-v2.json").stat().st_mtime_ns
    source.search("example")

    assert (tmp_path / "cache" / "fdroid-index-v2.json").stat().st_mtime_ns == first


# --------------------------------------------------------------------------- #
# What a version says about itself
# --------------------------------------------------------------------------- #


def test_a_version_carries_what_the_index_declares(tmp_path):
    apk = build_apk("org.example.app", 42)
    source = _source(tmp_path, _index(apk, native=["arm64-v8a"]), apk)

    version = source.versions("org.example.app")[0]

    assert version.version_code == 42
    assert version.abis == ("arm64-v8a",)
    assert version.min_sdk == 24
    assert version.signer_sha256 == "deadbeef" * 8
    assert version.verifiable is True


def test_declared_without_native_code_is_not_the_same_as_undeclared(tmp_path):
    """⚠️ The W96 distinction, carried through from the source.

    An index that says `nativecode: []` states the app runs anywhere. An index
    that omits the field says nothing. Collapsing them would invent a claim.
    """
    apk = build_apk("org.example.app", 42)

    declared = _source(tmp_path / "a", _index(apk, native=[]), apk)
    silent = _source(tmp_path / "b", _index(apk, native=None), apk)

    assert declared.versions("org.example.app")[0].abis == ()
    assert silent.versions("org.example.app")[0].abis is None


def test_a_download_that_does_not_match_the_index_is_refused(tmp_path):
    apk = build_apk("org.example.app", 42)
    source = _source(tmp_path, _index(apk), apk, corrupt_apk=True)
    version = source.versions("org.example.app")[0]

    with pytest.raises(SourceError) as raised:
        source.download(version)

    assert "does not match the digest" in str(raised.value)


def test_a_matching_download_is_marked_verified(tmp_path):
    apk = build_apk("org.example.app", 42)
    source = _source(tmp_path, _index(apk), apk)

    downloaded = source.download(source.versions("org.example.app")[0])

    assert downloaded.verified is True
    assert downloaded.data == apk


# --------------------------------------------------------------------------- #
# Import
# --------------------------------------------------------------------------- #


def test_an_imported_build_is_held_not_published(tmp_path, db, artifact_storage):
    """⚠️ Publishing aims every device at a build.

    Fetching something to look at must never do that as a side effect — and
    `ingest` would, since this build is newer than everything deployed.
    """
    apk = build_apk("org.example.app", 42)
    source = _source(tmp_path, _index(apk), apk)
    version = source.versions("org.example.app")[0]

    imported = repo_import.import_version(db, artifact_storage, source, version)
    db.commit()

    assert imported.published is False
    assert imported.source == "fdroid"
    assert imported.source_url.endswith("org.example.app_42.apk")


def test_identity_comes_from_the_file_not_the_listing(tmp_path, db, artifact_storage):
    """⚠️ A catalogue that names the wrong package must not be believed.

    The listing here claims `org.example.app`; the APK behind it is something
    else. What gets catalogued is what the file says it is.
    """
    apk = build_apk("com.somethingelse", 7)
    index = _index(apk, package="org.example.app", code=42)
    source = _source(tmp_path, index, apk)
    version = source.versions("org.example.app")[0]

    imported = repo_import.import_version(db, artifact_storage, source, version)
    db.commit()

    assert imported.package.package_name == "com.somethingelse"
    assert imported.version_code == 7


# --------------------------------------------------------------------------- #
# Preflight: answering "should I fetch this" while it is still free
# --------------------------------------------------------------------------- #


def _version(**kwargs) -> SourceVersion:
    base = dict(
        package_name="org.example.app",
        version_code=42,
        version_name="1.0",
        download_url=f"{REPO}/org.example.app_42.apk",
        sha256="a" * 64,
        source="fdroid",
    )
    base.update(kwargs)
    return SourceVersion(**base)


def test_a_different_signer_blocks_the_import(db, artifact_storage):
    """⚠️ Android refuses this update outright, and a changed signer is what a
    substituted binary looks like. Said before the download, not after."""
    from app.services import packages as package_service

    package_service.ingest(db, artifact_storage, build_apk("org.example.app", 1))
    db.commit()

    result = repo_import.preflight(db, _version(signer_sha256="b" * 64))

    assert result.ok is False
    assert "different certificate" in result.blocking[0]


def test_a_version_already_held_blocks_the_import(db, artifact_storage):
    from app.services import packages as package_service

    package_service.ingest(db, artifact_storage, build_apk("org.example.app", 42))
    db.commit()

    result = repo_import.preflight(db, _version(signer_sha256=None))

    assert result.ok is False
    assert "already in the library" in result.blocking[0]


def test_a_build_no_device_can_run_is_warned_about(db, artifact_storage):
    """⚠️ The whole point of W96, applied one step earlier.

    R19 was discovered days after the fact as a failed install. Here it is a
    sentence next to the download button.
    """
    db.add(Device(serial_number="SM-1", supported_abis="arm64-v8a", sdk_int=34))
    db.commit()

    result = repo_import.preflight(db, _version(abis=("armeabi-v7a",)))

    assert result.ok is True, "a warning, not a refusal — it is the operator's call"
    assert any("cannot run this build" in w for w in result.warnings)
    assert any("SM-1" in w for w in result.warnings)


def test_devices_that_have_not_reported_are_counted_not_ignored(db):
    """⚠️ Silence must not read as approval.

    A fleet of older agents reports no architecture at all, and a preflight that
    said nothing would look like a clean bill of health.
    """
    db.add(Device(serial_number="KNOWN", supported_abis="arm64-v8a", sdk_int=34))
    db.add(Device(serial_number="QUIET"))
    db.commit()

    result = repo_import.preflight(db, _version(abis=("arm64-v8a",)))

    assert any("have not reported their architecture" in w for w in result.warnings)


def test_a_source_without_a_checksum_says_so(db):
    result = repo_import.preflight(db, _version(sha256=None))

    assert any("no checksum" in w for w in result.warnings)
