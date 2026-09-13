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

from sqlalchemy import select

from app.db.models import AppPackage, AppPackageVersion, Device
from app.services import repo_import
from tests.conftest import ADMIN_HEADERS
from app.services.app_sources.base import SourceError, SourceVersion
from app.services.app_sources.fdroid import FDroidSource
from tests.apk_fixtures import build_apk, make_signing_certificate

REPO = "https://f-droid.example/repo"


@pytest.fixture(autouse=True)
def _no_shared_sources():
    """⚠️ Sources are cached per process for speed (W98), which tests must not
    inherit from one another — a cached index built against one stub would answer
    the next test's search."""
    from app.services.app_sources import repos

    repos.reset_cache()
    yield
    repos.reset_cache()


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


def test_an_imported_build_reaches_no_device(tmp_path, db, artifact_storage):
    """⚠️ Fetching something to look at must not ship it.

    This needed a `publish=False` when `ingest` would otherwise have published
    anything newer than what was deployed. Since W139 nothing is chosen
    automatically, so the guarantee holds for every path into the library — and
    is asserted here as what it actually means: no policy resolves to it.
    """
    from app.services import effective_policy as eff

    apk = build_apk("org.example.app", 42)
    source = _source(tmp_path, _index(apk), apk)
    version = source.versions("org.example.app")[0]

    imported = repo_import.import_version(db, artifact_storage, source, version)
    db.commit()

    assert imported.source == "fdroid"
    resolved = eff.resolve_required_apps(
        db, {"APP_CATALOG": {"required_apps": [{"package_name": "org.example.app"}]}}
    )[0]
    assert resolved["available"] is False
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


# --------------------------------------------------------------------------- #
# The console (W97, C2)
# --------------------------------------------------------------------------- #


def test_the_repo_tab_states_each_source_s_limits(client):
    """⚠️ The limits are stated on the page, not learned by searching in vain.

    F-Droid carries open-source apps only; APKPure answers to an exact package id
    and never to a name. An operator who knows neither reads an empty result as a
    broken feature — so both are written where the searching happens.
    """
    body = client.get("/apps").text

    assert 'data-tab-panel="repo"' in body
    assert "3rd Party Repos" in body
    assert "open-source apps" in body
    assert "only answers to an exact package id" in body


def test_one_search_covers_every_source(client, monkeypatch):
    """⚠️ One bar, every source, each row saying where it came from (W98).

    The operator asked for a single search; what makes that safe is that a row
    still carries its origin, because the sources are not equally trustworthy.
    """
    from app.services.app_sources.base import SourceApp
    from app.web import routes

    class Stub:
        def __init__(self, name):
            self.name = name

        def search(self, query, limit=25):
            return [SourceApp(package_name="org.example.app", name=f"App from {self.name}")]

    monkeypatch.setattr(routes, "_repo_source", lambda name, settings, *_a, **_k:Stub(name))

    body = client.get("/apps/repo/search?q=example", headers=ADMIN_HEADERS).json()

    sources = [row["source"] for row in body["apps"]]
    assert "fdroid" in sources and "apkpure" in sources
    assert all(row["source_label"] for row in body["apps"])
    # APKPure publishes no digest, and the row says so.
    assert {row["source"]: row["verifiable"] for row in body["apps"]}["apkpure"] is False


def test_a_failing_source_does_not_empty_the_page(client, monkeypatch):
    """⚠️ The failure mode a unified search invites.

    If one source raising meant an empty result, an operator would go hunting for
    an app that F-Droid was holding all along. The others' results stand and the
    broken one is named, in its own words.
    """
    from app.services.app_sources.base import SourceApp, SourceError
    from app.web import routes

    class Stub:
        def __init__(self, name):
            self.name = name

        def search(self, query, limit=25):
            if self.name == "apkpure":
                raise SourceError("apkeep is not installed on this server")
            return [SourceApp(package_name="org.example.app", name="Example")]

    monkeypatch.setattr(routes, "_repo_source", lambda name, settings, *_a, **_k:Stub(name))

    body = client.get("/apps/repo/search?q=example", headers=ADMIN_HEADERS).json()

    assert body["apps"], "the working sources still answered"
    assert [p["source"] for p in body["problems"]] == ["apkpure"]
    assert "not installed" in body["problems"][0]["error"]


