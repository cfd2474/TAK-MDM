"""Storage and retention for device-uploaded diagnostic logs.

Copyright 2026 TAK-Solutions LLC

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.models import Device, DeviceLogBundle

# The agent's own ring buffer is capped at 512 KB (two 256 KB generations), so
# anything materially larger is a bug or an abuse. Enforced here as well as there:
# the device half of a contract is the half an attacker controls.
MAX_BUNDLE_BYTES = 1024 * 1024

# Per-device history. Enough to compare "before the change" with "after it", and
# bounded so a device stuck in a collection loop cannot grow without limit.
MAX_BUNDLES_PER_DEVICE = 20


class LogBundleTooLarge(ValueError):
    """Raised when an upload exceeds :data:`MAX_BUNDLE_BYTES`."""


def store(
    session: Session,
    device: Device,
    *,
    content: str,
    command_id: uuid.UUID | None = None,
    agent_version: str | None = None,
    truncated: bool = False,
) -> DeviceLogBundle:
    """Record one uploaded bundle, then prune the device's history."""
    size = len(content.encode("utf-8"))
    if size > MAX_BUNDLE_BYTES:
        raise LogBundleTooLarge(
            f"log bundle is {size} bytes; the limit is {MAX_BUNDLE_BYTES}"
        )

    bundle = DeviceLogBundle(
        device_id=device.id,
        command_id=command_id,
        content=content,
        size_bytes=size,
        agent_version=agent_version or device.agent_version,
        truncated=truncated,
    )
    session.add(bundle)
    session.flush()

    _prune(session, device.id)
    return bundle


def _prune(session: Session, device_id: uuid.UUID) -> int:
    """Drop all but the newest :data:`MAX_BUNDLES_PER_DEVICE` for one device."""
    total = session.scalar(
        select(func.count())
        .select_from(DeviceLogBundle)
        .where(DeviceLogBundle.device_id == device_id)
    )
    if not total or total <= MAX_BUNDLES_PER_DEVICE:
        return 0

    # Select the survivors and delete the rest, rather than computing an offset
    # against a table another upload may be writing to concurrently.
    keep = session.scalars(
        select(DeviceLogBundle.id)
        .where(DeviceLogBundle.device_id == device_id)
        .order_by(DeviceLogBundle.collected_at.desc(), DeviceLogBundle.id.desc())
        .limit(MAX_BUNDLES_PER_DEVICE)
    ).all()

    removed = session.execute(
        delete(DeviceLogBundle).where(
            DeviceLogBundle.device_id == device_id,
            DeviceLogBundle.id.notin_(keep),
        )
    ).rowcount
    session.flush()
    return removed or 0


def list_for_device(
    session: Session, device_id: uuid.UUID, *, limit: int = MAX_BUNDLES_PER_DEVICE
) -> list[DeviceLogBundle]:
    """Newest first — an operator reads the most recent capture."""
    return list(
        session.scalars(
            select(DeviceLogBundle)
            .where(DeviceLogBundle.device_id == device_id)
            .order_by(DeviceLogBundle.collected_at.desc(), DeviceLogBundle.id.desc())
            .limit(limit)
        )
    )


def get(session: Session, bundle_id: uuid.UUID) -> DeviceLogBundle | None:
    return session.get(DeviceLogBundle, bundle_id)
