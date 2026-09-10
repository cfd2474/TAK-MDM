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

"""The master PIN that unblocks the provisioning permission step (W117).

⚠️ **The load-bearing test here is `test_the_pin_never_reaches_a_device`.** Every
other property — six digits, stable, capped — is a nice-to-have next to the one
design decision this feature rests on: the PIN is checked by the server and
never shipped, because a six-digit secret inside a photographed QR code is not a
secret.
"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.services import bypass_pin, settings_store
from tests.conftest import ADMIN_HEADERS


def _token(client: TestClient) -> str:
    response = client.post(
        "/api/v1/enrollment-tokens",
        json={"name": "bypass test"},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 201, response.text
    return response.json()["secret"]


def _check(client: TestClient, secret: str, pin: str):
    return client.post(
        "/api/v1/provisioning/bypass-pin",
        json={"secret": secret, "pin": pin},
    )


# --------------------------------------------------------------------------- #
# The PIN itself
# --------------------------------------------------------------------------- #


def test_it_is_six_digits(client: TestClient, db):
    pin = bypass_pin.get_or_create(db)

    assert len(pin) == 6
    assert pin.isdigit()


def test_it_is_fixed_once_generated(client: TestClient, db):
    """"Unique to each server install, but will remain fixed on the server."""
    first = bypass_pin.get_or_create(db)
    db.commit()

    assert bypass_pin.get_or_create(db) == first


def test_a_leading_zero_survives(client: TestClient, db):
    """⚠️ Stored and compared as a string. Held as an int, `012345` would come
    back as `12345` and the operator would type a code that cannot match."""
    settings_store.put(db, bypass_pin.KEY, "012345")
    db.commit()

    assert bypass_pin.get_or_create(db) == "012345"


def test_it_is_generated_on_first_read_not_only_at_install(client: TestClient, db):
    """⚠️ The brief said "generated upon install". Done literally, every existing
    deployment would have no PIN for ever, and so a bypass button nobody can
    use. Get-or-create covers the upgrade case as well as the fresh one."""
    assert settings_store.get(db, bypass_pin.KEY) == ""

    pin = bypass_pin.get_or_create(db)
    db.commit()

    assert settings_store.get(db, bypass_pin.KEY) == pin


# --------------------------------------------------------------------------- #
# ⚠️ It must never travel
# --------------------------------------------------------------------------- #


def test_the_pin_never_reaches_a_device(client: TestClient, db, enrolled, mtls_headers):
    """⚠️ The decision the whole feature rests on.

    Six digits is a million candidates, so the PIN inside anything a device
    receives — a QR, the provisioning extras, the desired state — is brute-forced
    the moment that artefact is photographed or pulled off a tablet. It is
    checked server-side precisely so it never has to travel.
    """
    pin = bypass_pin.get_or_create(db)
    db.commit()

    created = client.post(
        "/api/v1/enrollment-tokens",
        json={"name": "leak check"},
        headers=ADMIN_HEADERS,
    ).json()
    result = enrolled()
    headers = mtls_headers(result["certificate_pem"])
    checkin_body = client.post(
        "/api/v1/device/checkin", json={"force_full": True}, headers=headers
    ).text

    for blob in (json.dumps(created), checkin_body):
        assert pin not in blob


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #


def test_the_right_pin_is_accepted(client: TestClient, db):
    secret = _token(client)
    pin = bypass_pin.get_or_create(db)
    db.commit()

    body = _check(client, secret, pin).json()

    assert body["accepted"] is True


def test_a_wrong_pin_is_refused(client: TestClient, db):
    secret = _token(client)
    bypass_pin.get_or_create(db)
    db.commit()

    body = _check(client, secret, "000000" ).json()

    # Either the PIN really is 000000 (1 in a million) or it was refused.
    if bypass_pin.get_or_create(db) != "000000":
        assert body["accepted"] is False


def test_it_cannot_be_asked_without_a_valid_token(client: TestClient, db):
    """⚠️ Without this the endpoint is an open oracle for a six-digit secret."""
    bypass_pin.get_or_create(db)
    db.commit()

    response = _check(client, "not-a-real-token", "123456")

    assert response.status_code == 404


def test_guessing_is_capped_per_token(client: TestClient, db):
    """⚠️ A fixed per-install code gets treated as a master secret whatever the
    admin page says, so the endpoint must not answer indefinitely."""
    secret = _token(client)
    pin = bypass_pin.get_or_create(db)
    db.commit()
    wrong = "111111" if pin != "111111" else "222222"

    last = None
    for _ in range(bypass_pin.MAX_ATTEMPTS):
        last = _check(client, secret, wrong).json()
    assert last["attempts_remaining"] == 0

    # And now even the correct PIN is refused on this token.
    assert _check(client, secret, pin).json()["accepted"] is False


def test_a_success_restores_the_allowance(client: TestClient, db):
    """A fat-fingered code on a real provisioning run must not burn the token
    down for the operator who then types it correctly."""
    secret = _token(client)
    pin = bypass_pin.get_or_create(db)
    db.commit()
    wrong = "111111" if pin != "111111" else "222222"

    _check(client, secret, wrong)
    accepted = _check(client, secret, pin).json()

    assert accepted["accepted"] is True
    assert accepted["attempts_remaining"] == bypass_pin.MAX_ATTEMPTS


