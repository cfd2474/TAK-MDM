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

"""Request and response models for the admin API."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.models import (
    CommandStatus,
    CommandType,
    ComplianceStatus,
    EnrollmentState,
    IdentifierKind,
    PartRole,
)


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- #
# Devices, groups, tags
# --------------------------------------------------------------------------- #


class DeviceCreate(BaseModel):
    serial_number: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, max_length=128)
    model: str | None = None
    imei: str | None = None
    os_version: str | None = None


class DeviceUpdate(BaseModel):
    """Operator-editable device fields. Only `name` for now."""

    name: str | None = Field(default=None, max_length=128)


class DeviceRead(ORMModel):
    id: uuid.UUID
    serial_number: str
    name: str | None
    model: str | None
    imei: str | None
    os_version: str | None
    agent_version: str | None
    enrollment_state: EnrollmentState
    state_version: int
    acked_state_version: int
    compliance_status: ComplianceStatus
    compliance_detail: str | None
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
    published_by: str | None = None


class PolicyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    policy_type: str
    description: str | None = None
    spec: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None
    is_template: bool = False


class PolicyClone(BaseModel):
    """Copy a policy (or template) into a new one."""

    name: str = Field(min_length=1, max_length=128)
    as_template: bool = False


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
    is_template: bool
    profile_id: uuid.UUID | None = None
    profile_section: str | None = None
    versions: list[PolicyVersionRead]


# --------------------------------------------------------------------------- #
# Profiles (composite policies)
# --------------------------------------------------------------------------- #


class ProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    #: catalog category key -> raw spec. Empty specs are skipped.
    sections: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ProfileSectionUpsert(BaseModel):
    spec: dict[str, Any] = Field(default_factory=dict)


class ProfileSectionRead(ORMModel):
    id: uuid.UUID
    profile_section: str | None
    policy_type: str
    name: str
    archived_at: datetime | None
    versions: list[PolicyVersionRead]


class ProfileRead(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    created_by: str | None
    archived_at: datetime | None
    sections: list[ProfileSectionRead]


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


class PrimaryEnrollmentTokenCreate(BaseModel):
    """Retire whichever primary token is live and stand up a new one (Chunk 14).

    No ``ttl_hours`` or ``max_uses``: the primary is meant to persist until
    deliberately retired, and its raw secret is never handed to a device directly —
    only 15-minute derivatives of it are, which is what makes an unbounded lifetime
    and unlimited uses safe to fix rather than expose as settings here.
    """

    name: str = Field(min_length=1, max_length=128)
    group_ids: list[uuid.UUID] = Field(default_factory=list)
    tag_ids: list[uuid.UUID] = Field(default_factory=list)


class PrimaryEnrollmentQrIssued(BaseModel):
    """A fresh 15-minute QR minted from the active primary token."""

    token: EnrollmentTokenRead
    secret: str
    expires_at: datetime
    provisioning: dict[str, Any]


class ProvisioningRequest(BaseModel):
    """Re-render provisioning payloads for a secret the operator already holds."""

    secret: str
    wifi: WifiConfig | None = None


class DeviceIdentifierReport(BaseModel):
    """One identity a device claims for itself.

    ``kind`` is a plain string, not the enum: an older server must not reject an
    agent that learns a new identifier source, and an unrecognised kind is still a
    perfectly usable match key. It is normalised server-side.
    """

    kind: str
    value: str = Field(min_length=1, max_length=128)


class DeviceIdentifierRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: IdentifierKind
    value: str
    first_seen_at: datetime
    last_seen_at: datetime


class EnrollRequest(BaseModel):
    """Sent by the agent on first run. Public endpoint — the token is the credential."""

    token: str = Field(min_length=1)
    csr_pem: str = Field(min_length=1)
    serial_number: str = Field(min_length=1, max_length=64)
    model: str | None = None
    imei: str | None = None
    os_version: str | None = None
    agent_version: str | None = None

    # Every identity this device can report, so re-enrolment can match on any it has
    # used before (R13). Optional: an older agent sends only serial_number and
    # enrols exactly as it always did.
    identifiers: list[DeviceIdentifierReport] = Field(default_factory=list)


class EnrollResponse(BaseModel):
    device_id: uuid.UUID
    certificate_pem: str
    ca_certificate_pem: str
    not_valid_after: datetime
    state_version: int
    # Pinned by the agent at enrollment to verify every later desired-state bundle.
    # Enrollment is the right moment to establish this trust: it is the one exchange
    # already authenticated by a secret the operator handed over out of band.
    bundle_signing_public_key: str


# --------------------------------------------------------------------------- #
# App packages
# --------------------------------------------------------------------------- #


class PackageFileRead(ORMModel):
    role: PartRole
    file_name: str
    split_name: str | None
    artifact_sha256: str


class PackageVersionRead(ORMModel):
    id: uuid.UUID
    version_code: int
    version_name: str | None
    min_sdk: int | None
    target_sdk: int | None
    uploaded_at: datetime
    files: list[PackageFileRead]


class PackageRead(ORMModel):
    id: uuid.UUID
    package_name: str
    label: str | None
    signature_sha256: str | None
    signature_scheme: str | None
    store_listed: bool
    created_at: datetime
    versions: list[PackageVersionRead]


class PackageUpdate(BaseModel):
    label: str | None = None
    store_listed: bool | None = None


class AppGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    package_ids: list[uuid.UUID] = Field(default_factory=list)


class AppGroupUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    description: str | None = None


class AppGroupMembers(BaseModel):
    package_ids: list[uuid.UUID] = Field(default_factory=list)


class AppGroupPackageRead(ORMModel):
    id: uuid.UUID
    package_name: str
    label: str | None


class AppGroupRead(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    packages: list[AppGroupPackageRead]


class PackageUploadResult(BaseModel):
    package: PackageRead
    version: PackageVersionRead
    signature_sha256: str | None
    # base64url of the signing certificate hash — exactly the value
    # PROVISIONING_DEVICE_ADMIN_SIGNATURE_CHECKSUM wants for QR provisioning.
    provisioning_checksum: str | None


# --------------------------------------------------------------------------- #
# Managed files
# --------------------------------------------------------------------------- #


class ManagedFileRead(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None
    original_filename: str
    media_type: str
    is_archive: bool
    artifact_sha256: str
    created_at: datetime
    default_dest_path: str | None = None
    default_persist: bool | None = None
    default_extract: bool | None = None
    default_extract_to: str | None = None
    default_overwrite: str | None = None


class ManagedFileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    default_dest_path: str | None = Field(default=None, max_length=512)
    default_persist: bool | None = None
    default_extract: bool | None = None
    default_extract_to: str | None = Field(default=None, max_length=512)
    default_overwrite: Literal["always", "if_newer", "if_absent", None] = None


class FileSelectionRead(BaseModel):
    file_id: uuid.UUID
    name: str
    applied_at: datetime


# --------------------------------------------------------------------------- #
# Admin: custom attributes
# --------------------------------------------------------------------------- #


class CustomAttributeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    attr_type: Literal["string", "number", "boolean", "date"] = "string"
    description: str | None = None


class CustomAttributeRead(ORMModel):
    id: uuid.UUID
    name: str
    attr_type: str
    description: str | None
    created_at: datetime


class DeviceAttributeSet(BaseModel):
    attribute_id: uuid.UUID
    value: str = ""


class DeviceAttributeRead(BaseModel):
    attribute_id: uuid.UUID
    name: str
    attr_type: str
    value: str


# --------------------------------------------------------------------------- #
# Bulk assignment (F2)
# --------------------------------------------------------------------------- #


class PolicyTargets(BaseModel):
    """Assign one policy to many targets in a single call.

    Policy-first, mirroring how an operator actually thinks: open the policy, pick
    the devices it covers.
    """

    device_ids: list[uuid.UUID] = Field(default_factory=list)
    group_ids: list[uuid.UUID] = Field(default_factory=list)
    tag_ids: list[uuid.UUID] = Field(default_factory=list)
    rank: int = 0
    pinned_version: int | None = None
    # replace: targets not listed have their assignment removed. add: purely additive.
    mode: Literal["replace", "add"] = "replace"


class PolicyTargetsResult(BaseModel):
    policy_id: uuid.UUID
    created: int
    removed: int
    unchanged: int
    devices_affected: int


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


class CommandCreate(BaseModel):
    command_type: CommandType
    params: dict[str, Any] = Field(default_factory=dict)
    ttl_hours: int | None = Field(default=None, ge=1, le=8760)
    max_attempts: int = Field(default=5, ge=1, le=50)


class CommandRead(ORMModel):
    id: uuid.UUID
    device_id: uuid.UUID
    command_type: CommandType
    params: dict[str, Any]
    status: CommandStatus
    created_at: datetime
    expires_at: datetime
    dispatched_at: datetime | None
    completed_at: datetime | None
    attempts: int
    max_attempts: int
    result: dict[str, Any] | None
    error: str | None


class CommandEnvelope(BaseModel):
    """The trimmed form handed to a device."""

    id: uuid.UUID
    command_type: CommandType
    params: dict[str, Any]
    expires_at: datetime


# --------------------------------------------------------------------------- #
# Check-in
# --------------------------------------------------------------------------- #


class CommandResultReport(BaseModel):
    command_id: uuid.UUID
    succeeded: bool
    result: dict[str, Any] | None = None
    error: str | None = None


class CheckinRequest(BaseModel):
    # What the device currently holds. Used to decide whether to resend the bundle.
    state_version: int | None = None
    # What it has actually applied — not the same claim (D28).
    applied_state_version: int | None = None
    apply_errors: list[str] = Field(default_factory=list)

    agent_version: str | None = None
    os_version: str | None = None
    results: list[CommandResultReport] = Field(default_factory=list)
    # Escape hatch for an agent whose local cache is gone.
    force_full: bool = False

    # Optional files the device currently has applied, chosen by its user in the
    # marketplace (F4). The device's report is authoritative and replaces the
    # server's record — omit the field entirely to leave it untouched.
    applied_optional_files: list[uuid.UUID] | None = None


class DeviceLogUploadRequest(BaseModel):
    """One diagnostic bundle from an enrolled device.

    The agent's own log, not `logcat`: `READ_LOGS` is unavailable to a normally
    installed app, and Android's guidance is to keep your own logs rather than use
    the system buffer (D87).
    """

    content: str
    # Which COLLECT_LOGS command this answers, when it answers one.
    command_id: uuid.UUID | None = None
    agent_version: str | None = None
    # Set when the agent's ring buffer dropped older entries before sending, so a
    # reader knows the record starts mid-story rather than at the beginning.
    truncated: bool = False


class DeviceLogUploadResponse(BaseModel):
    id: uuid.UUID
    size_bytes: int
    collected_at: datetime


class DeviceLogBundleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    device_id: uuid.UUID
    command_id: uuid.UUID | None
    size_bytes: int
    agent_version: str | None
    truncated: bool
    collected_at: datetime


class DeviceLogBundleDetail(DeviceLogBundleRead):
    """A capture with its text. Separate from the listing, which omits it."""

    content: str


class CheckinResponse(BaseModel):
    device_id: uuid.UUID
    state_version: int
    generated_at: datetime
    policy_changed: bool
    # Omitted when the device already holds the current version — the bandwidth
    # saving that makes frequent check-in viable on a metered link.
    desired_state: dict[str, Any] | None = None
    signature: str | None = None
    commands: list[CommandEnvelope] = Field(default_factory=list)
    next_checkin_seconds: int
    unknown_command_ids: list[str] = Field(default_factory=list)
