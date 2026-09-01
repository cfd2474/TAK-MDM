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

"""Administrator authentication via an Authentik forward-auth proxy.

Authentik terminates the OIDC flow and forwards the resulting identity as headers.
This module reads them; it deliberately implements no OIDC itself. Discovery, PKCE,
token exchange, refresh and session handling are a large amount of security-critical
code solving a problem an identity provider already solves, and duplicating it here
would add risk without adding capability.

The trust model matches the mTLS one already in use for devices:

* the proxy is authoritative,
* the proxy **must** strip inbound copies of these headers, and
* the application must never be directly reachable.

Both surfaces therefore share one discipline rather than each inventing their own.

Devices are unaffected — they cannot perform an interactive login, so the
device-facing port keeps mTLS with no Authentik in the path.
"""

from __future__ import annotations

import enum
import logging
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from fastapi import Depends, HTTPException, Request, status

from app.config import Settings, get_settings
from app.security import csrf

logger = logging.getLogger(__name__)


class AuthMode(str, enum.Enum):
    """How the admin surface is protected.

    Only two values, deliberately. A partial or best-effort mode would be a mode
    nobody can reason about, and "is the console protected right now?" must have a
    yes/no answer.
    """

    DISABLED = "disabled"  # local development only
    FORWARD_AUTH = "forward_auth"  # Authentik proxy provider in front


@dataclass(frozen=True)
class AdminIdentity:
    """An authenticated administrator."""

    username: str
    email: str | None = None
    display_name: str | None = None
    groups: tuple[str, ...] = field(default_factory=tuple)
    # True when authentication is switched off, so callers and the UI can say so
    # rather than showing a fabricated user.
    is_anonymous: bool = False

    @property
    def label(self) -> str:
        return self.display_name or self.username


ANONYMOUS = AdminIdentity(
    username="anonymous",
    display_name="Unauthenticated (auth disabled)",
    is_anonymous=True,
)


def _split_groups(raw: str | None) -> tuple[str, ...]:
    """Authentik joins groups with '|' by default; commas are also seen."""
    if not raw:
        return ()
    separator = "|" if "|" in raw else ","
    return tuple(part.strip() for part in raw.split(separator) if part.strip())


def identify(request: Request, settings: Settings) -> AdminIdentity:
    """Resolve the caller, or raise 401/403. Never returns an unauthorized user."""
    mode = AuthMode(settings.admin_auth_mode)

    if mode is AuthMode.DISABLED:
        return ANONYMOUS

    username = request.headers.get(settings.admin_user_header)
    if not username:
        # Fail closed. A missing header means the proxy did not authenticate this
        # request — treating that as anonymous access would make a misconfigured
        # proxy silently equivalent to no protection at all.
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "no authenticated administrator; this endpoint must be reached through "
            "the Authentik proxy",
        )

    groups = _split_groups(request.headers.get(settings.admin_groups_header))
    required = settings.admin_group

    if required and required not in groups:
        # Authenticated but not authorized. Logged because it is the interesting
        # case operationally: someone signed in and was turned away.
        logger.warning(
            "admin access denied for %s: not in group %r (groups: %s)",
            username, required, ", ".join(groups) or "none",
        )
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"administrator access requires membership of {required!r}",
        )

    return AdminIdentity(
        username=username,
        email=request.headers.get(settings.admin_email_header),
        display_name=request.headers.get(settings.admin_name_header) or username,
        groups=groups,
    )


def admin_required(
    request: Request, settings: Settings = Depends(get_settings)
) -> AdminIdentity:
    """FastAPI dependency guarding every administrative route."""
    return identify(request, settings)


