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

"""Response headers that constrain what a browser will do with our pages.

`SEC_AUDIT.md` **M-6**. These do not fix a vulnerability on their own; they
decide how far one gets. A stored script in a policy description is a defect
either way, but under `script-src 'self'` it renders as text instead of running
with the signed-in administrator's session.

Three things were established before any of this was written, because each
would have made the policy either useless or actively breaking:

* **The console has no inline script.** It did — four handlers — and they were
  converted first (`data-confirm`, `data-reveals`, `data-add-app-group` in
  `atlas.js`). That is what buys a `script-src` with no `'unsafe-inline'`, which
  is the only directive here that stops an XSS rather than shaping it.
* **Map tiles are fetched by the browser from an operator-configurable URL.**
  A reflexive `img-src 'self'` would silently blank every map on every
  deployment that had pointed `location.tile_url` anywhere — including the
  default, which is openstreetmap.org. See `IMG_SRC` below.
* **HSTS is set by Caddy already.** It is deliberately not set here. Two places
  emitting one header is how the two come to disagree, and the one an operator
  reads is not necessarily the one the browser obeys.
"""

from __future__ import annotations

#: Where the browser may load images from.
#:
#: ⚠️ `https:` is wider than the rest of this policy and that is deliberate.
#: Map tiles come from `location.tile_url`, which an operator sets at runtime to
#: whatever tile server they use; the value lives in the database, changes
#: without a restart, and is read per page. Naming allowed origins here would
#: mean either a database read on every response or a policy that goes stale the
#: moment the setting is edited — and the failure mode of getting it wrong is a
#: map that is simply blank, with the reason only in the browser console.
#:
#: `data:` is required by Leaflet, which inlines a transparent GIF.
IMG_SRC = "'self' data: https:"

#: The policy for the console and the API.
BASE_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    # Inline *attributes* — style="..." — need this, and the templates are full
    # of them. It is a far weaker concession than script-src would be: the worst
    # an injected style does is deface a page.
    "style-src 'self' 'unsafe-inline'; "
    f"img-src {IMG_SRC}; "
    "font-src 'self'; "
    # Every fetch the console makes is same-origin. Geocoding and address
    # suggestions look like exceptions and are not: those calls are made by the
    # server, in app/services/geocoding.py, precisely so the browser never talks
    # to a third party.
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)

#: Paths whose CSP has to be loosened, and the only ones.
#:
#: ⚠️ FastAPI's built-in API documentation loads Swagger UI from a CDN and
#: bootstraps it with an inline `<script>`. Under `BASE_CSP` those pages render
#: as a blank frame with an error only in the browser console — working
#: endpoints, broken documentation, and nothing to suggest the cause. Rather
#: than weaken the policy everywhere for two pages nobody's session is at risk
#: on, they get their own.
DOCS_PATHS = ("/docs", "/redoc", "/docs/oauth2-redirect")

_CDN = "https://cdn.jsdelivr.net"

DOCS_CSP = (
    "default-src 'self'; "
    f"script-src 'self' 'unsafe-inline' {_CDN}; "
    f"style-src 'self' 'unsafe-inline' {_CDN}; "
    f"img-src {IMG_SRC}; "
    f"font-src 'self' {_CDN}; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)

#: Headers that do not vary by path.
#:
#: `Referrer-Policy: same-origin` rather than the usual
#: `strict-origin-when-cross-origin`: the cross-origin requests this console
#: makes are tile fetches, and a serial number or device id in the console URL
#: is not something a tile provider needs a copy of.
STATIC_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    # frame-ancestors supersedes this everywhere it is understood. Kept for the
    # browsers that do not.
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": (
        "geolocation=(), camera=(), microphone=(), payment=(), usb=()"
    ),
}


def csp_for(path: str) -> str:
    """The Content-Security-Policy for a request path."""
    if path in DOCS_PATHS:
        return DOCS_CSP
    return BASE_CSP


def headers_for(path: str) -> dict[str, str]:
    """Every security header this response should carry.

    A pure function of the path, so the policy can be asserted without a client,
    a database or a running application.
    """
    return dict(STATIC_HEADERS, **{"Content-Security-Policy": csp_for(path)})


def install(app) -> None:
    """Attach the headers to every response the application produces.

    Middleware rather than a dependency: a dependency covers the routes somebody
    remembered to put it on, and the static mount and the error responses are
    exactly the ones that get forgotten.
    """

    @app.middleware("http")
    async def _security_headers(request, call_next):
        response = await call_next(request)
        for name, value in headers_for(request.url.path).items():
            # ⚠️ setdefault, not assignment. A route that has deliberately set
            # its own — a download that must be framed, say — keeps it, and the
            # override is visible where it is made rather than silently undone
            # here.
            response.headers.setdefault(name, value)
        return response
