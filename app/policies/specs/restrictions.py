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

"""RESTRICTIONS policy spec.

Every boolean here is phrased as an *allow* so that MOST_RESTRICTIVE is a plain
logical AND. Naming a field ``disallow_x`` would invert the meaning of the strategy
and is the kind of subtle trap that produces a permissive fleet by accident.

Field ``title`` / ``description`` / ``json_schema_extra`` drive the form-driven
editor (W10). ``ui_group`` buckets fields into sections; ``ui_true`` / ``ui_false``
are the words shown for an allow-boolean's two managed states.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy

_DENY_WINS = Merge(MergeStrategy.MOST_RESTRICTIVE)


def _allow(title: str, group: str, description: str = ""):
    """An allow-boolean field with its form metadata."""
    return Field(
        default=None,
        title=title,
        description=description,
        json_schema_extra={"ui_group": group, "ui_true": "Allowed", "ui_false": "Blocked"},
    )


class RestrictionsSpec(PolicySpec):
    allow_camera: Annotated[bool | None, _DENY_WINS] = _allow(
        "Camera", "Device functionality"
    )
    allow_screen_capture: Annotated[bool | None, _DENY_WINS] = _allow(
        "Screen capture", "Device functionality"
    )
    allow_safe_mode: Annotated[bool | None, _DENY_WINS] = _allow(
        "Safe mode", "Device functionality",
        "Booting into safe mode disables device-admin apps.",
    )
    allow_factory_reset: Annotated[bool | None, _DENY_WINS] = _allow(
        "Factory reset", "Device functionality"
    )
    allow_developer_options: Annotated[bool | None, _DENY_WINS] = _allow(
        "Developer options", "Device functionality",
        "Also gates USB/wireless debugging.",
    )
    allow_install_unknown_sources: Annotated[bool | None, _DENY_WINS] = _allow(
        "Install from unknown sources", "Device functionality"
    )

    allow_bluetooth: Annotated[bool | None, _DENY_WINS] = _allow(
        "Bluetooth", "Network & communication"
    )
    allow_outgoing_calls: Annotated[bool | None, _DENY_WINS] = _allow(
        "Outgoing calls", "Network & communication"
    )
    allow_location_services: Annotated[bool | None, _DENY_WINS] = _allow(
        "Location services", "Network & communication"
    )
    allow_usb_file_transfer: Annotated[bool | None, _DENY_WINS] = _allow(
        "USB file transfer", "Network & communication",
        "MTP/PTP access to device storage over USB.",
    )

    allow_credential_configuration: Annotated[bool | None, _DENY_WINS] = _allow(
        "Credential configuration", "Network & communication",
        "Whether the user may manage certificates in Settings. ⚠️ Denying this "
        "is what stops someone deleting a CA a Certificates policy installed — "
        "without it ATLAS only puts the certificate back at the next check-in, "
        "leaving a window where the device does not trust it. ⚠️ It blocks the "
        "whole credentials screen, so the user also cannot add or remove their "
        "own certificates.",
    )

    screen_timeout_seconds: Annotated[int | None, Merge(MergeStrategy.MIN)] = Field(
        default=None,
        ge=15,
        le=3_600,
        title="Screen timeout",
        description="Seconds of inactivity before the screen locks (15–3600).",
        json_schema_extra={"ui_group": "Display", "ui_unit": "seconds"},
    )
