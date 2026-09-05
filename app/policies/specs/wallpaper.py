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

"""WALLPAPER policy spec.

Two slots, tablet and phone, because one image cannot suit both: a 16:9 phone
portrait crops to nothing useful on a 4:3 tablet landscape. Either may be left
empty, and a policy carrying only one applies that one everywhere — an operator
with a single-form-factor fleet should not have to upload the same picture twice.

**Which image a device gets is decided on the device** (D46). The desired state
carries whichever slots are filled and the agent picks using its own
`smallestScreenWidthDp`; the server never guesses at a screen it cannot see, and
nothing has to be recomputed when a device's configuration changes.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import Field, model_validator

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy


class WallpaperSpec(PolicySpec):
    tablet_file_id: Annotated[
        uuid.UUID | None, Merge(MergeStrategy.HIGHEST_RANK)
    ] = Field(
        default=None,
        title="Tablet wallpaper",
        description="Applied to devices at least 600dp wide (Android's own tablet line).",
        json_schema_extra={"ui_group": "Images", "ui_control": "image_file"},
    )

    phone_file_id: Annotated[
        uuid.UUID | None, Merge(MergeStrategy.HIGHEST_RANK)
    ] = Field(
        default=None,
        title="Phone wallpaper",
        description="Applied to devices narrower than 600dp.",
        json_schema_extra={"ui_group": "Images", "ui_control": "image_file"},
    )

    lock_screen: Annotated[bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)] = Field(
        default=None,
        title="Also set the lock screen",
        description="Apply the same image to the lock screen as well as the home screen.",
        json_schema_extra={"ui_group": "Images"},
    )

    prevent_user_change: Annotated[
        bool | None, Merge(MergeStrategy.MOST_RESTRICTIVE)
    ] = Field(
        default=None,
        title="Stop the user changing it",
        description=(
            "Sets DISALLOW_SET_WALLPAPER. The agent applies the image before "
            "imposing the restriction, because the restriction may block the agent "
            "too."
        ),
        json_schema_extra={"ui_group": "Images"},
    )

    @model_validator(mode="after")
    def _at_least_one_image(self):
        """A policy with neither slot filled does nothing at all.

        Rejected rather than accepted-and-inert: an operator who saves an empty
        wallpaper policy, assigns it, and sees no change would have no way to tell
        that from a policy that failed to apply.
        """
        if self.tablet_file_id is None and self.phone_file_id is None:
            raise ValueError(
                "a wallpaper policy needs at least one image — upload a tablet "
                "image, a phone image, or both"
            )
        return self
