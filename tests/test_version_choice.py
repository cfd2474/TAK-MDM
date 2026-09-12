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

"""The policy names the build it installs (W139).

Two earlier designs sit behind this one. First, uploading a package **deployed**
it: the newest build above each policy's floor won, so an operator uploading a
build "to have it on hand" shipped it to the fleet. Then a `published` flag was
added to gate that automatic selection, with a rule about never walking a fleet
backwards and a three-way question on the upload form.

Both are gone. A policy entry names an exact build, so an upload changes nothing
until someone chooses it, and a flag meaning "may be chosen automatically" has
nothing left to govern.

⚠️ **Unpinned means incomplete, not "newest".** That distinction is the whole
safety argument. This project's own library holds two packages whose every build
was held, one of them named by an unpinned policy entry — so a "newest wins"
reading would have installed Chrome across the fleet the moment the column was
dropped.
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
# ⚠️ Nothing is chosen on an operator's behalf
# --------------------------------------------------------------------------- #


def test_an_entry_naming_no_build_installs_nothing(db, artifact_storage):
    """⚠️ The safety property the whole change rests on.

    Not "the newest build". Two packages in this project's own library have
    every build held, and one is named by an unpinned policy entry — under a
    "newest wins" reading, dropping the `published` column would have installed
    Chrome across the fleet at the next check-in.
    """
    cert = make_signing_certificate()
    package_service.ingest(db, artifact_storage, build_apk("com.probe", 100, certificate_der=cert))
    package_service.ingest(db, artifact_storage, build_apk("com.probe", 200, certificate_der=cert))
    db.flush()

    resolved = resolve(db, {"package_name": "com.probe"})

    assert resolved["available"] is False
    assert "no version chosen" in resolved["reason"]


def test_the_reason_separates_never_uploaded_from_never_chosen(db, artifact_storage):
    """Two failures with one symptom and different fixes: one is an upload, the
    other is an edit. A reason covering both tells an operator nothing."""
    package_service.ingest(db, artifact_storage, build_apk("com.probe", 100))
    db.flush()

    assert "no version chosen" in resolve(db, {"package_name": "com.probe"})["reason"]
    assert resolve(db, {"package_name": "com.absent"})["reason"] == "nothing uploaded for it"


def test_a_floor_alone_still_chooses_nothing(db, artifact_storage):
    """`min_version_code` is automatic selection wearing a floor. It stays in the
    model so stored specs still validate, and it selects nothing."""
    cert = make_signing_certificate()
    package_service.ingest(db, artifact_storage, build_apk("com.probe", 100, certificate_der=cert))
    package_service.ingest(db, artifact_storage, build_apk("com.probe", 200, certificate_der=cert))
    db.flush()

    resolved = resolve(db, {"package_name": "com.probe", "min_version_code": 150})

    assert resolved["available"] is False


# --------------------------------------------------------------------------- #
# An upload adds to the library and does nothing else
# --------------------------------------------------------------------------- #


def test_an_older_build_can_be_the_one_a_policy_names(db, artifact_storage):
    """There is no "held" any more, so there is nothing to un-hold. An older
    build is just a build, and naming it is how it gets installed."""
    cert = make_signing_certificate()
    older = package_service.ingest(
        db, artifact_storage, build_apk("com.probe", 100, certificate_der=cert)
    )
    package_service.ingest(db, artifact_storage, build_apk("com.probe", 200, certificate_der=cert))
    db.flush()

    resolved = resolve(db, {"package_name": "com.probe", "artifact_sha256": base_sha(older)})

    assert resolved["version_code"] == 100


def test_uploading_takes_no_decision(db, artifact_storage):
    """⚠️ `ingest` no longer accepts a `publish` argument. It used to decide
    whether the fleet moved; there is nothing left for it to decide."""
    import inspect as _inspect

    assert "publish" not in _inspect.signature(package_service.ingest).parameters


# --------------------------------------------------------------------------- #
# The comparison shown before the upload is taken
# --------------------------------------------------------------------------- #


def test_a_first_upload_needs_no_decision(db, artifact_storage):
    c = package_service.compare_upload(db, build_apk("com.fresh", 1))

    assert c.relation == "first"
    # ⚠️ False even for a first upload: no upload deploys anything now (W139).
    assert c.would_deploy is False
    assert c.deployed_version_code is None


def test_a_newer_upload_names_what_is_already_there(db, artifact_storage):
    """Still worth saying, and it no longer means "what this replaces" — it is
    the newest build in the library, so the console can tell an operator they
    now have two."""
    cert = make_signing_certificate()
    package_service.ingest(db, artifact_storage, build_apk("com.probe", 100, "1.0", certificate_der=cert))
    db.flush()

    c = package_service.compare_upload(db, build_apk("com.probe", 200, "2.0", certificate_der=cert))

    assert c.relation == "newer"
    assert c.would_deploy is False
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
    """⚠️ And what it did is "added it to the library". The old message said
    "published", which was true then and would be a lie now."""
    response = client.post(
        "/apps/upload",
        files={"file": ("a.apk", build_apk("com.probe", 100), "application/octet-stream")},
        data={"label": "Probe"},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )

    location = response.headers["location"]
    assert "uploaded=" in location
    assert "added" in location
    assert "published" not in location


def test_an_upload_that_reaches_devices_says_where_to_go_next(client: TestClient, db):
    """A second build of a package some devices already follow. Nothing moves,
    and the sentence says the one useful thing: which policy to edit."""
    cert = make_signing_certificate()
    client.post(
        "/apps/upload",
        files={"file": ("a.apk", build_apk("com.probe", 200, certificate_der=cert), "application/octet-stream")},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )
    response = client.post(
        "/apps/upload",
        files={"file": ("b.apk", build_apk("com.probe", 100, certificate_der=cert), "application/octet-stream")},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )

    location = response.headers["location"]
    assert "added" in location
    # No claim that anything was deployed, held, or replaced.
    assert "held" not in location
    assert "replacing" not in location


def test_the_preview_route_stores_nothing(client: TestClient, db):
    body = client.post(
        "/apps/preview-upload",
        files={"file": ("a.apk", build_apk("com.ghost", 1), "application/octet-stream")},
        headers=ADMIN_HEADERS,
    ).json()

    assert body["relation"] == "first"
    assert body["package_name"] == "com.ghost"
    assert package_service.compare_upload(db, build_apk("com.ghost", 1)).relation == "first"


def test_there_is_nothing_to_publish_from_the_console(client: TestClient, db, artifact_storage):
    """⚠️ The route is gone, and a 404 is the assertion.

    Leaving it in place to quietly do nothing would be worse than removing it:
    an operator would keep pressing a button that reported success and changed
    nothing about any device.
    """
    cert = make_signing_certificate()
    result = package_service.ingest(
        db, artifact_storage, build_apk("com.probe", 100, certificate_der=cert)
    )
    db.commit()

    response = client.post(
        f"/apps/versions/{result.version.id}/publish",
        data={"published": "true"},
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )

    assert response.status_code == 404


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


def test_an_empty_choice_writes_no_build(db):
    """Reachable only for an app with nothing uploaded, where the select is
    disabled. The row is still written so the operator can see the app they
    picked; it resolves to a reason until a build exists and is chosen."""
    assert parse_apps("") == {"package_name": "com.probe"}


def test_a_floor_is_no_longer_parsed(db):
    """⚠️ `min:` was the "at least this versionCode" option, and the select
    stopped offering it (W139). The parser stopped accepting it too, rather
    than writing a floor the resolver ignores — a stored floor would produce a
    policy that looks configured and installs nothing.
    """
    assert parse_apps("min:400") == {"package_name": "com.probe"}


def test_the_picker_names_an_exact_build(db):
    """The only thing the control expresses now: install this build."""
    sha = "ab" * 32
    row = parse_apps(f"pin:{sha}")

    assert row["artifact_sha256"] == sha
    assert "min_version_code" not in row


def test_a_malformed_pin_is_dropped_rather_than_written(db):
    """A short sha would fail the spec's pattern and reject the whole policy."""
    assert parse_apps("pin:not-a-sha") == {"package_name": "com.probe"}


