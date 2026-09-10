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

"""Trusted certificates, SCEP and the global HTTP proxy are gone (W113).

⚠️ **Removing this feature was not the same as never having had it.** A device
trusting a policy-installed CA had to be told to stop, and the only thing that
could tell it was the agent — whose contract is *absent means removed*. So
chunk 1 kept shipping an empty `certificates` list purely to drive that cleanup.

Chunk 2 removed the applier, and with it the last reader, so the key is gone
too. These tests now defend the *end* state and the reason the intermediate one
existed, which is the part a future reader would otherwise have to guess at.
"""

from __future__ import annotations

import pathlib
import uuid

from fastapi.testclient import TestClient

from app.db.models import Assignment, AssignmentScope, Policy, PolicyVersion
from tests.test_checkin import checkin


# --------------------------------------------------------------------------- #
# ⚠️ The cleanup contract
# --------------------------------------------------------------------------- #


def test_the_certificates_key_is_gone(client: TestClient, db, enrolled, mtls_headers):
    """The key outlived the feature by one chunk, on purpose, and is now gone.

    ⚠️ Dropping it is safe in either order, which is why it could wait: an agent
    still carrying `CertificateApplier` reads a missing key as `JSONArray()` —
    `optJSONArray("certificates") ?: JSONArray()` — and an empty array means
    "remove the anchors you installed". So an old agent meeting a new server
    still cleans up rather than holding a stale anchor for ever.
    """
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])

    bundle = checkin(client, headers, force_full=True)["desired_state"]

    assert "certificates" not in bundle


def test_an_orphaned_certificates_policy_does_not_break_resolution(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ Rows for the deleted type outlive the code that understood them.

    The live server still holds `5064a51b` ("W112 trust check"), assigned to a
    device. The resolver skips unknown types on purpose — *"a rolled-back
    deployment: ignore, don't crash"* — and this is the test that says so, since
    the alternative is a tablet whose whole policy resolution fails.
    """
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])

    policy = Policy(name="stale trust check", policy_type="CERTIFICATES")
    db.add(policy)
    db.flush()
    version = PolicyVersion(
        policy_id=policy.id,
        version=1,
        spec={"trusted_ca_file_ids": [str(uuid.uuid4())]},
    )
    db.add(version)
    db.add(
        Assignment(
            policy_id=policy.id,
            scope=AssignmentScope.DEVICE,
            device_id=uuid.UUID(result["device_id"]),
            rank=1,
        )
    )
    db.commit()

    bundle = checkin(client, headers, force_full=True)["desired_state"]

    assert "certificates" not in bundle
    # The point is that a bundle was produced at all: an unknown policy type must
    # not take the device's whole desired state down with it.
    assert "apps" in bundle


# --------------------------------------------------------------------------- #
# The type is gone
# --------------------------------------------------------------------------- #


def test_the_policy_type_is_no_longer_offered(client: TestClient):
    response = client.post(
        "/api/v1/policies",
        json={
            "name": "trust",
            "policy_type": "CERTIFICATES",
            "spec": {"trusted_ca_file_ids": []},
        },
    )

    assert response.status_code == 422, response.text


def test_the_removed_panels_are_not_in_the_creator(client: TestClient):
    body = client.get("/policies/new").text

    for slug in ("trusted-certificates", "scep", "global-http-proxy"):
        assert f'data-page-panel="security:{slug}"' not in body, slug
    assert "trusted_ca_file_ids" not in body


def test_what_is_left_of_security_is_listed_as_unbuilt(client: TestClient):
    """⚠️ Security has no wired policy type any more, so it becomes a placeholder
    like Accounts and Knox rather than a category with panels.

    The first attempt kept `stub_pages`, which render nothing for an unwired
    category — the creator builds panels only for wired ones. Security would have
    silently disappeared, reading as "it was deleted" rather than "it is unbuilt".
    """
    body = client.get("/policies/new").text

    assert "Security" in body
    assert "web content filtering" in body
    assert "os updates" in body

# --------------------------------------------------------------------------- #
# What survives
# --------------------------------------------------------------------------- #


def test_the_credential_restriction_survives_on_its_own_merits(client: TestClient):
    """It blocks the credentials screen — useful without a Certificates policy to
    protect, so it stays. Only its cross-reference to the deleted page goes."""
    from app.policies import form_schema

    field = next(
        f for f in form_schema.form_fields("RESTRICTIONS")
        if f.name == "allow_credential_configuration"
    )

    assert "whole credentials screen" in field.help
    assert "Certificates policy" not in field.help


def test_the_agent_no_longer_carries_the_certificate_code(client: TestClient):
    """Chunk 2: the applier, its plan, and the config that remembered anchor
    bytes are all gone.

    Asserted rather than assumed, because a half-removal is the bad state: an
    agent still sweeping anchors against a key the server no longer sends.
    """
    agent = pathlib.Path("agent/app/src/main/java/com/taksolutions/atlasmdm")

    assert not (agent / "policy/CertificateApplier.kt").exists()
    assert not (agent / "policy/CertificatePlan.kt").exists()

    reconciler = (agent / "sync/Reconciler.kt").read_text(encoding="utf-8")
    assert "CertificateApplier" not in reconciler
    assert "downloadCertificateBytes" not in reconciler

    config = (agent / "core/AgentConfig.kt").read_text(encoding="utf-8")
    for gone in ("caCertsInstalled", "rememberCaCert", "forgetCaCert"):
        assert gone not in config, gone
