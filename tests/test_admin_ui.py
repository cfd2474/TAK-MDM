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

"""Admin console: rendering, form handling, and the stacking view."""

from __future__ import annotations

import json as _json
import re

import pytest
from fastapi.testclient import TestClient

from tests.conftest import FLEET_DEFAULT

ADMIN = {"x-authentik-username": "a", "x-authentik-groups": "takmdm-admins"}


def text_of(html: str) -> str:
    """Strip tags so assertions test what an operator reads, not the markup."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def create_policy(client: TestClient, name: str, policy_type: str, spec: str) -> str:
    """Create a policy via the API — the console form is form-driven (W10), so
    scripted tests use the machine surface."""
    response = client.post(
        "/api/v1/policies",
        json={"name": name, "policy_type": policy_type, "spec": _json.loads(spec)},
        headers=ADMIN,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


# --------------------------------------------------------------------------- #
# Chassis
# --------------------------------------------------------------------------- #


def test_dashboard_renders_with_no_devices(client: TestClient):
    response = client.get("/")

    assert response.status_code == 200
    assert "No devices yet" in text_of(response.text)


def test_console_warns_when_auth_is_disabled(client: TestClient):
    """With auth off, the banner is the only thing flagging an open console."""
    body = text_of(client.get("/").text)

    assert "Admin authentication is disabled" in body
    assert "not signed in" in body


def test_admin_routes_are_absent_from_the_api_schema(client: TestClient):
    """They are a human surface; listing them as API would invite exposing them."""
    paths = client.get("/openapi.json").json()["paths"]

    assert "/policies" not in paths
    assert "/enrollment" not in paths
    assert "/api/v1/policies" in paths


def test_dashboard_lists_an_enrolled_device(client: TestClient, enrolled):
    enrolled(serial="R5CN00TAK99")

    assert "R5CN00TAK99" in client.get("/").text


# --------------------------------------------------------------------------- #
# Eight-section shell (W1)
# --------------------------------------------------------------------------- #

SECTIONS = {
    "/enrollment": "Enroll",
    "/": "Manage",
    "/policies": "Policies",
    "/apps": "Apps",
    "/content": "Content",
    "/reports": "Reports",
    "/admin": "Admin",
    "/guides": "Guides",
}


def test_every_section_is_reachable(client: TestClient):
    for path in SECTIONS:
        assert client.get(path).status_code == 200, path


def test_nav_marks_the_active_section(client: TestClient):
    """The link for the page you are on carries `on`, in both navs, and nothing
    else does.

    ⚠️ **Twice, not once** (W190). There are two lists of the same sections now
    — the desktop banner and the mobile grid — and both mark the current one.
    The assertion counts rather than merely looking for the label, because
    `label in active` would pass just as happily for a page that marked every
    section in both.
    """
    for path, label in SECTIONS.items():
        body = client.get(path).text
        # The active link renders as: <a href="..." class="on">Label</a>
        active = re.findall(r'<a href="[^"]*" class="on">([^<]+)</a>', body)
        assert active == [label, label], (path, active)


def test_no_section_is_a_stub_any_more(client: TestClient):
    """Every nav entry now leads to a real page — W1's placeholder shells are gone."""
    for path in SECTIONS:
        assert "coming in a later chunk" not in client.get(path).text


def test_console_stylesheet_is_served(client: TestClient):
    response = client.get("/static/atlas.css")
    assert response.status_code == 200
    assert "text/css" in response.headers["content-type"]
    assert "--accent" in response.text


def test_console_script_is_served(client: TestClient):
    assert client.get("/static/atlas.js").status_code == 200


# --------------------------------------------------------------------------- #
# Apps — local packages, ATLAS store, app groups (W5)
# --------------------------------------------------------------------------- #


def _upload_app(client: TestClient, package: str, code: int = 1, label: str = "") -> None:
    from tests.apk_fixtures import build_apk

    response = client.post(
        "/apps/upload",
        data={"label": label},
        files={"file": ("app.apk", build_apk(package, code), "application/octet-stream")},
        follow_redirects=False,
    )
    assert response.status_code in (303, 200), response.text


def test_apps_page_has_three_tabs(client: TestClient):
    body = client.get("/apps").text
    for label in ("Local apps", "ATLAS store", "App groups"):
        assert label in body


def test_upload_lists_a_package(client: TestClient):
    _upload_app(client, "com.example.tool", 5, label="Tool")

    body = client.get("/apps").text
    assert "com.example.tool" in body
    assert "Tool" in body


def test_a_package_carrying_an_obb_is_flagged(client: TestClient):
    """A Device Owner cannot place OBB files on the device (R2) — the operator
    needs to see that before assigning, not as missing assets at runtime."""
    from tests.apk_fixtures import build_xapk

    response = client.post(
        "/apps/upload",
        data={"label": ""},
        files={"file": ("app.xapk", build_xapk("com.example.withobb", 1, with_obb=True),
                        "application/octet-stream")},
        follow_redirects=False,
    )
    assert response.status_code in (303, 200), response.text

    body = client.get("/apps").text
    assert "com.example.withobb" in body
    assert ">OBB</span>" in body


def test_there_is_no_add_to_store_button(client: TestClient):
    """⚠️ Removed at the operator's request (W140), and the route with it.

    A package no longer knows whether it is "in the store" — several storefronts
    may name it, at different builds. A button still posting to a route that no
    longer exists would look like a feature and 404 on use.
    """
    _upload_app(client, "com.example.store")
    pkg_id = client.get("/api/v1/packages", headers=ADMIN).json()[0]["id"]

    page = client.get("/apps").text
    assert "Add to store" not in page
    assert "store_listed" not in client.get("/api/v1/packages", headers=ADMIN).text

    gone = client.post(
        f"/apps/{pkg_id}/store", data={"listed": "true"}, follow_redirects=False
    )
    assert gone.status_code == 404


def test_delete_package(client: TestClient):
    _upload_app(client, "com.example.gone")
    pkg_id = client.get("/api/v1/packages", headers=ADMIN).json()[0]["id"]

    client.post(f"/apps/{pkg_id}/delete", follow_redirects=False)

    assert client.get("/api/v1/packages", headers=ADMIN).json() == []


def test_app_group_create_members_and_delete(client: TestClient):
    _upload_app(client, "com.a")
    _upload_app(client, "com.b")
    packages = client.get("/api/v1/packages", headers=ADMIN).json()
    ids = [p["id"] for p in packages]

    client.post(
        "/app-groups",
        data={"name": "Bundle", "package_ids": ids},
        follow_redirects=False,
    )

    groups = client.get("/api/v1/app-groups", headers=ADMIN).json()
    assert len(groups) == 1
    assert {p["package_name"] for p in groups[0]["packages"]} == {"com.a", "com.b"}

    gid = groups[0]["id"]
    client.post(
        f"/app-groups/{gid}/members", data={"package_ids": [ids[0]]}, follow_redirects=False
    )
    assert len(client.get(f"/api/v1/app-groups/{gid}", headers=ADMIN).json()["packages"]) == 1

    client.post(f"/app-groups/{gid}/delete", follow_redirects=False)
    assert client.get("/api/v1/app-groups", headers=ADMIN).json() == []


def test_app_group_api_rejects_unknown_package(client: TestClient):
    r = client.post(
        "/api/v1/app-groups",
        json={"name": "X", "package_ids": ["00000000-0000-0000-0000-000000000000"]},
        headers=ADMIN,
    )
    assert r.status_code == 422


def test_profile_creator_offers_app_group_shortcut(client: TestClient):
    _upload_app(client, "com.atakmap.app.civ")
    pkg_id = client.get("/api/v1/packages", headers=ADMIN).json()[0]["id"]
    client.post("/app-groups", data={"name": "ATAK", "package_ids": [pkg_id]})

    body = client.get("/policies/new").text
    # The button carries its payload as data, not as an onclick argument
    # (SEC_AUDIT M-6) — the page itself contains no script.
    assert "data-add-app-group" in body
    assert "com.atakmap.app.civ" in body  # the group's package is offered


# --------------------------------------------------------------------------- #
# Content — managed files & deployment references (W6)
# --------------------------------------------------------------------------- #


def _upload_file(client: TestClient, content: bytes, name: str = "map.xml") -> str:
    client.post(
        "/content/upload",
        data={"name": name},
        files={"file": (name, content, "text/xml")},
        follow_redirects=False,
    )
    return client.get("/api/v1/files", headers=ADMIN).json()[-1]["id"]


