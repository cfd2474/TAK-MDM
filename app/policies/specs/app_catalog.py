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
    #: Uninstall this app once no policy requires it any more (W192).
    #:
    #: ⚠️ **Opt-in, and the default is what happens today.** `wifiByPolicy` on
    #: the agent already removes a network profile the policy stops listing, and
    #: does it unconditionally — which is right, because a network profile has
    #: nothing in it. An app does: uninstalling destroys its data, and doing that
    #: to every fielded device the day this shipped is not a default anyone
    #: chose. So an operator turns it on per app, where they can see which app
    #: they are saying it about.
    #:
    #: ⚠️ **The device records this at install time, not at removal time**, and
    #: it cannot be otherwise: when the policy is withdrawn the policy is *gone*,
    #: and with it this field. Membership of the agent's `installedByPolicy` set
    #: is what survives to answer the question later.
    remove_when_no_longer_required: bool = False


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
    def _atak_belongs_in_its_own_section(self):
        """ATAK is refused in required apps and the allowlist (W141).

        ⚠️ **By package name, which is why this can live in the model at all.**
        `atak_compat.is_atak` is a prefix test on `com.atakmap.app`, so it needs
        no database and holds on every path into a policy — the console form,
        the API, a restored template. Its sibling rule, "no plugins here
        either", cannot: a plugin is a build that *declares a plugin-api*, which
        is a column, so that one is enforced where a session exists.

        Refused rather than migrated silently. An entry that moved itself would
        leave the operator's policy saying something they did not write, and the
        two sections differ in more than tidiness — the ATAK section is where a
        version mismatch can be reasoned about at all.
        """
        from app.services import atak_compat

        offenders = sorted(
            {
                entry.package_name
                for entry in (self.required_apps or [])
                if atak_compat.is_atak(entry.package_name)
            }
            | {
                name
                for name in (self.allowed_packages or [])
                if atak_compat.is_atak(name)
            }
        )
        if offenders:
            names = ", ".join(offenders)
            raise ValueError(
                f"{names} belongs in ATAK Core and Plugins, not in required apps "
                "or the allowlist. That section picks the ATAK build every plugin "
                "is checked against, which this one cannot do."
            )
        return self

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

        ⚠️ **Counted across required apps, ATAK Core and plugins together**
        (W141). A package named twice is the same Android slot filled twice
        however it is spelled, and checking each field on its own would let a
        plugin row and a required entry quietly disagree about one app — the
        exact failure above, wearing the new section as a disguise.
        """
        seen: dict[str, int] = {}
        entries = list(self.required_apps or []) + list(self.atak_plugins or [])
        if self.atak_core is not None:
            entries.append(self.atak_core)
        for entry in entries:
            seen[entry.package_name] = seen.get(entry.package_name, 0) + 1

        duplicates = sorted(name for name, count in seen.items() if count > 1)
        if duplicates:
            names = ", ".join(duplicates)
            raise ValueError(
                f"{names} appears more than once across required apps, ATAK Core "
                "and plugins. Only one build of a package can be installed on a "
                "device, so the second entry cannot take effect — if these are "
                "builds for different ATAK versions, put them in separate "
                "policies and assign each to the devices running that ATAK."
            )
        return self

    # ----------------------------------------------------------------------- #
    # ATAK Core and Plugins (W141)
    #
    # ⚠️ **The same `RequiredApp` shape as required apps, deliberately.** ATAK
    # and its plugins *are* required apps; they are sorted into their own
    # section because that is where a compatibility rule can be stated, not
    # because they install differently. `resolve_required_apps` folds all three
    # fields into one list, so the agent learns nothing new.
    # ----------------------------------------------------------------------- #

    atak_core: Annotated[
        RequiredApp | None, Merge(MergeStrategy.HIGHEST_RANK)
    ] = Field(
        default=None,
        title="ATAK Core",
        description=(
            "The ATAK build installed on this device, and the version every "
            "plugin below is checked against. ⚠️ One per device: two policies "
            "naming different ATAK builds is reported as a conflict, and only "
            "the higher-ranked one is installed."
        ),
        json_schema_extra={"ui_group": "ATAK Core and Plugins", "ui_control": "atak_core"},
    )

    atak_plugins: Annotated[
        list[RequiredApp] | None,
        Merge(MergeStrategy.MERGE_BY_KEY, key="package_name"),
    ] = Field(
        default=None,
        title="ATAK plugins",
        description=(
            "Plugins installed alongside ATAK Core. A plugin only loads in the "
            "ATAK build it was compiled against, so one targeting a different "
            "version is flagged \u2014 as a warning, never a refusal."
        ),
        json_schema_extra={"ui_group": "ATAK Core and Plugins", "ui_control": "atak_plugins"},
    )

    storefront_id: Annotated[
        str | None, Merge(MergeStrategy.HIGHEST_RANK)
    ] = Field(
        default=None,
        title="ATLAS store",
        description=(
            "The shelf of apps a user may install for themselves on this device. "
            "One per policy — a device has one store, not several. "
            "⚠️ Two policies on the same device naming different storefronts is "
            "reported as a conflict: the higher-ranked one wins and the other's "
            "apps are simply not offered. Where both list the same app at "
            "different builds, only one can ever be installed, so the losing "
            "build is not a fallback — it is unreachable."
        ),
        json_schema_extra={"ui_group": "ATLAS store", "ui_control": "storefront"},
    )

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
        json_schema_extra={
            "ui_group": "Blocklist",
            "ui_control": "package_list",
            # Offers the store shortcuts above this list. Only here: the
            # allowlist is the other package list, and writing a store into it
            # would mean the opposite of what the operator asked for.
            "ui_store_toggles": True,
        },
    )

    # ⚠️ `removed_packages` was here: a second list that uninstalled outright and
    # refused to fall back to hiding. It is gone (W154), on the operator's call.
    #
    # It differed from the blocklist in exactly two ways — it hid nothing when an
    # uninstall failed, and it reported that failure — and for an ordinary
    # sideloaded app the two did the same thing. Two lists that behave identically
    # in the common case, and differ only for preinstalled apps, cost more in
    # confusion than the distinction was worth.
    #
    # ⚠️ What went with it: the ability to *demand* real removal and be told when
    # it did not happen. `blocked_packages` uninstalls what it can and hides what
    # it cannot, so on a preinstalled app the data and storage remain. If that
    # guarantee is ever needed again, it belongs as an option on the blocklist
    # rather than a parallel list.

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
