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

"""Test fixtures.

The suite runs against in-memory SQLite. The models use ``JSON`` with a JSONB
variant and portable ``Uuid`` columns precisely so this works — the resolver and
API logic are dialect-independent, and Postgres is exercised by migrations.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import (
    get_bundle_signer,
    get_ca,
    get_session_factory,
    get_storage,
    get_token_vault,
)
from app.artifacts.storage import LocalArtifactStorage
from app.config import Settings, get_settings
from app.db.base import Base, get_session
from app.main import app
from app.security.bundle import BundleSigner
from app.security.ca import CertificateAuthority
from app.security.token_vault import TokenVault


@pytest.fixture
def session_factory() -> Iterator[sessionmaker]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enforce_foreign_keys(dbapi_connection, _record):
        """Make SQLite behave like Postgres about referential integrity.

        SQLite ignores foreign keys entirely unless this pragma is set, so every
        ``ON DELETE CASCADE`` and ``ON DELETE SET NULL`` in the schema was a no-op
        under test while being enforced in production. That is the same class of
        dialect divergence as the naive-vs-aware timestamp bug behind D27: the
        suite passes, the container does something else.
        """
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.drop_all(engine)


@pytest.fixture
def db(session_factory: sessionmaker) -> Iterator[Session]:
    """Direct session, for arranging state the API deliberately will not let you set."""
    with session_factory() as session:
        yield session


@pytest.fixture
def ca(tmp_path) -> CertificateAuthority:
    """A throwaway CA per test, so the suite never touches a real PKI directory."""
    return CertificateAuthority.load_or_create(
        tmp_path / "pki", common_name="Test CA", validity_days=30
    )


@pytest.fixture
def signer(tmp_path) -> BundleSigner:
    return BundleSigner.load_or_create(tmp_path / "pki")


@pytest.fixture
def artifact_storage(tmp_path) -> LocalArtifactStorage:
    return LocalArtifactStorage(tmp_path / "artifacts")


@pytest.fixture
def token_vault(tmp_path) -> TokenVault:
    return TokenVault.load_or_create(tmp_path / "pki")


#: What an unregistered hostname resolves to in tests: an ordinary public
#: address, so a URL is allowed unless a test says otherwise.
PUBLIC_ADDRESS = "93.184.216.34"


class StubResolver:
    """A DNS resolver that never leaves the process.

    Tests register what a name should answer with; anything unregistered is a
    public address, because "allowed" is the uninteresting case and every test
    that does not care about SSRF should behave as it did before the guard
    existed.
    """

    def __init__(self) -> None:
        self.answers: dict[str, list[str]] = {}
        self.asked: list[str] = []

    def points(self, host: str, *addresses: str) -> None:
        self.answers[host] = list(addresses)

    def __call__(self, host: str) -> list[str]:
        self.asked.append(host)
        return self.answers.get(host, [PUBLIC_ADDRESS])


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    """⚠️ **Autouse, because the limiter is module-level state.**

    `app.security.ratelimit.limiter` is one object for the process, so without
    this a test that spends a device's allowance leaves it spent for every test
    that runs afterwards — and the failure surfaces somewhere unrelated, as a
    429 nobody asked for.
    """
    from app.security import ratelimit

    ratelimit.limiter.reset()
    yield
    ratelimit.limiter.reset()


@pytest.fixture(autouse=True)
def resolves(monkeypatch) -> StubResolver:
    """⚠️ **Autouse, so no test ever performs a real DNS lookup.**

    `app.security.outbound` resolves the host of every operator-supplied URL it
    fetches (SEC_AUDIT M-2). Left alone, that made the geocoding tests query
    `nominatim.openstreetmap.org` and `photon.komoot.io` on every run — which is
    the W101 mistake wearing different clothes (a test that quietly queried a
    third party), and it would also fail the suite outright on a machine with no
    DNS, in the `except OSError` path.

    A test that cares where a name points calls `resolves.points(...)`.
    """
    from app.security import outbound

    resolver = StubResolver()
    monkeypatch.setattr(outbound, "_resolve", resolver)
    return resolver


@pytest.fixture
def settings() -> Settings:
    """Settings built in isolation from any local `.env`.

    Reading the developer's `.env` made the suite depend on ambient machine state —
    setting a real agent checksum locally broke a test asserting the behaviour when
    none is configured. Tests must describe the code, not the workstation.
    """
    return Settings(
        _env_file=None,
        agent_signature_checksum="",
        server_url="https://mdm.test.invalid",
        # ⚠️ No index warm-up. It runs on a background thread at startup and
        # would fetch 184 MB from F-Droid on every test session — making the
        # suite depend on a third party, and hammering them for nothing.
        warm_indexes=False,
        purge_location_history=False,
    )


@pytest.fixture
def client(
    session_factory: sessionmaker,
    ca: CertificateAuthority,
    signer: BundleSigner,
    artifact_storage: LocalArtifactStorage,
    token_vault: TokenVault,
    settings: Settings,
) -> Iterator[TestClient]:
    def override() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    app.dependency_overrides[get_ca] = lambda: ca
    app.dependency_overrides[get_bundle_signer] = lambda: signer
    app.dependency_overrides[get_storage] = lambda: artifact_storage
    app.dependency_overrides[get_token_vault] = lambda: token_vault
    # Background work must reach the test database, not the real one.
    app.dependency_overrides[get_session_factory] = lambda: session_factory
    app.dependency_overrides[get_settings] = lambda: settings
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------- #
# Certificate helpers
# --------------------------------------------------------------------------- #


def generate_csr(*, use_rsa: bool = False, common_name: str = "unverified") -> str:
    """A CSR as the agent would produce it (EC P-256, matching Android Keystore)."""
    key = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        if use_rsa
        else ec.generate_private_key(ec.SECP256R1())
    )
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)]))
        .sign(key, hashes.SHA256())
    )
    return csr.public_bytes(serialization.Encoding.PEM).decode()


@pytest.fixture
def mtls_headers(settings: Settings):
    """Simulate the reverse proxy forwarding a verified client certificate."""

    def _headers(certificate_pem: str) -> dict[str, str]:
        return {settings.client_cert_header: certificate_pem}

    return _headers


@pytest.fixture
def enrolled(client: TestClient):
    """Create a token, enroll a device, and return the enrollment response."""

    def _enroll(
        serial: str = "R5CN00TAK01",
        *,
        group_ids: list[str] | None = None,
    ) -> dict:
        created = client.post(
            "/api/v1/enrollment-tokens",
            json={
                "name": "Test Token",
                "group_ids": group_ids or [],
            },
            headers=ADMIN_HEADERS,
        )
        assert created.status_code == 201, created.text
        secret = created.json()["secret"]

        response = client.post(
            "/api/v1/enroll",
            json={
                "token": secret,
                "csr_pem": generate_csr(),
                "serial_number": serial,
                "model": "SM-G736U1",
                "os_version": "16",
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _enroll


# --------------------------------------------------------------------------- #
# Small builders, so tests read as scenarios rather than as HTTP plumbing
# --------------------------------------------------------------------------- #


# Helper fixtures reach the admin API, which is guarded once forward auth is on.
# Sending these always keeps them working in both modes; they are ignored when
# authentication is disabled.
ADMIN_HEADERS = {
    "x-authentik-username": "test-admin",
    "x-authentik-groups": "takmdm-admins",
}


#: A device's effective policy when nothing at all is assigned to it.
#:
#: ⚠️ Not `{}` any longer. Every enrolled device reports its position by default
#: (W161), so the fleet default resolves into the effective policy of a device no
#: policy reaches. Assertions compare against this rather than filtering it out,
#: so a stray policy leaking through still fails them.
FLEET_DEFAULT = {"TRACKING_FENCING": {"reporting_interval_minutes": 15}}


@pytest.fixture
def make_policy(client: TestClient):
    def _make(name: str, policy_type: str, spec: dict) -> dict:
        response = client.post(
            "/api/v1/policies",
            json={"name": name, "policy_type": policy_type, "spec": spec},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _make


@pytest.fixture
def make_device(client: TestClient):
    def _make(serial: str = "R5CN00TAK01", model: str = "SM-G736U1") -> dict:
        response = client.post(
            "/api/v1/devices",
            json={"serial_number": serial, "model": model},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _make


@pytest.fixture
def assign(client: TestClient):
    def _assign(
        policy_id: str,
        target_id: str,
        *,
        scope: str = "device",
        rank: int = 0,
        pinned_version: int | None = None,
    ) -> dict:
        body = {
            "policy_id": policy_id,
            "scope": scope,
            "target_id": target_id,
            "rank": rank,
        }
        if pinned_version is not None:
            body["pinned_version"] = pinned_version
        response = client.post("/api/v1/assignments", json=body, headers=ADMIN_HEADERS)
        assert response.status_code == 201, response.text
        return response.json()

    return _assign


def base_sha(uploaded: dict) -> str:
    """The base APK's content address, from an upload response.

    ⚠️ The value a policy entry pins (W139). A policy names the exact build it
    installs; there is no automatic "latest", so a test that requires an app and
    does not say which build is testing the unresolvable case whether it meant
    to or not.
    """
    return next(
        f["artifact_sha256"]
        for f in uploaded["version"]["files"]
        if f["role"] == "base"
    )