def _files_policy(client: TestClient, name: str, file_id: str, dest: str = "/sdcard/atak") -> str:
    r = client.post(
        "/api/v1/policies",
        json={
            "name": name,
            "policy_type": "FILES",
            "spec": {"entries": [{"file_id": file_id, "dest_path": dest}]},
        },
        headers=ADMIN,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_content_page_lists_uploaded_files(client: TestClient):
    _upload_file(client, b"<xml/>", "source.xml")
    body = client.get("/content").text
    assert "source.xml" in body


def test_content_shows_which_policy_deploys_a_file(client: TestClient):
    fid = _upload_file(client, b"payload")
    _files_policy(client, "Map push", fid, dest="/sdcard/atak/imagery")

    body = text_of(client.get("/content").text)
    assert "Map push" in body
    assert "/sdcard/atak/imagery" in body


def test_delete_is_refused_while_a_policy_references_the_file(client: TestClient):
    fid = _upload_file(client, b"payload")
    _files_policy(client, "Holder", fid)

    response = client.post(f"/content/{fid}/delete", follow_redirects=True)
    assert "Holder" in text_of(response.text)
    # Still there
    assert any(f["id"] == fid for f in client.get("/api/v1/files", headers=ADMIN).json())


def test_delete_works_when_unreferenced(client: TestClient):
    fid = _upload_file(client, b"payload")

    client.post(f"/content/{fid}/delete", follow_redirects=False)

    assert client.get("/api/v1/files", headers=ADMIN).json() == []


def test_edit_deployment_defaults(client: TestClient):
    fid = _upload_file(client, b"payload")

    client.post(
        f"/content/{fid}/edit",
        data={
            "name": "Renamed",
            "default_dest_path": "/sdcard/atak/cfg",
            "default_persist": "yes",
            "default_overwrite": "always",
        },
        follow_redirects=False,
    )

    got = client.get(f"/api/v1/files/{fid}", headers=ADMIN).json()
    assert got["name"] == "Renamed"
    assert got["default_dest_path"] == "/sdcard/atak/cfg"
    assert got["default_persist"] is True
    assert got["default_overwrite"] == "always"


# --------------------------------------------------------------------------- #
# Reports (W7)
# --------------------------------------------------------------------------- #


def test_reports_page_lists_the_catalogue(client: TestClient):
    body = client.get("/reports").text
    for title in ("Fleet inventory", "Convergence", "Command history", "App inventory"):
        assert title in body


def test_a_report_renders_a_table(client: TestClient, enrolled):
    enrolled(serial="W7-INV")
    body = text_of(client.get("/reports/fleet-inventory").text)
    assert "W7-INV" in body


def test_report_csv_export(client: TestClient, enrolled):
    enrolled(serial="W7-CSV")

    response = client.get("/reports/fleet-inventory?format=csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    lines = response.text.splitlines()
    assert lines[0].startswith("Name,Serial,Model")
    assert any("W7-CSV" in line for line in lines[1:])


def test_command_history_report_shows_a_queued_command(client: TestClient, enrolled):
    device = enrolled(serial="W7-CMD")
    client.post(f"/devices/{device['device_id']}/collect-logs", follow_redirects=False)

    body = text_of(client.get("/reports/command-history").text)
    assert "W7-CMD" in body and "collect_logs" in body


def test_unknown_report_is_404(client: TestClient):
    assert client.get("/reports/nope").status_code == 404


# --------------------------------------------------------------------------- #
# Admin — certificates, settings, custom attributes (W8)
# --------------------------------------------------------------------------- #


def test_admin_page_has_its_sections(client: TestClient):
    body = client.get("/admin").text
    for label in (
        "Certificates", "End-user licence agreement", "Email (SMTP)",
        "Custom attributes", "Environment",
    ):
        assert label in body


def test_certificate_is_listed_and_can_be_revoked(client: TestClient, enrolled, db):
    from sqlalchemy import select as _select
    from app.db.models import DeviceCertificate

    enrolled(serial="W8-CERT")
    cert = db.scalars(_select(DeviceCertificate)).first()
    assert cert is not None
    assert cert.serial_hex[:16] in client.get("/admin").text

    client.post(f"/admin/certs/{cert.id}/revoke", follow_redirects=False)

    db.expire_all()
    assert db.get(DeviceCertificate, cert.id).revoked_at is not None
    assert "revoked" in text_of(client.get("/admin").text)


def test_smtp_settings_save_and_password_is_not_echoed(client: TestClient):
    client.post(
        "/admin/settings/smtp",
        data={
            "smtp.host": "mail.example.org",
            "smtp.port": "587",
            "smtp.username": "alerts",
            "smtp.password": "s3cret",
            "smtp.from_address": "atlas@example.org",
            "smtp.use_tls": "true",
        },
        follow_redirects=False,
    )

    body = client.get("/admin").text
    assert "mail.example.org" in body
    assert "s3cret" not in body  # a stored password is never rendered back


def test_blank_password_keeps_the_stored_one(client: TestClient, db):
    from sqlalchemy import select as _select
    from app.db.models import AppSetting

    client.post("/admin/settings/sms", data={"sms.api_key": "KEY123", "sms.provider": "twilio"})
    client.post("/admin/settings/sms", data={"sms.api_key": "", "sms.provider": "twilio"})

    db.expire_all()
    from app.services import settings_store

    # The behaviour: a blank field does not overwrite what is held.
    assert settings_store.group_values(db, "sms")["sms.api_key"] == "KEY123"

    # ⚠️ And the property M-5 added: the column no longer carries the secret.
    # This assertion used to read `stored["sms.api_key"] == "KEY123"`, which was
    # exactly what a database dump would have given an attacker.
    raw = {s.key: s.value for s in db.scalars(_select(AppSetting))}["sms.api_key"]
    assert raw != "KEY123"
    assert "KEY123" not in raw


def test_custom_attribute_lifecycle(client: TestClient, enrolled):
    client.post(
        "/admin/attributes",
        data={"name": "Owning unit", "attr_type": "string"},
        follow_redirects=False,
    )
    attrs = client.get("/api/v1/custom-attributes", headers=ADMIN).json()
    assert [a["name"] for a in attrs] == ["Owning unit"]
    attr_id = attrs[0]["id"]

    device = enrolled(serial="W8-ATTR")
    body = client.get(f"/devices/{device['device_id']}").text
    assert "Owning unit" in body

    client.post(
        f"/devices/{device['device_id']}/attributes",
        data={"attribute_id": attr_id, "value": "2nd Recon"},
        follow_redirects=False,
    )
    got = client.get(
        f"/api/v1/devices/{device['device_id']}/attributes", headers=ADMIN
    ).json()
    assert got[0]["value"] == "2nd Recon"

    client.post(f"/admin/attributes/{attr_id}/delete", follow_redirects=False)
    assert client.get("/api/v1/custom-attributes", headers=ADMIN).json() == []


def test_custom_attribute_api_rejects_bad_type(client: TestClient):
    r = client.post(
        "/api/v1/custom-attributes",
        json={"name": "X", "attr_type": "wizardry"},
        headers=ADMIN,
    )
    assert r.status_code == 422


# --------------------------------------------------------------------------- #
# Guides (W9)
# --------------------------------------------------------------------------- #


def test_guides_page_lists_howto_and_faq(client: TestClient):
    body = client.get("/guides").text
    assert "Enrol a device" in body
    assert "FAQ" in body
    assert "Release notes" in body


def test_a_guide_renders_its_markdown(client: TestClient):
    body = client.get("/guides/howto/enrolment").text
    # markdown_lite turned '## Steps' into a heading and '- ' into a list
    assert "<h2>Steps</h2>" in body
    assert "<li>" in body


def test_release_notes_render(client: TestClient):
    body = text_of(client.get("/guides").text)
    assert "Eight-section console" in body


def test_unknown_guide_is_404(client: TestClient):
    assert client.get("/guides/howto/nope").status_code == 404
    assert client.get("/guides/bogus/x").status_code == 404


def test_markdown_lite_escapes_html():
    from app.web.markdown_lite import render

    out = render("Hello <b>world</b> and `<script>`")
    assert "<b>world</b>" not in out
    assert "&lt;b&gt;" in out
    assert "<code>&lt;script&gt;</code>" in out


def test_markdown_lite_escapes_quotes_too():
    """⚠️ `html.escape` leaves quotes alone unless asked (SEC_AUDIT L-3).

    Rendered text lands inside attributes — a link title, a table cell reused as
    a tooltip — where an unescaped quote closes the attribute and everything
    after it is markup.
    """
    from app.web.markdown_lite import render

    out = render("""He said "run" and it's fine""")

    assert '"run"' not in out
    assert "&quot;" in out
    assert "&#x27;" in out


@pytest.mark.parametrize(
    "scheme", ["javascript:alert(1)", "JaVaScRiPt:alert(1)", "data:text/html,<x>",
               "vbscript:msgbox", "  javascript:alert(1)"]
)
def test_markdown_lite_refuses_a_script_bearing_link(scheme):
    """A guide is authored in the repository, but the renderer is not only fed
    guides — and a link scheme is the cheapest way to turn read-only text into
    script execution.
    """
    from app.web.markdown_lite import render

    out = render(f"[click]({scheme})")

    # No anchor at all is the property that matters. Whether the leftover text
    # still reads "javascript:" is irrelevant — it is escaped body text, and
    # asserting on it instead would pass for a renderer that happened to fail to
    # parse the link while still linking the next one.
    assert "<a " not in out, out
    assert "href" not in out, out


@pytest.mark.parametrize(
    "target", ["https://example.com/x", "http://example.com/x", "/guides/howto/a",
               "#section", "mailto:someone@example.com"]
)
def test_markdown_lite_still_links_what_a_guide_actually_uses(target):
    """⚠️ The guides are full of these. A scheme allowlist that also drops them
    turns every cross-reference in the documentation into plain text, and nobody
    reads a 404 they cannot click.
    """
    from app.web.markdown_lite import render

    out = render(f"[click]({target})")

    assert f'href="{target}"' in out, out


# --------------------------------------------------------------------------- #
# Manage — fleet table (W2)
# --------------------------------------------------------------------------- #


def test_manage_table_names_the_policies_reaching_a_device(
    client: TestClient, enrolled, assign
):
    device = enrolled(serial="W2-POL")
    policy_id = create_policy(client, "Baseline PW", "PASSWORD", '{"min_length": 8}')
    assign(policy_id, device["device_id"], rank=10)

    body = text_of(client.get("/").text)
    assert "Baseline PW" in body


def test_manage_table_has_a_filter_and_is_sortable(client: TestClient, enrolled):
    enrolled(serial="W2-FILTER")
    body = client.get("/").text
    assert 'data-filter="#fleet-table"' in body
    assert "data-sortable" in body


def test_a_device_can_be_named_and_the_name_is_shown(client: TestClient, enrolled):
    device = enrolled(serial="W2-NAME")

    client.post(
        f"/devices/{device['device_id']}/rename",
        data={"name": "Command Post 1"},
        follow_redirects=False,
    )

    assert "Command Post 1" in text_of(client.get("/").text)
    assert "Command Post 1" in text_of(client.get(f"/devices/{device['device_id']}").text)


def test_renaming_returns_where_it_was_asked_to(client: TestClient, enrolled):
    """⚠️ The fleet list no longer offers a rename (W160) — a box per row put an
    edit one stray keystroke from every device on the page. The endpoint keeps
    honouring `next`, because that is what makes it usable from anywhere; it is
    the *control* that moved, not the capability.
    """
    device = enrolled(serial="W24-INLINE")

    assert f'action="/devices/{device["device_id"]}/rename"' not in client.get("/").text

    r = client.post(
        f"/devices/{device['device_id']}/rename",
        data={"name": "Bench 4", "next": "/"},
        follow_redirects=False,
    )
    assert r.headers["location"] == "/"
    assert "Bench 4" in text_of(client.get("/").text)


def test_rename_ignores_an_offsite_next(client: TestClient, enrolled):
    device = enrolled(serial="W24-OPENREDIR")
    r = client.post(
        f"/devices/{device['device_id']}/rename",
        data={"name": "x", "next": "//evil.example/"},
        follow_redirects=False,
    )
    assert r.headers["location"] == f"/devices/{device['device_id']}"


def test_a_blank_name_clears_it(client: TestClient, enrolled):
    device = enrolled(serial="W2-CLEAR")
    client.post(f"/devices/{device['device_id']}/rename", data={"name": "Temp"})

    client.post(f"/devices/{device['device_id']}/rename", data={"name": "   "})

    assert client.get(f"/api/v1/devices/{device['device_id']}").json()["name"] is None


def test_device_name_patch_endpoint(client: TestClient, enrolled):
    device = enrolled(serial="W2-PATCH")

    response = client.patch(
        f"/api/v1/devices/{device['device_id']}",
        json={"name": "Recon-7"},
        headers={"x-authentik-username": "a", "x-authentik-groups": "takmdm-admins"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Recon-7"


# --------------------------------------------------------------------------- #
# Enroll — QR + Wi-Fi on one page (W2)
# --------------------------------------------------------------------------- #


def test_enroll_page_carries_wifi_fields_on_the_qr_form(client: TestClient):
    client.post("/enrollment/primary", data={"name": "Fleet"})

    body = client.get("/enrollment").text
    assert 'name="wifi_ssid"' in body
    assert 'name="wifi_password"' in body
    assert 'action="/enrollment/qr"' in body


# --------------------------------------------------------------------------- #
# Policy editor
# --------------------------------------------------------------------------- #


def test_create_policy_through_the_form(client: TestClient):
    policy_id = create_policy(client, "Console PW", "PASSWORD", '{"min_length": 11}')

    body = client.get(f"/policies/{policy_id}").text
    assert "Console PW" in body
    assert "min_length" in body


def test_out_of_range_value_is_reported_not_swallowed(client: TestClient):
    """The form submits raw values; the spec's own constraints still bind."""
    response = client.post(
        "/policies",
        data={"name": "Bad", "policy_type": "PASSWORD", "min_length": "999"},
        follow_redirects=True,
    )

    assert "error" in response.url.query.decode()
    assert client.get("/policies").text.count("Bad") == 0


def test_duplicate_name_is_reported(client: TestClient):
    create_policy(client, "Dupe", "PASSWORD", '{"min_length": 8}')

    response = client.post(
        "/policies",
        data={"name": "Dupe", "policy_type": "PASSWORD", "min_length": "8"},
        follow_redirects=True,
    )

    assert "already exists" in text_of(response.text)


def test_publishing_a_version_keeps_the_previous_one(client: TestClient):
    policy_id = create_policy(client, "Versioned", "PASSWORD", '{"min_length": 6}')

    client.post(
        f"/policies/{policy_id}/versions",
        data={"min_length": "14"},
        follow_redirects=True,
    )

    body = text_of(client.get(f"/policies/{policy_id}").text)
    assert "v2" in body and "v1" in body
    latest = client.get(f"/api/v1/policies/{policy_id}", headers=ADMIN).json()["versions"][-1]
    assert latest["spec"] == {"min_length": 14}


def test_policy_form_shows_merge_hints(client: TestClient):
    """The form must keep stacking legible — D64's concern, answered per field."""
    policy_id = create_policy(client, "Apps", "APP_CATALOG", "{}")

    body = text_of(client.get(f"/policies/{policy_id}").text)
    assert "only entries present in every policy survive" in body  # INTERSECT
    assert "combine by key" in body  # MERGE_BY_KEY


# --------------------------------------------------------------------------- #
# Form-driven policy editing (W10)
# --------------------------------------------------------------------------- #


def _stored_spec(client: TestClient, policy_id: str) -> dict:
    return client.get(f"/api/v1/policies/{policy_id}", headers=ADMIN).json()["versions"][-1]["spec"]


def _create_via_form(client: TestClient, name: str, policy_type: str, fields) -> str:
    data: dict = {"name": name, "policy_type": policy_type}
    for key, value in fields:
        if key in data:
            existing = data[key] if isinstance(data[key], list) else [data[key]]
            data[key] = existing + [value]
        else:
            data[key] = value
    r = client.post("/policies", data=data, follow_redirects=True)
    assert r.status_code == 200, r.text
    return r.url.path.rsplit("/", 1)[-1]


def test_new_policy_page_renders_typed_controls_for_every_wired_type(client: TestClient):
    body = client.get("/policies/new/single").text
    assert 'name="min_length"' in body            # PASSWORD int
    assert 'name="allow_camera"' in body          # RESTRICTIONS tri-state
    assert 'name="blocked_packages"' in body      # APP_CATALOG list
    assert 'data-rowset="required_apps"' in body  # APP_CATALOG object list
    assert 'name="entries__file_id"' in body      # FILES object list
    assert "Spec (JSON)" not in body


def test_password_form_round_trip(client: TestClient):
    pid = _create_via_form(
        client, "PW form", "PASSWORD",
        [("min_length", "12"), ("min_digits", "2"), ("expiration_days", "")],
    )
    # min_length and min_digits stored; expiration_days left blank -> omitted
    assert _stored_spec(client, pid) == {"min_length": 12, "min_digits": 2}


def test_set_password_round_trips_and_shows_in_the_admin_ui(client: TestClient):
    pid = _create_via_form(
        client, "Fixed PW", "PASSWORD",
        [("min_length", "6"), ("set_password", "atlas12")],
    )
    assert _stored_spec(client, pid) == {"min_length": 6, "set_password": "atlas12"}
    # W21: the admin console shows the set passcode in plain text (it is masked
    # only on the on-device app, where the device user could read it).
    body = client.get(f"/policies/{pid}").text
    assert "atlas12" in body


def test_restrictions_tri_state(client: TestClient):
    pid = _create_via_form(
        client, "Restr form", "RESTRICTIONS",
        [("allow_camera", "false"), ("allow_bluetooth", "true"), ("allow_screen_capture", "")],
    )
    spec = _stored_spec(client, pid)
    assert spec == {"allow_camera": False, "allow_bluetooth": True}
    assert "allow_screen_capture" not in spec  # "Not managed" omits it


def test_package_list_round_trip(client: TestClient):
    pid = _create_via_form(
        client, "Blocklist form", "APP_CATALOG",
        [("blocked_packages", "com.foo"), ("blocked_packages", "com.bar"),
         ("blocked_packages", ""), ("blocked_packages", "com.foo")],  # blank + dupe
    )
    assert _stored_spec(client, pid) == {"blocked_packages": ["com.foo", "com.bar"]}


def test_file_list_round_trip(client: TestClient):
    fid = _upload_file(client, b"payload", "map.xml")
    pid = _create_via_form(
        client, "Files form", "FILES",
        [
            ("entries__file_id", fid), ("entries__dest_path", "/sdcard/atak/imagery"),
            ("entries__availability", "optional"), ("entries__persist", "no"),
            ("entries__extract", ""), ("entries__extract_to", ""),
            ("entries__overwrite", "always"),
        ],
    )
    spec = _stored_spec(client, pid)
    assert spec["entries"][0]["file_id"] == fid
    assert spec["entries"][0]["dest_path"] == "/sdcard/atak/imagery"
    assert spec["entries"][0]["availability"] == "optional"
    assert spec["entries"][0]["persist"] is False


def test_an_all_unmanaged_form_makes_an_empty_policy(client: TestClient):
    pid = _create_via_form(client, "Empty form", "RESTRICTIONS", [("allow_camera", "")])
    assert _stored_spec(client, pid) == {}


# --------------------------------------------------------------------------- #
# Sub-paged policy categories (W12)
# --------------------------------------------------------------------------- #


def test_creator_rail_shows_subpages(client: TestClient):
    body = client.get("/policies/new").text
    # App Management splits into a sub-page per field
    assert 'data-page="app_management:required-apps"' in body
    assert 'data-page="app_management:blocklist"' in body
    # Kiosk left App Management in W59 and is its own category now.
    assert 'data-page="app_management:kiosk"' not in body
    assert 'data-page="kiosk:single-app"' in body
    assert 'data-page="kiosk:kiosk-exit-settings"' in body
    # Restrictions splits by group
    assert 'data-page="restrictions:device-functionality"' in body


# The marker is now always in the markup and shown or hidden by the `hidden`
# attribute, because atlas.js toggles it live as the operator types — the server
# only decides the *initial* state (W47). "No check" therefore means present and
# hidden, not absent.
_VISIBLE_CHECK = 'class="rail-check" >'
_HIDDEN_CHECK = 'class="rail-check" hidden>'


def test_subpage_and_category_show_a_check_when_a_field_is_set(client: TestClient):
    # allow_camera lives on the "Device functionality" sub-page of Restrictions
    pid = _make_profile(client, "Locked", {"restrictions": {"allow_camera": False}})

    body = client.get(f"/profiles/{pid}").text
    # the sub-page link carries the check
    link = body[body.index('data-page="restrictions:device-functionality"'):]
    assert _VISIBLE_CHECK in link[: link.index("</a>")]
    # and the category header does too
    head = body[body.index('data-cat-group="restrictions"'):]
    assert _VISIBLE_CHECK in head[: head.index("</a>")]


def test_a_pristine_subpage_has_no_check(client: TestClient):
    pid = _make_profile(client, "Partly", {"restrictions": {"allow_camera": False}})
    body = client.get(f"/profiles/{pid}").text
    # "Display" (screen_timeout_seconds) was not set
    link = body[body.index('data-page="restrictions:display"'):]
    assert _HIDDEN_CHECK in link[: link.index("</a>")]


def test_the_policy_maker_starts_with_every_check_hidden(client: TestClient):
    """A brand-new policy has no saved spec, so the server can only ever render
    them hidden — this is the case that made the feature look missing entirely,
    since `/policies/new` builds its rail with no profile at all."""
    body = client.get("/policies/new").text

    assert _HIDDEN_CHECK in body
    assert _VISIBLE_CHECK not in body


def test_networks_wifi_subpage(client: TestClient):
    body = client.get("/policies/new").text
    assert 'data-page="networks:wi-fi"' in body
    assert 'name="wifi_networks__ssid"' in body
    assert "vpn_profiles" not in body  # VPN dropped (W14)


def test_wifi_form_round_trip(client: TestClient):
    pid = _create_via_form(
        client, "Wi-Fi policy", "NETWORKS",
        [
            ("wifi_networks__ssid", "TAK-Field"),
            ("wifi_networks__security", "wpa_psk"),
            ("wifi_networks__password", "hunter22"),
            ("wifi_networks__hidden", "yes"),
        ],
    )
    spec = _stored_spec(client, pid)
    entry = spec["wifi_networks"][0]
    assert entry["ssid"] == "TAK-Field"
    assert entry["password"] == "hunter22"
    assert entry["hidden"] is True
    # auto_join / mac_randomization were dropped in W18 (both @SystemApi for a DO)
    assert "auto_join" not in entry
    assert "mac_randomization" not in entry


def test_wifi_short_password_is_rejected(client: TestClient):
    r = client.post(
        "/policies",
        data={
            "name": "Bad wifi", "policy_type": "NETWORKS",
            "wifi_networks__ssid": "x", "wifi_networks__security": "wpa_psk",
            "wifi_networks__password": "short",
        },
        follow_redirects=True,
    )
    assert "error" in r.url.query.decode()


def test_networks_reaches_the_effective_policy(client: TestClient, enrolled):
    device = enrolled(serial="W13-NET")
    pid = _make_profile(
        client, "Netted",
        {"networks": {"wifi_networks": [{"ssid": "Ops", "security": "open"}]}},
    )
    client.put(
        f"/api/v1/profiles/{pid}/targets",
        json={"device_ids": [device["device_id"]]},
        headers=ADMIN,
    )
    values = client.get(
        f"/api/v1/devices/{device['device_id']}/effective-policy"
    ).json()["values"]
    assert values["NETWORKS"]["wifi_networks"][0]["ssid"] == "Ops"


def test_the_whole_policy_is_one_form_across_every_category(client: TestClient):
    """W21: one editor form covers all categories, so one save keeps everything."""
    pid = _make_profile(
        client,
        "Full restr",
        {"restrictions": {"allow_camera": False, "screen_timeout_seconds": 120}},
    )
    body = client.get(f"/profiles/{pid}").text

    form_start = body.index('action="/profiles/' + pid + '"')
    form_end = body.index("</form>", form_start)
    section = body[form_start:form_end]
    # controls from more than one category live in the single form
    assert 'name="allow_camera"' in section       # RESTRICTIONS
    assert 'name="screen_timeout_seconds"' in section
    assert 'value="120"' in section
    assert 'name="min_length"' in section          # PASSWORD — a category not yet filled

    # one submit carrying several categories writes them all
    client.post(
        f"/profiles/{pid}",
        data={"allow_camera": "true", "screen_timeout_seconds": "120", "min_length": "9"},
        follow_redirects=False,
    )
    sections = client.get(f"/api/v1/profiles/{pid}", headers=ADMIN).json()["sections"]
    by_type = {s["policy_type"]: s["versions"][-1]["spec"] for s in sections}
    assert by_type["RESTRICTIONS"] == {"allow_camera": True, "screen_timeout_seconds": 120}
    assert by_type["PASSWORD"] == {"min_length": 9}


# --------------------------------------------------------------------------- #
# Policy list: tabs, templates, archive/restore (W3)
# --------------------------------------------------------------------------- #


def test_policies_page_has_the_three_tabs_and_a_new_policy_button(client: TestClient):
    body = client.get("/policies").text
    for label in ("Device policies", "Templates", "Archived"):
        assert label in body
    assert 'data-modal-open="new-policy"' in body


def test_create_from_scratch_page_renders_form_controls(client: TestClient):
    body = client.get("/policies/new").text
    assert "Not managed" in body        # the tri-state option
    assert "Camera" in body             # a RESTRICTIONS field label
    assert "Password quality" in body   # a PASSWORD field label
    assert "Spec (JSON)" not in body    # no JSON typing (DW6)


def test_save_as_template_makes_a_template(client: TestClient):
    policy_id = create_policy(client, "PW Base", "PASSWORD", '{"min_length": 10}')

    client.post(
        "/policies/clone",
        data={"source_id": policy_id, "name": "PW Base (template)", "as_template": "true"},
        follow_redirects=False,
    )

    templates_body = client.get("/policies").text
    assert "PW Base (template)" in templates_body
    # And it is flagged as a template, not assignable
    tid = client.get("/api/v1/policies", params={"include_archived": True}, headers=ADMIN)
    made = [p for p in tid.json() if p["name"] == "PW Base (template)"][0]
    assert made["is_template"] is True


def test_using_a_template_creates_an_independent_policy(client: TestClient, enrolled):
    template_id = create_policy(client, "Kiosk src", "PASSWORD", '{"min_length": 12}')
    client.post(
        "/policies/clone",
        data={"source_id": template_id, "name": "Kiosk tmpl", "as_template": "true"},
    )
    tmpl = client.get("/api/v1/policies", params={"include_archived": True}, headers=ADMIN).json()
    tmpl_id = [p for p in tmpl if p["is_template"]][0]["id"]

    resp = client.post(
        "/policies/clone",
        data={"source_id": tmpl_id, "name": "Kiosk North"},
        follow_redirects=True,
    )

    assert resp.status_code == 200
    new = client.get("/api/v1/policies", headers=ADMIN).json()
    clone = [p for p in new if p["name"] == "Kiosk North"][0]
    assert clone["is_template"] is False
    assert clone["versions"][0]["spec"] == {"min_length": 12}


def test_a_template_cannot_be_assigned(client: TestClient, enrolled):
    device = enrolled(serial="W3-TMPL")
    policy_id = create_policy(client, "T", "PASSWORD", '{"min_length": 9}')
    client.post("/policies/clone", data={"source_id": policy_id, "name": "T copy", "as_template": "true"})
    tmpl_id = [
        p for p in client.get("/api/v1/policies", params={"include_archived": True}, headers=ADMIN).json()
        if p["is_template"]
    ][0]["id"]

    response = client.post(
        "/api/v1/assignments",
        json={"policy_id": tmpl_id, "scope": "device", "target_id": device["device_id"]},
        headers=ADMIN,
    )
    assert response.status_code == 409
    assert "template" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# Composite policies / profiles (W4)
# --------------------------------------------------------------------------- #


def test_profile_creator_lists_every_category(client: TestClient):
    from app.policies.creator_catalog import CATALOG

    body = client.get("/policies/new").text
    for category in CATALOG:
        assert category.label in body


def test_placeholder_category_says_not_available(client: TestClient):
    body = text_of(client.get("/policies/new").text)
    assert "Not available yet" in body  # e.g. Knox, VPN, geofencing


def test_create_profile_through_the_console_form(client: TestClient):
    response = client.post(
        "/profiles",
        data={
            "name": "Console Profile",
            "description": "made via the form",
            "spec__password": '{"min_length": 10}',
            "spec__restrictions": "{}",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    body = text_of(response.text)
    assert "Console Profile" in body
    # The editor page shows each category in the rail
    assert "Password" in body and "Restrictions" in body


def test_profile_editor_page_renders_and_offers_archive(client: TestClient):
    pid = _make_profile(client, "Editable", {"password": {"min_length": 9}})
    body = client.get(f"/profiles/{pid}").text
    assert 'action="/profiles/' in body
    assert "Archive" in text_of(body)
    assert "data-policy-form" in body  # W21: the unsaved-change guard hooks this


def test_one_save_adds_a_category_and_emptying_one_removes_it(client: TestClient):
    pid = _make_profile(client, "Evolving", {"password": {"min_length": 9}})

    # add RESTRICTIONS, keep PASSWORD, in a single save
    client.post(
        f"/profiles/{pid}",
        data={"min_length": "9", "allow_camera": "false"},
        follow_redirects=False,
    )
    sections = client.get(f"/api/v1/profiles/{pid}", headers=ADMIN).json()["sections"]
    assert {s["policy_type"] for s in sections} == {"PASSWORD", "RESTRICTIONS"}

    # empty PASSWORD out -> the category is dropped
    client.post(f"/profiles/{pid}", data={"allow_camera": "false"}, follow_redirects=False)
    sections = client.get(f"/api/v1/profiles/{pid}", headers=ADMIN).json()["sections"]
    assert {s["policy_type"] for s in sections} == {"RESTRICTIONS"}


def test_a_section_policy_redirects_to_its_composite(client: TestClient):
    pid = _make_profile(client, "Composite", {"password": {"min_length": 9}})
    child_id = client.get(f"/api/v1/profiles/{pid}", headers=ADMIN).json()["sections"][0]["id"]

    r = client.get(f"/policies/{child_id}", follow_redirects=False)
    assert r.status_code in (302, 303, 307)
    assert r.headers["location"] == f"/profiles/{pid}"


def _make_profile(client: TestClient, name: str, sections: dict) -> str:
    r = client.post("/api/v1/profiles", json={"name": name, "sections": sections}, headers=ADMIN)
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_create_profile_makes_children_only_for_filled_sections(client: TestClient):
    pid = _make_profile(
        client,
        "Field Baseline",
        {"password": {"min_length": 10}, "restrictions": {}},
    )

    profile = client.get(f"/api/v1/profiles/{pid}", headers=ADMIN).json()
    keys = {s["profile_section"] for s in profile["sections"]}
    assert keys == {"password"}
    assert profile["sections"][0]["versions"][0]["spec"] == {"min_length": 10}


def test_profile_shows_on_the_device_policies_tab_and_children_do_not(client: TestClient):
    _make_profile(client, "Kiosk Profile", {"password": {"min_length": 12}})

    body = client.get("/policies").text
    assert "Kiosk Profile" in body
    # The child policy is named "Kiosk Profile · Password" — it must not be listed
    assert "Kiosk Profile · Password" not in body


def test_child_policies_are_absent_from_the_standalone_policy_api(client: TestClient):
    _make_profile(client, "P", {"password": {"min_length": 9}})

    standalone = client.get("/api/v1/policies", headers=ADMIN).json()
    assert all(p["profile_id"] is None for p in standalone)


def test_editing_a_section_publishes_a_new_version(client: TestClient):
    pid = _make_profile(client, "Evolving", {"password": {"min_length": 8}})

    client.post(
        f"/profiles/{pid}/sections/password",
        data={"min_length": "14"},
        follow_redirects=False,
    )

    section = client.get(f"/api/v1/profiles/{pid}", headers=ADMIN).json()["sections"][0]
    assert [v["version"] for v in section["versions"]] == [1, 2]
    assert section["versions"][-1]["spec"] == {"min_length": 14}


def test_adding_a_section_later(client: TestClient):
    pid = _make_profile(client, "Growing", {"password": {"min_length": 8}})

    client.post(
        f"/profiles/{pid}/sections/app_management",
        data={"blocked_packages": "com.foo.bar"},
        follow_redirects=False,
    )

    keys = {s["profile_section"] for s in client.get(f"/api/v1/profiles/{pid}", headers=ADMIN).json()["sections"]}
    assert keys == {"password", "app_management"}


def test_removing_a_section(client: TestClient):
    pid = _make_profile(
        client, "Shrinking", {"password": {"min_length": 8}, "restrictions": {"allow_camera": False}}
    )

    client.post(f"/profiles/{pid}/sections/restrictions/remove", follow_redirects=False)

    keys = {s["profile_section"] for s in client.get(f"/api/v1/profiles/{pid}", headers=ADMIN).json()["sections"]}
    assert keys == {"password"}


def test_a_profile_section_cannot_be_assigned_directly(client: TestClient, enrolled):
    device = enrolled(serial="W4-SEC")
    pid = _make_profile(client, "PP", {"password": {"min_length": 11}})
    child_id = client.get(f"/api/v1/profiles/{pid}", headers=ADMIN).json()["sections"][0]["id"]

    resp = client.post(
        "/api/v1/assignments",
        json={"policy_id": child_id, "scope": "device", "target_id": device["device_id"]},
        headers=ADMIN,
    )
    assert resp.status_code == 409
    assert "profile" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# Profile assignment & resolution (W4b)
# --------------------------------------------------------------------------- #


def _effective(client: TestClient, device_id: str) -> dict:
    return client.get(f"/api/v1/devices/{device_id}/effective-policy").json()


def test_assigning_a_profile_resolves_all_its_sections(client: TestClient, enrolled):
    device = enrolled(serial="W4B-ALL")
    pid = _make_profile(
        client,
        "Full Profile",
        {
            "password": {"min_length": 12},
            "app_management": {"blocked_packages": ["com.bad.app"]},
        },
    )

    result = client.put(
        f"/api/v1/profiles/{pid}/targets",
        json={"device_ids": [device["device_id"]], "rank": 10},
        headers=ADMIN,
    )
    assert result.status_code == 200, result.text

    values = _effective(client, device["device_id"])["values"]
    assert values["PASSWORD"]["min_length"] == 12
    assert values["APP_CATALOG"]["blocked_packages"] == ["com.bad.app"]


def test_profile_stacks_against_a_standalone_policy_by_rank(
    client: TestClient, enrolled, assign
):
    device = enrolled(serial="W4B-RANK")
    standalone = create_policy(
        client, "Loose kiosk", "KIOSK", '{"kiosk_package": "com.standalone"}'
    )
    assign(standalone, device["device_id"], rank=1)
    pid = _make_profile(
        client, "Tight kiosk", {"kiosk": {"kiosk_package": "com.profile"}}
    )
    client.put(
        f"/api/v1/profiles/{pid}/targets",
        json={"device_ids": [device["device_id"]], "rank": 99},
        headers=ADMIN,
    )

    # Profile at rank 99 wins the HIGHEST_RANK field.
    assert _effective(client, device["device_id"])["values"]["KIOSK"][
        "kiosk_package"
    ] == "com.profile"


def test_unassigning_a_profile_clears_its_sections(client: TestClient, enrolled):
    device = enrolled(serial="W4B-UNASSIGN")
    pid = _make_profile(client, "Temp Profile", {"password": {"min_length": 13}})
    client.put(
        f"/api/v1/profiles/{pid}/targets",
        json={"device_ids": [device["device_id"]]},
        headers=ADMIN,
    )
    assert _effective(client, device["device_id"])["values"] != {}

    client.put(
        f"/api/v1/profiles/{pid}/targets", json={"device_ids": []}, headers=ADMIN
    )

    assert _effective(client, device["device_id"])["values"] == FLEET_DEFAULT


def test_archiving_an_assigned_profile_stops_it_applying(client: TestClient, enrolled):
    device = enrolled(serial="W4B-ARCH")
    pid = _make_profile(client, "Doomed Profile", {"password": {"min_length": 14}})
    client.put(
        f"/api/v1/profiles/{pid}/targets",
        json={"device_ids": [device["device_id"]]},
        headers=ADMIN,
    )
    assert _effective(client, device["device_id"])["values"] != {}

    client.post(f"/api/v1/profiles/{pid}/archive", headers=ADMIN)

    assert _effective(client, device["device_id"])["values"] == FLEET_DEFAULT


def test_archive_from_the_list_shows_an_impact_modal(client: TestClient, enrolled):
    device = enrolled(serial="W22-MODAL")
    pid = _make_profile(client, "Kiosk Baseline", {"password": {"min_length": 12}})
    client.put(
        f"/api/v1/profiles/{pid}/targets",
        json={"device_ids": [device["device_id"]]},
        headers=ADMIN,
    )

    body = client.get("/policies").text
    assert f'data-modal-open="archive-{pid}"' in body      # the quick button
    assert f'id="archive-{pid}"' in body                   # the modal
    assert "Password" in body and "Minimum length" in body  # what it does
    assert "W22-MODAL" in body                             # device it is on
    assert f'action="/profiles/{pid}/archive"' in body     # confirm target
    assert "Cancel" in body


def test_archiving_a_profile_drops_its_assignments(client: TestClient, enrolled):
    device = enrolled(serial="W22-DROP")
    pid = _make_profile(client, "Droppable", {"password": {"min_length": 13}})
    client.put(
        f"/api/v1/profiles/{pid}/targets",
        json={"device_ids": [device["device_id"]]},
        headers=ADMIN,
    )

    client.post(f"/profiles/{pid}/archive", follow_redirects=False)

    profile = client.get(f"/api/v1/profiles/{pid}", headers=ADMIN).json()
    assert profile["assignments"] == [] if "assignments" in profile else True
    assert _effective(client, device["device_id"])["values"] == FLEET_DEFAULT

    # restored profile is back but assigned to nothing
    client.post(f"/profiles/{pid}/restore", follow_redirects=False)
    assert _effective(client, device["device_id"])["values"] == FLEET_DEFAULT
    assert "Droppable" in client.get("/policies").text


def test_archived_profile_appears_in_the_archived_tab(client: TestClient):
    pid = _make_profile(client, "Old Baseline", {"password": {"min_length": 8}})
    client.post(f"/profiles/{pid}/archive", follow_redirects=False)

    body = client.get("/policies").text
    tail = body.split('data-tab-panel="archived"')[1]
    assert "Old Baseline" in tail
    assert f'action="/profiles/{pid}/restore"' in tail


def test_removing_a_section_stops_it_applying(client: TestClient, enrolled):
    device = enrolled(serial="W4B-RMSEC")
    pid = _make_profile(
        client,
        "Two Section",
        {"password": {"min_length": 11}, "kiosk": {"kiosk_package": "com.k"}},
    )
    client.put(
        f"/api/v1/profiles/{pid}/targets",
        json={"device_ids": [device["device_id"]]},
        headers=ADMIN,
    )

    client.delete(f"/api/v1/profiles/{pid}/sections/app_management", headers=ADMIN)

    values = _effective(client, device["device_id"])["values"]
    assert "PASSWORD" in values
    assert "APP_CATALOG" not in values


def test_editing_a_section_bumps_the_device_state_version(client: TestClient, enrolled):
    device = enrolled(serial="W4B-WAKE")
    pid = _make_profile(client, "Living Profile", {"password": {"min_length": 8}})
    client.put(
        f"/api/v1/profiles/{pid}/targets",
        json={"device_ids": [device["device_id"]]},
        headers=ADMIN,
    )
    _effective(client, device["device_id"])  # materialise the cache
    before = client.get(f"/api/v1/devices/{device['device_id']}", headers=ADMIN).json()[
        "state_version"
    ]

    client.put(
        f"/api/v1/profiles/{pid}/sections/password",
        json={"spec": {"min_length": 15}},
        headers=ADMIN,
    )
    _effective(client, device["device_id"])

    after = client.get(f"/api/v1/devices/{device['device_id']}", headers=ADMIN).json()[
        "state_version"
    ]
    assert after > before


def test_profile_editor_assign_form_assigns(client: TestClient, enrolled):
    device = enrolled(serial="W4B-FORM")
    pid = _make_profile(client, "Form Profile", {"password": {"min_length": 10}})

    body = client.get(f"/profiles/{pid}").text
    assert 'action="/profiles/' in body and "Assign to devices" in text_of(body)

    client.post(
        f"/profiles/{pid}/targets",
        data={"rank": "20", "device_ids": [device["device_id"]]},
        follow_redirects=False,
    )

    assert _effective(client, device["device_id"])["values"]["PASSWORD"]["min_length"] == 10


def test_profile_name_shows_in_the_fleet_table(client: TestClient, enrolled):
    device = enrolled(serial="W4B-FLEET")
    pid = _make_profile(client, "Fleet Profile", {"password": {"min_length": 9}})
    client.put(
        f"/api/v1/profiles/{pid}/targets",
        json={"device_ids": [device["device_id"]]},
        headers=ADMIN,
    )

    assert "Fleet Profile" in text_of(client.get("/").text)


def test_archive_then_restore_round_trip(client: TestClient, enrolled, assign):
    device = enrolled(serial="W3-ARCH")
    policy_id = create_policy(client, "Retire me", "PASSWORD", '{"min_length": 11}')
    assign(policy_id, device["device_id"], rank=5)

    client.post(f"/policies/{policy_id}/archive", follow_redirects=False)

    # Gone from the device tab, present in archived, no longer applied
    assert "Retire me" not in text_of(client.get("/policies").text).split("Archived")[0]
    assert client.get(
        f"/api/v1/devices/{device['device_id']}/effective-policy"
    ).json()["values"] == FLEET_DEFAULT

    client.post(f"/policies/{policy_id}/restore", follow_redirects=False)

    assert client.get(
        f"/api/v1/devices/{device['device_id']}/effective-policy"
    ).json()["values"]["PASSWORD"]["min_length"] == 11


# --------------------------------------------------------------------------- #
# Bulk assignment (F2)
# --------------------------------------------------------------------------- #


def test_assign_one_policy_to_several_devices(client: TestClient, enrolled):
    devices = [enrolled(serial=f"UI-BULK-{i}") for i in range(3)]
    policy_id = create_policy(client, "Fleet PW", "PASSWORD", '{"min_length": 9}')

    response = client.post(
        f"/policies/{policy_id}/targets",
        data={"rank": "40", "device_ids": [d["device_id"] for d in devices]},
        follow_redirects=True,
    )

    assert response.status_code == 200
    for device in devices:
        state = client.get(
            f"/api/v1/devices/{device['device_id']}/effective-policy"
        ).json()
        assert state["values"]["PASSWORD"]["min_length"] == 9


def test_unticking_a_device_removes_the_assignment(client: TestClient, enrolled):
    """The form describes the complete target set, so removal happens here too."""
    keep = enrolled(serial="UI-KEEP")
    drop = enrolled(serial="UI-DROP")
    policy_id = create_policy(client, "Fleet PW", "PASSWORD", '{"min_length": 9}')

    client.post(
        f"/policies/{policy_id}/targets",
        data={"rank": "10", "device_ids": [keep["device_id"], drop["device_id"]]},
        follow_redirects=True,
    )
    client.post(
        f"/policies/{policy_id}/targets",
        data={"rank": "10", "device_ids": [keep["device_id"]]},
        follow_redirects=True,
    )

    assert client.get(
        f"/api/v1/devices/{drop['device_id']}/effective-policy"
    ).json()["values"] == FLEET_DEFAULT
    assert client.get(
        f"/api/v1/devices/{keep['device_id']}/effective-policy"
    ).json()["values"]["PASSWORD"]["min_length"] == 9


def test_assignment_checkboxes_reflect_current_state(client: TestClient, enrolled):
    device = enrolled(serial="UI-CHECKED")
    policy_id = create_policy(client, "Fleet PW", "PASSWORD", '{"min_length": 9}')
    client.post(
        f"/policies/{policy_id}/targets",
        data={"rank": "10", "device_ids": [device["device_id"]]},
        follow_redirects=True,
    )

    body = client.get(f"/policies/{policy_id}").text
    marker = f'value="{device["device_id"]}"'
    assert marker in body
    assert "checked" in body[body.index(marker) : body.index(marker) + 120]


# --------------------------------------------------------------------------- #
# Stacking view
# --------------------------------------------------------------------------- #


def test_device_page_explains_where_a_value_came_from(client: TestClient, enrolled, assign):
    device = enrolled(serial="UI-PROV")
    weak = create_policy(client, "Convenience", "PASSWORD", '{"min_length": 4}')
    strong = create_policy(client, "Hardened", "PASSWORD", '{"min_length": 12}')
    assign(weak, device["device_id"], rank=99)
    assign(strong, device["device_id"], rank=1)

    body = text_of(client.get(f"/devices/{device['device_id']}").text)

    assert "min_length" in body
    assert "Hardened" in body          # the winning source is named
    assert "max" in body                # the strategy that decided it
    assert "Convenience" in body        # and what it beat


def test_device_page_lists_policies_in_resolution_order(client: TestClient, enrolled, assign):
    device = enrolled(serial="UI-ORDER")
    low = create_policy(client, "Low Rank", "PASSWORD", '{"min_length": 4}')
    high = create_policy(client, "High Rank", "PASSWORD", '{"min_length": 6}')
    assign(low, device["device_id"], rank=1)
    assign(high, device["device_id"], rank=99)

    body = client.get(f"/devices/{device['device_id']}").text

    assert body.index("High Rank") < body.index("Low Rank")


def test_device_page_surfaces_conflicts(client: TestClient, enrolled, assign):
    device = enrolled(serial="UI-CONFLICT")
    first = create_policy(client, "Field Kiosk", "KIOSK", '{"kiosk_package": "com.atakmap.app"}')
    second = create_policy(client, "Warehouse", "KIOSK", '{"kiosk_package": "com.scanner"}')
    assign(first, device["device_id"], rank=50)
    assign(second, device["device_id"], rank=10)

    body = text_of(client.get(f"/devices/{device['device_id']}").text)

    assert "conflict" in body.lower()
    assert "com.scanner" in body


def test_unknown_device_is_404(client: TestClient):
    assert client.get("/devices/00000000-0000-0000-0000-000000000000").status_code == 404


# --------------------------------------------------------------------------- #
# Enrollment and QR
# --------------------------------------------------------------------------- #


def test_enrollment_page_renders(client: TestClient):
    assert client.get("/enrollment").status_code == 200


def test_enrollment_page_starts_empty(client: TestClient):
    """No primary yet: the create form, not a device-bricking QR attempt."""
    body = text_of(client.get("/enrollment").text)
    assert "No active enrollment token" in body


def test_creating_the_primary_renders_its_qr_directly(client: TestClient):
    """No redirect to a per-token page any more — there is no such page."""
    response = client.post(
        "/enrollment/primary", data={"name": "Fleet enrollment"}, follow_redirects=True
    )

    assert response.status_code == 200
    assert "Fleet enrollment" in response.text


def test_qr_is_withheld_without_a_signature_checksum(client: TestClient):
    """Matches the API's behaviour: no payload beats one that fails on the tablet."""
    response = client.post(
        "/enrollment/primary", data={"name": "No checksum"}, follow_redirects=True
    )

    assert "<svg" not in response.text
    assert "no agent signature checksum available" in text_of(response.text)
    # The way out is named, because the operator hit this on a fresh install with
    # nothing uploaded and the old wording only named an environment variable.
    assert "Upload a build of the agent app" in text_of(response.text)


def test_qr_renders_when_a_checksum_is_configured(client: TestClient, settings):
    from app.api.deps import get_settings
    from app.main import app

    configured = settings.model_copy(update={"agent_signature_checksum": "abc123"})
    app.dependency_overrides[get_settings] = lambda: configured
    try:
        response = client.post(
            "/enrollment/primary", data={"name": "With checksum"}, follow_redirects=True
        )
        assert "<svg" in response.text
        assert "factory-reset" in text_of(response.text)
    finally:
        app.dependency_overrides[get_settings] = lambda: settings


def configured_checksum(client: TestClient, settings):
    """Enable QR rendering for a test by supplying a signature checksum."""
    from app.api.deps import get_settings
    from app.main import app

    configured = settings.model_copy(update={"agent_signature_checksum": "abc123"})
    app.dependency_overrides[get_settings] = lambda: configured
    return lambda: app.dependency_overrides.__setitem__(get_settings, lambda: settings)


def test_generate_qr_can_be_pressed_again(client: TestClient, settings):
    """No per-token page to revisit any more — 'come back later' means press it again."""
    restore = configured_checksum(client, settings)
    try:
        client.post("/enrollment/primary", data={"name": "Reusable"})

        again = client.post("/enrollment/qr")

        assert again.status_code == 200
        assert "<svg" in again.text
    finally:
        restore()


def test_enrollment_page_shows_the_active_primary(client: TestClient):
    client.post("/enrollment/primary", data={"name": "Listed"})

    body = text_of(client.get("/enrollment").text)
    assert "Listed" in body
    assert "Generate enrollment QR" in body


def test_wifi_credentials_are_embedded_when_supplied(client: TestClient, settings):
    restore = configured_checksum(client, settings)
    try:
        client.post("/enrollment/primary", data={"name": "Wifi"})

        response = client.post(
            "/enrollment/qr",
            data={
                "wifi_ssid": "TAK-Field",
                "wifi_password": "hunter2",
                "wifi_security": "WPA",
            },
        )

        body = response.text
        assert "PROVISIONING_WIFI_SSID" in body
        assert "TAK-Field" in body
        assert "Wi-Fi embedded" in text_of(body)
    finally:
        restore()


def test_wifi_password_is_not_persisted(client: TestClient, settings, db):
    """It is used for one render; storing it would be a second recoverable secret."""
    from sqlalchemy import select

    from app.db.models import EnrollmentToken

    restore = configured_checksum(client, settings)
    try:
        client.post("/enrollment/primary", data={"name": "Wifi"})
        client.post(
            "/enrollment/qr",
            data={"wifi_ssid": "TAK-Field", "wifi_password": "hunter2"},
        )

        token = db.scalars(
            select(EnrollmentToken).where(EnrollmentToken.name == "Wifi")
        ).one()
        assert "hunter2" not in str(token.__dict__)

        # And generating again, with no wifi fields this time, does not carry it
        # forward — each QR is minted fresh, with no memory of the last one.
        assert "hunter2" not in client.post("/enrollment/qr").text
    finally:
        restore()


def test_qr_refuses_once_the_primary_is_revoked(client: TestClient, settings):
    """The primary is what verification re-checks on every use; revoking it while
    a QR is still within its own 15 minutes must still refuse."""
    restore = configured_checksum(client, settings)
    try:
        client.post("/enrollment/primary", data={"name": "Doomed"})
        primary_id = client.get("/api/v1/enrollment-tokens/primary").json()["id"]
        client.post(f"/api/v1/enrollment-tokens/{primary_id}/revoke")

        response = client.post("/enrollment/qr")

        assert "<svg" not in response.text
        assert "no active enrollment token" in text_of(response.text)
    finally:
        restore()


def test_no_route_exists_for_a_per_token_qr_page(client: TestClient):
    """There is nothing to look up by id any more — every QR is minted fresh."""
    assert client.get(
        "/enrollment/00000000-0000-0000-0000-000000000000/qr"
    ).status_code == 404


def test_token_scoping_from_the_form(client: TestClient):
    group = client.post("/api/v1/groups", json={"name": "Console Group"}).json()

    client.post(
        "/enrollment/primary",
        data={"name": "Scoped", "group_ids": [group["id"]]},
    )

    primary = client.get("/api/v1/enrollment-tokens/primary").json()
    assert primary["name"] == "Scoped" and primary["groups"]


def test_retiring_without_replacing_clears_the_primary(client: TestClient):
    client.post("/enrollment/primary", data={"name": "Temporary"})
    assert client.get("/api/v1/enrollment-tokens/primary").json() is not None

    client.post("/enrollment/retire", follow_redirects=False)

    assert client.get("/api/v1/enrollment-tokens/primary").json() is None


def test_retire_and_create_replaces_in_one_call(client: TestClient):
    client.post("/enrollment/primary", data={"name": "First"})
    first_id = client.get("/api/v1/enrollment-tokens/primary").json()["id"]

    client.post("/enrollment/primary", data={"name": "Second"})

    primary = client.get("/api/v1/enrollment-tokens/primary").json()
    assert primary["name"] == "Second"
    assert primary["id"] != first_id


# --------------------------------------------------------------------------- #
# Diagnostics
# --------------------------------------------------------------------------- #


def test_device_page_offers_log_collection(client: TestClient, enrolled):
    device = enrolled(serial="UI-LOGS")

    body = client.get(f"/devices/{device['device_id']}").text

    assert "Collect logs" in body
    assert f"/devices/{device['device_id']}/collect-logs" in body


def test_device_page_says_when_no_logs_exist(client: TestClient, enrolled):
    device = enrolled(serial="UI-NOLOGS")

    body = text_of(client.get(f"/devices/{device['device_id']}").text)

    # An empty table with no explanation reads like a broken page.
    assert "No logs collected" in body


def test_collect_logs_button_queues_a_command(client: TestClient, enrolled):
    device = enrolled(serial="UI-QUEUE")

    client.post(
        f"/devices/{device['device_id']}/collect-logs", follow_redirects=False
    )

    commands = client.get(f"/api/v1/devices/{device['device_id']}/commands").json()
    assert [c["command_type"] for c in commands] == ["collect_logs"]


def test_page_shows_a_request_is_already_in_flight(client: TestClient, enrolled):
    device = enrolled(serial="UI-INFLIGHT")
    client.post(f"/devices/{device['device_id']}/collect-logs", follow_redirects=False)

    body = text_of(client.get(f"/devices/{device['device_id']}").text)

    # Without this an operator who sees nothing happen queues another, and another.
    assert "already in flight" in body


def test_an_uploaded_log_is_listed_and_readable(
    client: TestClient, enrolled, mtls_headers
):
    device = enrolled(serial="UI-READ")
    headers = mtls_headers(device["certificate_pem"])
    client.post(
        "/api/v1/device/logs",
        json={"content": "E/Reconciler: install failed\n", "agent_version": "0.3.0"},
        headers=headers,
    )

    listing = client.get(f"/devices/{device['device_id']}").text
    assert "0.3.0" in listing

    bundle_id = client.get(f"/api/v1/devices/{device['device_id']}/logs").json()[0]["id"]
    body = client.get(f"/devices/{device['device_id']}/logs/{bundle_id}").text
    assert "install failed" in body


def test_a_log_cannot_be_read_through_another_device(
    client: TestClient, enrolled, mtls_headers
):
    owner = enrolled(serial="UI-OWNER")
    other = enrolled(serial="UI-OTHER")
    client.post(
        "/api/v1/device/logs",
        json={"content": "private\n"},
        headers=mtls_headers(owner["certificate_pem"]),
    )
    bundle_id = client.get(f"/api/v1/devices/{owner['device_id']}/logs").json()[0]["id"]

    # Scoped to the device as well as the id, so a guessed id reveals nothing
    # (the same rule as D34).
    response = client.get(f"/devices/{other['device_id']}/logs/{bundle_id}")
    assert response.status_code == 404


def test_device_page_lists_identifiers(client: TestClient, enrolled):
    device = enrolled(serial="UI-IDENT")

    body = text_of(client.get(f"/devices/{device['device_id']}").text)

    assert "Identity" in body
    assert "UI-IDENT" in body


def test_device_page_warns_when_there_is_no_hardware_serial(client: TestClient):
    from tests.conftest import ADMIN_HEADERS, generate_csr

    secret = client.post(
        "/api/v1/enrollment-tokens", json={"name": "weak"}, headers=ADMIN_HEADERS
    ).json()["secret"]
    device = client.post(
        "/api/v1/enroll",
        json={
            "token": secret,
            "csr_pem": generate_csr(),
            "serial_number": "SM-X520-deadbeefdeadbeef",
            "identifiers": [
                {"kind": "android_id", "value": "SM-X520-deadbeefdeadbeef"}
            ],
        },
    ).json()

    body = text_of(client.get(f"/devices/{device['device_id']}").text)

    # A device one wipe away from becoming a duplicate is invisible from anything
    # else on the page, so it has to be said outright.
    assert "No hardware serial" in body


def test_device_page_offers_retire_not_delete_while_live(client: TestClient, enrolled):
    device = enrolled(serial="UI-LIVE")

    body = client.get(f"/devices/{device['device_id']}").text

    # Delete must not be one click away from a working tablet.
    assert f"/devices/{device['device_id']}/retire" in body
    assert f"/devices/{device['device_id']}/delete" not in body


def test_device_page_offers_delete_once_retired(client: TestClient, enrolled):
    device = enrolled(serial="UI-RETIRED")
    client.post(f"/devices/{device['device_id']}/retire", follow_redirects=False)

    body = client.get(f"/devices/{device['device_id']}").text

    assert f"/devices/{device['device_id']}/delete" in body


def test_console_delete_removes_the_device(client: TestClient, enrolled):
    device = enrolled(serial="UI-GONE")
    client.post(f"/devices/{device['device_id']}/retire", follow_redirects=False)

    client.post(f"/devices/{device['device_id']}/delete", follow_redirects=False)

    assert client.get(f"/api/v1/devices/{device['device_id']}").status_code == 404


def test_console_refuses_to_delete_a_live_device(client: TestClient, enrolled):
    device = enrolled(serial="UI-STILL-LIVE")

    response = client.post(
        f"/devices/{device['device_id']}/delete", follow_redirects=False
    )

    assert response.status_code == 409
    assert client.get(f"/api/v1/devices/{device['device_id']}").status_code == 200


# --------------------------------------------------------------------------- #
# ⚠️ Outbound credentials are sealed, not stored (SEC_AUDIT M-5)
# --------------------------------------------------------------------------- #


def test_every_secret_field_is_sealed_in_the_database(client: TestClient, db):
    """⚠️ What a database dump yields.

    The vault key lives in `pki/`, so this defends against a copy of the database
    travelling — a backup, a snapshot, a read-only injection — and not against
    `pki/` leaking, at which point everything is gone anyway (S-2). That is a
    narrower claim than "encrypted at rest" and it is the true one.
    """
    from sqlalchemy import select as _select

    from app.db.models import AppSetting
    from app.services import settings_store

    client.post(
        "/admin/settings/smtp",
        data={"smtp.host": "mail.example.org", "smtp.password": "hunter2"},
    )
    client.post("/admin/settings/ad", data={"ad.bind_password": "directory-secret"})
    client.post("/admin/settings/sms", data={"sms.api_key": "sms-secret"})
    db.expire_all()

    raw = " ".join(s.value or "" for s in db.scalars(_select(AppSetting)))
    for secret in ("hunter2", "directory-secret", "sms-secret"):
        assert secret not in raw, f"{secret} is readable in app_setting"

    # And each still round-trips for the code that uses it.
    assert settings_store.group_values(db, "smtp")["smtp.password"] == "hunter2"
    assert settings_store.group_values(db, "ad")["ad.bind_password"] == "directory-secret"
    assert settings_store.group_values(db, "sms")["sms.api_key"] == "sms-secret"


def test_a_non_secret_setting_is_still_plain(client: TestClient, db):
    """Sealing everything would make the settings table unreadable to an operator
    debugging their own deployment, for no gain."""
    from sqlalchemy import select as _select

    from app.db.models import AppSetting

    client.post("/admin/settings/smtp", data={"smtp.host": "mail.example.org"})
    db.expire_all()

    stored = {s.key: s.value for s in db.scalars(_select(AppSetting))}
    assert stored["smtp.host"] == "mail.example.org"


def test_a_credential_written_before_sealing_still_works(client: TestClient, db):
    """⚠️ Every credential stored before M-5 is plaintext.

    Treating those as corrupt would silently break outbound mail on the release
    that added the encryption — a security improvement that reads as an outage.
    """
    from app.services import settings_store

    # Exactly what an upgraded deployment has in its table.
    settings_store.put(db, "smtp.password", "legacy-plaintext")
    db.commit()

    assert settings_store.group_values(db, "smtp")["smtp.password"] == "legacy-plaintext"
