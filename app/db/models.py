"""ORM models for devices, grouping, policies, and assignments.

Two invariants drive the shape of this schema:

* Published policy versions are **immutable** (D2). Editing a policy creates a new
  ``PolicyVersion``; nothing ever mutates ``PolicyVersion.spec``. This is what lets
  us answer "what was actually on that device in March".
* An ``Assignment`` targets exactly one of device / group / tag, enforced by a CHECK
  constraint rather than convention, so the database itself rejects a malformed row.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Enum,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, JsonDict, UtcDateTime


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class EnrollmentState(str, enum.Enum):
    PENDING = "pending"
    ENROLLED = "enrolled"
    RETIRED = "retired"


class AssignmentScope(str, enum.Enum):
    """Target kind of an assignment. Also the specificity tiebreak in the resolver."""

    DEVICE = "device"
    GROUP = "group"
    TAG = "tag"


class ComplianceStatus(str, enum.Enum):
    """Whether a device has actually converged on its desired state."""

    UNKNOWN = "unknown"  # never reported
    COMPLIANT = "compliant"  # applied the current state_version cleanly
    DEGRADED = "degraded"  # applied, but some items failed
    FAILED = "failed"  # could not apply


class CommandType(str, enum.Enum):
    """Transient one-shots.

    Deliberately excludes anything expressible as policy. Installing an app is
    desired state, not a command — a device offline for three weeks must converge on
    the current intent, not replay a backlog. Only genuinely momentary actions belong
    here (D6).
    """

    REBOOT = "reboot"
    LOCK = "lock"
    WIPE = "wipe"
    LOCATE = "locate"
    SCREENSHOT = "screenshot"
    CLEAR_APP_DATA = "clear_app_data"


class CommandStatus(str, enum.Enum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"


# --------------------------------------------------------------------------- #
# Devices and grouping
# --------------------------------------------------------------------------- #

device_group_member = Table(
    "device_group_member",
    Base.metadata,
    Column("device_id", Uuid, ForeignKey("device.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", Uuid, ForeignKey("device_group.id", ondelete="CASCADE"), primary_key=True),
)

device_tag_member = Table(
    "device_tag_member",
    Base.metadata,
    Column("device_id", Uuid, ForeignKey("device.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Uuid, ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True),
)


class Device(Base):
    __tablename__ = "device"

    id: Mapped[uuid.UUID] = _uuid_pk()
    serial_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    model: Mapped[str | None] = mapped_column(String(64), default=None)
    imei: Mapped[str | None] = mapped_column(String(32), default=None)
    os_version: Mapped[str | None] = mapped_column(String(32), default=None)
    agent_version: Mapped[str | None] = mapped_column(String(32), default=None)
    enrollment_state: Mapped[EnrollmentState] = mapped_column(
        Enum(EnrollmentState, native_enum=False, length=16), default=EnrollmentState.PENDING
    )
    # Monotonic counter bumped whenever the device's desired state changes. The
    # check-in protocol keys off this to decide whether to send a bundle.
    state_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # What the device confirmed it actually applied. The gap between this and
    # state_version is the fleet's convergence lag — "the server has v7" and "the
    # device is running v7" are different claims and a dashboard needs both.
    acked_state_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    compliance_status: Mapped[ComplianceStatus] = mapped_column(
        Enum(ComplianceStatus, native_enum=False, length=16), default=ComplianceStatus.UNKNOWN
    )
    compliance_detail: Mapped[str | None] = mapped_column(Text, default=None)
    last_checkin_at: Mapped[datetime | None] = mapped_column(UtcDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)

    groups: Mapped[list[DeviceGroup]] = relationship(
        secondary=device_group_member, back_populates="devices", lazy="selectin"
    )
    tags: Mapped[list[Tag]] = relationship(
        secondary=device_tag_member, back_populates="devices", lazy="selectin"
    )


class DeviceGroup(Base):
    __tablename__ = "device_group"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)

    devices: Mapped[list[Device]] = relationship(
        secondary=device_group_member, back_populates="groups"
    )


class Tag(Base):
    __tablename__ = "tag"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)

    devices: Mapped[list[Device]] = relationship(
        secondary=device_tag_member, back_populates="tags"
    )


# --------------------------------------------------------------------------- #
# Policies
# --------------------------------------------------------------------------- #


class Policy(Base):
    """A named, single-concern policy. Its content lives in immutable versions."""

    __tablename__ = "policy"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(128), unique=True)
    # Validated against the policy type registry, not a DB enum, so adding a type
    # never requires a migration (Open/Closed).
    policy_type: Mapped[str] = mapped_column(String(64), index=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(UtcDateTime, default=None)

    versions: Mapped[list[PolicyVersion]] = relationship(
        back_populates="policy",
        cascade="all, delete-orphan",
        order_by="PolicyVersion.version",
        lazy="selectin",
    )

    @property
    def latest_version(self) -> PolicyVersion | None:
        return self.versions[-1] if self.versions else None


class PolicyVersion(Base):
    """An immutable published snapshot of a policy's spec."""

    __tablename__ = "policy_version"
    __table_args__ = (UniqueConstraint("policy_id", "version", name="uq_policy_version"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    policy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("policy.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    # Stored with exclude_unset=True: only explicitly-set fields are persisted, so
    # "absent" and "set to the default" stay distinguishable. The resolver depends
    # on this — an unset field must not contribute to a merge.
    spec: Mapped[dict] = mapped_column(JsonDict)
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    published_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)

    policy: Mapped[Policy] = relationship(back_populates="versions")


class Assignment(Base):
    """Binds a policy to a device, group, or tag at a given rank."""

    __tablename__ = "assignment"
    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN device_id IS NOT NULL THEN 1 ELSE 0 END) "
            "+ (CASE WHEN group_id IS NOT NULL THEN 1 ELSE 0 END) "
            "+ (CASE WHEN tag_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_assignment_single_target",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    policy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("policy.id", ondelete="CASCADE"), index=True
    )
    # NULL means "track latest published version"; set means pinned.
    pinned_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("policy_version.id", ondelete="RESTRICT"), default=None
    )

    scope: Mapped[AssignmentScope] = mapped_column(
        Enum(AssignmentScope, native_enum=False, length=16)
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("device.id", ondelete="CASCADE"), default=None, index=True
    )
    group_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("device_group.id", ondelete="CASCADE"), default=None, index=True
    )
    tag_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("tag.id", ondelete="CASCADE"), default=None, index=True
    )

    # Higher rank wins. Authoritative over scope specificity, which only breaks ties.
    rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)

    policy: Mapped[Policy] = relationship(lazy="selectin")
    pinned_version: Mapped[PolicyVersion | None] = relationship(lazy="selectin")


