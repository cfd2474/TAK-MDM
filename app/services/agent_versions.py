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

"""Whether a device's agent is new enough for a feature.

One comparison for every feature gate, so "0.82.5-knox" and "0.82.5+debug" read
the same everywhere and no gate grows its own idea of a version.
"""

from __future__ import annotations


def parse(agent_version: str | None) -> tuple[int, ...] | None:
    """`0.82.5-knox` → (0, 82, 5); None when the agent has not said."""
    head = (agent_version or "").split("-")[0].split("+")[0]
    try:
        parts = tuple(int(p) for p in head.split("."))
    except ValueError:
        return None
    return parts or None


def at_least(agent_version: str | None, minimum: tuple[int, ...]) -> bool | None:
    """True or False, or None when the agent hasn't said which version it is."""
    parts = parse(agent_version)
    return None if parts is None else parts >= minimum
