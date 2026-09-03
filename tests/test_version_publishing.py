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

"""Holding a build in the library instead of shipping it.

Before this, uploading a package **deployed** it: the upload invalidated every
device's cache, the resolver picked the newest build above each policy's floor,
and the fleet upgraded — with no confirmation anywhere. An operator uploading a
build "to have it on hand" shipped it to everything.

The asymmetry that matters: publishing is reversible by publishing something else,
but a fleet that has already upgraded cannot be walked back, because Android
refuses downgrades. So the defaults lean towards holding.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.db.models import PartRole
from app.policies import form_parse
from app.services import effective_policy as eff
from app.services import packages as package_service
from tests.apk_fixtures import build_apk, make_signing_certificate
from tests.conftest import ADMIN_HEADERS


def base_sha(result) -> str:
    return next(f.artifact_sha256 for f in result.version.files if f.role is PartRole.BASE)


def resolve(db, entry: dict) -> dict:
    return eff.resolve_required_apps(db, {"APP_CATALOG": {"required_apps": [entry]}})[0]


# --------------------------------------------------------------------------- #
# Publishing gates automatic selection, and only that
# --------------------------------------------------------------------------- #


def test_a_held_build_is_never_chosen_automatically(db, artifact_storage):
    cert = make_signing_certificate()
    package_service.ingest(db, artifact_storage, build_apk("com.probe", 100, certificate_der=cert))
    package_service.ingest(
        db, artifact_storage, build_apk("com.probe", 200, certificate_der=cert), publish=False
    )
    db.flush()

    assert resolve(db, {"package_name": "com.probe"})["version_code"] == 100


def test_a_held_build_can_still_be_pinned_to_exactly(db, artifact_storage):
    """Publishing means "may be chosen automatically". A pin names one build and is
    a deliberate act, so requiring publication too would be a second gate with no
    separate meaning — and a pin that silently did nothing is R17 again."""
    cert = make_signing_certificate()
    package_service.ingest(db, artifact_storage, build_apk("com.probe", 100, certificate_der=cert))
    held = package_service.ingest(
        db, artifact_storage, build_apk("com.probe", 200, certificate_der=cert), publish=False
    )
    db.flush()

    resolved = resolve(db, {"package_name": "com.probe", "artifact_sha256": base_sha(held)})
    assert resolved["version_code"] == 200


def test_holding_every_build_leaves_the_app_unresolvable_rather_than_guessing(
    db, artifact_storage
):
    package_service.ingest(
        db, artifact_storage, build_apk("com.probe", 100), publish=False
    )
    db.flush()

    assert resolve(db, {"package_name": "com.probe"})["available"] is False


# --------------------------------------------------------------------------- #
# What an upload does by default
# --------------------------------------------------------------------------- #


def test_a_newer_upload_publishes(db, artifact_storage):
    cert = make_signing_certificate()
    package_service.ingest(db, artifact_storage, build_apk("com.probe", 100, certificate_der=cert))
    newer = package_service.ingest(
        db, artifact_storage, build_apk("com.probe", 200, certificate_der=cert)
    )
    db.flush()

    assert newer.version.published is True


def test_an_older_upload_is_held_so_it_cannot_walk_a_fleet_backwards(db, artifact_storage):
    """The important default. Android refuses downgrades, so a fleet that has
    already moved cannot be recalled — an upload must not move it by accident."""
    cert = make_signing_certificate()
    package_service.ingest(db, artifact_storage, build_apk("com.probe", 200, certificate_der=cert))
    older = package_service.ingest(
        db, artifact_storage, build_apk("com.probe", 100, certificate_der=cert)
    )
    db.flush()

    assert older.version.published is False
    assert resolve(db, {"package_name": "com.probe"})["version_code"] == 200


def test_the_first_upload_of_a_package_publishes(db, artifact_storage):
    first = package_service.ingest(db, artifact_storage, build_apk("com.probe", 100))
    db.flush()

    assert first.version.published is True


def test_an_explicit_choice_beats_the_default_either_way(db, artifact_storage):
    cert = make_signing_certificate()
    package_service.ingest(db, artifact_storage, build_apk("com.probe", 100, certificate_der=cert))
    held = package_service.ingest(
        db, artifact_storage, build_apk("com.probe", 200, certificate_der=cert), publish=False
    )
    shipped = package_service.ingest(
        db, artifact_storage, build_apk("com.probe", 50, certificate_der=cert), publish=True
    )
    db.flush()

    assert held.version.published is False
    assert shipped.version.published is True


# --------------------------------------------------------------------------- #
# The comparison shown before the upload is taken
# --------------------------------------------------------------------------- #


def test_a_first_upload_needs_no_decision(db, artifact_storage):
    c = package_service.compare_upload(db, build_apk("com.fresh", 1))

    assert c.relation == "first"
    assert c.would_deploy is True
    assert c.deployed_version_code is None


def test_a_newer_upload_reports_what_it_would_replace(db, artifact_storage):
    cert = make_signing_certificate()
    package_service.ingest(db, artifact_storage, build_apk("com.probe", 100, "1.0", certificate_der=cert))
    db.flush()

    c = package_service.compare_upload(db, build_apk("com.probe", 200, "2.0", certificate_der=cert))

    assert c.relation == "newer"
    assert c.would_deploy is True
    assert (c.deployed_version_code, c.deployed_version_name) == (100, "1.0")


def test_an_older_upload_is_reported_as_older(db, artifact_storage):
    cert = make_signing_certificate()
    package_service.ingest(db, artifact_storage, build_apk("com.probe", 200, certificate_der=cert))
    db.flush()

    c = package_service.compare_upload(db, build_apk("com.probe", 100, certificate_der=cert))

    assert c.relation == "older"
    assert c.would_deploy is False


def test_a_duplicate_versioncode_is_reported_as_same(db, artifact_storage):
    cert = make_signing_certificate()
    package_service.ingest(db, artifact_storage, build_apk("com.probe", 100, certificate_der=cert))
    db.flush()

    assert package_service.compare_upload(
        db, build_apk("com.probe", 100, certificate_der=cert)
    ).relation == "same"


def test_comparing_rejects_what_ingest_would_reject(db, artifact_storage):
    """Better to refuse before asking the operator a question about it."""
    first = make_signing_certificate("A")
    package_service.ingest(db, artifact_storage, build_apk("com.probe", 100, certificate_der=first))
    db.flush()

    try:
        package_service.compare_upload(
            db, build_apk("com.probe", 200, certificate_der=make_signing_certificate("B"))
        )
    except package_service.PackageError as exc:
        assert "signing certificate" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("a signature mismatch should not reach the operator as a choice")


def test_the_comparison_names_the_policies_and_counts_the_devices(
    db, artifact_storage, client, enrolled, make_policy, assign
):
    """The number that makes the decision: how many devices this upload moves."""
    session = enrolled()
    cert = make_signing_certificate()
    package_service.ingest(db, artifact_storage, build_apk("com.probe", 100, certificate_der=cert))
    db.commit()

    policy = make_policy("ATAK required", "APP_CATALOG", {
        "required_apps": [{"package_name": "com.probe", "min_version_code": 1}]
    })
    assign(policy["id"], session["device_id"])
    db.commit()

    c = package_service.compare_upload(db, build_apk("com.probe", 200, certificate_der=cert))

    assert "ATAK required" in c.policy_names
    assert c.device_count == 1


# --------------------------------------------------------------------------- #
# The console
# --------------------------------------------------------------------------- #


def test_uploading_says_what_it_did(client: TestClient, db):
    response = client.post(
        "/apps/upload",
        files={"file": ("a.apk", build_apk("com.probe", 100), "application/octet-stream")},
        data={"label": "Probe", "publish": "auto"},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )
    assert "uploaded=" in response.headers["location"]
    assert "published" in response.headers["location"]


def test_an_older_upload_says_devices_stay_put(client: TestClient, db):
    cert = make_signing_certificate()
    client.post(
        "/apps/upload",
        files={"file": ("a.apk", build_apk("com.probe", 200, certificate_der=cert), "application/octet-stream")},
        data={"publish": "auto"},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )
    response = client.post(
        "/apps/upload",
        files={"file": ("b.apk", build_apk("com.probe", 100, certificate_der=cert), "application/octet-stream")},
        data={"publish": "auto"},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )

    location = response.headers["location"]
    assert "held" in location
    assert "200" in location  # names the build devices stay on


def test_the_preview_route_stores_nothing(client: TestClient, db):
    body = client.post(
        "/apps/preview-upload",
        files={"file": ("a.apk", build_apk("com.ghost", 1), "application/octet-stream")},
        headers=ADMIN_HEADERS,
    ).json()

    assert body["relation"] == "first"
    assert body["package_name"] == "com.ghost"
    assert package_service.compare_upload(db, build_apk("com.ghost", 1)).relation == "first"


def test_publishing_and_holding_from_the_console(client: TestClient, db, artifact_storage):
    cert = make_signing_certificate()
    package_service.ingest(db, artifact_storage, build_apk("com.probe", 100, certificate_der=cert))
    held = package_service.ingest(
        db, artifact_storage, build_apk("com.probe", 200, certificate_der=cert), publish=False
    )
    db.commit()
    version_id = held.version.id

    client.post(
        f"/apps/versions/{version_id}/publish",
        data={"published": "true"},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )
    db.expire_all()
    assert resolve(db, {"package_name": "com.probe"})["version_code"] == 200

    client.post(
        f"/apps/versions/{version_id}/publish",
        data={"published": "false"},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )
    db.expire_all()
    assert resolve(db, {"package_name": "com.probe"})["version_code"] == 100


# --------------------------------------------------------------------------- #
# The policy form's version picker
# --------------------------------------------------------------------------- #


def parse_apps(choice: str) -> dict:
    """Run one app row through the real form parser."""
    from starlette.datastructures import FormData

    form = FormData(
        [
            ("required_apps__package_name", "com.probe"),
            ("required_apps__version_choice", choice),
        ]
    )
    return form_parse.parse_form("APP_CATALOG", form)["required_apps"][0]


def test_the_picker_default_means_latest(db):
    assert parse_apps("") == {"package_name": "com.probe"}


def test_the_picker_can_express_a_floor(db):
    assert parse_apps("min:400")["min_version_code"] == 400


def test_the_picker_can_pin_an_exact_build(db):
    """The distinction that had no control at all: hold this fleet on one build,
    including an older one."""
    sha = "ab" * 32
    row = parse_apps(f"pin:{sha}")

    assert row["artifact_sha256"] == sha
    assert "min_version_code" not in row  # mutually exclusive, never both


def test_a_malformed_pin_is_dropped_rather_than_written(db):
    """A short sha would fail the spec's pattern and reject the whole policy."""
    assert parse_apps("pin:not-a-sha") == {"package_name": "com.probe"}
