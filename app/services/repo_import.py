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

"""Pull a build from a third-party repository into the library (W97).

⚠️ **Deliberately thin, for the reason `tak_gov_link.import_plugin` states**: the
file is downloaded and then handed to the ordinary ingest path, so identity —
package name, versionCode, signing certificate — is read from the file rather than
believed from the catalogue. A listing that names the wrong package therefore
cannot smuggle anything in under it.

⚠️ **An import reaches no device.** It used to need saying, and to need a
`publish=False` to enforce it: `ingest` would otherwise have published anything
newer than what was deployed, so fetching a build to look at would have shipped
it. Since W139 nothing is chosen automatically at all — a policy names the build
it installs — so this is now true of every path into the library rather than a
rule this one has to keep.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts.storage import ArtifactStorage
from app.db.models import AppPackage, AppPackageVersion, Device
from app.services import packages as package_service
from app.services.app_sources.base import AppSource, SourceVersion


@dataclass
class Preflight:
    """What is known about a build before a byte is downloaded.

    Separated from the import so the console can show it beside the version list:
    the point is to answer "should I fetch this" while it is still free to say no.
    """

    #: Reasons the import would fail or cause harm. Shown as refusals.
    blocking: list[str] = field(default_factory=list)
    #: Things worth knowing that do not stop the import.
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.blocking


def preflight(session: Session, version: SourceVersion) -> Preflight:
    """Check a catalogue's claims against what this deployment already knows.

    ⚠️ **Everything here is the catalogue's word**, so this can only catch what a
    listing states plainly. It is a courtesy, not a guarantee — the real checks
    happen against the file itself in `packages.ingest`.
    """
    result = Preflight()

    package = session.scalar(
        select(AppPackage).where(AppPackage.package_name == version.package_name)
    )
    if package is not None:
        # ⚠️ A different signer is not a warning. Android refuses the update
        # outright (INSTALL_FAILED_UPDATE_INCOMPATIBLE, which W96 classes as never
        # worth retrying), and `packages.ingest` refuses the upload — so saying it
        # here saves a download and explains it while the operator can still act.
        #
        # Compared against the package, not a version: the certificate is pinned
        # once at first upload and is a property of the app's identity, not of any
        # particular build.
        known = package.signature_sha256
        if version.signer_sha256 and known and version.signer_sha256 != known:
            result.blocking.append(
                f"{version.package_name} is already in the library signed by a "
                f"different certificate. This build claims "
                f"{version.signer_sha256[:16]}…, the library holds {known[:16]}…. "
                f"Android would refuse it as an update, and a changed signer is "
                f"how a substituted binary looks. Import it only if you know why "
                f"the signer changed."
            )

        if any(v.version_code == version.version_code for v in package.versions):
            result.blocking.append(
                f"versionCode {version.version_code} of {version.package_name} is "
                f"already in the library."
            )

    if not version.verifiable:
        result.warnings.append(
            "This source publishes no checksum, so the download can only be "
            "checked by reading the file after it arrives."
        )

    result.warnings.extend(_fleet_warnings(session, version))
    return result


def _fleet_warnings(session: Session, version: SourceVersion) -> list[str]:
    """Would this build actually run on the devices we have? (W96)

    ⚠️ **Only answerable for devices that have reported themselves.** A fleet of
    silent, older agents produces no warning here, and that absence must not read
    as approval — so a count is always given.
    """
    out: list[str] = []
    devices = list(session.scalars(select(Device)).all())
    if not devices:
        return out

    if version.abis:
        offered = set(version.abis)
        known = [d for d in devices if d.supported_abis]
        unable = [
            d for d in known if not (set(d.supported_abis.split(",")) & offered)
        ]
        if known and unable:
            names = ", ".join(sorted(d.serial_number for d in unable)[:4])
            out.append(
                f"{len(unable)} of {len(known)} devices that have reported their "
                f"architecture cannot run this build ({', '.join(sorted(offered))}): "
                f"{names}. It would fail to install on them, permanently."
            )

    if version.min_sdk is not None:
        known = [d for d in devices if d.sdk_int]
        too_old = [d for d in known if d.sdk_int < version.min_sdk]
        if too_old:
            names = ", ".join(sorted(d.serial_number for d in too_old)[:4])
            out.append(
                f"{len(too_old)} device(s) run an Android older than this build "
                f"needs (API {version.min_sdk}): {names}."
            )

    unreported = [d for d in devices if not d.supported_abis]
    if unreported and (version.abis or version.min_sdk is not None):
        out.append(
            f"{len(unreported)} of {len(devices)} devices have not reported their "
            f"architecture yet, so they are not covered by the checks above."
        )
    return out


def import_version(
    session: Session,
    storage: ArtifactStorage,
    source: AppSource,
    version: SourceVersion,
    *,
    label: str | None = None,
    progress=None,
) -> AppPackageVersion:
    """Fetch one build and add it to the library."""
    downloaded = source.download(version, progress)

    result = package_service.ingest(
        session,
        storage,
        downloaded.data,
        label=label,
    )
    result.version.source = source.name
    result.version.source_url = downloaded.source_url
    session.flush()
    return result.version
