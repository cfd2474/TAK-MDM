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

"""Ten-minute Authentik app passwords for one user (W458).

The same kind of token TAK Portal puts in its QR code
(`services/authentikTokens.service.js`: `POST /core/tokens/`,
`intent: app_password`). TAK Server checks it as the password through
Authentik's LDAP outpost.

⚠️ **A deleted token keeps working for up to an hour.** The LDAP provider on an
InfraTAK box is `bind_mode=cached`, and the outpost remembers a successful bind
until the Authentik session it made expires (`session_duration=hours=1` on
`ldap-authentication-login`, measured on leckliter2). Deleting still stops new
binds; the window is why the token goes only to the device, over mutual TLS.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

import httpx

#: Long enough for a check-in, the agent's fetch and ATAK handing the plugin its
#: new configuration; TAK Portal's QR passwords last 15 minutes.
LIFETIME = timedelta(minutes=10)

#: Every token this makes starts with it, and `delete` touches nothing else. A
#: compromised API asking for deletions cannot sign anyone else out.
TOKEN_PREFIX = "atlas-renew-"

#: Authentik user types a person has. Service accounts and outposts never
#: enroll into TAK.
PERSON_TYPES = ("internal", "external")


class AuthentikError(Exception):
    """Authentik could not be reached, or answered something unexpected."""


class Refused(Exception):
    """This user must not be given a token. The text is safe to show."""


class Authentik:
    def __init__(self, base_url: str, token: str, transport: httpx.BaseTransport | None = None,
                 clock=lambda: datetime.now(timezone.utc)) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/") + "/api/v3/",
            headers={"Authorization": "Bearer %s" % token},
            timeout=15, transport=transport)
        self._clock = clock

    def close(self) -> None:
        self._client.close()

    def _call(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise AuthentikError("Authentik unreachable: %s" % type(exc).__name__) from None
        if response.status_code >= 400:
            raise AuthentikError("Authentik answered %d on %s" % (response.status_code, path))
        return response

    def user(self, username: str) -> dict:
        rows = self._call("GET", "core/users/", params={"username": username}).json().get("results", [])
        for row in rows:
            if row.get("username") == username:
                return row
        raise Refused("no Authentik user named %r" % username)

    @staticmethod
    def check_eligible(user: dict) -> None:
        """Refuse anyone a token would make dangerous or pointless."""
        if not user.get("is_active", False):
            raise Refused("user is deactivated")
        if user.get("type") not in PERSON_TYPES:
            raise Refused("user is a %s, not a person" % user.get("type"))
        if user.get("is_superuser"):
            raise Refused("user is an Authentik administrator")
        for group in user.get("groups_obj") or []:
            if group.get("is_superuser"):
                raise Refused("user is in the administrator group %r" % group.get("name"))

    def mint(self, user: dict) -> tuple[str, str, datetime]:
        """Make a token for this user. Returns (identifier, key, expires)."""
        identifier = TOKEN_PREFIX + secrets.token_hex(8)
        expires = self._clock() + LIFETIME
        self._call("POST", "core/tokens/", json={
            "identifier": identifier,
            "intent": "app_password",
            "user": user["pk"],
            "expiring": True,
            "expires": expires.strftime("%Y-%m-%dT%H:%M:%SZ"),  # utc-by-design: Authentik's API
            "description": "ATLAS certificate renewal for %s" % user.get("username"),
        })
        key = self._call("GET", "core/tokens/%s/view_key/" % identifier).json().get("key")
        if not key:
            raise AuthentikError("Authentik returned no key")
        return identifier, key, expires

    def delete(self, identifier: str) -> None:
        if not identifier.startswith(TOKEN_PREFIX) or not identifier.replace("-", "").isalnum():
            raise Refused("not a renewal token")
        try:
            self._call("DELETE", "core/tokens/%s/" % identifier)
        except AuthentikError as exc:
            # Already gone (expired and swept) is the outcome we wanted.
            if "answered 404" not in str(exc):
                raise
