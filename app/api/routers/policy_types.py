"""Exposes the policy type registry so the admin UI can render a policy builder
and show operators what each field's stacking behaviour will be."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.policies.registry import PolicyTypeError, registry

router = APIRouter(prefix="/api/v1/policy-types", tags=["policy-types"])


@router.get("")
def list_policy_types() -> list[dict[str, Any]]:
    return [registry.get(name).describe() for name in registry.names()]


@router.get("/{name}")
def get_policy_type(name: str) -> dict[str, Any]:
    try:
        return registry.get(name).describe()
    except PolicyTypeError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
