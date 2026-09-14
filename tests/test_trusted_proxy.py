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

"""The admin surface stops believing an identity header from anywhere (SEC_AUDIT S-1).

⚠️ **This is a network control and it is not the whole answer.** Caddy runs on the
host and reaches the container through the bridge gateway; so does every other
process on that host. The peer address cannot separate them, so this closes the
*accidental exposure* case — the port republished on `0.0.0.0` and reached from
somewhere else — and not host-local forgery. The finding stays open until the
proxy can prove it is the proxy, which needs InfraTAK's `X-Infratak-Proxy-Auth`
secret to be offered to module vhosts.

⚠️ **It also must not be able to lock an operator out.** The InfraTAK module
rewrites `.env` on deploy but not on update, so an unset value cannot mean
"refuse everything" — a release that did would take every existing box down on a
routine update. Unset means not enforced, said loudly at startup.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.config import Settings
from app.security import admin_auth
from tests.conftest import ADMIN_HEADERS


def _request(peer: str | None) -> Request:
    """A request whose ASGI scope carries the peer the transport saw."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "client": (peer, 44321) if peer else None,
    }
    return Request(scope)


def _settings(**over) -> Settings:
    base = {
        "admin_auth_mode": "forward_auth",
        "admin_group": "",
        "trusted_proxies": "",
    }
    base.update(over)
    return Settings(**base)


# --------------------------------------------------------------------------- #
# The peer check
# --------------------------------------------------------------------------- #


def test_the_bridge_gateway_is_accepted():
    """What Caddy actually looks like: measured as 172.24.0.1 on the dev host."""
    settings = _settings(trusted_proxies="172.24.0.0/16")

    assert admin_auth._peer_is_trusted(_request("172.24.0.1"), settings)


def test_an_address_outside_the_range_is_refused():
    settings = _settings(trusted_proxies="172.24.0.0/16")

    assert not admin_auth._peer_is_trusted(_request("203.0.113.7"), settings)
    assert not admin_auth._peer_is_trusted(_request("192.168.1.50"), settings)


def test_a_refused_peer_never_reaches_the_identity_headers():
    """⚠️ The order matters. Checking identity first and the peer second would
    still authenticate the caller, and a 403 that has already trusted a forged
    username is a 403 with the damage done."""
    settings = _settings(trusted_proxies="172.24.0.0/16")
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [
            (b"x-authentik-username", b"attacker"),
            (b"x-authentik-groups", b"takmdm-admins"),
        ],
        "client": ("203.0.113.7", 44321),
    }

    with pytest.raises(Exception) as raised:
        admin_auth.identify(Request(scope), settings)

    assert getattr(raised.value, "status_code", None) == 403


def test_a_single_address_works_as_well_as_a_range():
    settings = _settings(trusted_proxies="172.24.0.1")

    assert admin_auth._peer_is_trusted(_request("172.24.0.1"), settings)
    assert not admin_auth._peer_is_trusted(_request("172.24.0.2"), settings)


def test_several_entries_are_all_honoured():
    settings = _settings(trusted_proxies="127.0.0.1, 172.24.0.0/16")

    assert admin_auth._peer_is_trusted(_request("127.0.0.1"), settings)
    assert admin_auth._peer_is_trusted(_request("172.24.9.9"), settings)
    assert not admin_auth._peer_is_trusted(_request("10.1.1.1"), settings)


# --------------------------------------------------------------------------- #
# ⚠️ It must never be the thing that locks an operator out
# --------------------------------------------------------------------------- #


def test_unset_does_not_enforce():
    """The update path never rewrites `.env`, so unset has to keep working.

    ⚠️ Mutation-checking found this guard to be **redundant**: deleting the
    `not raw` test still passes, because an empty string parses to zero networks
    and the no-usable-entries guard returns True anyway. Recorded rather than
    removed — two independent reasons to not lock an operator out is the right
    number, and a reader who deletes one should know the other exists.
    """
    settings = _settings(trusted_proxies="")

    assert admin_auth._peer_is_trusted(_request("203.0.113.7"), settings)


def test_any_is_an_explicit_opt_out():
    settings = _settings(trusted_proxies="any")

    assert admin_auth._peer_is_trusted(_request("203.0.113.7"), settings)


