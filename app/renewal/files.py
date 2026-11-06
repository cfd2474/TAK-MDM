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

"""What InfraTAK writes for the renewal container (W458).

`<atlas dir>/secrets/renewal/`, mounted read-only at `/run/renewal`. Read on
every request, not at start: InfraTAK rotates the token on each ATLAS update,
and a container that cached it would hold a deleted token until restarted.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DIR = "/run/renewal"

TOKEN = "authentik.token"
URL = "authentik.url"
CA = "tak-ca.pem"
CLIENT_KEY = "client.key"


@dataclass(frozen=True)
class Config:
    authentik_url: str
    authentik_token: str
    tak_ca_pem: str
    client_key: str


class RenewalFiles:
    def __init__(self, directory: str | os.PathLike | None = None) -> None:
        self.directory = Path(directory or os.environ.get("TAKMDM_RENEWAL_DIR") or DEFAULT_DIR)

    def _read(self, name: str) -> str:
        try:
            return (self.directory / name).read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def load(self) -> Config | None:
        """The current files, or None while any of them is missing."""
        config = Config(
            authentik_url=self._read(URL).rstrip("/"),
            authentik_token=self._read(TOKEN),
            tak_ca_pem=self._read(CA),
            client_key=self._read(CLIENT_KEY),
        )
        if not all((config.authentik_url, config.authentik_token,
                    "BEGIN CERTIFICATE" in config.tak_ca_pem, config.client_key)):
            return None
        return config