# --------------------------------------------------------------------------- #
# The control an operator actually uses (W139 chunk 2)
# --------------------------------------------------------------------------- #


def _form_page(client: TestClient) -> str:
    return client.get("/policies/new?policy_type=APP_CATALOG", headers=ADMIN_HEADERS).text


def _macro() -> str:
    import pathlib

    return pathlib.Path("app/web/templates/_policy_form.html").read_text(encoding="utf-8")


def test_the_version_select_offers_builds_and_nothing_else(client: TestClient, db):
    """⚠️ "Latest published" and "At least N" were automatic-selection modes the
    server no longer honours. Leaving either in the list would let an operator
    save a policy that looks configured and installs nothing."""
    page = _form_page(client)

    picker = page[page.index("__version_choice") :]
    picker = picker[: picker.index("</select>")]

    assert "Latest published" not in picker
    assert "At least" not in picker
    assert "held" not in picker


def test_every_build_of_the_picked_app_is_offered_newest_first(
    client: TestClient, db, artifact_storage
):
    """The operator's example: three builds of one plugin, all choosable."""
    cert = make_signing_certificate()
    for code in (1786490539, 1786490584, 1786490659):
        package_service.ingest(
            db, artifact_storage,
            build_apk("com.beartooth.beartoothtakplugin", code, certificate_der=cert),
        )
    db.commit()

    page = _form_page(client)
    picker = page[page.index("__version_choice") :]
    picker = picker[: picker.index("</select>")]

    for code in (1786490539, 1786490584, 1786490659):
        assert str(code) in picker
    # Newest first, and labelled, so the default is visible rather than implied.
    assert picker.index("1786490659") < picker.index("1786490584")
    assert "newest" in picker


