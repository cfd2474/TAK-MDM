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

"""A sign-in that a reload cannot fix, and the way out of it.

When ATLAS reads the administrator from Authentik's signed token, a browser can
hold an Authentik session whose token ATLAS will not accept: the session began
before the server changed how tokens are signed, or while Authentik was briefly
without its signing key. Authentik keeps sending that same token until the
session ends, so "reload the page" does not help for up to an hour.

Signing out of Authentik's outpost ends that session, and the next page load
signs in again with a token ATLAS accepts. This module carries that way out.

⚠️ **A link, never an automatic redirect.** A background request refused in the
middle of someone's work must not sign them out by itself.
"""

from __future__ import annotations

import html

from fastapi import HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, Response

#: Authentik's outpost serves this on every host it protects, ATLAS's included.
SIGN_OUT_PATH = "/outpost.goauthentik.io/sign_out"

DETAIL = ("your sign-in could not be verified; sign out and sign in again "
          "(a reload does not help)")


class SignInRefused(HTTPException):
    """401 for a token that was refused for a reason other than its age."""

    def __init__(self) -> None:
        super().__init__(status.HTTP_401_UNAUTHORIZED, DETAIL)
        self.sign_out = SIGN_OUT_PATH


def _wants_page(request: Request) -> bool:
    """A browser navigating (a page load or a form post), not a script.

    Browsers send `text/html` in Accept only for a navigation; `fetch` and
    XHR send `*/*` unless told otherwise.
    """
    return "text/html" in request.headers.get("accept", "")


def page(exc: SignInRefused) -> str:
    """A minimal page: no script, no style, nothing the CSP has to allow."""
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>Sign in again</title></head><body>"
        "<h1>Sign in again</h1>"
        "<p>ATLAS could not verify your sign-in. Reloading the page will not fix "
        "this. Sign out, and you will be asked to sign in again.</p>"
        "<p><a href=\"%s\">Sign out and sign in again</a></p>"
        "</body></html>" % html.escape(exc.sign_out, quote=True)
    )


async def respond(request: Request, exc: SignInRefused) -> Response:
    """The exception handler: a page for a browser, JSON for the API."""
    if _wants_page(request):
        return HTMLResponse(page(exc), status_code=exc.status_code)
    return JSONResponse(status_code=exc.status_code,
                        content={"detail": exc.detail, "sign_out": exc.sign_out})
