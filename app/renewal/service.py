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

"""The renewal container's HTTP surface (W458). Reached only by ATLAS's API.

    GET    /health            {"configured": bool}            no key needed
    POST   /challenge         {"nonce", "expires_in"}
    POST   /mint              proof in, a ten-minute password out
    DELETE /tokens/{id}       delete a token this container made

Every call but `/health` needs `Authorization: Bearer <client key>`, the key
InfraTAK wrote both here and into ATLAS's `.env`.

Each mint and each refusal is one log line, with the user, the connection and
the reason. Never the password.

W461: a certificate TAK Server revoked gets 403 with `X-Atlas-Refusal:
revoked`; a missing or stale revoked list gets 503 (`revocation`).
"""

from __future__ import annotations

import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Callable

from fastapi import FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, Field

from app.renewal import proof, revocation
from app.renewal.authentik import Authentik, AuthentikError, Refused
from app.renewal.files import Config, RenewalFiles
from app.renewal.limits import Limited, RateLimiter

log = logging.getLogger("atlas.renewal")

#: W461: set on a 403 for a certificate TAK Server revoked, so ATLAS stops
#: trying that certificate instead of waiting a day and asking again.
REFUSAL_HEADER = "X-Atlas-Refusal"


class MintRequest(BaseModel):
    nonce: str = Field(max_length=200)
    connect_string: str = Field(max_length=300)
    certificate: str = Field(max_length=20_000)
    chain: list[str] = Field(default_factory=list, max_length=proof.MAX_CHAIN)
    signature: str = Field(max_length=2_000)


def _audit(event: str, **fields) -> None:
    log.info(json.dumps({"event": event, **fields}, sort_keys=True))


def create_app(files: RenewalFiles | None = None,
               authentik_factory: Callable[[Config], Authentik] | None = None,
               nonces: proof.Nonces | None = None,
               limiter: RateLimiter | None = None) -> FastAPI:
    files = files or RenewalFiles()
    authentik_factory = authentik_factory or (
        lambda c: Authentik(c.authentik_url, c.authentik_token))
    nonces = nonces or proof.Nonces()
    limiter = limiter or RateLimiter()
    app = FastAPI(title="ATLAS renewal", docs_url=None, redoc_url=None, openapi_url=None)

    def config_for(authorization: str | None) -> Config:
        config = files.load()
        if config is None:
            raise HTTPException(503, "certificate renewal is not set up on this server")
        presented = (authorization or "").removeprefix("Bearer ").strip()
        if not hmac.compare_digest(presented.encode(), config.client_key.encode()):
            raise HTTPException(401, "wrong client key")
        return config

    @app.get("/health")
    def health() -> dict:
        return {"configured": files.load() is not None}

    @app.post("/challenge")
    def challenge(authorization: str | None = Header(default=None)) -> dict:
        config_for(authorization)
        return {"nonce": nonces.issue(), "expires_in": proof.NONCE_TTL_SECONDS}

    @app.post("/mint")
    def mint(body: MintRequest, authorization: str | None = Header(default=None)) -> dict:
        config = config_for(authorization)
        where = {"connection": body.connect_string}
        try:
            nonces.redeem(body.nonce)
            proven = proof.prove(
                certificate=body.certificate, chain=body.chain, signature=body.signature,
                nonce=body.nonce, connect_string=body.connect_string,
                anchors_pem=config.tak_ca_pem)
        except proof.ProofError as exc:
            _audit("refused", reason=str(exc), **where)
            raise HTTPException(400, str(exc)) from None
        username = where["user"] = proven.username
        # W461: before Authentik, so a revoked certificate never gets a login.
        try:
            revocation.parse(config.revoked, config.crls_pem).check(
                proven.leaf, proven.issuer, datetime.now(timezone.utc))
        except revocation.Revoked as exc:
            _audit("refused", reason=str(exc), **where)
            raise HTTPException(403, str(exc), headers={REFUSAL_HEADER: "revoked"}) from None
        except revocation.Unknown as exc:
            _audit("refused", reason=str(exc), **where)
            raise HTTPException(503, str(exc)) from None
        authentik = authentik_factory(config)
        try:
            user = authentik.user(username)
            Authentik.check_eligible(user)
            limiter.take(username)
            identifier, key, expires = authentik.mint(user)
        except Refused as exc:
            _audit("refused", reason=str(exc), **where)
            raise HTTPException(403, str(exc)) from None
        except Limited as exc:
            _audit("refused", reason=str(exc), **where)
            raise HTTPException(429, str(exc)) from None
        except AuthentikError as exc:
            _audit("failed", reason=str(exc), **where)
            raise HTTPException(502, str(exc)) from None
        finally:
            authentik.close()
        _audit("minted", identifier=identifier, expires=expires.isoformat(), **where)
        return {"username": username, "identifier": identifier, "password": key,
                "expires": expires.isoformat()}

    @app.delete("/tokens/{identifier}", status_code=204)
    def delete(identifier: str, authorization: str | None = Header(default=None)) -> Response:
        config = config_for(authorization)
        authentik = authentik_factory(config)
        try:
            authentik.delete(identifier)
        except Refused as exc:
            raise HTTPException(400, str(exc)) from None
        except AuthentikError as exc:
            raise HTTPException(502, str(exc)) from None
        finally:
            authentik.close()
        _audit("deleted", identifier=identifier)
        return Response(status_code=204)

    return app


# uvicorn configures its own loggers only; without this the audit lines vanish.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
app = create_app()
