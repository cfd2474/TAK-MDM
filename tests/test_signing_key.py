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

"""ATLAS signs with its own key, and never with the Play Store one.

`SEC_AUDIT.md` **H-2**. The agent is the Device Owner on every device of every
customer, and the key that signs it is what those devices pin for ever. That key
must belong to ATLAS alone.

⚠️ **It did not.** Until v1.34.0 the build used
`D:/Code/ANDROID/APK Keys/AppSign.jks` — a general-purpose workstation keystore
that also signs an app distributed through Google Play. One key therefore stood
behind two unrelated trust domains: a Play listing and every managed fleet. A
compromise of either was a compromise of both.

⚠️ **Play App Signing does not help here, and it is easy to assume it does.** The
agent is sideloaded by a Device Owner during provisioning and never installed
from Play, so whatever key signs the file in `dist/` is what devices pin. Google
holding an app signing key protects the Play listing and nothing about the fleet.

These guards exist because the failure is silent: signing with the wrong key
produces a perfectly working APK, and the damage only becomes visible years
later when the two domains have to be separated and cannot be.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.apk_signing import NotSigned, signer_sha256

AGENT = Path("dist/atlas-agent.apk")
LAUNCHER = Path("dist/atlas-launcher.apk")

#: The Google Play key. ⚠️ **Never sign an ATLAS artifact with this.**
#:
#: Recorded by fingerprint rather than by path so the rule survives the keystore
#: moving, being renamed, or being copied to another machine. Confirmed by the
#: operator against the Play Console, 2026-09-15.
PLAY_KEY_SHA256 = "2094bccc054c681f46d8c812378c07657cf339dd7d4e80b546026b77aff2c644"


@pytest.mark.parametrize("apk", [AGENT, LAUNCHER], ids=lambda p: p.name)
def test_the_artifact_is_signed_and_readable(apk):
    """If this breaks, every assertion below is vacuously true.

    A parser that returned nothing useful would make "is not the Play key" pass
    for an APK signed with anything at all.
    """
    digest = signer_sha256(apk)

    assert len(digest) == 64 and int(digest, 16) >= 0, digest


@pytest.mark.parametrize("apk", [AGENT, LAUNCHER], ids=lambda p: p.name)
def test_no_shipped_artifact_is_signed_with_the_play_key(apk):
    """⚠️ The guard this file exists for.

    Signing with the Play key works perfectly and looks completely normal. The
    cost only arrives later: a Play incident becomes a fleet incident, a fleet
    incident becomes a Play incident, and separating them afterwards needs a
    signing lineage and every device to have already accepted it.
    """
    assert signer_sha256(apk) != PLAY_KEY_SHA256, (
        f"{apk} is signed with the Google Play key. ATLAS must use its own "
        f"keystore — see docs/AGENT-SIGNING-KEY.md. Signing with the Play key "
        f"puts a Play listing and every customer's fleet behind one secret."
    )


def test_the_agent_and_launcher_share_one_key():
    """⚠️ L-4 depends on this and fails silently without it.

    The launcher opens the agent's kiosk tiles through a `signature` permission,
    which is granted only when both APKs carry the same certificate. Two
    different keys means the tiles stop opening — on a locked kiosk, with
    "cannot open" as the only symptom.
    """
    assert signer_sha256(AGENT) == signer_sha256(LAUNCHER), (
        "the agent and launcher are signed by different keys; the kiosk tiles "
        "will not open (SEC_AUDIT L-4)"
    )


def test_an_unsigned_file_is_reported_rather_than_passing(tmp_path):
    """The parser must refuse what it cannot read.

    ⚠️ Returning a placeholder for an unreadable APK would turn both guards
    above into decoration — "not the Play key" is trivially true of a value that
    is not a key at all.
    """
    import zipfile

    plain = tmp_path / "unsigned.apk"
    with zipfile.ZipFile(plain, "w") as archive:
        archive.writestr("AndroidManifest.xml", "not really")

    with pytest.raises(NotSigned):
        signer_sha256(plain)
