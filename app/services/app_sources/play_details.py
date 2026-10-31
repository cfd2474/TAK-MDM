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

"""Which build Google Play would serve, without downloading it (W435).

Operator: "Is there a way to ping the Google play version that comes up of an
app when we run a search? Something we can use to compare against the library
version?"

apkeep can't say (its Play `list_versions` only prints that Play keeps no old
versions), so this asks Play's own details call, as the linked account and the
chosen device profile. The request sequence and constants follow the gpapi
crate, which apkeep downloads through (MIT, see NOTICE). The contract, and what
the test against Google showed, are in `docs/GOOGLE_PLAY_DETAILS.md`.

⚠️ **The answer belongs to one device profile.** Chrome was 156 as the Flagship
and 155 as an SM-X520 on the same day. A row compared with the library has to
be looked up as the profile its download will use.

⚠️ **The AAS token is sent in the query string of the auth POST** (gpapi's own
behaviour, over TLS to Google). So a URL from this module is never logged, and
every error message is redacted before it leaves.

⚠️ **One sign-in per account and profile, reused.** Each sign-in registers a new
device (GSF id) with Google, as apkeep does on every call. A session is kept
for :data:`SESSION_SECONDS` and renewed once when Play refuses it.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from urllib.parse import urlencode

from app.services.app_sources import protowire as pw
from app.services.app_sources.base import SourceError

BASE_URL = "https://android.clients.google.com"

#: The Play client's signing-certificate digest, as gpapi sends it.
CLIENT_SIG = "38918a453d07199354f8b19af05ec6562ced5788"
_GMS = "com.google.android.gms"
_VENDING = "com.android.vending"

#: gpapi's `DEFAULT_DFE_TARGETS` and `DEFAULT_DFE_PHENOTYPE`, verbatim.
DFE_TARGETS = "CAESN/qigQYC2AMBFfUbyA7SM5Ij/CvfBoIDgxHqGP8R3xzIBvoQtBKFDZ4HAY4FrwSVMasHBO0O2Q8akgYRAQECAQO7AQEpKZ0CnwECAwRrAQYBr9PPAoK7sQMBAQMCBAkIDAgBAwEDBAICBAUZEgMEBAMLAQEBBQEBAcYBARYED+cBfS8CHQEKkAEMMxcBIQoUDwYHIjd3DQ4MFk0JWGYZEREYAQOLAYEBFDMIEYMBAgICAgICOxkCD18LGQKEAcgDBIQBAgGLARkYCy8oBTJlBCUocxQn0QUBDkkGxgNZQq0BZSbeAmIDgAEBOgGtAaMCDAOQAZ4BBIEBKUtQUYYBQscDDxPSARA1oAEHAWmnAsMB2wFyywGLAxol+wImlwOOA80CtwN26A0WjwJVbQEJPAH+BRDeAfkHK/ABASEBCSAaHQemAzkaRiu2Ad8BdXeiAwEBGBUBBN4LEIABK4gB2AFLfwECAdoENq0CkQGMBsIBiQEtiwGgA1zyAUQ4uwS8AwhsvgPyAcEDF27vApsBHaICGhl3GSKxAR8MC6cBAgItmQYG9QIeywLvAeYBDArLAh8HASI4ELICDVmVBgsY/gHWARtcAsMBpALiAdsBA7QBpAJmIArpByn0AyAKBwHTARIHAX8D+AMBcRIBBbEDmwUBMacCHAciNp0BAQF0OgQLJDuSAh54kwFSP0eeAQQ4M5EBQgMEmwFXywFo0gFyWwMcapQBBugBPUW2AVgBKmy3AR6PAbMBGQxrUJECvQR+8gFoWDsYgQNwRSczBRXQAgtRswEW0ALMAREYAUEBIG6yATYCRE8OxgER8gMBvQEDRkwLc8MBTwHZAUOnAXiiBakDIbYBNNcCIUmuArIBSakBrgFHKs0EgwV/G3AD0wE6LgECtQJ4xQFwFbUCjQPkBS6vAQqEAUZF3QIM9wEhCoYCQhXsBCyZArQDugIziALWAdIBlQHwBdUErQE6qQaSA4EEIvYBHir9AQVLmgMCApsCKAwHuwgrENsBAjNYswEVmgIt7QJnN4wDEnta+wGfAcUBxgEtEFXQAQWdAUAeBcwBAQM7rAEJATJ0LENrdh73A6UBhAE+qwEeASxLZUMhDREuH0CGARbd7K0GlQo"
DFE_PHENOTYPE = "H4sIAAAAAAAAAB3OO3KjMAAA0KRNuWXukBkBQkAJ2MhgAZb5u2GCwQZbCH_EJ77QHmgvtDtbv-Z9_H63zXXU0NVPB1odlyGy7751Q3CitlPDvFd8lxhz3tpNmz7P92CFw73zdHU2Ie0Ad2kmR8lxhiErTFLt3RPGfJQHSDy7Clw10bg8kqf2owLokN4SecJTLoSwBnzQSd652_MOf2d1vKBNVedzg4ciPoLz2mQ8efGAgYeLou-l-PXn_7Sna1MfhHuySxt-4esulEDp8Sbq54CPPKjpANW-lkU2IZ0F92LBI-ukCKSptqeq1eXU96LD9nZfhKHdtjSWwJqUm_2r6pMHOxk01saVanmNopjX3YxQafC4iC6T55aRbC8nTI98AF_kItIQAJb5EQxnKTO7TZDWnr01HVPxelb9A2OWX6poidMWl16K54kcu_jhXw-JSBQkVcD_fPsLSZu6joIBAAA"

#: What a profile must carry to sign in. A captured W312 profile has all of
#: them once `play_profiles.with_play_client` has filled in the Play client.
REQUIRED = (
    "Build.DEVICE", "Build.ID", "Build.HARDWARE", "Build.PRODUCT", "Build.MODEL",
    "Build.VERSION.SDK_INT", "Build.VERSION.RELEASE", "GSF.version",
    "Vending.version", "Vending.versionString",
)

#: How long a sign-in is reused. Play's auth token lasts about an hour.
SESSION_SECONDS = 45 * 60

#: Packages per bulkDetails call.
BATCH = 100

_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True)
class PlayBuild:
    """The build Play would serve this profile."""

    package_name: str
    version_code: int
    version_name: str
    target_sdk: int | None = None


# --------------------------------------------------------------------------- #
# Requests, from a profile's properties
# --------------------------------------------------------------------------- #


def _int(props: Mapping[str, str], key: str) -> int | None:
    value = (props.get(key) or "").strip()
    try:
        return int(value) if value else None
    except ValueError:
        return None


def _list(props: Mapping[str, str], key: str) -> list[str]:
    return [x for x in (props.get(key) or "").split(",") if x]


def missing(props: Mapping[str, str]) -> list[str]:
    """The required properties this profile lacks; empty when it can sign in."""
    return [k for k in REQUIRED if not (props.get(k) or "").strip()]


def device_configuration(props: Mapping[str, str]) -> bytes:
    """`DeviceConfigurationProto`, from the same properties apkeep reads."""
    out = b""
    for field, key in ((1, "TouchScreen"), (2, "Keyboard"), (3, "Navigation"), (4, "ScreenLayout")):
        if _int(props, key) is not None:
            out += pw.varint(field, _int(props, key))
    for field, key in ((5, "HasHardKeyboard"), (6, "HasFiveWayNavigation")):
        if props.get(key):
            out += pw.varint(field, props[key].strip().lower() == "true")
    for field, key in ((7, "Screen.Density"), (8, "GL.Version")):
        if _int(props, key) is not None:
            out += pw.varint(field, _int(props, key))
    for field, key in ((9, "SharedLibraries"), (10, "Features"), (11, "Platforms")):
        out += b"".join(pw.string(field, x) for x in _list(props, key))
    for field, key in ((12, "Screen.Width"), (13, "Screen.Height")):
        if _int(props, key) is not None:
            out += pw.varint(field, _int(props, key))
    for field, key in ((14, "Locales"), (15, "GL.Extensions")):
        out += b"".join(pw.string(field, x) for x in _list(props, key))
    # deviceFeature: every feature again, as a {name, value=0} record.
    out += b"".join(pw.string(26, pw.string(1, x) + pw.varint(2, 0)) for x in _list(props, "Features"))
    return out


def checkin_request(props: Mapping[str, str], now: float) -> bytes:
    """`AndroidCheckinRequest` for a first checkin."""
    build = b""
    for field, key in ((1, "Build.FINGERPRINT"), (2, "Build.HARDWARE"), (3, "Build.BRAND"),
                       (4, "Build.RADIO"), (5, "Build.BOOTLOADER"), (6, "Client")):
        if props.get(key):
            build += pw.string(field, props[key])
    # gpapi's own arithmetic (seconds ÷ 1000), kept: it is what Google has seen.
    build += pw.varint(7, int(now) // 1000)
    build += pw.varint(8, _int(props, "GSF.version") or 0)
    build += pw.string(9, props["Build.DEVICE"])
    build += pw.varint(10, _int(props, "Build.VERSION.SDK_INT") or 0)
    for field, key in ((11, "Build.MODEL"), (12, "Build.MANUFACTURER"), (13, "Build.PRODUCT")):
        if props.get(key):
            build += pw.string(field, props[key])
    build += pw.varint(14, False)

    checkin = pw.string(1, build) + pw.varint(2, 0)
    for field, key in ((6, "CellOperator"), (7, "SimOperator"), (8, "Roaming")):
        if props.get(key):
            checkin += pw.string(field, props[key])
    checkin += pw.varint(9, 0)
    return (pw.varint(2, 0) + pw.string(4, checkin) + pw.string(6, "en_US") + pw.string(12, "UTC")
            + pw.varint(14, 3) + pw.string(18, device_configuration(props)) + pw.varint(20, 0))


def finsky_user_agent(props: Mapping[str, str]) -> str:
    """The Play Store's User-Agent for this profile, in gpapi's exact form."""
    return (
        f"Android-Finsky/{props['Vending.versionString']} (api=3,versionCode={props['Vending.version']},"
        f"sdk={props['Build.VERSION.SDK_INT']},device={props['Build.DEVICE']},"
        f"hardware={props['Build.HARDWARE']},product={props['Build.PRODUCT']},"
        f"platformVersionRelease={props['Build.VERSION.RELEASE']},model={props['Build.MODEL']},"
        f"buildId={props['Build.ID']},isWideScreen=0,supportedAbis={';'.join(_list(props, 'Platforms'))})"
    )


def bulk_details_request(packages: Sequence[str]) -> bytes:
    return b"".join(pw.string(1, p) for p in packages) + pw.varint(2, False)


# --------------------------------------------------------------------------- #
# Responses
# --------------------------------------------------------------------------- #


def build_of(item: bytes | None) -> PlayBuild | None:
    """An `Item`'s package and version, or None when it carries no app details."""
    app = pw.first(item, 13, 1)
    package = pw.text(pw.first(item, 1))
    if app is None or not package:
        return None
    fields = pw.decode(app)
    code = (fields.get(3) or [None])[0]
    if not isinstance(code, int) or code <= 0:
        return None
    return PlayBuild(
        package_name=package,
        version_code=code,
        version_name=pw.text((fields.get(4) or [None])[0]) or str(code),
        target_sdk=(fields.get(32) or [None])[0],
    )


