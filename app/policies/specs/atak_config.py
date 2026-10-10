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

import enum
import re
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


#: A TAK Server host: a DNS name or an IPv4 address.
#:
#: ⚠️ **No colons, so no IPv6 literal.** ATAK's connect string is
#: `host:port:proto`, split on `:` (`NetConnectString.fromString`), so an IPv6
#: address would be read as a host of its first group.
_HOST_PATTERN = r"^[A-Za-z0-9](?:[A-Za-z0-9.\-]{0,251}[A-Za-z0-9])?$"

_SHA256_PATTERN = r"^[a-f0-9]{64}$"


class TakServerAuth(str, enum.Enum):
    """How a device authenticates to the TAK Server (W365)."""

    #: Certificates uploaded to ATLAS, delivered in a data package.
    CERTIFICATE = "certificate"
    #: The ATLAS plugin enrols for a client certificate with a login.
    ENROLL = "enroll"


class TakServerProtocol(str, enum.Enum):
    """The streaming protocol, as ATAK's connect string spells it."""

    SSL = "ssl"
    QUIC = "quic"


def connection_address(row: dict) -> str:
    """`host:port:proto`, as ATAK spells a connect string, from a connection's fields.

    The one definition: the spec derives `address` with it, and the console
    matches a submitted row to its stored passwords with it.
    """
    host = str(row.get("host") or "").strip().lower()
    port = row.get("port") if row.get("port") not in (None, "") else 8089
    protocol = row.get("protocol") or TakServerProtocol.SSL.value
    protocol = getattr(protocol, "value", protocol)
    return f"{host}:{port}:{protocol}"


class TakServerConnection(BaseModel):
    """One TAK Server connection (W365).

    ⚠️ **Passwords are stored in the spec in clear text**, as the NETWORKS Wi-Fi
    password is: the device needs them. The console treats them as write-only
    (never rendered back; a blank field keeps the stored value), see
    `app/policies/secrets.py`.

    `address` is derived from host, port and protocol, never typed. It is the
    merge key, so two policies naming the same server are one connection and the
    higher-ranked policy's settings win. It is also the id the ATLAS plugin
    tracks the connection by (`docs/ATLAS-PLUGIN-CONTRACT.md`).
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    host: str = Field(max_length=253)
    port: int = Field(default=8089, ge=1, le=65535)
    protocol: TakServerProtocol = TakServerProtocol.SSL
    auth: TakServerAuth
    address: str = ""

    truststore_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    truststore_password: str | None = Field(default=None, max_length=256)
    client_cert_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    client_cert_password: str | None = Field(default=None, max_length=256)
    #: What the upload check found ("CN=…, expires 2028-04-05"), kept so the
    #: editor can show which file is attached without opening it again.
    truststore_description: str | None = Field(default=None, max_length=300)
    client_cert_description: str | None = Field(default=None, max_length=300)

    username: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, max_length=256)

    #: Remove the connection from ATAK once no policy names it (the operator's
    #: checkbox, like an app's `remove_when_no_longer_required`). Only the ATLAS
    #: plugin can remove a connection; ATAK's own configuration cannot.
    remove_when_no_longer_required: bool = False

    @model_validator(mode="before")
    @classmethod
    def _derive_address(cls, data: Any) -> Any:
        """`address` always follows host, port and protocol, whatever was sent."""
        if isinstance(data, dict):
            data = dict(data)
            data["host"] = str(data.get("host") or "").strip().lower()
            data["address"] = connection_address(data)
        return data

    @field_validator("host")
    @classmethod
    def _host_is_a_name_or_ipv4(cls, value: str) -> str:
        if not re.fullmatch(_HOST_PATTERN, value):
            raise ValueError(
                f"{value!r} is not a server name or IPv4 address. ATAK cannot use "
                f"an IPv6 address here, and the name must not include a port or "
                f"\"https://\"."
            )
        return value

    @model_validator(mode="after")
    def _what_each_auth_needs(self) -> "TakServerConnection":
        """Each auth carries exactly its own fields; the other kind's are dropped.

        Dropped rather than refused: the editor shows one set at a time, and a
        connection switched from one kind to the other would otherwise keep a
        password nothing uses.
        """
        if self.auth is TakServerAuth.CERTIFICATE:
            missing = [
                label
                for label, value in (
                    ("the CA truststore", self.truststore_sha256),
                    ("the truststore password", self.truststore_password),
                    ("the client certificate", self.client_cert_sha256),
                    ("the client certificate password", self.client_cert_password),
                )
                if not value
            ]
            if missing:
                raise ValueError(
                    f"TAK Server {self.name!r} uses uploaded certificates and needs "
                    f"{', '.join(missing)}."
                )
            self.username = None
            self.password = None
        else:
            missing = [
                label
                for label, value in (("a username", self.username), ("a password", self.password))
                if not value
            ]
            if missing:
                raise ValueError(
                    f"TAK Server {self.name!r} enrols for a certificate and needs "
                    f"{' and '.join(missing)}."
                )
            self.truststore_sha256 = None
            self.truststore_password = None
            self.client_cert_sha256 = None
            self.client_cert_password = None
            self.truststore_description = None
            self.client_cert_description = None
        return self


class AtakConfigSpec(PolicySpec):
    # ⚠️ Declared first so "Plugin behavior" stays the first sub-page of ATAK
    # Config, where the operator asked for it when it was a stub (D94). Sub-pages
    # are ordered by first-seen `ui_group`.
    auto_load_plugins: Annotated[
        list[Annotated[str, Field(pattern=_PACKAGE_PATTERN)]] | None,
        Merge(
            MergeStrategy.UNION,
            note="A plugin ticked in any policy is auto-loaded.",
        ),
    ] = Field(
        default=None,
        title="Auto-Load Plugin",
        description=(
            "The ATLAS plugin loads each ticked plugin inside ATAK as soon as it "
            "is installed and not loaded, including after an update, with no "
            "restart. ATAK still checks each plugin's version and signature. "
            "Unticking stops this but does not unload the plugin."
        ),
        json_schema_extra={
            "ui_group": "Plugin behavior",
            "ui_control": "auto_load_plugins",
        },
    )

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

    tak_servers: Annotated[
        list[TakServerConnection] | None,
        Merge(
            MergeStrategy.MERGE_BY_KEY,
            key="address",
            note="One connection per server address: the highest-ranked policy's "
            "settings for that server win.",
        ),
    ] = Field(
        default=None,
        title="TAK Server connections",
        description=(
            "Servers ATAK connects to. Uploaded certificates are delivered to ATAK "
            "directly. Enroll needs the ATLAS plugin 1.3.0 or later on the device, "
            "and the server's enrollment port (8446) must have a publicly trusted "
            "certificate, such as Let's Encrypt. Every device under this policy "
            "enrols as the same TAK Server user."
        ),
        json_schema_extra={
            "ui_group": "TAK Server connections",
            "ui_control": "tak_servers",
        },
    )

    @model_validator(mode="after")
    def _one_connection_per_server(self):
        """One entry per server address in one policy (rank settles it across policies)."""
        duplicates = _duplicates(entry.address for entry in self.tak_servers or [])
        if duplicates:
            raise ValueError(
                f"{', '.join(duplicates)} is set up more than once. Keep one "
                f"connection per server."
            )
        return self

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
