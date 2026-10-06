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

"""How a private key reaches the disk, and how we notice when it should not have.

Five private keys live in ``pki/`` — the device CA, the token vault, the CSRF
signer, the enrollment-QR signer, and the desired-state bundle signer. Read
access to that directory is total compromise of this system: mint a certificate
for any device, decrypt every stored enrollment secret, forge an administrator's
CSRF token, forge a provisioning QR, and sign a management document the agent
believes. `SEC_AUDIT.md` **S-2**.

⚠️ **This module does not solve S-2, and nothing on this host can.** A key the
application must read at runtime, on a machine the attacker is assumed to have
reached, is readable by that attacker. Encrypting it with a passphrase stored
beside it is the oldest anti-pattern in the subject. The real answer is custody
somewhere the application only *asks* — a KMS or an HSM — which is `R8`.

What this module does is narrower and worth doing anyway:

* **A key is never briefly world-readable.** The previous pattern wrote the file
  and then chmod'd it, leaving a window at the process umask.
* **The directory is not listable** by anyone but its owner.
* **We notice when the modes are wrong**, which is the realistic failure: a
  restore, a `cp -r`, a bind mount, or an archive that widened them. Nobody
  watches a file's permissions; something has to look.
"""

from __future__ import annotations

import logging
import os
import stat
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

#: Every private key this system keeps on disk.
#:
#: ⚠️ Named explicitly rather than globbed. A glob decides what to audit from
#: what happens to be there, so a key added under a name the pattern misses is
#: silently not audited — and the audit reporting nothing is indistinguishable
#: from the audit finding nothing. A new key must be added here, and the test
#: that walks the writers is what makes that unmissable.
PRIVATE_KEYS = (
    "ca.key",
    "token_vault.key",
    "csrf.key",
    "enrollment_qr.key",
    "bundle_signing.key",
)

#: Mode a private key is created with, and the only mode it may have.
KEY_MODE = 0o600

#: Mode the directory holding them is created with.
DIR_MODE = 0o700

#: Bits that must never be set on a key or its directory.
_FORBIDDEN = stat.S_IRWXG | stat.S_IRWXO

#: ⚠️ Windows does not implement POSIX modes: `os.chmod` sets little more than the
#: read-only flag, and `st_mode` reports 0o666 or 0o444 whatever we ask for. The
#: audit would therefore report every key as exposed on a developer workstation,
#: and an alarm that always fires is one nobody reads. Enforcement is Linux-only;
#: the deployment is Linux, and the pure functions below are tested everywhere.
POSIX_MODES = os.name != "nt"


@dataclass(frozen=True)
class Exposure:
    """One key file whose permissions are wider than they should be."""

    path: str
    mode: int

    @property
    def detail(self) -> str:
        who = []
        if self.mode & stat.S_IRWXG:
            who.append("group")
        if self.mode & stat.S_IRWXO:
            who.append("others")
        return f"{self.path} is {oct(self.mode & 0o777)} — readable by {' and '.join(who)}"


def is_exposed(mode: int) -> bool:
    """Does this mode let anyone but the owner near the file?

    Pure, so the rule is testable on a platform that cannot express it.
    """
    return bool(mode & _FORBIDDEN)


def secure_dir(path: Path) -> Path:
    """Create (or tighten) the directory a private key lives in.

    ⚠️ The mode is passed to `mkdir` as well as applied afterwards — the same
    reason `write_private` uses `os.open`. Creating the directory at the umask and
    tightening it after leaves it listable in between, and on the reference box it
    was found at `drwxr-xr-x`: the keys inside were `0600`, but anyone able to
    traverse could enumerate them and read `ca.crt`.

    The `chmod` is still needed for a directory that already exists, which is the
    common case — a bind mount created by the installer.
    """
    path.mkdir(parents=True, exist_ok=True, mode=DIR_MODE)
    if POSIX_MODES:
        try:
            path.chmod(DIR_MODE)
        except OSError as exc:
            # Not fatal: a bind-mounted directory owned by someone else cannot be
            # re-moded by us, and refusing to start over it would be worse than
            # the exposure. The audit reports it instead.
            logger.warning("could not restrict %s to %o: %s", path, DIR_MODE, exc)
    return path


