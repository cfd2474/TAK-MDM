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

"""ATAK_CONFIG policy spec (W90).

ATAK's own settings, and its plugins', expressed as policy. The values travel to
the device as a `.pref` document carried in ATAK's `enterpriseConfigurationPreferences`
managed-configuration key — ATAK's own designed route, which needs no file push
and no Knox (see `docs/ANDROID_PLATFORM_REFERENCE.md` §10).

⚠️ **The keys belong to ATAK, not to this schema.** They are read out of the
uploaded build at edit time (D91), 293 of them in 5.8.0.4, and they change
between releases. Pinning them here would mean redeploying the server to
configure a setting ATAK added — the same reasoning `AppConfig.values` already
follows for managed configuration.

Values are carried as strings and given their real type from the APK's own widget
class when the document is generated. `PreferenceControl` parses numbers
unguarded, so a value that cannot be its declared type is refused on the server
rather than discovered as a half-applied configuration on a tablet.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.policies.specs.base import PolicySpec
from app.policies.strategies import Merge, MergeStrategy

_PACKAGE_PATTERN = r"^[a-zA-Z][a-zA-Z0-9_]*(\.[a-zA-Z][a-zA-Z0-9_]*)+$"

#: An ATAK preference key. Deliberately permissive about shape — the plugins own
#: this namespace and use dots freely (`uastool.mavlink.mirror.udp_remote_ip`) —
#: but not about characters, because the key goes into an XML attribute and out
#: the far side through ATAK's own escaping.
_KEY_PATTERN = r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*$"


class CorePref(BaseModel):
    """One ATAK setting and the value it should hold."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(pattern=_KEY_PATTERN, max_length=255)
    value: str = Field(max_length=4096)


class PluginPrefs(BaseModel):
    """One plugin's settings — the keys its own APK declares.

    ``values`` is an open map for the same reason `AppConfig.values` is: the
    schema belongs to the plugin, is read from its APK at edit time, and differs
    per build.
    """

    model_config = ConfigDict(extra="forbid")

    package_name: str = Field(pattern=_PACKAGE_PATTERN)
    values: dict[str, str] = Field(default_factory=dict)


class AtakConfigSpec(PolicySpec):
    core_prefs: Annotated[
        list[CorePref] | None,
        Merge(
            MergeStrategy.MERGE_BY_KEY,
            key="key",
            note="Stacked ATAK policies compose setting by setting; the "
            "highest-ranked policy wins a clash on the same one.",
        ),
    ] = Field(
        default=None,
        title="ATAK core settings",
        description=(
            "Settings read from the ATAK build in the app library. Only what ATAK "
            "declares in its own preference screens can be set here."
        ),
        json_schema_extra={
            "ui_group": "ATAK Core Pref Config",
            "ui_control": "atak_core_prefs",
        },
    )

    plugin_prefs: Annotated[
        list[PluginPrefs] | None,
        Merge(
            MergeStrategy.MERGE_BY_KEY,
            key="package_name",
            note="One configuration per plugin: the highest-ranked policy's "
            "values win.",
        ),
    ] = Field(
        default=None,
        title="Plugin settings",
        description=(
            "Settings read from a plugin's own APK. Pick the plugin from the app "
            "library — plugins have no naming convention to find them by."
        ),
        json_schema_extra={
            "ui_group": "Plugin Pref Config",
            "ui_control": "plugin_prefs",
        },
    )

    @model_validator(mode="after")
    def _one_entry_per_setting(self):
        """Refuse the same setting twice in one policy.

        ⚠️ **A `.pref` document is applied in order, so a duplicate is not a
        conflict the resolver can arbitrate — it is the last one winning
        silently.** MERGE_BY_KEY settles a clash *between* policies and records
        who won; a policy that disagrees with itself has no such record, and the
        console would show both values as applied.
        """
        duplicates = _duplicates(entry.key for entry in self.core_prefs or [])
        if duplicates:
            names = ", ".join(duplicates)
            raise ValueError(
                f"{names} appears more than once in the ATAK core settings. A "
                f"setting holds one value, so the second entry would silently "
                f"replace the first."
            )

        duplicates = _duplicates(entry.package_name for entry in self.plugin_prefs or [])
        if duplicates:
            names = ", ".join(duplicates)
            raise ValueError(
                f"{names} is configured more than once. Put every setting for a "
                f"plugin in its one entry, or split them across policies and let "
                f"rank decide."
            )
        return self

    @model_validator(mode="after")
    def _plugin_entries_carry_something(self):
        """An empty configuration is never what an empty form meant.

        The device applies `.pref` entries; a plugin entry with no values
        contributes nothing to the document but does occupy the merge slot for
        that package — so a higher-ranked policy's *deliberately empty* entry
        would suppress a lower-ranked policy's real one, with nothing on screen
        to explain it.
        """
        empty = sorted(
            entry.package_name for entry in self.plugin_prefs or [] if not entry.values
        )
        if empty:
            names = ", ".join(empty)
            raise ValueError(
                f"{names} has no settings selected. Remove the plugin from this "
                f"policy, or choose at least one setting for it."
            )
        return self


def _duplicates(names) -> list[str]:
    seen: dict[str, int] = {}
    for name in names:
        seen[name] = seen.get(name, 0) + 1
    return sorted(name for name, count in seen.items() if count > 1)
