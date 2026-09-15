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

"""A setting only exists if `docker-compose.yml` names it.

⚠️ **This file exists because the same mistake was made twice.**
`docker-compose.yml` has no `env_file`, so a variable in `.env` reaches the
container only where compose names it explicitly. The first time, provisioning
went on pinning a CA it should not have. The second time, `TAKMDM_TRUSTED_PROXIES`
was written correctly into `.env` by the InfraTAK module, and the application
logged *"is not set"* for a release — so the mitigation for `SEC_AUDIT.md` **S-1**
shipped and did nothing.

A warning comment was added after the first occurrence. It was read during the
second and did not prevent it. **A comment is not a control.**
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

COMPOSE = Path("docker-compose.yml")

#: Settings that must reach the container, because something outside the image
#: sets them and a default cannot stand in.
#:
#: ⚠️ Add to this list whenever the InfraTAK module starts writing a new
#: `TAKMDM_*` into `.env`. The module and this file live in different
#: repositories, so nothing else connects the two.
MUST_BE_PASSED = (
    "TAKMDM_DATABASE_URL",
    "TAKMDM_SERVER_URL",
    "TAKMDM_ADMIN_AUTH_MODE",
    "TAKMDM_CONSOLE_ORIGIN",
    # SEC_AUDIT S-1. Written by the module; inert until compose named it.
    "TAKMDM_TRUSTED_PROXIES",
)


def _api_environment() -> dict[str, str]:
    """The `environment:` block of the `api` service, as a dict.

    Parsed rather than loaded with PyYAML: the project has no YAML dependency and
    adding one to read a dozen lines would be the wrong trade.
    """
    lines = io.open(COMPOSE, encoding="utf-8").read().splitlines()
    out: dict[str, str] = {}
    in_api = in_env = False
    for line in lines:
        if re.match(r"^  [a-z]", line):
            in_api = line.strip().startswith("api:")
            in_env = False
            continue
        if in_api and re.match(r"^    [a-z_]+:", line):
            in_env = line.strip().startswith("environment:")
            continue
        if in_api and in_env:
            match = re.match(r"^      ([A-Z0-9_]+):\s*(.*)$", line)
            if match:
                out[match.group(1)] = match.group(2).strip()
    return out


def test_the_api_service_environment_parses():
    """If this breaks, every assertion below is vacuously true."""
    environment = _api_environment()

    assert len(environment) > 5, environment
    assert "TAKMDM_PKI_DIR" in environment


@pytest.mark.parametrize("name", MUST_BE_PASSED)
def test_a_deployment_setting_reaches_the_container(name):
    """⚠️ In `.env` is not in the container.

    The failure this prevents is silent and total: the value is correct in every
    file an operator would look at, and the application never sees it.
    """
    assert name in _api_environment(), (
        f"{name} is not named in docker-compose.yml's api environment, so a value "
        f"in .env never reaches the application. See the comment beside "
        f"TAKMDM_INCLUDE_SERVER_CA."
    )


def test_every_passed_variable_is_a_real_setting():
    """A typo in compose is a variable that silently does nothing.

    ⚠️ The same class of failure from the other direction: `TAKMDM_TRUSTED_PROXY`
    would be accepted by compose, ignored by pydantic-settings, and look correct
    in a `docker compose config`.
    """
    from app.config import Settings

    known = {f"TAKMDM_{name.upper()}" for name in Settings.model_fields}
    # Not every variable maps to a Settings field — some are read by the
    # entrypoint or by other services.
    entrypoint_only = {
        "TAKMDM_SKIP_DB_WAIT",
        "TAKMDM_SKIP_MIGRATIONS",
        "TAKMDM_SKIP_SEED",
        "TAKMDM_SEED_DIR",
        "TAKMDM_DB_PASSWORD",
        "TAKMDM_LAN_ADDRESS",
    }

    unknown = [
        name
        for name in _api_environment()
        if name.startswith("TAKMDM_") and name not in known and name not in entrypoint_only
    ]

    assert not unknown, (
        "these are passed to the container but match no Settings field, so they "
        f"are ignored: {unknown}"
    )
