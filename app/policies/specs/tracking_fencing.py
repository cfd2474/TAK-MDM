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

"""TRACKING_FENCING policy spec — where devices are, and where they may be (W106).

The category has two sub-pages, and in this console **a sub-page is a `ui_group`**
(W12) — so both halves of *Tracking and fencing* live in this one spec rather than
in two policy types. Groups are ordered first-seen, which is why
`reporting_interval_minutes` is declared first: that is what puts **Device location
tracking above Geofencing**, as asked. Geofencing's fields arrive in C4, in a group
of their own declared below this one.

⚠️ **Zero means off, and off means the device stops reporting** — it does not mean
"report as rarely as possible". A tracking policy whose disabled value quietly
became "once a day" would be the worst kind of wrong: it reads as off in the
console and keeps writing positions.

⚠️ **`HIGHEST_RANK`, not `MIN`.** Two stacked policies both naming an interval
look like they should resolve to the more frequent one, and for most numbers here
that instinct is right. It is wrong for this field, because `0` is not a smaller
interval — it is a different kind of answer. Under `MIN`, a policy that turns
tracking *off* would win every contest and silently disable it fleet-wide; under
`MAX`, off would always lose and a device could never be exempted. Rank is the
only rule that lets an operator say either thing and have it hold.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy

_TRACKING = "Device location tracking"

#: Refuses an interval so long the feature is a lie. Six hours of silence looks
#: identical to a broken agent, and someone would spend an afternoon on it.
MAX_INTERVAL_MINUTES = 360


class TrackingFencingSpec(PolicySpec):
    reporting_interval_minutes: Annotated[
        int | None,
        Merge(
            MergeStrategy.HIGHEST_RANK,
            note="0 disables tracking, so the most frequent value cannot simply win.",
        ),
    ] = Field(
        default=None,
        ge=0,
        le=MAX_INTERVAL_MINUTES,
        title="Reporting interval (minutes)",
        description=(
            "How often the device records its position. 0 disables location "
            "tracking entirely — the device stops reporting and no new points are "
            "stored. Points are buffered on the device and delivered at the next "
            "check-in, so a device that is offline keeps its track rather than "
            "losing it."
        ),
        json_schema_extra={"ui_group": _TRACKING},
    )
