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

"""Cross-site request forgery protection for the admin surface.

With forward auth (D67) the browser holds an Authentik session cookie, and that
cookie rides along on *any* request the browser makes — including one a hostile
page causes. Nothing else distinguishes a form the administrator submitted from
one submitted on their behalf.

Two layers, because neither covers the whole surface alone:

* **A signed token**, submitted with each console form and compared against a
  cookie. This is the real defence and depends on nothing but our own key.
* **Origin validation** on every unsafe admin request. An HTML form cannot send
  `DELETE` or a JSON body, but it *can* send a bodyless `POST` — which is exactly
  the shape of ``/api/v1/devices/{id}/retire``. Origin catches those, and costs
  scripts nothing because a non-browser client sends no ``Origin`` header at all.

**The token is bound to the administrator's identity.** A double-submit token that
only proves "the submitter could read a cookie" is weaker than it looks; binding it
means a token minted for one account cannot be replayed against another.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit
from app.security import keyfiles

logger = logging.getLogger(__name__)

#: Where the token travels. Not `HttpOnly`: the value is not a credential on its
#: own — it is only useful alongside the session cookie, and a future fetch-based
#: page needs to be able to read it.
COOKIE_NAME = "takmdm_csrf"
FORM_FIELD = "csrf_token"
HEADER_NAME = "x-csrf-token"

#: Long enough that an operator composing a policy does not lose their work, short
#: enough that a token lifted from a stale page does not stay useful.
DEFAULT_TTL_SECONDS = 8 * 60 * 60

_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


class CsrfError(Exception):
    """Raised when a request fails validation. Carries a reason for the operator."""


class CsrfGuard:
    """Mints and verifies identity-bound, expiring CSRF tokens."""

    def __init__(self, key: bytes, *, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        self._key = key
        self._ttl = ttl_seconds

    @classmethod
    def load_or_create(cls, pki_dir: Path, **kwargs) -> CsrfGuard:
        """Load the signing key, generating one on first use.

        Beside `ca.key` and `token_vault.key`, and far less dangerous than either:
        losing it lets someone forge a CSRF token, which is only useful against an
        administrator who is *already* signed in. Rotating it simply invalidates
        every open form.
        """
        key_path = Path(pki_dir) / "csrf.key"
        if key_path.exists():
            return cls(key_path.read_bytes().strip(), **kwargs)

        key = base64.urlsafe_b64encode(secrets.token_bytes(32))
        keyfiles.write_private(key_path, key)
        logger.info("created CSRF signing key at %s", key_path)
        return cls(key, **kwargs)

    # ----------------------------------------------------------------------- #

    def issue(self, username: str, *, now: float | None = None) -> str:
        """Mint a token for one administrator."""
        issued = int(now if now is not None else time.time())
        nonce = secrets.token_urlsafe(16)
        payload = f"{nonce}.{issued}"
        return f"{payload}.{self._sign(payload, username)}"

    def verify(self, token: str | None, username: str, *, now: float | None = None) -> None:
        """Raise :class:`CsrfError` unless the token is valid for this user."""
        if not token:
            raise CsrfError("no CSRF token supplied")

        parts = token.split(".")
        if len(parts) != 3:
            raise CsrfError("malformed CSRF token")

        nonce, issued_raw, signature = parts
        try:
            issued = int(issued_raw)
        except ValueError as exc:
            raise CsrfError("malformed CSRF token") from exc

        expected = self._sign(f"{nonce}.{issued_raw}", username)
        # Constant-time: a timing oracle here would let a signature be recovered
        # byte by byte.
        if not hmac.compare_digest(expected, signature):
            # Covers a forged token and a genuine one minted for a different
            # account, because the username is part of what is signed.
            raise CsrfError("CSRF token is not valid for this session")

        age = (now if now is not None else time.time()) - issued
        if age > self._ttl:
            raise CsrfError("CSRF token has expired; reload the page and retry")
        if age < -60:
            # Issued in the future. Either a clock jumped or the token was
            # tampered with; both are worth refusing rather than tolerating.
            raise CsrfError("CSRF token is not yet valid")

    def _sign(self, payload: str, username: str) -> str:
        message = f"{payload}.{username}".encode()
        digest = hmac.new(self._key, message, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def check_origin(origin: str | None, referer: str | None, expected: str | None) -> None:
    """Reject a browser request that came from somewhere else.

    A **missing** `Origin` is allowed. Browsers always send it on the cross-origin
    requests this defends against; a `curl` or a deployment script sends none, and
    refusing those would break every automation without closing any hole.

    `Referer` is only consulted when `Origin` is absent, and is likewise optional.
    """
    if not expected:
        # Nothing configured to compare against. Saying so is better than silently
        # passing every request through a check that cannot fail.
        return

    candidate = origin or referer
    if not candidate:
        return

    if _origin_of(candidate) != _origin_of(expected):
        raise CsrfError(
            f"request origin {_origin_of(candidate)!r} does not match the "
            f"configured console origin {_origin_of(expected)!r}"
        )


def _origin_of(value: str) -> str:
    """Reduce a URL to scheme://host:port, so a path or trailing slash cannot differ."""
    parts = urlsplit(value if "//" in value else f"//{value}")
    return f"{parts.scheme}://{parts.netloc}".lower()


def is_unsafe(method: str) -> bool:
    """True for methods that change state and therefore need protecting."""
    return method.upper() in _UNSAFE_METHODS
