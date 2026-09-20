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

"""XAPK / APKS container handling.

An XAPK or APKS is a ZIP holding a base APK, its split APKs, and sometimes OBB
expansion files. These are **unpacked server-side** (D13) into separate
content-addressed parts rather than shipped whole.

Three reasons that is the right split of work. The server can validate the package
name, version, and signature at upload, where a mistake is legible. The device
opens one `PackageInstaller` session and writes parts whose hashes it already knows,
instead of unzipping a large archive with a copy of it on disk at the same time. And
a split that did not change between versions deduplicates for free.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass

# ⚠️ One enum, deliberately. This module used to define its own `PartRole` with
# the same three values as the ORM's, and because both are `str` enums the two
# compared equal with `==` while `is` silently returned False. Code holding a row
# from the database and the copy imported from here would disagree about a value
# that printed identically. Re-exported rather than redefined so there is exactly
# one object to be identical to.
#
# The dependency direction is safe: `app.db.models` imports nothing from
# `app.artifacts`.
from app.db.models import PartRole  # re-export

from app.artifacts.apk import ApkError, ApkInfo, inspect_apk
from app.artifacts.app_icon import AppIcon


@dataclass(frozen=True)
class BundlePart:
    role: PartRole
    file_name: str
    data: bytes
    # Populated for BASE and SPLIT; OBB files have no manifest.
    info: ApkInfo | None = None


@dataclass(frozen=True)
class InspectedBundle:
    package_name: str
    version_code: int
    version_name: str | None
    min_sdk: int | None
    target_sdk: int | None
    signature_sha256: str | None
    signature_scheme: str | None
    #: ATAK plugin compatibility key, from the base APK's manifest (D45).
    plugin_api: str | None
    parts: tuple[BundlePart, ...]
    #: The app's display name — what the launcher shows on the device (W51).
    #: An XAPK states it outright; a plain APK only when its manifest inlines
    #: the label rather than referencing a string resource. None when unknown,
    #: so the caller falls back to the package name rather than inventing one.
    label: str | None = None
    #: The launcher icon from the base APK, when extractable (W53). Splits never
    #: carry it — a `config.*` split holds density-specific resources but the
    #: manifest that names the icon is the base's.
    icon: AppIcon | None = None

    @property
    def base(self) -> BundlePart:
        return next(p for p in self.parts if p.role is PartRole.BASE)

    @property
    def abis(self) -> tuple[str, ...]:
        """Every architecture any part of this bundle carries code for (W96).

        ⚠️ **Across all parts, because that is where a bundle keeps it.** The base
        of a split app often holds no native code at all — the operator's Chrome
        XAPK is exactly that shape — so reading only `base.info` would report the
        whole app as running anywhere while the split that actually carries the
        code is `armeabi-v7a` only.
        """
        found: set[str] = set()
        for part in self.parts:
            if part.info is not None:
                found |= set(part.info.abis)
        return tuple(sorted(found))


def is_container(data: bytes) -> bool:
    """True for a ZIP that holds APKs rather than being one."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()
    except zipfile.BadZipFile:
        return False
    if "AndroidManifest.xml" in names:
        return False  # it is an APK itself
    return any(name.lower().endswith((".apk", ".obb")) for name in names)


def _container_label(archive: zipfile.ZipFile) -> str | None:
    """XAPK containers carry a manifest.json; APKS ones do not."""
    try:
        manifest = json.loads(archive.read("manifest.json"))
    except (KeyError, ValueError):
        return None
    return manifest.get("name") or manifest.get("package_name")


def inspect_bundle(data: bytes) -> InspectedBundle:
    """Unpack a container into its base APK, splits, and OBB files."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ApkError("not a valid ZIP archive") from exc

    parts: list[BundlePart] = []
    base_part: BundlePart | None = None
    container_label: str | None = None

    with archive:
        # Read inside the block: `with archive` closes the zip, and reading a
        # closed one raises ValueError — which `_container_label` catches and
        # turns into a silent None.
        container_label = _container_label(archive)

        for name in sorted(archive.namelist()):
            lowered = name.lower()

            if lowered.endswith(".obb"):
                parts.append(
                    BundlePart(role=PartRole.OBB, file_name=name, data=archive.read(name))
                )
                continue

            if not lowered.endswith(".apk"):
                continue

            member = archive.read(name)
            try:
                info = inspect_apk(member)
            except ApkError as exc:
                raise ApkError(f"{name}: {exc}") from exc

            # A split APK declares split="config.arm64_v8a" in its manifest; the base
            # does not. Trusting the file name instead would misclassify archives
            # whose parts were renamed.
            if info.split_name:
                parts.append(
                    BundlePart(role=PartRole.SPLIT, file_name=name, data=member, info=info)
                )
            elif base_part is None:
                base_part = BundlePart(
                    role=PartRole.BASE, file_name=name, data=member, info=info
                )
            else:
                raise ApkError(
                    f"container holds more than one base APK "
                    f"({base_part.file_name} and {name})"
                )

    if base_part is None:
        raise ApkError("container holds no base APK")

    parts.insert(0, base_part)
    base_info = base_part.info
    assert base_info is not None

    for part in parts:
        if part.info and part.info.package_name != base_info.package_name:
            raise ApkError(
                f"{part.file_name} belongs to {part.info.package_name}, "
                f"not {base_info.package_name}"
            )

    return InspectedBundle(
        package_name=base_info.package_name,
        version_code=base_info.version_code,
        version_name=base_info.version_name,
        min_sdk=base_info.min_sdk,
        target_sdk=base_info.target_sdk,
        signature_sha256=base_info.signature_sha256,
        signature_scheme=base_info.signature_scheme,
        plugin_api=base_info.plugin_api,
        # The container states the display name outright; the base APK's own
        # label is usually a resource reference (W51).
        label=container_label or base_info.label,
        icon=base_info.icon,
        parts=tuple(parts),
    )


def inspect_single_apk(data: bytes) -> InspectedBundle:
    """Wrap a bare APK in the same shape as a container, so callers stay uniform."""
    info = inspect_apk(data)
    if info.split_name:
        raise ApkError(
            f"this is a split APK ({info.split_name}); upload the full "
            "XAPK/APKS container instead"
        )
    return InspectedBundle(
        package_name=info.package_name,
        version_code=info.version_code,
        version_name=info.version_name,
        min_sdk=info.min_sdk,
        target_sdk=info.target_sdk,
        signature_sha256=info.signature_sha256,
        signature_scheme=info.signature_scheme,
        plugin_api=info.plugin_api,
        label=info.label,
        icon=info.icon,
        parts=(BundlePart(role=PartRole.BASE, file_name="base.apk", data=data, info=info),),
    )


def inspect(data: bytes) -> InspectedBundle:
    """Identify an upload, whether it is a bare APK or a container."""
    return inspect_bundle(data) if is_container(data) else inspect_single_apk(data)
