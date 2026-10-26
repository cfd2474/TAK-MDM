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

"""Records every change made through the console or the admin API (W421).

Two halves, because neither can do it alone:

* :func:`audit_trail`, a dependency attached at admin-router registration
  **before** `csrf_protected`, notes who is asking and from where. Attached
  there, a route added tomorrow is recorded without anyone remembering to (the
  D70 principle), and a request the CSRF check refuses is still noted.
* :class:`AuditMiddleware` writes the row once the response is known. A
  dependency never sees the response, and most refusals here are *returned*,
  not raised: a 303 to `?error=…`, or the editor's 422. Recorded from the
  dependency, every one of those read "ok".

⚠️ **Its own session.** The row is written through the factory the dependency
resolved (`get_session_factory`), not the request's session: a change that
fails and rolls back is still recorded, and recording can never commit half of
a change that failed.

⚠️ **Never throws into the request.** A broken audit write is logged loudly,
but it does not turn an operator's successful change into an error page.
"""

from __future__ import annotations

import ipaddress
import logging
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable
from urllib.parse import parse_qs, urlsplit

from fastapi import Depends, Request

from app.api.deps import get_session_factory
from app.config import Settings, get_settings
from app.security import admin_auth
from app.security.admin_auth import AdminIdentity, admin_required
from app.services import audit, audit_log, clock

logger = logging.getLogger(__name__)

_UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}

#: Where the dependency leaves the request for the middleware.
_STATE_KEY = "audit_pending"


@dataclass
class _Pending:
    actor: str
    groups: tuple[str, ...]
    anonymous: bool
    source_ip: str | None
    session_factory: Callable[[], Any]


def client_address(request: Request, settings: Settings) -> str | None:
    """Who sent it, as the proxy saw them.

    The proxy appends the address it saw to `X-Forwarded-For`, so the last entry
    is the real one, but only when the request really came through a proxy
    named in `TAKMDM_TRUSTED_PROXIES`. Otherwise the header is whatever the
    client wrote, and the peer is the only honest answer.

    ⚠️ **Not `_peer_is_trusted`.** That check lets everything through when the
    setting is unset, so it can't open the door to an address the client
    chose. This one opens it only when proxies are named and the peer is one of
    them. It is a record, never a decision: nothing reads it to allow anything.
    """
    peer = request.client.host if request.client else None
    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded or not peer:
        return peer
    networks = admin_auth._trusted_networks(settings.trusted_proxies or "")
    try:
        through_proxy = any(ipaddress.ip_address(peer) in net for net in networks)
    except ValueError:
        through_proxy = False
    return (forwarded.split(",")[-1].strip() or peer) if through_proxy else peer


class _Presence:
    """Records each user's first request of the day (console time), once (C3).

    Reads are not otherwise recorded, so without this "who used the console
    today" would miss everyone who only looked.

    ⚠️ **Remembered per process**, so the database is asked once per user per
    day, not once per request. Two workers may each write the row once; the
    page reads the earliest, so a duplicate costs a row, not a wrong answer.
    """

    _TZ_FOR = timedelta(seconds=60)

    def __init__(self) -> None:
        self._seen: set[tuple[str, date]] = set()
        self._tz: tuple[datetime, Any] | None = None
        self._lock = threading.Lock()

    def _zone(self, session_factory):
        now = datetime.now(timezone.utc)
        cached = self._tz
        if cached is None or now - cached[0] > self._TZ_FOR:
            with session_factory() as session:
                cached = (now, clock.configured(session))
            self._tz = cached
        return cached[1]

    def note(self, pending: _Pending, method: str, path: str) -> None:
        try:
            tz = self._zone(pending.session_factory)
            key = (pending.actor, datetime.now(timezone.utc).astimezone(tz).date())
            with self._lock:
                if key in self._seen:
                    return
                self._seen = {k for k in self._seen if k[1] == key[1]}  # yesterday's go
                self._seen.add(key)
            with pending.session_factory() as session:
                if audit_log.seen_today(session, pending.actor, tz):
                    return
                audit.record(
                    session, actor=pending.actor, groups=pending.groups, anonymous=pending.anonymous,
                    source_ip=pending.source_ip, method=method, path=path, status_code=None,
                    description=audit.Description(audit_log.FIRST_SEEN, "First request today"),
                )
        except Exception:  # noqa: BLE001 - see the module docstring
            logger.exception("could not record that %s was seen today", pending.actor)

    def forget(self) -> None:
        """For tests: a fresh process."""
        with self._lock:
            self._seen.clear()
            self._tz = None


