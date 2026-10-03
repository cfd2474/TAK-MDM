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

"""COMPLIANCE policy spec — rules a device must keep meeting (W323).

Each field is one rule, off when unset. The server checks them against what the
device reports (`app/services/compliance_rules.py`), on every check-in and on
the periodic alert pass.

⚠️ **Rules only, for now (W323 D-d).** The graded response (suspend apps, lock,
wipe) arrives with chunk 2, when the agent can carry it out. Offering those
settings before then would let an operator save a consequence that never
happens, which is worse than offering nothing.

⚠️ **"Strictest wins" when policies stack.** The rules are phrased as
requirements, so for the yes/no ones MAX is the strict choice (True beats
False), not MOST_RESTRICTIVE, which is for "allow …" switches where False wins.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import Field

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy

_DEVICE = "Device"
_SETTINGS = "Security settings"
_ATAK = "ATAK"
_CONTACT = "Contact"


class ComplianceSpec(PolicySpec):
    # --- Device ------------------------------------------------------------- #

    min_android_version: Annotated[int | None, Merge(MergeStrategy.MAX)] = Field(
        default=None, ge=10, le=30,
        title="Minimum Android version",
        description="The device's Android major version must be at least this, e.g. 14.",
        json_schema_extra={"ui_group": _DEVICE},
    )

    max_patch_age_days: Annotated[int | None, Merge(MergeStrategy.MIN)] = Field(
        default=None, ge=1, le=3650,
        title="Maximum security patch age",
        description=(
            "The device's Android security patch must be no older than this many "
            "days. The patch date is the device's own, from Settings → About."
        ),
        json_schema_extra={"ui_group": _DEVICE, "ui_unit": "days"},
    )

    require_encryption: Annotated[bool | None, Merge(MergeStrategy.MAX)] = Field(
        default=None,
        title="Storage encrypted",
        description=(
            "The device's storage must be encrypted. Every device on Android 10 or "
            "later is, so this mainly catches an unusual build."
        ),
        json_schema_extra={"ui_group": _DEVICE, "ui_true": "Required", "ui_false": "Not checked"},
    )

    # --- Security settings ---------------------------------------------------- #

    require_password_sufficient: Annotated[bool | None, Merge(MergeStrategy.MAX)] = Field(
        default=None,
        title="Passcode meets the Password policy",
        description=(
            "The device's current passcode must satisfy its Password policy, as "
            "Android itself judges it."
        ),
        json_schema_extra={"ui_group": _SETTINGS, "ui_true": "Required", "ui_false": "Not checked"},
    )

    require_usb_debugging_off: Annotated[bool | None, Merge(MergeStrategy.MAX)] = Field(
        default=None,
        title="USB debugging off",
        json_schema_extra={"ui_group": _SETTINGS, "ui_true": "Required", "ui_false": "Not checked"},
    )

    require_developer_options_off: Annotated[bool | None, Merge(MergeStrategy.MAX)] = Field(
        default=None,
        title="Developer options off",
        json_schema_extra={"ui_group": _SETTINGS, "ui_true": "Required", "ui_false": "Not checked"},
    )

    require_unknown_sources_blocked: Annotated[bool | None, Merge(MergeStrategy.MAX)] = Field(
        default=None,
        title="Installs from unknown sources blocked",
        description=(
            "The device must not allow its user to install apps from unknown "
            "sources. Set it under Restrictions; this checks that it holds."
        ),
        json_schema_extra={"ui_group": _SETTINGS, "ui_true": "Required", "ui_false": "Not checked"},
    )

    # --- ATAK ------------------------------------------------------------------ #

    min_atak_version: Annotated[
        str | None,
        Merge(
            MergeStrategy.HIGHEST_RANK,
            note="A version string, which MAX would compare as text (5.10 < 5.9); "
                 "the highest-ranked policy's value is used.",
        ),
    ] = Field(
        default=None, pattern=r"^\d+\.\d+(\.\d+)?$",
        title="Minimum ATAK version",
        description="ATAK must be installed at this version or later, e.g. 5.8.0.",
        json_schema_extra={"ui_group": _ATAK},
    )

    require_atlas_plugin_running: Annotated[bool | None, Merge(MergeStrategy.MAX)] = Field(
        default=None,
        title="ATLAS plugin running",
        description="The ATLAS plugin must be reporting from inside ATAK.",
        json_schema_extra={"ui_group": _ATAK, "ui_true": "Required", "ui_false": "Not checked"},
    )

    # --- Contact ----------------------------------------------------------------- #

    max_checkin_age_hours: Annotated[int | None, Merge(MergeStrategy.MIN)] = Field(
        default=None, ge=1, le=8760,
        title="Checked in within",
        description="The device must have checked in within this many hours.",
        json_schema_extra={"ui_group": _CONTACT, "ui_unit": "hours"},
    )
