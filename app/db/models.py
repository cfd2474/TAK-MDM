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

"""ORM models for devices, grouping, policies, and assignments.

Two invariants drive the shape of this schema:

* Published policy versions are **immutable** (D2). Editing a policy creates a new
  ``PolicyVersion``; nothing ever mutates ``PolicyVersion.spec``. This is what lets
  us answer "what was actually on that device in March".
* An ``Assignment`` targets exactly one of device / group, enforced by a CHECK
  constraint rather than convention, so the database itself rejects a malformed row.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Table,
    Text,
    UniqueConstraint,
    Uuid,
    false as sa_false,
    true as sa_true,
)
from sqlalchemy import text as sa_text
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
    #: Make the device announce itself so a person can find it — the "find my
    #: device" call. A command and not a policy for the reason the rest of this
    #: enum exists: it is momentary, and a device offline for a week must not
    #: start ringing when it comes back to answer a question somebody asked and
    #: has long since resolved. See the TTL table in `services/commands.py`.
    PING = "ping"
    WIPE = "wipe"
    LOCATE = "locate"
    SCREENSHOT = "screenshot"
    CLEAR_APP_DATA = "clear_app_data"
    # Ask the device to upload its own diagnostic log. A command rather than a
    # policy because it is a momentary request for a snapshot, not state to
    # converge on — and because an operator wants it *now*, on a device that is
    # already misbehaving.
    COLLECT_LOGS = "collect_logs"


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


class Device(Base):
    __tablename__ = "device"

    id: Mapped[uuid.UUID] = _uuid_pk()
    serial_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # Failed guesses at the provisioning bypass PIN, once this device has an
    # identity of its own (W117). The enrollment token's counter covers the
    # pre-enrolment case; the token is destroyed at enrolment, so the counter has
    # to follow whichever credential the check actually used.
    bypass_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # An operator-assigned friendly name. Optional: a freshly enrolled device has
    # only the identity it reported. The console falls back to the serial for
    # display when this is unset.
    name: Mapped[str | None] = mapped_column(String(128), default=None)
    model: Mapped[str | None] = mapped_column(String(64), default=None)
    imei: Mapped[str | None] = mapped_column(String(32), default=None)
    #: The second SIM slot's IMEI on a dual-SIM device (W108). NULL on a device
    #: with one slot, and on every device that has no cellular radio at all.
    imei2: Mapped[str | None] = mapped_column(String(32), default=None)
    #: The line number, when the carrier provisioned one onto the SIM.
    #:
    #: ⚠️ **Very often NULL even on a perfectly working cellular device.** The
    #: number is stored on the SIM only if the carrier put it there, and many do
    #: not. Absence here is normal and is not a fault to chase.
    phone_number: Mapped[str | None] = mapped_column(String(32), default=None)
    #: Whether this device has a cellular radio at all.
    #:
    #: ⚠️ **This is what makes an absent IMEI readable.** Without it, "this tablet
    #: has no modem" and "the IMEI could not be read" are the same blank on the
    #: page, and an operator would go hunting for a permission bug on a Wi-Fi-only
    #: device. NULL means an agent too old to say — a third state again.
    has_telephony: Mapped[bool | None] = mapped_column(Boolean, default=None)
    #: Battery charge 0-100, as of `last_checkin_at`.
    #:
    #: ⚠️ Shown against that timestamp rather than as a bare number: 4% reported a
    #: minute ago and 4% reported yesterday are different situations, and the bare
    #: figure reads as current.
    battery_level: Mapped[int | None] = mapped_column(Integer, default=None)
    battery_charging: Mapped[bool | None] = mapped_column(Boolean, default=None)
    os_version: Mapped[str | None] = mapped_column(String(32), default=None)
    agent_version: Mapped[str | None] = mapped_column(String(32), default=None)
    # The agent's versionCode, distinct from the display versionName above: the
    # self-update gate has to compare numerically, and Android's own upgrade rule
    # is on the code. NULL until an agent new enough to report it checks in.
    agent_version_code: Mapped[int | None] = mapped_column(Integer, default=None)
    # Which ATAK the device actually has, reported at check-in. An ATAK plugin
    # only loads in the build it was compiled against, and a mismatch is silent on
    # the device — the plugin installs and never appears — so this is what lets the
    # console say so (W32). NULL until an agent new enough to report it checks in,
    # or when no ATAK is installed.
    atak_package: Mapped[str | None] = mapped_column(String(128), default=None)
    atak_version: Mapped[str | None] = mapped_column(String(64), default=None)
    #: What this device can actually run, most-preferred first, comma-separated
    #: (W96). NULL means an agent too old to report it — never "runs nothing".
    supported_abis: Mapped[str | None] = mapped_column(String(128), default=None)
    #: `Build.VERSION.SDK_INT`. The API level, which `os_version` ("14") is not:
    #: comparing a build's `min_sdk` needs the number, not the marketing name.
    sdk_int: Mapped[int | None] = mapped_column(Integer, default=None)
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
    # Things worth telling the operator about a device that *has* converged (W50).
    #
    # Deliberately not folded into compliance_detail, and deliberately unable to
    # move compliance_status: a policy naming an older build than the device
    # already carries is a mismatch to report, not a failure to converge. Filing it
    # as an error marked healthy devices DEGRADED — which, because the agent-update
    # gate refuses a DEGRADED device, also cut them off from agent updates entirely.
    compliance_warnings: Mapped[str | None] = mapped_column(Text, default=None)
    last_checkin_at: Mapped[datetime | None] = mapped_column(UtcDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)

    groups: Mapped[list[DeviceGroup]] = relationship(
        secondary=device_group_member, back_populates="devices", lazy="selectin"
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


# --------------------------------------------------------------------------- #
# Policies
# --------------------------------------------------------------------------- #


class PolicyProfile(Base):
    """A named bundle of single-concern policies, edited as tabs and assigned as a
    unit.

    A profile does not hold policy content itself — each of its tabs is a real
    ``Policy`` row (``Policy.profile_id`` set), so the resolver, the merge registry
    and the stacking view keep working unchanged. The profile is a bulk editor and
    a bulk-assignment target over those children (DW5).
    """

    __tablename__ = "policy_profile"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)
    created_by: Mapped[str | None] = mapped_column(String(128), default=None)
    archived_at: Mapped[datetime | None] = mapped_column(UtcDateTime, default=None)

    sections: Mapped[list[Policy]] = relationship(
        back_populates="profile",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


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
    # A template is a reusable blueprint: it is never assigned and never reaches a
    # device (the resolver skips it), it only gets cloned into a real policy.
    is_template: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default=sa_false()
    )
    # Set when this policy is a section of a profile: it is then managed only
    # through that profile and hidden from the standalone policy list. NULL is an
    # ordinary standalone policy.
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("policy_profile.id", ondelete="CASCADE"), default=None, index=True
    )
    # Which creator-catalog category this section fills (e.g. "password"). NULL for
    # standalone policies.
    profile_section: Mapped[str | None] = mapped_column(String(64), default=None)

    versions: Mapped[list[PolicyVersion]] = relationship(
        back_populates="policy",
        cascade="all, delete-orphan",
        order_by="PolicyVersion.version",
        lazy="selectin",
    )
    profile: Mapped[PolicyProfile | None] = relationship(back_populates="sections")

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
    # Who published it. Nullable because versions created before authentication
    # existed genuinely have no author, and inventing one would be a lie in an
    # audit trail.
    published_by: Mapped[str | None] = mapped_column(String(128), default=None)

    policy: Mapped[Policy] = relationship(back_populates="versions")


class Assignment(Base):
    """Binds a policy to a device or a group at a given rank."""

    __tablename__ = "assignment"
    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN device_id IS NOT NULL THEN 1 ELSE 0 END) "
            "+ (CASE WHEN group_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
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

    # Higher rank wins. Authoritative over scope specificity, which only breaks ties.
    rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)

    policy: Mapped[Policy] = relationship(lazy="selectin")
    pinned_version: Mapped[PolicyVersion | None] = relationship(lazy="selectin")


class ProfileAssignment(Base):
    """Binds a whole profile to a device or a group at a given rank.

    The resolver expands one of these into an assignment of every section the
    profile owns, so a profile stacks against standalone policies exactly as its
    sections would individually — at this one rank.
    """

    __tablename__ = "profile_assignment"
    __table_args__ = (
        CheckConstraint(
            "(CASE WHEN device_id IS NOT NULL THEN 1 ELSE 0 END) "
            "+ (CASE WHEN group_id IS NOT NULL THEN 1 ELSE 0 END) = 1",
            name="ck_profile_assignment_single_target",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    profile_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("policy_profile.id", ondelete="CASCADE"), index=True
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
    rank: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)

    profile: Mapped[PolicyProfile] = relationship(lazy="selectin")


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


class EnrollmentToken(Base):
    """A short-lived credential that authorizes one or more devices to enroll.

    Only a hash of the secret is stored, so a database dump does not yield usable
    enrollment credentials. The plaintext is returned exactly once, at creation.

    Group scoping is what makes enrollment a single step: a device that
    enrolls with the "Field Tablets" token lands in that group and immediately
    inherits its policy stack, with no second manual assignment.
    """

    __tablename__ = "enrollment_token"
    __table_args__ = (
        # "At most one live primary" as a database guarantee rather than an
        # application-level hope — the same reasoning as D24's unique device
        # serial or R13's unique identifier value. Partial: a *revoked* primary
        # does not block a new one, which is exactly the retire-and-replace flow.
        # The index only ever contains rows matching the WHERE clause, so
        # uniqueness on a single always-true column there means "at most one".
        Index(
            "uq_enrollment_token_one_live_primary",
            "is_primary",
            unique=True,
            postgresql_where=sa_text("is_primary AND revoked_at IS NULL"),
            sqlite_where=sa_text("is_primary AND revoked_at IS NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(128))
    # Authentication looks only at this. Enrollment matches an indexed hash and
    # never decrypts anything.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # The same secret, encrypted under a key held in pki/ rather than the database.
    # Exists solely so an operator can re-display a token's QR; see
    # app/security/token_vault.py for why this is a deliberate, bounded weakening.
    # Nullable: tokens created before this existed cannot be recovered.
    token_ciphertext: Mapped[str | None] = mapped_column(Text, default=None)
    # Leading characters of the secret, for identifying a token in the UI.
    prefix: Mapped[str] = mapped_column(String(12))

    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    # A KME profile can enroll a whole shipment, so one token legitimately serves
    # many devices. NULL means unlimited until expiry.
    max_uses: Mapped[int | None] = mapped_column(Integer, default=None)
    use_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UtcDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)
    # A token authorizes devices onto the fleet, so who minted it is worth keeping.
    created_by: Mapped[str | None] = mapped_column(String(128), default=None)

    # Marks the one standing enrollment credential an operator manages day to day
    # (Chunk 14). Its raw secret is never displayed; only a signed, 15-minute
    # derivative of it is ever shown, as a QR. Everything else about this row —
    # hash, vault seal, scoping, revocation — is the ordinary EnrollmentToken
    # machinery, unchanged; a primary is just a token nobody types in by hand.
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Failed guesses at the provisioning bypass PIN (W117). Per token rather than
    # global: one global counter would let anyone holding a token lock every
    # other operator out of provisioning.
    bypass_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    groups: Mapped[list[DeviceGroup]] = relationship(
        secondary=enrollment_token_group, lazy="selectin"
    )

    def is_usable(self, *, now: datetime) -> bool:
        if self.revoked_at is not None or now >= self.expires_at:
            return False
        return self.max_uses is None or self.use_count < self.max_uses

    def unusable_reason(self, *, now: datetime) -> str | None:
        """Why this token cannot enrol a device, for showing an operator.

        Worth being specific about: handing someone a QR that cannot work costs
        them a factory reset before they find out.
        """
        if self.revoked_at is not None:
            return "this token has been revoked"
        if now >= self.expires_at:
            return "this token expired"
        if self.max_uses is not None and self.use_count >= self.max_uses:
            return f"this token has been used all {self.max_uses} time(s)"
        return None


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


class IdentifierKind(str, enum.Enum):
    """Where a device identifier came from, strongest first.

    Priority matters: a device reports several at once, and when two of them point
    at different records the match has to resolve the same way every time.
    """

    #: ``Build.getSerial()`` — the hardware serial. Survives a factory reset.
    SERIAL = "serial"
    #: A record's original ``serial_number``, backfilled at migration. Preserves the
    #: pre-existing matching behaviour exactly, whatever that string actually was.
    LEGACY = "legacy"
    #: ``Settings.Secure.ANDROID_ID``. **Changes on factory reset**, so it is a weak
    #: identifier kept only to re-adopt a device that once enrolled under it.
    ANDROID_ID = "android_id"


#: Match order. A device supplying several identifiers is resolved by the
#: strongest that is already known, so the outcome does not depend on dict order.
IDENTIFIER_PRIORITY: tuple[IdentifierKind, ...] = (
    IdentifierKind.SERIAL,
    IdentifierKind.LEGACY,
    IdentifierKind.ANDROID_ID,
)


class DeviceIdentifier(Base):
    """One way a device has identified itself.

    A device's reported identity is not a constant — this fleet proved that twice,
    when `Build.getSerial()` was refused and the agent fell back to `ANDROID_ID`,
    which then changed on each factory reset. Matching re-enrolment on a single
    string (D24) forks a new record every time that string moves, orphaning the
    device's history and its group membership.

    Keeping the set means a device that arrives on *any* identity it has used
    before re-adopts its own record, and a new identity source costs a row rather
    than a protocol change.
    """

    __tablename__ = "device_identifier"
    __table_args__ = (
        # Globally unique across kinds: one value must never name two devices, or
        # matching stops being deterministic.
        UniqueConstraint("value", name="uq_device_identifier_value"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("device.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[IdentifierKind] = mapped_column(
        Enum(IdentifierKind, native_enum=False, length=16)
    )
    value: Mapped[str] = mapped_column(String(128), index=True)
    first_seen_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)


class DeviceLogBundle(Base):
    """One upload of a device's own diagnostic log.

    Stored as text on the row rather than in the content-addressed artifact store.
    That store exists to deduplicate blobs many devices download; a log bundle is
    unique to one device and one moment, so content addressing buys nothing and
    would cost a reference-counted delete on data that should simply age out.

    Capped at upload, so a misbehaving or hostile agent cannot fill the disk one
    check-in at a time.
    """

    __tablename__ = "device_log_bundle"

    id: Mapped[uuid.UUID] = _uuid_pk()
    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("device.id", ondelete="CASCADE"), index=True
    )
    # Which request produced it, when there was one. Null for a bundle the agent
    # sent on its own initiative rather than in answer to a command.
    command_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("device_command.id", ondelete="SET NULL"), default=None
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    # What the device said about itself when it uploaded, so a bundle stays
    # interpretable after the device has moved on to another agent build.
    agent_version: Mapped[str | None] = mapped_column(String(32), default=None)
    # True when the agent's own cap trimmed the oldest entries before sending.
    truncated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    collected_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)


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
    # The launcher icon, extracted from the APK (W53), stored as the original PNG
    # or WEBP bytes. On the row rather than in the artifact store because these are
    # small, and a column cannot go missing independently of the record that points
    # at it. None for an app whose icon is a vector drawable.
    #
    # ⚠️ **Deferred**, and that is load-bearing. Fourteen places `select(AppPackage)`
    # and one of them — `desired_state` enriching app configs — runs on the **device
    # check-in path**, once per configured app per check-in. Loaded eagerly, every
    # check-in would drag a blob across the wire that nothing on that path reads;
    # our own agent icon is 213 KB. Ask for presence with `icon_media_type`, which
    # is a 32-char column on the main row, not by touching these bytes.
    icon_data: Mapped[bytes | None] = mapped_column(LargeBinary, default=None, deferred=True)
    icon_media_type: Mapped[str | None] = mapped_column(String(32), default=None)
    # The version whose APK was last inspected for a name and an icon.
    #
    # ⚠️ Without this the boot-time backfill never converges. It selects rows with
    # no icon, but an app whose icon is a vector drawable can never *get* one —
    # so it stays selected, and its base APK is re-read in full at every start,
    # forever, to produce nothing. Outlook is 172 MB and costs 1.4 s and 356 MB of
    # heap per attempt. Recording the attempt is what ends that; comparing against
    # the *version* means a newly uploaded build is still re-examined.
    icon_source_version_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, default=None)
    # True when the bytes are an adaptive icon's foreground layer, which is drawn
    # on a 108dp canvas of which only the centre 72dp is meant to be seen. The
    # display has to crop it; a legacy icon must be shown whole.
    icon_adaptive: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default=sa_false()
    )
    # Offered in the ATLAS store — the curated set that ships with a deployment and
    # is presented to operators as ready-to-assign.
    store_listed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default=sa_false()
    )
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


app_group_member = Table(
    "app_group_member",
    Base.metadata,
    Column("group_id", Uuid, ForeignKey("app_group.id", ondelete="CASCADE"), primary_key=True),
    Column("package_id", Uuid, ForeignKey("app_package.id", ondelete="CASCADE"), primary_key=True),
    Column("position", Integer, nullable=False, default=0),
)


class AppGroup(Base):
    """A named set of app packages, so a policy can reference the group rather than
    listing every package by hand."""

    __tablename__ = "app_group"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)

    packages: Mapped[list[AppPackage]] = relationship(
        secondary=app_group_member,
        order_by=app_group_member.c.position,
        lazy="selectin",
    )


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
    #: Where this build came from (W97): a source name like "fdroid", or NULL for
    #: the honest answer about everything uploaded by hand. An APK fetched from a
    #: remote repository and one an operator carried in are different things to
    #: trust, and only the record can say which afterwards.
    source: Mapped[str | None] = mapped_column(String(32), default=None)
    source_url: Mapped[str | None] = mapped_column(String(1024), default=None)
    #: CPU architectures this build carries native code for, comma-separated
    #: (W96). ⚠️ **NULL and empty mean different things.** NULL is "uploaded
    #: before anything looked"; empty is "looked, and it carries none" — which is
    #: the build that runs on every device. Collapsing the two would let an
    #: unscanned arm64-only APK pass for universal.
    abis: Mapped[str | None] = mapped_column(String(128), default=None)
    # The ATAK build an ATAK plugin was compiled against, e.g.
    # "com.atakmap.app@5.5.0.CIV". A plugin only loads in that build, so this is a
    # **compatibility key, not a version** — two builds of one plugin targeting
    # different ATAK lines are alternatives, and their versionCodes cannot
    # meaningfully be ranked against each other (D45). NULL for anything that is
    # not an ATAK plugin.
    plugin_api: Mapped[str | None] = mapped_column(String(128), default=None)
    # The managed configuration this build declares, as JSON: `{key: restrictionType}`
    # for every top-level key in its `<restrictions>` document (W49).
    #
    # Stored rather than re-read because the desired state is rebuilt on every
    # check-in for every device, and rescanning a 130 MB Chrome APK each time to
    # recover three integers is not a trade worth making. Safe to store precisely
    # because a version row is **immutable** — its bytes never change, so this can
    # never drift from the build it describes. NULL means "not scanned yet", which
    # is different from "declares nothing" (an empty object).
    declared_config: Mapped[str | None] = mapped_column(Text, default=None)
    # Eligible for *automatic* selection — "latest", or "newest above the floor".
    # A held build stays in the library and can still be reached by an explicit
    # `artifact_sha256` pin, because a pin names one exact build and is a
    # deliberate act; making it also require publication would be a second gate
    # with no separate meaning, and a pin that silently did nothing is the R17
    # failure wearing a different hat.
    published: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default=sa_true()
    )
    uploaded_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)

    package: Mapped[AppPackage] = relationship(back_populates="versions")
    files: Mapped[list[AppPackageFile]] = relationship(
        back_populates="version", cascade="all, delete-orphan", lazy="selectin"
    )

    @property
    def has_obb(self) -> bool:
        """True when this version carries an OBB expansion file.

        A normally-installed Device Owner cannot place another app's OBB on the
        device — scoped storage blocks ``Android/obb/<pkg>/`` even with all-files
        access (verified EACCES on ``SM-X520``). Surfaced so the operator sees it
        before assigning, not as missing assets at runtime.
        """
        return any(f.role == PartRole.OBB for f in self.files)


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


class ManagedFile(Base):
    """An arbitrary file an admin has published: a zip, a .pref, a cert, a map source.

    Separate from :class:`AppPackage` because APKs are inspected and validated against
    Android-specific structure, while these are opaque payloads whose meaning comes
    entirely from the policy that places them.
    """

    __tablename__ = "managed_file"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, default=None)
    original_filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    # Detected at upload, so the policy layer can refuse to mark a non-archive for
    # extraction instead of failing on the device.
    is_archive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # A zip carrying MANIFEST/manifest.xml that satisfies ATAK's own validity
    # rules (W91, Android reference §11). Detected at upload for the same reason
    # `is_archive` is: the policy picker can then offer packages rather than
    # arbitrary zips, and a file ATAK would ignore is refused where the operator
    # is standing rather than on a tablet.
    #
    # ⚠️ Not every archive is a data package and not every data package is only
    # an archive, so this is its own column rather than a refinement of
    # `is_archive`.
    is_data_package: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, server_default=sa_text("false")
    )
    artifact_sha256: Mapped[str] = mapped_column(
        String(64), ForeignKey("artifact.sha256", ondelete="RESTRICT"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)

    # False for a file uploaded from inside a policy editor — a wallpaper, say.
    # It is an ordinary managed file in every way that matters to the device; it
    # simply is not part of the browsable Content library, because an operator who
    # picked an image for one policy did not mean to publish an asset to the fleet's
    # catalogue. Listings filter on this; nothing in the delivery path reads it.
    in_library: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default=sa_text("true")
    )

    # Suggested deployment, set on the Content page. These are *defaults* the
    # policy editor pre-fills — the authoritative destination/persist/extract for a
    # given placement still live on the FILES policy entry that places the file.
    default_dest_path: Mapped[str | None] = mapped_column(String(512), default=None)
    default_persist: Mapped[bool | None] = mapped_column(Boolean, default=None)
    default_extract: Mapped[bool | None] = mapped_column(Boolean, default=None)
    default_extract_to: Mapped[str | None] = mapped_column(String(512), default=None)
    default_overwrite: Mapped[str | None] = mapped_column(String(16), default=None)

    artifact: Mapped[Artifact] = relationship(lazy="selectin")


class DeviceFileSelection(Base):
    """An optional file a device's user chose to install (F4).

    The server offers; the device reports back what was taken. Recording it here is
    what lets an admin see which optional items are actually out in the fleet,
    rather than only what was made available.
    """

    __tablename__ = "device_file_selection"
    __table_args__ = (
        UniqueConstraint("device_id", "file_id", name="uq_device_file_selection"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("device.id", ondelete="CASCADE"), index=True
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("managed_file.id", ondelete="CASCADE"), index=True
    )
    applied_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)

    file: Mapped[ManagedFile] = relationship(lazy="selectin")


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


# --------------------------------------------------------------------------- #
# Admin: settings store and custom attributes
# --------------------------------------------------------------------------- #


class AppSetting(Base):
    """A key/value the operator edits through the Admin console — EULA text, SMTP,
    directory and SMS credentials, geofencing defaults. Environment-backed settings
    are not stored here; they are shown read-only with their variable name."""

    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow, onupdate=_utcnow)
    updated_by: Mapped[str | None] = mapped_column(String(128), default=None)


class CustomAttribute(Base):
    """An operator-defined field attached to devices — asset tag, owning unit,
    deployment date. Not interpreted by the MDM; it is for the operator's own
    inventory."""

    __tablename__ = "custom_attribute"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(64), unique=True)
    # string | number | boolean | date — validated in the schema, not a DB enum.
    attr_type: Mapped[str] = mapped_column(String(16), default="string")
    description: Mapped[str | None] = mapped_column(Text, default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)


class DeviceAttributeValue(Base):
    __tablename__ = "device_attribute_value"

    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("device.id", ondelete="CASCADE"), primary_key=True
    )
    attribute_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("custom_attribute.id", ondelete="CASCADE"), primary_key=True
    )
    value: Mapped[str] = mapped_column(Text, default="")

    attribute: Mapped[CustomAttribute] = relationship(lazy="selectin")


class GooglePlayLinkStatus(str, enum.Enum):
    UNLINKED = "unlinked"
    LINKED = "linked"
    #: The stored token stopped working. Google can revoke an AAS token, and an
    #: account can be locked — both need a human to mint a new one.
    BROKEN = "broken"


class GooglePlayLink(Base):
    """The single Google account this ATLAS instance downloads Play apps as (W99).

    One row, id 1, for the same reason `TakGovLink` is a singleton: ATLAS is one
    instance per operator.

    ⚠️ **The AAS token is a durable bearer credential to a real Google account.**
    Anyone holding it can act as that account against Play. It is sealed with the
    same `TokenVault` as every other stored secret, is never rendered back to the
    console once saved, and `unlink` destroys it.

    ⚠️ **`device_profile` is part of the credential's meaning, not decoration.**
    Play serves *device-matched* builds, so the profile decides which
    architecture arrives. It is stored rather than defaulted at call time, so what
    a device was handed can be explained afterwards — the lesson R19 cost a week
    to learn.

    ⚠️ **Using this violates Play's Terms of Service §3.3** and the account may be
    locked. That is the operator's decision, made knowingly; the console says so
    where the token is entered rather than burying it.
    """

    __tablename__ = "google_play_link"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    status: Mapped[GooglePlayLinkStatus] = mapped_column(
        Enum(GooglePlayLinkStatus, native_enum=False, length=16),
        default=GooglePlayLinkStatus.UNLINKED,
    )

    #: The account downloads are made as. Shown in the console; not a secret.
    email: Mapped[str | None] = mapped_column(String(256), default=None)
    #: Fernet-sealed AAS token. Never leaves the server unsealed.
    aas_token_sealed: Mapped[str | None] = mapped_column(Text, default=None)
    #: apkeep's device profile, e.g. "px_9a". See the class note.
    device_profile: Mapped[str] = mapped_column(String(64), default="px_9a")

    linked_at: Mapped[datetime | None] = mapped_column(UtcDateTime, default=None)
    linked_by: Mapped[str | None] = mapped_column(String(128), default=None)
    #: Why the last attempt failed, shown verbatim — these name the actual
    #: problem, and paraphrasing them into "link failed" throws that away.
    last_error: Mapped[str | None] = mapped_column(Text, default=None)


class TakGovLinkStatus(str, enum.Enum):
    UNLINKED = "unlinked"
    #: A device-authorization code has been issued and the operator has not yet
    #: entered it at tak.gov, or has and we have not yet noticed.
    PENDING = "pending"
    LINKED = "linked"
    #: The link was live and stopped working — most often a rotated refresh token
    #: that was lost, which needs a human to re-enter a code.
    BROKEN = "broken"


class TakGovLink(Base):
    """The single TAK.gov account this ATLAS instance pulls plugins as.

    One row, id 1. ATLAS is one instance per operator, so the per-tenant model in
    `tpc.md` collapses to a singleton — but it stays a table rather than settings
    because it carries a state machine, timestamps, and a credential that must not
    sit in `app_setting`, which is plaintext.

    ⚠️ The refresh token is a **durable bearer credential to a named person's
    TAK.gov account**, it inherits exactly that person's entitlements, and it does
    not idle out. It is sealed with the same `TokenVault` as enrollment tokens.

    ⚠️ Keycloak **rotates the refresh token on every refresh** and invalidates the
    old one. `previous_refresh_token` exists solely so that losing the race —
    crashing between "received" and "committed" — costs a retry rather than a trip
    to tak.gov for a human to type a code.
    """

    __tablename__ = "tak_gov_link"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    status: Mapped[TakGovLinkStatus] = mapped_column(
        Enum(TakGovLinkStatus, native_enum=False, length=16),
        default=TakGovLinkStatus.UNLINKED,
    )

    # --- device-authorization flow, only meaningful while PENDING ---
    device_code: Mapped[str | None] = mapped_column(Text, default=None)
    user_code: Mapped[str | None] = mapped_column(String(64), default=None)
    verification_uri: Mapped[str | None] = mapped_column(Text, default=None)
    verification_uri_complete: Mapped[str | None] = mapped_column(Text, default=None)
    #: Seconds between polls, raised when the server answers `slow_down`.
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=5)
    code_expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime, default=None)

    # --- credentials ---
    refresh_token_sealed: Mapped[str | None] = mapped_column(Text, default=None)
    previous_refresh_token_sealed: Mapped[str | None] = mapped_column(Text, default=None)
    access_token_sealed: Mapped[str | None] = mapped_column(Text, default=None)
    access_expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime, default=None)

    # --- who linked, for the console ---
    account_label: Mapped[str | None] = mapped_column(String(256), default=None)
    linked_at: Mapped[datetime | None] = mapped_column(UtcDateTime, default=None)
    linked_by: Mapped[str | None] = mapped_column(String(128), default=None)

    #: Why the last operation failed, shown verbatim. An undocumented API fails in
    #: undocumented ways, and paraphrasing them loses the only clue there is.
    last_error: Mapped[str | None] = mapped_column(Text, default=None)
    updated_at: Mapped[datetime] = mapped_column(
        UtcDateTime, default=_utcnow, onupdate=_utcnow
    )


# --------------------------------------------------------------------------- #
# Where devices have been (W106)
# --------------------------------------------------------------------------- #


class LocationSource(str, enum.Enum):
    """Why this point exists. Kept because the three are not equally trustworthy
    and an operator reading a track deserves to know which is which."""

    #: The device reported it on its own schedule, per the tracking policy.
    PERIODIC = "periodic"
    #: An operator asked, via the `locate` command.
    COMMAND = "command"
    #: Recorded because a geofence condition changed (W106 C4).
    GEOFENCE = "geofence"


class DeviceLocation(Base):
    """One position report from one device.

    ⚠️ **This is the only table in the schema expected to reach millions of rows**,
    and the two decisions below follow from that rather than from house style.

    **A `bigint` identity key, not a `uuid4`.** Everything else here uses
    :func:`_uuid_pk`, and for tables of thousands of rows that is right. Random
    keys on an append-only table scatter every insert across the index instead of
    filling the rightmost page, which costs write throughput and bloats the index
    precisely as the table gets big. Nothing links to a point by id, so the key
    carries no meaning worth randomising.

    **Two timestamps, and they mean different things.**

    * ``recorded_at`` is the device's own fix time. It can be stale by hours —
      `LocateCommandHandler` returns *last known* position deliberately, since a
      live fix can take minutes indoors — and it can be wrong outright if the
      device's clock is.
    * ``received_at`` is when this server was told, which is the only timestamp we
      can vouch for.

    A track drawn on ``recorded_at`` is the honest one; ``received_at`` is what
    explains a device that went quiet and then delivered six hours at once.
    Recording only one of them would make those two situations indistinguishable.
    """

    __tablename__ = "device_location"

    #: ⚠️ `bigint` on Postgres, `INTEGER` on SQLite — and the variant is load-bearing,
    #: not tidiness. SQLite auto-assigns a rowid only for a column declared exactly
    #: `INTEGER PRIMARY KEY`; a `BIGINT` one is an ordinary column that stays NULL,
    #: so every insert fails a NOT NULL check under the test suite while working
    #: perfectly in production.
    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("device.id", ondelete="CASCADE"), index=True
    )

    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)

    #: Reported accuracy radius in metres. NULL means the device did not say —
    #: never "perfectly accurate". The console shows those two differently.
    accuracy_m: Mapped[float | None] = mapped_column(Float, default=None)
    #: `gps`, `network`, or whatever the platform called it. Free text on purpose:
    #: it is the device's word, and an OEM may use one we have never seen.
    provider: Mapped[str | None] = mapped_column(String(32), default=None)

    recorded_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
    received_at: Mapped[datetime] = mapped_column(UtcDateTime, default=_utcnow)

    source: Mapped[LocationSource] = mapped_column(
        Enum(LocationSource, native_enum=False, length=16),
        default=LocationSource.PERIODIC,
    )

    device: Mapped[Device] = relationship(lazy="selectin")

    __table_args__ = (
        # Every read is "this device, newest first" — the detail page's latest
        # point, the history range, and the retention purge alike.
        Index("ix_device_location_device_recorded", "device_id", "recorded_at"),
        # ⚠️ Refused at the database, not only in the schema. A latitude of 91 is
        # not a coordinate, and a NaN silently poisons every bounding box drawn
        # from the table thereafter.
        CheckConstraint(
            "latitude >= -90 AND latitude <= 90", name="ck_device_location_latitude"
        ),
        CheckConstraint(
            "longitude >= -180 AND longitude <= 180",
            name="ck_device_location_longitude",
        ),
        CheckConstraint(
            "accuracy_m IS NULL OR accuracy_m >= 0", name="ck_device_location_accuracy"
        ),
    )
