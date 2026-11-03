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

"""ATAK session logs, collected through ATLAS (W416).

"Enable automatic error logging" sits beside the ATAK build in a policy. When
it is on, two things follow, both decided here and nowhere else:

* ATAK writes a log file per session: `loggingfile` (Enable Logcat File) is
  pushed true, and `loggingfile_error_only` false. The whole session, not just
  errors, is what ATAK's developers need from a failed launch.
* The agent uploads those files to ATLAS. It is told through
  :data:`PAYLOAD_KEY` in its desired state.

⚠️ **Unset counts as on (operator, 2026-10-20: "Existing policies too").**
Every policy that installs ATAK Core logs unless someone unticks the box.

⚠️ **Off is pushed as `false`, never as an absent key.** ATAK only writes the
values it's sent, so a key that stops arriving leaves the last value in place
(platform reference §10b). A policy that unticks the box must say so.

⚠️ **Only where the policy installs ATAK Core.** With no ATAK in the policy
there is no ATAK to configure and no log to collect, so nothing is said.
"""

from __future__ import annotations

from typing import Any

#: The policy field, in APP_CATALOG beside `atak_core`.
FIELD = "atak_error_logging"

#: The agent's cue, a sibling key in its desired state. Additive: an older
#: agent ignores it, so no schema_version bump.
PAYLOAD_KEY = "atak_session_logs"

#: ATAK's own preference keys (read from the shipping build's screens).
LOG_FILE_KEY = "loggingfile"
ERRORS_ONLY_KEY = "loggingfile_error_only"

#: How old the live session must be before the agent sends an early copy.
#: The log of a launch that lost its certificate is usually the live one:
#: ATAK keeps running without it (W416 C1), so waiting for the session to
#: finish could mean waiting days. Ten minutes covers the launch.
LIVE_AFTER_SECONDS = 600


def enabled(policy: dict[str, Any]) -> bool | None:
    """Whether a resolved policy turns ATAK session logging on.

    None when the policy installs no ATAK Core, so it has nothing to say.
    """
    catalog = policy.get("APP_CATALOG") or {}
    if not catalog.get("atak_core"):
        return None
    return catalog.get(FIELD) is not False


def pref_values(state: bool | None) -> dict[str, str]:
    """ATAK settings for `state`, as `.pref` values. Empty when None."""
    if state is None:
        return {}
    if state:
        return {LOG_FILE_KEY: "true", ERRORS_ONLY_KEY: "false"}
    return {LOG_FILE_KEY: "false"}


def marker(policy: dict[str, Any]) -> dict[str, Any] | None:
    """The agent's instruction, or None when it should not collect."""
    if not enabled(policy):
        return None
    return {"live_after_seconds": LIVE_AFTER_SECONDS}