# --------------------------------------------------------------------------- #
# Enrollment and device identity
# --------------------------------------------------------------------------- #

enrollment_token_group = Table(
    "enrollment_token_group",
    Base.metadata,
    Column(
        "token_id", Uuid, ForeignKey("enrollment_token.id", ondelete="CASCADE"), primary_key=True
    ),
    Column("group_id", Uuid, ForeignKey("device_group.id", ondelete="CASCADE"), primary_key=True),
)

enrollment_token_tag = Table(
    "enrollment_token_tag",
    Base.metadata,
    Column(
        "token_id", Uuid, ForeignKey("enrollment_token.id", ondelete="CASCADE"), primary_key=True
    ),
    Column("tag_id", Uuid, ForeignKey("tag.id", ondelete="CASCADE"), primary_key=True),
)


class EnrollmentToken(Base):
    """A short-lived credential that authorizes one or more devices to enroll.

    Only a hash of the secret is stored, so a database dump does not yield usable
    enrollment credentials. The plaintext is returned exactly once, at creation.

    Group and tag scoping is what makes enrollment a single step: a device that
    enrolls with the "Field Tablets" token lands in that group and immediately
    inherits its policy stack, with no second manual assignment.
    """

    __tablename__ = "enrollment_token"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(128))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Leading characters of the secret, for identifying a token in the UI without
    # being able to reconstruct it.
    prefix: Mapped[str] = mapped_column(String(12))

    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    # A KME profile can enroll a whole shipment, so one token legitimately serves
    # many devices. NULL means unlimited until expiry.
    max_uses: Mapped[int | None] = mapped_column(Integer, default=None)
    use_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)

    groups: Mapped[list[DeviceGroup]] = relationship(
        secondary=enrollment_token_group, lazy="selectin"
    )
    tags: Mapped[list[Tag]] = relationship(secondary=enrollment_token_tag, lazy="selectin")

    def is_usable(self, *, now: datetime) -> bool:
        if self.revoked_at is not None or now >= self.expires_at:
            return False
        return self.max_uses is None or self.use_count < self.max_uses


class DeviceCertificate(Base):
    """A client certificate issued to a device.

    Revocation is a row update rather than a CRL or OCSP responder (D25): at this
    fleet size a database check during authentication is simpler to operate and
    strictly more current than a periodically published list.
    """

    __tablename__ = "device_certificate"

    id: Mapped[uuid.UUID] = _uuid_pk()
    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("device.id", ondelete="CASCADE"), index=True
    )
    serial_hex: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    not_valid_after: Mapped[datetime] = mapped_column(UtcDateTime)
    issued_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime, default=None)
    revoked_reason: Mapped[str | None] = mapped_column(String(128), default=None)

    device: Mapped[Device] = relationship(lazy="selectin")


