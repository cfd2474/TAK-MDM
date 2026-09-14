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

"""How private keys reach the disk, and how an exposed one is noticed (S-2).

⚠️ **None of this solves S-2.** A key the application reads at runtime, on a host
the attacker is assumed to have reached, is readable by that attacker. What is
testable here is narrower: the key is never *briefly* wide, the directory is not
listable, and something looks on every start — because the realistic failure is a
restore or a `cp -r`, and nobody watches a file's mode.

⚠️ **Windows cannot express POSIX modes.** `os.chmod` sets little more than a
read-only flag and `st_mode` reports 0o666 regardless, so the mode assertions are
skipped there and the *rules* are tested as pure functions instead. The
deployment is Linux; a developer workstation is not what these protect.
"""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

import pytest

from app.security import keyfiles

posix_only = pytest.mark.skipif(
    not keyfiles.POSIX_MODES, reason="Windows does not implement POSIX file modes"
)


# --------------------------------------------------------------------------- #
# The rule, testable anywhere
# --------------------------------------------------------------------------- #


def test_owner_only_is_not_exposed():
    assert not keyfiles.is_exposed(0o600)
    assert not keyfiles.is_exposed(0o400)


def test_any_group_or_other_bit_is_exposed():
    """⚠️ Execute and write count, not just read. A key an attacker can *replace*
    is a key they control, which is worse than one they can copy."""
    for mode in (0o640, 0o604, 0o660, 0o644, 0o601, 0o610, 0o666):
        assert keyfiles.is_exposed(mode), oct(mode)


def test_the_message_names_who_can_read_it():
    exposure = keyfiles.Exposure("/pki/ca.key", 0o644)

    assert "/pki/ca.key" in exposure.detail
    assert "others" in exposure.detail

    assert "group" in keyfiles.Exposure("/pki/ca.key", 0o640).detail


# --------------------------------------------------------------------------- #
# Writing
# --------------------------------------------------------------------------- #


@posix_only
def test_a_key_is_never_briefly_world_readable(tmp_path):
    """⚠️ The whole point of `os.open` over write-then-chmod.

    The old pattern left the key at the process umask between the two calls. This
    sets a wide umask first: under write-then-chmod the file would exist as 0666
    for that window, and the mode asserted here would have been reached only
    afterwards.
    """
    previous = os.umask(0o000)
    try:
        path = keyfiles.write_private(tmp_path / "pki" / "ca.key", b"secret")
    finally:
        os.umask(previous)

    assert path.read_bytes() == b"secret"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@posix_only
def test_the_directory_is_not_listable(tmp_path):
    keyfiles.write_private(tmp_path / "pki" / "ca.key", b"secret")

    assert stat.S_IMODE((tmp_path / "pki").stat().st_mode) == 0o700


@posix_only
def test_the_directory_is_created_private_rather_than_tightened_after(
    tmp_path, monkeypatch
):
    """⚠️ The *window*, which the assertion above cannot see.

    `secure_dir` both passes `mode=` to `mkdir` and chmods afterwards, so removing
    either leaves the same end state and the test above still passes — the
    mutation run proved exactly that. Neutralising the chmod is what makes the
    creation mode observable: without `mode=`, the directory is born at the umask
    and listable until the chmod lands.
    """
    monkeypatch.setattr(Path, "chmod", lambda self, mode: None)

    previous = os.umask(0o000)
    try:
        keyfiles.secure_dir(tmp_path / "pki")
    finally:
        os.umask(previous)

    assert stat.S_IMODE((tmp_path / "pki").stat().st_mode) == 0o700


def test_writing_over_an_existing_key_is_refused(tmp_path):
    """⚠️ Silently overwriting a CA key destroys every enrolled device's identity.

    `O_EXCL` makes that impossible to do by accident. A key already present when
    one is being created means something happened that nobody intended, and the
    right response is to stop rather than to proceed.
    """
    path = tmp_path / "pki" / "ca.key"
    keyfiles.write_private(path, b"original")

    with pytest.raises(FileExistsError):
        keyfiles.write_private(path, b"replacement")

    assert path.read_bytes() == b"original"


def test_a_failed_write_leaves_nothing_behind(tmp_path, monkeypatch):
    """A half-written key would be loaded on the next start and fail far from
    here, with a message about the wrong thing entirely."""
    path = tmp_path / "pki" / "ca.key"

    class Unwritable(bytes):
        def __len__(self):  # pragma: no cover - only the write path matters
            raise OSError("disk full")

    real_fdopen = os.fdopen

    def exploding_fdopen(fd, *a, **k):
        handle = real_fdopen(fd, *a, **k)
        original_write = handle.write

        def write(_data):
            original_write(b"partial")
            raise OSError("disk full")

        handle.write = write
        return handle

    monkeypatch.setattr(os, "fdopen", exploding_fdopen)

    with pytest.raises(OSError):
        keyfiles.write_private(path, b"secret")

    assert not path.exists(), "a partial key survived"


