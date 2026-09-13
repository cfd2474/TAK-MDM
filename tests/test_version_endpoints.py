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

"""Passive signals an orchestrator can verify a deploy against (W151).

The contract infra-TAK already uses for its other modules: a `VERSION` file in
the repo root says what a checkout *should* be, and a `/version` endpoint says
what the container *is*. Both, because they can disagree.

⚠️ That disagreement is the reason this exists. `docker compose up -d` without
`--build` keeps the old image — an operational note this project already carries
— so a checkout can read 1.2.2 while the process still serves 1.0.0. Anything
reading only the repo reports success for a deploy that did not happen.
"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient

VERSION_FILE = "VERSION"


def _declared() -> str:
    return io.open(VERSION_FILE, encoding="utf-8").read().strip()


def test_version_reports_the_running_build(client: TestClient):
    body = client.get("/version").json()

    assert body["version"] == _declared()
    assert body["service"] == "atlas-mdm"


def test_version_names_the_service(client: TestClient):
    """⚠️ So a caller can tell it reached ATLAS and not whatever else is
    listening on a port it was handed."""
    assert client.get("/version").json()["service"] == "atlas-mdm"


def test_version_carries_the_revision_too(client: TestClient):
    """A tag can move; a commit cannot. Releases compare `version`, humans
    chasing one build want `revision`."""
    assert client.get("/version").json()["revision"]


def test_health_carries_the_version(client: TestClient):
    body = client.get("/healthz").json()

    assert body["status"] == "ok"
    assert body["version"] == _declared()


def test_both_are_reachable_without_signing_in(client: TestClient):
    """⚠️ The orchestrator runs beside the container, not through the console's
    login. An endpoint it cannot reach is no use for verifying anything."""
    for path in ("/version", "/healthz"):
        assert client.get(path).status_code == 200, path


def test_the_endpoints_agree_with_each_other(client: TestClient):
    assert client.get("/version").json()["version"] == client.get("/healthz").json()["version"]
