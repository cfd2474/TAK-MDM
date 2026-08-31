"""Base class for all policy spec schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class PolicySpec(BaseModel):
    """A typed policy body.

    Every field must be optional and carry a :class:`~app.policies.strategies.Merge`
    annotation. Optionality is load-bearing: an unset field contributes nothing to a
    merge, which is what lets a narrow policy stack on a broad one without clobbering
    it. Specs are therefore persisted with ``exclude_unset=True``.
    """

    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    def to_stored(self) -> dict[str, Any]:
        """Serialize for persistence: JSON-safe, and only what was explicitly set."""
        return self.model_dump(mode="json", exclude_unset=True)
