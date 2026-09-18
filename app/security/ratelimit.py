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

"""Bounding how fast one caller can make this server work.

`SEC_AUDIT.md` **M-8**. The audit is right about which risk this is and is not:
credential brute force is already answered (enrollment secrets are
`secrets.token_urlsafe(32)`, comparisons use `hmac.compare_digest`, and the
bypass PIN has an attempt counter). What nothing bounded was how much work one
caller could ask for.

## Keyed on identity, never on the address

⚠️ **Per-IP limiting would take the whole fleet down.** It is the reflex, and in
a tactical deployment several hundred tablets sit behind one Wi-Fi uplink and
therefore one NAT address. The first time a per-IP limit on the device endpoints
actually fired, it would throttle every device at once — and it would present as
a server fault rather than as a limiter doing its job.

⚠️ **And this application cannot see the client address anyway.** The image runs
uvicorn with `--no-proxy-headers` on purpose (`SEC_AUDIT.md` S-1: uvicorn would
otherwise rewrite `request.client` from a header anyone can forge). So
`request.client.host` is the reverse proxy on every single request, and keying on
it would put the entire internet in one bucket.

So the rule here is: **key on an identity, and where there is none, do not
pretend to have one.** A limiter that cannot tell two callers apart must not act
as though it can — refusing the innocent is not a safe default when the innocent
is the fleet.

## Correct only in a single-process server

The state is a dict in this process. `Dockerfile` runs one uvicorn worker and
`tests/test_ratelimit.py` pins that, because `--workers 4` would silently turn
every limit below into four times itself — a change that breaks nothing, fails
no test, and quietly removes most of the control.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

#: Stop tracking a caller that has been idle for this long.
#:
#: Without it the dict grows once per distinct key for the life of the process,
#: which for enrollment tokens means once per garbage token an attacker invents —
#: a rate limiter that is itself a memory exhaustion bug.
IDLE_SECONDS = 900.0

#: How many keys may be tracked before idle ones are swept.
#:
#: Swept on write rather than on a timer: there is no background task here, and a
#: limiter that needs one is a limiter that stops working when the task dies.
SWEEP_AT = 4096

#: What the table is cut back to when sweeping idle keys is not enough.
#:
#: ⚠️ Sweeping alone does not guarantee progress. If every tracked caller is
#: recent, an idle sweep frees nothing and the table grows for ever — a rate
#: limiter that is itself the memory exhaustion bug it was written to prevent.
#: The keys in use here are device ids and enrollment token ids, both bounded by
#: real records, so this is a backstop rather than the primary bound.
KEEP = 3072


@dataclass(frozen=True)
class Limit:
    """A sustained rate and the burst allowed on top of it.

    `burst` is the bucket's capacity: a caller that has been quiet may spend that
    many requests at once, then settles to `per_minute`. Bursts are the normal
    shape of this traffic — a device that has been parked on a long poll answers
    a doorbell with several requests in a second — so a limiter with no burst
    allowance would fire during ordinary operation.
    """

    per_minute: float
    burst: int

    @property
    def per_second(self) -> float:
        return self.per_minute / 60.0


#: What a single enrolled device may ask for.
#:
#: A device checks in every 5 minutes and holds one long poll. 300/minute is
#: roughly 300x that, and the headroom is not laziness: ⚠️ an administrator making
#: a run of policy changes rings the doorbell once per change, and the device
#: answers each ring with a check-in. The ceiling has to clear a burst of
#: doorbell-driven re-polls, not just the steady state, or bulk editing looks
#: like a broken fleet.
DEVICE = Limit(per_minute=300, burst=60)

#: What one enrollment token may enrol.
#:
#: ⚠️ Sized for a provisioning bench, which is the case that looks like abuse: a
#: permanent token is *designed* to be shared across many tablets set up together
#: (`SEC_AUDIT.md` M-7). Twenty devices enrolling in the same minute is a normal
#: morning; 60 is not.
ENROLLMENT = Limit(per_minute=60, burst=20)

# ⚠️ There is deliberately no limit for the bypass PIN, and it was written and
# then removed rather than never considered. Six digits looks like the obvious
# guessing oracle here — but `bypass_pin.verify` already caps it at MAX_ATTEMPTS
# guesses per token for the token's whole life, which is strictly stronger than
# any per-minute rate. The limit fired *before* that counter could, turning the
# `attempts_remaining: 0` the setup wizard shows an operator into a 429 it does
# not understand. A control that pre-empts a better control is a regression.


class RateLimited(Exception):
    """This caller has asked for more than its share. `retry_after` is seconds."""

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"rate limit exceeded; retry in {retry_after:.0f}s")
        self.retry_after = max(1, int(retry_after + 0.999))


class _Bucket:
    __slots__ = ("tokens", "touched")

    def __init__(self, tokens: float, touched: float) -> None:
        self.tokens = tokens
        self.touched = touched


class RateLimiter:
    """Token buckets keyed by caller identity.

    Instances are cheap; the module-level `limiter` is the one the application
    uses, and tests build their own so they never share state with each other.
    """

    def __init__(self, *, clock=time.monotonic) -> None:
        self._buckets: dict[tuple[str, str], _Bucket] = {}
        self._lock = threading.Lock()
        self._clock = clock

    def check(self, scope: str, key: str, limit: Limit) -> None:
        """Spend one request, or raise `RateLimited`.

        `scope` separates the counters, so a device's check-ins and its log
        uploads are not competing for the same allowance if they are ever limited
        separately. `key` is the caller — a device id, a token hash.
        """
        now = self._clock()
        with self._lock:
            if len(self._buckets) >= SWEEP_AT:
                self._sweep(now)

            bucket = self._buckets.get((scope, key))
            if bucket is None:
                bucket = _Bucket(tokens=float(limit.burst), touched=now)
                self._buckets[(scope, key)] = bucket
            else:
                elapsed = max(0.0, now - bucket.touched)
                bucket.tokens = min(
                    float(limit.burst), bucket.tokens + elapsed * limit.per_second
                )
                bucket.touched = now

            if bucket.tokens < 1.0:
                # ⚠️ The clock is *not* advanced past this point and no token is
                # taken. A refused request must not push the caller further from
                # recovery, or a client that retries hard can never get back in.
                needed = 1.0 - bucket.tokens
                raise RateLimited(needed / limit.per_second)

            bucket.tokens -= 1.0

    def _sweep(self, now: float) -> None:
        """Make room, and guarantee that it did. Called with the lock held.

        ⚠️ Eviction hands the evicted caller a fresh bucket, which is a full
        allowance. That is why it is the second step and not the first: anything
        that can be dropped for being *idle* has nothing left to bypass, while a
        busy caller evicted under pressure gets its limit reset. The keys here are
        device ids and token ids, so filling the table means creating thousands of
        real records — which is not a path an attacker has.
        """
        stale = [
            identity
            for identity, bucket in self._buckets.items()
            if now - bucket.touched > IDLE_SECONDS
        ]
        for identity in stale:
            del self._buckets[identity]

        if len(self._buckets) <= KEEP:
            return

        oldest = sorted(self._buckets.items(), key=lambda item: item[1].touched)
        for identity, _ in oldest[: len(self._buckets) - KEEP]:
            del self._buckets[identity]

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()

    @property
    def tracked(self) -> int:
        with self._lock:
            return len(self._buckets)


#: The application's limiter.
limiter = RateLimiter()
