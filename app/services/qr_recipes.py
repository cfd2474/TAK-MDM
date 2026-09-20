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

"""Reproducing a permanent enrollment QR (W204, GitHub issue #2).

An operator prints a permanent QR for a provisioning bench and comes back a week
later wanting *that* picture. Retyping the group and the Wi-Fi from memory
produces a different QR, and nothing on screen says so.

⚠️ **Nothing here stores a QR or an enrollment secret.** A permanent QR carries
the token's own secret (W137), already sealed on the token row — which is what
makes re-rendering byte-identical rather than minting a second credential. A
recipe holds only the options: which token, which group, which Wi-Fi.

⚠️ **The Wi-Fi password is the exception, and keeping it was a decision.**
Everything else in the payload the server can reproduce; the password it cannot.
It is sealed with the same `TokenVault` as the token secret, under a key in
`pki/` rather than in the database. It is still a network password recoverable
from this server, and `SEC_AUDIT.md` records that trade.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import DeviceGroup, EnrollmentQrRecipe, EnrollmentToken
from app.security.token_vault import TokenVault


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Options:
    """Everything needed to render one permanent QR again.

    ``wifi_password`` is None both when the QR carried no Wi-Fi and when the seal
    cannot be opened — a key replaced since it was written. The caller has to
    tell those apart by looking at :attr:`wifi_recoverable`, because rendering a
    QR with the network silently dropped would hand someone a code that looks
    right and does not join anything.
    """

    group: DeviceGroup | None
    wifi_ssid: str | None
    wifi_security: str | None
    wifi_password: str | None
    wifi_recoverable: bool


def _matches(
    recipe: EnrollmentQrRecipe,
    *,
    group_id: uuid.UUID | None,
    wifi_ssid: str | None,
    wifi_security: str | None,
) -> bool:
    return (
        recipe.group_id == group_id
        and recipe.wifi_ssid == wifi_ssid
        and recipe.wifi_security == wifi_security
    )


def remember(
    session: Session,
    token: EnrollmentToken,
    *,
    group: DeviceGroup | None = None,
    wifi_ssid: str | None = None,
    wifi_security: str | None = None,
    wifi_password: str | None = None,
    vault: TokenVault | None = None,
    created_by: str | None = None,
) -> EnrollmentQrRecipe:
    """Record that this permanent QR was made, so it can be made again.

    ⚠️ **De-duplicated on what identifies the QR, not on the password.** `Fernet`
    seals are non-deterministic — the same password seals to a different string
    every time — so comparing ciphertexts would make every generate look like a
    new recipe and the shelf would fill with duplicates nobody could tell apart.

    The key is therefore the token, the group, the SSID and the security type,
    and a later generate **refreshes** the sealed password. That is the right way
    round: "recall what I last made" is the question being answered, so the last
    one made is the truth.

    ⚠️ Only ever called for *persistent* QRs. A fifteen-minute derivative is a
    different credential every time and a shelf of expired ones would be a list
    of pictures that no longer work.
    """
    group_id = group.id if group is not None else None
    ssid = (wifi_ssid or "").strip() or None
    security = wifi_security if ssid else None

    existing = next(
        (
            r
            for r in for_token(session, token)
            if _matches(r, group_id=group_id, wifi_ssid=ssid, wifi_security=security)
        ),
        None,
    )

    sealed: str | None = None
    if ssid and wifi_password and vault is not None:
        sealed = vault.seal(wifi_password)

    if existing is not None:
        # An open network stays open: only overwrite the seal when this generate
        # actually carried a password, so re-rendering from the shelf (which
        # sends none) cannot quietly forget the one already kept.
        if sealed is not None:
            existing.wifi_password_ciphertext = sealed
        existing.last_shown_at = _utcnow()
        session.flush()
        return existing

    recipe = EnrollmentQrRecipe(
        token_id=token.id,
        group_id=group_id,
        wifi_ssid=ssid,
        wifi_security=security,
        wifi_password_ciphertext=sealed,
        created_by=created_by,
        last_shown_at=_utcnow(),
    )
    session.add(recipe)
    session.flush()
    return recipe


def for_token(session: Session, token: EnrollmentToken) -> list[EnrollmentQrRecipe]:
    """The shelf for one token, newest first.

    One token's rows, which is what `remember` de-duplicates against. The page
    wants :func:`live` instead — a group QR belongs to that group's own standing
    token, so no single token holds the whole shelf.
    """
    return list(
        session.scalars(
            select(EnrollmentQrRecipe)
            .where(EnrollmentQrRecipe.token_id == token.id)
            .order_by(EnrollmentQrRecipe.created_at.desc())
        )
    )


def live(session: Session) -> list[EnrollmentQrRecipe]:
    """Every recipe whose token can still enrol a device, newest first.

    ⚠️ **Not "the primary's recipes", which is what this started as and was
    wrong.** A group-scoped QR resolves to that *group's* standing token, not to
    the primary (W121) — so a shelf filtered to the primary would have hidden
    every group QR, which is most of what a provisioning bench prints.

    The honest filter is whether the token still works: `is_usable` covers
    revoked, expired and used-up alike. A recipe whose token has been retired
    describes a picture that enrols nothing, and showing it next to ones that
    work is the failure this filter exists to prevent.
    """
    now = _utcnow()
    out: list[EnrollmentQrRecipe] = []
    for recipe in session.scalars(
        select(EnrollmentQrRecipe).order_by(EnrollmentQrRecipe.created_at.desc())
    ):
        token = session.get(EnrollmentToken, recipe.token_id)
        if token is not None and token.is_usable(now=now):
            out.append(recipe)
    return out


def get(session: Session, recipe_id: uuid.UUID) -> EnrollmentQrRecipe | None:
    return session.get(EnrollmentQrRecipe, recipe_id)


def options(
    session: Session, recipe: EnrollmentQrRecipe, vault: TokenVault | None
) -> Options:
    """Unpack a recipe into the arguments that render its QR."""
    group = (
        session.get(DeviceGroup, recipe.group_id)
        if recipe.group_id is not None
        else None
    )
    password: str | None = None
    recoverable = True
    if recipe.wifi_password_ciphertext:
        password = vault.open(recipe.wifi_password_ciphertext) if vault else None
        # ⚠️ Sealed but unopenable means the key changed. Saying so beats
        # rendering the QR without the network: the code would scan, look
        # correct, and leave the tablet unable to reach anything.
        recoverable = password is not None
    return Options(
        group=group,
        wifi_ssid=recipe.wifi_ssid,
        wifi_security=recipe.wifi_security,
        wifi_password=password,
        wifi_recoverable=recoverable,
    )


def mark_shown(session: Session, recipe: EnrollmentQrRecipe) -> None:
    recipe.last_shown_at = _utcnow()
    session.flush()


def forget(session: Session, recipe: EnrollmentQrRecipe) -> None:
    """Drop a recipe.

    ⚠️ This takes the *recipe* away, not the credential. The QR it describes goes
    on working, because it carries the token's own secret — only retiring the
    token stops that. A console that implied otherwise would be worse than one
    that says nothing.
    """
    session.delete(recipe)
    session.flush()


def describe(recipe: EnrollmentQrRecipe, group: DeviceGroup | None) -> str:
    """A short label for the shelf: what this QR enrols into, and onto what."""
    scope = group.name if group is not None else "Any group"
    if recipe.wifi_ssid:
        return f"{scope} · Wi-Fi “{recipe.wifi_ssid}”"
    return scope
