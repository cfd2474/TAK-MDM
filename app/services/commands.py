"""Transient command queue.

Delivery is at-least-once, so every command type must be idempotent: a device that
receives `REBOOT`, reboots, and dies before acknowledging will get it again. That is
the right trade for an intermittent fleet — the alternative, at-most-once, silently
drops actions whenever a device drops off mid-execution.

Staleness is enforced on read, not by a background sweeper. A command that outlived
its TTL is expired the moment anyone looks at it, so there is no window where a
device could collect a command the console already considers dead.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CommandStatus, CommandType, Device, DeviceCommand

# Per-type defaults. A LOCATE answers a question that goes stale in hours; a WIPE
# on a lost device stays worth executing for as long as the device might reappear.
DEFAULT_TTL_HOURS: dict[CommandType, int] = {
    CommandType.LOCATE: 6,
    CommandType.SCREENSHOT: 6,
    CommandType.LOCK: 72,
    CommandType.REBOOT: 24,
    CommandType.CLEAR_APP_DATA: 168,
    CommandType.WIPE: 720,
}
_FALLBACK_TTL_HOURS = 24


class CommandError(ValueError):
    """Raised for an unusable command request."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enqueue(
    session: Session,
    device: Device,
    *,
    command_type: CommandType,
    params: dict[str, Any] | None = None,
    ttl_hours: int | None = None,
    max_attempts: int = 5,
) -> DeviceCommand:
    params = params or {}

    if command_type is CommandType.CLEAR_APP_DATA and not params.get("package_name"):
        raise CommandError("clear_app_data requires a package_name parameter")

    ttl = ttl_hours or DEFAULT_TTL_HOURS.get(command_type, _FALLBACK_TTL_HOURS)
    command = DeviceCommand(
        device_id=device.id,
        command_type=command_type,
        params=params,
        expires_at=_utcnow() + timedelta(hours=ttl),
        max_attempts=max_attempts,
    )
    session.add(command)
    session.flush()
    return command


def expire_stale(session: Session, device: Device) -> int:
    """Mark timed-out or exhausted commands expired. Returns how many."""
    now = _utcnow()
    open_commands = session.scalars(
        select(DeviceCommand).where(
            DeviceCommand.device_id == device.id,
            DeviceCommand.status.in_([CommandStatus.PENDING, CommandStatus.DISPATCHED]),
        )
    ).all()

    expired = 0
    for command in open_commands:
        if not command.is_live(now=now):
            command.status = CommandStatus.EXPIRED
            command.completed_at = now
            command.error = (
                "exceeded max attempts"
                if command.attempts >= command.max_attempts
                else "expired before delivery"
            )
            expired += 1

    if expired:
        session.flush()
    return expired


def claim_for_delivery(session: Session, device: Device) -> list[DeviceCommand]:
    """Commands to hand this device now, counting an attempt against each."""
    expire_stale(session, device)
    now = _utcnow()

    pending = session.scalars(
        select(DeviceCommand)
        .where(
            DeviceCommand.device_id == device.id,
            DeviceCommand.status.in_([CommandStatus.PENDING, CommandStatus.DISPATCHED]),
        )
        .order_by(DeviceCommand.created_at)
    ).all()

    claimed = [c for c in pending if c.is_live(now=now)]
    for command in claimed:
        command.status = CommandStatus.DISPATCHED
        command.dispatched_at = now
        command.attempts += 1

    if claimed:
        session.flush()
    return claimed


def record_results(
    session: Session, device: Device, results: Sequence[Any]
) -> tuple[int, list[str]]:
    """Apply device-reported command outcomes.

    Acknowledging an already-finished command is a no-op rather than an error: a
    device that retries a check-in whose response was lost must not be punished for
    reporting the same result twice.

    Returns the number applied and any ids that were not recognised.
    """
    if not results:
        return 0, []

    by_id = {
        command.id: command
        for command in session.scalars(
            select(DeviceCommand).where(
                DeviceCommand.device_id == device.id,
                DeviceCommand.id.in_([r.command_id for r in results]),
            )
        )
    }

    applied = 0
    unknown: list[str] = []
    now = _utcnow()

    for report in results:
        command = by_id.get(report.command_id)
        if command is None:
            # Belongs to another device, or was purged. Never trust the id to
            # select the row on its own.
            unknown.append(str(report.command_id))
            continue
        if command.status in (
            CommandStatus.SUCCEEDED,
            CommandStatus.FAILED,
            CommandStatus.EXPIRED,
        ):
            continue

        command.status = (
            CommandStatus.SUCCEEDED if report.succeeded else CommandStatus.FAILED
        )
        command.completed_at = now
        command.result = report.result
        command.error = report.error
        applied += 1

    session.flush()
    return applied, unknown


def list_for_device(
    session: Session, device_id: uuid.UUID, *, include_finished: bool = True
) -> list[DeviceCommand]:
    stmt = select(DeviceCommand).where(DeviceCommand.device_id == device_id)
    if not include_finished:
        stmt = stmt.where(
            DeviceCommand.status.in_([CommandStatus.PENDING, CommandStatus.DISPATCHED])
        )
    return list(session.scalars(stmt.order_by(DeviceCommand.created_at.desc())))


def cancel(session: Session, command: DeviceCommand) -> None:
    if command.status in (CommandStatus.PENDING, CommandStatus.DISPATCHED):
        command.status = CommandStatus.EXPIRED
        command.completed_at = _utcnow()
        command.error = "cancelled by operator"
        session.flush()
