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

"""`SEC_AUDIT.md` M-6 — the headers, and the two things that keep them honest.

The policy is worth very little on its own. Its value is almost entirely in
`script-src 'self'`, and that directive survives only as long as no template
reintroduces an inline handler — at which point the page breaks visibly, someone
adds `'unsafe-inline'` to make it work again, and the whole policy quietly
becomes decoration. The guards at the bottom are the ones that stop that.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.security import headers

TEMPLATES = Path("app/web/templates")
ATLAS_JS = Path("app/web/static/atlas.js")


def _directive(policy: str, name: str) -> list[str]:
    for part in policy.split(";"):
        tokens = part.split()
        if tokens and tokens[0] == name:
            return tokens[1:]
    return []


# --------------------------------------------------------------------------- #
# The policy itself
# --------------------------------------------------------------------------- #


def test_a_console_page_carries_every_security_header(client: TestClient):
    response = client.get("/fleet")

    assert response.status_code == 200
    for name, value in headers.STATIC_HEADERS.items():
        assert response.headers.get(name) == value, name
    assert response.headers.get("Content-Security-Policy") == headers.BASE_CSP


def test_a_device_endpoint_carries_them_too(client: TestClient):
    """Middleware, not a dependency, so nothing has to remember."""
    response = client.get("/api/v1/device/nonexistent-serial/config")

    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert "frame-ancestors 'none'" in response.headers.get("Content-Security-Policy", "")


def test_the_static_mount_carries_them_too(client: TestClient):
    """The mount sits outside every router, which is exactly why it gets missed."""
    response = client.get("/static/atlas.js")

    assert response.status_code == 200
    assert response.headers.get("X-Content-Type-Options") == "nosniff"


def test_a_not_found_carries_them_too(client: TestClient):
    """An error response is still a response a browser renders."""
    response = client.get("/no-such-page-anywhere")

    assert response.status_code == 404
    assert response.headers.get("Content-Security-Policy") == headers.BASE_CSP


def test_script_src_forbids_inline_script():
    """The one directive that turns an injection into inert text.

    ⚠️ If this ever fails because a page needed inline script, the fix is to move
    the script into atlas.js, never to relax the directive.
    """
    directive = _directive(headers.BASE_CSP, "script-src")

    assert directive == ["'self'"], directive


def test_the_policy_names_the_directives_that_have_no_fallback():
    """`default-src` does not cover these, so omitting one leaves it open."""
    for name in ("frame-ancestors", "form-action", "base-uri", "object-src"):
        assert _directive(headers.BASE_CSP, name), name


def test_hsts_is_left_to_the_reverse_proxy():
    """⚠️ Caddy sets it. Two emitters is how two policies come to disagree."""
    everything = " ".join(headers.STATIC_HEADERS) + headers.BASE_CSP

    assert "Strict-Transport-Security" not in everything


# --------------------------------------------------------------------------- #
# The map. A blank map is the failure this would actually have shipped.
# --------------------------------------------------------------------------- #


def test_the_default_tile_server_is_still_allowed_to_load():
    """⚠️ `img-src 'self'` would blank every map on every deployment.

    Tiles are fetched by the browser from `location.tile_url`, whose default is
    openstreetmap.org. Tying the assertion to that constant rather than to a
    literal means narrowing img-src fails here instead of in the field.
    """
    from app.services.locations import DEFAULT_TILE_URL

    assert DEFAULT_TILE_URL.startswith("https://")
    assert "https:" in _directive(headers.BASE_CSP, "img-src")


def test_leaflets_inlined_placeholder_is_allowed():
    """Leaflet inlines a transparent GIF as a data: URI for every empty tile."""
    assert "data:" in _directive(headers.BASE_CSP, "img-src")


def test_connect_src_is_same_origin_because_geocoding_is_server_side():
    """The browser never calls a geocoder; app/services/geocoding.py does."""
    assert _directive(headers.BASE_CSP, "connect-src") == ["'self'"]


# --------------------------------------------------------------------------- #
# The relaxation, and its blast radius
# --------------------------------------------------------------------------- #


def test_only_the_api_documentation_gets_the_looser_policy():
    for path in headers.DOCS_PATHS:
        assert headers.csp_for(path) == headers.DOCS_CSP

    for path in ("/", "/fleet", "/guides", "/docs/../fleet", "/static/atlas.js"):
        assert headers.csp_for(path) == headers.BASE_CSP, path


def test_the_looser_policy_still_refuses_framing_and_stray_forms():
    """Relaxed for Swagger's CDN and bootstrap, not abandoned."""
    assert "frame-ancestors 'none'" in headers.DOCS_CSP
    assert _directive(headers.DOCS_CSP, "form-action") == ["'self'"]
    assert _directive(headers.DOCS_CSP, "object-src") == ["'none'"]


