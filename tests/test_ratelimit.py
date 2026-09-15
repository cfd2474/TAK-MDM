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

"""`SEC_AUDIT.md` M-8 — rate limiting, keyed on something that is not the address.

⚠️ **The tests that matter most here are the ones asserting a limit does *not*
fire.** Getting this wrong does not leave a hole; it takes the fleet off the air.
Two specific ways:

* **Per-address keying.** Several hundred tablets sit behind one NAT address in a
  real deployment, so an address-keyed limit throttles all of them together. The
  application cannot even see the address — it runs with `--no-proxy-headers` —
  so keying on `request.client` would put the entire world in one bucket.
* **Pre-empting a better control.** A bypass-PIN rate limit was written and then
  removed: `bypass_pin.verify` already caps guessing at `MAX_ATTEMPTS` for the
  token's whole life, and the rate limit fired first, replacing the
  `attempts_remaining` a setup wizard shows with a 429 it does not understand.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.security import ratelimit


class FakeClock:
    """Time under the test's control — a limiter tested against the real clock
    is a limiter tested by sleeping."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def limiter(clock) -> ratelimit.RateLimiter:
    return ratelimit.RateLimiter(clock=clock)


SMALL = ratelimit.Limit(per_minute=60, burst=3)


# --------------------------------------------------------------------------- #
# The bucket
# --------------------------------------------------------------------------- #


def test_a_burst_is_allowed_then_refused(limiter):
    for _ in range(SMALL.burst):
        limiter.check("s", "caller", SMALL)

    with pytest.raises(ratelimit.RateLimited):
        limiter.check("s", "caller", SMALL)


def test_the_allowance_comes_back_over_time(limiter, clock):
    for _ in range(SMALL.burst):
        limiter.check("s", "caller", SMALL)

    clock.advance(1.0)  # 60/minute is one per second
    limiter.check("s", "caller", SMALL)

    with pytest.raises(ratelimit.RateLimited):
        limiter.check("s", "caller", SMALL)


def test_a_refusal_does_not_push_the_caller_further_away(limiter, clock):
    """⚠️ A refused request must not spend anything.

    Otherwise a client that retries hard — which is exactly what a client does
    when it starts getting errors — can never recover, and a momentary burst
    becomes a permanent outage for that device.
    """
    for _ in range(SMALL.burst):
        limiter.check("s", "caller", SMALL)
    for _ in range(50):
        with pytest.raises(ratelimit.RateLimited):
            limiter.check("s", "caller", SMALL)

    clock.advance(1.0)
    limiter.check("s", "caller", SMALL)


def test_a_long_quiet_period_does_not_bank_requests(limiter, clock):
    """⚠️ The bucket refills to `burst` and stops.

    Without the cap, a device that was switched off overnight comes back holding
    hours of accumulated allowance — which is exactly the caller you least want
    to hand a free run at the server, and the limit would look correct in every
    other test.
    """
    limiter.check("s", "caller", SMALL)
    clock.advance(3600)

    for _ in range(SMALL.burst):
        limiter.check("s", "caller", SMALL)

    with pytest.raises(ratelimit.RateLimited):
        limiter.check("s", "caller", SMALL)


def test_the_refusal_says_how_long_to_wait(limiter):
    for _ in range(SMALL.burst):
        limiter.check("s", "caller", SMALL)

    with pytest.raises(ratelimit.RateLimited) as raised:
        limiter.check("s", "caller", SMALL)

    assert raised.value.retry_after >= 1


def test_one_caller_does_not_spend_another_s_allowance(limiter):
    """The property the whole design rests on."""
    for _ in range(SMALL.burst):
        limiter.check("s", "first", SMALL)
    with pytest.raises(ratelimit.RateLimited):
        limiter.check("s", "first", SMALL)

    limiter.check("s", "second", SMALL)


def test_scopes_are_separate(limiter):
    for _ in range(SMALL.burst):
        limiter.check("one", "caller", SMALL)

    limiter.check("two", "caller", SMALL)


# --------------------------------------------------------------------------- #
# The limiter must not become the bug it prevents
# --------------------------------------------------------------------------- #


def test_idle_callers_are_forgotten(limiter, clock):
    for index in range(ratelimit.SWEEP_AT):
        limiter.check("s", f"caller-{index}", SMALL)

    clock.advance(ratelimit.IDLE_SECONDS + 1)
    limiter.check("s", "someone-new", SMALL)

    assert limiter.tracked == 1


