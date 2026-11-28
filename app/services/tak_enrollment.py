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

⚠️ **Which login failed is the one that was sent, not the one in force now**
(W456). The plugin repeats its last result until it next tries, and it tries
only with a password. Before W456 every `failed` report was pinned to the
current login and any `failed` held the password back, so once an operator
corrected a wrong password the stale report pinned itself to the correction
and the correction was never sent. Now a failure is recorded once per attempt,
keyed by the plugin's own `at`, against the fingerprint in the marker last
delivered; a repeat of the same attempt changes nothing; and a `failed` holds
the password back only while the failed login is still the current one.
When the delivered marker no longer names the connection (the login was
corrected before the failure arrived, and the refresh held it back), the
failure is charged to :data:`UNKNOWN_LOGIN`, not to the current login: the
current login goes out once, and only a fresh attempt is charged to it.
Residual race, accepted: an attempt with the old login that lands after the
corrected one was sent is charged to the corrected login, which then waits
for the next change, exactly as any failure does.

The result is a marker, `{connection id: login fingerprint}`, kept in the
effective-policy payload. `effective_policy.refresh` compares it like every other
part of the device-facing state, so a change moves `state_version`; and it
holds no secret, so it can sit in the cache and on the Effective policy page.
`desired_state` turns the marker into credentials when it builds the bundle.
"""

from __future__ import annotations

import hashlib
from collections.abc import Collection, Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db.models import Device
from app.services import plugin_status

#: Where the marker lives in the effective-policy payload.
PAYLOAD_KEY = "tak_enroll"

#: W453: the retiring CAs this device's enroll connections report, beside the
#: marker. ⚠️ The marker alone cannot carry a retirement: a device whose login
#: is already due (a first enrollment, a renewal) has the same marker before
#: and after, so `state_version` stayed put and the agent never applied the
#: list naming the retiring CA (SM-X520, v1.131.0).
REENROLL_KEY = "tak_reenroll"

#: The login a failure is charged to when no login was on record as sent:
#: "an earlier login failed", never equal to a real fingerprint (W456).
UNKNOWN_LOGIN = "unknown"

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


#: The plugin capability that reports `cert_issuer` and acts on
#: `reenroll_issuers` (contract; the same one `tak_ca` reads).
REENROLL_CAPABILITY = "tak_server_reenroll"


def _issuer(status: plugin_status.PluginStatus, address: str) -> str | None:
    """The client certificate's issuer the device reports, from a plugin that
    can act on a move (1.5.0+). None otherwise: sending a login a plugin cannot
    use only leaves it on the device."""
    if REENROLL_CAPABILITY not in status.capabilities:
        return None
    for server in status.tak_servers:
        if server.connect_string == address:
            return server.cert_issuer
    return None


def _failed_login(record: Any) -> str | None:
    """The fingerprint a failure record charges. A bare string is a record
    from before W456, which held only that."""
    if isinstance(record, Mapping):
        return record.get("fp")
    return record if isinstance(record, str) else None


def _failed_at(record: Any) -> str | None:
    """The plugin's `at` for the attempt a record describes (None before W456)."""
    return record.get("at") if isinstance(record, Mapping) else None


def due(
    connections: Sequence[Mapping[str, Any]],
    status: plugin_status.PluginStatus | None,
    failures: Mapping[str, Any] | None,
    now: datetime,
    retiring: Collection[str] = (),
) -> dict[str, str]:
    """`{id: fingerprint}` for each enroll connection whose password should be sent.

    :param retiring: W453, issuer DNs being retired. An enrolled device whose
        reported client certificate is from one of them is due, as for a
        renewal. A device that reports no issuer (an older plugin) is not.
    """
    if status is None or status.tak_server_enroll is None:
        return {}
    results = {row.id: row.result for row in status.tak_server_enroll}
    failures = failures or {}
    out: dict[str, str] = {}
    for connection in connections:
        address = connection["address"]
        current = fingerprint(connection)
        failed_login = _failed_login(failures.get(address))
        if failed_login == current:
            continue
        result = results.get(address)
        # ⚠️ A `failed` with no record yet is held back: `observe` records it
        # in this same check-in. One with a record for another login is stale,
        # and the corrected login goes out (W456).
        if result == "failed" and failed_login is None:
            continue
        if result in _DONE:
            expires = _expiry(status, address)
            renewing = expires is not None and expires - now <= RENEW_WITHIN
            if not renewing and _issuer(status, address) not in retiring:
                continue
        out[address] = current
    return out