# --------------------------------------------------------------------------- #
# What keeps script-src 'self' true
# --------------------------------------------------------------------------- #

#: Any `on*="..."` attribute. Rendered by the browser as inline script, and
#: blocked outright by `script-src 'self'`.
_INLINE_HANDLER = re.compile(r"""\son[a-z]+\s*=\s*["']""", re.IGNORECASE)


@pytest.mark.parametrize(
    "template", sorted(TEMPLATES.rglob("*.html")), ids=lambda p: p.name
)
def test_no_template_carries_an_inline_event_handler(template: Path):
    """⚠️ One of these does not degrade — the control simply stops working.

    Four were removed to make the policy possible (W181). The delegated
    replacements live in atlas.js: `data-confirm`, `data-reveals`,
    `data-add-app-group`.
    """
    body = io.open(template, encoding="utf-8").read()
    found = _INLINE_HANDLER.findall(body)

    assert not found, (
        f"{template} carries {found}; script-src 'self' blocks it. Move the "
        f"behaviour into atlas.js and reach it with a data- attribute."
    )


@pytest.mark.parametrize(
    "template", sorted(TEMPLATES.rglob("*.html")), ids=lambda p: p.name
)
def test_no_template_carries_an_inline_script_block(template: Path):
    """`<script>` with a body, as opposed to `<script src=...>`."""
    body = io.open(template, encoding="utf-8").read()

    for match in re.finditer(r"<script\b([^>]*)>(.*?)</script>", body, re.S | re.I):
        attributes, content = match.groups()
        assert "src=" in attributes, f"{template} has an inline <script> block"
        assert not content.strip(), f"{template} has a <script src> with a body"


#: Each converted handler: the attribute a template carries, the event its
#: replacement listens for, a fragment that must appear *inside* that listener,
#: and the expressions that read what the template wrote.
#:
#: ⚠️ Inside, not merely present. Three mutants got through weaker forms of this
#: check, and none of them changed how a single page renders:
#:
#: * deleting the `change` registration left `applyReveal` defined, unreferenced
#:   and passing;
#: * asserting `addEventListener("click"` alone passed when that listener was
#:   turned into an ordinary function, because atlas.js registers several;
#: * asserting the bare string `getAttribute("data-packages")` passed when this
#:   handler stopped reading it, because an unrelated feature 1900 lines away
#:   reads an attribute of the same name.
#:
#: A static check cannot prove the wiring runs. It can insist that removing
#: either half is visible here.
WIRING = [
    ("data-confirm", "submit", 'getAttribute("data-confirm")',
     ['e.target.getAttribute("data-confirm")']),
    ("data-reveals", "change", 'matches("[data-reveals]")',
     ['select.getAttribute("data-reveals")']),
    ("data-add-app-group", "click", 'closest("[data-add-app-group]")',
     ['JSON.parse(btn.getAttribute("data-packages")',
      'addAppGroup(btn.getAttribute("data-add-app-group")']),
]


#: How far past a registration its body is taken to extend.
#:
#: ⚠️ Needed *as well as* the next-registration bound, because the two fail in
#: opposite directions. Bounding only by the next registration lets a deleted
#: registration merge two bodies, so code that is no longer in any listener still
#: looks as though it is. Bounding only by a span lets a fragment from the
#: listener below be read as belonging to this one.
_LISTENER_SPAN = 600


def _listener_bodies(script: str, event: str) -> list[str]:
    """Each `document.addEventListener("<event>", ...)` body in atlas.js."""
    registration = f'document.addEventListener("{event}"'
    bodies, at = [], script.find(registration)
    while at != -1:
        following = script.find("document.addEventListener(", at + 1)
        end = len(script) if following == -1 else following
        bodies.append(script[at: min(end, at + _LISTENER_SPAN)])
        at = script.find(registration, at + 1)
    return bodies


