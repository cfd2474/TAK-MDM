"""CSRF protection for the admin surface (R11).

Copyright 2026 TAK-Solutions LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app.security import csrf

ADMIN = {
    "x-authentik-username": "csrf-admin",
    "x-authentik-groups": "takmdm-admins",
}
OTHER_ADMIN = {
    "x-authentik-username": "someone-else",
    "x-authentik-groups": "takmdm-admins",
}
ORIGIN = "https://atlas.example.org"


@pytest.fixture
def guarded(client: TestClient, settings):
    """A client with authentication on, so CSRF protection is live."""
    settings.admin_auth_mode = "forward_auth"
    settings.console_origin = ORIGIN
    yield client
    settings.admin_auth_mode = "disabled"
    settings.console_origin = ""


def token_from_page(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "the page rendered no CSRF token"
    return match.group(1)


def load_console(guarded: TestClient) -> str:
    """Fetch a page, which issues the cookie, and return its token."""
    response = guarded.get("/enrollment", headers=ADMIN)
    assert response.status_code == 200
    return token_from_page(response.text)


def make_token(guarded: TestClient) -> tuple[str, dict]:
    token = load_console(guarded)
    return token, {**ADMIN, "origin": ORIGIN}


# --------------------------------------------------------------------------- #
# The attack R11 describes
# --------------------------------------------------------------------------- #


def test_a_form_post_without_a_token_is_refused(guarded: TestClient):
    load_console(guarded)  # the browser now holds the cookie

    response = guarded.post(
        "/enrollment",
        data={"name": "forged", "ttl_hours": "24"},
        headers={**ADMIN, "origin": ORIGIN},
    )

    # This is the whole risk: the session cookie rides along, so without a token
    # nothing distinguishes this from a form the administrator submitted.
    assert response.status_code == 403


def test_a_cross_site_origin_is_refused(guarded: TestClient):
    token, _ = make_token(guarded)

    response = guarded.post(
        "/enrollment",
        data={"name": "evil", "ttl_hours": "24", "csrf_token": token},
        headers={**ADMIN, "origin": "https://attacker.example"},
    )

    assert response.status_code == 403


def test_a_legitimate_submission_succeeds(guarded: TestClient):
    token, headers = make_token(guarded)

    response = guarded.post(
        "/enrollment",
        data={"name": "genuine", "ttl_hours": "24", "csrf_token": token},
        headers=headers,
        follow_redirects=False,
    )

    assert response.status_code in (302, 303, 307)


# --------------------------------------------------------------------------- #
# Token validity
# --------------------------------------------------------------------------- #


def test_a_forged_token_is_refused(guarded: TestClient):
    load_console(guarded)

    response = guarded.post(
        "/enrollment",
        data={"name": "x", "ttl_hours": "24", "csrf_token": "made.123456.up"},
        headers={**ADMIN, "origin": ORIGIN},
    )

    assert response.status_code == 403


def test_another_administrators_token_is_refused(guarded: TestClient):
    stolen = load_console(guarded)

    response = guarded.post(
        "/enrollment",
        data={"name": "x", "ttl_hours": "24", "csrf_token": stolen},
        headers={**OTHER_ADMIN, "origin": ORIGIN},
    )

    # The token is signed over the username, so one minted for one account cannot
    # be replayed against another. A plain double-submit token would pass here.
    assert response.status_code == 403


def test_the_token_must_match_its_cookie(guarded: TestClient):
    token, headers = make_token(guarded)
    guarded.cookies.set(csrf.COOKIE_NAME, "a-different-value")

    response = guarded.post(
        "/enrollment",
        data={"name": "x", "ttl_hours": "24", "csrf_token": token},
        headers=headers,
    )

    # Double submit: a cross-site page can cause the cookie to be sent but cannot
    # read it, so it cannot put a matching value in the body.
    assert response.status_code == 403


def test_an_expired_token_is_refused():
    guard = csrf.CsrfGuard(b"k" * 32, ttl_seconds=60)
    token = guard.issue("admin", now=1000)

    with pytest.raises(csrf.CsrfError, match="expired"):
        guard.verify(token, "admin", now=1000 + 61)


def test_a_token_from_the_future_is_refused():
    guard = csrf.CsrfGuard(b"k" * 32)
    token = guard.issue("admin", now=10_000)

    with pytest.raises(csrf.CsrfError):
        guard.verify(token, "admin", now=1_000)


# --------------------------------------------------------------------------- #
# What must NOT be broken
# --------------------------------------------------------------------------- #


def test_safe_methods_need_no_token(guarded: TestClient):
    # A GET must never require one, or the console could not issue a token in the
    # first place.
    assert guarded.get("/", headers=ADMIN).status_code == 200
    assert guarded.get("/api/v1/devices", headers=ADMIN).status_code == 200


def test_a_script_sending_no_origin_still_works(guarded: TestClient):
    token = load_console(guarded)

    response = guarded.post(
        "/enrollment",
        data={"name": "from-a-script", "ttl_hours": "24", "csrf_token": token},
        headers=ADMIN,  # no Origin, as curl sends none
        follow_redirects=False,
    )

    # Browsers always send Origin on the cross-origin requests this defends
    # against. Refusing requests without one would break every deployment script
    # while closing no hole.
    assert response.status_code in (302, 303, 307)


def test_protection_is_inert_when_authentication_is_disabled(client: TestClient):
    # With no authentication there is no session to ride, and the request could
    # simply be made directly. Enforcing here would cost every local script a
    # round trip and protect nothing.
    response = client.post(
        "/enrollment", data={"name": "local-dev", "ttl_hours": "24"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303, 307)


def test_the_device_surface_is_untouched(guarded: TestClient, enrolled, mtls_headers):
    device = enrolled()
    headers = mtls_headers(device["certificate_pem"])

    # Devices authenticate by client certificate, not a cookie, so CSRF does not
    # apply — and requiring a token would break every tablet in the fleet.
    assert guarded.post(
        "/api/v1/device/checkin", json={}, headers=headers
    ).status_code == 200


# --------------------------------------------------------------------------- #
# Origin comparison
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "candidate,expected,ok",
    [
        ("https://a.example", "https://a.example", True),
        ("https://a.example/some/path", "https://a.example", True),
        ("https://a.example", "https://a.example/", True),
        ("http://a.example", "https://a.example", False),
        ("https://b.example", "https://a.example", False),
        ("https://a.example:8443", "https://a.example", False),
    ],
)
def test_origin_comparison(candidate, expected, ok):
    # Scheme and port are part of an origin. Comparing hostnames alone would let
    # a plaintext or wrong-port impostor through.
    if ok:
        csrf.check_origin(candidate, None, expected)
    else:
        with pytest.raises(csrf.CsrfError):
            csrf.check_origin(candidate, None, expected)


def test_compose_passes_the_console_origin_through():
    """The setting must actually reach the container.

    It did not: `docker-compose.yml` enumerates environment variables explicitly,
    so adding `TAKMDM_CONSOLE_ORIGIN` to `.env` left `console_origin` empty in the
    container and the origin check silently returned early. Every unit test passed
    — they set the value directly — and a hostile origin was accepted against the
    running stack. The same shape as the nginx traps in PROJECT_STATE: correct
    code, no effect, because of config plumbing.
    """
    import pathlib

    compose = pathlib.Path(__file__).resolve().parents[1] / "docker-compose.yml"
    assert "TAKMDM_CONSOLE_ORIGIN" in compose.read_text(encoding="utf-8")
