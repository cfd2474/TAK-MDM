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

"""The master PIN that lets an operator past the provisioning permission block.

W115 blocked setup until the required permissions are granted, with a plain
"Continue anyway" confirmation behind it. A confirmation dialog is tapped by
someone in a hurry who does not read it — roughly the situation that produced
the bug — so W117 puts a six-digit PIN in front of it instead.

⚠️ **The PIN never travels to a device.** The obvious design is to ship it, or a
hash of it, in the provisioning extras so the agent can check offline. That
leaks it: six digits is a million candidates, so a hash inside a QR code that
gets displayed on screens and photographed is brute-forced immediately, and a
slow KDF only changes how immediately. The agent sends what the operator typed
and this server answers yes or no.

⚠️ **Stored in plaintext**, next to the SMTP and directory credentials already in
`app_setting` (see `settings_store`, folded into R8). It has to be displayable to
be usable at all — the operator reads it off the Admin page and types it into a
tablet — so hashing is not on the table. Sealing it with `TokenVault` was
considered and rejected as theatre: the vault key lives on this same host, and
see below for how little the secret is worth.

⚠️ **What it can actually do, so nobody over-trusts it:** skip the permission
grants while provisioning a device the holder already has a valid enrollment
token for. The result is a *less* capable managed device — no file access, no
overlay — not a compromise of the fleet or of this server. It is an
administrative control. The Admin page says so rather than dressing it up.

That said, a fixed per-install code gets treated as a master secret whatever the
note says, so guessing is capped per enrollment token (see `verify`).
"""

from __future__ import annotations

import hmac
import logging
import secrets

from typing import Protocol

from sqlalchemy.orm import Session

from app.services import settings_store


class AttemptSubject(Protocol):
    """Whatever is being rate-limited: an enrollment token, or a device.

    ⚠️ **Both exist because the credential changes halfway through provisioning.**
    The first version authorized this check with the enrollment token alone, and
    that token is deliberately destroyed the moment the device enrols
    (`Reconciler.kt`: *"keeping it would leave a usable enrollment credential on
    the device"*). An operator who reached the permission screen after enrolment
    — which is the normal case, not an edge case — had no credential left and
    was told the code could not be checked. So an enrolled device authenticates
    with its client certificate instead, and the counter follows whichever
    identity was used.
    """

    bypass_attempts: int

logger = logging.getLogger(__name__)

#: Where the PIN lives in `app_setting`.
KEY = "provisioning.bypass_pin"

#: Six digits, as asked for. Kept as a string throughout: a leading zero is a
#: perfectly good part of a PIN and int() would eat it.
DIGITS = 6

#: Failed attempts allowed per enrollment token before that token is refused.
#: ⚠️ Per *token*, deliberately, not global. A global counter would let anyone
#: holding one token lock every other operator out of provisioning, turning a
#: brute-force guard into a denial of service. A token is minted by an admin, so
#: an attacker cannot mint themselves fresh attempts.
MAX_ATTEMPTS = 10


def get_or_create(session: Session) -> str:
    """This install's PIN, generating it the first time it is asked for.

    ⚠️ **Generated on first read rather than only at install.** The brief said
    "generated upon install", and doing that literally — in the `init` container
    — would leave every *existing* deployment permanently without a PIN, and so
    with a bypass button nobody can use. Get-or-create is idempotent, covers
    fresh and upgraded installs alike, and still yields one fixed value per
    install, which is what the requirement is actually for.
    """
    existing = settings_store.get(session, KEY)
    if existing:
        return existing

    # secrets, not random: this is a credential, however modest.
    pin = "".join(secrets.choice("0123456789") for _ in range(DIGITS))
    settings_store.put(session, KEY, pin, updated_by="system")
    logger.info("generated the provisioning bypass PIN for this install")
    return pin


def verify(session: Session, subject: AttemptSubject, candidate: str, *,
           label: str = "") -> bool:
    """Check `candidate` against this install's PIN, counting failures.

    ⚠️ The attempt counter is spent **before** the comparison and only reset on
    success, so a crash or a dropped connection mid-check cannot be used to get a
    free guess.

    `subject` is the identity being rate-limited — an enrollment token before the
    device enrols, the device itself afterwards. See `AttemptSubject`.
    """
    who = label or type(subject).__name__

    if subject.bypass_attempts >= MAX_ATTEMPTS:
        logger.warning(
            "bypass PIN refused: %s has spent its %d attempts", who, MAX_ATTEMPTS
        )
        return False

    subject.bypass_attempts += 1
    session.flush()

    # compare_digest, not ==: the timing leak is tiny over a network and the
    # correct call costs nothing.
    if not hmac.compare_digest(get_or_create(session), (candidate or "").strip()):
        logger.warning(
            "bypass PIN rejected for %s (attempt %d of %d)",
            who, subject.bypass_attempts, MAX_ATTEMPTS,
        )
        return False

    subject.bypass_attempts = 0
    session.flush()
    logger.info("bypass PIN accepted for %s", who)
    return True


def attempts_remaining(subject: AttemptSubject) -> int:
    return max(0, MAX_ATTEMPTS - subject.bypass_attempts)