def test_an_all_typo_configuration_does_not_lock_the_console(caplog):
    """⚠️ Every entry unparseable means the operator wrote something, and none of
    it is usable. Refusing everything would lock them out of the console over a
    typo; the warning is what tells them."""
    settings = _settings(trusted_proxies="172.24.0.999, not-an-ip")

    with caplog.at_level(logging.WARNING):
        assert admin_auth._peer_is_trusted(_request("203.0.113.7"), settings)

    assert "not an IP or CIDR" in caplog.text


def test_one_bad_entry_does_not_disable_the_good_ones(caplog):
    settings = _settings(trusted_proxies="172.24.0.0/16, not-an-ip")

    with caplog.at_level(logging.WARNING):
        assert admin_auth._peer_is_trusted(_request("172.24.0.1"), settings)
        assert not admin_auth._peer_is_trusted(_request("203.0.113.7"), settings)


def test_the_refusal_names_both_halves_of_the_comparison(caplog):
    """The recovery for a misconfiguration is reading this line."""
    settings = _settings(trusted_proxies="172.24.0.0/16")
    scope = {
        "type": "http", "method": "GET", "path": "/",
        "headers": [(b"x-authentik-username", b"someone")],
        "client": ("10.9.9.9", 1234),
    }

    with caplog.at_level(logging.ERROR):
        with pytest.raises(Exception):
            admin_auth.identify(Request(scope), settings)

    assert "10.9.9.9" in caplog.text
    assert "172.24.0.0/16" in caplog.text
    assert "'any'" in caplog.text, "the log must say how to switch it off"


def test_disabled_auth_is_unaffected():
    """Local development binds to loopback and has no proxy at all."""
    settings = _settings(admin_auth_mode="disabled", trusted_proxies="172.24.0.0/16")

    identity = admin_auth.identify(_request("203.0.113.7"), settings)

    assert identity.is_anonymous


def test_the_startup_warning_names_the_setting(caplog):
    with caplog.at_level(logging.WARNING):
        admin_auth.warn_if_unprotected(_settings(trusted_proxies=""))

    assert "TAKMDM_TRUSTED_PROXIES" in caplog.text


def test_an_explicit_opt_out_still_says_so(caplog):
    with caplog.at_level(logging.WARNING):
        admin_auth.warn_if_unprotected(_settings(trusted_proxies="any"))

    assert "deliberately off" in caplog.text


# --------------------------------------------------------------------------- #
# ⚠️ The peer has to be the real peer
# --------------------------------------------------------------------------- #


def test_the_image_does_not_let_uvicorn_rewrite_the_peer():
    """⚠️ Without `--no-proxy-headers` uvicorn overwrites the ASGI `client` from
    `X-Forwarded-For`, which would let a forged header choose the address this
    check is made against — defeating the control with the very class of header
    it exists to defend against."""
    import io

    lines = io.open("Dockerfile", encoding="utf-8").read().splitlines()
    # ⚠️ The CMD line itself, not the file. Asserting the flag appears *anywhere*
    # passed happily when it was deleted from the command and left in the comment
    # that explains it — the mutation check caught that, the first version of this
    # test did not.
    cmd = [line for line in lines if line.startswith("CMD ")]
    assert len(cmd) == 1, cmd
    assert "--no-proxy-headers" in cmd[0], cmd[0]

    assert any("X-Forwarded-For" in line for line in lines), (
        "the reason belongs next to the flag"
    )


def test_nothing_reads_a_forwarded_address():
    """The flag above is safe only while this stays true.

    ⚠️ Matched on a *read* — the header name alongside a header lookup — not on
    the bare string. Prose naming `X-Forwarded-For` to explain why it is not
    trusted is the opposite of the problem, and a scan that flags its own
    reasoning gets deleted by the next person rather than fixed.
    """
    import pathlib
    import re

    read = re.compile(r"headers[^\n]*forwarded|forwarded[^\n]*headers", re.I)
    offenders = []
    for path in pathlib.Path("app").rglob("*.py"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or "`" in line:
                continue
            if read.search(line):
                offenders.append(f"{path}:{number}: {stripped}")

    assert not offenders, offenders


# --------------------------------------------------------------------------- #
# The console still works
# --------------------------------------------------------------------------- #


def test_the_console_is_unaffected_when_not_enforcing(client: TestClient):
    """The suite runs with auth disabled; this is the regression guard that the
    check has not broken ordinary rendering."""
    assert client.get("/admin", headers=ADMIN_HEADERS).status_code == 200