def parse_bulk(body: bytes) -> dict[str, PlayBuild]:
    """Every app a bulkDetails reply describes, by package.

    ⚠️ Matched by the item's own package id, not by position: an entry with no
    item is Play declining that package for this profile (the W314 case), and
    the reply is not documented to keep the request's order.
    """
    response = pw.first(body, 1, 19)
    if response is None:
        return {}
    builds = (build_of(pw.first(entry, 1)) for entry in pw.decode(response).get(1, []))
    return {b.package_name: b for b in builds if b is not None}


def parse_form(text: str) -> dict[str, str]:
    """The auth endpoint's `Key=value` lines, keys lower-cased (gpapi's rule)."""
    out = {}
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep:
            out[key.strip().lower()] = value.strip()
    return out


# --------------------------------------------------------------------------- #
# A signed-in session, and the cache of them
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _Session:
    gsf_id: int
    consistency_token: str | None
    config_token: str | None
    auth: str
    cookie: str | None
    signed_in_at: float


class SessionCache:
    """Sign-ins reused per (account, profile), so a search doesn't register a device."""

    def __init__(self) -> None:
        self._sessions: dict[str, _Session] = {}
        self._lock = threading.Lock()

    def get(self, key: str, now: float) -> _Session | None:
        with self._lock:
            found = self._sessions.get(key)
        if found is not None and now - found.signed_in_at < SESSION_SECONDS:
            return found
        return None

    def put(self, key: str, session: _Session) -> None:
        with self._lock:
            self._sessions[key] = session

    def drop(self, key: str) -> None:
        with self._lock:
            self._sessions.pop(key, None)


