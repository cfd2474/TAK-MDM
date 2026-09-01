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

"""Reversible storage for enrollment token secrets.

**This deliberately weakens D21**, which stored token secrets as a one-way hash so a
database dump yielded nothing usable. Re-displaying a past token's QR requires the
server to recover the secret, so one-way storage is no longer possible.

The weakening is bounded on purpose:

* The key lives in ``pki/`` on the filesystem, never in the database, so a database
  dump alone still yields nothing. **Two** things must leak, not one.
* The SHA-256 hash is kept and remains the only thing authentication looks at.
  Enrollment matches an indexed hash; it never decrypts. Ciphertext exists solely
  so an operator can re-display a QR.
* Only enrollment tokens are stored this way. They are already scoped, expiring and
  use-limited — a far smaller blast radius than the device CA key beside them.

The alternative was making operators save secrets elsewhere, which in practice means
they screenshot the QR instead. A photograph of a provisioning payload in someone's
camera roll is worse than ciphertext behind a key file.
"""

from __future__ import annotations

import logging
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


class TokenVault:
    """Encrypts and decrypts enrollment token secrets."""

    def __init__(self, key: bytes):
        self._fernet = Fernet(key)

    @classmethod
    def load_or_create(cls, pki_dir: Path) -> TokenVault:
        key_path = Path(pki_dir) / "token_vault.key"

        if key_path.exists():
            return cls(key_path.read_bytes().strip())

        pki_dir.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        key_path.write_bytes(key)
        key_path.chmod(0o600)
        logger.info("created token vault key at %s", key_path)
        return cls(key)

    def seal(self, secret: str) -> str:
        return self._fernet.encrypt(secret.encode()).decode()

    def open(self, ciphertext: str | None) -> str | None:
        """Recover a secret, or None if it cannot be recovered.

        Returns None rather than raising for the two cases that are expected in
        normal operation: a token created before this existed, and a token sealed
        under a key that has since been replaced. Neither is an error — the caller
        simply cannot offer a QR and should say so.
        """
        if not ciphertext:
            return None
        try:
            return self._fernet.decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            logger.warning("token secret could not be decrypted; key may have changed")
            return None
