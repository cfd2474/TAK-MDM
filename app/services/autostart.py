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

"""Apps started after a restart, where they meet a kiosk (W506 D4).

The agent starts each app on App Management's "Apps to start after a restart"
list. In a kiosk, Android refuses to start an app that lock task does not
permit, so those apps join the kiosk's background apps: permitted, with no
tile. Done once here, on the resolved values, so the agent's kiosk code needs
no second list and the device page shows the list the device really applies.
"""

from __future__ import annotations


def permitted_in_kiosk(values: dict) -> dict:
    """Add the apps to start after a restart to a kiosk's background apps.

    Nothing changes without both a kiosk section and apps to start. The
    operator's own background apps keep their order; started apps follow, once
    each. Returns new values; the input is not changed.
    """
    started = (values.get("APP_CATALOG") or {}).get("autostart_apps") or []
    kiosk = values.get("KIOSK")
    if not started or not kiosk:
        return values
    background = list(kiosk.get("background_packages") or [])
    extra = [pkg for pkg in dict.fromkeys(started) if pkg not in background]
    if not extra:
        return values
    return {**values, "KIOSK": {**kiosk, "background_packages": background + extra}}
