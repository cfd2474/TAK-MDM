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

"""The dashboard's status tiles: ATLAS's own health, one judgement each (W440).

The sample the operator pointed at shows its host's services (tomcat,
nginx, docker). ATLAS's container cannot see Docker and should not, so its
tiles are what ATLAS itself can vouch for.

⚠️ **A tile that cannot be read says so.** `UNKNOWN`, never `OK` by default:
a green tile that only means "we did not look" is the failure a status page
exists to prevent. And a link nobody set up is `OFF` (neutral), not a fault:
an instance that never linked Google Play is not broken.
"""

from __future__ import annotations

import socket
import ssl
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit

from cryptography import x509
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AlertOccurrence,
    Device,
    EnrollmentState,
    GooglePlayLink,
    GooglePlayLinkStatus,
    TakGovLink,
    TakGovLinkStatus,
)
from app.services import clock, device_cert_status, device_health

OK, WARN, BAD, OFF, UNKNOWN = "ok", "warn", "bad", "off", "unknown"

#: A certificate this close to expiry is amber.
CERT_WARN_DAYS = 30
#: How long a probe of the public certificate is trusted. It changes on renewal,
#: every 60-90 days; a minute's refresh must not open a TLS connection each time.
PROBE_CACHE_SECONDS = 3600.0
PROBE_TIMEOUT_SECONDS = 3.0


@dataclass(frozen=True)
class Tile:
    key: str
    label: str
    value: str
    level: str
    #: One line of why, for the tooltip and the screen reader.
    detail: str = ""


def _cert_tile(key: str, label: str, expires: datetime | None, now: datetime, unknown: str,
               tz=timezone.utc) -> Tile:
    if expires is None:
        return Tile(key, label, "Unknown", UNKNOWN, unknown)
    days = (expires - now).days
    # The date in the console's zone: a certificate expiring at 01:00 UTC
    # expires the evening before on an American console.
    when = clock.format(expires, tz, "%Y-%m-%d")
    if expires <= now:
        return Tile(key, label, "Expired", BAD, f"Expired {when}")
    level = WARN if days < CERT_WARN_DAYS else OK
    value = "1 day left" if days == 1 else f"{days} days left"
    return Tile(key, label, value, level, f"Expires {when}")


def _count_tile(key: str, label: str, count: int, none: str, some: str) -> Tile:
    if count == 0:
        return Tile(key, label, "None", OK, none)
    return Tile(key, label, str(count), WARN, some)


def database(database_bytes: int | None, format_bytes: Callable[[int], str]) -> Tile:
    """Up: this request read from it. The size where the database can say."""
    value = "Up" if database_bytes is None else f"Up · {format_bytes(database_bytes)}"
    return Tile("database", "Database", value, OK, "Answering queries")


def device_ca(expires: datetime | None, now: datetime, tz=timezone.utc) -> Tile:
    return _cert_tile(
        "device_ca", "Device CA", expires, now, "The device CA certificate could not be read", tz
    )


def https_certificate(expires: datetime | None, now: datetime, tz=timezone.utc) -> Tile:
    return _cert_tile(
        "https", "HTTPS certificate", expires, now,
        "ATLAS could not reach its own address to read the certificate", tz,
    )


def google_play(status: GooglePlayLinkStatus | None) -> Tile:
    if status is GooglePlayLinkStatus.LINKED:
        return Tile("google_play", "Google Play", "Linked", OK, "Account linked")
    if status is GooglePlayLinkStatus.BROKEN:
        return Tile("google_play", "Google Play", "Broken", BAD, "The linked account stopped working: link it again")
    if status is GooglePlayLinkStatus.UNLINKED:
        return Tile("google_play", "Google Play", "Not linked", OFF, "No Google account is linked")
    return Tile("google_play", "Google Play", "Unknown", UNKNOWN, "The link could not be read")


def tak_gov(status: TakGovLinkStatus | None) -> Tile:
    if status is TakGovLinkStatus.LINKED:
        return Tile("tak_gov", "TAK.gov", "Linked", OK, "Account linked")
    if status is TakGovLinkStatus.BROKEN:
        return Tile("tak_gov", "TAK.gov", "Broken", BAD, "The link stopped working: enter a new code")
    if status is TakGovLinkStatus.PENDING:
        return Tile("tak_gov", "TAK.gov", "Waiting for code", WARN, "A code was issued and not yet entered at tak.gov")
    if status is TakGovLinkStatus.UNLINKED:
        return Tile("tak_gov", "TAK.gov", "Not linked", OFF, "No TAK.gov account is linked")
    return Tile("tak_gov", "TAK.gov", "Unknown", UNKNOWN, "The link could not be read")


