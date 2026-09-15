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

"""`SEC_AUDIT.md` M-4 — the takeover primitive is not in a release build.

`DebugConfigReceiver` accepts a broadcast setting `server_url`,
`enrollment_token` and `server_ca_pem`. It repoints an agent at an arbitrary
management server, and it was declared `exported="true" enabled="true"` in every
build type — so any app on the device could send it that broadcast, and the whole
defence was one runtime `if (!BuildConfig.DEBUG) return`.

⚠️ **What these tests can and cannot prove.** They read source, not artifacts.
The actual removal was verified against the built APKs with `aapt2 dump xmltree`
(zero occurrences in release, present and exported in debug) and that check needs
an Android SDK, so it cannot live here. What this file prevents is the overlay
being deleted, renamed past its target, or quietly reduced to a disabled flag —
each of which leaves a release APK carrying the receiver again with nothing in a
test run to say so.
"""

from __future__ import annotations

import io
import re
from pathlib import Path

MAIN_MANIFEST = Path("agent/app/src/main/AndroidManifest.xml")
RELEASE_MANIFEST = Path("agent/app/src/release/AndroidManifest.xml")
RECEIVER_KT = Path(
    "agent/app/src/main/java/com/taksolutions/atlasmdm/admin/DebugConfigReceiver.kt"
)

RECEIVER = ".admin.DebugConfigReceiver"


def _read(path: Path) -> str:
    return io.open(path, encoding="utf-8").read()


def test_the_release_overlay_exists():
    """Without this file the receiver is in every build, as it was."""
    assert RELEASE_MANIFEST.is_file(), (
        f"{RELEASE_MANIFEST} is gone — a release APK now declares "
        f"{RECEIVER}, exported to every app on the device."
    )


def test_the_release_overlay_removes_the_receiver():
    body = _read(RELEASE_MANIFEST)

    match = re.search(r"<receiver\b[^>]*>", body, re.S)
    assert match, "the release overlay declares no receiver at all"
    element = match.group(0)

    assert RECEIVER in element, element
    assert 'tools:node="remove"' in element, (
        "the overlay no longer removes the receiver. ⚠️ Disabling it is not the "
        "same thing: a component that exists can be enabled again, and a "
        "component that is not in the merged manifest cannot."
    )


def test_the_overlay_still_names_something_that_exists():
    """⚠️ `tools:node="remove"` for a component nothing declares is a no-op.

    The merger does not warn, the build succeeds, and the overlay reads exactly
    as it does today while removing nothing — so renaming or moving the receiver
    without touching this file would silently put it back into every release.
    """
    assert RECEIVER in _read(MAIN_MANIFEST), (
        f"the release overlay removes {RECEIVER}, but the main manifest no "
        f"longer declares it under that name, so the removal matches nothing."
    )
    assert RECEIVER_KT.is_file(), f"{RECEIVER_KT} moved; the overlay still names it"


def test_the_runtime_guard_is_still_the_first_thing_onreceive_does():
    """The second layer, and the one that was carrying it alone.

    Kept deliberately: a debug APK reaching a real device is an ordinary event,
    and the manifest removal does nothing for that case.
    """
    body = _read(RECEIVER_KT)

    match = re.search(r"override fun onReceive\([^)]*\)[^{]*\{(.*?)\n    \}", body, re.S)
    assert match, "onReceive is no longer shaped the way this guard reads it"

    first = [line.strip() for line in match.group(1).splitlines() if line.strip()][0]
    assert first == "if (!BuildConfig.DEBUG) {", first


def test_the_receiver_is_declared_exported_only_for_the_debug_variant():
    """It has to stay exported — `adb shell am broadcast` cannot reach an
    unexported component, and bench provisioning over ADB is the reason it
    exists. ⚠️ That is exactly why the removal, not the export flag, is the
    control: there is no setting here that makes it safe to ship."""
    main = _read(MAIN_MANIFEST)

    block = re.search(
        r"<receiver\b[^>]*" + re.escape(RECEIVER) + r"[^>]*>", main, re.S
    )
    assert block, "the main manifest no longer declares the receiver"
    assert 'android:exported="true"' in block.group(0)
