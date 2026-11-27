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
