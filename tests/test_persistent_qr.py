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

"""A provisioning QR that does not expire (W137).

⚠️ **The token never expired; the picture did.** A primary token is created with
a fifty-year life. What lasts fifteen minutes is the signed derivative the QR
carries, so "persistent" means putting the token's own secret in the picture
instead — and the tests that matter are the ones proving that difference
survives the clock, and that retiring the token still kills it.
"""

from __future__ import annotations

import re
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import Device, DeviceGroup, EnrollmentToken
from app.security import enrollment_qr as qr_module
from tests.conftest import ADMIN_HEADERS, generate_csr


@pytest.fixture(autouse=True)
def _qr_renderable(client, settings):
    """Without `agent_signature_checksum` the payload raises and the whole QR
    block is replaced by an error banner — every assertion here would then fail
    for a reason unrelated to what it tests. Depends on `client` deliberately;
    see test_group_qr.py."""
    from app.api.deps import get_settings
    from app.main import app

    configured = settings.model_copy(update={"agent_signature_checksum": "abc123"})
    app.dependency_overrides[get_settings] = lambda: configured
    yield
    app.dependency_overrides[get_settings] = lambda: settings


def _primary(client: TestClient) -> None:
    client.post(
        "/enrollment/primary",
        data={"name": "Primary"},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )


def _qr(client: TestClient, *, persistent: bool = False, group_id: str | None = None):
    data = {"wifi_ssid": "", "wifi_password": "", "wifi_security": "WPA"}
    if persistent:
        data["persistent"] = "true"
    if group_id:
        data["group_id"] = group_id
    return client.post("/enrollment/qr", data=data, headers=ADMIN_HEADERS)


def _secret_from(html: str) -> str:
    match = re.search(r"QR secret.*?<pre[^>]*>([^<]+)</pre>", html, re.S)
    assert match, "no QR secret rendered on the page"
    return match.group(1).strip()


def _enrol(client: TestClient, secret: str, serial: str = "PERSIST001"):
    return client.post(
        "/api/v1/enroll",
        json={
            "token": secret,
            "csr_pem": generate_csr(),
            "serial_number": serial,
            "model": "SM-X828U",
            "os_version": "16",
        },
    )


# --------------------------------------------------------------------------- #
# ⚠️ The whole feature, against the clock
# --------------------------------------------------------------------------- #


def test_a_persistent_qr_still_enrols_an_hour_later(client: TestClient, monkeypatch):
    """⚠️ The test the feature exists for.

    An hour on, the ordinary QR is refused and the persistent one still works.
    Asserting only that a persistent secret enrols *now* would pass against a
    version that had changed nothing at all.
    """
    _primary(client)
    short = _secret_from(_qr(client).text)
    persistent = _secret_from(_qr(client, persistent=True).text)

    later = time.time() + 3600
    monkeypatch.setattr(qr_module.time, "time", lambda: later)

    assert _enrol(client, short, "SHORTLIVED").status_code >= 400
    assert _enrol(client, persistent, "PERSIST001").status_code in (200, 201)


def test_retiring_the_token_kills_the_persistent_qr(client: TestClient):
    """⚠️ The only thing that stops it, so it had better work.

    The page tells an operator that retiring is how a leaked QR is undone. That
    sentence is a promise about behaviour.
    """
    _primary(client)
    secret = _secret_from(_qr(client, persistent=True).text)

    client.post("/enrollment/retire", headers=ADMIN_HEADERS, follow_redirects=False)

    assert _enrol(client, secret, "AFTERRETIRE").status_code >= 400


def test_generating_it_again_gives_the_same_code(client: TestClient):
    """What "persistent" has to mean for a printed sheet: re-rendering returns
    the same picture, not a second forever-credential nobody can count."""
    _primary(client)

    first = _secret_from(_qr(client, persistent=True).text)
    second = _secret_from(_qr(client, persistent=True).text)

    assert first == second


def test_the_ordinary_qr_is_still_short_lived(client: TestClient):
    """⚠️ Off by default. A permanent credential must never be what someone gets
    by pressing the button they have always pressed."""
    _primary(client)

    secret = _secret_from(_qr(client).text)

    # The guard's derivative shape: {token_id}.{nonce}.{issued}.{signature}.
    # A raw token secret from `secrets.token_urlsafe` never contains a dot.
    assert len(secret.split(".")) == 4


def test_a_persistent_qr_is_not_a_guard_derivative(client: TestClient):
    """The distinction the whole design rests on, asserted directly rather than
    inferred from behaviour."""
    _primary(client)

    secret = _secret_from(_qr(client, persistent=True).text)

    assert "." not in secret


# --------------------------------------------------------------------------- #
# What the page says
# --------------------------------------------------------------------------- #


