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

"""APP_CATALOG policy spec."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy

_PACKAGE_PATTERN = r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$"


class RequiredApp(BaseModel):
    """One app the device must have installed."""

    model_config = ConfigDict(extra="forbid")

    package_name: str = Field(pattern=_PACKAGE_PATTERN)
    min_version_code: int | None = Field(default=None, ge=0)
    # Content address of the APK/XAPK artifact (Chunk 4). Absent means "any build
    # satisfying min_version_code", which is how a policy expresses a floor without
    # pinning a specific upload.
    artifact_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    auto_update: bool = True


class AppCatalogSpec(PolicySpec):
    required_apps: Annotated[
        list[RequiredApp] | None,
        Merge(MergeStrategy.MERGE_BY_KEY, key="package_name"),
    ] = None

    blocked_packages: Annotated[list[str] | None, Merge(MergeStrategy.UNION)] = None

    # INTERSECT is the correct "most restrictive" reading of an allowlist but it
    # surprises people: stacking two allowlists yields only their overlap, which can
    # be empty. Surfaced in the preview diff before publish (R4).
    allowed_packages: Annotated[
        list[str] | None,
        Merge(
            MergeStrategy.INTERSECT,
            note="Stacking allowlists yields only their overlap, which may be empty.",
        ),
    ] = None

    # No natural ordering between two kiosk apps — someone has to lose, loudly.
    kiosk_package: Annotated[str | None, Merge(MergeStrategy.HIGHEST_RANK)] = Field(
        default=None, pattern=_PACKAGE_PATTERN
    )