async def csrf_protected(
    request: Request,
    identity: AdminIdentity = Depends(admin_required),
    settings: Settings = Depends(get_settings),
) -> AdminIdentity:
    """Reject an unsafe request that this administrator did not deliberately make.

    Applied at router registration alongside `admin_required`, not per endpoint, so
    a new admin route is protected by default and forgetting a decorator cannot
    quietly open one (the D70 principle).

    **Enforcement follows authentication.** With `admin_auth_mode=disabled` there is
    no session for a hostile page to ride and the request could simply be made
    directly, so a token would protect nothing while costing every local script a
    round trip. The admin surface is protected or it is not; there is no third state
    (D68).

    Safe methods pass untouched — a GET must never require a token, or the console
    could not issue one in the first place.
    """
    if AuthMode(settings.admin_auth_mode) is AuthMode.DISABLED:
        return identity
    if not csrf.is_unsafe(request.method):
        return identity

    try:
        # First, because it is the layer that covers the endpoints an HTML form can
        # reach but a token was never attached to — a bodyless POST such as
        # /api/v1/devices/{id}/retire.
        csrf.check_origin(
            request.headers.get("origin"),
            request.headers.get("referer"),
            settings.console_origin,
        )

        # The token is demanded of **form-shaped** requests, which is precisely what
        # a cross-site HTML form can produce — including the bodyless POST that
        # /api/v1/devices/{id}/retire accepts.
        #
        # A JSON request is deliberately exempt. A form cannot send
        # `application/json`, and a cross-origin `fetch` that does triggers a CORS
        # preflight this application answers no headers for, so the browser refuses
        # it before we see it. Demanding a token there would break every script and
        # close nothing. What covers a JSON or text/plain `fetch` is the origin
        # check above — which is why an unset `console_origin` is warned about at
        # startup.
        if _is_form_shaped(request):
            submitted = request.headers.get(csrf.HEADER_NAME) or await _form_token(request)
            cookie = request.cookies.get(csrf.COOKIE_NAME)
            if not cookie:
                raise csrf.CsrfError("no CSRF cookie; reload the page and retry")
            if submitted != cookie:
                # Double submit: a cross-site page can cause the cookie to be sent
                # but cannot read it, so it cannot put a matching value in the body.
                raise csrf.CsrfError("CSRF token does not match its cookie")

            _guard(settings).verify(submitted, identity.username)
    except csrf.CsrfError as exc:
        logger.warning(
            "CSRF check failed for %s %s (%s): %s",
            request.method, request.url.path, identity.username, exc,
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc

    return identity


_FORM_CONTENT_TYPES = ("application/x-www-form-urlencoded", "multipart/form-data")


def _is_form_shaped(request: Request) -> bool:
    """True when this request is something a cross-site HTML form could have sent.

    A form can only submit `application/x-www-form-urlencoded` or
    `multipart/form-data`, and it always sets one of them — including when the
    form has no fields at all, which is the shape that reaches a bodyless endpoint
    such as `/api/v1/devices/{id}/retire`.

    Anything else came from a script or a `fetch`, and is covered by the origin
    check instead.
    """
    return request.headers.get("content-type", "").startswith(_FORM_CONTENT_TYPES)


async def _form_token(request: Request) -> str | None:
    """Read the token out of a submitted form.

    Safe to do here even though the endpoint will parse the body again: Starlette
    caches the parsed form on the request, so the second read is the same object
    rather than an attempt to consume an already-drained stream.

    Only for form content types. Calling `form()` on a JSON body would parse
    nothing useful, and on a malformed multipart body it raises — neither of which
    should surface as a CSRF failure.
    """
    content_type = request.headers.get("content-type", "")
    if not content_type.startswith(
        ("application/x-www-form-urlencoded", "multipart/form-data")
    ):
        return None

    try:
        form = await request.form()
    except Exception:  # noqa: BLE001 — a malformed body is not a CSRF verdict
        return None
    value = form.get(csrf.FORM_FIELD)
    return value if isinstance(value, str) else None


@lru_cache(maxsize=4)
def _guard_for(pki_dir: str) -> csrf.CsrfGuard:
    return csrf.CsrfGuard.load_or_create(Path(pki_dir))


def _guard(settings: Settings) -> csrf.CsrfGuard:
    return _guard_for(str(settings.pki_dir))


def issue_csrf_token(identity: AdminIdentity, settings: Settings) -> str:
    """Mint a token for embedding in a form."""
    return _guard(settings).issue(identity.username)


def warn_if_unprotected(settings: Settings) -> None:
    """Say so loudly at startup. Silence here is how a console ends up open."""
    if AuthMode(settings.admin_auth_mode) is AuthMode.DISABLED:
        logger.warning(
            "ADMIN AUTHENTICATION IS DISABLED. The console and write API are "
            "unauthenticated. Acceptable only on a loopback-bound development "
            "instance; set TAKMDM_ADMIN_AUTH_MODE=forward_auth behind Authentik "
            "before this is reachable by anyone else."
        )
        return

    if not settings.console_origin:
        # The token covers form submissions, which is the classic attack. What it
        # does not cover is a cross-origin `fetch` sending JSON or text/plain to a
        # bodyless endpoint, and the origin check is the only thing that does —
        # so an unset origin is a real gap, not a cosmetic one. Said out loud for
        # the same reason the disabled-auth warning is (D73).
        logger.warning(
            "TAKMDM_CONSOLE_ORIGIN is not set. CSRF tokens still protect the "
            "console's forms, but cross-origin requests cannot be rejected by "
            "origin, which is what covers the admin API's bodyless endpoints. "
            "Set it to the console's public origin, e.g. https://atlas.example.org"
        )
