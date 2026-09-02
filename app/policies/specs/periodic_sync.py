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

"""PERIODIC_SYNC policy spec.

Whether the agent runs its periodic check-in as a foreground service (reliable
under battery/data saver and while locked, at the cost of a persistent
notification and a little battery) or a background service (lighter, but may not
sync while locked or saving power).
"""

from __future__ import annotations

import enum
from typing import Annotated

from pydantic import Field

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy


class SyncBehavior(str, enum.Enum):
    FOREGROUND = "foreground"
    BACKGROUND = "background"


class PeriodicSyncSpec(PolicySpec):
    sync_behavior: Annotated[
        SyncBehavior | None,
        Merge(
            MergeStrategy.HIGHEST_RANK,
            note="One operational choice with no safety ordering — the "
            "highest-ranked policy decides; an equal-rank clash is a conflict.",
        ),
    ] = Field(
        default=None,
        title="Periodic sync behavior",
        description=(
            "Foreground service keeps the device syncing with the server even "
            "under battery saver, data saver, or while locked — at the cost of a "
            "non-dismissible notification and slightly higher battery use. "
            "Background service is lighter but may not sync in those conditions, "
            "and policy changes can be delayed."
        ),
        json_schema_extra={
            "ui_group": "Periodic sync",
            "ui_choices": {
                "foreground": "Foreground service",
                "background": "Background service",
            },
        },
    )
