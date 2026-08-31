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

from app.policies.specs import AppCatalogSpec, PasswordSpec, PolicySpec, RestrictionsSpec
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
            raise PolicyTypeError(f"invalid {policy_type} spec: {exc}") from exc
        return model.to_stored()


registry = PolicyTypeRegistry()
registry.register("PASSWORD", PasswordSpec, "Passcode strength, expiry, and lockout.")
registry.register(
    "RESTRICTIONS", RestrictionsSpec, "Device feature restrictions and screen timeout."
)
registry.register(
    "APP_CATALOG", AppCatalogSpec, "Required apps, blocklist, allowlist, and kiosk app."
)
