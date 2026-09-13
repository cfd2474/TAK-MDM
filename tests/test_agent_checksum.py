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

"""The agent's signature checksum comes from the agent build (W143).

⚠️ Android verifies the APK it downloads from this server against the checksum
carried in the provisioning QR. The signing certificate of *that file* is
therefore the only answer that can be right — a configured value is a claim
about it, and the platform reference records two different checksums for two
different keystores, so pasting the wrong one is a live trap rather than a
hypothetical one.

The operator met this on a fresh InfraTAK deployment: nothing uploaded, no
environment variable, and an error naming only the variable.
"""

from __future__ import annotations

import base64
import hashlib

import pytest
from fastapi.testclient import TestClient

from app.services import packages as package_service
from app.services.provisioning import ProvisioningError, resolve_signature_checksum

UPLOADED = "AAAAuploadedAAAAuploadedAAAAuploadedAAAAuploa"
CONFIGURED = "BBBBconfiguredBBBBconfiguredBBBBconfiguredBB"


# --------------------------------------------------------------------------- #
# Which value wins
# --------------------------------------------------------------------------- #


def test_the_uploaded_build_is_used(settings):
    """The APK the device downloads is the one whose signature it checks."""
    assert resolve_signature_checksum(settings, UPLOADED) == UPLOADED


def test_the_setting_still_works_when_nothing_is_uploaded(settings):
    """⚠️ The standalone deployment sets this by hand and must keep working."""
    configured = settings.model_copy(update={"agent_signature_checksum": CONFIGURED})

    assert resolve_signature_checksum(configured, None) == CONFIGURED


def test_disagreement_is_refused_rather_than_resolved(settings):
    """One of the two is wrong. Picking either silently would mean a QR that
    fails on the tablet, or quietly ignoring what an operator set on purpose."""
    configured = settings.model_copy(update={"agent_signature_checksum": CONFIGURED})

    with pytest.raises(ProvisioningError) as raised:
        resolve_signature_checksum(configured, UPLOADED)

    assert UPLOADED in str(raised.value)
    assert CONFIGURED in str(raised.value)


def test_agreement_is_not_a_conflict(settings):
    configured = settings.model_copy(update={"agent_signature_checksum": UPLOADED})

    assert resolve_signature_checksum(configured, UPLOADED) == UPLOADED


def test_neither_available_says_what_to_do(settings):
    """⚠️ The message the operator actually hit. It named an environment
    variable and not the ordinary way out, which is to upload the agent."""
    with pytest.raises(ProvisioningError) as raised:
        resolve_signature_checksum(settings, None)

    assert "Upload a build of the agent app" in str(raised.value)


# --------------------------------------------------------------------------- #
# ⚠️ Derived from the real archive, not from a fixture constant
# --------------------------------------------------------------------------- #


def test_an_uploaded_build_supplies_its_own_checksum(
    client: TestClient, db, artifact_storage, settings
):
    """The whole point: uploading the agent is enough, with nothing configured."""
    from tests.apk_fixtures import build_apk, make_signing_certificate

    certificate = make_signing_certificate("ATLAS Agent")
    response = client.post(
        "/apps/upload",
        data={"label": "ATLAS Agent"},
        files={
            "file": (
                "agent.apk",
                build_apk(settings.agent_package_name, 1, certificate_der=certificate),
                "application/octet-stream",
            )
        },
        follow_redirects=False,
    )
    assert response.status_code in (303, 200), response.text

    facts = package_service.agent_build_facts(
        db, artifact_storage, settings.agent_package_name
    )

    expected = (
        base64.urlsafe_b64encode(hashlib.sha256(certificate).digest())
        .decode()
        .rstrip("=")
    )
    assert facts is not None
    assert facts.signature_checksum == expected
    # And it is enough on its own — this is the fresh-install path.
    assert resolve_signature_checksum(settings, facts.signature_checksum) == expected


def test_nothing_uploaded_is_not_an_error(db, artifact_storage, settings):
    """A caller with nothing to verify against is a normal state, not a failure."""
    assert (
        package_service.agent_build_facts(
            db, artifact_storage, settings.agent_package_name
        )
        is None
    )
