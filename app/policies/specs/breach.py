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

"""BREACH policy spec — what a device in the wrong hands destroys (W193).

⚠️ **This type carries the directories and nothing else.** Everything else
breach mode does — blocking the library, forcing a passcode, the wallpaper, the
lock note, the one-minute reporting interval — is an existing policy type in the
same profile. Each of those settings already has exactly one writer on the
device, and a second writer is silently undone by the next reconcile minutes
later, which is the trap `applyPassword` documents at length.

⚠️ **Absent is not the same as empty, and the difference is the whole feature.**
A device with no breach policy carries no `BREACH` section at all. A `purge_paths`
that defaulted to a list would put a destructive instruction into the payload of
every tablet in the fleet, where one bug in the applier is a fleet-wide wipe.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field, model_validator

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy

#: Absolute paths Android will actually let the agent reach. The same two roots
#: `FileEntry` writes to, for the same reason: anything else resolves against the
#: filesystem root, where the agent can neither write nor delete.
_DEVICE_ROOTS = ("/sdcard/", "/storage/emulated/0/")

#: Paths that must never be handed to a recursive delete.
#:
#: ⚠️ Not defence against a hostile operator — anyone who can edit this policy
#: can already wipe the device outright. It is defence against a **typo**:
#: `/sdcard` instead of `/sdcard/atak` is one missing word and it empties the
#: device's entire external storage, including the agent's own working files.
_REFUSED = {"/", "/sdcard", "/storage", "/storage/emulated", "/storage/emulated/0"}


class BreachSpec(PolicySpec):
    """Directories emptied on a device reported lost or stolen."""

    purge_paths: Annotated[
        list[str] | None,
        Merge(
            MergeStrategy.UNION,
            note="Stacked breach policies empty every directory either one names.",
        ),
    ] = Field(
        default=None,
        title="Directories to empty",
        description=(
            "Deleted, contents and all, on a device put into breach mode. "
            "Absolute device paths under /sdcard — for example /sdcard/Download "
            "or /sdcard/atak. This cannot be undone."
        ),
        json_schema_extra={"ui_group": "Breach", "ui_control": "path_list"},
    )

    @model_validator(mode="after")
    def _paths_are_reachable_and_not_the_whole_card(self) -> "BreachSpec":
        """Refuse at publish time what the device could only refuse in the field.

        ⚠️ Two different mistakes, told apart on purpose. A path outside device
        storage is the `/atak/imagery` trap `FileEntry` documents — it *looks*
        absolute and resolves from `/`, where nothing is writable, so the device
        fails with a permission error that says nothing about the real problem.
        A path that **is** device storage is the opposite: it would work
        perfectly and take everything with it.
        """
        for value in self.purge_paths or []:
            path = (value or "").replace("\\", "/").rstrip("/") or "/"

            if ".." in path.split("/"):
                raise ValueError(f"{value!r} escapes its directory")

            if path in _REFUSED:
                raise ValueError(
                    f"{value!r} is the whole of the device's storage. Name the "
                    f"directories to empty — /sdcard/Download, /sdcard/atak — "
                    f"rather than everything at once."
                )

            if not path.startswith("/"):
                raise ValueError(
                    f"{value!r} is a relative path. It resolves from the "
                    f"filesystem root on the device, not from storage: write "
                    f"'/sdcard/{path}'."
                )

            if not path.startswith(_DEVICE_ROOTS):
                raise ValueError(
                    f"{value!r} is an absolute path outside device storage, so "
                    f"there is nothing there to delete. Did you mean "
                    f"'/sdcard{path}'?"
                )
        return self
