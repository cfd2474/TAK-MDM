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
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select, update
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
            # A limited QR is its own credential (W330): never the one a
            # permanent generate refreshes.
            if not r.limited
            and _matches(r, group_id=group_id, wifi_ssid=ssid, wifi_security=security)
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


# --------------------------------------------------------------------------- #
# Limited QR codes (W330)
# --------------------------------------------------------------------------- #

#: The longest a timed QR may run. Past this, a use count or a permanent QR is
#: the honest tool.
MAX_TIMER = timedelta(days=30)

#: A dead limited QR is kept this long, then purged on a later generate.
KEEP_DEAD_FOR = timedelta(days=7)


#: The units the Generate form offers for the timer, in seconds.
TIMER_UNITS = {"minutes": 60, "hours": 3600, "days": 86400}

#: A use count above this is a typo, not a plan.
MAX_USES_LIMIT = 10_000


@dataclass(frozen=True)
class Limits:
    """What the operator asked a new QR to stop at. Neither = permanent."""

    expires_after: timedelta | None = None
    max_uses: int | None = None

    @property
    def permanent(self) -> bool:
        return self.expires_after is None and self.max_uses is None


#: What the Generate form starts with: a fifteen-minute timer, no use count.
DEFAULT_FORM = {"timer_on": True, "timer_amount": 15, "timer_unit": "minutes",
                "uses_on": False, "max_uses": ""}


def parse_limits(
    *, timer_on: bool, timer_amount: str, timer_unit: str, uses_on: bool, max_uses: str
) -> Limits:
    """Read the Generate form's two optional limits, or raise ValueError.

    The message is a sentence for the operator: it is shown as the page's error.
    """
    expires_after = None
    if timer_on:
        seconds = TIMER_UNITS.get(timer_unit)
        amount = _positive_int(timer_amount)
        if seconds is None or amount is None:
            raise ValueError("the expiration timer needs a whole number of minutes, hours or days")
        expires_after = timedelta(seconds=amount * seconds)
        if expires_after > MAX_TIMER:
            raise ValueError("the expiration timer can be at most 30 days")
    uses = None
    if uses_on:
        uses = _positive_int(max_uses)
        if uses is None or uses > MAX_USES_LIMIT:
            raise ValueError(
                f"the use count needs a whole number from 1 to {MAX_USES_LIMIT:,}"
            )
    return Limits(expires_after, uses)


def _positive_int(text: str) -> int | None:
    text = (text or "").strip()
    if not text.isdigit():
        return None
    value = int(text)
    return value if value >= 1 else None


def form_values(recipe: EnrollmentQrRecipe | None) -> dict:
    """The Generate form, filled in as this QR was made (the defaults for none).

    The QR page's own form carries these, so adding Wi-Fi to a 5-use QR makes
    another 5-use QR rather than quietly falling back to the defaults.
    """
    if recipe is None:
        return dict(DEFAULT_FORM)
    if not recipe.limited:
        return form_for(Limits())
    expires_after = (
        recipe.expires_at - recipe.created_at if recipe.expires_at is not None else None
    )
    return form_for(Limits(expires_after, recipe.max_uses))


def form_for(limits: Limits) -> dict:
    """The Generate form, filled in from limits just parsed."""
    values = {**DEFAULT_FORM, "timer_on": limits.expires_after is not None,
              "uses_on": limits.max_uses is not None, "max_uses": limits.max_uses or ""}
    if limits.expires_after is not None:
        seconds = round(limits.expires_after.total_seconds())
        # The largest unit that says it exactly: 2 days, not 48 hours.
        for unit in ("days", "hours", "minutes"):
            if seconds % TIMER_UNITS[unit] == 0:
                values["timer_amount"], values["timer_unit"] = seconds // TIMER_UNITS[unit], unit
                break
    return values


@dataclass(frozen=True)
class State:
    live: bool
    #: Why it can't enrol, in words, or None while live.
    reason: str | None
    expires_at: datetime | None
    uses_left: int | None


def state(recipe: EnrollmentQrRecipe, token: EnrollmentToken | None, now: datetime) -> State:
    """Whether a recipe's QR can enrol a device right now, and how much is left."""
    uses_left = (
        max(recipe.max_uses - recipe.use_count, 0) if recipe.max_uses is not None else None
    )
    reason = None
    if token is None or not token.is_usable(now=now):
        reason = "its enrolment token was retired"
    elif recipe.limited and recipe.expires_at is not None and now >= recipe.expires_at:
        reason = "it expired"
    elif recipe.limited and uses_left == 0:
        reason = "it was used up"
    return State(reason is None, reason, recipe.expires_at, uses_left)


