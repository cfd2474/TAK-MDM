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

import enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy

_TRACKING = "Device location tracking"

#: Refuses an interval so long the feature is a lie. Six hours of silence looks
#: identical to a broken agent, and someone would spend an afternoon on it.
MAX_INTERVAL_MINUTES = 360


_GEOFENCING = "Geofencing"


class RadioState(str, enum.Enum):
    """What a fence asks of a radio.

    `UNMANAGED` is not a third setting so much as the absence of one: the fence
    has no opinion, and whatever the device is doing continues. It is the default
    because a geofence about Bluetooth should not silently also be about Wi-Fi.
    """

    ON = "on"
    OFF = "off"
    UNMANAGED = "unmanaged"


class FenceTrigger(str, enum.Enum):
    """When a fence's actions apply.

    ⚠️ **A state, not an edge**, in the operator's own words: *"Entry will be when
    the device is inside the geofence, exit is when device is outside."* So the
    actions hold for as long as the condition holds and are released when it stops
    — which is also the only version that survives a reboot, a missed transition,
    or a device that was carried across the boundary while switched off. An
    edge-triggered fence that missed its edge stays wrong for ever.
    """

    ENTRY = "entry"
    EXIT = "exit"


class Geofence(BaseModel):
    """A circle on the map, and what changes on a device while it is inside or
    outside it (W106 C4)."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(
        min_length=1,
        max_length=64,
        description="What this fence is for. Shown in the device's log when it "
        "takes effect, so name the place rather than the rule.",
    )
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    radius_m: int = Field(
        ge=25,
        le=500_000,
        description=(
            "Metres from the centre. The floor is 25 m because a fence tighter "
            "than a consumer GPS fix would flap between inside and outside while "
            "the device sat still, applying and releasing its actions each time."
        ),
    )

    trigger: FenceTrigger = Field(
        default=FenceTrigger.ENTRY,
        description="Entry: the actions apply while the device is inside. "
        "Exit: while it is outside.",
    )

    password_enforced: bool = Field(
        default=False,
        description=(
            "Require a screen lock while this fence applies, and lock the device "
            "immediately so it takes effect at once. On a device with no password "
            "set, Android will prompt whoever is holding it to create one."
        ),
    )
    wifi: RadioState = Field(
        default=RadioState.UNMANAGED,
        description=(
            "Turning Wi-Fi off also cuts the path the server uses to reach this "
            "device. The fence is evaluated on the device itself, so leaving it "
            "restores the radio without needing the network — but a device "
            "switched off inside the fence and moved stays off until it gets a fix."
        ),
    )
    bluetooth: RadioState = Field(default=RadioState.UNMANAGED)

    reporting_interval_override_minutes: int = Field(
        default=0,
        ge=0,
        le=MAX_INTERVAL_MINUTES,
        description=(
            "Report position this often while the fence applies, instead of the "
            "usual interval. 0 means no override. Unlike the interval above, 0 "
            "here cannot mean off: a fence that stopped reporting would stop "
            "being able to tell it had been left."
        ),
    )


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

    geofences: Annotated[
        list[Geofence] | None, Merge(MergeStrategy.MERGE_BY_KEY, key="name")
    ] = Field(
        default=None,
        title="Geofences",
        description=(
            "Places this device behaves differently. Each fence is a coordinate "
            "and a radius; its actions apply while the device is inside it "
            "(Entry) or outside it (Exit), and are released when that stops being "
            "true. Where two active fences disagree, the more restrictive answer "
            "wins — a radio off beats it on, a password required beats not, and "
            "the shorter reporting interval beats the longer."
        ),
        json_schema_extra={"ui_group": _GEOFENCING, "ui_control": "geofences"},
    )