def failures_after(
    connections: Sequence[Mapping[str, Any]],
    status: plugin_status.PluginStatus | None,
    failures: Mapping[str, Any] | None,
    sent: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """The failure record once a report is taken into account.

    A new `failed` attempt is recorded as `{"fp", "at"}` against the login the
    device was last sent (`sent`, the delivered marker), or
    :data:`UNKNOWN_LOGIN` when the marker names none; a repeat of an attempt
    already recorded changes nothing; a success clears it; a connection no
    longer in the policy is forgotten.
    """
    by_id = {c["address"]: c for c in connections}
    out = {k: v for k, v in (failures or {}).items() if k in by_id}
    if status is None or status.tak_server_enroll is None:
        return out
    sent = sent or {}
    for row in status.tak_server_enroll:
        connection = by_id.get(row.id)
        if connection is None:
            continue
        if row.result == "failed":
            record = out.get(row.id)
            if record is not None and _failed_at(record) == row.at and row.at is not None:
                continue  # the same attempt, reported again
            if record is not None and _failed_at(record) is None and not isinstance(record, Mapping):
                # A record from before W456: keep the login it charged and
                # learn which attempt it was, so the repeat is recognised.
                out[row.id] = {"fp": record, "at": row.at}
                continue
            # ⚠️ Never the current login as a fallback: that is the W456
            # failure in another order (correction published, then the old
            # failure arrives, and is pinned to the correction).
            out[row.id] = {"fp": sent.get(row.id) or UNKNOWN_LOGIN, "at": row.at}
        elif row.result in _DONE:
            out.pop(row.id, None)
    return out


def _status(device: Device) -> plugin_status.PluginStatus | None:
    return plugin_status.read(device.atlas_plugin_report, device.atlas_plugin_reported_at)


def marker(
    device: Device, values: Mapping[str, Any], now: datetime, retiring: Collection[str] = ()
) -> dict[str, str]:
    """The payload marker for this device and this resolved policy.

    :param retiring: W453, the issuer DNs being retired
        (`tak_ca_retirement.active_issuers`).
    """
    return due(enroll_connections(values), _status(device), device.tak_enroll_failures, now,
               retiring)


def reenroll_marker(
    device: Device,
    values: Mapping[str, Any],
    retiring: Collection[str],
    choices: Mapping[str, Mapping[str, bool]] | None = None,
) -> list[str]:
    """The retiring issuers this device's enroll connections report, sorted.

    Empty for a plugin that cannot act on a move (`_issuer` says None), so a
    retirement moves only the devices it can move.

    :param choices: W459, the profile answers per issuer
        (`tak_ca_retirement.profile_choices`). An issuer with answers carries
        them, so changing an answer reaches the devices on that CA. An issuer
        without reads as before, so the deploy moves no one.
    """
    status = _status(device)
    if status is None or not retiring:
        return []
    issuers = {_issuer(status, c["address"]) for c in enroll_connections(values)}
    return sorted(_with_choice(i, choices) for i in issuers if i in retiring)


def _with_choice(issuer: str, choices: Mapping[str, Mapping[str, bool]] | None) -> str:
    choice = (choices or {}).get(issuer)
    if choice is None:
        return issuer
    return "%s\nconfig=%s channels=%s" % (
        issuer, "yes" if choice["config"] else "no", "yes" if choice["channels"] else "no")


def observe(session: Session, device: Device, payload: Mapping[str, Any], now: datetime) -> bool:
    """Take a fresh plugin report into account. True when the marker moved.

    Updates the device's failure record; the caller refreshes the effective
    policy when this returns True, which is what moves `state_version`.
    """
    connections = enroll_connections(payload.get("values") or {})
    failures = failures_after(connections, _status(device), device.tak_enroll_failures,
                              payload.get(PAYLOAD_KEY) or {})
    if failures != (device.tak_enroll_failures or {}):
        device.tak_enroll_failures = failures or None
    from app.services import tak_ca_retirement

    retiring = tak_ca_retirement.active_issuers(session)
    choices = tak_ca_retirement.profile_choices(session)
    values = payload.get("values") or {}
    return (
        marker(device, values, now, retiring) != (payload.get(PAYLOAD_KEY) or {})
        or reenroll_marker(device, values, retiring, choices) != (payload.get(REENROLL_KEY) or [])
    )


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