def open_alerts(count: int) -> Tile:
    return _count_tile(
        "alerts", "Open alerts", count, "No alert condition holds",
        "Alert conditions still holding (Admin › General › Alerts)",
    )


def expired_certificates(count: int) -> Tile:
    return _count_tile(
        "expired_certs", "Expired device certificates", count, "Every device certificate is valid",
        "These devices cannot check in until reinstated",
    )


def stalled_enrollments(count: int) -> Tile:
    return _count_tile(
        "stalled", "Stalled enrollments", count, "Every enrolled device has checked in",
        "Enrolled, then never checked in",
    )


# --------------------------------------------------------------------------- #
# Reading the facts
# --------------------------------------------------------------------------- #


def count_open_alerts(session: Session) -> int:
    """Conditions still holding. An event is cleared as it is written."""
    return int(session.scalar(
        select(func.count()).select_from(AlertOccurrence).where(AlertOccurrence.cleared_at.is_(None))
    ) or 0)


def count_stalled(session: Session, now: datetime) -> int:
    devices = session.scalars(select(Device).where(Device.enrollment_state == EnrollmentState.ENROLLED))
    return sum(1 for d in devices if device_health.enrollment_stalled(d, now=now))


def _safely(read: Callable[[], object]):
    try:
        return read()
    except Exception:
        return None


def link_status(session: Session, model, unlinked):
    """A link's status without creating its row, as `google_play_link.get` would:
    a page that only looks must not write. No row is a link never made."""
    link = session.get(model, 1)
    return unlinked if link is None else link.status


def probe_certificate_expiry(url: str, timeout: float = PROBE_TIMEOUT_SECONDS) -> datetime | None:
    """The notAfter of the certificate `url` serves, or None if it cannot be had.

    ⚠️ Unverified on purpose: this reads a date, it trusts nothing. A
    self-signed or misconfigured certificate still has an expiry worth
    showing, and verification failing is not the question being asked.
    """
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        return None
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((parts.hostname, parts.port or 443), timeout=timeout) as raw:
            with context.wrap_socket(raw, server_hostname=parts.hostname) as tls:
                der = tls.getpeercert(binary_form=True)
    except (OSError, ssl.SSLError, ValueError):
        return None
    if not der:
        return None
    return x509.load_der_x509_certificate(der).not_valid_after_utc


class CachedProbe:
    """`probe_certificate_expiry` at most once an hour per URL, a failure included."""

    def __init__(self, probe: Callable[[str], datetime | None] = probe_certificate_expiry,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._probe = probe
        self._clock = clock
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, datetime | None]] = {}

    def __call__(self, url: str) -> datetime | None:
        with self._lock:
            hit = self._cache.get(url)
            if hit and self._clock() - hit[0] < PROBE_CACHE_SECONDS:
                return hit[1]
        expires = self._probe(url)
        with self._lock:
            self._cache[url] = (self._clock(), expires)
        return expires


PROBE = CachedProbe()


def tiles(
    session: Session,
    *,
    database_bytes: int | None,
    ca_expires: datetime | None,
    public_url: str,
    format_bytes: Callable[[int], str],
    now: datetime | None = None,
    probe: Callable[[str], datetime | None] | None = None,
    tz=timezone.utc,
) -> list[Tile]:
    """Every tile, in the order the page shows them; dates in `tz`."""
    now = now or datetime.now(timezone.utc)
    probe = probe or PROBE
    play = _safely(lambda: link_status(session, GooglePlayLink, GooglePlayLinkStatus.UNLINKED))
    gov = _safely(lambda: link_status(session, TakGovLink, TakGovLinkStatus.UNLINKED))
    expired = _safely(lambda: len(device_cert_status.expired(session, now=now)))
    return [
        database(database_bytes, format_bytes),
        https_certificate(probe(public_url) if public_url else None, now, tz),
        device_ca(ca_expires, now, tz),
        google_play(play),
        tak_gov(gov),
        open_alerts(count_open_alerts(session)),
        expired_certificates(expired) if expired is not None
        else Tile("expired_certs", "Expired device certificates", "Unknown", UNKNOWN, "Could not be read"),
        stalled_enrollments(count_stalled(session, now)),
    ]
