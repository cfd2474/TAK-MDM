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

"""Talking to TAK.gov: the account link, and the plugin catalog.

ATAK's "Link EUD" is not device-bound magic — it is a stock **OAuth 2.0 Device
Authorization Grant (RFC 8628)** against TAK.gov's Keycloak. Nothing in it needs
Android, so a headless server can complete it and hold the credential.

Two things about this API shape the whole module:

* **`eud_api` is undocumented and effectively unversioned.** So every catalog
  field is read defensively — a rename upstream must degrade one column to "—",
  never take down the Apps page with a `KeyError`.
* **The credential is a person, not a service account.** The refresh token
  inherits exactly the entitlements of whoever linked, does not idle out, and is
  a durable bearer credential to their TAK.gov account.

Network I/O is confined to the ``_post``/``_get`` helpers and everything above
them is pure, so the protocol can be tested without touching the internet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import httpx

REALM = "https://auth.tak.gov/auth/realms/TPC/protocol/openid-connect"
DEVICE_ENDPOINT = f"{REALM}/auth/device"
TOKEN_ENDPOINT = f"{REALM}/token"
CATALOG_ENDPOINT = "https://tak.gov/eud_api/software/v1/plugins"

#: Where to send the operator if the server ever omits `verification_uri`.
#: ⚠️ `tpc.md` documents `https://tak.gov/register-device`; the live realm returns
#: this instead (verified 2026-09-02), and a code entered at the documented page
#: does not work. Using the server's value is always preferred — this is only the
#: fallback, and it is the realm's own page rather than the wrong one.
FALLBACK_VERIFICATION_URI = "https://auth.tak.gov/auth/realms/TPC/device"

#: Public client, no secret. This is the same id ATAK itself uses.
CLIENT_ID = "tak-gov-eud"
DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"

#: ``offline_access`` is load-bearing: it is what yields a refresh token that
#: survives the operator closing the browser tab.
SCOPE = "openid offline_access email profile"

#: tak.gov rejects requests with no User-Agent.
USER_AGENT = "ATLAS-MDM/1.0"

#: ATAK-CIV object code carries a distribution grant. ATAK-MIL explicitly does
#: not, and GOV/MIL plugins carry access and export controls — so CIV is the
#: default and the console says why (D38).
PRODUCTS = ("ATAK-CIV", "ATAK-GOV", "ATAK-MIL")
DEFAULT_PRODUCT = "ATAK-CIV"

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

#: ⚠️ Verified against the live service (2026-09-02): `eud_api` answers
#: **421 "HTTP/2 Required"** over HTTP/1.1. The auth endpoints at auth.tak.gov do
#: not care, so the link succeeds and only the catalog fails — which reads as a
#: permissions problem and is not one. Requires the `h2` package.
_HTTP2 = True


class TakGovError(RuntimeError):
    """A call to TAK.gov failed in a way the operator has to see."""


class AuthorizationPending(Exception):
    """RFC 8628 soft error: the operator has not entered the code yet."""


class SlowDown(Exception):
    """RFC 8628 soft error: we are polling too fast. Raise the interval."""


# --------------------------------------------------------------------------- #
# Pure parsing — no network, so the contract is testable
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class DeviceCode:
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    interval: int
    expires_in: int


def parse_device_code(payload: dict[str, Any]) -> DeviceCode:
    try:
        device_code = payload["device_code"]
        user_code = payload["user_code"]
    except KeyError as exc:  # pragma: no cover - defensive
        raise TakGovError(f"device authorization response missing {exc}") from exc

    uri = payload.get("verification_uri") or FALLBACK_VERIFICATION_URI
    return DeviceCode(
        device_code=device_code,
        user_code=user_code,
        verification_uri=uri,
        # Keycloak supplies the code-embedded variant; fall back to the plain URI
        # so the console always has something to link to.
        verification_uri_complete=payload.get("verification_uri_complete") or uri,
        # RFC 8628 says 5 seconds when the server does not say.
        interval=int(payload.get("interval") or 5),
        expires_in=int(payload.get("expires_in") or 600),
    )


@dataclass(frozen=True)
class Tokens:
    access_token: str
    refresh_token: str
    expires_in: int
    account_label: str | None = None


def parse_tokens(payload: dict[str, Any]) -> Tokens:
    try:
        access = payload["access_token"]
        refresh = payload["refresh_token"]
    except KeyError as exc:
        raise TakGovError(
            f"token response missing {exc} — the 'offline_access' scope is what "
            "makes a refresh token appear; without it the link cannot survive."
        ) from exc

    return Tokens(
        access_token=access,
        refresh_token=refresh,
        expires_in=int(payload.get("expires_in") or 300),
        account_label=_account_label(access),
    )


def _account_label(access_token: str) -> str | None:
    """Best-effort human name for the linked account, read from the JWT body.

    Not verified, and never trusted for anything: the token is validated by
    tak.gov, not by us, and this value is only ever shown on a console page so an
    operator can tell *whose* entitlements the catalog reflects. A malformed token
    yields None rather than an error.
    """
    import base64
    import json

    try:
        body = access_token.split(".")[1]
        body += "=" * (-len(body) % 4)
        claims = json.loads(base64.urlsafe_b64decode(body))
    except Exception:
        return None

    for key in ("preferred_username", "email", "name"):
        value = claims.get(key)
        if isinstance(value, str) and value:
            return value[:256]
    return None


@dataclass(frozen=True)
class Plugin:
    """One catalog entry, read defensively.

    Only ``package_name`` is required — it is the catalog's primary key and a row
    without one cannot be matched against anything. Everything else degrades to
    None so a field rename upstream costs a column, not the page.
    """

    package_name: str
    #: The catalog's own stable id (e.g. "wave-5-8-0-civ"). Absent from the field
    #: table in `tpc.md`, found on every live row, and load-bearing: both
    #: ``apk_url`` and ``icon_url`` are built from it.
    identifier: str | None = None
    display_name: str | None = None
    version: str | None = None
    revision_code: int | None = None
    apk_url: str | None = None
    apk_hash: str | None = None
    apk_size_bytes: int | None = None
    apk_type: str | None = None
    os_requirement: str | None = None
    tak_prerequisite: str | None = None
    description: str | None = None
    platform: str | None = None
    #: Fields present upstream that this adapter does not model. Kept so an
    #: operator can see that the API grew, rather than it passing unnoticed.
    unknown_fields: tuple[str, ...] = field(default=())


_KNOWN = {
    "package_name", "identifier", "display_name", "version", "revision_code", "apk_url",
    "apk_hash", "apk_size_bytes", "apk_type", "os_requirement",
    "tak_prerequisite", "description", "platform", "icon_url",
}


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def parse_plugin(raw: dict[str, Any]) -> Plugin | None:
    package_name = _str_or_none(raw.get("package_name"))
    if not package_name:
        return None
    return Plugin(
        package_name=package_name,
        identifier=_str_or_none(raw.get("identifier")),
        display_name=_str_or_none(raw.get("display_name")),
        version=_str_or_none(raw.get("version")),
        revision_code=_int_or_none(raw.get("revision_code")),
        apk_url=_str_or_none(raw.get("apk_url")),
        apk_hash=(_str_or_none(raw.get("apk_hash")) or "").lower() or None,
        apk_size_bytes=_int_or_none(raw.get("apk_size_bytes")),
        apk_type=_str_or_none(raw.get("apk_type")),
        os_requirement=_str_or_none(raw.get("os_requirement")),
        tak_prerequisite=_str_or_none(raw.get("tak_prerequisite")),
        description=_str_or_none(raw.get("description")),
        platform=_str_or_none(raw.get("platform")),
        unknown_fields=tuple(sorted(set(raw) - _KNOWN)),
    )


def parse_catalog(payload: Any) -> list[Plugin]:
    """Rows from a catalog response, whatever shape it arrives in.

    The endpoint is undocumented; a bare list and a wrapped object are both
    plausible and both are accepted. An unrecognised shape yields an empty list
    rather than an exception — the console then shows "no plugins", which is
    honest, instead of a stack trace.
    """
    rows: Any = payload
    if isinstance(payload, dict):
        for key in ("results", "plugins", "data", "items"):
            if isinstance(payload.get(key), list):
                rows = payload[key]
                break
        else:
            rows = []
    if not isinstance(rows, list):
        return []

    plugins = [parse_plugin(r) for r in rows if isinstance(r, dict)]
    return [p for p in plugins if p is not None]


def token_error(status_code: int, payload: dict[str, Any]) -> Exception:
    """Map a non-200 token response onto the RFC 8628 state machine.

    The two soft errors are the whole point of polling and are the part
    OpenTAKServer's implementation skips (`tpc.md` §2.3).
    """
    error = str(payload.get("error") or f"HTTP {status_code}")
    if error == "authorization_pending":
        return AuthorizationPending()
    if error == "slow_down":
        return SlowDown()

    detail = payload.get("error_description")
    return TakGovError(f"{error}: {detail}" if detail else error)


# --------------------------------------------------------------------------- #
# Network
# --------------------------------------------------------------------------- #


def _headers(access_token: str | None = None) -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT}
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


def request_device_code(client: httpx.Client | None = None) -> DeviceCode:
    with _client(client) as http:
        response = http.post(
            DEVICE_ENDPOINT,
            headers=_headers(),
            data={"client_id": CLIENT_ID, "scope": SCOPE, "grant_type": DEVICE_GRANT},
        )
    if response.status_code != 200:
        raise TakGovError(
            f"tak.gov refused a device code (HTTP {response.status_code}): "
            f"{response.text[:300]}"
        )
    return parse_device_code(response.json())


def exchange_device_code(device_code: str, client: httpx.Client | None = None) -> Tokens:
    """One poll. Raises AuthorizationPending / SlowDown for the soft states."""
    with _client(client) as http:
        response = http.post(
            TOKEN_ENDPOINT,
            headers=_headers(),
            data={
                "grant_type": DEVICE_GRANT,
                "device_code": device_code,
                "client_id": CLIENT_ID,
            },
        )
    if response.status_code == 200:
        return parse_tokens(response.json())
    raise token_error(response.status_code, _json_or_empty(response))


def refresh_tokens(refresh_token: str, client: httpx.Client | None = None) -> Tokens:
    with _client(client) as http:
        response = http.post(
            TOKEN_ENDPOINT,
            headers=_headers(),
            data={
                "client_id": CLIENT_ID,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
    if response.status_code == 200:
        return parse_tokens(response.json())
    raise token_error(response.status_code, _json_or_empty(response))


def fetch_catalog(
    access_token: str,
    *,
    product: str = DEFAULT_PRODUCT,
    product_version: str = "5.8.0",
    client: httpx.Client | None = None,
) -> list[Plugin]:
    with _client(client) as http:
        response = http.get(
            CATALOG_ENDPOINT,
            headers=_headers(access_token),
            params={"product": product, "product_version": product_version},
        )
    if response.status_code != 200:
        raise TakGovError(
            f"catalog request failed (HTTP {response.status_code}): {response.text[:300]}"
        )
    return parse_catalog(response.json())


def download_apk(
    plugin: Plugin, access_token: str, client: httpx.Client | None = None
) -> bytes:
    """Fetch a plugin APK and verify its hash before returning a single byte.

    The hash check is not belt-and-braces: ``apk_url`` redirects to presigned
    storage, so what arrives is not served by the host that vouched for it.
    """
    if not plugin.apk_url:
        raise TakGovError(f"{plugin.package_name}: the catalog gave no download URL")

    with _client(client) as http:
        response = http.get(
            plugin.apk_url, headers=_headers(access_token), follow_redirects=True
        )
    if response.status_code != 200:
        raise TakGovError(
            f"{plugin.package_name}: download failed (HTTP {response.status_code})"
        )

    data = response.content
    if plugin.apk_hash:
        import hashlib

        actual = hashlib.sha256(data).hexdigest()
        if actual != plugin.apk_hash:
            raise TakGovError(
                f"{plugin.package_name}: APK hash mismatch — expected "
                f"{plugin.apk_hash[:16]}…, got {actual[:16]}…. Not installing."
            )
    return data


def _client(client: httpx.Client | None) -> httpx.Client:
    """The caller's client, or a short-lived one.

    Returned as a context manager either way; a caller-supplied client is wrapped
    so that closing it here does not close something the caller still needs.
    """
    if client is not None:
        return _Borrowed(client)  # type: ignore[return-value]
    return httpx.Client(timeout=_TIMEOUT, http2=_HTTP2)


class _Borrowed:
    """Context manager that yields a client it does not own."""

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def __enter__(self) -> httpx.Client:
        return self._client

    def __exit__(self, *exc: object) -> None:
        return None


def _json_or_empty(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}