@pytest.mark.parametrize(
    "attribute,event,fragment,reads", WIRING, ids=[row[0] for row in WIRING]
)
def test_each_replacement_attribute_is_actually_wired_up(
    attribute, event, fragment, reads
):
    """⚠️ A template attribute nothing listens for is a dead control.

    It looks right in the markup and does nothing in the browser — the exact
    failure converting an inline handler invites.
    """
    script = io.open(ATLAS_JS, encoding="utf-8").read()
    used_by = [
        path
        for path in TEMPLATES.rglob("*.html")
        if attribute in io.open(path, encoding="utf-8").read()
    ]

    assert used_by, f"{attribute} is wired up in atlas.js but no template uses it"

    bodies = _listener_bodies(script, event)
    assert any(fragment in body for body in bodies), (
        f"templates use {attribute}, but no document.addEventListener(\"{event}\") "
        f"in atlas.js contains {fragment} — so nothing happens in the browser."
    )

    # Firing is not enough: the handler also has to read what the template wrote.
    # One that stops consulting the attribute is still a dead control, and every
    # page still renders exactly the same.
    for reader in reads:
        assert reader in script, (
            f"atlas.js listens for {attribute} but never evaluates {reader}, so "
            f"the value the template writes is ignored."
        )


def test_an_app_group_button_carries_the_packages_it_should_insert():
    """The other half of the same pair, on the template side.

    ⚠️ Without `data-packages` the button still renders, still looks clickable,
    and inserts nothing. Before the conversion the packages were an argument in
    the onclick and could not go missing without a syntax error; as an attribute
    they can.
    """
    seen = 0
    for path in TEMPLATES.rglob("*.html"):
        body = io.open(path, encoding="utf-8").read()
        for match in re.finditer(r"<button[^>]*data-add-app-group[^>]*>", body):
            seen += 1
            assert "data-packages" in match.group(0), (
                f"{path} has an app-group button with no data-packages: "
                f"{match.group(0)}"
            )

    assert seen, "no app-group buttons found; this guard has stopped guarding"


# --------------------------------------------------------------------------- #
# What the conversion closed on its way past (SEC_AUDIT.md H-4)
# --------------------------------------------------------------------------- #

#: A serial number that ends the JavaScript string it used to be interpolated
#: into, and runs a call before re-opening it.
#:
#: ⚠️ Commas rather than semicolons, and no spaces. The serial also becomes the
#: certificate subject's CN, which is encoded as an ASN.1 `PrintableString` — so
#: a payload containing `;`, `<`, `!` or `_` is refused at enrolment by the X.509
#: encoder, long before it reaches a page. That narrows the alphabet to
#: `A-Z a-z 0-9 space ' ( ) + , - . / : = ?` and does **not** close the hole:
#: every character below is legal.
HOSTILE_SERIAL = "SER'),alert(1),('"


def test_a_device_serial_cannot_close_a_javascript_string(
    client: TestClient, enrolled
):
    """⚠️ Autoescaping did **not** protect the inline handler this replaced.

    `onsubmit="return confirm('Retire {{ device.serial_number }}?')"` escaped the
    apostrophe to `&#39;` — and the browser decodes entities in an attribute
    *before* the JavaScript parser sees it, so the string ended and what followed
    ran with the administrator's session. Jinja's autoescape is an HTML escape;
    the context here was JavaScript.

    A serial is reported by the device at enrolment and validated only for
    length, so it is attacker-supplied to anyone holding an enrolment credential
    — including the permanent QR that M-7 says is designed to be printed.

    As `data-confirm`, the same bytes are a string handed to `window.confirm`.
    """
    device = enrolled(serial=HOSTILE_SERIAL)

    body = client.get(f"/devices/{device['device_id']}").text

    assert "alert(1)" in body, "the serial should still be displayed"
    # The apostrophes stay entities, and there is no script context left on the
    # page for a decoded one to escape from.
    assert "SER')" not in body
    assert not _INLINE_HANDLER.findall(body)
