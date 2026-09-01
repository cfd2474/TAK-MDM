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

"""FILES policy spec.

Places curated files onto devices. Two things distinguish it from every other
policy type so far:

* An entry can be **optional** — offered to the device's user through the agent's
  marketplace rather than installed unconditionally (F4). This is the first place
  the desired state describes something the server *offers* instead of *requires*.
* An entry can carry **extraction** instructions, so a zip lands unpacked into a
  destination directory rather than as an archive (F5). The admin decides that, not
  the device.
"""

from __future__ import annotations

import enum
import uuid
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy


class Availability(str, enum.Enum):
    REQUIRED = "required"  # installed unconditionally
    OPTIONAL = "optional"  # offered in the marketplace, user chooses


class OverwriteRule(str, enum.Enum):
    ALWAYS = "always"
    IF_NEWER = "if_newer"
    IF_ABSENT = "if_absent"


class FileEntry(BaseModel):
    """One file, its destination, and how it should be placed."""

    model_config = ConfigDict(extra="forbid")

    file_id: uuid.UUID
    # Directory the file is written into. Absolute device path, e.g. /sdcard/atak.
    dest_path: str = Field(min_length=1, max_length=512)
    availability: Availability = Availability.REQUIRED
    overwrite: OverwriteRule = OverwriteRule.IF_NEWER

    extract: bool = False
    # Where an archive's contents land. Defaults to dest_path when extracting.
    extract_to: str | None = Field(default=None, max_length=512)

    # Shown in the marketplace. Falls back to the managed file's own name.
    # Whether the MDM keeps this file present, or places it once and leaves it.
    #
    # **The MDM never deletes a managed file.** Deployment is write-only, so this
    # governs replacement, not removal:
    #
    #   on  - re-push whenever the file is missing or the wrong size on the device
    #   off - place it once; if the user removes it, it stays removed until they
    #         ask for it again from the agent's marketplace
    #
    # Left unset it derives from the tier, which is what each one already means:
    # a *required* file that has vanished should come back, and an *optional* one
    # the user took and then deleted was their decision to make.
    persist: bool | None = None

    title: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _check_extraction(self) -> FileEntry:
        if self.extract_to and not self.extract:
            raise ValueError("extract_to is set but extract is false")
        if self.extract and not self.extract_to:
            # Defaulting rather than rejecting: "unzip it here" is the obvious intent
            # and forcing the admin to repeat the path twice invites a mismatch.
            object.__setattr__(self, "extract_to", self.dest_path)
            # Mark it explicitly set, or persistence with exclude_unset drops the
            # value we just derived and the device receives extract_to: null.
            self.__pydantic_fields_set__.add("extract_to")
        return self

    #: Absolute destinations Android will actually let the agent write to. A path
    #: outside these resolves against the filesystem root, where nothing is
    #: writable.
    _DEVICE_ROOTS = ("/sdcard/", "/storage/emulated/0/")

    @model_validator(mode="after")
    def _default_persist(self) -> FileEntry:
        """Derive `persist` from the tier when the admin has not said.

        Marked explicitly set for the same reason `extract_to` is (D50): with
        `exclude_unset` persistence a derived value is otherwise dropped, and the
        device receives `persist: null` and has to guess.
        """
        if self.persist is None:
            object.__setattr__(
                self, "persist", self.availability is Availability.REQUIRED
            )
            self.__pydantic_fields_set__.add("persist")
        return self

    @model_validator(mode="after")
    def _reject_unwritable_root(self) -> FileEntry:
        """Catch a destination the device could never write, at publish time.

        `/atak/imagery` is how ATAK paths are conventionally written and it is a
        trap: an absolute path resolves from the **filesystem root**, not external
        storage, so it fails on every device with a permission error that says
        nothing about the real mistake. Rejecting here means the operator is told
        while they are still looking at the policy — the same reasoning as catching
        signature pinning at upload rather than on the tablet.
        """
        for value in (self.dest_path, self.extract_to):
            if not value:
                continue
            path = value.replace("\\", "/")
            if not path.startswith("/"):
                continue  # relative: resolved against external storage
            if path.startswith(self._DEVICE_ROOTS) or path.rstrip("/") == "/sdcard":
                continue
            raise ValueError(
                f"{value!r} is an absolute path outside device storage, so nothing "
                f"can write there. Did you mean '/sdcard{value}'?"
            )
        return self

    @model_validator(mode="after")
    def _reject_traversal(self) -> FileEntry:
        for value in (self.dest_path, self.extract_to):
            if value and ".." in value.replace("\\", "/").split("/"):
                raise ValueError(f"path must not contain '..': {value}")
        return self


class FilesSpec(PolicySpec):
    entries: Annotated[
        list[FileEntry] | None,
        Merge(
            MergeStrategy.MERGE_BY_KEY,
            key="file_id",
            note="Stacked FILES policies union by file; the highest-ranked entry "
            "wins a collision on the same file.",
        ),
    ] = None
