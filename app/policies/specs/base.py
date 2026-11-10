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
