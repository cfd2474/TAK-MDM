"""Test fixtures.

The suite runs against in-memory SQLite. The models use ``JSON`` with a JSONB
variant and portable ``Uuid`` columns precisely so this works — the resolver and
API logic are dialect-independent, and Postgres is exercised by migrations.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base, get_session
from app.main import app


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
def client(session_factory: sessionmaker) -> Iterator[TestClient]:
    def override() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


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
