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

"""Managed files, the marketplace tier, bulk assignment, and live propagation.

Covers operator requirements F2-F5.
"""

from __future__ import annotations

import io
import threading
import time
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.policies.specs.files import FileEntry
from app.services import notifications


def make_zip(entries: dict[str, bytes] | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in (entries or {"readme.txt": b"hello"}).items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def upload_file(client: TestClient, data: bytes, filename: str, **form) -> dict:
    response = client.post(
        "/api/v1/files",
        files={"file": (filename, data, "application/octet-stream")},
        data=form,
    )
    assert response.status_code == 201, response.text
    return response.json()


def files_policy(client: TestClient, name: str, entries: list[dict]) -> dict:
    response = client.post(
        "/api/v1/policies",
        json={"name": name, "policy_type": "FILES", "spec": {"entries": entries}},
    )
    assert response.status_code == 201, response.text
    return response.json()


def desired_state(client: TestClient, device_id: str) -> dict:
    return client.get(f"/api/v1/devices/{device_id}/desired-state").json()["desired_state"]


# --------------------------------------------------------------------------- #
# File catalog
# --------------------------------------------------------------------------- #


def test_upload_detects_an_archive(client: TestClient):
    body = upload_file(client, make_zip(), "atak-data.zip", name="ATAK Data Package")

    assert body["is_archive"] is True
    assert body["name"] == "ATAK Data Package"
    assert len(body["artifact_sha256"]) == 64


def test_upload_of_a_plain_file_is_not_an_archive(client: TestClient):
    body = upload_file(client, b"key=value\n", "atak.pref")

    assert body["is_archive"] is False
    assert body["name"] == "atak.pref"


def test_empty_upload_is_rejected(client: TestClient):
    response = client.post(
        "/api/v1/files", files={"file": ("empty.txt", b"", "application/octet-stream")}
    )
    assert response.status_code == 422


def test_deleting_a_file_reclaims_its_artifact(client: TestClient, artifact_storage):
    body = upload_file(client, b"some bytes", "thing.bin")
    digest = body["artifact_sha256"]
    assert artifact_storage.exists(digest)

    client.delete(f"/api/v1/files/{body['id']}")

    assert artifact_storage.exists(digest) is False


# --------------------------------------------------------------------------- #
# FILES policy spec (F5)
# --------------------------------------------------------------------------- #


def test_extract_defaults_its_destination():
    """Repeating the path twice invites a mismatch, so it defaults."""
    entry = FileEntry(file_id=uuid.uuid4(), dest_path="/sdcard/atak", extract=True)

    assert entry.extract_to == "/sdcard/atak"


def test_extract_to_without_extract_is_rejected():
    with pytest.raises(ValueError, match="extract_to is set"):
        FileEntry(
            file_id=uuid.uuid4(), dest_path="/sdcard/atak", extract_to="/sdcard/other"
        )


def test_path_traversal_is_rejected():
    with pytest.raises(ValueError, match=r"\.\."):
        FileEntry(file_id=uuid.uuid4(), dest_path="/sdcard/../../data/data/other")


def test_traversal_check_handles_windows_separators():
    with pytest.raises(ValueError, match=r"\.\."):
        FileEntry(file_id=uuid.uuid4(), dest_path=r"\sdcard\..\..\secret")


def test_legitimate_dotted_directory_is_allowed():
    """Only a '..' path segment is a traversal; a dot in a name is fine."""
    entry = FileEntry(file_id=uuid.uuid4(), dest_path="/sdcard/atak/prefs.v2")

    assert entry.dest_path == "/sdcard/atak/prefs.v2"


# --------------------------------------------------------------------------- #
# Resolution into desired state
# --------------------------------------------------------------------------- #


def test_required_file_resolves_with_extraction_instructions(
    client: TestClient, enrolled, assign
):
    device = enrolled()
    managed = upload_file(client, make_zip(), "data.zip", name="ATAK Data")
    policy = files_policy(
        client,
        "ATAK Data",
        [
            {
                "file_id": managed["id"],
                "dest_path": "/sdcard/atak",
                "extract": True,
                "availability": "required",
            }
        ],
    )
    assign(policy["id"], device["device_id"], rank=1)

    entry = desired_state(client, device["device_id"])["files"]["required"][0]

    assert entry["extract"] is True
    assert entry["extract_to"] == "/sdcard/atak"
    assert entry["sha256"] == managed["artifact_sha256"]
    assert entry["url"].startswith("/api/v1/device/artifacts/")
    assert entry["size_bytes"] > 0


def test_optional_file_lands_in_the_available_catalogue(
    client: TestClient, enrolled, assign
):
    """F4: the server offers it; the user decides."""
    device = enrolled()
    managed = upload_file(client, make_zip(), "maps.zip", name="Offline Maps")
    policy = files_policy(
        client,
        "Optional Maps",
        [
            {
                "file_id": managed["id"],
                "dest_path": "/sdcard/atak/maps",
                "availability": "optional",
                "title": "Regional Map Pack",
                "description": "Large. Install only if you need offline coverage.",
            }
        ],
    )
    assign(policy["id"], device["device_id"], rank=1)

    files = desired_state(client, device["device_id"])["files"]

    assert files["required"] == []
    assert len(files["available"]) == 1
    assert files["available"][0]["title"] == "Regional Map Pack"
    assert "offline coverage" in files["available"][0]["description"]


def test_required_and_optional_are_kept_separate(client: TestClient, enrolled, assign):
    device = enrolled()
    must = upload_file(client, b"cert", "server.p12", name="Server Cert")
    maybe = upload_file(client, make_zip(), "maps.zip", name="Maps")
    policy = files_policy(
        client,
        "Mixed",
        [
            {"file_id": must["id"], "dest_path": "/sdcard/atak/cert"},
            {
                "file_id": maybe["id"],
                "dest_path": "/sdcard/atak/maps",
                "availability": "optional",
            },
        ],
    )
    assign(policy["id"], device["device_id"], rank=1)

    files = desired_state(client, device["device_id"])["files"]

    assert [f["name"] for f in files["required"]] == ["Server Cert"]
    assert [f["name"] for f in files["available"]] == ["Maps"]


def test_deleted_file_is_reported_not_dropped(client: TestClient, enrolled, assign):
    """A broken policy should be visible, not silently do nothing."""
    device = enrolled()
    managed = upload_file(client, b"payload", "thing.bin")
    policy = files_policy(
        client, "Refers", [{"file_id": managed["id"], "dest_path": "/sdcard/x"}]
    )
    assign(policy["id"], device["device_id"], rank=1)
    assert desired_state(client, device["device_id"])["files"]["required"][0]["available"]

    client.delete(f"/api/v1/files/{managed['id']}")

    entry = desired_state(client, device["device_id"])["files"]["required"][0]
    assert entry["available"] is False


def test_stacked_files_policies_union_by_file(client: TestClient, enrolled, assign):
    device = enrolled()
    first = upload_file(client, b"one", "one.bin", name="One")
    second = upload_file(client, b"two", "two.bin", name="Two")
    a = files_policy(client, "Base", [{"file_id": first["id"], "dest_path": "/sdcard/a"}])
    b = files_policy(client, "Extra", [{"file_id": second["id"], "dest_path": "/sdcard/b"}])

    assign(a["id"], device["device_id"], rank=10)
    assign(b["id"], device["device_id"], rank=20)

    names = {f["name"] for f in desired_state(client, device["device_id"])["files"]["required"]}
    assert names == {"One", "Two"}


def test_higher_ranked_policy_wins_a_destination_collision(
    client: TestClient, enrolled, assign
):
    device = enrolled()
    managed = upload_file(client, b"payload", "thing.bin", name="Thing")
    low = files_policy(
        client, "Low", [{"file_id": managed["id"], "dest_path": "/sdcard/low"}]
    )
    high = files_policy(
        client, "High", [{"file_id": managed["id"], "dest_path": "/sdcard/high"}]
    )

    assign(low["id"], device["device_id"], rank=1)
    assign(high["id"], device["device_id"], rank=99)

    entries = desired_state(client, device["device_id"])["files"]["required"]
    assert len(entries) == 1
    assert entries[0]["dest_path"] == "/sdcard/high"


# --------------------------------------------------------------------------- #
# User selections (F4)
# --------------------------------------------------------------------------- #


def test_device_reports_which_optional_files_it_applied(
    client: TestClient, enrolled, assign, mtls_headers
):
    device = enrolled()
    managed = upload_file(client, make_zip(), "maps.zip", name="Maps")
    policy = files_policy(
        client,
        "Optional",
        [
            {
                "file_id": managed["id"],
                "dest_path": "/sdcard/atak/maps",
                "availability": "optional",
            }
        ],
    )
    assign(policy["id"], device["device_id"], rank=1)

    client.post(
        "/api/v1/device/checkin",
        json={"applied_optional_files": [managed["id"]]},
        headers=mtls_headers(device["certificate_pem"]),
    )

    selections = client.get(
        f"/api/v1/devices/{device['device_id']}/file-selections"
    ).json()
    assert [s["file_id"] for s in selections] == [managed["id"]]
    assert selections[0]["name"] == "Maps"


def test_removing_a_selection_clears_the_record(
    client: TestClient, enrolled, mtls_headers
):
    """The device's report is authoritative — a stale record would misinform."""
    device = enrolled()
    managed = upload_file(client, make_zip(), "maps.zip", name="Maps")
    headers = mtls_headers(device["certificate_pem"])

    client.post(
        "/api/v1/device/checkin",
        json={"applied_optional_files": [managed["id"]]},
        headers=headers,
    )
    client.post(
        "/api/v1/device/checkin", json={"applied_optional_files": []}, headers=headers
    )

    assert client.get(f"/api/v1/devices/{device['device_id']}/file-selections").json() == []


def test_omitting_the_field_leaves_selections_untouched(
    client: TestClient, enrolled, mtls_headers
):
    device = enrolled()
    managed = upload_file(client, make_zip(), "maps.zip", name="Maps")
    headers = mtls_headers(device["certificate_pem"])

    client.post(
        "/api/v1/device/checkin",
        json={"applied_optional_files": [managed["id"]]},
        headers=headers,
    )
    client.post("/api/v1/device/checkin", json={}, headers=headers)

    assert len(client.get(f"/api/v1/devices/{device['device_id']}/file-selections").json()) == 1


def test_selection_of_an_unknown_file_is_ignored(
    client: TestClient, enrolled, mtls_headers
):
    device = enrolled()

    response = client.post(
        "/api/v1/device/checkin",
        json={"applied_optional_files": [str(uuid.uuid4())]},
        headers=mtls_headers(device["certificate_pem"]),
    )

    assert response.status_code == 200
    assert client.get(f"/api/v1/devices/{device['device_id']}/file-selections").json() == []


# --------------------------------------------------------------------------- #
# Bulk assignment (F2)
# --------------------------------------------------------------------------- #


def test_one_policy_assigns_to_many_devices_in_one_call(client: TestClient, enrolled):
    devices = [enrolled(serial=f"BULK-{i}") for i in range(4)]
    policy = client.post(
        "/api/v1/policies",
        json={"name": "Fleet PW", "policy_type": "PASSWORD", "spec": {"min_length": 9}},
    ).json()

    response = client.put(
        f"/api/v1/policies/{policy['id']}/targets",
        json={"device_ids": [d["device_id"] for d in devices], "rank": 5},
    )

    assert response.status_code == 200
    assert response.json()["created"] == 4
    assert response.json()["devices_affected"] == 4
    for device in devices:
        state = client.get(
            f"/api/v1/devices/{device['device_id']}/effective-policy"
        ).json()
        assert state["values"]["PASSWORD"]["min_length"] == 9


def test_replace_mode_removes_targets_not_listed(client: TestClient, enrolled):
    keep = enrolled(serial="KEEP-1")
    drop = enrolled(serial="DROP-1")
    policy = client.post(
        "/api/v1/policies",
        json={"name": "Fleet PW", "policy_type": "PASSWORD", "spec": {"min_length": 9}},
    ).json()
    client.put(
        f"/api/v1/policies/{policy['id']}/targets",
        json={"device_ids": [keep["device_id"], drop["device_id"]]},
    )

    result = client.put(
        f"/api/v1/policies/{policy['id']}/targets",
        json={"device_ids": [keep["device_id"]]},
    ).json()

    assert result["removed"] == 1
    assert result["unchanged"] == 1
    assert client.get(
        f"/api/v1/devices/{drop['device_id']}/effective-policy"
    ).json()["values"] == {}


def test_add_mode_never_removes(client: TestClient, enrolled):
    first = enrolled(serial="ADD-1")
    second = enrolled(serial="ADD-2")
    policy = client.post(
        "/api/v1/policies",
        json={"name": "Fleet PW", "policy_type": "PASSWORD", "spec": {"min_length": 9}},
    ).json()
    client.put(
        f"/api/v1/policies/{policy['id']}/targets", json={"device_ids": [first["device_id"]]}
    )

    result = client.put(
        f"/api/v1/policies/{policy['id']}/targets",
        json={"device_ids": [second["device_id"]], "mode": "add"},
    ).json()

    assert result["removed"] == 0
    for device in (first, second):
        assert client.get(
            f"/api/v1/devices/{device['device_id']}/effective-policy"
        ).json()["values"]["PASSWORD"]["min_length"] == 9


def test_bulk_assignment_mixes_devices_groups_and_tags(client: TestClient, enrolled):
    device = enrolled(serial="MIX-1")
    group = client.post("/api/v1/groups", json={"name": "Field"}).json()
    tag = client.post("/api/v1/tags", json={"name": "urgent"}).json()
    policy = client.post(
        "/api/v1/policies",
        json={"name": "Fleet PW", "policy_type": "PASSWORD", "spec": {"min_length": 9}},
    ).json()

    result = client.put(
        f"/api/v1/policies/{policy['id']}/targets",
        json={
            "device_ids": [device["device_id"]],
            "group_ids": [group["id"]],
            "tag_ids": [tag["id"]],
        },
    ).json()

    assert result["created"] == 3


def test_bulk_assignment_to_unknown_target_is_404(client: TestClient):
    policy = client.post(
        "/api/v1/policies",
        json={"name": "Fleet PW", "policy_type": "PASSWORD", "spec": {"min_length": 9}},
    ).json()

    response = client.put(
        f"/api/v1/policies/{policy['id']}/targets",
        json={"device_ids": [str(uuid.uuid4())]},
    )

    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# Live propagation (F3)
# --------------------------------------------------------------------------- #


def test_wait_returns_immediately_when_state_already_moved(
    client: TestClient, enrolled, mtls_headers, assign
):
    device = enrolled()
    policy = client.post(
        "/api/v1/policies",
        json={"name": "PW", "policy_type": "PASSWORD", "spec": {"min_length": 9}},
    ).json()
    assign(policy["id"], device["device_id"], rank=1)

    response = client.get(
        "/api/v1/device/wait?state_version=0&timeout=5",
        headers=mtls_headers(device["certificate_pem"]),
    )

    assert response.status_code == 200
    assert response.json()["should_checkin"] is True


def test_wait_times_out_when_nothing_changes(client: TestClient, enrolled, mtls_headers):
    device = enrolled()
    headers = mtls_headers(device["certificate_pem"])
    settled = client.post("/api/v1/device/checkin", json={}, headers=headers).json()

    response = client.get(
        f"/api/v1/device/wait?state_version={settled['state_version']}&timeout=5",
        headers=headers,
    )

    body = response.json()
    assert body["should_checkin"] is False
    assert body["reason"] == "timeout"


def test_wait_is_released_by_a_policy_change(client: TestClient, enrolled, mtls_headers):
    """F3: a policy edit reaches the device at once, not at its next poll."""
    device = enrolled()
    headers = mtls_headers(device["certificate_pem"])
    settled = client.post("/api/v1/device/checkin", json={}, headers=headers).json()
    policy = client.post(
        "/api/v1/policies",
        json={"name": "PW", "policy_type": "PASSWORD", "spec": {"min_length": 9}},
    ).json()

    captured: dict = {}

    def park() -> None:
        response = client.get(
            f"/api/v1/device/wait?state_version={settled['state_version']}&timeout=30",
            headers=headers,
        )
        captured["body"] = response.json()

    waiter = threading.Thread(target=park, daemon=True)
    waiter.start()

    deadline = time.monotonic() + 5
    while notifications.bus.waiter_count(uuid.UUID(device["device_id"])) == 0:
        if time.monotonic() > deadline:
            pytest.fail("waiter never registered")
        time.sleep(0.02)

    started = time.monotonic()
    client.put(
        f"/api/v1/policies/{policy['id']}/targets",
        json={"device_ids": [device["device_id"]], "rank": 5},
    )
    waiter.join(timeout=15)
    elapsed = time.monotonic() - started

    assert not waiter.is_alive(), "the wait was never released"
    assert captured["body"]["should_checkin"] is True
    # The point of the feature: this must not take a check-in interval.
    assert elapsed < 5, f"release took {elapsed:.2f}s"


def test_wait_is_released_by_a_queued_command(client: TestClient, enrolled, mtls_headers):
    """A wipe on a lost device should not wait for the next poll."""
    device = enrolled()
    headers = mtls_headers(device["certificate_pem"])
    settled = client.post("/api/v1/device/checkin", json={}, headers=headers).json()

    captured: dict = {}

    def park() -> None:
        captured["body"] = client.get(
            f"/api/v1/device/wait?state_version={settled['state_version']}&timeout=30",
            headers=headers,
        ).json()

    waiter = threading.Thread(target=park, daemon=True)
    waiter.start()

    deadline = time.monotonic() + 5
    while notifications.bus.waiter_count(uuid.UUID(device["device_id"])) == 0:
        if time.monotonic() > deadline:
            pytest.fail("waiter never registered")
        time.sleep(0.02)

    client.post(
        f"/api/v1/devices/{device['device_id']}/commands", json={"command_type": "wipe"}
    )
    waiter.join(timeout=15)

    assert not waiter.is_alive()
    assert captured["body"]["should_checkin"] is True


def test_wait_requires_mtls(client: TestClient, enrolled):
    enrolled()
    assert client.get("/api/v1/device/wait?timeout=5").status_code == 401


def test_wait_reports_a_queued_command_without_parking(
    client: TestClient, enrolled, mtls_headers
):
    device = enrolled()
    headers = mtls_headers(device["certificate_pem"])
    settled = client.post("/api/v1/device/checkin", json={}, headers=headers).json()
    client.post(
        f"/api/v1/devices/{device['device_id']}/commands", json={"command_type": "lock"}
    )

    response = client.get(
        f"/api/v1/device/wait?state_version={settled['state_version']}&timeout=30",
        headers=headers,
    )

    assert response.json()["reason"] == "command_queued"


def test_waiters_are_cleaned_up_after_release(client: TestClient, enrolled, mtls_headers):
    """A leaked waiter set would grow without bound across a fleet's lifetime."""
    device = enrolled()
    headers = mtls_headers(device["certificate_pem"])
    settled = client.post("/api/v1/device/checkin", json={}, headers=headers).json()

    client.get(
        f"/api/v1/device/wait?state_version={settled['state_version']}&timeout=5",
        headers=headers,
    )

    assert notifications.bus.waiter_count(uuid.UUID(device["device_id"])) == 0


def test_rollback_does_not_wake_devices(client: TestClient, enrolled, session_factory):
    """A wake before commit could send a device to read data that never landed."""
    from app.db.models import Device

    device_id = uuid.UUID(enrolled()["device_id"])

    with session_factory() as session:
        # Touch the database first: SQLAlchemy only emits after_rollback when a
        # transaction was actually open.
        session.get(Device, device_id)
        notifications.schedule_wake(session, {device_id})
        session.rollback()

        assert "takmdm_wake_devices" not in session.info
