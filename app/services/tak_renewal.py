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

"""Renewing a TAK client certificate no ATLAS policy manages (W458).

A device enrolled from a TAK Portal QR code holds a certificate ATLAS never
issued and a password that expired 15 minutes after the QR was made. When that
certificate nears its end (or its CA is being retired, W453), ATLAS renews it
through the renewal container (`app.renewal`), one connection at a time:

1. **challenge**: ATLAS asks the container for a nonce and sends it to the
   plugin under `atlas.plugin.tak_renew`;
2. the plugin signs it with the connection's private key and reports the proof
   (`tak_server_proofs`);
3. **credential**: ATLAS hands the proof to the container, which checks it and
   makes a ten-minute Authentik app password for the certificate's CN. ATLAS
   seals it with the token vault and sends it to the plugin, which enrolls that
   connection in place and reports the result (`tak_server_renew`);
4. ATLAS deletes the token either way.

Each step happens at a check-in, so a renewal takes three or four. A refusal or
a failure waits a day before the next try, so a broken renewal never loops on a
user's lockout counter.

⚠️ **Only connections no policy manages.** An ATAK_CONFIG `enroll` connection
renews with its policy's login (`tak_enrollment`), and a `certificate`
connection gets its policy's uploaded file back on the next import.

The per-connection record lives in `device.tak_renewal`. The effective-policy
payload carries only a marker (`PAYLOAD_KEY`), so a step moves `state_version`
and the password itself never sits in the cache.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import Device
from app.security.token_vault import TokenVault
from app.services import plugin_status

log = logging.getLogger(__name__)

#: The plugin capability that reports proofs and acts on `PLUGIN_KEY`.
CAPABILITY = "tak_server_renew"

#: The marker in the effective-policy payload: `{address: step id}`.
PAYLOAD_KEY = "tak_renew"

#: The plugin's read-out (`docs/ATLAS-PLUGIN-CONTRACT.md`).
PLUGIN_KEY = "atlas.plugin.tak_renew"

#: Start this long before the end. A stock TAK Server certificate lasts 728
#: days; a month gives a device that is off for weeks time to come back.
RENEW_WITHIN = timedelta(days=30)

#: Under the container's 15 minutes, so a nonce is never sent that it will
#: refuse as expired.
CHALLENGE_TTL = timedelta(minutes=14)

#: After a refusal or a failed enrollment. One try a day costs a user one point
#: of the five their lockout allows.
RETRY_AFTER_FAILURE = timedelta(days=1)

#: After the container was unreachable, rate-limited or not set up.
RETRY_AFTER_OUTAGE = timedelta(hours=1)

#: After a success, until the device reports the new certificate.
SETTLE_AFTER_SUCCESS = timedelta(hours=1)

CHALLENGE, CREDENTIAL, WAIT = "challenge", "credential", "wait"

#: Renewed once while its CA was being retired, and TAK Server signed the new
#: certificate with that same CA. Not renewed again for that CA, or a retirement
#: of the CA TAK Server still signs with would renew the connection every hour.
#: Nothing is sent; the record only remembers.
DONE = "done"


# ---------------------------------------------------------------- the container

@dataclass(frozen=True)
class Minted:
    username: str
    identifier: str
    password: str
    expires: datetime


class Refusal(Exception):
    """The container refused the proof or the user. Retry in a day."""


class Unavailable(Exception):
    """The container could not answer now. Retry in an hour."""


class RenewalClient:
    def __init__(self, base_url: str, client_key: str,
                 transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=20,
                                    headers={"Authorization": "Bearer %s" % client_key},
                                    transport=transport)

    def _call(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise Unavailable("renewal container unreachable (%s)" % type(exc).__name__) from None
        if response.status_code in (400, 403):
            raise Refusal(_detail(response))
        if response.status_code >= 300:
            raise Unavailable(_detail(response))
        return response

    def challenge(self) -> str:
        return self._call("POST", "/challenge").json()["nonce"]

    def mint(self, proof: plugin_status.ProofRow) -> Minted:
        body = self._call("POST", "/mint", json={
            "nonce": proof.nonce, "connect_string": proof.id,
            "certificate": proof.certificate, "chain": list(proof.chain),
            "signature": proof.signature,
        }).json()
        return Minted(body["username"], body["identifier"], body["password"],
                      datetime.fromisoformat(body["expires"]))

    def delete(self, identifier: str) -> None:
        self._call("DELETE", "/tokens/%s" % identifier)


def _detail(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
    except Exception:
        detail = None
    return str(detail or "renewal container answered %d" % response.status_code)[:200]


def client_from_settings() -> RenewalClient | None:
    """None when this server has no renewal container (no client key)."""
    settings = get_settings()
    if not settings.renewal_client_key:
        return None
    return RenewalClient(settings.renewal_url, settings.renewal_client_key)


def configured() -> bool:
    return bool(get_settings().renewal_client_key)


def _vault() -> TokenVault:
    return TokenVault.load_or_create(Path(get_settings().pki_dir))


# ---------------------------------------------------------------- what is due

def managed_addresses(values: Mapping[str, Any]) -> set[str]:
    """Connections an ATAK_CONFIG policy manages, whatever their kind."""
    spec = values.get("ATAK_CONFIG") or {}
    return {c.get("address") for c in spec.get("tak_servers") or []
            if isinstance(c, Mapping) and c.get("address")}


def _expires(server: plugin_status.TakServer) -> datetime | None:
    if not server.cert_expires:
        return None
    try:
        when = datetime.fromisoformat(server.cert_expires.replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def due(status: plugin_status.PluginStatus | None, values: Mapping[str, Any],
        retiring: Collection[str], now: datetime) -> dict[str, plugin_status.TakServer]:
    """`{address: server}` for each unmanaged connection that should renew."""
    if status is None or CAPABILITY not in status.capabilities:
        return {}
    managed = managed_addresses(values)
    out: dict[str, plugin_status.TakServer] = {}
    for server in status.tak_servers:
        if not server.cert_sha256 or server.connect_string in managed:
            continue
        if _ending(server, now) or (server.cert_issuer and server.cert_issuer in retiring):
            out[server.connect_string] = server
    return out


def _rotation_choice(server: plugin_status.TakServer, retiring: Collection[str],
                     choices: Mapping[str, Mapping[str, bool]] | None) -> dict[str, bool] | None:
    """W459: the answers of the rotation this renewal is part of, if any."""
    if not server.cert_issuer or server.cert_issuer not in retiring:
        return None
    choice = (choices or {}).get(server.cert_issuer)
    return dict(choice) if choice is not None else None


def _ending(server: plugin_status.TakServer, now: datetime) -> bool:
    expires = _expires(server)
    return expires is not None and expires - now <= RENEW_WITHIN


# ---------------------------------------------------------------- the steps

def _iso(when: datetime) -> str:
    return when.astimezone(timezone.utc).isoformat()


def _when(text: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(text) if text else None
    except ValueError:
        return None


def _wait(until: datetime, reason: str, sha: str | None) -> dict[str, Any]:
    return {"stage": WAIT, "until": _iso(until), "reason": reason[:200], "sha": sha}


def _forget(client: RenewalClient | None, record: Mapping[str, Any] | None) -> None:
    """Delete a record's token. Best effort: an unreachable container leaves a
    token that expires by itself within ten minutes."""
    if client is None or not record or record.get("stage") != CREDENTIAL:
        return
    try:
        client.delete(record["identifier"])
    except (Refusal, Unavailable) as exc:
        log.warning("renewal token %s not deleted: %s", record.get("identifier"), exc)


def advance(
    records: Mapping[str, Any],
    status: plugin_status.PluginStatus | None,
    values: Mapping[str, Any],
    retiring: Collection[str],
    now: datetime,
    client: RenewalClient | None,
    vault: TokenVault | None,
    choices: Mapping[str, Mapping[str, bool]] | None = None,
) -> dict[str, Any]:
    """The records after this check-in. Calls the container as each step needs.

    :param choices: W459, the operator's profile answers per retiring issuer
        (`tak_ca_retirement.profile_choices`). A renewal because its CA is
        retiring carries that rotation's answers to the plugin; a renewal for
        its end date carries none, so ATAK behaves as it is set.
    """
    candidates = due(status, values, retiring, now)
    proofs = {p.id: p for p in (status.tak_server_proofs if status else None) or []}
    results = {r.id: r for r in (status.tak_server_renew if status else None) or []}
    out: dict[str, Any] = {}

    for address, record in records.items():
        if address not in candidates:
            _forget(client, record)

    for address, server in candidates.items():
        record = dict(records.get(address) or {})
        # ⚠️ Once per retiring CA (the W453 plugin path has the same guard, per
        # login per ATAK start): a connection renewed while its CA was retiring
        # and still issued by it is due again only when it nears its end.
        renewed_from = record.get("renewed_issuer")
        if renewed_from and server.cert_issuer == renewed_from and not _ending(server, now):
            out[address] = {"stage": DONE, "renewed_issuer": renewed_from}
            continue
        if record and record.get("sha") != server.cert_sha256:
            _forget(client, record)
            record = {}
        stage = record.get("stage")

        if stage == WAIT:
            if now < (_when(record.get("until")) or now):
                out[address] = record
                continue
            record, stage = {}, None

        if stage == CREDENTIAL:
            result = results.get(address)
            if result and result.token == record.get("identifier") and result.result in ("enrolled", "failed"):
                _forget(client, record)
                if result.result == "enrolled":
                    out[address] = _wait(now + SETTLE_AFTER_SUCCESS, "renewed", server.cert_sha256)
                    out[address]["renewed_issuer"] = server.cert_issuer
                else:
                    out[address] = _wait(now + RETRY_AFTER_FAILURE,
                                         "enrollment failed: %s" % (result.error or "no reason given"),
                                         server.cert_sha256)
                continue
            if now < (_when(record.get("expires")) or now):
                out[address] = record
                continue
            _forget(client, record)
            record, stage = {}, None

        if stage == CHALLENGE:
            proof = proofs.get(address)
            if proof is not None and proof.nonce == record.get("nonce"):
                if client is None or vault is None:
                    out[address] = _wait(now + RETRY_AFTER_OUTAGE, "renewal is not set up", server.cert_sha256)
                    continue
                try:
                    minted = client.mint(proof)
                except Refusal as exc:
                    out[address] = _wait(now + RETRY_AFTER_FAILURE, "refused: %s" % exc, server.cert_sha256)
                    continue
                except Unavailable as exc:
                    out[address] = _wait(now + RETRY_AFTER_OUTAGE, str(exc), server.cert_sha256)
                    continue
                out[address] = {
                    "stage": CREDENTIAL, "identifier": minted.identifier,
                    "username": minted.username, "password": vault.seal(minted.password),
                    "expires": _iso(minted.expires), "sha": server.cert_sha256,
                }
                choice = _rotation_choice(server, retiring, choices)
                if choice is not None:
                    out[address]["profile"] = choice
                continue
            if now - (_when(record.get("at")) or now) < CHALLENGE_TTL:
                out[address] = record
                continue

        if client is None:
            out[address] = _wait(now + RETRY_AFTER_OUTAGE, "renewal is not set up", server.cert_sha256)
            continue
        try:
            nonce = client.challenge()
        except (Refusal, Unavailable) as exc:
            out[address] = _wait(now + RETRY_AFTER_OUTAGE, str(exc), server.cert_sha256)
            continue
        out[address] = {"stage": CHALLENGE, "nonce": nonce, "at": _iso(now), "sha": server.cert_sha256}
    return out


# ---------------------------------------------------------------- the device

def marker(records: Mapping[str, Any] | None) -> dict[str, str]:
    """`{address: step id}` for the steps that send the plugin something.

    The nonce and the token identifier are not secrets; the password is never
    here. A wait sends nothing, so it is not in the marker.
    """
    out: dict[str, str] = {}
    for address, record in (records or {}).items():
        if record.get("stage") == CHALLENGE:
            out[address] = "c:" + str(record.get("nonce"))
        elif record.get("stage") == CREDENTIAL:
            out[address] = "p:" + str(record.get("identifier"))
    return out


def plugin_entries(records: Mapping[str, Any] | None, vault: TokenVault | None = None) -> list[dict[str, Any]]:
    """What the plugin reads under `PLUGIN_KEY`. Sorted by address."""
    entries: list[dict[str, str]] = []
    for address, record in sorted((records or {}).items()):
        if record.get("stage") == CHALLENGE:
            entries.append({"id": address, "challenge": str(record["nonce"])})
        elif record.get("stage") == CREDENTIAL:
            password = (vault or _vault()).open(record.get("password"))
            if password:
                entry: dict[str, Any] = {"id": address, "username": str(record["username"]),
                                         "password": password, "token": str(record["identifier"])}
                if isinstance(record.get("profile"), Mapping):
                    entry["profile"] = {"config": bool(record["profile"].get("config")),
                                        "channels": bool(record["profile"].get("channels"))}
                entries.append(entry)
    return entries


def capable(device: Device) -> bool:
    status = plugin_status.read(device.atlas_plugin_report, device.atlas_plugin_reported_at)
    return status is not None and CAPABILITY in status.capabilities


def observe(session: Session, device: Device, payload: Mapping[str, Any], now: datetime,
            client: RenewalClient | None = None, vault: TokenVault | None = None) -> bool:
    """Take a check-in into account. True when the marker moved.

    The caller refreshes the effective policy when this returns True, which is
    what moves `state_version` and sends the plugin its next step.
    """
    from app.services import tak_ca_retirement

    status = plugin_status.read(device.atlas_plugin_report, device.atlas_plugin_reported_at)
    records = device.tak_renewal or {}
    if client is None and configured():
        client = client_from_settings()
    if vault is None and client is not None:
        vault = _vault()
    after = advance(records, status, payload.get("values") or {},
                    tak_ca_retirement.active_issuers(session), now, client, vault,
                    tak_ca_retirement.profile_choices(session))
    if after != records:
        device.tak_renewal = after or None
    return marker(after) != (payload.get(PAYLOAD_KEY) or {})
