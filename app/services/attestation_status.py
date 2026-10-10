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

"""Google's attestation revocation list, fetched and cached (W323 chunk 3).

📖 `https://android.googleapis.com/attestation/status`: ``{"entries": {serial:
{"status": "REVOKED" | "SUSPENDED", "reason": ...}}}``, the serial in lowercase
hex (schema on developer.android.com's key-attestation page). A listed key is
untrusted whichever status it has.

⚠️ **Unavailable is not "nothing revoked" (W323 D-i).** :func:`revoked_serials`
returns None when the list has never been fetched, or the last good copy is more
than a week old. The integrity rule then reads "not reported": it never passes
a device on a list it couldn't check, and never fails one for the box being
offline.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

URL = "https://android.googleapis.com/attestation/status"

#: Refetch after this long. Google's own guidance is to refresh at least daily.
REFRESH_AFTER = timedelta(hours=24)
#: Stop trusting the last good copy after this long without a refresh.
USABLE_FOR = timedelta(days=7)

_lock = threading.Lock()
_cache: dict = {"serials": None, "fetched_at": None, "tried_at": None}


def _fetch() -> set[str]:
    import httpx

    from app.security import outbound

    with httpx.Client(timeout=10) as client:
        response = outbound.fetch(client, URL)
    response.raise_for_status()
    entries = (response.json() or {}).get("entries") or {}
    # ⚠️ Every entry, not only REVOKED: the schema's only other status is
    # SUSPENDED, and a key Google has suspended mustn't vouch for a device either.
    return {str(serial).lower() for serial in entries}


def revoked_serials(now: datetime | None = None) -> set[str] | None:
    """Revoked serials in lowercase hex, or None if no usable copy exists.

    Fetches at most once per hour when a refresh fails, so a box without
    internet doesn't stall every check-in on a timeout.
    """
    now = now or datetime.now(timezone.utc)
    with _lock:
        fetched, tried = _cache["fetched_at"], _cache["tried_at"]
        due = fetched is None or now - fetched >= REFRESH_AFTER
        if due and (tried is None or now - tried >= timedelta(hours=1)):
            _cache["tried_at"] = now
            try:
                _cache["serials"], _cache["fetched_at"] = _fetch(), now
            except Exception as exc:  # noqa: BLE001 - offline must not break check-ins
                log.warning("attestation revocation list unavailable: %s", exc)
        fetched = _cache["fetched_at"]
        if fetched is None or now - fetched >= USABLE_FOR:
            return None
        return set(_cache["serials"] or ())


def _reset_for_tests(serials: set[str] | None = None, fetched_at: datetime | None = None) -> None:
    with _lock:
        _cache.update(serials=serials, fetched_at=fetched_at,
                      tried_at=fetched_at)