presence = _Presence()


def audit_trail(
    request: Request,
    identity: AdminIdentity = Depends(admin_required),
    settings: Settings = Depends(get_settings),
    session_factory=Depends(get_session_factory),
) -> None:
    """Note who is asking. :class:`AuditMiddleware` records a change, and
    :data:`presence` the first request of the day, once the response is out."""
    setattr(request.state, _STATE_KEY, _Pending(
        actor=identity.username,
        groups=tuple(identity.groups),
        anonymous=identity.is_anonymous,
        source_ip=client_address(request, settings),
        session_factory=session_factory,
    ))


def refusal_in(location: str | None) -> str | None:
    """The `error` a redirect carries back to the page, if it carries one.

    The console's way of saying no to a form post is a 303 to the page it came
    from with `?error=…` (or a tab's own `?play_error=…`), so a redirect is a
    refusal exactly when it says one.
    """
    if not location:
        return None
    for key, values in parse_qs(urlsplit(location).query).items():
        if key == "error" or key.endswith("_error"):
            return values[0]
    return None


class AuditMiddleware:
    """Writes the row for a request :func:`audit_trail` noted, with its real outcome."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        if scope["method"].upper() not in _UNSAFE:
            scope.setdefault("state", {})
            try:
                await self.app(scope, receive, send)
            finally:
                self._presence(scope)
            return

        # ⚠️ Made here, before the app runs, so the dict the dependency writes
        # into is this one even if a layer below copies the scope. Insurance,
        # not a control, and said plainly because a mutation sweep survives it:
        # nothing below copies the scope today.
        scope.setdefault("state", {})
        seen: dict[str, Any] = {"status": None, "location": None}

        async def watch(message) -> None:
            if message["type"] == "http.response.start":
                seen["status"] = message["status"]
                for name, value in message.get("headers", []):
                    if name.lower() == b"location":
                        seen["location"] = value.decode("latin-1")
            await send(message)

        try:
            await self.app(scope, receive, watch)
        except Exception:
            if seen["status"] is None:
                seen["status"] = 500
            raise
        finally:
            # No presence row: the change itself is the user's activity today.
            self._record(scope, seen["status"], seen["location"])

    @staticmethod
    def _presence(scope) -> None:
        pending: _Pending | None = (scope.get("state") or {}).get(_STATE_KEY)
        if pending is not None:
            presence.note(pending, scope["method"].upper(), scope["path"])

    @staticmethod
    def _record(scope, status: int | None, location: str | None) -> None:
        state = scope.get("state") or {}
        pending: _Pending | None = state.get(_STATE_KEY)
        if pending is None:
            return  # not an admin request, or refused before anyone was identified
        try:
            with pending.session_factory() as session:
                audit.record(
                    session,
                    actor=pending.actor,
                    groups=pending.groups,
                    anonymous=pending.anonymous,
                    source_ip=pending.source_ip,
                    method=scope["method"].upper(),
                    path=scope["path"],
                    status_code=status,
                    refusal=refusal_in(location),
                    description=state.get(audit.STATE_KEY),
                )
        except Exception:  # noqa: BLE001 - see the module docstring
            logger.exception("could not write the audit record for %s %s",
                             scope.get("method"), scope.get("path"))


def install(app) -> None:
    app.add_middleware(AuditMiddleware)
