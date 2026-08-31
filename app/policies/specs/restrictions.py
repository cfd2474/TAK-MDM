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
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy

_DENY_WINS = Merge(MergeStrategy.MOST_RESTRICTIVE)


class RestrictionsSpec(PolicySpec):
    allow_camera: Annotated[bool | None, _DENY_WINS] = None
    allow_screen_capture: Annotated[bool | None, _DENY_WINS] = None
    allow_bluetooth: Annotated[bool | None, _DENY_WINS] = None
    allow_usb_file_transfer: Annotated[bool | None, _DENY_WINS] = None
    allow_factory_reset: Annotated[bool | None, _DENY_WINS] = None
    allow_safe_mode: Annotated[bool | None, _DENY_WINS] = None
    allow_developer_options: Annotated[bool | None, _DENY_WINS] = None
    allow_install_unknown_sources: Annotated[bool | None, _DENY_WINS] = None
    allow_outgoing_calls: Annotated[bool | None, _DENY_WINS] = None
    allow_location_services: Annotated[bool | None, _DENY_WINS] = None

    screen_timeout_seconds: Annotated[int | None, Merge(MergeStrategy.MIN)] = Field(
        default=None, ge=15, le=3_600
    )