def write_private(path: Path, data: bytes) -> Path:
    """Write a private key that is never, at any instant, readable by anyone else.

    ⚠️ **The mode is set by `os.open`, not by a later `chmod`.** The previous
    pattern — `write_bytes` then `chmod(0o600)` — left the key on disk at the
    process umask for the time between the two calls, commonly `0644`. The window
    is short and it is real, and it applied to all five keys.

    `O_EXCL` because every caller here is creating a key that does not exist yet.
    A key file already being there means something happened that nobody intended,
    and silently overwriting a CA key would destroy every enrolled device's
    identity. Louder is better.
    """
    secure_dir(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, KEY_MODE)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
    except BaseException:
        # A half-written key is worse than none: it would be loaded on the next
        # start and fail somewhere far from here.
        path.unlink(missing_ok=True)
        raise
    return path


def shred(path: Path) -> None:
    """Overwrite a key file and remove it. Best effort, and the word is chosen.

    ⚠️ **This does not guarantee the bytes are gone**, and claiming otherwise
    would be worse than not doing it. On an SSD wear levelling means the
    overwrite lands somewhere else; on a journalling or copy-on-write filesystem
    the old extent may survive; and a VM snapshot or a backup taken while the key
    was present is untouched by anything this process can do.

    It is still worth doing: it defeats casual recovery and undelete, and it
    makes the file unreadable to anything that opens it afterwards. The controls
    that actually bound this are that the key was on the disk only briefly, and
    that the disk should be encrypted.
    """
    try:
        size = path.stat().st_size
        with open(path, "r+b", buffering=0) as handle:
            handle.write(bytes(size))
            handle.flush()
            os.fsync(handle.fileno())
    except OSError:
        # An unwritable or already-missing file still gets the unlink below;
        # failing the removal because the overwrite failed would leave the key
        # exactly where it was, which is the worse outcome.
        pass
    path.unlink(missing_ok=True)


def audit(pki_dir: Path) -> list[Exposure]:
    """Report any key in ``pki_dir`` whose permissions are too wide.

    Reports rather than raises. ⚠️ Refusing to start would convert a permissions
    problem into an outage of the whole management plane — including the console
    an operator would use to investigate — and the keys are no safer for the
    server being down. The log line is the alarm.
    """
    if not POSIX_MODES:
        return []

    exposures: list[Exposure] = []
    for name in PRIVATE_KEYS:
        path = pki_dir / name
        try:
            mode = path.stat().st_mode
        except OSError:
            # Absent is not a finding. Not every deployment has every key: the
            # bundle signer and the QR signer are created on first use.
            continue
        if is_exposed(mode):
            exposures.append(Exposure(str(path), mode))
    return exposures


def warn_on_exposed_keys(pki_dir: Path) -> list[Exposure]:
    """Run the audit at startup and say what it found.

    The realistic way a key becomes exposed is not this code — it is a restore, a
    `cp -r` that dropped the mode, an archive unpacked with a default umask, or a
    bind mount from a host directory nobody tightened. None of those announce
    themselves, so something has to look on every start.
    """
    exposures = audit(Path(pki_dir))
    for exposure in exposures:
        logger.error(
            "PRIVATE KEY EXPOSED: %s. Anyone who can read it can impersonate this "
            "server to its devices. Fix with: chmod 600 %s",
            exposure.detail,
            exposure.path,
        )
    if exposures:
        logger.error(
            "%d private key(s) in %s are readable beyond their owner. See "
            "SEC_AUDIT.md S-2.",
            len(exposures),
            pki_dir,
        )
    return exposures
