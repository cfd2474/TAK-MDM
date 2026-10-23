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

"""Which device gets a TAK Server enrollment password, and when (W365 S3c).

Operator, 2026-10-09: one login per policy, and silent enrollment through the
ATLAS plugin. The login must not sit on every device, so the server sends the
password **only to a device that still needs it**:

* its plugin can enrol: the status file has a `tak_server_enroll` array, so the
  plugin is 1.3.0 or later. An older plugin would never read the password and
  never scrub it from ATAK's settings;
* and the connection is not yet `enrolled`/`existing`, or it is, but its client
  certificate expires within 14 days (renewal);
* and no enrollment with this same login has failed on this device. ⚠️ The
  plugin retries a failure after every ATAK restart, and a wrong password tried
  again and again locks the account. A failure is remembered against a
  **fingerprint** of the login, so a corrected login goes out once more.

The result is a marker, `{connection id: login fingerprint}`, kept in the
effective-policy payload. `effective_policy.refresh` compares it like every other
part of the device-facing state, so a change moves `state_version`; and it
holds no secret, so it can sit in the cache and on the Effective policy page.
`desired_state` turns the marker into credentials when it builds the bundle.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Device
from app.services import plugin_status

#: Where the marker lives in the effective-policy payload.
PAYLOAD_KEY = "tak_enroll"

#: Renew a client certificate this close to its expiry (contract).
RENEW_WITHIN = timedelta(days=14)

_DONE = ("enrolled", "existing")


def fingerprint(connection: Mapping[str, Any]) -> str:
    """A short, stable digest of one connection's login. Never the login itself."""
    material = "\n".join(
        str(connection.get(k) or "") for k in ("address", "username", "password")
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def enroll_connections(values: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """The resolved policy's connections that enrol, with a login to enrol with."""
    spec = values.get("ATAK_CONFIG") or {}
    return [
        c
        for c in spec.get("tak_servers") or []
        if isinstance(c, Mapping) and c.get("auth") == "enroll" and c.get("password")
    ]


def _expiry(status: plugin_status.PluginStatus, address: str) -> datetime | None:
    for server in status.tak_servers:
        if server.connect_string == address and server.cert_expires:
            try:
                when = datetime.fromisoformat(server.cert_expires.replace("Z", "+00:00"))
            except ValueError:
                return None
            return when if when.tzinfo else when.replace(tzinfo=timezone.utc)
    return None


def due(
    connections: Sequence[Mapping[str, Any]],
    status: plugin_status.PluginStatus | None,
    failures: Mapping[str, str] | None,
    now: datetime,
) -> dict[str, str]:
    """`{id: fingerprint}` for each enroll connection whose password should be sent."""
    if status is None or status.tak_server_enroll is None:
        return {}
    results = {row.id: row.result for row in status.tak_server_enroll}
    failures = failures or {}
    out: dict[str, str] = {}
    for connection in connections:
        address = connection["address"]
        current = fingerprint(connection)
        if failures.get(address) == current:
            continue
        result = results.get(address)
        if result == "failed":
            continue
        if result in _DONE:
            expires = _expiry(status, address)
            if expires is None or expires - now > RENEW_WITHIN:
                continue
        out[address] = current
    return out


def failures_after(
    connections: Sequence[Mapping[str, Any]],
    status: plugin_status.PluginStatus | None,
    failures: Mapping[str, str] | None,
) -> dict[str, str]:
    """The failure record once a report is taken into account.

    A `failed` result is recorded against the login in force now; a success
    clears it; a connection no longer in the policy is forgotten.
    """
    by_id = {c["address"]: c for c in connections}
    out = {k: v for k, v in (failures or {}).items() if k in by_id}
    if status is None or status.tak_server_enroll is None:
        return out
    for row in status.tak_server_enroll:
        connection = by_id.get(row.id)
        if connection is None:
            continue
        if row.result == "failed":
            out[row.id] = fingerprint(connection)
        elif row.result in _DONE:
            out.pop(row.id, None)
    return out


def _status(device: Device) -> plugin_status.PluginStatus | None:
    return plugin_status.read(device.atlas_plugin_report, device.atlas_plugin_reported_at)


def marker(device: Device, values: Mapping[str, Any], now: datetime) -> dict[str, str]:
    """The payload marker for this device and this resolved policy."""
    return due(enroll_connections(values), _status(device), device.tak_enroll_failures, now)


def observe(session: Session, device: Device, payload: Mapping[str, Any], now: datetime) -> bool:
    """Take a fresh plugin report into account. True when the marker moved.

    Updates the device's failure record; the caller refreshes the effective
    policy when this returns True, which is what moves `state_version`.
    """
    connections = enroll_connections(payload.get("values") or {})
    failures = failures_after(connections, _status(device), device.tak_enroll_failures)
    if failures != (device.tak_enroll_failures or {}):
        device.tak_enroll_failures = failures or None
    return marker(device, payload.get("values") or {}, now) != (payload.get(PAYLOAD_KEY) or {})


def credentials(values: Mapping[str, Any], due_marker: Mapping[str, str]) -> dict[str, tuple[str, str]]:
    """`{id: (username, password)}` for the marker's connections.

    ⚠️ Only while the fingerprint still matches: a login changed since the
    marker was computed waits for the next refresh rather than going out under
    a marker that describes another login.
    """
    out: dict[str, tuple[str, str]] = {}
    for connection in enroll_connections(values):
        address = connection["address"]
        if due_marker.get(address) == fingerprint(connection):
            out[address] = (str(connection.get("username") or ""), str(connection["password"]))
    return out