#: The process's sessions. One per worker; a second worker signs in once more.
sessions = SessionCache()


def _cache_key(email: str, props: Mapping[str, str]) -> str:
    """The account and the exact profile: a changed capture is a different device."""
    digest = hashlib.sha256(json.dumps(dict(props), sort_keys=True).encode()).hexdigest()
    return f"{email}|{digest}"


# --------------------------------------------------------------------------- #
# The client
# --------------------------------------------------------------------------- #


class PlayDetails:
    """Ask Play, as one account and one device profile, which builds it serves."""

    def __init__(
        self,
        email: str,
        aas_token: str,
        properties: Mapping[str, str],
        *,
        client=None,
        cache: SessionCache | None = None,
        clock: Callable[[], float] = time.time,
        timeout: float = _TIMEOUT_SECONDS,
    ) -> None:
        lacking = missing(properties)
        if lacking:
            raise SourceError(
                "this device profile can't be used to ask Google Play for versions: "
                f"it has no {', '.join(lacking)}"
            )
        self._email = email
        self._token = aas_token
        self._props = dict(properties)
        # Injected so no test reaches Google.
        self._client = client
        self._cache = cache if cache is not None else sessions
        self._clock = clock
        self._timeout = timeout
        self._key = _cache_key(email, self._props)

    # ------------------------------------------------------------------ #

    def lookup(self, packages: Iterable[str]) -> dict[str, PlayBuild | None]:
        """Each package's current build for this profile; None where Play offers none."""
        wanted = list(dict.fromkeys(p.strip() for p in packages if p and p.strip()))
        if not wanted:
            return {}
        found: dict[str, PlayBuild] = {}
        with self._http() as http:
            for start in range(0, len(wanted), BATCH):
                found.update(self._bulk(http, wanted[start:start + BATCH]))
        return {p: found.get(p) for p in wanted}

    # ------------------------------------------------------------------ #

    def _http(self):
        if self._client is not None:
            return _Borrowed(self._client)
        import httpx

        return httpx.Client(timeout=httpx.Timeout(self._timeout, connect=min(5.0, self._timeout)))

    def _bulk(self, http, packages: Sequence[str]) -> dict[str, PlayBuild]:
        session = self._session(http)
        response = self._send(http, "POST", "/fdfe/bulkDetails", session,
                              content=bulk_details_request(packages))
        if response.status_code in (401, 403):
            # A session Play has stopped honouring: sign in once more, then give up.
            self._cache.drop(self._key)
            session = self._session(http)
            response = self._send(http, "POST", "/fdfe/bulkDetails", session,
                                  content=bulk_details_request(packages))
        if response.status_code != 200:
            raise SourceError(f"Google Play's details call returned {response.status_code}")
        try:
            return parse_bulk(response.content)
        except pw.WireError as exc:
            raise SourceError(f"Google Play's details reply could not be read ({exc})") from exc

    def _session(self, http) -> _Session:
        now = self._clock()
        cached = self._cache.get(self._key, now)
        if cached is not None:
            return cached
        try:
            session = self._sign_in(http, now)
        except pw.WireError as exc:
            raise SourceError(f"Google Play's sign-in reply could not be read ({exc})") from exc
        self._cache.put(self._key, session)
        return session

    def _sign_in(self, http, now: float) -> _Session:
        p = self._props

        # 1. Checkin: a GSF id for this profile.
        response = self._post(http, f"{BASE_URL}/checkin", checkin_request(p, now),
                              {**self._auth_headers(None), "content-type": "application/x-protobuf"})
        if response.status_code != 200:
            raise SourceError(f"Google Play's device checkin returned {response.status_code}")
        fields = pw.decode(response.content)
        gsf = (fields.get(7) or [None])[0]
        if not gsf:
            raise SourceError("Google Play's device checkin gave no device id")
        consistency = pw.text((fields.get(12) or [None])[0])

        # 2. The device's configuration, which Play matches builds against.
        partial = _Session(gsf, consistency, None, "", None, now)
        response = self._send(http, "POST", "/fdfe/uploadDeviceConfig", partial,
                              content=pw.string(1, device_configuration(p)))
        config_token = pw.text(pw.first(response.content, 1, 28, 1)) if response.status_code == 200 else None
        if not config_token:
            raise SourceError(f"Google Play did not accept the device profile ({response.status_code})")

        # 3. The account's durable token for a Play one.
        params = {
            "androidId": f"{gsf:x}", "sdk_version": p["Build.VERSION.SDK_INT"], "Email": self._email,
            "google_play_services_version": p["GSF.version"], "device_country": "us", "lang": "en",
            "callerSig": CLIENT_SIG, "app": _VENDING, "client_sig": CLIENT_SIG, "callerPkg": _GMS,
            "Token": self._token, "oauth2_foreground": "1", "token_request_options": "CAA4AVAB",
            "check_email": "1", "system_partition": "1",
            "service": "oauth2:https://www.googleapis.com/auth/googleplay",
        }
        response = self._post(http, f"{BASE_URL}/auth?{urlencode(params)}", b"",
                              {**self._auth_headers(gsf), "content-length": "0"})
        reply = parse_form(response.text)
        auth = reply.get("auth")
        if not auth:
            # Google's own code (BadAuthentication, NeedsBrowser ...) names the fix.
            reason = reply.get("error") or str(response.status_code)
            raise SourceError(
                f"Google refused the linked account ({reason}). If this persists, "
                f"relink it under Admin → Google Play."
            )

        # 4. The table of contents: the DFE cookie, and whether the terms are accepted.
        signed_in = _Session(gsf, consistency, config_token, auth, None, now)
        response = self._send(http, "GET", "/fdfe/toc", signed_in)
        if response.status_code != 200:
            raise SourceError(f"Google Play's sign-in returned {response.status_code}")
        if pw.first(response.content, 1, 6, 7) is not None:
            raise SourceError("the linked Google account has not accepted Google Play's terms of service")
        cookie = pw.text(pw.first(response.content, 1, 6, 22))
        return _Session(gsf, consistency, config_token, auth, cookie, now)

    # ------------------------------------------------------------------ #

    def _auth_headers(self, gsf: int | None) -> dict[str, str]:
        headers = {"app": _GMS,
                   "User-Agent": f"GoogleAuth/1.4 ({self._props['Build.DEVICE']} {self._props['Build.ID']})"}
        if gsf:
            headers["device"] = f"{gsf:x}"
        return headers

    def _dfe_headers(self, session: _Session) -> dict[str, str]:
        headers = {
            "user-agent": finsky_user_agent(self._props),
            "accept-language": "en-US",
            "X-DFE-Encoded-Targets": DFE_TARGETS,
            "X-DFE-Phenotype": DFE_PHENOTYPE,
            "X-DFE-Client-Id": "am-android-google",
            "X-DFE-Network-Type": "4",
            "X-DFE-Content-Filters": "",
            "X-Limit-Ad-Tracking-Enabled": "false",
            "X-Ad-Id": "",
            "X-DFE-UserLanguages": "en_US",
            "X-DFE-Request-Params": "timeoutMs=4000",
            "X-DFE-Device-Id": f"{session.gsf_id:x}",
        }
        optional = {
            "Authorization": f"Bearer {session.auth}" if session.auth else None,
            "X-DFE-Device-Checkin-Consistency-Token": session.consistency_token,
            "X-DFE-Device-Config-Token": session.config_token,
            "X-DFE-Cookie": session.cookie,
            "X-DFE-MCCMCN": self._props.get("SimOperator") or None,
        }
        headers.update({k: v for k, v in optional.items() if v})
        return headers

    def _send(self, http, method: str, path: str, session: _Session, content: bytes | None = None):
        headers = self._dfe_headers(session)
        if content is not None:
            headers["content-type"] = "application/x-protobuf"
            return self._post(http, f"{BASE_URL}{path}", content, headers)
        return self._request(http, "GET", f"{BASE_URL}{path}", None, headers)

    def _post(self, http, url: str, content: bytes, headers: dict[str, str]):
        return self._request(http, "POST", url, content, headers)

    def _request(self, http, method: str, url: str, content: bytes | None, headers: dict[str, str]):
        try:
            return http.request(method, url, content=content, headers=headers)
        except Exception as exc:  # noqa: BLE001 - httpx's errors can carry the URL, and the URL the token
            raise SourceError(f"could not reach Google Play ({self._redact(exc)})") from None

    def _redact(self, exc: Exception) -> str:
        message = f"{type(exc).__name__}: {exc}"
        for secret in (self._token, self._email):
            if secret:
                message = message.replace(secret, "<redacted>")
        # Anything that still looks like a request URL goes whole.
        return message.split("https://", 1)[0].rstrip(" (") or type(exc).__name__


class _Borrowed:
    """An injected client, used as a context manager without being closed."""

    def __init__(self, client) -> None:
        self._client = client

    def __enter__(self):
        return self._client

    def __exit__(self, *exc):
        return False