# --------------------------------------------------------------------------- #
# Noticing
# --------------------------------------------------------------------------- #


@posix_only
def test_a_widened_key_is_reported(tmp_path, caplog):
    """The realistic failure: a restore or a copy that dropped the mode."""
    keyfiles.write_private(tmp_path / "ca.key", b"secret")
    (tmp_path / "ca.key").chmod(0o644)

    with caplog.at_level(logging.ERROR):
        exposures = keyfiles.warn_on_exposed_keys(tmp_path)

    assert [Path(e.path).name for e in exposures] == ["ca.key"]
    assert "PRIVATE KEY EXPOSED" in caplog.text
    assert "chmod 600" in caplog.text, "the log must carry the remedy"


@posix_only
def test_correct_permissions_report_nothing(tmp_path, caplog):
    """⚠️ An alarm that always fires is one nobody reads."""
    for name in keyfiles.PRIVATE_KEYS:
        keyfiles.write_private(tmp_path / name, b"secret")

    with caplog.at_level(logging.ERROR):
        assert keyfiles.warn_on_exposed_keys(tmp_path) == []

    assert caplog.text == ""


def test_a_missing_key_is_not_a_finding(tmp_path):
    """Not every deployment has every key — the bundle and QR signers are made
    on first use, and reporting their absence as an exposure is noise."""
    assert keyfiles.audit(tmp_path) == []


@posix_only
def test_every_key_the_code_writes_is_one_the_audit_looks_at(tmp_path):
    """⚠️ The audit reporting nothing must not be able to mean it looked at nothing.

    This creates a real deployment's keys through the real constructors, then
    asserts the audit's list covers exactly what appeared on disk. A sixth key
    added later without being registered fails here rather than being silently
    unaudited for the rest of the project's life.
    """
    from app.security.bundle import BundleSigner
    from app.security.ca import CertificateAuthority
    from app.security.csrf import CsrfGuard
    from app.security.enrollment_qr import EnrollmentQrGuard
    from app.security.token_vault import TokenVault

    pki = tmp_path / "pki"
    CertificateAuthority.load_or_create(
        pki, common_name="audit-test", validity_days=825
    )
    TokenVault.load_or_create(pki)
    CsrfGuard.load_or_create(pki)
    EnrollmentQrGuard.load_or_create(pki, ttl_seconds=900)
    BundleSigner.load_or_create(pki)

    on_disk = {p.name for p in pki.glob("*.key")}

    assert on_disk == set(keyfiles.PRIVATE_KEYS), (
        f"on disk but unaudited: {on_disk - set(keyfiles.PRIVATE_KEYS)}; "
        f"audited but never written: {set(keyfiles.PRIVATE_KEYS) - on_disk}"
    )


@posix_only
def test_every_key_a_real_deployment_creates_is_owner_only(tmp_path):
    """End to end, through the constructors rather than the helper."""
    from app.security.bundle import BundleSigner
    from app.security.ca import CertificateAuthority
    from app.security.csrf import CsrfGuard
    from app.security.enrollment_qr import EnrollmentQrGuard
    from app.security.token_vault import TokenVault

    pki = tmp_path / "pki"
    previous = os.umask(0o000)
    try:
        CertificateAuthority.load_or_create(
        pki, common_name="audit-test", validity_days=825
    )
        TokenVault.load_or_create(pki)
        CsrfGuard.load_or_create(pki)
        EnrollmentQrGuard.load_or_create(pki, ttl_seconds=900)
        BundleSigner.load_or_create(pki)
    finally:
        os.umask(previous)

    for key in pki.glob("*.key"):
        assert stat.S_IMODE(key.stat().st_mode) == 0o600, key


def test_nothing_writes_a_private_key_outside_the_helper():
    """⚠️ The guard that keeps this from decaying.

    A sixth key written with `write_bytes` then `chmod` would reintroduce the
    window without failing anything — the tests above only cover the five that
    exist today.
    """
    import re

    offenders = []
    for path in sorted(Path("app").rglob("*.py")):
        if path.name == "keyfiles.py":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#") or "`" in line:
                continue
            if re.search(r"chmod\(0o[67]00\)", line):
                offenders.append(f"{path}:{number}: {stripped}")

    assert not offenders, (
        "these set a private mode after creating the file, which leaves a window "
        "at the process umask. Use keyfiles.write_private:\n" + "\n".join(offenders)
    )
