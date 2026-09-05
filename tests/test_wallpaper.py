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

"""The WALLPAPER policy: two slots, and the device picking between them.

The server deliberately does **not** choose (D46). It sends whichever slots are
filled and the agent decides from its own `smallestScreenWidthDp` — so most of
what is worth testing here is that both slots travel intact, that a missing file
is reported rather than dropped, and that replacing an image actually moves the
fleet.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.policies import form_parse
from app.policies.registry import PolicyTypeError, registry
from tests.conftest import ADMIN_HEADERS

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


# --------------------------------------------------------------------------- #
# The spec
# --------------------------------------------------------------------------- #


def test_a_policy_with_no_image_is_refused():
    """Accepting it would give an operator a policy that assigns cleanly, changes
    nothing, and is indistinguishable from one that failed."""
    try:
        registry.validate_spec("WALLPAPER", {})
    except PolicyTypeError as exc:
        assert "at least one image" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an empty wallpaper policy should not validate")


def test_either_slot_alone_is_enough():
    for slot in ("tablet_file_id", "phone_file_id"):
        spec = registry.validate_spec("WALLPAPER", {slot: str(uuid.uuid4())})
        assert slot in spec


def test_both_slots_survive_together():
    tablet, phone = str(uuid.uuid4()), str(uuid.uuid4())
    spec = registry.validate_spec(
        "WALLPAPER", {"tablet_file_id": tablet, "phone_file_id": phone}
    )
    assert spec["tablet_file_id"] == tablet
    assert spec["phone_file_id"] == phone


def test_an_empty_slot_stays_unset_rather_than_null():
    """`to_stored` uses exclude_unset, so an absent field must not contribute to a
    merge. Writing null would make an empty slot beat a lower-ranked policy's image."""
    from starlette.datastructures import FormData

    parsed = form_parse.parse_form(
        "WALLPAPER",
        FormData([("tablet_file_id", str(uuid.uuid4())), ("phone_file_id", "")]),
    )
    assert "phone_file_id" not in parsed


# --------------------------------------------------------------------------- #
# Resolution — both slots travel, the device chooses
# --------------------------------------------------------------------------- #


def resolve(db, values: dict) -> dict:
    from app.services import files

    return files.resolve_wallpaper(db, values)


def test_nothing_resolves_when_no_policy_sets_a_wallpaper(db):
    assert resolve(db, {}) == {}


def test_a_missing_file_is_reported_not_dropped(db):
    """A slot pointing at a deleted upload has to look broken. Dropping it would
    read as "no wallpaper configured", which is a different and wrong story."""
    resolved = resolve(db, {"WALLPAPER": {"tablet_file_id": str(uuid.uuid4())}})

    assert resolved["tablet"]["available"] is False
    assert "sha256" not in resolved["tablet"]


def test_flags_travel_with_the_slots(db):
    resolved = resolve(
        db,
        {
            "WALLPAPER": {
                "phone_file_id": str(uuid.uuid4()),
                "lock_screen": True,
                "prevent_user_change": False,
            }
        },
    )
    assert resolved["lock_screen"] is True
    assert resolved["prevent_user_change"] is False


def test_flags_left_unset_do_not_appear(db):
    resolved = resolve(db, {"WALLPAPER": {"phone_file_id": str(uuid.uuid4())}})

    assert "lock_screen" not in resolved
    assert "prevent_user_change" not in resolved


def test_a_malformed_id_is_ignored_rather_than_raising(db):
    assert resolve(db, {"WALLPAPER": {"tablet_file_id": "not-a-uuid"}}) == {}


# --------------------------------------------------------------------------- #
# The console
# --------------------------------------------------------------------------- #


def test_the_creator_offers_wallpaper_as_a_real_section(client: TestClient):
    """It used to be a subtopic of a placeholder. Listing it in both places would
    offer the same thing twice, once working and once inert."""
    body = client.get("/policies/new", headers=ADMIN_HEADERS).text

    assert "Wallpaper" in body
    configurations = body[body.find("Configurations"):][:400]
    assert "wallpaper" not in configurations.lower()


def test_the_form_offers_both_slots_and_a_preview(client: TestClient):
    body = client.get("/policies/new/single?type=WALLPAPER", headers=ADMIN_HEADERS).text

    assert "tablet_file_id" in body
    assert "phone_file_id" in body
    assert "data-image-preview" in body
    # Both orientations, which is what was asked for.
    assert "portrait" in body and "landscape" in body


def test_serving_an_unknown_file_is_a_404_not_a_stack_trace(client: TestClient):
    response = client.get(f"/content/{uuid.uuid4()}/raw", headers=ADMIN_HEADERS)
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# It has to reach the device
# --------------------------------------------------------------------------- #


def test_the_wallpaper_reaches_the_signed_bundle(client: TestClient, enrolled, mtls_headers):
    """The gap that shipped: resolution worked, the payload carried it, and the
    bundle did not — `desired_state.build` enumerates its keys explicitly, so a new
    section is invisible until it is named there. Every other test passed while the
    device was never told."""
    session = enrolled()
    headers = mtls_headers(session["certificate_pem"])

    # force_full, because a device already at the current state_version is sent
    # no bundle at all and the assertion would pass vacuously on None.
    body = client.post(
        "/api/v1/device/checkin",
        json={"state_version": 0, "force_full": True},
        headers=headers,
    ).json()

    assert "wallpaper" in body["desired_state"]


def test_an_assigned_wallpaper_travels_with_both_slots(
    client: TestClient, db, enrolled, mtls_headers, make_policy, assign
):
    from app.db.models import Artifact, ManagedFile

    db.add(Artifact(sha256="ab" * 32, size_bytes=10, media_type="image/png"))
    images = {}
    for slot in ("tablet", "phone"):
        managed = ManagedFile(
            name=f"{slot}-image",
            original_filename=f"{slot}.png",
            media_type="image/png",
            artifact_sha256="ab" * 32,
        )
        db.add(managed)
        db.flush()
        images[slot] = str(managed.id)
    db.commit()

    session = enrolled()
    policy = make_policy("Wall", "WALLPAPER", {
        "tablet_file_id": images["tablet"],
        "phone_file_id": images["phone"],
    })
    assign(policy["id"], session["device_id"])
    db.commit()

    body = client.post(
        "/api/v1/device/checkin",
        json={"state_version": 0},
        headers=mtls_headers(session["certificate_pem"]),
    ).json()

    wallpaper = body["desired_state"]["wallpaper"]
    # Both slots travel; the device picks. The server never chooses (D46).
    assert wallpaper["tablet"]["available"] is True
    assert wallpaper["phone"]["available"] is True
    assert wallpaper["tablet"]["sha256"] == "ab" * 32
    assert wallpaper["tablet"]["url"].endswith("ab" * 32)


def test_the_enrollment_page_prompts_for_a_network_name(client: TestClient):
    """"TAK-Field" read as a value to keep rather than an example of one.

    The field only renders once a primary token exists, so the token has to be
    minted first — asserting against the tokenless page would pass vacuously.
    """
    client.post(
        "/enrollment/primary", data={"name": "T"}, headers=ADMIN_HEADERS,
        follow_redirects=False,
    )
    body = client.get("/enrollment", headers=ADMIN_HEADERS).text

    assert 'name="wifi_ssid"' in body, "the SSID field should be on the page"
    assert 'placeholder="Enter Network Name"' in body
    assert "TAK-Field" not in body
