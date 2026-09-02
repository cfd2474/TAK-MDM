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

"""Lifecycle of the single TAK.gov account link.

The credential here is unusual enough to be worth stating plainly: it is an
**offline refresh token belonging to a named person**, it inherits exactly that
person's TAK.gov entitlements, and it does not idle out. It is sealed with the
same `TokenVault` as enrollment tokens.

⚠️ **Rotation is the failure mode.** Keycloak issues a *new* refresh token on
every refresh and invalidates the old one immediately. Refresh twice
concurrently, or crash between "received" and "committed", and the link is dead
until a human re-enters a code at tak.gov. `tpc.md` calls this the number one
outage source. Three defences, in order of importance:

1. one lock around the whole refresh, so two requests cannot race;
2. **commit the new token before using it**, so a crash costs a retry;
3. keep the previous token as a one-step fallback, so losing the race anyway is
   recoverable without a human.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db.models import TakGovLink, TakGovLinkStatus
from app.security.token_vault import TokenVault
from app.services import tak_gov

logger = logging.getLogger(__name__)

#: One process, one link. The deployment is single-worker today; when that
#: changes this has to become a database-level lock, and that is recorded as a
#: risk rather than pretended away.
_REFRESH_LOCK = threading.Lock()

#: Refresh this far ahead of expiry. Fetching a token per request would burn a
#: rotation every time, which is the mistake `tpc.md` §2.2 calls out.
_EXPIRY_MARGIN = timedelta(seconds=30)


def get(session: Session) -> TakGovLink:
    """The link row, created unlinked on first use."""
    link = session.get(TakGovLink, 1)
    if link is None:
        link = TakGovLink(id=1, status=TakGovLinkStatus.UNLINKED)
        session.add(link)
        session.flush()
    return link


def is_linked(session: Session) -> bool:
    return get(session).status is TakGovLinkStatus.LINKED


# --------------------------------------------------------------------------- #
# Linking
# --------------------------------------------------------------------------- #


def start(session: Session, *, client=None) -> TakGovLink:
    """Ask tak.gov for a device code and park the link in PENDING."""
    link = get(session)
    code = tak_gov.request_device_code(client=client)

    link.status = TakGovLinkStatus.PENDING
    link.device_code = code.device_code
    link.user_code = code.user_code
    link.verification_uri = code.verification_uri
    link.verification_uri_complete = code.verification_uri_complete
    link.poll_interval_seconds = code.interval
    link.code_expires_at = _now() + timedelta(seconds=code.expires_in)
    link.last_error = None
    session.flush()
    return link


def poll(
    session: Session,
    vault: TokenVault,
    *,
    client=None,
    linked_by: str | None = None,
) -> TakGovLink:
    """One RFC 8628 poll of a PENDING link.

    Returns the link either way — the console renders its state rather than
    branching on an exception. `authorization_pending` is the *expected* answer
    for most of the window and must not be recorded as an error, or the operator
    watches a red banner during the normal path.
    """
    link = get(session)
    if link.status is not TakGovLinkStatus.PENDING or not link.device_code:
        return link

    if link.code_expires_at and _now() >= link.code_expires_at:
        link.status = TakGovLinkStatus.UNLINKED
        link.last_error = "the code expired before it was entered at tak.gov"
        _clear_flow(link)
        session.flush()
        return link

    try:
        tokens = tak_gov.exchange_device_code(link.device_code, client=client)
    except tak_gov.AuthorizationPending:
        return link
    except tak_gov.SlowDown:
        # The server is telling us to back off. RFC 8628 says add 5 seconds.
        link.poll_interval_seconds += 5
        session.flush()
        return link
    except tak_gov.TakGovError as exc:
        link.status = TakGovLinkStatus.UNLINKED
        link.last_error = str(exc)
        _clear_flow(link)
        session.flush()
        return link

    _store_tokens(session, link, tokens, vault=vault)
    link.status = TakGovLinkStatus.LINKED
    link.account_label = tokens.account_label
    link.linked_at = _now()
    link.linked_by = linked_by
    link.last_error = None
    _clear_flow(link)
    session.flush()
    return link


def unlink(session: Session) -> TakGovLink:
    """Forget the credential.

    Local only: this does not revoke anything at tak.gov, and the operator should
    be told that rather than left to assume it.
    """
    link = get(session)
    link.status = TakGovLinkStatus.UNLINKED
    link.refresh_token_sealed = None
    link.previous_refresh_token_sealed = None
    link.access_token_sealed = None
    link.access_expires_at = None
    link.account_label = None
    link.linked_at = None
    link.linked_by = None
    link.last_error = None
    _clear_flow(link)
    session.flush()
    return link


# --------------------------------------------------------------------------- #
# Using the credential
# --------------------------------------------------------------------------- #


def access_token(session: Session, vault: TokenVault, *, client=None) -> str | None:
    """A usable access token, refreshing only when the cached one is nearly out.

    None when the link is not usable — callers render "not linked" rather than
    raising, because that is a normal state of the console, not a fault.
    """
    with _REFRESH_LOCK:
        link = get(session)
        if link.status is not TakGovLinkStatus.LINKED:
            return None

        cached = vault.open(link.access_token_sealed)
        if cached and link.access_expires_at:
            if link.access_expires_at - _EXPIRY_MARGIN > _now():
                return cached

        refresh = vault.open(link.refresh_token_sealed)
        previous = vault.open(link.previous_refresh_token_sealed)
        if not refresh:
            link.status = TakGovLinkStatus.BROKEN
            link.last_error = (
                "the stored refresh token could not be read — it was sealed under "
                "a token-vault key that no longer exists. Re-link at tak.gov."
            )
            session.commit()
            return None

        try:
            tokens = tak_gov.refresh_tokens(refresh, client=client)
        except tak_gov.TakGovError as first_error:
            # The one case worth a second attempt: we may have rotated and lost
            # the result, in which case the *previous* token is still the live
            # one. Any other failure is not retried — repeatedly presenting a
            # dead token to Keycloak achieves nothing.
            if not previous:
                _break(session, link, str(first_error))
                return None
            try:
                tokens = tak_gov.refresh_tokens(previous, client=client)
                logger.warning(
                    "tak.gov refresh recovered using the previous token; a "
                    "rotation was lost but the link survived"
                )
            except tak_gov.TakGovError:
                _break(session, link, str(first_error))
                return None

        _store_tokens(session, link, tokens, vault=vault)
        # Committed before the token is handed out (defence 2): a crash after
        # this point costs nothing, a crash before it costs one retry.
        session.commit()
        return tokens.access_token


def catalog(
    session: Session,
    vault: TokenVault,
    *,
    product: str = tak_gov.DEFAULT_PRODUCT,
    product_version: str = "5.8.0",
    client=None,
) -> tuple[list[tak_gov.Plugin], str | None]:
    """(plugins, error). Never raises — the tab shows whichever it gets."""
    token = access_token(session, vault, client=client)
    if not token:
        return [], None  # not linked; the page says so on its own
    try:
        return (
            tak_gov.fetch_catalog(
                token, product=product, product_version=product_version, client=client
            ),
            None,
        )
    except tak_gov.TakGovError as exc:
        return [], str(exc)


# --------------------------------------------------------------------------- #


def _store_tokens(
    session: Session, link: TakGovLink, tokens: tak_gov.Tokens, *, vault: TokenVault
) -> None:
    """Persist a rotation, keeping the token it replaced as a fallback."""
    link.previous_refresh_token_sealed = link.refresh_token_sealed
    link.refresh_token_sealed = vault.seal(tokens.refresh_token)
    link.access_token_sealed = vault.seal(tokens.access_token)
    link.access_expires_at = _now() + timedelta(seconds=tokens.expires_in)
    session.flush()


def _break(session: Session, link: TakGovLink, detail: str) -> None:
    link.status = TakGovLinkStatus.BROKEN
    link.last_error = detail
    session.commit()


def _clear_flow(link: TakGovLink) -> None:
    link.device_code = None
    link.user_code = None
    link.verification_uri = None
    link.verification_uri_complete = None
    link.code_expires_at = None


def _now() -> datetime:
    return datetime.now(timezone.utc)
