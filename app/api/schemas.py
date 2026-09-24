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
from app.services.locations import MAX_BATCH as MAX_LOCATION_BATCH


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
    compliance_warnings: str | None = None
    last_checkin_at: datetime | None
    created_at: datetime


class NamedCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None


class GroupRead(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None


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


class PrimaryEnrollmentQrIssued(BaseModel):
    """A fresh 15-minute QR minted from the active primary token."""

    token: EnrollmentTokenRead
    secret: str
    expires_at: datetime
    provisioning: dict[str, Any]


class BypassPinRequest(BaseModel):
    """A device asking whether the operator typed this install's bypass PIN.

    ⚠️ **`secret` is optional because only one of the two paths needs it.**
    Before enrolment the enrollment token is what authorizes the question —
    without it that endpoint would be an unauthenticated oracle for a six-digit
    secret. After enrolment the client certificate identifies the caller and the
    token no longer exists, so the agent sends `{"pin": ...}` alone.

    It was required, and the enrolled agent's body was therefore rejected with a
    422 that surfaced on the tablet as "could not reach the server". The
    server-side test passed throughout because it sent `secret: ""` — a body the
    agent never produces. A test that constructs its own request can only ever
    check the server against the author's idea of the client.
    """

    secret: str = ""
    pin: str


class BypassPinResult(BaseModel):
    accepted: bool
    attempts_remaining: int


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
    created_at: datetime
    versions: list[PackageVersionRead]


class PackageUpdate(BaseModel):
    label: str | None = None


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


class LocationReport(BaseModel):
    """One position the device recorded, delivered on a later check-in (W106).

    ⚠️ **`recorded_at` is the device's clock, not ours.** The agent reports *last
    known* position on purpose — a live fix can take minutes indoors — so a point
    can legitimately be older than the check-in carrying it, sometimes by hours.
    The server stores its own receipt time alongside, and the two together are
    what distinguish a stale fix from a delayed delivery.

    The bounds here are the same ones the table enforces. Being refused twice is
    deliberate: this catches a malformed report with a readable 422, and the CHECK
    constraint catches anything that ever reaches the database another way.
    """

    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0)
    provider: str | None = Field(default=None, max_length=32)
    recorded_at: datetime


class OemLicenseReport(BaseModel):
    """What a device says about its OEM licence (W227).

    One shape from both agent flavours — the AOSP build reports
    `NOT_APPLICABLE` rather than omitting the field — so the console renders one
    status column and the server never has to guess which build it is talking to.

    ⚠️ **`status` is a free string, not an enum, and that is deliberate.** A
    newer agent reporting a status this server has not heard of must not 422 its
    whole check-in: the device would then fail to report its policy convergence,
    its battery and its location, all over one unrecognised word. It is stored
    verbatim and the console falls back to showing it raw.

    ⚠️ **No field here carries the licence key**, and none ever should.
    `masked_key` is the vendor's own masking, which is what lets an operator see
    *which* licence is active without the secret making a return trip.
    """

    status: str = Field(max_length=32)
    #: Samsung's own masking, e.g. `KLM09-…-A1B2C`. Never the key.
    masked_key: str | None = Field(default=None, max_length=64)
    #: Epoch milliseconds, as the device reported it.
    activated_at: int | None = None
    #: The vendor's numeric code, kept verbatim for a support conversation.
    error_code: int | None = None
    detail: str | None = Field(default=None, max_length=2000)


