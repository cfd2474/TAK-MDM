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
    DateTime,
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

from app.db.base import Base, JsonDict


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
    # check-in protocol (Chunk 3) keys off this to decide whether to send a bundle.
    state_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_checkin_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    devices: Mapped[list[Device]] = relationship(
        secondary=device_group_member, back_populates="groups"
    )


class Tag(Base):
    __tablename__ = "tag"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

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
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    policy: Mapped[Policy] = relationship(lazy="selectin")
    pinned_version: Mapped[PolicyVersion | None] = relationship(lazy="selectin")


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
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
