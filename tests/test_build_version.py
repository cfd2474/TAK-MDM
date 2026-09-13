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

"""Which build the console says it is running (W102).

⚠️ **The value of a build footer is entirely in its truthfulness.** One that is
merely plausible gets believed, and then an operator debugs the wrong code. So
what is tested here is mostly what it refuses to claim.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import version as build_version
from app.version import BuildInfo, build_info, write_build_file


@pytest.fixture(autouse=True)
def _fresh():
    """The build is cached for the process; tests must not inherit each other's."""
    build_info.cache_clear()
    yield
    build_info.cache_clear()


# --------------------------------------------------------------------------- #
# What it refuses to invent
# --------------------------------------------------------------------------- #


def test_with_nothing_to_go_on_it_says_unknown(monkeypatch, tmp_path):
    """⚠️ Never a plausible-looking guess.

    A wrong build number is believed and sends someone debugging code that is not
    running. A missing one is merely unhelpful, which is the safer failure.
    """
    monkeypatch.delenv("TAKMDM_BUILD", raising=False)
    monkeypatch.delenv("TAKMDM_VERSION", raising=False)
    monkeypatch.setattr(build_version, "BUILD_FILE", tmp_path / "BUILD")
    monkeypatch.setattr(build_version, "VERSION_FILE", tmp_path / "VERSION")
    monkeypatch.setattr(build_version, "_ROOT", tmp_path)

    info = build_info()

    assert info.known is False
    assert info.version is None
    assert info.label == "build unknown"
    assert info.source == "none"


def test_a_build_file_without_a_revision_is_not_a_build(monkeypatch, tmp_path):
    """A truncated or half-written file must not read as an answer."""
    path = tmp_path / "BUILD"
    path.write_text("committed=2026-09-08\ndirty=false\n", encoding="utf-8")
    monkeypatch.delenv("TAKMDM_BUILD", raising=False)
    monkeypatch.setattr(build_version, "BUILD_FILE", path)
    monkeypatch.setattr(build_version, "_ROOT", tmp_path)

    assert build_info().known is False


# --------------------------------------------------------------------------- #
# Where it looks, and in what order
# --------------------------------------------------------------------------- #


def test_the_shipped_file_is_what_production_reads(monkeypatch, tmp_path):
    """⚠️ The deploy tarball excludes `.git`, so this file is the only carrier."""
    path = write_build_file(
        tmp_path / "BUILD",
        BuildInfo(revision="abc1234", committed="2026-09-08", dirty=False),
    )
    monkeypatch.delenv("TAKMDM_BUILD", raising=False)
    monkeypatch.delenv("TAKMDM_VERSION", raising=False)
    monkeypatch.setattr(build_version, "BUILD_FILE", path)
    monkeypatch.setattr(build_version, "VERSION_FILE", tmp_path / "absent")
    # ⚠️ And no git either: _resolve_version falls back to `git describe`, so
    # leaving _ROOT pointed at the real checkout would let this repo's own tag
    # answer a question the test is asking about a deployment without one.
    monkeypatch.setattr(build_version, "_ROOT", tmp_path)

    info = build_info()

    assert (info.revision, info.committed, info.source) == ("abc1234", "2026-09-08", "file")
    # ⚠️ The BUILD file carries the revision, not the release number (W144) —
    # so an unversioned build still reports the commit rather than inventing one.
    assert info.label == "build abc1234 · 2026-09-08"


def test_an_explicit_override_wins(monkeypatch, tmp_path):
    """For an image built by something other than this deploy."""
    monkeypatch.setenv("TAKMDM_BUILD", "ci-4821")
    monkeypatch.setattr(
        build_version,
        "BUILD_FILE",
        write_build_file(tmp_path / "BUILD", BuildInfo(revision="fromfile")),
    )

    assert build_info().revision == "ci-4821"


def test_a_dirty_tree_says_so(monkeypatch, tmp_path):
    """⚠️ Deploying uncommitted work is ordinary; labelling it with the last
    commit's hash alone would make the footer claim something false."""
    path = write_build_file(
        tmp_path / "BUILD", BuildInfo(revision="abc1234", committed="2026-09-08", dirty=True)
    )
    monkeypatch.delenv("TAKMDM_BUILD", raising=False)
    monkeypatch.setattr(build_version, "BUILD_FILE", path)

    assert "modified" in build_info().label


# --------------------------------------------------------------------------- #
# On the page
# --------------------------------------------------------------------------- #


def test_every_page_carries_the_footer(client: TestClient):
    """Injected centrally, for the reason the CSRF token is: a page that forgot
    would show nothing rather than fail, so nobody would ever notice."""
    from app.version import build_info

    label = build_info().label
    for path in ("/", "/apps", "/policies", "/admin"):
        body = client.get(path).text
        assert "site-footer" in body, path
        # The release label (W144), whatever it resolved to — asserting the
        # literal text here would just restate the implementation.
        assert label in body, path
        # ⚠️ And the revision stays reachable, in the tooltip.
        assert "revision " in body, path


# --------------------------------------------------------------------------- #
# Navigation (W105)
# --------------------------------------------------------------------------- #


def test_manage_links_to_the_fleet_page_not_the_site_root(client: TestClient):
    """⚠️ The root is not the fleet page on every host.

    `mdm.tak-solutions.com` redirects `/` to the enrolment page, which is what
    that hostname exists for — and while Manage pointed at `/`, the redirect
    swallowed it and Manage went to Enroll. A nav link names the page it opens
    rather than relying on what the root happens to mean where it is served.
    """
    body = client.get("/fleet").text

    assert 'href="/fleet"' in body
    assert '<a href="/" ' not in body, "no nav link depends on the root"


def test_the_fleet_page_answers_on_both_paths(client: TestClient):
    """`/` still works — it is the dashboard on the port that has no redirect."""
    assert client.get("/fleet").status_code == 200
    assert client.get("/").status_code == 200