def test_the_cap_is_per_token_not_global(client: TestClient, db):
    """⚠️ A global counter would turn a brute-force guard into a denial of
    service: anyone holding one token could lock every other operator out of
    provisioning."""
    victim = _token(client)
    attacker = _token(client)
    pin = bypass_pin.get_or_create(db)
    db.commit()
    wrong = "111111" if pin != "111111" else "222222"

    for _ in range(bypass_pin.MAX_ATTEMPTS):
        _check(client, attacker, wrong)

    assert _check(client, victim, pin).json()["accepted"] is True


# --------------------------------------------------------------------------- #
# The console
# --------------------------------------------------------------------------- #


def test_the_admin_page_shows_it_with_the_operators_note(client: TestClient, db):
    body = client.get("/admin", headers=ADMIN_HEADERS).text

    assert "master bypass code" in body
    assert "skip the permissions step" in body


def test_the_admin_page_says_what_it_does_not_grant(client: TestClient, db):
    """⚠️ A code labelled "master" invites the reader to assume it is a skeleton
    key for the server. It is not, and the page has to say so where the code is
    displayed rather than somewhere else."""
    body = client.get("/admin", headers=ADMIN_HEADERS).text

    assert "grants no access to this server" in body


# --------------------------------------------------------------------------- #
# The agent side (chunk 2)
# --------------------------------------------------------------------------- #


def test_the_agent_asks_the_server_without_a_client_certificate():
    """⚠️ `enrollClient`, not `mtlsClient`.

    The check happens in the setup wizard, before the device has any identity —
    the same position `enroll` is in. Using the mTLS client would fail every
    time on the one screen this exists for.
    """
    import pathlib

    api = pathlib.Path(
        "agent/app/src/main/java/com/taksolutions/atlasmdm/net/ApiClient.kt"
    ).read_text(encoding="utf-8")

    body = api[api.index("fun checkBypassPin("):]
    body = body[: body.index("\n    fun ")]
    assert "enrollClient" in body
    assert "mtlsClient" not in body


def test_the_agent_never_stores_the_pin():
    """⚠️ It is a fixed per-install secret, so a copy in a preference file or a
    log bundle outlives the moment it was needed."""
    import pathlib

    agent = pathlib.Path("agent/app/src/main/java/com/taksolutions/atlasmdm")
    api = (agent / "net/ApiClient.kt").read_text(encoding="utf-8")
    activity = (agent / "admin/PolicyComplianceActivity.kt").read_text(encoding="utf-8")
    config = (agent / "core/AgentConfig.kt").read_text(encoding="utf-8")

    # Never persisted.
    assert "bypassPin" not in config and "bypass_pin" not in config

    # ⚠️ Never *interpolated* into a log line. Asserting the absence of the word
    # "pin" was the first version of this test and it failed immediately on
    # `"bypass PIN check could not be completed"` — a log line that mentions the
    # PIN without containing it. The thing that matters is the value, so this
    # looks for the variable being substituted in, not the topic being named.
    for source in (api, activity):
        for line in source.splitlines():
            if "AgentLog" not in line:
                continue
            assert "$pin" not in line and "${pin}" not in line, line


def test_the_agent_separates_refused_from_unreachable():
    """⚠️ The two look identical if both are reported as failure, and the
    operator can do something about one and not the other."""
    import pathlib

    activity = pathlib.Path(
        "agent/app/src/main/java/com/taksolutions/atlasmdm/admin/"
        "PolicyComplianceActivity.kt"
    ).read_text(encoding="utf-8")

    assert "compliance_override_unreachable" in activity
    assert "compliance_override_wrong" in activity
    assert "compliance_override_locked" in activity


def test_only_an_accepted_answer_lets_setup_continue():
    """⚠️ Anything else — refused, locked out, unreachable, a malformed body —
    must leave the block in place. `finishProvisioning` is reachable from the
    override path exactly once, under `answer.accepted`."""
    import pathlib

    activity = pathlib.Path(
        "agent/app/src/main/java/com/taksolutions/atlasmdm/admin/"
        "PolicyComplianceActivity.kt"
    ).read_text(encoding="utf-8")

    # Bounded to the function. Running to end-of-file also caught
    # `private fun finishProvisioning() {` — its own definition — and counted 2.
    start = activity.index("private fun submitBypassPin(")
    end = activity.index("\n    private fun ", start + 1)
    submit = activity[start:end]

    assert submit.count("finishProvisioning()") == 1
    assert submit.index("answer.accepted") < submit.index("finishProvisioning()")


def test_the_pin_length_matches_the_server():
    """A four-digit box against a six-digit code fails in a way that reads as a
    wrong code rather than a wrong app."""
    import pathlib

    activity = pathlib.Path(
        "agent/app/src/main/java/com/taksolutions/atlasmdm/admin/"
        "PolicyComplianceActivity.kt"
    ).read_text(encoding="utf-8")

    assert f"BYPASS_PIN_LENGTH = {bypass_pin.DIGITS}" in activity
