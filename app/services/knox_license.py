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

"""The Knox licence key: where it is kept, and how little of it travels.

The operator pastes a KPE/KLM key from Samsung's Knox Admin Portal into Admin →
Samsung Knox. Devices running the `knox` build of the agent activate against it
and report what Samsung said; every other device reports `NOT_APPLICABLE` and is
unaffected.

⚠️ **The key is sealed at rest and must stay out of the cached effective
policy.** `AppSetting` holds it through `TokenVault`, so a database dump carries
ciphertext (SEC_AUDIT.md M-5). The effective-policy cache is plain JSON, one row
per device, in that same database — writing the key there would put N plaintext
copies of it beside the one sealed copy and make the sealing decorative. It is
also what the console renders on the Effective policy page.

So this module gives out two different things:

- [`marker`] — what goes in the **cached** payload: that a key is configured, and
  a fingerprint of it. No key.
- [`configured_key`] — the key itself, for the **outgoing signed bundle** only,
  assembled per response and never stored.

⚠️ **The fingerprint is load-bearing, not decoration.** `effective_policy.refresh`
decides whether to bump `state_version` by comparing the payload it just computed
against the cached one. With nothing in that payload that moves when the key
moves, changing the key would reach only devices whose state happened to change
for some other reason — Knox licensed on some tablets and not others, with
nothing on any page to say why.

It is truncated to 12 hex characters deliberately. It exists to answer "is this
the same key as last time?", and 48 bits answers that while identifying no
particular key: a full digest of a secret is a thing worth attacking, and a
change-detector need not be one.
"""

from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.orm import Session

#: The settings key, defined once. The form field, the reader and the
#: invalidation hook all name this rather than the string.
LICENSE_KEY_SETTING = "knox.license_key"

#: The settings group, so the save route can recognise it without a literal.
SETTINGS_GROUP = "knox"

#: Where the marker sits in the effective-policy payload.
#:
#: ⚠️ Deliberately not under `values`. `values` is resolved policy, rendered with
#: provenance on the device page and diffed by `preview`; a fleet-wide admin
#: setting is none of those things, and a row in that table with no policy behind
#: it reads as a resolver bug.
PAYLOAD_KEY = "oem_licensing"

#: Where the key itself sits in the signed bundle the device receives.
#:
#: ⚠️ **Neither name says "knox", and that is enforced rather than tasteful.**
#: The agent reads this in `Reconciler`, which is in `main` and therefore
#: compiled into the AOSP artifact — and `verifyAospHasNoKnox` fails a build
#: whose dex mentions Knox at all. A field called `knox_license_key` would put
#: the word there, for a wire name that was never Samsung-specific to begin
#: with. Same lesson as `OemLicenseState`, which was `KnoxLicenseState` for an
#: hour (W226).
BUNDLE_KEY = "oem"

#: The field inside that block.
LICENSE_KEY_FIELD = "license_key"


def configured_key(session: Session) -> str:
    """The licence key in plaintext, or `""` when none is set.

    ⚠️ **Only ever for the outgoing bundle.** Every other caller wants
    [`marker`]. Read through `settings_store` rather than `AppSetting` directly,
    because the stored value is sealed and `group_values` is what unseals it.
    """
    from app.services import settings_store

    values = settings_store.group_values(session, SETTINGS_GROUP)
    return (values.get(LICENSE_KEY_SETTING) or "").strip()


def fingerprint(key: str) -> str:
    """A short, stable token that changes when, and only when, the key changes."""
    if not key:
        return ""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def unset_marker() -> dict[str, Any]:
    """What [`marker`] returns when no key is set.

    Named, because `refresh` needs it as the baseline for a cache row written
    before this feature existed. ⚠️ Defaulting that lookup to `{}` instead
    would make every such row differ from the marker computed for a fleet with
    no Knox key at all — bumping `state_version` for every enrolled device on
    the release that added this, and resending a bundle to all of them to say
    nothing.

    A fresh dict each call rather than a module constant: a shared mutable
    default is the oldest trap in the language, and this one would be handed to
    a comparison that a caller could poison.
    """
    return {"knox": {"configured": False, "fingerprint": ""}}


def marker(session: Session) -> dict[str, Any]:
    """What the cached payload records about the licence. Never the key.

    Always returns a block, including when no key is set: `configured: False` is
    a fact the device page can render and, more importantly, one the cache
    comparison can notice changing. Omitting the block when unset would make
    "cleared the key" indistinguishable from "an older payload that predates this
    feature", and a cleared key would not reach the fleet.
    """
    key = configured_key(session)
    if not key:
        return unset_marker()
    return {"knox": {"configured": True, "fingerprint": fingerprint(key)}}


def bundle_block(session: Session) -> dict[str, Any] | None:
    """The key as the device receives it, or None when there is nothing to send.

    ⚠️ **Plaintext, and there is no alternative shape.** Samsung's
    `activateLicense(String, LicenseResultCallback)` takes the key itself. What
    protects it in flight is what protects every other policy value: mTLS, and an
    Ed25519 signature over the document. That is the same protection the
    enrolment secret and the Wi-Fi password in a QR already rely on.

    ⚠️ **Nothing is sent when no key is set**, rather than an empty string. The
    agent treats absent as "no licence configured" and reports `NOT_LICENSED`,
    which is a state; an empty key sent to Knox would spend an attempt from the
    rate limit error 209 enforces to be told what we already knew.
    """
    key = configured_key(session)
    if not key:
        return None
    return {LICENSE_KEY_FIELD: key}


# --------------------------------------------------------------------------- #
# What the console shows
# --------------------------------------------------------------------------- #

#: A short label per status the agent can report.
#:
#: ⚠️ Keyed on `OemLicenseState.Status` in the agent, and the two have to
#: agree. `tests/test_knox_license.py` reads the Kotlin enum and asserts that
#: every member is here — a status added on the device and forgotten here would
#: otherwise reach an operator as a raw `NOT_LICENSED`-shaped word.
STATUS_LABELS: dict[str, str] = {
    "NOT_APPLICABLE": "Not applicable",
    "NOT_LICENSED": "Not licensed",
    "ACTIVATING": "Activating…",
    "ACTIVE": "Active",
    "FAILED": "Failed",
    "LAPSED": "Lapsed",
}

#: Statuses that should read as a problem an operator can act on.
#:
#: ⚠️ `NOT_LICENSED` is **not** one of them. On a fleet with no Knox key
#: configured that is every Samsung tablet, and colouring all of them red would
#: train an operator to ignore the column before it ever says anything true.
PROBLEM_STATUSES = frozenset({"FAILED", "LAPSED"})


def status_label(status: str | None) -> str:
    """A human label, falling back to whatever the device actually said.

    ⚠️ **An unrecognised status is shown verbatim, not as "Unknown".** This
    is what a newer agent reporting a status this server has not learned looks
    like, and the raw word is the one thing that lets an operator search for it.
    """
    if not status:
        return "Not reported"
    return STATUS_LABELS.get(status, status)


def is_problem(status: str | None) -> bool:
    return status in PROBLEM_STATUSES
