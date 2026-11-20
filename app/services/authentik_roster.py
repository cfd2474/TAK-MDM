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

"""Who the agency's administrators are, read from Authentik (W495).

infra-TAK (#572) gives each agency ATLAS a read-only Authentik token with
`view_group` on exactly two groups: the agency's super admin group and its
standard admin group. Listing groups with it returns those two, each with its
members. Measured on Authentik 2026.5.6 before it was built.

⚠️ **The roster never grants access.** It tells the super admin who the
administrators are, so they can set a standard admin up before that person
first signs in. Every request is still decided from the groups Authentik sends
with that request (`admin_auth.identify`).

⚠️ **Redirects are refused, not followed.** The request carries a bearer
token; a redirect could carry it to another host. `outbound.fetch` follows
redirects (with headers), so it is deliberately not used here.

⚠️ **Never the global superusers** (operator decision 6). Only groups named in
`TAKMDM_ADMIN_GROUP` or `TAKMDM_STANDARD_ADMIN_GROUP` are kept, and a group
with `is_superuser` is dropped even if it is named — `authentik Admins` sits in
`TAKMDM_ADMIN_GROUP` on every agency box.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.config import Settings
from app.security import admin_auth

logger = logging.getLogger(__name__)

#: Seconds. The page waits for this, so it is short.
TIMEOUT = 10.0


@dataclass(frozen=True)
class Member:
    username: str
    name: str = ""
    email: str = ""
    is_active: bool = True


@dataclass(frozen=True)
class Roster:
    """What the page shows. `configured` False: no URL or token on this box."""

    configured: bool
    super_admins: tuple[Member, ...] = ()
    standard_admins: tuple[Member, ...] = ()
    #: Why the roster could not be read, in words for the operator. None when it
    #: was read. Never contains the token.
    error: str | None = None

    @property
    def available(self) -> bool:
        return self.configured and self.error is None


class RosterReader(Protocol):
    def read(self) -> Roster: ...


def _members(group: dict) -> tuple[Member, ...]:
    out = []
    for user in group.get("users_obj") or ():
        username = str(user.get("username") or "").strip()
        if not username:
            continue
        out.append(Member(
            username=username,
            name=str(user.get("name") or ""),
            email=str(user.get("email") or ""),
            is_active=bool(user.get("is_active", True)),
        ))
    return tuple(sorted(out, key=lambda m: m.username.casefold()))


@dataclass
class AuthentikRoster:
    """`RosterReader` over Authentik's REST API."""

    settings: Settings
    #: Tests pass an `httpx.MockTransport`; production uses the network.
    transport: httpx.BaseTransport | None = field(default=None)

    def read(self) -> Roster:
        url = (self.settings.authentik_url or "").strip().rstrip("/")
        token = (self.settings.authentik_roster_token or "").strip()
        if not url or not token:
            return Roster(configured=False)

        standard = admin_auth.standard_group(self.settings)
        supers = set(admin_auth.required_groups(self.settings))
        try:
            with httpx.Client(
                transport=self.transport, timeout=TIMEOUT, follow_redirects=False
            ) as client:
                response = client.get(
                    f"{url}/api/v3/core/groups/",
                    params={"include_users": "true", "page_size": "100"},
                    headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
                )
        except httpx.HTTPError as exc:
            # ⚠️ The exception's text, never the request: the request has the token.
            logger.warning("Authentik roster unreachable at %s: %s", url, type(exc).__name__)
            return Roster(configured=True, error=f"Authentik could not be reached ({type(exc).__name__}).")

        if response.is_redirect:
            logger.warning("Authentik roster at %s answered a redirect; not followed", url)
            return Roster(configured=True, error=(
                "Authentik answered with a redirect, which is not followed because "
                "the request carries a token. Check TAKMDM_AUTHENTIK_URL."))
        if response.status_code != 200:
            logger.warning("Authentik roster at %s answered %s", url, response.status_code)
            return Roster(configured=True, error=f"Authentik answered {response.status_code}.")
        try:
            groups = response.json().get("results") or []
        except ValueError:
            return Roster(configured=True, error="Authentik's answer was not JSON.")

        super_members: dict[str, Member] = {}
        standard_members: dict[str, Member] = {}
        for group in groups:
            if not isinstance(group, dict) or group.get("is_superuser"):
                continue
            name = group.get("name")
            if standard and name == standard:
                for m in _members(group):
                    standard_members[m.username] = m
            elif name in supers:
                for m in _members(group):
                    super_members[m.username] = m

        # In both groups means super (`admin_auth.resolve_role`).
        for username in super_members:
            standard_members.pop(username, None)
        return Roster(
            configured=True,
            super_admins=tuple(sorted(super_members.values(), key=lambda m: m.username.casefold())),
            standard_admins=tuple(sorted(standard_members.values(), key=lambda m: m.username.casefold())),
        )
