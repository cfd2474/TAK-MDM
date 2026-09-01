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

    # ⚠️ Blocked means **hidden, not removed**. `setApplicationHidden` leaves the
    # app, its code and its data on the device; it simply cannot be seen or
    # launched, and unblocking restores it instantly. That is the right tool for a
    # temporary restriction and the wrong one for reclaiming storage or handing a
    # device on — use `removed_packages` for that.
    blocked_packages: Annotated[list[str] | None, Merge(MergeStrategy.UNION)] = None

    # Packages that must **not be installed**. Uninstalled outright, destroying
    # their data and reclaiming their storage.
    #
    # State rather than a command (D5/D6): "this device must not have X" is a
    # property to converge on, so a tablet that was dark for three weeks removes it
    # on return. Dropping an app from `required_apps` deliberately does *not* remove
    # it — "no longer required" and "must be gone" are different claims, and
    # conflating them would delete apps every time a policy was tidied.
    #
    # UNION for the same reason as the blocklist: with several policies stacked, any
    # one of them saying "not this" is the restrictive answer, and a merge that
    # could drop that instruction would be a policy that silently fails to remove.
    removed_packages: Annotated[list[str] | None, Merge(MergeStrategy.UNION)] = None

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
