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

"""The declared version, and why it is allowed to be hand-maintained (W144).

⚠️ `app/version.py` exists because a hand-maintained `version="0.1.0"` in
`main.py` went stale for a hundred work items. Reintroducing a version string
only became reasonable with a guard, and this is the guard: `VERSION` must match
the newest git tag, so a release that forgot to bump it fails here rather than
lying in a footer for months.
"""

from __future__ import annotations

import dataclasses
import re
import subprocess
from pathlib import Path

import pytest

from app.version import VERSION_FILE, BuildInfo, _resolve_version, build_info

ROOT = Path(__file__).resolve().parent.parent


def _newest_tag() -> str | None:
    if not (ROOT / ".git").exists():
        return None
    found = subprocess.run(
        ["git", "-C", str(ROOT), "describe", "--tags", "--abbrev=0"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    return found.stdout.strip() or None if found.returncode == 0 else None


# --------------------------------------------------------------------------- #
# ⚠️ The anti-staleness guard
# --------------------------------------------------------------------------- #


def test_the_declared_version_matches_the_newest_tag():
    """The whole reason a version string is allowed to exist here again."""
    tag = _newest_tag()
    if tag is None:
        pytest.skip("no tags reachable — not a release checkout")

    declared = VERSION_FILE.read_text(encoding="utf-8").strip()

    assert declared == tag.lstrip("v"), (
        f"VERSION says {declared!r} but the newest tag is {tag!r}. Bump VERSION "
        f"in the same commit you tag, or the footer and InfraTAK's update check "
        f"will both report a release this is not."
    )


def test_the_version_is_three_numbers():
    """InfraTAK compares these to decide whether an update exists, and it can
    only do that if they are ordered."""
    declared = VERSION_FILE.read_text(encoding="utf-8").strip()

    assert re.fullmatch(r"\d+\.\d+\.\d+", declared), declared


# --------------------------------------------------------------------------- #
# What the footer shows
# --------------------------------------------------------------------------- #


def test_the_footer_leads_with_the_version():
    info = BuildInfo(revision="abc1234", committed="2026-09-13", version="1.0.0")

    assert info.label == "v1.0.0"


def test_a_modified_build_still_says_so():
    """A version is a claim about released code; a dirty tree is not that."""
    info = BuildInfo(revision="abc1234", version="1.0.0", dirty=True)

    assert "modified" in info.label


def test_without_a_version_it_falls_back_to_the_revision():
    """⚠️ A working copy between tags is a real state and must not read as a
    release it is not."""
    info = BuildInfo(revision="abc1234", committed="2026-09-13")

    assert info.label == "build abc1234 · 2026-09-13"


def test_the_commit_is_still_reachable():
    """Showing the version must not cost the answer to "is this that code"."""
    info = BuildInfo(revision="abc1234", committed="2026-09-13",
                     version="1.0.0", source="file")

    assert "abc1234" in info.detail and "file" in info.detail


def test_unknown_stays_unknown():
    assert BuildInfo().label == "build unknown"


# --------------------------------------------------------------------------- #
# Resolution order
# --------------------------------------------------------------------------- #


def test_an_explicit_override_wins(monkeypatch):
    monkeypatch.setenv("TAKMDM_VERSION", "9.9.9")

    assert _resolve_version() == "9.9.9"


def test_a_leading_v_is_not_doubled(monkeypatch):
    """⚠️ The footer prints "v" itself. `v1.0.0` here would render `vv1.0.0`."""
    monkeypatch.setenv("TAKMDM_VERSION", "v2.3.4")

    assert _resolve_version() == "2.3.4"


def test_the_running_build_reports_a_version():
    """End to end, through the real resolver the app uses."""
    assert build_info().version == VERSION_FILE.read_text(encoding="utf-8").strip()
