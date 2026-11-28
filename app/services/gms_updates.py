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

"""ATLAS keeps Google Play services updated (W517, issue #16).

Operator: "automatically download and apply each specific device variant to the
appropriate device ... a theoretical 'easy button' that applies to all devices in
the policy."

**Why this is possible at all** (T516, SM-X520, One UI / Android 16): a Device
Owner's install of Google Play services goes through silently, although Samsung
names the Play Store as its update owner, and ATLAS's per-model Google Play
download (W312) gives the exact package Play itself installs. See
`docs/ANDROID_PLATFORM_REFERENCE.md`, "Google Play services as Play installed it".

**Which build a device gets.** The newest build in the library that:

- was **downloaded as the device's own model**. Play picks the build and its
  splits (screen density, device type) per model, so another model's download
  can install and still be the wrong variant;
- is signed by **Google's Play services certificate**. Anything else fails on the
  device as a signature mismatch, or worse, is not Google's;
- runs on the device (Android level, CPU type), by `newest_build.runs_on`;
- is **not older** than what the device has. Android refuses a downgrade and the
  agent would report it on every sync; a device the Play Store moved ahead is
  simply left alone.

Nothing fits → nothing is sent, with the reason, never another model's build.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppPackage, AppPackageVersion, Device
from app.services import model_builds, newest_build

GMS_PACKAGE = "com.google.android.gms"

#: SHA-256 of the certificate Google signs Play services with (v3), read on the
#: SM-X520 from both the installed build and Play's download (R516, ✅).
GMS_SIGNER = "5f2391277b1dbd489000467e4c2fa6af802430080457dce2f618992e9dfb5402"


@dataclass(frozen=True)
class Choice:
    version: AppPackageVersion | None
    reason: str | None = None

    @property
    def base_sha(self) -> str | None:
        if self.version is None:
            return None
        return next(
            (f.artifact_sha256 for f in self.version.files if f.role.value == "base"), None
        )


#: W519: the record moved to `model_builds`, shared by every app.
model_label = model_builds.model_label
downloaded_for = model_builds.downloaded_for


def builds_for_model(session: Session, model: str | None,
                     package: AppPackage | None = None) -> list[AppPackageVersion]:
    """The library's Play services builds Google Play served to `model`, newest first.

    A build counts when it was downloaded as the model, or when a later download
    as the model turned out to be the same build and was linked to it
    (`ModelBuild`, W517 C2: two models, one versionCode, different splits).
    """
    if package is None:
        package = session.scalar(select(AppPackage).where(AppPackage.package_name == GMS_PACKAGE))
    return model_builds.builds_for_model(session, model, package)


def link(session: Session, model: str, version: AppPackageVersion) -> None:
    """Record that Google Play served `version` to `model`."""
    model_builds.link(session, model, version)


def choose(session: Session, device: Device | None) -> Choice:
    """The Google Play services build this device should have, or why none."""
    if device is None or not device.model:
        return Choice(None, "the device has not reported its model yet")
    package = session.scalar(select(AppPackage).where(AppPackage.package_name == GMS_PACKAGE))
    if package is None:
        return Choice(None, f"no Google Play services build for {model_label(device.model)} yet")
    if (package.signature_sha256 or "").lower() != GMS_SIGNER:
        return Choice(None, "the library's Google Play services is not signed by Google; "
                            "nothing is sent")
    builds = [v for v in builds_for_model(session, device.model, package)
              if any(f.role.value == "base" for f in v.files)]
    if not builds:
        return Choice(None, f"no Google Play services build for {model_label(device.model)} yet")
    runnable = [v for v in builds if newest_build.runs_on(v, device)]
    if not runnable:
        return Choice(None, "no Google Play services build for this model runs on this "
                            "device's Android version or CPU type")
    best = runnable[0]
    installed = device.gms_version_code
    if installed is not None and best.version_code < installed:
        return Choice(None, f"the device already has a newer build ({installed}) than "
                            f"ATLAS holds ({best.version_code})")
    return Choice(best)


def record_installed(device: Device, properties: dict | None) -> bool:
    """Keep the Play services build a device reported in its Play profile.

    ⚠️ `GSF.version` is apkeep's name for it: the agent writes Play *services'*
    `longVersionCode` there (`DeviceProfilePlan`), not the services framework's.
    Returns True when the stored value changed.
    """
    raw = (properties or {}).get("GSF.version")
    try:
        code = int(str(raw).strip())
    except (TypeError, ValueError):
        return False
    if code <= 0 or code == device.gms_version_code:
        return False
    device.gms_version_code = code
    return True