def test_the_table_is_bounded_even_when_nothing_is_idle(limiter):
    """⚠️ Sweeping idle keys alone does not guarantee progress.

    If every tracked caller is recent the sweep frees nothing, and the table
    grows without limit — a rate limiter that is itself the memory exhaustion bug
    it exists to prevent.
    """
    for index in range(ratelimit.SWEEP_AT + 500):
        limiter.check("s", f"caller-{index}", SMALL)

    assert limiter.tracked <= ratelimit.SWEEP_AT


# --------------------------------------------------------------------------- #
# The sizes, argued against real traffic rather than picked
# --------------------------------------------------------------------------- #


def test_a_device_may_answer_a_run_of_doorbell_rings():
    """⚠️ An administrator making a run of policy changes rings the long-poll
    once per change, and each ring produces a check-in. The ceiling has to clear
    a burst of those, not just the 5-minute steady state — otherwise bulk editing
    looks like a broken fleet."""
    assert ratelimit.DEVICE.burst >= 50
    # A device at its steady state uses about 12 requests an hour.
    assert ratelimit.DEVICE.per_minute >= 120


def test_one_token_may_provision_a_bench():
    """⚠️ A permanent token is *designed* to be shared across many tablets set up
    together (M-7), so the case that looks most like abuse is a normal morning."""
    assert ratelimit.ENROLLMENT.burst >= 20


def test_nothing_is_limited_more_tightly_than_the_bypass_pin_counter():
    """The control that was removed, pinned as an absence.

    `bypass_pin.MAX_ATTEMPTS` guesses per token for the token's whole life is
    strictly stronger than any per-minute rate, and a rate limit on top fired
    first and turned a readable answer into a 429.
    """
    assert not hasattr(ratelimit, "BYPASS_PIN")


# --------------------------------------------------------------------------- #
# Through the application
# --------------------------------------------------------------------------- #


@pytest.fixture
def tight(monkeypatch):
    """A device ceiling small enough to reach without 300 requests."""
    monkeypatch.setattr(ratelimit, "DEVICE", ratelimit.Limit(per_minute=60, burst=2))


def _checkin(client: TestClient, device: dict):
    """⚠️ Check-in, not the long poll.

    The long poll holds the request open for its whole timeout, and the bucket
    refills while it is parked — so three sequential five-second polls never
    reach a 60-per-minute ceiling no matter how small the burst. Correct
    behaviour, useless as a test.
    """
    return client.post(
        "/api/v1/device/checkin",
        json={},
        headers={"x-ssl-client-cert": device["certificate_pem"]},
    )


def test_a_device_over_its_ceiling_is_refused_with_retry_after(
    client: TestClient, enrolled, tight
):
    device = enrolled(serial="RL-ONE")

    seen = [_checkin(client, device).status_code for _ in range(3)]

    assert seen == [200, 200, 429], seen
    assert _checkin(client, device).headers.get("Retry-After")


def test_one_noisy_device_does_not_silence_its_neighbours(
    client: TestClient, enrolled, tight
):
    """⚠️ The property an address-keyed limiter would destroy. Both devices are
    the same client from the same address; only the certificate tells them
    apart."""
    noisy = enrolled(serial="RL-NOISY")
    quiet = enrolled(serial="RL-QUIET")

    for _ in range(4):
        _checkin(client, noisy)

    assert _checkin(client, quiet).status_code == 200


@pytest.fixture
def tight_enrolment(monkeypatch):
    monkeypatch.setattr(
        ratelimit, "ENROLLMENT", ratelimit.Limit(per_minute=60, burst=2)
    )


def _enroll(client: TestClient, secret: str, serial: str):
    from tests.conftest import generate_csr

    return client.post(
        "/api/v1/enroll",
        json={"token": secret, "csr_pem": generate_csr(), "serial_number": serial},
    )


def test_one_token_over_its_ceiling_is_refused(client: TestClient, tight_enrolment):
    from tests.conftest import ADMIN_HEADERS

    created = client.post(
        "/api/v1/enrollment-tokens",
        json={"name": "bench", "group_ids": []},
        headers=ADMIN_HEADERS,
    )
    secret = created.json()["secret"]

    seen = [_enroll(client, secret, f"RL-BENCH-{i}").status_code for i in range(3)]

    assert seen[:2] == [201, 201], seen
    assert seen[2] == 429, seen


