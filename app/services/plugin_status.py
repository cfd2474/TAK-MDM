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

"""What the ATLAS ATAK plugin last said about itself, read for the console (W303).

The plugin writes `/sdcard/atak/atlas/plugin-status.json`; the agent forwards
it unchanged with the file's age, measured on the device's own clock. This is
where it is interpreted. The contract (`docs/ATLAS-PLUGIN-CONTRACT.md`) sets
the reading rules:

* **Missing or stale means "not running", never an error.** Stale is older
  than 15 minutes. The plugin writes at least every 300 s (measured 270 s).
* `shutting_down: true` means *the plugin* stopped. It is also written when the
  plugin is unloaded inside a running ATAK, for example by an update.
* **Unknown fields are ignored**, so a newer plugin never breaks the page.

⚠️ **Every field is read defensively.** The file is written by another app,
and a value of the wrong type must show as blank, never raise into the
device page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

#: Older than this is "not running" (contract: stale after 15 minutes).
STALE_AFTER_SECONDS = 15 * 60


@dataclass(frozen=True)
class PluginRow:
    package: str
    version: str | None
    state: str
    error: str | None


@dataclass(frozen=True)
class AutoLoadRow:
    package: str
    #: loaded, pending, not_installed, refused or failed (contract, W304).
    result: str
    error: str | None
    at: str | None
    #: When the plugin last told ATAK to load this package's next update itself,
    #: without the "Load plugin" prompt (W321, plugin 1.2.0). None = not yet.
    preapproved_at: str | None = None


@dataclass(frozen=True)
class EnrollRow:
    """One TAK Server connection the plugin enrols or removes (W365, plugin 1.3.0)."""

    #: The connection's id, which is its address `host:port:proto`.
    id: str
    address: str | None
    #: enrolled, existing, pending, in_progress, failed or removed (contract).
    result: str
    error: str | None
    at: str | None


@dataclass(frozen=True)
class TakServer:
    connect_string: str
    description: str | None
    enabled: bool | None
    connected: bool | None
    error: str | None
    server_version: str | None
    cert_expires: str | None
    truststore_expires: str | None


@dataclass(frozen=True)
class PluginStatus:
    #: "running", "stopped", "stale", "absent" or "unreadable".
    state: str
    #: One line saying what the state means, for the operator.
    summary: str
    reported_at: datetime | None
    age_seconds: int | None = None
    plugin_version: str | None = None
    atak_version: str | None = None
    written_at: str | None = None
    error: str | None = None
    plugins: list[PluginRow] = field(default_factory=list)
    tak_servers: list[TakServer] = field(default_factory=list)
    #: None when the plugin predates auto-load: the array's presence is the
    #: capability signal (contract). An empty list means "supported, none set".
    auto_load: list[AutoLoadRow] | None = None
    #: W321: True when the plugin pre-approves updates (1.2.0+). The top-level
    #: key's presence is the signal, as `auto_load`'s is for auto-load.
    preapproves: bool = False
    #: When the ATLAS plugin last pre-approved its own next update. None = not yet.
    self_update_preapproved_at: str | None = None
    #: W365: None when the plugin predates TAK Server enrollment (before 1.3.0);
    #: the array's presence is the capability signal, as for `auto_load`.
    tak_server_enroll: list[EnrollRow] | None = None

    @property
    def running(self) -> bool:
        return self.state == "running"


def _text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _flag(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _records(value: Any) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _plugins(status: dict) -> list[PluginRow]:
    return [
        PluginRow(
            package=_text(item.get("package")) or "unknown",
            version=_text(item.get("version")),
            state=_text(item.get("state")) or "unknown",
            error=_text(item.get("error")),
        )
        for item in _records(status.get("plugins"))
    ]


def _servers(status: dict) -> list[TakServer]:
    return [
        TakServer(
            connect_string=_text(item.get("connect_string")) or "unknown",
            description=_text(item.get("description")),
            enabled=_flag(item.get("enabled")),
            connected=_flag(item.get("connected")),
            error=_text(item.get("error")),
            server_version=_text(item.get("server_version")),
            cert_expires=_text(item.get("cert_expires")),
            truststore_expires=_text(item.get("truststore_expires")),
        )
        for item in _records(status.get("tak_servers"))
    ]


def _auto_load(status: dict) -> list[AutoLoadRow] | None:
    if "auto_load" not in status:
        return None
    return [
        AutoLoadRow(
            package=_text(item.get("package")) or "unknown",
            result=_text(item.get("result")) or "unknown",
            error=_text(item.get("error")),
            at=_text(item.get("at")),
            preapproved_at=_text(item.get("preapproved_at")),
        )
        for item in _records(status.get("auto_load"))
    ]


def _enroll(status: dict) -> list[EnrollRow] | None:
    if "tak_server_enroll" not in status:
        return None
    return [
        EnrollRow(
            id=_text(item.get("id")) or "unknown",
            address=_text(item.get("address")),
            result=_text(item.get("result")) or "unknown",
            error=_text(item.get("error")),
            at=_text(item.get("at")),
        )
        for item in _records(status.get("tak_server_enroll"))
    ]


def enrolling_host(report: dict | None) -> str | None:
    """The ATAK package a TAK-Server-capable ATLAS plugin reports running in, or None (W365).

    "Capable" is the `tak_server_enroll` array's presence (plugin 1.3.0 or
    later). Read from the device's own report rather than its policy: a device
    whose ATAK policy was withdrawn still has ATAK and the plugin installed, and
    the plugin still needs to be told its list is now empty (S3f).

    Stale or stopped still counts: the plugin is installed, ATAK is just not
    running, and it will read its configuration when it next starts.
    """
    if not isinstance(report, dict) or not report.get("present"):
        return None
    status = report.get("status")
    if not isinstance(status, dict) or "tak_server_enroll" not in status:
        return None
    return _text(status.get("atak_package"))


def read(report: dict | None, reported_at: datetime | None) -> PluginStatus | None:
    """The plugin's status from a device's stored report, or None if it never sent one.

    None means the agent predates plugin reporting, which is not the same as
    "no plugin": that is `absent`.
    """
    if not isinstance(report, dict):
        return None

    if not report.get("present"):
        return PluginStatus(
            state="absent",
            summary="Not running. ATAK has never started the plugin on this device, "
            "or ATAK is not installed.",
            reported_at=reported_at,
        )

    age = report.get("age_seconds")
    age = age if isinstance(age, int) and not isinstance(age, bool) and age >= 0 else None
    status = report.get("status")

    if not isinstance(status, dict):
        return PluginStatus(
            state="unreadable",
            summary="The plugin's status file is there, but ATLAS couldn't read it.",
            reported_at=reported_at,
            age_seconds=age,
            error=_text(report.get("error")) or "no status in the report",
        )

    details = dict(
        reported_at=reported_at,
        age_seconds=age,
        plugin_version=_text(status.get("plugin_version")),
        atak_version=_text(status.get("atak_version")),
        written_at=_text(status.get("written_at")),
        plugins=_plugins(status),
        tak_servers=_servers(status),
        auto_load=_auto_load(status),
        preapproves="self_update_preapproved_at" in status,
        self_update_preapproved_at=_text(status.get("self_update_preapproved_at")),
        tak_server_enroll=_enroll(status),
    )

    if status.get("shutting_down") is True:
        return PluginStatus(
            state="stopped",
            summary="Stopped. The plugin's last word was that it was shutting down: "
            "ATAK closed, or the plugin was unloaded (for example by an update).",
            **details,
        )
    if age is None or age > STALE_AFTER_SECONDS:
        return PluginStatus(
            state="stale",
            summary="Not running. The plugin hasn't written its status for over "
            "15 minutes, so ATAK is most likely closed.",
            **details,
        )
    return PluginStatus(state="running", summary="Running in ATAK.", **details)
