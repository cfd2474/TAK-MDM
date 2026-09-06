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

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy

_PACKAGE_PATTERN = r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$"


class AppConfig(BaseModel):
    """One app's managed configuration — the keys it declares, and their values.

    ``values`` is deliberately an open map rather than a typed model: the schema
    belongs to the app, is read out of its APK at edit time (W49), and differs
    per build. Pinning it here would mean redeploying the server to configure an
    app that added a key.

    Values are carried as strings and coerced on the device, where the app's own
    declared type is authoritative. The console renders the right control from
    that same declaration, so an operator is not typing "true" into a free-text
    box unless the app really did declare a string.
    """

    model_config = ConfigDict(extra="forbid")

    package_name: str = Field(pattern=_PACKAGE_PATTERN)
    values: dict[str, str] = Field(default_factory=dict)


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
    ] = Field(
        default=None,
        title="Required apps",
        description="Apps the device must have installed. Pick from uploaded packages.",
        json_schema_extra={"ui_group": "Required apps", "ui_control": "app_list"},
    )

    @model_validator(mode="after")
    def _one_entry_per_package(self):
        """Refuse two entries for the same package in one policy.

        Rejected rather than warned about, unlike a plugin/ATAK mismatch: that has
        a plausible reason behind it, this does not. A package name **is** the
        app's identity on Android, so only one build of it can exist on a device.
        Two entries are not a choice between builds, they are the same slot filled
        twice.

        The trap this closes is a plugin pinned to two ATAK lines at once — say UAS
        Tool for 5.5.0 *and* for 5.8.0. Both are legitimate builds and an operator
        can reasonably think they are covering a mixed fleet, but Android will
        install exactly one. Without this the merge silently kept the first and
        recorded a "conflict", which is language meant for two policies disagreeing
        — here a policy disagrees with itself, and the resolved state never says
        which build won.

        Different ATAK lines mean different policies, assigned to different
        devices.
        """
        seen: dict[str, int] = {}
        for entry in self.required_apps or []:
            seen[entry.package_name] = seen.get(entry.package_name, 0) + 1

        duplicates = sorted(name for name, count in seen.items() if count > 1)
        if duplicates:
            names = ", ".join(duplicates)
            raise ValueError(
                f"{names} appears more than once in required apps. Only one build "
                "of a package can be installed on a device, so a second entry "
                "cannot take effect — if these are builds for different ATAK "
                "versions, put them in separate policies and assign each to the "
                "devices running that ATAK."
            )
        return self

    # The blacklist: make these packages unusable by whatever means each one allows.
    #
    # An ordinary app is uninstalled. One that ships with the device is **hidden**
    # instead — invisible in the launcher and unlaunchable — because a preinstalled
    # app cannot be removed. Verified on `SM-X520`: "uninstalling" Gmail only strips
    # the update and reverts to the factory build, and `PackageInstaller` reports
    # SUCCESS for it, so an agent trusting that status would report an app gone
    # while the user could still open it.
    #
    # **Reversible.** Taking a package off this list unhides it, and the agent only
    # unhides what it hid. Removal is not reversible; that is the trade for it
    # actually reclaiming the storage.
    blocked_packages: Annotated[list[str] | None, Merge(MergeStrategy.UNION)] = Field(
        default=None,
        title="Blocklist (hide / uninstall)",
        description="Made unusable: an ordinary app is uninstalled, a preinstalled "
        "one is hidden. Reversible.",
        json_schema_extra={"ui_group": "Blocklist", "ui_control": "package_list"},
    )

    # Packages that must **not be installed** — the strict form of the blacklist.
    #
    # Uninstalled outright, destroying their data and reclaiming their storage, and
    # the result is **verified afterwards**: a package that survives is reported as
    # a failure rather than quietly hidden. Use this when the storage or the data is
    # the point and "it did not actually work" is something you need to be told.
    # For preinstalled apps, which can never satisfy it, use `blocked_packages`.
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
    removed_packages: Annotated[list[str] | None, Merge(MergeStrategy.UNION)] = Field(
        default=None,
        title="Must-not-be-installed (uninstall, verified)",
        description="Uninstalled outright and checked afterwards. Not reversible. "
        "Use the blocklist for preinstalled apps.",
        json_schema_extra={"ui_group": "Must-not-be-installed", "ui_control": "package_list"},
    )

    # INTERSECT is the correct "most restrictive" reading of an allowlist but it
    # surprises people: stacking two allowlists yields only their overlap, which can
    # be empty. Surfaced in the preview diff before publish (R4).
    allowed_packages: Annotated[
        list[str] | None,
        Merge(
            MergeStrategy.INTERSECT,
            note="Stacking allowlists yields only their overlap, which may be empty.",
        ),
    ] = Field(
        default=None,
        title="Allowlist (only these may run)",
        description="If set, only these packages are permitted.",
        json_schema_extra={"ui_group": "Allowlist", "ui_control": "package_list"},
    )

    # No natural ordering between two kiosk apps — someone has to lose, loudly.
    kiosk_package: Annotated[str | None, Merge(MergeStrategy.HIGHEST_RANK)] = Field(
        default=None,
        pattern=_PACKAGE_PATTERN,
        title="Kiosk app",
        description="Lock the device to this single app. Leave unmanaged for a "
        "normal (non-kiosk) device.",
        json_schema_extra={"ui_group": "Kiosk"},
    )

    app_configs: Annotated[
        list[AppConfig] | None,
        Merge(
            MergeStrategy.MERGE_BY_KEY,
            key="package_name",
            note="One configuration per app: the highest-ranked policy's values win.",
        ),
    ] = Field(
        default=None,
        title="App configurations",
        description=(
            "Managed configuration pushed into an app — the keys the app itself "
            "declares. Only apps whose uploaded build advertises a configuration "
            "can be configured here."
        ),
        json_schema_extra={"ui_group": "App configurations", "ui_control": "app_configs"},
    )