def test_each_option_says_which_app_it_belongs_to(client: TestClient, db, artifact_storage):
    """`atlas.js` filters on `data-package`; without it every build of every app
    stays in one list, which is how the wrong build gets pinned."""
    package_service.ingest(db, artifact_storage, build_apk("com.probe", 1))
    db.commit()

    page = _form_page(client)

    assert 'data-package="com.probe"' in page


def test_the_newest_build_is_the_default(client: TestClient, db):
    """⚠️ Asserted against the filter that actually runs. The template marks the
    newest option, but nothing is selected until an app is picked — the default
    is whatever `rebuild` chooses, and `wanted[0]` is the newest only because
    the template sorts descending."""
    import pathlib

    js = pathlib.Path("app/web/static/atlas.js").read_text(encoding="utf-8")
    body = js[js.index("function rebuild(keepValue)") :]
    body = body[: body.index("picker.addEventListener")]

    assert "choice.value = wanted[0].value" in body
    # The saved choice still wins when it belongs to this app.
    assert "keepValue" in body


def test_an_app_with_no_builds_says_so_rather_than_going_blank(client: TestClient, db):
    """An empty select reads as "still loading"."""
    import pathlib

    js = pathlib.Path("app/web/static/atlas.js").read_text(encoding="utf-8")

    assert "no builds uploaded for this app" in js


def test_saving_the_form_writes_a_pin(client: TestClient, db, artifact_storage):
    """⚠️ End to end, through the real form parser, because every other test
    here could pass while the saved policy still carried no build.

    This is also the conversion path for a policy written before W139: it holds
    a floor or nothing, the select falls back to the newest build, and saving
    turns it into a policy that installs something.
    """
    result = package_service.ingest(db, artifact_storage, build_apk("com.probe", 700))
    db.commit()
    sha = base_sha(result)

    response = client.post(
        "/policies",
        data={
            "name": "Probe 700",
            "policy_type": "APP_CATALOG",
            "required_apps__package_name": ["com.probe"],
            "required_apps__version_choice": [f"pin:{sha}"],
        },
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )
    assert response.status_code in (302, 303), response.text

    from app.db.models import Policy
    from sqlalchemy import select as _select

    policy = db.scalar(_select(Policy).where(Policy.name == "Probe 700"))
    entry = policy.latest_version.spec["required_apps"][0]

    assert entry["artifact_sha256"] == sha
    assert resolve(db, entry)["version_code"] == 700