class DeviceCommand(Base):
    """A queued transient action for one device.

    Delivery is at-least-once: a command stays deliverable until acknowledged, so a
    device that goes dark mid-execution gets it again. Every command type is
    therefore required to be idempotent — rebooting an already-rebooted device or
    wiping an already-wiped one is harmless.

    ``expires_at`` is what keeps the queue honest offline. A `LOCATE` issued three
    weeks ago answers a question nobody is still asking; it expires rather than
    surprising a device that just came back on the air.
    """

    __tablename__ = "device_command"

    id: Mapped[uuid.UUID] = _uuid_pk()
    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("device.id", ondelete="CASCADE"), index=True
    )
    command_type: Mapped[CommandType] = mapped_column(
        Enum(CommandType, native_enum=False, length=24)
    )
    params: Mapped[dict] = mapped_column(JsonDict, default=dict)
    status: Mapped[CommandStatus] = mapped_column(
        Enum(CommandStatus, native_enum=False, length=16),
        default=CommandStatus.PENDING,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    dispatched_at: Mapped[datetime | None] = mapped_column(UtcDateTime, default=None)
    completed_at: Mapped[datetime | None] = mapped_column(UtcDateTime, default=None)

    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5, nullable=False)

    result: Mapped[dict | None] = mapped_column(JsonDict, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)

    def is_live(self, *, now: datetime) -> bool:
        """Still worth delivering: not finished, not expired, not out of attempts."""
        if self.status in (CommandStatus.SUCCEEDED, CommandStatus.FAILED, CommandStatus.EXPIRED):
            return False
        return now < self.expires_at and self.attempts < self.max_attempts


# --------------------------------------------------------------------------- #
# Artifacts and app packages
# --------------------------------------------------------------------------- #


class PartRole(str, enum.Enum):
    BASE = "base"
    SPLIT = "split"
    OBB = "obb"


class Artifact(Base):
    """A content-addressed blob. The digest is the primary key (D8)."""

    __tablename__ = "artifact"

    sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    media_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)


class AppPackage(Base):
    """An Android application, tracked across versions.

    ``signature_sha256`` is pinned at first upload. Android refuses an update whose
    signing certificate differs from the installed app, so a mismatch here is a
    guaranteed on-device failure — caught at upload, where the error can say why.
    """

    __tablename__ = "app_package"

    id: Mapped[uuid.UUID] = _uuid_pk()
    package_name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    label: Mapped[str | None] = mapped_column(String(255), default=None)
    signature_sha256: Mapped[str | None] = mapped_column(String(64), default=None)
    signature_scheme: Mapped[str | None] = mapped_column(String(8), default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)

    versions: Mapped[list[AppPackageVersion]] = relationship(
        back_populates="package",
        cascade="all, delete-orphan",
        order_by="AppPackageVersion.version_code",
        lazy="selectin",
    )

    @property
    def latest_version(self) -> AppPackageVersion | None:
        return self.versions[-1] if self.versions else None


class AppPackageVersion(Base):
    __tablename__ = "app_package_version"
    __table_args__ = (
        UniqueConstraint("package_id", "version_code", name="uq_package_version_code"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    package_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app_package.id", ondelete="CASCADE"), index=True
    )
    version_code: Mapped[int] = mapped_column(Integer)
    version_name: Mapped[str | None] = mapped_column(String(128), default=None)
    min_sdk: Mapped[int | None] = mapped_column(Integer, default=None)
    target_sdk: Mapped[int | None] = mapped_column(Integer, default=None)
    uploaded_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)

    package: Mapped[AppPackage] = relationship(back_populates="versions")
    files: Mapped[list[AppPackageFile]] = relationship(
        back_populates="version", cascade="all, delete-orphan", lazy="selectin"
    )


class AppPackageFile(Base):
    """One installable part: the base APK, a split, or an OBB expansion file."""

    __tablename__ = "app_package_file"

    id: Mapped[uuid.UUID] = _uuid_pk()
    version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("app_package_version.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[PartRole] = mapped_column(Enum(PartRole, native_enum=False, length=8))
    file_name: Mapped[str] = mapped_column(String(255))
    split_name: Mapped[str | None] = mapped_column(String(128), default=None)
    artifact_sha256: Mapped[str] = mapped_column(
        String(64), ForeignKey("artifact.sha256", ondelete="RESTRICT"), index=True
    )

    version: Mapped[AppPackageVersion] = relationship(back_populates="files")
    artifact: Mapped[Artifact] = relationship(lazy="selectin")


class EffectivePolicyCache(Base):
    """Memoized resolver output for one device, invalidated on any input change.

    Invalidation flips ``stale`` rather than deleting the row. The retained payload
    is the baseline the refresh compares against to decide whether
    ``Device.state_version`` should move — deleting it would make every invalidation
    look like a change and wake the fleet over cosmetic edits.
    """

    __tablename__ = "effective_policy_cache"

    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("device.id", ondelete="CASCADE"), primary_key=True
    )
    state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict] = mapped_column(JsonDict)
    stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)