def test_an_unknown_source_is_a_404_when_one_is_named(client):
    """Search no longer takes a source — but the routes that must know which one
    still refuse an unknown name rather than guessing."""
    response = client.get(
        "/apps/repo/versions?package=org.example.app&source=nowhere", headers=ADMIN_HEADERS
    )
    assert response.status_code == 404


def test_a_blocked_build_is_refused_before_anything_is_downloaded(
    client, db, artifact_storage, monkeypatch, tmp_path
):
    """⚠️ The reasons are knowable from the listing, so the bandwidth is not spent.

    Here the library already holds that versionCode; the import must not fetch the
    file only to have `ingest` reject it at the end.
    """
    from app.services import packages as package_service
    from app.web import routes

    apk = build_apk("org.example.app", 42)
    package_service.ingest(db, artifact_storage, apk)
    db.commit()

    source = _source(tmp_path, _index(apk), apk)
    fetched: list[str] = []
    original = source.download
    source.download = lambda v: (fetched.append(v.download_url), original(v))[1]
    monkeypatch.setattr(routes, "_repo_source", lambda name, settings, *_a, **_k:source)

    response = client.post(
        "/apps/repo/import",
        data={"package": "org.example.app", "version_key": "42"},
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 422
    assert "already in the library" in response.json()["error"]
    assert fetched == [], "nothing should have been downloaded"


def test_the_version_is_re_read_at_import_not_taken_from_the_form(
    client, db, artifact_storage, monkeypatch, tmp_path
):
    """⚠️ Everything the browser holds is the catalogue's word relayed by a page.

    Asking the index again means the download URL and digest come from the source
    at the moment of import, so a stale or edited form cannot redirect the fetch.
    """
    from app.web import routes

    apk = build_apk("org.example.app", 42)
    source = _source(tmp_path, _index(apk), apk)
    monkeypatch.setattr(routes, "_repo_source", lambda name, settings, *_a, **_k:source)

    response = client.post(
        "/apps/repo/import",
        data={"package": "org.example.app", "version_key": "999"},
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 404
    assert "no longer offered" in response.json()["error"]


def test_an_import_runs_as_a_job_and_lands_held(
    client, db, artifact_storage, monkeypatch, tmp_path
):
    """The whole path, driven synchronously so the outcome cannot depend on
    thread timing."""
    from app.services import import_jobs
    from app.web import routes

    apk = build_apk("org.example.app", 42)
    source = _source(tmp_path, _index(apk), apk)
    monkeypatch.setattr(routes, "_repo_source", lambda name, settings, *_a, **_k:source)
    monkeypatch.setattr(import_jobs, "_thread", lambda work: work())

    started = client.post(
        "/apps/repo/import",
        data={"package": "org.example.app", "version_key": "42", "label": "Example"},
        headers=ADMIN_HEADERS,
    )
    assert started.status_code == 202, started.text

    job = client.get(f"/apps/repo/import/{started.json()['id']}", headers=ADMIN_HEADERS)
    assert job.json()["state"] == "done", job.json().get("error")

    stored = db.scalar(
        select(AppPackageVersion).where(AppPackageVersion.version_code == 42)
    )
    assert stored.source == "fdroid"


def test_a_job_the_server_has_forgotten_says_so(client):
    """A modal that spun forever would be the worst answer to a restart."""
    response = client.get("/apps/repo/import/nosuchjob", headers=ADMIN_HEADERS)

    assert response.status_code == 404
    assert "no longer known" in response.json()["error"]


# --------------------------------------------------------------------------- #
# Several repositories, one format (W97, C3)
# --------------------------------------------------------------------------- #


def test_each_repository_caches_its_own_index(tmp_path):
    """⚠️ The bug a shared filename would have caused.

    Every repository verifies its index against its own `entry.json`, so one
    overwriting another's cache would surface as a digest mismatch — or worse, as
    the wrong catalogue answering a search.
    """
    apk = build_apk("org.example.app", 42)
    cache = tmp_path / "cache"

    first = _source(tmp_path, _index(apk), apk)
    first._cache_dir = cache
    first.name = "fdroid"
    first.search("example")

    second = _source(tmp_path, _index(apk, package="org.other.app"), apk)
    second._cache_dir = cache
    second.name = "izzyondroid"
    second.search("other")

    assert (cache / "fdroid-index-v2.json").exists()
    assert (cache / "izzyondroid-index-v2.json").exists()


def test_provenance_records_the_repository_that_served_it(tmp_path, db, artifact_storage):
    """⚠️ A build from a third-party repository recorded as "fdroid" would be a lie
    in the one field that exists to answer where it came from."""
    apk = build_apk("org.example.app", 42)
    source = _source(tmp_path, _index(apk), apk)
    source.name = "izzyondroid"

    imported = repo_import.import_version(db, artifact_storage, source, source.versions("org.example.app")[0])
    db.commit()

    assert imported.source == "izzyondroid"


def test_the_offered_repositories_say_what_they_are():
    """Each carries a note, because listing them side by side would otherwise
    imply they are the same decision. They are not."""
    from app.services.app_sources import repos

    names = [r.name for r in repos.KNOWN]
    assert names[0] == "fdroid", "official F-Droid is the recommendation"
    assert "izzyondroid" in names
    assert all(r.note for r in repos.KNOWN)

    third_party = next(r for r in repos.KNOWN if r.name == "izzyondroid")
    assert "third-party" in third_party.note


def test_an_unknown_repository_builds_nothing(tmp_path):
    from app.services.app_sources import repos

    assert repos.build("nowhere", tmp_path) is None
    assert repos.build("fdroid", tmp_path).name == "fdroid"


def test_the_console_offers_every_source_with_its_note(client):
    """⚠️ The picker is gone — one bar searches everything (W98).

    What must survive that is the *labelling*: every source still appears with
    what it is, because merging them into one result list is only safe if a row
    still says where it came from.
    """
    body = client.get("/apps").text

    assert "data-repo-source" not in body, "the per-source picker was removed"

    for label in ("F-Droid", "F-Droid archive", "IzzyOnDroid", "APKPure"):
        assert label in body
    assert "third-party repository" in body
    # APKPure's limitation is stated on the page rather than discovered.
    assert "only answers to an exact package id" in body


def test_google_play_has_its_own_tab_and_leaves_the_repository_search(client):
    """⚠️ Play is not a repository row (W101).

    A Play result costs a linked Google account and carries terms the others do
    not; putting it behind a shared bar would hide that. It gets a tab, between
    TPC Plugins and the 3rd party repositories, and drops out of the unified
    search — so each panel has its own bar rather than sharing one.

    ⚠️ The count is one, not two, until an account is linked (W145): Play offers
    no search box at all without one, because every Play request is made *as*
    the linked account. `test_play_search_gate.py` covers both states; what
    matters here is that the repository bar is unaffected either way.
    """
    body = client.get("/apps").text

    assert 'data-tab-panel="play"' in body
    assert body.count("data-repo-query") == 1, "the repository panel keeps its own bar"

    # Ordered between the TPC and repository tabs, as asked.
    assert (
        body.index('data-tab="tpc"')
        < body.index('data-tab="play"')
        < body.index('data-tab="repo"')
    )

    # The repository panel's own "what each source is" table no longer lists
    # Play, which would promise a search that panel does not perform.
    panel = body[body.index('data-tab-panel="repo"'):]
    panel = panel[: panel.index('data-tab-panel=', 10)] if 'data-tab-panel=' in panel[10:] else panel
    assert "IzzyOnDroid" in panel, "the repository table is in this slice"
    assert "Google Play" not in panel
