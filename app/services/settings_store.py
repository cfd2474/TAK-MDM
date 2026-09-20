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

⚠️ **Secret fields are sealed, not encrypted away.** SMTP / AD / SMS credentials
are stored through `TokenVault` (SEC_AUDIT.md M-5), which is the same mechanism
already protecting enrolment secrets and the Google Play token. The vault key
lives in `pki/`, so what this defends against is a **database-only** compromise —
a dump, a backup, a snapshot, a read-only injection somewhere else. It does
**not** help if `pki/` leaks, because then everything is gone anyway (S-2).

That is a narrower claim than "encrypted at rest" and it is the true one. It is
also the realistic threat: a database copy travels far more easily than a
directory of 0600 files on a running host.

The console never echoes a stored secret back into a form — it shows "set".
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppSetting
from app.services import clock


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    kind: str = "text"  # text | textarea | password | number | bool | select
    help: str = ""
    #: What the form shows when nothing is stored.
    #:
    #: ⚠️ This is the *displayed* default, and it has to agree with the one the
    #: code falls back to. A blank box beside help text reading "Default 30" made
    #: an operator guess whether 30 was in force or whether the field was simply
    #: unset — and the two look identical until a month of history disappears.
    default: str = ""
    #: The permitted answers, for `kind="select"`. Ignored by every other kind.
    #:
    #: A tuple rather than a list because `Field` is frozen and a mutable default
    #: shared between instances is the oldest trap in the language.
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class Group:
    key: str
    title: str
    description: str
    fields: list[Field] = field(default_factory=list)


def _timezone_field() -> Field:
    """The timezone picker, built from the IANA database at import.

    ⚠️ Built lazily-ish — at import of this module rather than at class-definition
    time of `Field` — so that a missing tz database fails here, loudly, with a
    stack trace naming `zoneinfo`, rather than producing an empty dropdown that
    looks like a rendering bug. `available()` on a system with no database returns
    just `["UTC"]`, which is a usable console and an obvious symptom.
    """
    return Field(
        "general.timezone", "Default timezone", "select",
        "Times in the console — location history, check-ins, certificate dates — "
        "are shown in this zone. Everything is still stored in UTC; this changes "
        "only what is displayed. Devices are unaffected: the agent reports "
        "absolute instants and never sees this setting.",
        default=clock.DEFAULT_TIMEZONE,
        choices=tuple(clock.available()),
    )


