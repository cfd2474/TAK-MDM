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

"""`SEC_AUDIT.md` **S-1** — proving the identity headers came from the proxy.

ATLAS reads the administrator from `X-Authentik-Username`. Nothing in that
header proves Caddy set it, so anything able to open a socket to the
application's port is an administrator by sending two headers.

⚠️ **`TAKMDM_TRUSTED_PROXIES` cannot close this and never could.** Caddy runs on
the *host* and reaches the container through the bridge gateway — and so does
every other process on that host. A peer address cannot separate them. It closes
accidental exposure from elsewhere on the network and leaves host-local forgery
untouched, which is why S-1 stayed open after v1.16.0.

A secret the proxy holds *can* separate them: Caddy attaches
`X-Infratak-Proxy-Auth` only after `forward_auth` has passed.

⚠️ **Unset means unchecked, and that is the important half of the design.** The
header exists only where the reverse proxy emits it. A deployment whose proxy
does not — an older infra-TAK, a Caddyfile not yet regenerated — would otherwise
reject every administrator, with the console as the thing they would use to fix
it. Fail-open when unconfigured, fail-closed when configured.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

SECRET = "b3d1f0c2a9e84f17bb6d5c2e0a7f391d"

ADMIN = {
    "x-authentik-username": "proxy-admin",
    "x-authentik-groups": "authentik Admins",
}


@pytest.fixture
def gated(client: TestClient, settings):
    """Authentication on, and the proxy-auth gate armed.

    ⚠️ `admin_group` is cleared. The Settings default is `takmdm-admins`, a
    group no Authentik has — leaving it set made every test here fail with 403
    on the *group* check before reaching the proxy-auth one, which is a
    different finding and would have made these assertions meaningless.
    """
    settings.admin_auth_mode = "forward_auth"
    settings.admin_group = ""
    settings.proxy_auth_secret = SECRET
    yield client
    settings.admin_auth_mode = "disabled"
    settings.proxy_auth_secret = ""


def test_a_request_carrying_the_secret_is_let_through(gated: TestClient):
    response = gated.get(
        "/fleet", headers={**ADMIN, "x-infratak-proxy-auth": SECRET}
    )

    assert response.status_code == 200, response.text


def test_forged_identity_headers_alone_are_refused(gated: TestClient):
    """⚠️ The finding, exactly.

    Two headers and a socket used to be enough. This is the request a
    host-local process makes, and it now fails before the identity is read.
    """
    response = gated.get("/fleet", headers=ADMIN)

    assert response.status_code == 401, response.text


def test_a_wrong_secret_is_refused(gated: TestClient):
    response = gated.get(
        "/fleet", headers={**ADMIN, "x-infratak-proxy-auth": "not-the-secret"}
    )

    assert response.status_code == 401


def test_an_empty_secret_header_is_refused(gated: TestClient):
    """⚠️ Empty must not compare equal to unset.

    The setting being blank turns the gate off; a *request* offering nothing
    must still be refused while the gate is on, or a forger simply sends the
    header empty.
    """
    response = gated.get("/fleet", headers={**ADMIN, "x-infratak-proxy-auth": ""})

    assert response.status_code == 401


def test_the_gate_is_off_until_a_secret_is_configured(client: TestClient, settings):
    """⚠️ The property that makes this safe to ship before the proxy emits it.

    An ATLAS that demanded the header on every deployment would lock out every
    operator whose infra-TAK predates the injection — and the console is what
    they would use to recover.
    """
    settings.admin_auth_mode = "forward_auth"
    settings.admin_group = ""
    settings.proxy_auth_secret = ""
    try:
        response = client.get("/fleet", headers=ADMIN)
    finally:
        settings.admin_auth_mode = "disabled"

    assert response.status_code == 200, response.text


def test_the_check_runs_before_the_identity_is_read(gated: TestClient, caplog):
    """A refused caller must never be authenticated, even in the log.

    ⚠️ Same reasoning as the peer check, and the same ordering. Authenticating
    first and rejecting after leaves an audit trail saying somebody signed in.
    """
    import logging

    with caplog.at_level(logging.INFO):
        gated.get("/fleet", headers=ADMIN)

    assert not any(
        "authenticated" in record.message and "groups as received" in record.message
        for record in caplog.records
    ), [r.message for r in caplog.records]


# --------------------------------------------------------------------------- #
# H-1 — ATLAS checking the group itself
# --------------------------------------------------------------------------- #


def test_the_group_is_enforced_when_one_is_named(client: TestClient, settings):
    """⚠️ Closes H-1's residual: if Authentik's application binding is ever
    removed — it was found absent on a live box once — ATLAS still refuses."""
    settings.admin_auth_mode = "forward_auth"
    settings.admin_group = "authentik Admins"
    try:
        allowed = client.get("/fleet", headers=ADMIN)
        refused = client.get(
            "/fleet",
            headers={
                "x-authentik-username": "someone",
                "x-authentik-groups": "tak_LECK FAMILY",
            },
        )
    finally:
        settings.admin_auth_mode = "disabled"

    assert allowed.status_code == 200, allowed.text
    assert refused.status_code == 403, refused.text


def test_a_group_name_containing_a_space_survives_parsing(client: TestClient, settings):
    """⚠️ `authentik Admins` has a space, and it is the group to use.

    `_split_groups` splits on `|` or `,` and strips — never on whitespace. A
    splitter that took spaces would make the only sensible value unusable, and
    the symptom would be every administrator refused.
    """
    settings.admin_auth_mode = "forward_auth"
    settings.admin_group = "authentik Admins"
    try:
        response = client.get(
            "/fleet",
            headers={
                "x-authentik-username": "admin",
                "x-authentik-groups": "vid_public|authentik Admins|tak_ROLE_ADMIN",
            },
        )
    finally:
        settings.admin_auth_mode = "disabled"

    assert response.status_code == 200, response.text


def test_the_groups_received_are_announced_once(client: TestClient, settings, caplog):
    """⚠️ Choosing TAKMDM_ADMIN_GROUP otherwise means guessing what Authentik
    sends, and guessing wrong locks everyone out of the console they would use
    to correct it. One log line makes the setting verifiable."""
    import logging

    from app.security import admin_auth

    admin_auth._ANNOUNCED_GROUPS = False
    settings.admin_auth_mode = "forward_auth"
    settings.admin_group = ""
    try:
        with caplog.at_level(logging.INFO):
            client.get("/fleet", headers=ADMIN)
            client.get("/fleet", headers=ADMIN)
    finally:
        settings.admin_auth_mode = "disabled"

    announcements = [
        r for r in caplog.records if "groups as received" in r.message
    ]
    assert len(announcements) == 1, [r.message for r in announcements]
    assert "authentik Admins" in announcements[0].getMessage()
