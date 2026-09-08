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

"""APKPure, reached through EFF's `apkeep` (W98).

⚠️ **apkeep is never actually run here.** The binary is stubbed, which keeps the
suite offline and — more usefully — lets the failures be *arranged*: a missing
binary, a non-zero exit, a success that produces no file. Those are the paths
worth having tests for, and none can be produced by asking APKPure nicely.
"""

from __future__ import annotations

import hashlib
import pathlib
from types import SimpleNamespace

import pytest

from app.db.models import Device
from app.services import repo_import
from app.services.app_sources.apkpure import ApkPureSource
from app.services.app_sources.base import SourceError, SourceVersion
from tests.apk_fixtures import build_apk


class _Apkeep:
    """A stand-in for the apkeep binary."""

    LISTING = "Versions available for net.osmand on APKPure:\n| 5.3.10, 5.4.3, 5.4.4\n"

    def __init__(self, *, stdout="", returncode=0, writes=None, stderr=""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr
        self.writes = writes
        self.calls: list[list[str]] = []

    def __call__(self, args, **kwargs):
        self.calls.append(args)
        if self.writes and kwargs.get("cwd"):
            for name, payload in self.writes.items():
                pathlib.Path(kwargs["cwd"], name).write_bytes(payload)
        return SimpleNamespace(
            stdout=self.stdout, stderr=self.stderr, returncode=self.returncode
        )


@pytest.fixture
def installed(monkeypatch):
    """apkeep is not on the test machine, and that is not what these test."""
    monkeypatch.setattr(
        ApkPureSource, "available", property(lambda self: True), raising=False
    )


def _version(name: str = "5.4.4") -> SourceVersion:
    return SourceVersion(
        package_name="net.osmand",
        version_code=None,
        version_name=name,
        version_key=name,
    )


# --------------------------------------------------------------------------- #
# Listing
# --------------------------------------------------------------------------- #


def test_versions_are_parsed_from_apkeeps_listing(installed):
    source = ApkPureSource(runner=_Apkeep(stdout=_Apkeep.LISTING))

    versions = source.versions("net.osmand")

    assert [v.version_name for v in versions] == ["5.4.4", "5.4.3", "5.3.10"]
    assert versions[0].version_key == "5.4.4"


def test_a_version_code_is_not_invented(installed):
    """⚠️ APKPure states names, not codes.

    `None` is the honest answer until the file is read; a fabricated number would
    land in the field the library keys builds on.
    """
    source = ApkPureSource(runner=_Apkeep(stdout=_Apkeep.LISTING))

    assert all(v.version_code is None for v in source.versions("net.osmand"))


def test_nothing_is_claimed_about_a_checksum(installed):
    """APKPure publishes none, so `verifiable` must read False rather than the
    download quietly looking checked."""
    source = ApkPureSource(runner=_Apkeep(stdout=_Apkeep.LISTING))

    assert source.versions("net.osmand")[0].verifiable is False


# --------------------------------------------------------------------------- #
# ⚠️ The architecture, which the live test proved cannot be left to the default
# --------------------------------------------------------------------------- #


def test_listing_pins_the_architecture(installed):
    """apkeep documents its default as preferring arm64-v8a and returned an
    armeabi-v7a build anyway, for an arm64-only fleet — R19's exact shape."""
    runner = _Apkeep(stdout=_Apkeep.LISTING)

    ApkPureSource(runner=runner).versions("net.osmand")

    assert any("arch=arm64-v8a" in arg for arg in runner.calls[0])


def test_downloading_pins_the_architecture_too(installed):
    apk = build_apk("net.osmand", 5404)
    runner = _Apkeep(writes={"net.osmand@5.4.4.xapk": apk})

    got = ApkPureSource(runner=runner).download(_version())

    assert any("arch=arm64-v8a" in arg for arg in runner.calls[0])
    assert got.data == apk
    assert got.sha256 == hashlib.sha256(apk).hexdigest()
    assert got.verified is False


# --------------------------------------------------------------------------- #
# ⚠️ No search, and saying so honestly
# --------------------------------------------------------------------------- #


def test_a_name_is_not_a_search(installed):
    """apkeep answers for an exact package id only. Returning nothing for a name
    is a property of the source, which the console explains rather than letting it
    look like an outage."""
    runner = _Apkeep(stdout=_Apkeep.LISTING)
    source = ApkPureSource(runner=runner)

    assert source.search("osmand") == []
    assert runner.calls == [], "no lookup is attempted for something that is not an id"


def test_an_exact_package_id_is_confirmed(installed):
    source = ApkPureSource(runner=_Apkeep(stdout=_Apkeep.LISTING))

    assert [a.package_name for a in source.search("net.osmand")] == ["net.osmand"]


# --------------------------------------------------------------------------- #
# Failure, arranged
# --------------------------------------------------------------------------- #


def test_something_that_is_not_a_package_never_reaches_a_command_line(installed):
    runner = _Apkeep()
    source = ApkPureSource(runner=runner)

    with pytest.raises(SourceError):
        source.versions("net.osmand; rm -rf /")
    assert runner.calls == []


def test_a_missing_binary_is_explained_rather_than_thrown():
    source = ApkPureSource(binary="definitely-not-installed", runner=_Apkeep())

    with pytest.raises(SourceError) as raised:
        source.versions("net.osmand")

    assert "not installed" in str(raised.value)


def test_apkeep_failing_is_reported_in_its_own_words(installed):
    runner = _Apkeep(returncode=1, stderr="app not found on APKPure")

    with pytest.raises(SourceError) as raised:
        ApkPureSource(runner=runner).versions("net.osmand")

    assert "app not found" in str(raised.value)


def test_success_with_no_file_is_still_a_failure(installed):
    """apkeep exiting 0 while producing nothing would otherwise import silence."""
    with pytest.raises(SourceError) as raised:
        ApkPureSource(runner=_Apkeep(writes={})).download(_version())

    assert "produced no file" in str(raised.value)


# --------------------------------------------------------------------------- #
# ⚠️ The end of the R19 chain, for the source most likely to serve one
# --------------------------------------------------------------------------- #


def test_a_32_bit_build_is_still_caught_before_import(db):
    """The live test's first APKPure fetch was `armeabi-v7a` for an arm64-only
    fleet. APKPure declares no ABIs, so the catch happens on what the file turns
    out to be — named by device, before anything is deployed.
    """
    db.add(Device(serial_number="SM-X520", supported_abis="arm64-v8a", sdk_int=36))
    db.commit()

    checked = repo_import.preflight(
        db,
        SourceVersion(
            package_name="net.osmand",
            version_code=5404,
            version_name="5.4.4",
            abis=("armeabi-v7a",),
            source="apkpure",
        ),
    )

    assert any("cannot run this build" in w for w in checked.warnings)
    assert any("SM-X520" in w for w in checked.warnings)
    assert any("no checksum" in w for w in checked.warnings)
