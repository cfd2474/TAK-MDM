"""Shared FastAPI dependencies."""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.base import get_session
from app.db.models import Device


def get_db(session: Session = Depends(get_session)) -> Session:
    return session


def require_device(device_id: uuid.UUID, session: Session = Depends(get_db)) -> Device:
    device = session.get(Device, device_id)
    if device is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"device {device_id} not found")
    return device


def fetch_or_404(session: Session, model: type, entity_id: uuid.UUID, label: str):
    entity = session.get(model, entity_id)
    if entity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} {entity_id} not found")
    return entity
