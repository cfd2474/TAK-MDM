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

"""Moving devices off a TAK Server intermediate CA (W453, GitHub issue #4).

When an agency rotates its TAK Server intermediate CA, every device's client
certificate must come from the new one before the old one leaves TAK Server's
truststore. The operator names the CA to retire here; ATLAS then moves devices
the way each connection allows:

* **`enroll`**: the device is sent the policy's login again with the issuer in
  `reenroll_issuers`, and the ATLAS plugin re-enrolls (contract: "Moving to a
  new intermediate"). It reaches each device at its next check-in, because
  `tak_enrollment.observe` compares the marker on every one.
* **`certificate`**: one uploaded certificate serves the whole policy, so the
  operator uploads a new one; ATAK replaces the connection's certificates on
  re-import (✅ C1, platform reference §10h). This module flags those policies.

⚠️ **ATLAS never reads or changes TAK Server.** Which CA TAK Server signs with,
and when the old one leaves its truststore, is the operator's. Retiring the CA
TAK Server still signs with only re-enrolls each device onto the same CA, once
per login per ATAK start (the plugin's guard), so the page says so.

**W459: the profile answers.** A re-enrollment downloads the TAK Server's
enrollment profile, and depending on ATAK's `pref_import_pref_action` ATAK may
prompt for each `.pref` in it. The operator answers once per rotation whether
ATAK applies the config pref and the channels pref (`enable-channels.pref`);
the plugin applies those answers with no prompt for that re-enrollment only,
then puts ATAK's setting back. A renewal for any other reason carries none.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts.storage import ArtifactStorage
from app.db.models import Device, EffectivePolicyCache, Policy, TakCaRetirement
from app.services import plugin_status, tak_ca, tak_certs, tak_renewal

MAX_ISSUER = 1024


class RetirementError(ValueError):
    """A request the console refuses, with the reason to show."""


@dataclass
class OnIt:
    """A device with a connection whose client certificate is from the CA."""

    device: Device
    connect_string: str
    #: The plugin's enrollment result for the connection, None when it is not
    #: an `enroll` connection ATLAS manages.
    enroll_result: str | None
    enroll_error: str | None = None
    #: W458: True when an ATAK_CONFIG policy manages this connection.
    managed: bool = False
    #: W458: the renewal record (`tak_renewal`) for an unmanaged connection.
    renewal: dict | None = None
    #: W458: whether the device's plugin can renew (1.6.0+).
    renew_capable: bool = False

    @property
    def renewal_until(self) -> datetime | None:
        """W458: when a paused renewal tries again, for the page's own zone."""
        try:
            return datetime.fromisoformat((self.renewal or {}).get("until") or "")
        except ValueError:
            return None


@dataclass
class Progress:
    retirement: TakCaRetirement
    on_it: list[OnIt] = field(default_factory=list)
    #: Devices whose plugin reports TAK connections, none from this CA.
    elsewhere: int = 0
    #: Devices with TAK connections whose plugin is too old to say.
    unknown: list[Device] = field(default_factory=list)
    #: `certificate` policies whose uploaded client certificate is from it.
    policies: list[Policy] = field(default_factory=list)


@dataclass(frozen=True)
class FleetCa:
    issuer: str
    devices: int
    retiring: bool

    @property
    def name(self) -> str:
        return tak_ca.short_name(self.issuer) or self.issuer


# ---------------------------------------------------------------- the list

def active(session: Session) -> list[TakCaRetirement]:
    return list(session.scalars(select(TakCaRetirement).order_by(TakCaRetirement.started_at)))


def active_issuers(session: Session) -> tuple[str, ...]:
    """What `tak_enrollment.due` and the plugin list read. Sorted: stable bytes."""
    return tuple(sorted(r.issuer for r in active(session)))


def start(
    session: Session,
    issuer: str,
    retire_by: date | None,
    actor: str,
    accept_config: bool | None = None,
    accept_channels: bool | None = None,
) -> TakCaRetirement:
    """Begin moving devices off `issuer`; a second start changes the date and,
    when given, the answers (W459)."""
    issuer = (issuer or "").strip()
    if not issuer:
        raise RetirementError("Choose the certificate authority to retire.")
    if len(issuer) > MAX_ISSUER:
        raise RetirementError("That certificate authority name is too long.")
    row = session.scalar(select(TakCaRetirement).where(TakCaRetirement.issuer == issuer))
    if row is None:
        row = TakCaRetirement(issuer=issuer, started_by=actor or "")
        session.add(row)
    row.retire_by = retire_by
    if accept_config is not None and accept_channels is not None:
        row.accept_config, row.accept_channels = accept_config, accept_channels
    session.flush()
    return row


