"""Where a managed file is allowed to land.

Copyright 2026 TAK-Solutions LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.policies.specs.files import FileEntry

FILE_ID = uuid.uuid4()


def entry(dest: str, **kwargs) -> FileEntry:
    return FileEntry(file_id=FILE_ID, dest_path=dest, **kwargs)


@pytest.mark.parametrize(
    "dest",
    ["/sdcard/atak/imagery", "/storage/emulated/0/atak/imagery", "atak/imagery", "/sdcard"],
)
def test_writable_destinations_are_accepted(dest):
    assert entry(dest).dest_path == dest


@pytest.mark.parametrize("dest", ["/atak/imagery", "/data/local/tmp", "/etc"])
def test_absolute_paths_outside_device_storage_are_refused(dest):
    # An absolute path resolves from the filesystem root, not external storage, so
    # it fails on every device with a permission error that says nothing about the
    # real mistake. Caught here, where the operator is still looking at the policy.
    with pytest.raises(ValidationError, match="outside device storage"):
        entry(dest)


def test_the_refusal_suggests_the_path_that_would_work():
    # "/atak/..." is how ATAK paths are conventionally written, so this is the
    # mistake an operator is most likely to make. Naming the fix is the difference
    # between a useful error and a puzzle.
    with pytest.raises(ValidationError, match=r"/sdcard/atak/imagery"):
        entry("/atak/imagery")


def test_extract_to_is_checked_as_well_as_dest_path():
    # Otherwise an archive extracts to an unwritable root while its own destination
    # looks perfectly fine.
    with pytest.raises(ValidationError, match="outside device storage"):
        entry("/sdcard/ok", extract=True, extract_to="/atak/unpacked")


def test_traversal_is_still_refused():
    with pytest.raises(ValidationError, match=r"\.\."):
        entry("/sdcard/atak/../../etc")


# --------------------------------------------------------------------------- #
# persist: replacement, never removal
# --------------------------------------------------------------------------- #


def test_required_files_persist_by_default():
    # "Required" already means present. A required file that vanished should come
    # back without the admin having to say so twice.
    assert entry("/sdcard/atak/imagery").persist is True


def test_optional_files_do_not_persist_by_default():
    # The user opted in, so deleting it was their decision. They can take it again
    # from the marketplace; the MDM re-imposing it would make "optional" a lie.
    assert entry("/sdcard/atak/imagery", availability="optional").persist is False


@pytest.mark.parametrize("availability,persist", [("required", False), ("optional", True)])
def test_persist_can_be_set_against_the_default(availability, persist):
    e = entry("/sdcard/atak/imagery", availability=availability, persist=persist)
    assert e.persist is persist


def test_the_derived_default_survives_persistence():
    # exclude_unset would drop a value the validator derived, and the device would
    # receive persist: null and have to guess — the same trap as extract_to (D50).
    assert "persist" in entry("/sdcard/atak/imagery").model_dump(exclude_unset=True)
