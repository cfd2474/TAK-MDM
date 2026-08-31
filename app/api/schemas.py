"""Request and response models for the admin API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.models import EnrollmentState


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- #
# Devices, groups, tags
# --------------------------------------------------------------------------- #


class DeviceCreate(BaseModel):
    serial_number: str = Field(min_length=1, max_length=64)
    model: str | None = None
    imei: str | None = None
    os_version: str | None = None


class DeviceRead(ORMModel):
    id: uuid.UUID
    serial_number: str
    model: str | None
    imei: str | None
    os_version: str | None
    agent_version: str | None
    enrollment_state: EnrollmentState
    state_version: int
    last_checkin_at: datetime | None
    created_at: datetime


class NamedCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None


class GroupRead(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class TagRead(ORMModel):
    id: uuid.UUID
    name: str


class MembershipUpdate(BaseModel):
    device_ids: list[uuid.UUID]


# --------------------------------------------------------------------------- #
# Policies
# --------------------------------------------------------------------------- #


class PolicyVersionRead(ORMModel):
    id: uuid.UUID
    version: int
    spec: dict[str, Any]
    notes: str | None
    published_at: datetime


class PolicyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    policy_type: str
    description: str | None = None
    spec: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


class PolicyVersionCreate(BaseModel):
    """Publishing an edit. Never mutates an existing version (D2)."""

    spec: dict[str, Any]
    notes: str | None = None


class PolicyRead(ORMModel):
    id: uuid.UUID
    name: str
    policy_type: str
    description: str | None
    created_at: datetime
    archived_at: datetime | None
    versions: list[PolicyVersionRead]


# --------------------------------------------------------------------------- #
# Assignments
# --------------------------------------------------------------------------- #


class AssignmentCreate(BaseModel):
    policy_id: uuid.UUID
    scope: Literal["device", "group", "tag"]
    target_id: uuid.UUID
    rank: int = 0
    enabled: bool = True
    # Omit to track the policy's latest published version.
    pinned_version: int | None = None


class AssignmentUpdate(BaseModel):
    rank: int | None = None
    enabled: bool | None = None


class AssignmentRead(BaseModel):
    id: uuid.UUID
    policy_id: uuid.UUID
    policy_name: str
    policy_type: str
    scope: str
    target_id: uuid.UUID
    rank: int
    enabled: bool
    pinned_version: int | None


# --------------------------------------------------------------------------- #
# Preview
# --------------------------------------------------------------------------- #


class DraftAssignment(BaseModel):
    """A hypothetical assignment, never persisted."""

    policy_id: uuid.UUID
    rank: int = 0
    scope: Literal["device", "group", "tag"] = "device"
    pinned_version: int | None = None


class PreviewRequest(BaseModel):
    add: list[DraftAssignment] = Field(default_factory=list)
    remove_assignment_ids: list[uuid.UUID] = Field(default_factory=list)

    @model_validator(mode="after")
    def _require_a_change(self) -> PreviewRequest:
        if not self.add and not self.remove_assignment_ids:
            raise ValueError("preview requires at least one addition or removal")
        return self


# --------------------------------------------------------------------------- #
# Enrollment
# --------------------------------------------------------------------------- #


class WifiConfig(BaseModel):
    ssid: str
    password: str | None = None
    security: Literal["WPA", "WEP", "NONE"] = "WPA"


class EnrollmentTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    ttl_hours: int | None = Field(default=None, ge=1, le=8760)
    # None means unlimited until expiry — the KME case, where one profile enrolls a
    # whole shipment.
    max_uses: int | None = Field(default=None, ge=1, le=10_000)
    group_ids: list[uuid.UUID] = Field(default_factory=list)
    tag_ids: list[uuid.UUID] = Field(default_factory=list)
    wifi: WifiConfig | None = None


class EnrollmentTokenRead(ORMModel):
    id: uuid.UUID
    name: str
    prefix: str
    expires_at: datetime
    max_uses: int | None
    use_count: int
    revoked_at: datetime | None
    created_at: datetime
    groups: list[GroupRead]
    tags: list[TagRead]


class EnrollmentTokenCreated(BaseModel):
    """The one and only time the secret is returned."""

    token: EnrollmentTokenRead
    secret: str
    provisioning: dict[str, Any]


class ProvisioningRequest(BaseModel):
    """Re-render provisioning payloads for a secret the operator already holds."""

    secret: str
    wifi: WifiConfig | None = None


class EnrollRequest(BaseModel):
    """Sent by the agent on first run. Public endpoint — the token is the credential."""

    token: str = Field(min_length=1)
    csr_pem: str = Field(min_length=1)
    serial_number: str = Field(min_length=1, max_length=64)
    model: str | None = None
    imei: str | None = None
    os_version: str | None = None
    agent_version: str | None = None


class EnrollResponse(BaseModel):
    device_id: uuid.UUID
    certificate_pem: str
    ca_certificate_pem: str
    not_valid_after: datetime
    state_version: int


class CheckinRequest(BaseModel):
    state_version: int | None = None
    agent_version: str | None = None
    os_version: str | None = None


class CheckinResponse(BaseModel):
    device_id: uuid.UUID
    state_version: int
    policy_changed: bool
