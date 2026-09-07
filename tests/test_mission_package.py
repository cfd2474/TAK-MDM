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

"""Reading and writing ATAK data packages (W91, chunk B1).

Every rule asserted here is one `atak-civ` enforces in `isValid()` or in
`MissionPackageExtractorFactory`, cited in `docs/ANDROID_PLATFORM_REFERENCE.md`
§11. The tests are written against ATAK's requirements, not against this
module's conveniences — a validator that agrees only with itself would accept
packages the tablet then refuses, which is the whole failure this exists to
prevent.
"""

from __future__ import annotations

import io
import zipfile

import pytest

from app.artifacts import mission_package as mp


def _zip(entries: dict[str, bytes | str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def _manifest(
    *,
    name: str = "Ops Layer",
    uid: str = "1a2b3c",
    version: str = "2",
    contents: str = '<Content ignore="false" zipEntry="overlay.kml"/>',
    configuration: str | None = None,
    root: str = "MissionPackageManifest",
) -> str:
    config = configuration
    if config is None:
        config = (
            f'<Parameter name="uid" value="{uid}"/>'
            f'<Parameter name="name" value="{name}"/>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<{root} version="{version}">'
        f"<Configuration>{config}</Configuration>"
        f"<Contents>{contents}</Contents>"
        f"</{root}>"
    )


def _package(**kwargs) -> bytes:
    return _zip({mp.MANIFEST_NAME: _manifest(**kwargs), "overlay.kml": b"<kml/>"})


# --------------------------------------------------------------------------- #
# What ATAK accepts
# --------------------------------------------------------------------------- #


def test_a_conforming_package_is_read():
    package = mp.inspect(_package())

    assert package.name == "Ops Layer"
    assert package.uid == "1a2b3c"
    assert package.base_directory == ""
    assert [c.zip_entry for c in package.contents] == ["overlay.kml"]
    assert package.missing == ()


def test_a_manifest_nested_under_a_folder_is_found():
    """⚠️ The layout a Windows right-click "compress folder" produces.

    ATAK finds the manifest with `endsWith("MANIFEST/manifest.xml")`, so this is
    a perfectly valid package — and a validator that only looks at the zip root
    rejects a large share of the packages that exist in the wild.
    """
    package = mp.inspect(
        _zip({f"mydata/{mp.MANIFEST_NAME}": _manifest(), "mydata/overlay.kml": b"<kml/>"})
    )

    assert package.base_directory == "mydata/"
    assert package.manifest_path == f"mydata/{mp.MANIFEST_NAME}"


def test_content_paths_resolve_against_the_manifest_not_the_zip_root():
    """The other half of the same rule: `mydata/MANIFEST/...` means the manifest's
    `overlay.kml` is `mydata/overlay.kml`, and resolving from the root would
    report a file that is plainly there as missing."""
    package = mp.inspect(
        _zip({f"mydata/{mp.MANIFEST_NAME}": _manifest(), "mydata/overlay.kml": b"<kml/>"})
    )
    assert package.missing == ()


def test_a_package_with_no_contents_is_still_valid():
    """`MissionPackageContents.isValid()` returns true unconditionally, so an
    empty Contents is ATAK-legal even though building one is refused."""
    package = mp.inspect(_zip({mp.MANIFEST_NAME: _manifest(contents="")}))
    assert package.content_count == 0


def test_a_named_file_that_is_absent_is_reported_but_not_fatal():
    """ATAK tolerates it, so refusing would be stricter than the device. The
    operator still wants telling."""
    package = mp.inspect(_zip({mp.MANIFEST_NAME: _manifest()}))

    assert package.missing == ("overlay.kml",)
    assert package.name == "Ops Layer"


def test_an_ignored_entry_is_not_reported_missing():
    package = mp.inspect(
        _zip({mp.MANIFEST_NAME: _manifest(contents='<Content ignore="true" zipEntry="gone.kml"/>')})
    )
    assert package.missing == ()


# --------------------------------------------------------------------------- #
# What it refuses, and why the operator is told
# --------------------------------------------------------------------------- #


def test_a_zip_without_a_manifest_is_refused_and_says_atak_would_take_it():
    """⚠️ This is an MDM rule, not ATAK's.

    `GetExtractor` falls back to `PlainZipExtractor`, so ATAK *would* unpack it —
    just without any of the manifest's placement semantics. The message has to
    say that, or the operator concludes their file is broken.
    """
    with pytest.raises(mp.DataPackageError) as raised:
        mp.inspect(_zip({"overlay.kml": b"<kml/>"}))

    message = str(raised.value)
    assert "MANIFEST/manifest.xml" in message
    assert "plain zip" in message
    assert "Create Data Package" in message


def test_something_that_is_not_a_zip_is_refused():
    with pytest.raises(mp.DataPackageError) as raised:
        mp.inspect(b"not a zip at all")
    assert "not a readable zip" in str(raised.value)


def test_a_manifest_missing_the_uid_parameter_is_refused():
    """`MissionPackageConfiguration.isValid()` demands both name and uid."""
    with pytest.raises(mp.DataPackageError) as raised:
        mp.inspect(_package(configuration='<Parameter name="name" value="Ops"/>'))
    assert "uid" in str(raised.value)


def test_a_manifest_missing_the_name_parameter_is_refused():
    with pytest.raises(mp.DataPackageError) as raised:
        mp.inspect(_package(configuration='<Parameter name="uid" value="abc"/>'))
    assert "name" in str(raised.value)


def test_a_configuration_with_a_single_parameter_is_refused():
    """⚠️ ATAK requires `_parameters.size() > 1`, not merely the two it names.

    A manifest carrying only `uid` fails on both counts; one carrying only one
    parameter of any kind fails the count even if that parameter is required.
    """
    with pytest.raises(mp.DataPackageError):
        mp.inspect(_package(configuration='<Parameter name="uid" value="abc"/>'))


def test_a_manifest_of_the_wrong_version_is_refused():
    with pytest.raises(mp.DataPackageError) as raised:
        mp.inspect(_package(version="1"))
    assert "version 1" in str(raised.value)


def test_a_manifest_with_no_version_is_refused():
    package = _zip(
        {mp.MANIFEST_NAME: '<?xml version="1.0"?><MissionPackageManifest>'
         "<Configuration/><Contents/></MissionPackageManifest>"}
    )
    with pytest.raises(mp.DataPackageError) as raised:
        mp.inspect(package)
    assert "version" in str(raised.value)


def test_a_manifest_with_the_wrong_root_element_is_refused():
    with pytest.raises(mp.DataPackageError) as raised:
        mp.inspect(_package(root="MissionPackage"))
    assert "MissionPackageManifest" in str(raised.value)


def test_a_content_row_without_a_zip_entry_is_refused():
    with pytest.raises(mp.DataPackageError) as raised:
        mp.inspect(_package(contents='<Content ignore="false"/>'))
    assert "zipEntry" in str(raised.value)


def test_a_manifest_that_is_not_xml_is_refused():
    with pytest.raises(mp.DataPackageError) as raised:
        mp.inspect(_zip({mp.MANIFEST_NAME: "<<<not xml"}))
    assert "not valid XML" in str(raised.value)


# --------------------------------------------------------------------------- #
# Building one
# --------------------------------------------------------------------------- #


def test_a_built_package_passes_our_own_validator():
    """The round trip that matters: what Create Data Package produces is exactly
    what an operator could have uploaded."""
    built = mp.build("Ops Layer", [("overlay.kml", b"<kml/>"), ("notes.txt", b"hi")])
    package = mp.inspect(built)

    assert package.name == "Ops Layer"
    assert package.uid
    assert {c.zip_entry for c in package.contents} == {"overlay.kml", "notes.txt"}
    assert package.missing == ()


def test_a_built_package_has_the_manifest_where_atak_looks():
    built = mp.build("Ops", [("a.kml", b"<kml/>")])
    with zipfile.ZipFile(io.BytesIO(built)) as archive:
        names = archive.namelist()

    assert names[0] == mp.MANIFEST_NAME, "ATAK stops at the first matching entry"
    assert "a.kml" in names


def test_every_built_package_gets_its_own_uid():
    """The uid is how ATAK tells packages apart; two sharing one would collide on
    the device."""
    first = mp.inspect(mp.build("Ops", [("a.kml", b"x")]))
    second = mp.inspect(mp.build("Ops", [("a.kml", b"x")]))
    assert first.uid != second.uid


def test_a_name_with_xml_metacharacters_survives():
    package = mp.inspect(mp.build('Recon "North" & <East>', [("a.kml", b"x")]))
    assert package.name == 'Recon "North" & <East>'


def test_a_file_named_with_a_traversal_cannot_escape_the_package():
    built = mp.build("Ops", [("../../etc/passwd", b"x")])
    with zipfile.ZipFile(io.BytesIO(built)) as archive:
        assert "etc/passwd" in archive.namelist()
        assert not any(n.startswith("..") for n in archive.namelist())


def test_a_file_cannot_be_placed_inside_the_manifest_directory():
    """It would shadow or corrupt the manifest ATAK reads."""
    with pytest.raises(mp.DataPackageError) as raised:
        mp.build("Ops", [("MANIFEST/manifest.xml", b"x")])
    assert "reserved" in str(raised.value)


def test_two_files_with_the_same_name_are_refused():
    with pytest.raises(mp.DataPackageError) as raised:
        mp.build("Ops", [("a.kml", b"1"), ("a.kml", b"2")])
    assert "more than once" in str(raised.value)


def test_a_package_with_no_files_is_refused():
    """ATAK would accept it — Contents may be empty — but it imports as a silent
    no-op, which is never what the operator meant to build."""
    with pytest.raises(mp.DataPackageError) as raised:
        mp.build("Ops", [])
    assert "at least one file" in str(raised.value)


def test_a_package_with_no_name_is_refused():
    with pytest.raises(mp.DataPackageError):
        mp.build("   ", [("a.kml", b"x")])


def test_extra_configuration_parameters_are_carried_through():
    """`onReceiveImport` and friends are how a package says what to do on
    arrival; the builder must not silently drop them."""
    built = mp.build(
        "Ops", [("a.kml", b"x")], parameters={"onReceiveImport": "true", "remarks": "hi"}
    )
    package = mp.inspect(built)

    assert package.parameters["onReceiveImport"] == "true"
    assert package.parameters["remarks"] == "hi"


def test_a_built_package_gets_a_tidy_filename():
    """It is the name an operator reads in ATAK's own directory.

    "ATLAS test overlay (W91)" landed on hardware as
    `atlas-test-overlay--w91.zip` — " (" is two characters and each became its
    own hyphen.
    """
    from app.services.data_packages import _slug

    assert _slug("ATLAS test overlay (W91)") == "atlas-test-overlay-w91"
    assert _slug("Recon  ///  north") == "recon-north"
    assert _slug("   ") == "data-package"


# --------------------------------------------------------------------------- #
# ATAK's own "is this a data package" test
# --------------------------------------------------------------------------- #


def test_has_manifest_matches_atak_s_own_suffix_test():
    """`MissionPackageExtractorFactory.HasManifest` is `endsWith(...)` and nothing
    more — it never opens the manifest."""
    assert mp.has_manifest(mp.build("Ops", [("a.kml", b"x")])) is True
    assert mp.has_manifest(_zip({"overlay.kml": b"<kml/>"})) is False


def test_has_manifest_finds_a_nested_one():
    assert mp.has_manifest(_zip({f"mydata/{mp.MANIFEST_NAME}": _manifest()})) is True


def test_has_manifest_is_laxer_than_inspect_on_purpose():
    """⚠️ A broken manifest still makes it a data package.

    `inspect` asks "is this a good package"; `has_manifest` asks "was this meant
    to be one". The second is the right question when deciding whether an upload
    belongs in the general file path — a zip somebody built as a package does
    not become an ordinary file by being malformed.
    """
    broken = _zip({mp.MANIFEST_NAME: "<not even xml"})

    assert mp.has_manifest(broken) is True
    with pytest.raises(mp.DataPackageError):
        mp.inspect(broken)


def test_has_manifest_says_no_to_something_that_is_not_a_zip():
    assert mp.has_manifest(b"not a zip") is False
