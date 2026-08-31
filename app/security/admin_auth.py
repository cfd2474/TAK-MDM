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

from fastapi import Depends, HTTPException, Request, status

from app.config import Settings, get_settings

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


def warn_if_unprotected(settings: Settings) -> None:
    """Say so loudly at startup. Silence here is how a console ends up open."""
    if AuthMode(settings.admin_auth_mode) is AuthMode.DISABLED:
        logger.warning(
            "ADMIN AUTHENTICATION IS DISABLED. The console and write API are "
            "unauthenticated. Acceptable only on a loopback-bound development "
            "instance; set TAKMDM_ADMIN_AUTH_MODE=forward_auth behind Authentik "
            "before this is reachable by anyone else."
        )