class CheckinRequest(BaseModel):
    # What the device currently holds. Used to decide whether to resend the bundle.
    state_version: int | None = None
    # What it has actually applied — not the same claim (D28).
    applied_state_version: int | None = None
    apply_errors: list[str] = Field(default_factory=list)
    #: Things worth reporting about a device that nonetheless converged (W50).
    #: Kept apart from apply_errors because they must never move compliance:
    #: a policy asking for an older build than the device carries is a mismatch
    #: to surface, not a failure to apply.
    apply_warnings: list[str] = Field(default_factory=list)

    agent_version: str | None = None
    # The numeric versionCode. The display version above cannot be compared, and
    # the self-update gate has to decide "is the target newer than this" (W27).
    agent_version_code: int | None = None
    os_version: str | None = None
    # The ATAK actually installed, so the console can flag a plugin built for a
    # different one. Absent means "no ATAK", which is not the same as "unknown" —
    # an agent too old to report it also sends nothing, so the server only ever
    # overwrites what it is told (W32).
    atak_package: str | None = None
    atak_version: str | None = None
    #: What this device can run, from `Build.SUPPORTED_ABIS`, most-preferred
    #: first — and the API level it is on. Both optional, because an older agent
    #: reports neither and must not have its record erased for staying quiet.
    supported_abis: list[str] | None = None
    sdk_int: int | None = None

    #: Hardware facts an operator wants on the device page (W108). All optional,
    #: all None-means-unsaid: an older agent reports none of them and must not
    #: have its record blanked for staying quiet.
    #:
    #: ⚠️ `has_telephony` is what makes an absent IMEI interpretable. `False` says
    #: "this device has no cellular radio" — definitive. `None` says "the agent did
    #: not say". Collapsing the two would send an operator looking for a permission
    #: bug on a Wi-Fi-only tablet.
    has_telephony: bool | None = None
    imei: str | None = Field(default=None, max_length=32)
    imei2: str | None = Field(default=None, max_length=32)
    phone_number: str | None = Field(default=None, max_length=32)
    battery_level: int | None = Field(default=None, ge=0, le=100)
    battery_charging: bool | None = None

    #: The device's OEM licence, as of its last apply (W227). None-means-unsaid
    #: like every other optional fact here: an agent too old to report it must
    #: not have its record blanked for staying quiet, and an operator reading
    #: "not licensed" on a tablet whose agent simply predates the feature would
    #: go looking for a key that was never missing.
    oem_license: OemLicenseReport | None = None

    results: list[CommandResultReport] = Field(default_factory=list)
    # Escape hatch for an agent whose local cache is gone.
    force_full: bool = False

    # Optional files the device currently has applied, chosen by its user in the
    # marketplace (F4). The device's report is authoritative and replaces the
    # server's record — omit the field entirely to leave it untouched.
    applied_optional_files: list[uuid.UUID] | None = None

    #: Positions buffered since the last successful check-in (W106).
    #:
    #: Unlike `applied_optional_files` above, this is *not* None-versus-empty:
    #: location history is append-only, so "said nothing" and "had nothing to add"
    #: are the same statement and there is no record for an empty list to erase.
    #: An agent too old to know the field simply never sends it.
    #:
    #: ⚠️ Capped, and the cap is enforced here rather than by trimming later. A
    #: device with a long backlog sends it across several check-ins; being told so
    #: by a 422 is a debuggable failure, whereas silently keeping the first 500 of
    #: 2,000 points would leave a gap nobody could account for.
    #:
    #: The limit is imported rather than repeated: the schema's 422 and the
    #: service's "only the first N were read" warning describe the same threshold,
    #: and two literals would eventually disagree about where it is.
    locations: list[LocationReport] = Field(
        default_factory=list, max_length=MAX_LOCATION_BATCH
    )


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
    # Echoed so the on-device console can show the operator-assigned name.
    # Null when the device has not been named.
    name: str | None = None
    # The names of the policies currently reaching this device, so the on-device
    # console can list them without the server sending policy content.
    policy_names: list[str] = Field(default_factory=list)
    # An agent build this device should install now, or null. Decided server-side
    # per device (W27) — candidate builds reach canaries only.
    agent_update: dict[str, Any] | None = None
    #: ⚠️ Optional so an older agent, which does not read it, is unaffected — and
    #: so a device that has never seen it keeps its existing behaviour rather than
    #: failing to parse the response it depends on to be managed at all.
    certificate: CertificatePolicy | None = None
    # Omitted when the device already holds the current version — the bandwidth
    # saving that makes frequent check-in viable on a metered link.
    desired_state: dict[str, Any] | None = None
    signature: str | None = None
    commands: list[CommandEnvelope] = Field(default_factory=list)
    next_checkin_seconds: int
    unknown_command_ids: list[str] = Field(default_factory=list)


class CertificatePolicy(BaseModel):
    """What the server wants devices to do about their certificates (W174)."""

    #: Renew once this many days of validity remain.
    renew_within_days: int
    #: How long a renewed certificate lasts, so a device can sanity-check what it
    #: was given rather than assume.
    validity_days: int


class CertificateRenewalRequest(BaseModel):
    """A device asking for a new certificate over its existing connection (W174)."""

    csr_pem: str = Field(min_length=1, max_length=8192)


class CertificateRenewalResponse(BaseModel):
    certificate_pem: str
    #: The whole trust bundle, not just the issuer — a device that stored only its
    #: own issuer could not build a chain once that intermediate retired.
    ca_pem: str
    serial_hex: str
    not_valid_after: datetime