def profile_choice(row: TakCaRetirement) -> dict[str, bool] | None:
    """W459: the operator's answers as the plugin reads them, or None when the
    retirement has none (started before W459): then nothing is overridden."""
    if row.accept_config is None or row.accept_channels is None:
        return None
    return {"config": bool(row.accept_config), "channels": bool(row.accept_channels)}


def profile_choices(session: Session) -> dict[str, dict[str, bool]]:
    """`{issuer: answers}` for each retiring CA that has answers (W459)."""
    out: dict[str, dict[str, bool]] = {}
    for row in active(session):
        choice = profile_choice(row)
        if choice is not None:
            out[row.issuer] = choice
    return out


def stop(session: Session, issuer: str) -> bool:
    row = session.scalar(select(TakCaRetirement).where(TakCaRetirement.issuer == issuer))
    if row is None:
        return False
    session.delete(row)
    session.flush()
    return True


# ---------------------------------------------------------------- the fleet

def _statuses(session: Session) -> list[tuple[Device, plugin_status.PluginStatus | None]]:
    devices = session.scalars(select(Device).order_by(Device.serial_number))
    return [(d, plugin_status.read(d.atlas_plugin_report, d.atlas_plugin_reported_at))
            for d in devices]


def fleet_cas(session: Session) -> list[FleetCa]:
    """Every CA a device reports a client certificate from, and how many devices.

    Retiring CAs are listed even when no device reports them any more: that is
    what "everyone has moved" looks like.
    """
    counts: dict[str, set] = {}
    for device, status in _statuses(session):
        if not tak_ca.reports_issuer(status):
            continue
        for server in status.tak_servers:
            if server.cert_issuer:
                counts.setdefault(server.cert_issuer, set()).add(device.id)
    retiring = set(active_issuers(session))
    for issuer in retiring:
        counts.setdefault(issuer, set())
    return sorted((FleetCa(i, len(d), i in retiring) for i, d in counts.items()),
                  key=lambda c: (not c.retiring, c.name))


def progress(session: Session, storage: ArtifactStorage) -> list[Progress]:
    """For each CA being retired: who is still on it, who cannot say, which
    certificate policies still hand it out."""
    rows = active(session)
    if not rows:
        return []
    out = {r.issuer: Progress(r) for r in rows}
    statuses = _statuses(session)
    for device, status in statuses:
        if status is None or not status.tak_servers:
            continue
        if not tak_ca.reports_issuer(status):
            for p in out.values():
                p.unknown.append(device)
            continue
        enroll = {row.id: row for row in (status.tak_server_enroll or [])}
        cache = session.get(EffectivePolicyCache, device.id)
        managed = tak_renewal.managed_addresses((cache.payload if cache else {}).get("values") or {})
        renewals = device.tak_renewal or {}
        hit: set[str] = set()
        for server in status.tak_servers:
            p = out.get(server.cert_issuer or "")
            if p is None:
                continue
            row = enroll.get(server.connect_string)
            p.on_it.append(OnIt(device, server.connect_string,
                                row.result if row else None, row.error if row else None,
                                managed=server.connect_string in managed,
                                renewal=renewals.get(server.connect_string),
                                renew_capable=tak_renewal.CAPABILITY in status.capabilities))
            hit.add(p.retirement.issuer)
        for issuer, p in out.items():
            if issuer not in hit:
                p.elsewhere += 1
    for policy, issuer in _certificate_policies(session, storage):
        if issuer in out:
            out[issuer].policies.append(policy)
    return [out[r.issuer] for r in rows]


def _certificate_policies(
    session: Session, storage: ArtifactStorage
) -> list[tuple[Policy, str]]:
    """Each live ATAK_CONFIG policy's uploaded client certificate issuers."""
    found: list[tuple[Policy, str]] = []
    policies = session.scalars(select(Policy).where(
        Policy.policy_type == "ATAK_CONFIG", Policy.archived_at.is_(None)))
    for policy in policies:
        if not policy.versions:
            continue
        spec = policy.versions[-1].spec or {}
        issuers = set()
        for conn in spec.get("tak_servers") or []:
            if conn.get("auth") != "certificate" or not conn.get("client_cert_sha256"):
                continue
            issuer = client_issuer(storage, conn["client_cert_sha256"],
                                   conn.get("client_cert_password") or "")
            if issuer:
                issuers.add(issuer)
        found.extend((policy, i) for i in sorted(issuers))
    return found


def client_issuer(storage: ArtifactStorage, digest: str, password: str) -> str | None:
    """The issuer DN of a stored client `.p12`, as the plugin reports one."""
    try:
        with storage.open(digest) as handle:
            data = handle.read()
        return tak_certs.inspect(data, password, expect=tak_certs.CLIENT).issuer
    except Exception:  # noqa: BLE001 - a missing or unreadable blob flags nothing
        return None
