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

"""Operator-defined device attributes (asset tag, owning unit, deployment date)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CustomAttribute, DeviceAttributeValue

ATTR_TYPES = ("string", "number", "boolean", "date")


class AttributeError_(Exception):
    """A custom-attribute operation cannot be completed."""


def list_attributes(session: Session) -> list[CustomAttribute]:
    return list(session.scalars(select(CustomAttribute).order_by(CustomAttribute.name)))


def create(
    session: Session, *, name: str, attr_type: str, description: str | None = None
) -> CustomAttribute:
    name = name.strip()
    if not name:
        raise AttributeError_("an attribute needs a name")
    if attr_type not in ATTR_TYPES:
        raise AttributeError_(f"type must be one of {', '.join(ATTR_TYPES)}")
    attribute = CustomAttribute(
        name=name, attr_type=attr_type, description=(description or None)
    )
    session.add(attribute)
    session.flush()
    return attribute


def delete(session: Session, attribute: CustomAttribute) -> None:
    session.delete(attribute)
    session.flush()


def values_for_device(
    session: Session, device_id: uuid.UUID
) -> list[tuple[CustomAttribute, str]]:
    """Every defined attribute paired with this device's value (blank if unset)."""
    stored = {
        v.attribute_id: v.value
        for v in session.scalars(
            select(DeviceAttributeValue).where(
                DeviceAttributeValue.device_id == device_id
            )
        )
    }
    return [(attr, stored.get(attr.id, "")) for attr in list_attributes(session)]


def set_value(
    session: Session, device_id: uuid.UUID, attribute_id: uuid.UUID, value: str
) -> None:
    row = session.get(DeviceAttributeValue, (device_id, attribute_id))
    value = (value or "").strip()
    if not value:
        if row is not None:
            session.delete(row)
        return
    if row is None:
        row = DeviceAttributeValue(device_id=device_id, attribute_id=attribute_id)
        session.add(row)
    row.value = value
    session.flush()
