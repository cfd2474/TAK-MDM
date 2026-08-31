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
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_bundle_signer, get_ca, get_storage
from app.artifacts.storage import LocalArtifactStorage
from app.config import Settings, get_settings
from app.db.base import Base, get_session
from app.main import app
from app.security.bundle import BundleSigner
from app.security.ca import CertificateAuthority


@pytest.fixture
def session_factory() -> Iterator[sessionmaker]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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
    )


@pytest.fixture
def client(
    session_factory: sessionmaker,
    ca: CertificateAuthority,
    signer: BundleSigner,
    artifact_storage: LocalArtifactStorage,
    settings: Settings,
) -> Iterator[TestClient]:
    def override() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    app.dependency_overrides[get_ca] = lambda: ca
    app.dependency_overrides[get_bundle_signer] = lambda: signer
    app.dependency_overrides[get_storage] = lambda: artifact_storage
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
        tag_ids: list[str] | None = None,
    ) -> dict:
        created = client.post(
            "/api/v1/enrollment-tokens",
            json={
                "name": "Test Token",
                "group_ids": group_ids or [],
                "tag_ids": tag_ids or [],
            },
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


@pytest.fixture
def make_policy(client: TestClient):
    def _make(name: str, policy_type: str, spec: dict) -> dict:
        response = client.post(
            "/api/v1/policies",
            json={"name": name, "policy_type": policy_type, "spec": spec},
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _make


@pytest.fixture
def make_device(client: TestClient):
    def _make(serial: str = "R5CN00TAK01", model: str = "SM-G736U1") -> dict:
        response = client.post(
            "/api/v1/devices", json={"serial_number": serial, "model": model}
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
        response = client.post("/api/v1/assignments", json=body)
        assert response.status_code == 201, response.text
        return response.json()

    return _assign
