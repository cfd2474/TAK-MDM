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

"""The agent self-update channel: who is offered which build, and when not.

Weighted towards the refusals. An offer that fails to arrive costs a delayed
update; an offer that arrives at the wrong moment can strand a device with no
remote management and no rollback, because Android will not install a downgrade.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import ComplianceStatus, Device
from app.services import agent_update
from tests.apk_fixtures import build_apk, make_signing_certificate
from tests.conftest import ADMIN_HEADERS

AGENT = "org.takmdm.agent"


# --------------------------------------------------------------------------- #
# The gate, exercised directly — no device, no database
# --------------------------------------------------------------------------- #


def gate(**overrides) -> agent_update.Decision:
    kwargs = {
        "target_version_code": 40,
        "device_version_code": 39,
        "compliance": ComplianceStatus.COMPLIANT,
        "settled": True,
    }
    kwargs.update(overrides)
    return agent_update.decide(**kwargs)


def test_a_newer_build_is_offered_to_a_healthy_settled_device():
    assert gate().offer is True


def test_nothing_is_offered_when_no_build_is_aimed_at_the_fleet():
    assert gate(target_version_code=None).offer is False


def test_the_same_build_is_not_re_offered():
    assert gate(target_version_code=39).offer is False


def test_an_older_build_is_never_offered():
    """Android refuses downgrades, so an offer to go backwards is an offer to
    fail forever."""
    assert gate(target_version_code=38).offer is False


def test_an_agent_too_old_to_report_its_version_code_is_left_alone():
    decision = gate(device_version_code=None)
    assert decision.offer is False
    assert "versionCode" in decision.reason


def test_a_device_failing_to_apply_policy_is_not_updated():
    for status in (ComplianceStatus.DEGRADED, ComplianceStatus.FAILED):
        assert gate(compliance=status).offer is False


def test_an_unsettled_device_waits():
    """The crash-loop guard: a build that manages exactly one check-in per launch
    must not be handed a fresh update on every relaunch."""
    decision = gate(settled=False)
    assert decision.offer is False
    assert "clean check-in" in decision.reason


def test_every_refusal_names_itself():
    for decision in (
        gate(target_version_code=None),
        gate(target_version_code=39),
        gate(device_version_code=None),
        gate(compliance=ComplianceStatus.FAILED),
        gate(settled=False),
    ):
        assert decision.reason and decision.reason != "eligible"


# --------------------------------------------------------------------------- #
# Targeting: candidate vs current
# --------------------------------------------------------------------------- #


def upload_agent(client: TestClient, version_code: int, certificate: bytes) -> None:
    response = client.post(
        "/api/v1/packages",
        files={
            "file": (
                f"agent-{version_code}.apk",
                build_apk(AGENT, version_code, f"0.9.{version_code}", certificate_der=certificate),
                "application/octet-stream",
            )
        },
        data={"label": "ATLAS Agent"},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code in (200, 201), response.text


def device_of(db, serial: str = "R5CN00TAK01") -> Device:
    return db.scalar(select(Device).where(Device.serial_number == serial))


def test_a_candidate_reaches_only_canaries(client: TestClient, db, enrolled):
    enrolled()
    certificate = make_signing_certificate()
    upload_agent(client, 40, certificate)
    upload_agent(client, 41, certificate)

    agent_update.set_candidate(db, 41)
    agent_update._store(db, agent_update.KEY_CURRENT, 40)
    db.commit()

    device = device_of(db)
    device.agent_version_code = 39
    assert agent_update.target_version_code(db, device) == 40

    device.is_agent_canary = True
    assert agent_update.target_version_code(db, device) == 41


def test_a_canary_is_never_dragged_backwards_by_an_older_candidate(client: TestClient, db, enrolled):
    """Withdrawing a bad candidate by pointing it at an older build must not
    become an offer to downgrade the canary that already took the newer one."""
    enrolled()
    agent_update._store(db, agent_update.KEY_CURRENT, 41)
    agent_update.set_candidate(db, 40)
    db.commit()

    device = device_of(db)
    device.is_agent_canary = True
    assert agent_update.target_version_code(db, device) == 41


def test_promotion_moves_the_candidate_to_the_fleet(db):
    agent_update.set_candidate(db, 41)
    db.commit()

    assert agent_update.promote(db) == 41
    assert agent_update.current(db) == 41
    assert agent_update.candidate(db) is None


def test_promoting_nothing_is_a_no_op(db):
    assert agent_update.promote(db) is None
    assert agent_update.current(db) is None


def test_withdrawing_a_candidate_leaves_the_fleet_build_alone(db):
    agent_update._store(db, agent_update.KEY_CURRENT, 40)
    agent_update.set_candidate(db, 41)
    db.commit()

    agent_update.withdraw_candidate(db)
    assert agent_update.candidate(db) is None
    assert agent_update.current(db) == 40


def test_canary_health_counts_only_healthy_canaries_on_the_candidate(client, db, enrolled):
    enrolled(serial="CANARY-A")
    enrolled(serial="CANARY-B")
    enrolled(serial="FLEET-C")

    good = device_of(db, "CANARY-A")
    good.is_agent_canary = True
    good.agent_version_code = 41
    good.compliance_status = ComplianceStatus.COMPLIANT

    bad = device_of(db, "CANARY-B")
    bad.is_agent_canary = True
    bad.agent_version_code = 41
    bad.compliance_status = ComplianceStatus.DEGRADED  # installed, then broke
    db.commit()

    assert agent_update.canary_health(db, 41) == (1, 2)


def test_an_offer_aimed_at_a_build_that_was_never_uploaded_is_dropped(client, db, enrolled):
    enrolled()
    agent_update._store(db, agent_update.KEY_CURRENT, 99)
    db.commit()

    device = device_of(db)
    device.agent_version_code = 39
    assert agent_update.offer_for(db, device, package_name=AGENT, settled=True) is None


# --------------------------------------------------------------------------- #
# End to end, through the check-in the agent actually makes
# --------------------------------------------------------------------------- #


def checkin(client: TestClient, headers: dict, **body) -> dict:
    response = client.post("/api/v1/device/checkin", json=body, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_the_first_checkin_on_a_build_settles_and_the_second_is_offered(
    client: TestClient, db, enrolled, mtls_headers
):
    """The whole crash-loop guard, seen from the wire."""
    session = enrolled()
    headers = mtls_headers(session["certificate_pem"])
    upload_agent(client, 40, make_signing_certificate())
    agent_update._store(db, agent_update.KEY_CURRENT, 40)
    db.commit()

    first = checkin(client, headers, state_version=0, agent_version_code=39)
    assert first["agent_update"] is None  # not yet settled

    second = checkin(client, headers, state_version=first["state_version"], agent_version_code=39)
    assert second["agent_update"]["version_code"] == 40
    assert second["agent_update"]["package_name"] == AGENT
    assert second["agent_update"]["sha256"]
    assert second["agent_update"]["url"].endswith(second["agent_update"]["sha256"])


def test_a_device_reporting_apply_errors_is_not_offered_an_update(
    client: TestClient, db, enrolled, mtls_headers
):
    """The gate reads the compliance this very check-in reported, not the last."""
    session = enrolled()
    headers = mtls_headers(session["certificate_pem"])
    upload_agent(client, 40, make_signing_certificate())
    agent_update._store(db, agent_update.KEY_CURRENT, 40)
    db.commit()

    checkin(client, headers, state_version=0, agent_version_code=39)
    body = checkin(
        client,
        headers,
        state_version=0,
        agent_version_code=39,
        applied_state_version=0,
        apply_errors=["password: minimum length rejected"],
    )
    assert body["agent_update"] is None


def test_arriving_on_the_new_build_ends_the_offers(
    client: TestClient, db, enrolled, mtls_headers
):
    """The success path: no acknowledgement protocol, just a higher versionCode."""
    session = enrolled()
    headers = mtls_headers(session["certificate_pem"])
    upload_agent(client, 40, make_signing_certificate())
    agent_update._store(db, agent_update.KEY_CURRENT, 40)
    db.commit()

    checkin(client, headers, state_version=0, agent_version_code=39)
    assert checkin(client, headers, state_version=0, agent_version_code=39)["agent_update"]

    after = checkin(client, headers, state_version=0, agent_version_code=40)
    assert after["agent_update"] is None
    db.expire_all()
    assert device_of(db).agent_version_code == 40


def test_a_checkin_without_a_version_code_leaves_the_record_untouched(
    client: TestClient, db, enrolled, mtls_headers
):
    session = enrolled()
    headers = mtls_headers(session["certificate_pem"])
    checkin(client, headers, state_version=0, agent_version_code=39)
    checkin(client, headers, state_version=0)  # an older agent, silent on the field

    db.expire_all()
    assert device_of(db).agent_version_code == 39
