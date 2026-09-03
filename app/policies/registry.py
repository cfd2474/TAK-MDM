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

"""Policy type registry.

Maps a policy type name to its spec schema and the per-field merge rules extracted
from that schema's annotations. The resolver consults only this registry, so a new
policy type is added by registering a module here and nothing else changes (OCP).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from app.policies.specs import (
    AppCatalogSpec,
    FilesSpec,
    NetworksSpec,
    PasswordSpec,
    PolicySpec,
    RestrictionsSpec,
)
from app.policies.strategies import Merge, MergeStrategy


class PolicyTypeError(ValueError):
    """Raised for an unknown policy type or an invalid spec."""


def _extract_merge_rules(spec_class: type[PolicySpec]) -> dict[str, Merge]:
    """Pull the ``Merge`` annotation off every field, refusing anything ambiguous.

    Failing here at import time is deliberate: adding a field and forgetting its
    merge rule would otherwise produce a field that silently never composes.
    """
    rules: dict[str, Merge] = {}
    for name, field_info in spec_class.model_fields.items():
        found = [m for m in field_info.metadata if isinstance(m, Merge)]
        if len(found) != 1:
            raise PolicyTypeError(
                f"{spec_class.__name__}.{name} must declare exactly one Merge "
                f"annotation, found {len(found)}"
            )
        rule = found[0]
        if rule.strategy is MergeStrategy.MERGE_BY_KEY and not rule.key:
            raise PolicyTypeError(
                f"{spec_class.__name__}.{name} uses MERGE_BY_KEY without a key"
            )
        rules[name] = rule
    return rules


@dataclass(frozen=True)
class PolicyTypeDefinition:
    name: str
    spec_class: type[PolicySpec]
    description: str
    merge_rules: Mapping[str, Merge]

    def describe(self) -> dict[str, Any]:
        """Machine-readable contract, for the admin UI's policy builder."""
        return {
            "name": self.name,
            "description": self.description,
            "schema": self.spec_class.model_json_schema(),
            "merge_rules": {
                field: {"strategy": rule.strategy.value, "key": rule.key, "note": rule.note}
                for field, rule in self.merge_rules.items()
            },
        }


class PolicyTypeRegistry:
    def __init__(self) -> None:
        self._types: dict[str, PolicyTypeDefinition] = {}

    def register(self, name: str, spec_class: type[PolicySpec], description: str) -> None:
        if name in self._types:
            raise PolicyTypeError(f"policy type {name!r} is already registered")
        self._types[name] = PolicyTypeDefinition(
            name=name,
            spec_class=spec_class,
            description=description,
            merge_rules=_extract_merge_rules(spec_class),
        )

    def get(self, name: str) -> PolicyTypeDefinition:
        try:
            return self._types[name]
        except KeyError:
            known = ", ".join(sorted(self._types)) or "none"
            raise PolicyTypeError(f"unknown policy type {name!r}; known types: {known}") from None

    def names(self) -> list[str]:
        return sorted(self._types)

    def validate_spec(self, policy_type: str, raw_spec: Mapping[str, Any]) -> dict[str, Any]:
        """Validate a raw spec and return its stored form (set fields only)."""
        definition = self.get(policy_type)
        try:
            model = definition.spec_class.model_validate(dict(raw_spec))
        except ValidationError as exc:
            raise PolicyTypeError(_readable(policy_type, exc)) from exc
        return model.to_stored()


def _readable(policy_type: str, exc: ValidationError) -> str:
    """A validation failure an operator can act on.

    `str(ValidationError)` carries the model name, a `[type=value_error, ...]`
    suffix and a repr of the whole input. That is useful in a stack trace and
    hostile in a console banner, where it is also the thing most likely to be
    truncated — losing the sentence that says what to do while keeping the noise.
    """
    parts = []
    for error in exc.errors():
        location = ".".join(str(piece) for piece in error.get("loc", ()) if piece != "__root__")
        message = error.get("msg", "").removeprefix("Value error, ")
        parts.append(f"{location}: {message}" if location else message)

    joined = "; ".join(dict.fromkeys(parts))  # de-duped, order kept
    return f"invalid {policy_type} spec — {joined}" if joined else f"invalid {policy_type} spec"


registry = PolicyTypeRegistry()
registry.register("PASSWORD", PasswordSpec, "Passcode strength, expiry, and lockout.")
registry.register(
    "RESTRICTIONS", RestrictionsSpec, "Device feature restrictions and screen timeout."
)
registry.register(
    "APP_CATALOG", AppCatalogSpec, "Required apps, blocklist, allowlist, and kiosk app."
)
registry.register(
    "FILES",
    FilesSpec,
    "Files placed on the device, required or offered in the marketplace.",
)
registry.register(
    "NETWORKS",
    NetworksSpec,
    "Wi-Fi networks and built-in VPN profiles.",
)
