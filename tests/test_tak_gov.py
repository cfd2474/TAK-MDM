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

"""The TAK.gov account link and plugin catalog.

Nothing here touches the network: `httpx.MockTransport` stands in for tak.gov, so
these are contract tests against the shape `tpc.md` documents. That matters more
than usual because `eud_api` is undocumented and unversioned — the point of the
adapter is that an upstream rename degrades a column rather than the page, and
that is only true if something checks it.

Weighted towards refresh-token rotation, which `tpc.md` names the number one
outage source: a lost rotation means a human has to type a code at tak.gov again.
"""

from __future__ import annotations

import base64
import json
import re
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from sqlalchemy import select

from app.db.models import AppPackage, TakGovLink, TakGovLinkStatus
from app.services import tak_gov, tak_gov_link
from tests.apk_fixtures import build_apk, make_signing_certificate
from tests.conftest import ADMIN_HEADERS


def text_of(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def jwt_with(claims: dict) -> str:
    """A structurally valid JWT. Never verified by us — only read for a label."""
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"header.{body}.signature"


def transport(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def json_response(status: int, payload: dict) -> httpx.Response:
    return httpx.Response(status, json=payload)


# --------------------------------------------------------------------------- #
# Protocol parsing — pure, no I/O
# --------------------------------------------------------------------------- #


def test_device_code_defaults_fill_in_what_keycloak_omits():
    code = tak_gov.parse_device_code({"device_code": "d", "user_code": "ABCD-EFGH"})

    assert code.interval == 5  # RFC 8628 default
    assert code.expires_in == 600
    # ⚠️ Not tak.gov/register-device, which is what tpc.md documents and what the
    # live realm does NOT return. The fallback is the realm's own device page, so
    # an operator following it lands where the code actually works.
    assert code.verification_uri == tak_gov.FALLBACK_VERIFICATION_URI
    assert "auth.tak.gov" in code.verification_uri
    # Falls back to the plain URI so the console always has something to link to.
    assert code.verification_uri_complete == code.verification_uri


def test_a_token_response_without_a_refresh_token_names_the_missing_scope():
    """The single most likely misconfiguration, and the least self-explanatory."""
    with pytest.raises(tak_gov.TakGovError) as exc:
        tak_gov.parse_tokens({"access_token": "a", "expires_in": 300})

    assert "offline_access" in str(exc.value)


def test_the_account_label_comes_from_the_token_but_is_never_trusted():
    tokens = tak_gov.parse_tokens(
        {
            "access_token": jwt_with({"preferred_username": "kate@example.mil"}),
            "refresh_token": "r",
        }
    )
    assert tokens.account_label == "kate@example.mil"


def test_a_malformed_token_yields_no_label_rather_than_an_error():
    tokens = tak_gov.parse_tokens({"access_token": "not-a-jwt", "refresh_token": "r"})
    assert tokens.account_label is None


@pytest.mark.parametrize(
    "error,expected",
    [
        ("authorization_pending", tak_gov.AuthorizationPending),
        ("slow_down", tak_gov.SlowDown),
        ("access_denied", tak_gov.TakGovError),
        ("expired_token", tak_gov.TakGovError),
    ],
)
def test_the_rfc_8628_soft_errors_are_distinguished_from_real_ones(error, expected):
    """OpenTAKServer ignores the first two (tpc.md 2.3); conflating them turns the
    normal path into a red banner."""
    assert isinstance(tak_gov.token_error(400, {"error": error}), expected)


# --------------------------------------------------------------------------- #
# Catalog parsing — the undocumented surface
# --------------------------------------------------------------------------- #


# Field-for-field the shape a live ATAK-CIV 5.8.0 row has (captured 2026-09-02),
# so this file is a contract test rather than a guess about one.
FULL_PLUGIN = {
    "identifier": "example-5-8-0-civ",
    "package_name": "com.atakmap.android.plugin.example",
    "display_name": "Example Plugin",
    "version": "5.8.0",
    "revision_code": 42,
    "apk_url": "https://tak.gov/eud_api/software/v1/plugins/example-5-8-0-civ/apk",
    "apk_hash": "AABBCC",
    "apk_size_bytes": 1048576,
    "apk_type": "plugin",
    "os_requirement": "33",
    "tak_prerequisite": "5.8.0",
    "description": "Does a thing.",
    "platform": "Android",
}


def test_a_full_row_maps_across():
    plugin = tak_gov.parse_plugin(FULL_PLUGIN)

    assert plugin.package_name == "com.atakmap.android.plugin.example"
    assert plugin.revision_code == 42
    assert plugin.apk_hash == "aabbcc"  # lowered, so hash comparison is stable
    assert plugin.identifier == "example-5-8-0-civ"
    assert plugin.unknown_fields == ()


def test_the_identifier_is_kept_because_the_urls_are_built_from_it():
    """Absent from tpc.md's field table, present on every live row, and the
    stable key both apk_url and icon_url embed."""
    plugin = tak_gov.parse_plugin(FULL_PLUGIN)
    assert plugin.identifier == "example-5-8-0-civ"
    assert plugin.identifier in FULL_PLUGIN["apk_url"]


def test_os_requirement_survives_arriving_as_a_number():
    """Live rows send it as an int, not the string the field table implies."""
    plugin = tak_gov.parse_plugin({**FULL_PLUGIN, "os_requirement": 21})
    assert plugin.os_requirement == "21"


def test_a_row_missing_everything_but_the_package_name_still_lists():
    """An upstream rename should cost a column, not the page."""
    plugin = tak_gov.parse_plugin({"package_name": "com.example", "verzion": "9"})

    assert plugin is not None
    assert plugin.version is None
    assert plugin.revision_code is None
    assert "verzion" in plugin.unknown_fields  # surfaced, not swallowed


def test_a_row_with_no_package_name_is_dropped():
    """It is the catalog's primary key; a row without one matches nothing."""
    assert tak_gov.parse_plugin({"display_name": "Nameless"}) is None


def test_unparseable_numbers_become_none_rather_than_raising():
    plugin = tak_gov.parse_plugin(
        {"package_name": "com.example", "revision_code": "not-a-number"}
    )
    assert plugin.revision_code is None


@pytest.mark.parametrize(
    "payload",
    [
        [FULL_PLUGIN],
        {"results": [FULL_PLUGIN]},
        {"plugins": [FULL_PLUGIN]},
        {"data": [FULL_PLUGIN]},
    ],
)
def test_the_catalog_is_read_from_any_plausible_envelope(payload):
    assert len(tak_gov.parse_catalog(payload)) == 1


@pytest.mark.parametrize("payload", [{}, {"unexpected": "shape"}, "a string", None])
def test_an_unrecognised_catalog_shape_reads_as_empty_not_as_a_crash(payload):
    assert tak_gov.parse_catalog(payload) == []


# --------------------------------------------------------------------------- #
# Download integrity
# --------------------------------------------------------------------------- #


def test_a_download_whose_hash_does_not_match_is_refused():
    """apk_url redirects to presigned storage, so what arrives is not served by
    the host that vouched for it."""
    plugin = tak_gov.parse_plugin({**FULL_PLUGIN, "apk_hash": "00" * 32})
    client = transport(lambda request: httpx.Response(200, content=b"not the apk"))

    with pytest.raises(tak_gov.TakGovError) as exc:
        tak_gov.download_apk(plugin, "token", client=client)

    assert "hash mismatch" in str(exc.value)


def test_a_download_whose_hash_matches_is_returned():
    import hashlib

    body = b"the real apk"
    plugin = tak_gov.parse_plugin(
        {**FULL_PLUGIN, "apk_hash": hashlib.sha256(body).hexdigest().upper()}
    )
    client = transport(lambda request: httpx.Response(200, content=body))

    assert tak_gov.download_apk(plugin, "token", client=client) == body


# --------------------------------------------------------------------------- #
# The link lifecycle
# --------------------------------------------------------------------------- #


def link_row(db) -> TakGovLink:
    return db.get(TakGovLink, 1)


def test_a_fresh_instance_is_unlinked(db):
    assert tak_gov_link.get(db).status is TakGovLinkStatus.UNLINKED
    assert tak_gov_link.is_linked(db) is False


def test_starting_a_link_parks_it_pending_with_a_code_to_type(db):
    client = transport(
        lambda r: json_response(
            200,
            {
                "device_code": "dev-code",
                "user_code": "WXYZ-1234",
                "verification_uri": "https://tak.gov/register-device",
                "verification_uri_complete": "https://tak.gov/register-device?code=WXYZ-1234",
                "interval": 5,
                "expires_in": 180,
            },
        )
    )

    link = tak_gov_link.start(db, client=client)

    assert link.status is TakGovLinkStatus.PENDING
    assert link.user_code == "WXYZ-1234"
    assert link.code_expires_at > datetime.now(timezone.utc)


def test_polling_before_the_operator_acts_changes_nothing(db, token_vault):
    _start_pending(db)
    client = transport(lambda r: json_response(400, {"error": "authorization_pending"}))

    link = tak_gov_link.poll(db, token_vault, client=client)

    assert link.status is TakGovLinkStatus.PENDING
    assert link.last_error is None  # the normal path must not look like a failure


def test_slow_down_backs_the_interval_off(db, token_vault):
    _start_pending(db)
    client = transport(lambda r: json_response(400, {"error": "slow_down"}))

    link = tak_gov_link.poll(db, token_vault, client=client)

    assert link.poll_interval_seconds == 10  # RFC 8628 says add 5
    assert link.status is TakGovLinkStatus.PENDING


def test_a_successful_poll_links_and_forgets_the_device_code(db, token_vault):
    _start_pending(db)
    client = transport(
        lambda r: json_response(
            200,
            {
                "access_token": jwt_with({"email": "kate@example.mil"}),
                "refresh_token": "refresh-1",
                "expires_in": 300,
            },
        )
    )

    link = tak_gov_link.poll(db, token_vault, client=client, linked_by="kate")

    assert link.status is TakGovLinkStatus.LINKED
    assert link.account_label == "kate@example.mil"
    assert link.linked_by == "kate"
    assert link.device_code is None and link.user_code is None
    # Sealed, not stored in the clear.
    assert "refresh-1" not in (link.refresh_token_sealed or "")
    assert token_vault.open(link.refresh_token_sealed) == "refresh-1"


def test_access_denied_drops_the_link_and_says_why(db, token_vault):
    _start_pending(db)
    client = transport(
        lambda r: json_response(
            400, {"error": "access_denied", "error_description": "user said no"}
        )
    )

    link = tak_gov_link.poll(db, token_vault, client=client)

    assert link.status is TakGovLinkStatus.UNLINKED
    assert "access_denied" in link.last_error and "user said no" in link.last_error


def test_an_expired_code_is_given_up_on_without_asking_tak_gov(db, token_vault):
    link = _start_pending(db)
    link.code_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.flush()

    def explode(request):  # pragma: no cover - must not be reached
        raise AssertionError("polled tak.gov with a code we knew had expired")

    link = tak_gov_link.poll(db, token_vault, client=transport(explode))

    assert link.status is TakGovLinkStatus.UNLINKED
    assert "expired" in link.last_error


def test_unlinking_forgets_every_credential(db, token_vault):
    _link_with(db, token_vault, refresh="refresh-1")

    link = tak_gov_link.unlink(db)

    assert link.status is TakGovLinkStatus.UNLINKED
    assert link.refresh_token_sealed is None
    assert link.previous_refresh_token_sealed is None
    assert link.access_token_sealed is None
    assert link.account_label is None


# --------------------------------------------------------------------------- #
# Refresh-token rotation — the number one outage source
# --------------------------------------------------------------------------- #


def test_a_cached_access_token_is_reused_rather_than_rotating(db, token_vault):
    """Refreshing per request burns a rotation each time (tpc.md 2.2)."""
    _link_with(db, token_vault, refresh="refresh-1", access="access-1", ttl=300)

    def explode(request):  # pragma: no cover - must not be reached
        raise AssertionError("refreshed while a valid access token was cached")

    assert tak_gov_link.access_token(db, token_vault, client=transport(explode)) == "access-1"


def test_a_token_inside_the_expiry_margin_is_refreshed(db, token_vault):
    """29 seconds left is not enough to start a request with."""
    _link_with(db, token_vault, refresh="refresh-1", access="access-1", ttl=29)
    client = transport(
        lambda r: json_response(
            200, {"access_token": "access-2", "refresh_token": "refresh-2", "expires_in": 300}
        )
    )

    assert tak_gov_link.access_token(db, token_vault, client=client) == "access-2"


def test_a_rotation_is_persisted_and_the_replaced_token_kept_as_a_fallback(db, token_vault):
    _link_with(db, token_vault, refresh="refresh-1", access="access-1", ttl=0)
    client = transport(
        lambda r: json_response(
            200, {"access_token": "access-2", "refresh_token": "refresh-2", "expires_in": 300}
        )
    )

    tak_gov_link.access_token(db, token_vault, client=client)

    db.expire_all()
    link = link_row(db)
    assert token_vault.open(link.refresh_token_sealed) == "refresh-2"
    assert token_vault.open(link.previous_refresh_token_sealed) == "refresh-1"


def test_a_lost_rotation_recovers_from_the_previous_token(db, token_vault):
    """The crash window: we rotated, the write was lost, so the token we hold is
    already dead while the one it replaced is still live. Without this the only
    cure is a human typing a code at tak.gov."""
    _link_with(db, token_vault, refresh="dead-token", access="a", ttl=0)
    link_row(db).previous_refresh_token_sealed = token_vault.seal("still-live")
    db.flush()

    def handler(request):
        sent = httpx.QueryParams(request.content.decode())["refresh_token"]
        if sent == "dead-token":
            return json_response(400, {"error": "invalid_grant"})
        return json_response(
            200, {"access_token": "access-9", "refresh_token": "refresh-9", "expires_in": 300}
        )

    assert tak_gov_link.access_token(db, token_vault, client=transport(handler)) == "access-9"
    db.expire_all()
    assert link_row(db).status is TakGovLinkStatus.LINKED


def test_when_both_tokens_are_dead_the_link_breaks_visibly(db, token_vault):
    _link_with(db, token_vault, refresh="dead-1", access="a", ttl=0)
    link_row(db).previous_refresh_token_sealed = token_vault.seal("dead-2")
    db.flush()
    client = transport(lambda r: json_response(400, {"error": "invalid_grant"}))

    assert tak_gov_link.access_token(db, token_vault, client=client) is None

    db.expire_all()
    link = link_row(db)
    assert link.status is TakGovLinkStatus.BROKEN
    assert "invalid_grant" in link.last_error


def test_a_token_sealed_under_a_lost_vault_key_breaks_the_link_clearly(db, token_vault):
    """`TokenVault.open` returns None rather than raising for exactly this case,
    so without a check it would look like 'not linked' forever."""
    _link_with(db, token_vault, refresh="refresh-1", access="a", ttl=0)
    link_row(db).refresh_token_sealed = "gAAAAABmnot-a-valid-ciphertext"
    db.flush()

    assert tak_gov_link.access_token(db, token_vault) is None

    db.expire_all()
    assert link_row(db).status is TakGovLinkStatus.BROKEN
    assert "token-vault key" in link_row(db).last_error


def test_an_unlinked_instance_returns_no_token_rather_than_raising(db, token_vault):
    assert tak_gov_link.access_token(db, token_vault) is None


def test_the_catalog_is_empty_and_quiet_when_unlinked(db, token_vault):
    assert tak_gov_link.catalog(db, token_vault) == ([], None)


def test_a_catalog_failure_is_returned_not_raised(db, token_vault):
    _link_with(db, token_vault, refresh="r", access="access-1", ttl=300)
    client = transport(lambda r: httpx.Response(503, text="upstream is down"))

    plugins, error = tak_gov_link.catalog(db, token_vault, client=client)

    assert plugins == []
    assert "503" in error


# --------------------------------------------------------------------------- #
# Console
# --------------------------------------------------------------------------- #


def test_the_admin_page_offers_a_link_and_states_the_licence_difference(client: TestClient):
    body = text_of(client.get("/admin", headers=ADMIN_HEADERS).text)

    assert "TAK.gov account" in body
    assert "not linked" in body
    # The constraint that shapes the product, shown where the decision is made.
    assert "ATAK-CIV carries a distribution grant" in body


def test_the_apps_page_says_plainly_that_it_is_not_linked(client: TestClient):
    body = text_of(client.get("/apps", headers=ADMIN_HEADERS).text)

    assert "TPC Plugins" in body
    assert "not linked to a TAK.gov account" in body
    assert "Admin" in body  # and where to go about it


def test_the_pending_state_shows_the_code_to_type(client: TestClient, db):
    _start_pending(db)
    db.commit()

    page = client.get("/admin", headers=ADMIN_HEADERS).text

    assert "WXYZ-1234" in page
    assert "register-device" in page


def test_the_linked_state_names_the_account_and_warns_unlink_is_local(
    client: TestClient, db, token_vault
):
    _link_with(db, token_vault, refresh="r", account="kate@example.mil")
    db.commit()

    body = text_of(client.get("/admin", headers=ADMIN_HEADERS).text)

    assert "kate@example.mil" in body
    # Unlinking here does not revoke at tak.gov, and an operator would assume it does.
    assert "does not revoke anything at tak.gov" in body.replace("  ", " ")


def test_unlinking_through_the_console_clears_the_credential(
    client: TestClient, db, token_vault
):
    _link_with(db, token_vault, refresh="r")
    db.commit()

    response = client.post(
        "/admin/takgov/unlink", headers=ADMIN_HEADERS, follow_redirects=False
    )
    assert response.status_code in (302, 303)

    db.expire_all()
    assert link_row(db).status is TakGovLinkStatus.UNLINKED


def test_the_catalog_is_not_fetched_unless_the_tab_is_asked_for(
    client: TestClient, db, token_vault
):
    """A third-party call and a token refresh must not sit in front of unrelated
    work like uploading an APK."""
    _link_with(db, token_vault, refresh="r", access="access-1", ttl=300)
    db.commit()

    body = text_of(client.get("/apps", headers=ADMIN_HEADERS).text)

    assert "Press Show to fetch the catalog" in body.replace("  ", " ")


# --------------------------------------------------------------------------- #


def _start_pending(db) -> TakGovLink:
    link = tak_gov_link.get(db)
    link.status = TakGovLinkStatus.PENDING
    link.device_code = "dev-code"
    link.user_code = "WXYZ-1234"
    link.verification_uri = "https://tak.gov/register-device"
    link.verification_uri_complete = "https://tak.gov/register-device?code=WXYZ-1234"
    link.code_expires_at = datetime.now(timezone.utc) + timedelta(minutes=3)
    db.flush()
    return link


def _link_with(
    db,
    vault,
    *,
    refresh: str,
    access: str | None = None,
    ttl: int = 300,
    account: str = "kate@example.mil",
) -> TakGovLink:
    link = tak_gov_link.get(db)
    link.status = TakGovLinkStatus.LINKED
    link.refresh_token_sealed = vault.seal(refresh)
    link.access_token_sealed = vault.seal(access) if access else None
    link.access_expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
    link.account_label = account
    link.linked_at = datetime.now(timezone.utc)
    db.flush()
    return link


# --------------------------------------------------------------------------- #
# Import — catalog row to local package library
# --------------------------------------------------------------------------- #


def catalog_and_apk(apk: bytes, plugin: dict, *, hash_override: str | None = None):
    """A transport serving one catalog row and its APK."""
    import hashlib

    row = {
        **plugin,
        "apk_hash": hash_override or hashlib.sha256(apk).hexdigest(),
        "apk_size_bytes": len(apk),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return json_response(
                200,
                {"access_token": "a", "refresh_token": "r", "expires_in": 300},
            )
        if request.url.path.endswith("/apk"):
            return httpx.Response(200, content=apk)
        return httpx.Response(200, json=[row])

    return transport(handler), row


def test_importing_reads_identity_from_the_apk_not_the_catalog(
    db, token_vault, artifact_storage
):
    """The catalog is an ingest source, not an authority. A row that lies about
    its package name must not be able to smuggle one in under that name."""
    from app.services import packages as package_service

    apk = build_apk("com.real.package", 77, "1.2.3")
    client, _ = catalog_and_apk(
        apk, {**FULL_PLUGIN, "package_name": "com.catalog.claims.otherwise"}
    )
    _link_with(db, token_vault, refresh="r", access="access-1", ttl=300)

    result = tak_gov_link.import_plugin(
        db, token_vault, artifact_storage, FULL_PLUGIN["identifier"],
        product="ATAK-CIV", product_version="5.8.0", client=client,
    )

    assert result.package.package_name == "com.real.package"
    assert result.version.version_code == 77
    assert isinstance(result, package_service.IngestResult)


def test_an_apk_whose_hash_does_not_match_is_never_ingested(
    db, token_vault, artifact_storage
):
    client, _ = catalog_and_apk(
        build_apk("com.example", 1), FULL_PLUGIN, hash_override="00" * 32
    )
    _link_with(db, token_vault, refresh="r", access="access-1", ttl=300)

    with pytest.raises(tak_gov.TakGovError) as exc:
        tak_gov_link.import_plugin(
            db, token_vault, artifact_storage, FULL_PLUGIN["identifier"],
            product="ATAK-CIV", product_version="5.8.0", client=client,
        )

    assert "hash mismatch" in str(exc.value)
    assert db.scalar(select(AppPackage).where(AppPackage.package_name == "com.example")) is None


def test_a_failed_download_leaves_no_half_file_behind(tmp_path):
    """A complete-looking but unverified APK on disk is the thing most likely to
    get picked up by something else."""
    plugin = tak_gov.parse_plugin({**FULL_PLUGIN, "apk_hash": "11" * 32})
    dest = tmp_path / "plugin.apk"
    client = transport(lambda r: httpx.Response(200, content=b"wrong bytes"))

    with pytest.raises(tak_gov.TakGovError):
        tak_gov.download_apk_to_file(plugin, "token", dest, client=client)

    assert not dest.exists()


def test_streaming_a_good_download_writes_every_byte(tmp_path):
    import hashlib

    body = b"x" * (700 * 1024)  # spans several 256 KiB chunks
    plugin = tak_gov.parse_plugin(
        {**FULL_PLUGIN, "apk_hash": hashlib.sha256(body).hexdigest()}
    )
    dest = tmp_path / "plugin.apk"
    client = transport(lambda r: httpx.Response(200, content=body))

    assert tak_gov.download_apk_to_file(plugin, "token", dest, client=client) == len(body)
    assert dest.read_bytes() == body


def test_importing_an_identifier_the_catalog_does_not_have_says_so(
    db, token_vault, artifact_storage
):
    client, _ = catalog_and_apk(build_apk("com.example", 1), FULL_PLUGIN)
    _link_with(db, token_vault, refresh="r", access="access-1", ttl=300)

    with pytest.raises(tak_gov.TakGovError) as exc:
        tak_gov_link.import_plugin(
            db, token_vault, artifact_storage, "withdrawn-plugin",
            product="ATAK-CIV", product_version="5.8.0", client=client,
        )

    assert "withdrawn-plugin" in str(exc.value)


def test_the_upload_paths_own_guards_still_apply_to_an_import(
    db, token_vault, artifact_storage
):
    """Import goes through package_service.ingest, so signature continuity is
    enforced against an already-known package exactly as for a manual upload."""
    from app.services import packages as package_service

    first, second = make_signing_certificate("A"), make_signing_certificate("B")
    package_service.ingest(
        db, artifact_storage, build_apk("com.example", 1, certificate_der=first)
    )
    db.flush()

    apk = build_apk("com.example", 2, certificate_der=second)
    client, _ = catalog_and_apk(apk, FULL_PLUGIN)
    _link_with(db, token_vault, refresh="r", access="access-1", ttl=300)

    with pytest.raises(package_service.PackageError) as exc:
        tak_gov_link.import_plugin(
            db, token_vault, artifact_storage, FULL_PLUGIN["identifier"],
            product="ATAK-CIV", product_version="5.8.0", client=client,
        )

    assert "signing certificate" in str(exc.value)


# --------------------------------------------------------------------------- #
# Import jobs — progress the console can actually watch
# --------------------------------------------------------------------------- #


def run_now(work):
    """Runner that executes the job inline, so a test never depends on timing."""
    work()


def test_a_job_carries_progress_through_from_the_download(
    db, token_vault, artifact_storage
):
    """The bar must reflect bytes that actually landed. A download that stalls
    should show a bar that stops, not one that keeps animating."""
    from app.services import import_jobs
    import app.services.tak_gov_link as tgl

    body = b"y" * (900 * 1024)  # several 256 KiB chunks, so progress is stepwise
    client, _ = catalog_and_apk(build_apk("com.example", 3), FULL_PLUGIN)
    _link_with(db, token_vault, refresh="r", access="access-1", ttl=300)
    db.commit()

    def fake_import(session, vault, storage, identifier, *, product,
                    product_version, client=None, on_progress=None):
        for sent in range(0, len(body) + 1, 300 * 1024):
            on_progress(sent, len(body))
        return real(
            db, token_vault, artifact_storage, identifier,
            product=product, product_version=product_version, client=client_,
        )

    client_ = client
    real = tgl.import_plugin
    tgl.import_plugin = fake_import
    try:
        job = import_jobs.start(
            lambda: db, token_vault, artifact_storage,
            identifier=FULL_PLUGIN["identifier"], label="Example",
            product="ATAK-CIV", product_version="5.8.0", runner=run_now,
        )
    finally:
        tgl.import_plugin = real

    assert job.state == "done", job.error
    assert job.total == len(body)
    assert job.downloaded == len(body)
    assert job.percent == 100


def test_percent_is_zero_rather_than_a_division_by_an_unknown_total():
    from app.services.import_jobs import ImportJob

    job = ImportJob(id="x", identifier="i", label="l", downloaded=5_000, total=0)
    assert job.percent == 0  # "size unknown", not a fabricated fraction

    job.total = 10_000
    assert job.percent == 50


def test_percent_never_exceeds_one_hundred():
    """Content-Length can undercount a re-encoded body; the bar must not overrun."""
    from app.services.import_jobs import ImportJob

    job = ImportJob(id="x", identifier="i", label="l", downloaded=120, total=100)
    assert job.percent == 100


def test_a_failing_job_keeps_the_specific_reason(db, token_vault, artifact_storage):
    """"Import failed" would throw away the only useful part of a hash mismatch."""
    from app.services import import_jobs

    client, _ = catalog_and_apk(
        build_apk("com.example", 1), FULL_PLUGIN, hash_override="00" * 32
    )
    _link_with(db, token_vault, refresh="r", access="access-1", ttl=300)
    db.commit()

    import app.services.tak_gov_link as tgl

    real = tgl.import_plugin
    tgl.import_plugin = lambda *a, **k: real(*a, **{**k, "client": client})
    try:
        job = import_jobs.start(
            lambda: db, token_vault, artifact_storage,
            identifier=FULL_PLUGIN["identifier"], label="Example",
            product="ATAK-CIV", product_version="5.8.0", runner=run_now,
        )
    finally:
        tgl.import_plugin = real

    assert job.state == "failed"
    assert "hash mismatch" in job.error


def test_a_successful_job_names_the_package_it_actually_ingested(
    db, token_vault, artifact_storage
):
    from app.services import import_jobs
    import app.services.tak_gov_link as tgl

    client, _ = catalog_and_apk(build_apk("com.real.one", 9), FULL_PLUGIN)
    _link_with(db, token_vault, refresh="r", access="access-1", ttl=300)
    db.commit()

    real = tgl.import_plugin
    tgl.import_plugin = lambda *a, **k: real(*a, **{**k, "client": client})
    try:
        job = import_jobs.start(
            lambda: db, token_vault, artifact_storage,
            identifier=FULL_PLUGIN["identifier"], label="Example",
            product="ATAK-CIV", product_version="5.8.0", runner=run_now,
        )
    finally:
        tgl.import_plugin = real

    assert job.state == "done", job.error
    assert job.package_name == "com.real.one"


def test_the_status_route_answers_for_a_job_it_knows(client: TestClient):
    from app.services import import_jobs

    job = import_jobs.start(
        lambda: None, None, None, identifier="i", label="Example",
        product="ATAK-CIV", product_version="5.8.0", runner=lambda work: None,
    )

    body = client.get(f"/apps/tpc/import/{job.id}", headers=ADMIN_HEADERS).json()
    assert body["state"] == "running"
    assert body["label"] == "Example"


def test_an_unknown_job_says_the_server_may_have_restarted(client: TestClient):
    """A 404 into a spinner would leave the modal turning forever."""
    response = client.get("/apps/tpc/import/deadbeef", headers=ADMIN_HEADERS)

    assert response.status_code == 404
    assert "restarted" in response.json()["error"]


def test_starting_an_import_returns_a_job_to_poll_rather_than_blocking(
    client: TestClient, db, token_vault
):
    _link_with(db, token_vault, refresh="r", access="access-1", ttl=300)
    db.commit()

    response = client.post(
        "/apps/tpc/import",
        data={"identifier": "nope", "product": "ATAK-CIV", "product_version": "5.8.0"},
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 202
    assert response.json()["id"]
    assert response.json()["state"] == "running"
