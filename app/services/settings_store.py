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

"""Database-backed operator settings for the Admin console.

Deployment-critical settings (server URL, auth mode, PKI dir) stay in the
environment and are shown read-only. Everything here is operational configuration
an operator legitimately edits at runtime: the EULA, and credentials for outbound
email, a directory, and SMS.

⚠️ Secret fields (SMTP / AD / SMS passwords) are stored **in plaintext** in
`app_setting`, next in danger to `pki/ca.key` and the token vault. Acceptable on
the single trusted host this project targets; folded into the R8 KMS work. The
console never echoes a stored secret back into a form — it shows "set" instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppSetting


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    kind: str = "text"  # text | textarea | password | number | bool
    help: str = ""


@dataclass(frozen=True)
class Group:
    key: str
    title: str
    description: str
    fields: list[Field] = field(default_factory=list)


GROUPS: dict[str, Group] = {
    g.key: g
    for g in (
        Group("eula", "End-user licence agreement",
              "Shown to a user during provisioning, if your agent build displays it.",
              [Field("eula.text", "EULA text", "textarea")]),
        Group("smtp", "Email (SMTP)",
              "Outbound mail for notifications and operator alerts.",
              [
                  Field("smtp.host", "Host"),
                  Field("smtp.port", "Port", "number"),
                  Field("smtp.username", "Username"),
                  Field("smtp.password", "Password", "password"),
                  Field("smtp.from_address", "From address"),
                  Field("smtp.use_tls", "Use STARTTLS", "bool"),
              ]),
        Group("ad", "Active Directory / LDAP",
              "Directory lookups for operator identity or device ownership.",
              [
                  Field("ad.server", "Server URI", help="ldaps://dc.example.org"),
                  Field("ad.base_dn", "Base DN"),
                  Field("ad.bind_dn", "Bind DN"),
                  Field("ad.bind_password", "Bind password", "password"),
              ]),
        Group("sms", "SMS",
              "Outbound SMS for operator alerts.",
              [
                  Field("sms.provider", "Provider", help="twilio | messagebird | …"),
                  Field("sms.api_key", "API key", "password"),
                  Field("sms.from_number", "From number"),
              ]),
        Group("location", "Location map",
              "Where the console fetches map tiles. The default is OpenStreetMap's "
              "public tile service, which means a browser showing a device's "
              "position asks openstreetmap.org for the tiles around it — that "
              "reveals roughly where an operator is looking to a third party. Point "
              "these at an internal tile server to keep it in-house, or on a "
              "deployment with no internet, where the default silently shows an "
              "empty map.",
              [
                  Field("location.tile_url", "Tile URL template", "text",
                        "Leaflet template, e.g. "
                        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"),
                  Field("location.tile_attribution", "Tile attribution", "text",
                        "Shown in the map corner. Most tile providers require it."),
              ]),
        Group("geofencing", "Geofencing defaults",
              "Defaults a new geofence policy starts from (the policy type is a "
              "placeholder until its backend lands).",
              [
                  Field("geofencing.default_radius_m", "Default radius (m)", "number"),
                  Field("geofencing.poll_interval_s", "Location poll interval (s)", "number"),
              ]),
    )
}

_SECRET_KINDS = {"password"}


def get(session: Session, key: str, default: str = "") -> str:
    row = session.get(AppSetting, key)
    return row.value if row is not None else default


def put(session: Session, key: str, value: str, *, updated_by: str | None = None) -> None:
    """Set one setting that is not part of a form group — the agent-update
    pointers, for instance, which are edited by dedicated buttons rather than a
    generic field list."""
    row = session.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key)
        session.add(row)
    row.value = value
    row.updated_by = updated_by
    session.flush()


def group_values(session: Session, group_key: str) -> dict[str, str]:
    group = GROUPS[group_key]
    stored = {
        s.key: s.value
        for s in session.scalars(
            select(AppSetting).where(
                AppSetting.key.in_([f.key for f in group.fields])
            )
        )
    }
    return {f.key: stored.get(f.key, "") for f in group.fields}


def group_is_secret(field_kind: str) -> bool:
    return field_kind in _SECRET_KINDS


def save_group(
    session: Session,
    group_key: str,
    values: dict[str, str],
    *,
    updated_by: str | None = None,
) -> None:
    """Persist a group's fields. A blank secret field leaves the stored one
    untouched (so 'set' in the form does not have to be retyped)."""
    group = GROUPS[group_key]
    for f in group.fields:
        incoming = (values.get(f.key) or "").strip()
        if group_is_secret(f.kind) and not incoming:
            continue
        row = session.get(AppSetting, f.key)
        if row is None:
            row = AppSetting(key=f.key)
            session.add(row)
        row.value = incoming
        row.updated_by = updated_by
    session.flush()
