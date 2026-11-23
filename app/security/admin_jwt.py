"""The administrator's identity from Authentik's signed token (W504).

Authentik's proxy outpost sends `X-authentik-jwt`: the ID token of the
application's provider, signed by Authentik. Its `preferred_username` and
`groups` claims are the same identity the plain headers carry, but signed, and
`groups` is a JSON list, so every name arrives whole.

Why not the plain headers: see `tests/test_admin_jwt.py`.

This module only verifies a token and reads it; `admin_auth.identify` decides
what a refusal means for the request.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

import jwt

logger = logging.getLogger(__name__)

#: Public-key algorithms only. ⚠️ Never HS256: Authentik signs with the
#: provider's client secret when the provider has no signing key, and accepting
#: that would mean holding a secret that also lets its holder mint tokens.
#: Never `none`.
ALGORITHMS: tuple[str, ...] = ("RS256", "RS384", "RS512", "ES256", "ES384", "ES512")

#: Clock difference tolerated between Authentik and this host.
LEEWAY_SECONDS = 30

#: How long fetched keys are kept. An unknown `kid` refetches at once anyway,
#: so a rotated key works on its first use.
KEYS_LIFESPAN_SECONDS = 300

FETCH_TIMEOUT_SECONDS = 10


class TokenRefused(Exception):
    """The token cannot be used. The text is safe to log: it never holds the token."""

    def __init__(self, reason: str, *, expired: bool = False):
        super().__init__(reason)
        self.expired = expired


@dataclass(frozen=True)
class TokenIdentity:
    username: str
    groups: tuple[str, ...]
    email: str | None = None
    name: str | None = None


class KeySource(Protocol):
    def key_for(self, token: str) -> object:
        """The public key that should have signed this token."""


class JwksKeys:
    """Keys from the provider's JWKS endpoint, cached."""

    def __init__(self, url: str):
        self._client = jwt.PyJWKClient(
            url,
            cache_keys=True,
            lifespan=KEYS_LIFESPAN_SECONDS,
            timeout=FETCH_TIMEOUT_SECONDS,
        )

    def key_for(self, token: str) -> object:
        # ⚠️ PyJWT's base error, not only `PyJWKClientError`: an empty key set
        # (what a provider with no signing key serves) raises `PyJWKSetError`,
        # which is neither, and would have ended as a 500 rather than a refusal.
        # Network failures arrive as `PyJWKClientConnectionError`.
        try:
            return self._client.get_signing_key_from_jwt(token).key
        except jwt.PyJWTError as exc:
            raise TokenRefused("no matching signing key: %s" % exc) from exc


@lru_cache(maxsize=8)
def keys_at(url: str) -> JwksKeys:
    """One cache per JWKS address, shared by every request."""
    return JwksKeys(url)


def jwks_url(issuer: str | None, configured: str = "") -> str:
    """The JWKS address: the configured one, else Authentik's beside the issuer.

    📖 Authentik serves a provider's keys at `/application/o/<slug>/jwks/` and
    names `/application/o/<slug>/` as its issuer (per-provider issuer mode).

    ⚠️ Never the `X-authentik-meta-jwks` header: a key address taken from the
    request would let whoever shapes the request choose the key.
    """
    if configured.strip():
        return configured.strip()
    if not (issuer or "").strip():
        raise ValueError("a JWKS address needs an issuer or a configured address")
    return issuer.strip().rstrip("/") + "/jwks/"


def verify(token: str | None, keys: KeySource, *, issuer: str | None, audience: str) -> TokenIdentity:
    """Check the token and return who it names, or raise `TokenRefused`.

    `issuer` None skips the issuer check. That is safe only because the key is
    the provider's own (the InfraTAK module gives each ATLAS provider a key of
    its own) and `aud` names the provider: together they already say which
    provider issued the token.
    """
    if not token:
        raise TokenRefused("no token")
    try:
        algorithm = jwt.get_unverified_header(token).get("alg")
    except jwt.InvalidTokenError as exc:
        raise TokenRefused("unreadable token header: %s" % exc) from exc
    # ⚠️ Before the key lookup, so a token naming a symmetric algorithm never
    # gets as far as being checked against anything.
    if algorithm not in ALGORITHMS:
        raise TokenRefused("algorithm %r is not accepted" % algorithm)

    key = keys.key_for(token)
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=list(ALGORITHMS),
            audience=audience,
            issuer=issuer or None,
            leeway=LEEWAY_SECONDS,
            options={
                "require": ["exp", "aud", "preferred_username"] + (["iss"] if issuer else []),
                "verify_iss": bool(issuer),
            },
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenRefused("token expired", expired=True) from exc
    except jwt.InvalidTokenError as exc:
        raise TokenRefused(str(exc)) from exc

    username = claims.get("preferred_username")
    if not isinstance(username, str) or not username.strip():
        raise TokenRefused("token names no user")
    groups = claims.get("groups", [])
    if not isinstance(groups, list) or not all(isinstance(g, str) for g in groups):
        raise TokenRefused("token groups are not a list of names")
    email = claims.get("email")
    name = claims.get("name")
    return TokenIdentity(
        username=username.strip(),
        # Whole names, as Authentik holds them. Stripped only of the outer
        # spaces the header path also strips, never split.
        groups=tuple(g.strip() for g in groups if g.strip()),
        email=email if isinstance(email, str) else None,
        name=name if isinstance(name, str) else None,
    )