GROUPS: dict[str, Group] = {
    g.key: g
    for g in (
        Group("general", "General",
              "Settings that apply to the console as a whole.",
              [_timezone_field()]),
        Group("eula", "End-user licence agreement",
              "Shown to a user during provisioning, if your agent build displays it.",
              [Field("eula.text", "EULA text", "textarea")]),
        Group("smtp", "Email (SMTP)",
              "Outbound mail for notifications and operator alerts.",
              [
                  # ⚠️ First in the group because it decides whether the rest of
                  # it applies. A toggle underneath the fields it disables reads
                  # as one more option rather than the switch above them.
                  Field("smtp.use_infratak_relay",
                        "Use InfraTAK's email configuration", "bool",
                        "Send through InfraTAK's Email Relay instead of the "
                        "settings below. The relay is Postfix on this host and "
                        "needs no username or password from ATLAS — it holds the "
                        "provider credentials itself. Requires InfraTAK's Email "
                        "Relay to be deployed; if it is not, nothing will send.",
                        default=""),
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
        Group("location", "Location",
              "How long device location history is kept, and where the console "
              "fetches map tiles. The tile default is OpenStreetMap's public "
              "service, which means a browser showing a device's position asks "
              "openstreetmap.org for the tiles around it — revealing roughly where "
              "an operator is looking to a third party. Point these at an internal "
              "tile server to keep it in-house, or on a deployment with no "
              "internet, where the default silently shows an empty map.",
              [
                  Field("location.retention_days", "Keep location history for (days)",
                        "number",
                        "Points older than this are deleted permanently, once a "
                        "day. Set 0 to keep history for ever — note that 0 here "
                        "means KEEP EVERYTHING, the opposite of the 0 in a "
                        "tracking policy's reporting interval, which means off.",
                        default="30"),
                  Field("location.default_interval_minutes",
                        "Default reporting interval (minutes)", "number",
                        "How often an enrolled device records its position when "
                        "no policy says otherwise — every device reports from the "
                        "moment it enrols. A Tracking and fencing policy "
                        "overrides this, and a policy setting 0 is the only way "
                        "to switch reporting off. Blank or unparseable falls back "
                        "to 15.",
                        default="15"),
                  Field("location.tile_url", "Tile URL template", "text",
                        "Leaflet template. Blank uses OpenStreetMap's public "
                        "tiles, which are run by volunteers for casual use and "
                        "may block a busy console — point this at your own tile "
                        "server or a commercial provider for anything beyond a "
                        "few operators.",
                        "https://tile.openstreetmap.org/{z}/{x}/{y}.png"),
                  Field("location.tile_attribution", "Tile attribution", "text",
                        "Shown in the map corner. Most tile providers require it."),
                  Field("location.suggest_url", "Address suggestions URL", "text",
                        "Used for the as-you-type suggestions in the geofence "
                        "editor. Blank uses komoot's public Photon service, which "
                        "is free and needs no key. ⚠️ Suggestions send what you "
                        "are part-way through typing, not just the finished "
                        "address — more disclosure than the Find button. Clear "
                        "this and set it to something unreachable to turn "
                        "suggestions off; Find keeps working."),
                  Field("location.geocoder_url", "Address lookup URL", "text",
                        "Used by the geofence editor to turn a typed address into "
                        "a coordinate. Sent only when someone presses Find, from "
                        "this server rather than the browser — but what is sent is "
                        "where a geofence is about to go, so point this at your own "
                        "geocoder if that matters. Leave blank for OpenStreetMap's "
                        "public service; coordinates can always be typed directly, "
                        "so this is optional."),
              ]),
        Group("knox", "Samsung Knox",
              "The Knox licence for Samsung hardware. Devices running the Knox "
              "build of the agent activate against this key at their next "
              "check-in and report back what Samsung said; every other device "
              "reports “not applicable” and is unaffected.",
              [
                  # ⚠️ A password field, so it is sealed by TokenVault and the
                  # form shows "set" rather than the key. It still travels to the
                  # device in plaintext inside the signed bundle — `activateLicense`
                  # takes the key itself and there is no other shape Samsung
                  # accepts. What sealing buys is the same thing it buys for SMTP:
                  # a database copy carries ciphertext.
                  #
                  # ⚠️ It is deliberately NOT written into the cached effective
                  # policy. See `effective_policy.apply_knox_license`.
                  Field("knox.license_key", "Knox licence key", "password",
                        "A KPE or KLM key from the Samsung Knox Admin Portal. "
                        "Leave blank to activate nothing — Knox devices then "
                        "report “not licensed”, which is a state, not a "
                        "fault. ⚠️ Samsung rate-limits activation attempts, so a "
                        "key that is wrong is not retried until it is changed."),
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


def _vault():
    """The token vault, resolved late so importing this module needs no PKI."""
    from app.config import get_settings
    from app.security.token_vault import TokenVault

    return TokenVault.load_or_create(Path(get_settings().pki_dir))


def _unseal(spec: "Field", stored: str) -> str:
    """Recover a secret, tolerating one written before sealing existed.

    ⚠️ A value that will not unseal is returned **as-is**, not discarded. Every
    credential stored before M-5 is plaintext, and treating those as corrupt would
    silently break outbound mail on the release that added the encryption — a
    security improvement that reads as an outage.

    The cost is that a plaintext value cannot be told apart from a corrupt sealed
    one. Accepted: the alternative is a migration that has to guess, and guessing
    wrong locks an operator out of their own mail relay.
    """
    if not stored or not group_is_secret(spec.kind):
        return stored
    try:
        opened = _vault().open(stored)
    except Exception:
        return stored
    return stored if opened is None else opened


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
    return {
        f.key: _unseal(f, stored.get(f.key, f.default))
        for f in group.fields
    }


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
        # ⚠️ Sealed on the way in, so a database copy carries ciphertext. The key
        # is in `pki/`; see the module docstring for exactly what that does and
        # does not buy.
        row.value = _vault().seal(incoming) if group_is_secret(f.kind) else incoming
        row.updated_by = updated_by
    session.flush()