def test_every_qr_derived_secret_shares_its_primary_s_allowance(
    client: TestClient, tight_enrolment
):
    """⚠️ The reason the key is the resolved token and not the string presented.

    A QR-derived secret is a **fresh string on every issue** (Chunk 14) while
    resolving to the same primary token. Keying on the string would hand each QR
    its own allowance — defeating the limit for precisely the flow it exists to
    bound, and looking correct in every test that reuses one secret.
    """
    from tests.conftest import ADMIN_HEADERS

    created = client.post(
        "/api/v1/enrollment-tokens/primary",
        json={"name": "Fleet enrollment"},
        headers=ADMIN_HEADERS,
    )
    assert created.status_code == 200, created.text

    secrets = []
    for _ in range(3):
        issued = client.post(
            "/api/v1/enrollment-tokens/primary/qr", json={}, headers=ADMIN_HEADERS
        )
        assert issued.status_code == 200, issued.text
        secrets.append(issued.json()["secret"])

    assert len(set(secrets)) == 3, "the QR secrets are not distinct; this proves nothing"

    seen = [_enroll(client, s, f"RL-QR-{i}").status_code for i, s in enumerate(secrets)]

    assert seen[2] == 429, seen


def test_a_garbage_token_never_earns_a_bucket(client: TestClient):
    """⚠️ Keying enrolment on the presented *string* would let an attacker mint a
    fresh allowance per request by inventing secrets — an unlimited limiter, and
    an unbounded table of them. The key is the token that resolved."""
    from tests.conftest import generate_csr

    before = ratelimit.limiter.tracked
    for index in range(5):
        response = client.post(
            "/api/v1/enroll",
            json={
                "token": f"not-a-real-token-{index}",
                "csr_pem": generate_csr(),
                "serial_number": f"RL-GARBAGE-{index}",
            },
        )
        assert response.status_code == 401, response.text

    assert ratelimit.limiter.tracked == before


# --------------------------------------------------------------------------- #
# What the limits silently depend on
# --------------------------------------------------------------------------- #


def test_the_image_runs_one_worker():
    """⚠️ The buckets are a dict in one process.

    `--workers 4` multiplies every limit above by four. Nothing would fail, no
    test would go red, and most of the control would quietly be gone — which is
    why the absence is asserted rather than assumed.
    """
    dockerfile = io.open("Dockerfile", encoding="utf-8").read()
    cmd = [line for line in dockerfile.splitlines() if line.strip().startswith("CMD")]

    assert cmd, "the Dockerfile has no CMD"
    assert "--workers" not in cmd[0], cmd[0]
    assert "uvicorn" in cmd[0], cmd[0]


def test_the_standalone_proxy_limits_the_unauthenticated_endpoints():
    """The volumetric half, which only the standalone deployment has.

    ⚠️ The InfraTAK deployment fronts :8449 with Caddy straight to the
    application, so this proxy is not in that path and Caddy's standard build has
    no rate limiting. Asserted here so the protection is not assumed to be
    everywhere — see the comment in nginx.conf.
    """
    conf = io.open("docker/nginx/nginx.conf", encoding="utf-8").read()

    assert re.search(r"limit_req_zone\s+\$binary_remote_addr", conf), conf[:200]
    for path in ("/api/v1/enroll", "/api/v1/provisioning/bypass-pin"):
        block = re.search(
            r"location = " + re.escape(path) + r" \{(.*?)\n        \}", conf, re.S
        )
        assert block, f"no location block for {path}"
        assert "limit_req " in block.group(1), path


def test_the_provisioning_download_is_left_alone():
    """⚠️ The obvious candidate, and the worst place to be wrong.

    A throttled APK download fails inside Android's setup wizard, which reports
    "something went wrong" and nothing else — the device is then a brick until
    somebody factory resets it and guesses why.
    """
    conf = io.open("docker/nginx/nginx.conf", encoding="utf-8").read()
    # ⚠️ Every block, not the first. The APK is served from two listeners — the
    # TLS one and the plaintext one the setup wizard uses — and checking only the
    # first let a `limit_req` on the other through a mutation sweep.
    blocks = re.findall(
        r"location = /api/v1/provisioning/agent\.apk \{(.*?)\n        \}", conf, re.S
    )

    assert len(blocks) == 2, f"expected two agent.apk locations, found {len(blocks)}"
    for block in blocks:
        assert "limit_req" not in block, block
