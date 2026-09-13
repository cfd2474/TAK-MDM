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

"""Binding one Google account, so Play can be a source (W99).

The operator does the browser half themselves — Google's embedded setup page,
devtools open, copy the `oauth_token` cookie — and pastes the result here. That
value is **single-use**: apkeep spends it to mint a long-lived AAS token, which is
what every later download presents.

⚠️ **Two things never happen in this module.** The AAS token is never written to a
command line, because argv is readable by anything that can see `/proc` on the
host; and it is never returned to the console once sealed. The only ways out are a
download, or `unlink`, which destroys it.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import GooglePlayLink, GooglePlayLinkStatus
from app.security.token_vault import TokenVault

logger = logging.getLogger(__name__)

#: apkeep's own default. Play serves device-matched builds, so this decides the
#: architecture that arrives — arm64, which is what this fleet runs.
DEFAULT_DEVICE = "px_9a"

#: Every device profile apkeep's bundled `gpapi` knows, as
#: `(profile, model, primary ABI)`.
#:
#: ⚠️ **Play serves a build matched to this profile.** Choosing one whose primary
#: ABI is 32-bit makes Play hand back an armeabi-v7a APK, which is the wrong
#: binary for an arm64 tablet — and nothing downstream would call that an error,
#: because it is a real APK that simply will not run well.
#:
#: Transcribed from `gpapi/device.properties` in EFForg/rs-google-play (23
#: profiles, read 2026-09-13). ⚠️ **It is a convenience, not a gate**: the server
#: still accepts any non-empty value, because a list that drifts from the
#: apkeep in the image should cost an operator a dropdown entry, never the
#: ability to link an account.
DEVICE_PROFILES: tuple[tuple[str, str, str], ...] = (
    ('bravia_vu2', 'BRAVIA VU2', 'armeabi-v7a'),
    ('google_kiwi_x86_64', 'Google Play Games on PC', 'x86_64'),
    ('hw_mate20', 'Huawei Mate 20', 'arm64-v8a'),
    ('mi_a1', 'Xiaomi Mi A1', 'arm64-v8a'),
    ('nk_drx', 'Nokia 1.3', 'arm64-v8a'),
    ('nothing_p1', 'Nothing Phone(1)', 'arm64-v8a'),
    ('op_8_pro', 'OnePlus8Pro_EEA', 'arm64-v8a'),
    ('oppo_r17', 'Oppo R17', 'arm64-v8a'),
    ('poco_f1', 'reloaded_beryllium', 'arm64-v8a'),
    ('px_9_fold', 'Google Pixel 9 Pro Fold', 'arm64-v8a'),
    ('px_9a', 'Google Pixel 9a', 'arm64-v8a'),
    ('px_tablet', 'Google Pixel Tablet', 'arm64-v8a'),
    ('rm_5_pro', 'Realme 5 Pro', 'armeabi-v7a'),
    ('rm_5i', 'Realme 5i', 'arm64-v8a'),
    ('rm_7', 'Redmi 7', 'arm64-v8a'),
    ('rm_note_12_4g', 'Redmi Note 12 4G', 'arm64-v8a'),
    ('sm_a13_5g', 'Samsung A13 5G', 'armeabi-v7a'),
    ('sm_f34_5g', 'Samsung F34 5G', 'arm64-v8a'),
    ('sm_j5_prime', 'Samsung J5 Prime', 'armeabi-v7a'),
    ('sm_s20_plus', 'Samsung S20+', 'arm64-v8a'),
    ('sm_s25u', 'Galaxy S25 Ultra', 'arm64-v8a'),
    ('xm_11a', 'Xiaomi 11 Lite 5G NE', 'arm64-v8a'),
    ('xp_5_dual', 'Xperia 5 Dual', 'arm64-v8a'),
)


def profiles_by_architecture() -> list[tuple[str, list[tuple[str, str, str]]]]:
    """`DEVICE_PROFILES` grouped for a picker, 64-bit first.

    The architecture is the only part of this choice that can go quietly wrong,
    so it is what the groups are built on rather than the manufacturer.
    """
    groups: dict[str, list[tuple[str, str, str]]] = {}
    for profile, model, abi in DEVICE_PROFILES:
        if abi == "arm64-v8a":
            key = "64-bit ARM — what ATAK tablets use"
        elif abi.startswith("armeabi"):
            key = "32-bit ARM only"
        else:
            key = "x86"
        groups.setdefault(key, []).append((profile, model, abi))
    order = ["64-bit ARM — what ATAK tablets use", "32-bit ARM only", "x86"]
    return [(name, groups[name]) for name in order if name in groups]


#: The one-time value copied out of the browser. Checked so an obvious paste
#: mistake is caught here rather than surfacing as an opaque apkeep failure.
_OAUTH = re.compile(r"^oauth2_4/[A-Za-z0-9._\-]+$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

#: apkeep prints the minted token; this is how it is recognised in the output.
_AAS = re.compile(r"\b(aas_et/[A-Za-z0-9._\-]+)\b")

_TIMEOUT_SECONDS = 180


class GooglePlayLinkError(RuntimeError):
    """The account could not be bound, in words an operator can act on."""


def get(session: Session) -> GooglePlayLink:
    """The singleton row, created unlinked on first look."""
    link = session.get(GooglePlayLink, 1)
    if link is None:
        link = GooglePlayLink(id=1, status=GooglePlayLinkStatus.UNLINKED)
        session.add(link)
        session.flush()
    return link


def link_account(
    session: Session,
    vault: TokenVault,
    *,
    email: str,
    oauth_token: str,
    device_profile: str = DEFAULT_DEVICE,
    linked_by: str | None = None,
    binary: str = "apkeep",
    runner=subprocess.run,
) -> GooglePlayLink:
    """Spend the one-time token for a durable one, and seal it.

    ⚠️ **The oauth token is spent whether or not this succeeds.** Google issues it
    for a single exchange, so a failure here means the operator must fetch a fresh
    one — which the error says, because otherwise they will retry with a value
    that can no longer work and conclude the feature is broken.
    """
    email = (email or "").strip()
    oauth_token = (oauth_token or "").strip()

    if not _EMAIL.match(email):
        raise GooglePlayLinkError(f"{email!r} does not look like an email address")
    if not _OAUTH.match(oauth_token):
        raise GooglePlayLinkError(
            "that does not look like an oauth token — it should start with "
            "'oauth2_4/'. Copy the *value* of the oauth_token cookie, not the "
            "whole cookie."
        )

    link = get(session)
    try:
        # ⚠️ The oauth token is single-use and already spent by this call, so it
        # goes on the command line and the AAS token never does. The durable
        # secret is the one worth keeping out of the process list.
        result = runner(
            [binary, "-e", email, "--oauth-token", oauth_token],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        link.status = GooglePlayLinkStatus.BROKEN
        link.last_error = f"apkeep timed out after {_TIMEOUT_SECONDS}s"
        raise GooglePlayLinkError(link.last_error) from exc
    except OSError as exc:
        link.status = GooglePlayLinkStatus.BROKEN
        link.last_error = f"could not run apkeep ({exc})"
        raise GooglePlayLinkError(link.last_error) from exc

    found = _AAS.search(f"{result.stdout}\n{result.stderr}")
    if result.returncode != 0 or not found:
        detail = (result.stderr or result.stdout or "").strip()[:200]
        link.status = GooglePlayLinkStatus.BROKEN
        link.last_error = detail or "apkeep produced no AAS token"
        # Said plainly: an oauth token cannot be reused, and an operator retrying
        # with the same one would blame the wrong thing.
        raise GooglePlayLinkError(
            f"{link.last_error}. The oauth token has now been used up either way — "
            f"fetch a fresh one before trying again."
        )

    link.email = email
    link.aas_token_sealed = vault.seal(found.group(1))
    link.device_profile = (device_profile or DEFAULT_DEVICE).strip() or DEFAULT_DEVICE
    link.status = GooglePlayLinkStatus.LINKED
    link.linked_at = datetime.now(timezone.utc)
    link.linked_by = linked_by
    link.last_error = None
    session.flush()
    logger.info("google play linked as %s (device %s)", email, link.device_profile)
    return link


def unlink(session: Session) -> GooglePlayLink:
    """Forget the account and destroy the token.

    ⚠️ **This does not revoke anything at Google.** The token stops being held
    here; it may still be valid until the account owner removes access from their
    Google security settings. The console says so rather than implying a
    completeness it cannot deliver.
    """
    link = get(session)
    link.status = GooglePlayLinkStatus.UNLINKED
    link.aas_token_sealed = None
    link.email = None
    link.linked_at = None
    link.linked_by = None
    link.last_error = None
    session.flush()
    return link


def credentials(session: Session, vault: TokenVault) -> tuple[str, str, str] | None:
    """`(email, aas_token, device_profile)`, or None when nothing is linked."""
    link = get(session)
    if link.status is not GooglePlayLinkStatus.LINKED or not link.aas_token_sealed:
        return None
    return (link.email or "", vault.open(link.aas_token_sealed), link.device_profile)


def write_ini(directory: Path, email: str, aas_token: str) -> Path:
    """Put the credentials in a file apkeep reads, readable only by this user.

    ⚠️ **This exists so the token stays off the command line.** `apkeep -t <token>`
    puts a durable Google credential in argv, where any process able to read
    `/proc` on the host can see it. apkeep documents an ini file for exactly this,
    and it is written `0600` into a directory that is deleted afterwards.
    """
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "apkeep.ini"
    # Created with restrictive permissions from the start rather than chmod-ed
    # afterwards: between the two there is a window where it is world-readable.
    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(handle, "w", encoding="utf-8") as out:
        out.write(f"[google]\nemail = {email}\naas_token = {aas_token}\n")
    return path


def temporary_ini(email: str, aas_token: str):
    """A context manager yielding an ini path that is removed on exit."""

    class _Ini:
        def __enter__(self):
            self._dir = tempfile.TemporaryDirectory()
            return write_ini(Path(self._dir.name), email, aas_token)

        def __exit__(self, *exc):
            self._dir.cleanup()
            return False

    return _Ini()