def remember_limited(
    session: Session,
    token: EnrollmentToken,
    limits: Limits,
    *,
    group: DeviceGroup | None = None,
    wifi_ssid: str | None = None,
    wifi_security: str | None = None,
    wifi_password: str | None = None,
    vault: TokenVault | None = None,
    created_by: str | None = None,
    recipe_id: uuid.UUID | None = None,
) -> EnrollmentQrRecipe:
    """A new limited QR. Never de-duplicated: each one counts its own uses.

    `recipe_id` lets the caller sign the QR's secret before the row exists, so
    nothing is saved for a QR that then fails to draw.
    """
    if limits.permanent:
        raise ValueError("a limited QR needs an expiry, a use count, or both")
    if limits.max_uses is not None and limits.max_uses < 1:
        raise ValueError("a use count is at least 1")
    _purge_dead(session)
    ssid = (wifi_ssid or "").strip() or None
    now = _utcnow()
    recipe = EnrollmentQrRecipe(
        id=recipe_id or uuid.uuid4(),
        token_id=token.id,
        group_id=group.id if group is not None else None,
        wifi_ssid=ssid,
        wifi_security=wifi_security if ssid else None,
        wifi_password_ciphertext=(
            vault.seal(wifi_password) if ssid and wifi_password and vault is not None else None
        ),
        created_by=created_by,
        created_at=now,
        last_shown_at=now,
        limited=True,
        expires_at=now + limits.expires_after if limits.expires_after is not None else None,
        max_uses=limits.max_uses,
        use_count=0,
    )
    session.add(recipe)
    session.flush()
    return recipe


def _purge_dead(session: Session) -> None:
    """Drop limited QRs that have been unable to enrol for a week."""
    now = _utcnow()
    cutoff = now - KEEP_DEAD_FOR
    for recipe in session.scalars(select(EnrollmentQrRecipe).where(EnrollmentQrRecipe.limited.is_(True))):
        expired_long_ago = recipe.expires_at is not None and recipe.expires_at < cutoff
        used_up_long_ago = (
            recipe.max_uses is not None and recipe.use_count >= recipe.max_uses
            and (recipe.last_shown_at or recipe.created_at) < cutoff
        )
        if expired_long_ago or used_up_long_ago:
            session.delete(recipe)
    session.flush()


def claim(session: Session, recipe_id: uuid.UUID, now: datetime | None = None) -> bool:
    """Take one use of a limited QR, or report that none is left.

    ⚠️ **One conditional UPDATE, not a read then a write.** Two devices racing
    for a QR's last use would both read "1 left" and both enrol; the database
    applies this atomically, so exactly one gets the row back. It runs inside the
    enrolment's transaction, so a failed enrolment gives the use back.
    """
    now = now or _utcnow()
    result = session.execute(
        update(EnrollmentQrRecipe)
        .where(
            EnrollmentQrRecipe.id == recipe_id,
            EnrollmentQrRecipe.limited.is_(True),
            or_(EnrollmentQrRecipe.max_uses.is_(None),
                EnrollmentQrRecipe.use_count < EnrollmentQrRecipe.max_uses),
            or_(EnrollmentQrRecipe.expires_at.is_(None), EnrollmentQrRecipe.expires_at > now),
        )
        .values(use_count=EnrollmentQrRecipe.use_count + 1)
        .execution_options(synchronize_session="fetch")
    )
    return result.rowcount == 1


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
        # W330: a limited QR also stops at its expiry or its last use.
        if state(recipe, token, now).live:
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

    ⚠️ For a **permanent** QR this takes the *recipe* away, not the credential.
    The QR it describes goes on working, because it carries the token's own
    secret; only retiring the token stops that.

    ⚠️ For a **limited** QR (W330) the recipe *is* the credential: its secret names
    this row, so dropping it **revokes** the code. The console calls it Revoke.
    """
    session.delete(recipe)
    session.flush()


def describe(recipe: EnrollmentQrRecipe, group: DeviceGroup | None) -> str:
    """A short label for the shelf: what this QR enrols into, and onto what."""
    scope = group.name if group is not None else "Any group"
    if recipe.wifi_ssid:
        return f"{scope} · Wi-Fi “{recipe.wifi_ssid}”"
    return scope
