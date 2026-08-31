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

"""Change bus for live propagation (F3).

A device parks on a long-poll; the moment its state is invalidated or a command is
queued for it, the request is released and it checks in. Typical latency is
milliseconds instead of up to a check-in interval.

This is a **doorbell, not a channel**. It carries no payload and guarantees no
delivery — a device that missed a wake still converges on its next poll. D7 stands:
polling is the correctness floor, and it has to be, for a fleet that goes dark for
days. Making the doorbell authoritative would trade a working offline story for a
faster online one.

Waking is wired to SQLAlchemy's ``after_commit``, so a write path physically cannot
forget to ring it, and can never ring it before the data it describes is durable.

**Scope limit:** waiters live in this process. One uvicorn worker serves the whole
fleet correctly; running several would need the notification fanned out through
Redis or Postgres ``LISTEN/NOTIFY``. At 50-500 devices a single process is ample,
and long-poll waiters are cheap because they are asyncio tasks, not threads.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections import defaultdict

from sqlalchemy import event
from sqlalchemy.orm import Session

_SESSION_KEY = "takmdm_wake_devices"


class ChangeBus:
    """Releases long-poll waiters for specific devices."""

    def __init__(self) -> None:
        self._waiters: dict[uuid.UUID, set[asyncio.Event]] = defaultdict(set)
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Record the serving loop. Notifications arrive from worker threads."""
        self._loop = loop

    def waiter_count(self, device_id: uuid.UUID) -> int:
        with self._lock:
            return len(self._waiters.get(device_id, ()))

    def notify(self, device_ids: set[uuid.UUID]) -> None:
        """Wake every waiter for these devices. Safe to call from any thread."""
        if not device_ids:
            return
        with self._lock:
            events = [
                event_
                for device_id in device_ids
                for event_ in self._waiters.get(device_id, ())
            ]
        if not events:
            return

        loop = self._loop
        if loop is None:
            return  # no server running (unit tests touching services directly)

        for event_ in events:
            # asyncio.Event is not thread-safe and request handlers run in a
            # threadpool, so hop back onto the serving loop to set it.
            loop.call_soon_threadsafe(event_.set)

    async def wait(self, device_id: uuid.UUID, timeout: float) -> bool:
        """Park until this device is notified. True if woken, False on timeout."""
        event_ = asyncio.Event()
        with self._lock:
            self._waiters[device_id].add(event_)
        try:
            await asyncio.wait_for(event_.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            with self._lock:
                waiters = self._waiters.get(device_id)
                if waiters is not None:
                    waiters.discard(event_)
                    if not waiters:
                        del self._waiters[device_id]


bus = ChangeBus()


def schedule_wake(session: Session, device_ids: set[uuid.UUID]) -> None:
    """Queue devices to be woken once this session's transaction commits."""
    if not device_ids:
        return
    session.info.setdefault(_SESSION_KEY, set()).update(device_ids)


@event.listens_for(Session, "after_commit")
def _wake_after_commit(session: Session) -> None:
    """Ring the doorbell only for data that is actually durable."""
    device_ids = session.info.pop(_SESSION_KEY, None)
    if device_ids:
        bus.notify(device_ids)


@event.listens_for(Session, "after_rollback")
def _discard_on_rollback(session: Session) -> None:
    session.info.pop(_SESSION_KEY, None)
