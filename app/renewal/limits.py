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

"""How many tokens the renewal container makes (W458).

A ceiling on the whole box and one per user, over a sliding hour. A real fleet
renews a handful of certificates a day; anything near these numbers is a fault
or an attack, and stopping it costs one user a retry at the next check-in.

⚠️ The lockout on an InfraTAK box counts failures per username (reputation
policy `infratak-brute-force`, `check_username=True`, threshold -5), so the
per-user ceiling also keeps a looping device from locking its own user out.
"""

from __future__ import annotations

import time
from collections import deque

PER_HOUR = 120
PER_USER_PER_HOUR = 3
WINDOW_SECONDS = 3600


class Limited(Exception):
    """Too many tokens. The text is safe to show."""


class RateLimiter:
    def __init__(self, per_hour: int = PER_HOUR, per_user: int = PER_USER_PER_HOUR,
                 clock=time.time) -> None:
        self._per_hour = per_hour
        self._per_user = per_user
        self._clock = clock
        self._events: deque[tuple[float, str]] = deque()

    def take(self, username: str) -> None:
        now = self._clock()
        while self._events and now - self._events[0][0] > WINDOW_SECONDS:
            self._events.popleft()
        if len(self._events) >= self._per_hour:
            raise Limited("renewal limit reached (%d an hour)" % self._per_hour)
        if sum(1 for _, user in self._events if user == username) >= self._per_user:
            raise Limited("renewal limit reached for this user (%d an hour)" % self._per_user)
        self._events.append((now, username))
