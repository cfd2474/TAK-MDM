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

"""What the device itself trusts (W112).

⚠️ **Trust is the one setting where a stale value is a security hole**, not an
untidy one. Most of what is tested here is that the set the device ends up with is
exactly the set the policy names — and that removal takes away what ATLAS
installed and nothing else.
"""

from __future__ import annotations

import pathlib
import uuid

from sqlalchemy import select

from fastapi.testclient import TestClient

from app.db.models import Device, ManagedFile
from tests.conftest import ADMIN_HEADERS
from tests.test_checkin import checkin


def _upload_ca(client: TestClient, name: str = "Corp Root CA") -> str:
    """A file standing in for a certificate. The server stores opaque bytes."""
    response = client.post(
        "/api/v1/files",
        files={"file": (f"{name}.crt", b"-----BEGIN CERTIFICATE-----\nMIIB\n", "application/x-x509-ca-cert")},
        data={"name": name},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["id"]


def _policy(client: TestClient, file_ids: list[str], name: str = "trust"):
    return client.post(
        "/api/v1/policies",
        json={
            "name": name,
            "policy_type": "CERTIFICATES",
            "spec": {"trusted_ca_file_ids": file_ids},
        },
    )


def _assign(client: TestClient, policy_id: str, device_id: str) -> None:
    client.post(
        "/api/v1/assignments",
        json={
            "policy_id": policy_id,
            "scope": "device",
            "target_id": device_id,
            "rank": 1,
        },
    )


# --------------------------------------------------------------------------- #
# Reaching the device
# --------------------------------------------------------------------------- #


def test_a_trusted_ca_reaches_the_device(client: TestClient, db, enrolled, mtls_headers):
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    file_id = _upload_ca(client)
    policy = _policy(client, [file_id])
    assert policy.status_code == 201, policy.text
    _assign(client, policy.json()["id"], result["device_id"])

    bundle = checkin(client, headers, force_full=True)["desired_state"]

    anchors = bundle["certificates"]
    assert len(anchors) == 1
    assert anchors[0]["available"] is True
    assert anchors[0]["name"] == "Corp Root CA"


def test_the_anchor_travels_as_a_hash_not_as_bytes(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ The integrity story for a trust anchor.

    The bundle is signed and carries the sha256; the artifact store is keyed by
    it and the agent's download verifies it. So the certificate cannot be swapped
    in transit without breaking either the signature or the hash — which matters
    more here than for any other file, because these bytes decide what the device
    will trust.
    """
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    file_id = _upload_ca(client)
    _assign(client, _policy(client, [file_id]).json()["id"], result["device_id"])

    anchor = checkin(client, headers, force_full=True)["desired_state"]["certificates"][0]

    assert len(anchor["sha256"]) == 64
    assert anchor["url"] == f"/api/v1/device/artifacts/{anchor['sha256']}"
    assert "bytes" not in anchor and "content" not in anchor


def test_a_deleted_file_travels_as_unavailable_rather_than_vanishing(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ A broken policy has to look broken, not empty.

    Dropped silently, an operator would see a policy naming one authority and a
    device trusting none, with nothing connecting the two.
    """
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    file_id = _upload_ca(client)
    _assign(client, _policy(client, [file_id]).json()["id"], result["device_id"])

    managed = db.scalar(select(ManagedFile).where(ManagedFile.id == uuid.UUID(file_id)))
    db.delete(managed)
    db.commit()

    anchors = checkin(client, headers, force_full=True)["desired_state"]["certificates"]

    assert len(anchors) == 1
    assert anchors[0]["available"] is False


def test_two_policies_union_their_anchors(client: TestClient, db, enrolled, mtls_headers):
    """Stacked policies add trust rather than one replacing the other — a device
    in two groups needs both authorities, not the higher-ranked one's."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    first = _upload_ca(client, "Root A")
    second = _upload_ca(client, "Root B")

    _assign(client, _policy(client, [first], "trust-a").json()["id"], result["device_id"])
    _assign(client, _policy(client, [second], "trust-b").json()["id"], result["device_id"])

    anchors = checkin(client, headers, force_full=True)["desired_state"]["certificates"]

    assert {a["name"] for a in anchors} == {"Root A", "Root B"}


def test_no_policy_means_an_empty_list_not_a_missing_key(
    client: TestClient, db, enrolled, mtls_headers
):
    """⚠️ The agent has to be *told* to trust nothing, so it can remove what it
    installed. A missing key would read as "no instruction" and leave a revoked
    authority in place."""
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])

    bundle = checkin(client, headers, force_full=True)["desired_state"]

    assert bundle["certificates"] == []


# --------------------------------------------------------------------------- #
# The console
# --------------------------------------------------------------------------- #


def test_the_security_category_is_wired(client: TestClient):
    body = client.get("/policies/new").text

    assert 'data-page-panel="security:trusted-certificates"' in body
    assert "trusted_ca_file_ids" in body


def test_the_working_page_comes_before_the_scoped_stubs(client: TestClient):
    """The W106 lesson: stubs sort first by default, which would bury the one
    sub-topic that does something."""
    body = client.get("/policies/new").text

    real = body.index('data-page-panel="security:trusted-certificates"')
    for slug in ("scep", "global-http-proxy", "web-content-filtering", "os-updates"):
        assert real < body.index(f'data-page-panel="security:{slug}"'), slug


def test_the_console_says_this_is_not_what_configures_atak(client: TestClient):
    """⚠️ The mistake this category invites.

    An operator installing their TAK server CA here and expecting ATAK to trust
    it gets a device that looks configured and an ATAK that cannot connect, with
    nothing anywhere saying why.
    """
    body = client.get("/policies/new").text
    panel = body[body.index('data-page-panel="security:trusted-certificates"'):]
    panel = panel[: panel.index("</section>")]

    assert "not what configures ATAK" in panel
    assert "/sdcard/atak/" in panel


def test_the_picker_does_not_ask_where_to_put_a_certificate(client: TestClient):
    """It is not a file push. `file_list` would ask for a destination path, and
    there is no correct answer to that question for a trust anchor."""
    body = client.get("/policies/new").text
    panel = body[body.index('data-page-panel="security:trusted-certificates"'):]
    panel = panel[: panel.index("</section>")]

    assert "dest_path" not in panel
    assert "extract" not in panel


# --------------------------------------------------------------------------- #
# ⚠️ Removal
# --------------------------------------------------------------------------- #


def test_the_agent_removes_only_what_it_installed(client: TestClient):
    """⚠️ `uninstallAllUserCaCerts` is the convenient call and the wrong one: it
    removes every user-installed anchor, including ones a person added for their
    own reasons."""
    applier = pathlib.Path(
        "agent/app/src/main/java/com/taksolutions/atlasmdm/policy/CertificateApplier.kt"
    ).read_text(encoding="utf-8")

    assert "uninstallAllUserCaCerts" not in applier.split("*/")[-1], (
        "the sweeping call must not be used, only named in the warning"
    )
    assert "caCertsInstalled" in applier
    assert "uninstallCaCert" in applier


def test_the_bytes_are_kept_because_removal_names_a_certificate_by_content(
    client: TestClient,
):
    """⚠️ `uninstallCaCert` takes the certificate itself, not an alias. Without the
    original bytes there is no way to remove one specific anchor — only the API
    that removes everybody's."""
    config = pathlib.Path(
        "agent/app/src/main/java/com/taksolutions/atlasmdm/core/AgentConfig.kt"
    ).read_text(encoding="utf-8")

    assert "rememberCaCert" in config
    assert "rememberedCaCert" in config
    assert "forgetCaCert" in config


def test_the_applier_runs_even_with_no_certificates_section(client: TestClient):
    """⚠️ Absent must mean *removed*. Run only when a section exists, a policy
    that stopped applying would leave the device trusting a revoked CA."""
    reconciler = pathlib.Path(
        "agent/app/src/main/java/com/taksolutions/atlasmdm/sync/Reconciler.kt"
    ).read_text(encoding="utf-8")

    assert 'CertificateApplier(context, ::downloadCertificateBytes)' in reconciler
    assert 'optJSONArray("certificates") ?: JSONArray()' in reconciler


# --------------------------------------------------------------------------- #
# ⚠️ What the hardware taught (SM-X828U, 2026-09-09)
# --------------------------------------------------------------------------- #


def test_a_user_removed_anchor_is_put_back(client: TestClient):
    """⚠️ A user *can* delete a policy-installed CA from Settings — observed on
    hardware, along with a "CA cert installed" notification.

    The first version skipped anything in its own `installedByUs` record, so a
    deleted anchor would never have come back: ATLAS believing trust was in place
    while the device had dropped it, and the policy silently not holding. The
    device is asked instead of the record.
    """
    applier = pathlib.Path(
        "agent/app/src/main/java/com/taksolutions/atlasmdm/policy/CertificateApplier.kt"
    ).read_text(encoding="utf-8")

    body = applier[applier.index("fun apply("):]
    assert "hasCaCertInstalled" in body
    assert "restoring" in body


def test_the_console_does_not_claim_trust_is_enforced(client: TestClient):
    """⚠️ It is maintained, not enforced. An operator told otherwise would believe
    a device trusts an authority during a window when it does not."""
    body = client.get("/policies/new").text
    panel = body[body.index('data-page-panel="security:trusted-certificates"'):]
    panel = panel[: panel.index("</section>")]

    assert "A user can delete these from the device" in panel
    assert "maintained rather than enforced" in panel


def test_denying_credential_configuration_is_offered(client: TestClient):
    """⚠️ The answer to "can a user delete these" is a user restriction, not Knox.

    `DISALLOW_CONFIG_CREDENTIALS` blocks the credentials screen outright. Without
    it ATLAS only *restores* a deleted anchor at the next check-in, which narrows
    the window rather than closing it.
    """
    from app.policies import form_schema

    names = [f.name for f in form_schema.form_fields("RESTRICTIONS")]
    assert "allow_credential_configuration" in names


def test_the_certificates_page_points_at_that_restriction(client: TestClient):
    """An operator asking "can I stop them deleting it" is looking at Certificates,
    and the answer lives under Restrictions."""
    body = client.get("/policies/new").text
    panel = body[body.index('data-page-panel="security:trusted-certificates"'):]
    panel = panel[: panel.index("</section>")]

    assert "Credential configuration" in panel


def test_the_restriction_says_it_is_broader_than_our_certificates(client: TestClient):
    """⚠️ It is not "lock this CA" — it blocks the whole credentials screen, so the
    user cannot manage their own certificates either. An operator who reads it as
    the narrow thing will be surprised by a support call."""
    from app.policies import form_schema

    field = next(
        f for f in form_schema.form_fields("RESTRICTIONS")
        if f.name == "allow_credential_configuration"
    )

    assert "their own certificates" in field.help
    assert "whole credentials screen" in field.help
