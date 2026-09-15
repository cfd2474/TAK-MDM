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

"""`SEC_AUDIT.md` L-4 — only the launcher may open the launcher's tiles.

`DeviceSettingsActivity` and `PowerTileActivity` are `exported="true"` because a
**separate application** opens them — the kiosk launcher has its own
`applicationId`, so `exported="false"` would lock it out along with everything
else. A `signature` permission admits exactly one caller: an app carrying the
same signing certificate.

⚠️ **The two halves live in different manifests and nothing but this file
connects them.** A permission the agent declares and the launcher does not
request is granted to nobody; a name that differs by a character between them is
the same thing, and neither fails the build. What it looks like in the field is a
kiosk tile that shows "cannot open" — on a device the user cannot escape to
investigate.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

import pytest

AGENT_MANIFEST = Path("agent/app/src/main/AndroidManifest.xml")
LAUNCHER_MANIFEST = Path("agent/launcher/src/main/AndroidManifest.xml")
HOME_ACTIVITY = Path(
    "agent/launcher/src/main/java/com/taksolutions/atlaslauncher/HomeActivity.kt"
)

PERMISSION = "com.taksolutions.atlasmdm.permission.LAUNCHER_TILE"

#: The activities the launcher puts tiles on, and the only ones this guards.
TILES = ("PowerTileActivity", "DeviceSettingsActivity")


def _read(path: Path) -> str:
    return io.open(path, encoding="utf-8").read()


def _element(body: str, tag: str, name_ends_with: str) -> str:
    for match in re.finditer(rf"<{tag}\b[^>]*/?>", body, re.S):
        if name_ends_with in match.group(0):
            return match.group(0)
    raise AssertionError(f"no <{tag}> whose name contains {name_ends_with}")


def test_the_agent_declares_it_at_signature_level():
    """`signature` is the whole control. `normal` would grant it to anything that
    asked, which is the finding rather than the fix."""
    element = _element(_read(AGENT_MANIFEST), "permission", PERMISSION)

    assert 'android:protectionLevel="signature"' in element, element


@pytest.mark.parametrize("activity", TILES)
def test_each_tile_activity_is_guarded_by_it(activity):
    element = _element(_read(AGENT_MANIFEST), "activity", activity)

    assert f'android:permission="{PERMISSION}"' in element, element
    # ⚠️ Still exported, deliberately. The launcher is a different application
    # and has to be able to start these; the permission is what makes that safe.
    # Flipping to exported="false" would "fix" the finding by breaking the kiosk.
    assert 'android:exported="true"' in element, element


def test_the_launcher_asks_for_it():
    body = _read(LAUNCHER_MANIFEST)

    assert f'<uses-permission android:name="{PERMISSION}" />' in body, (
        "the launcher does not request the permission, so the system grants it "
        "to nobody and both kiosk tiles stop opening"
    )


def test_the_name_is_identical_on_both_sides():
    """⚠️ The failure a typo produces is silent.

    A misspelled `uses-permission` is simply a permission that does not exist;
    Android does not complain, the build succeeds, and the tiles fail at the
    moment somebody taps them.
    """
    declared = re.findall(
        r'<permission\s+android:name="([^"]+)"', _read(AGENT_MANIFEST)
    )
    requested = re.findall(
        r'<uses-permission android:name="([^"]+)" />', _read(LAUNCHER_MANIFEST)
    )

    assert PERMISSION in declared, declared
    assert PERMISSION in requested, requested


def test_the_launcher_survives_being_refused():
    """The property that made a permission the safe choice here.

    ⚠️ Checked before the permission was added, not after. If the grant ever does
    not happen — an install order nobody planned, an OEM quirk — `startActivity`
    throws `SecurityException`, and a kiosk home screen that crashed on that
    would be a brick. It is caught, logged and surfaced as a toast instead.
    """
    body = _read(HOME_ACTIVITY)

    assert "runCatching { startActivity(intent) }" in body
    assert ".onFailure {" in body