def test_the_page_says_it_does_not_expire(client: TestClient):
    """⚠️ A persistent QR labelled with a countdown is how a credential leaks
    without anyone deciding to leak it. The page has to say which kind this is,
    where someone standing over a tablet will read it."""
    _primary(client)

    body = _qr(client, persistent=True).text

    assert "does not expire" in body
    assert "data-countdown=" not in body


def test_the_ordinary_page_still_counts_down(client: TestClient):
    _primary(client)

    body = _qr(client).text

    assert "data-countdown=" in body
    assert "does not expire" not in body


def test_the_checkbox_is_offered_and_unticked(client: TestClient):
    _primary(client)

    body = client.get("/enrollment", headers=ADMIN_HEADERS).text

    assert 'name="persistent"' in body
    assert "checked" not in body.split('name="persistent"')[1][:120]


# --------------------------------------------------------------------------- #
# Groups, and the case with no recoverable secret
# --------------------------------------------------------------------------- #


def test_a_persistent_group_qr_enrols_into_the_group(client: TestClient, db):
    """Persistent composes with a group rather than replacing it: the picture
    carries the group token's own secret, and enrolment is unchanged."""
    _primary(client)
    client.post(
        "/groups", data={"name": "Bench"}, headers=ADMIN_HEADERS, follow_redirects=False
    )
    group = db.scalar(select(DeviceGroup).where(DeviceGroup.name == "Bench"))

    secret = _secret_from(_qr(client, persistent=True, group_id=str(group.id)).text)
    enrolled = _enrol(client, secret, "PERSISTGRP").json()

    device = db.get(Device, uuid.UUID(enrolled["device_id"]))
    assert [g.name for g in device.groups] == ["Bench"]


def test_an_unrecoverable_secret_is_explained_not_rendered(client: TestClient, db):
    """⚠️ A token sealed before there was a vault cannot be recovered — by
    design, the hash is one-way. The operator gets told to make a new one rather
    than a page that half-renders or a QR built from nothing."""
    _primary(client)
    token = db.scalar(
        select(EnrollmentToken).where(EnrollmentToken.is_primary.is_(True))
    )
    token.token_ciphertext = None
    db.commit()

    body = _qr(client, persistent=True).text

    assert "cannot be recovered" in body
    assert "QR secret" not in body


# --------------------------------------------------------------------------- #
# Saving it as a file (W138)
# --------------------------------------------------------------------------- #


def _atlas_js() -> str:
    import pathlib

    return pathlib.Path("app/web/static/atlas.js").read_text(encoding="utf-8")


def test_a_permanent_qr_can_be_saved(client: TestClient):
    """The button and the thing it reads from have to arrive together — the
    handler looks up `[data-qr-image]` and does nothing at all without it."""
    _primary(client)

    body = _qr(client, persistent=True).text

    assert "data-save-qr=" in body
    assert "data-qr-image" in body


def test_a_short_lived_qr_offers_no_save(client: TestClient):
    """⚠️ Deliberately absent. A saved copy of a fifteen-minute code is a file
    that expires before anyone opens it, and offering to make one invites that
    confusion."""
    _primary(client)

    body = _qr(client).text

    assert "data-save-qr=" not in body


def test_the_filename_names_the_group(client: TestClient, db):
    """⚠️ Two printed sheets that look identical and enrol into different groups
    is the W121 hazard on paper. The filename is what tells them apart once the
    browser tab is closed."""
    _primary(client)
    client.post(
        "/groups", data={"name": "Bench Two"}, headers=ADMIN_HEADERS,
        follow_redirects=False,
    )
    group = db.scalar(select(DeviceGroup).where(DeviceGroup.name == "Bench Two"))

    body = _qr(client, persistent=True, group_id=str(group.id)).text

    assert 'data-save-qr="atlas-enrollment-qr-bench-two"' in body


def test_saving_falls_back_to_svg_when_the_canvas_refuses():
    """⚠️ Browsers disagree about whether drawing an SVG taints a canvas, and a
    Save button that silently does nothing is worse than one that hands over a
    less convenient file. Both failure paths — the draw throwing and the image
    never loading — have to reach the fallback."""
    js = _atlas_js()

    handler = js[js.index("data-save-qr") :]
    handler = handler[: handler.index("Unsaved-change guard")]

    assert handler.count("fallback()") >= 3
    assert "img.onerror" in handler


def test_the_saved_png_is_painted_on_white():
    """⚠️ The SVG has no background of its own. A transparent PNG is
    black-on-black wherever something assumes a dark ground — it would look
    perfect in the browser and refuse to scan off the page."""
    js = _atlas_js()

    handler = js[js.index("data-save-qr") :]
    handler = handler[: handler.index("Unsaved-change guard")]

    assert 'ctx.fillStyle = "#fff"' in handler
    assert handler.index("fillRect") < handler.index("drawImage")
