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

"""Read and write ATAK data packages — "mission packages" in ATAK's own words (W91).

A data package is a zip carrying `MANIFEST/manifest.xml`::

    <?xml version="1.0" encoding="UTF-8"?>
    <MissionPackageManifest version="2">
      <Configuration>
        <Parameter name="uid" value="…"/>
        <Parameter name="name" value="…"/>
      </Configuration>
      <Contents>
        <Content ignore="false" zipEntry="path/inside/the/zip.kml"/>
      </Contents>
    </MissionPackageManifest>

Every rule below is read out of `atak-civ`, not remembered — see
`docs/ANDROID_PLATFORM_REFERENCE.md` §11 for the citations.

⚠️ **The manifest is found by suffix, at any depth.** ATAK's own lookup is
`entry.getName().endsWith("MANIFEST/manifest.xml")`, so
`mydata/MANIFEST/manifest.xml` is as valid as `MANIFEST/manifest.xml` — which is
what a Windows right-click "compress folder" produces, and therefore what half
the packages in the wild look like. **Everything the manifest names is relative
to the MANIFEST directory's parent**, not to the zip root. A validator that only
looks at the root rejects perfectly good packages.

⚠️ **ATAK accepts a zip with no manifest at all** — `GetExtractor` falls back to
`PlainZipExtractor`. Refusing those is an **MDM-side** rule the operator asked
for, not ATAK's: a plain zip is unpacked with none of the manifest's placement or
`onReceiveImport` semantics, so where its contents end up is far less
predictable. The rejection says so, rather than implying ATAK could not read it.
"""

from __future__ import annotations

import io
import uuid
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field

#: The manifest's path *within its base directory*, and the suffix ATAK matches on.
MANIFEST_DIR = "MANIFEST"
MANIFEST_NAME = f"{MANIFEST_DIR}/manifest.xml"

#: `MissionPackageManifest`'s own `@Attribute(name="version") private int VERSION = 2`.
MANIFEST_VERSION = 2

_ROOT = "MissionPackageManifest"

#: Required by `MissionPackageConfiguration.isValid()`, which also demands the
#: configuration hold **more than one** parameter — so these two are both the
#: required set and the minimum count.
PARAM_NAME = "name"
PARAM_UID = "uid"

#: Zip entries a package may carry that are not content: the manifest itself, and
#: the directory entries some tools write.
_METADATA_SUFFIX = MANIFEST_NAME

#: A hostile or broken archive must not be able to exhaust memory here. A data
#: package is curated content, not an app bundle; anything past this is either a
#: mistake or an attack, and both deserve the same refusal.
MAX_PACKAGE_BYTES = 2 * 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 4 * 1024 * 1024
MAX_ENTRIES = 10_000


class DataPackageError(ValueError):
    """A zip that is not a usable data package, in words an operator can act on."""


@dataclass(frozen=True)
class PackageContent:
    """One `<Content>` row: the entry it names, and whether ATAK should skip it."""

    zip_entry: str
    ignore: bool = False


@dataclass(frozen=True)
class DataPackage:
    """What a valid package declares about itself."""

    name: str
    uid: str
    #: Prefix the MANIFEST directory sits under — "" at the zip root, else e.g.
    #: "mydata/". Everything the manifest names hangs off this.
    base_directory: str
    #: Where the manifest was actually found, for diagnosis.
    manifest_path: str
    contents: tuple[PackageContent, ...] = ()
    #: Entries named by the manifest that are not in the zip. Not fatal — ATAK
    #: tolerates it — but an operator almost always wants to know.
    missing: tuple[str, ...] = ()
    parameters: dict[str, str] = field(default_factory=dict)

    @property
    def content_count(self) -> int:
        return len(self.contents)


def _find_manifest(archive: zipfile.ZipFile) -> tuple[str, str]:
    """(entry path, base directory) of the manifest, mirroring ATAK's own lookup.

    ATAK takes the **first** entry whose name ends with `MANIFEST/manifest.xml`
    and stops. Doing the same means a package with two manifests resolves here
    exactly as it will on the device, rather than to whichever this code
    happened to prefer.
    """
    for name in archive.namelist():
        normalised = name.replace("\\", "/")
        if normalised.endswith(MANIFEST_NAME):
            return name, normalised[: -len(MANIFEST_NAME)]
    raise DataPackageError(
        "this zip has no MANIFEST/manifest.xml, so it is not a data package. "
        "ATAK would still unpack it as a plain zip, but with none of the "
        "manifest's placement rules — which is why it is not accepted here. "
        "Use Create Data Package to build one from these files."
    )


def _text_attr(element: ET.Element, name: str) -> str:
    return (element.get(name) or "").strip()


def _parameters(configuration: ET.Element) -> dict[str, str]:
    """`<Parameter name= value=/>` rows, as a map."""
    found: dict[str, str] = {}
    for parameter in configuration.findall("Parameter"):
        key = _text_attr(parameter, "name")
        if key:
            found[key] = parameter.get("value") or ""
    return found


def inspect(data: bytes) -> DataPackage:
    """Read a zip as a data package, refusing anything ATAK would not accept.

    Raises `DataPackageError` with a reason worth showing an operator — the whole
    point of validating on upload rather than discovering it on a tablet.
    """
    if len(data) > MAX_PACKAGE_BYTES:
        raise DataPackageError(
            f"the package is larger than {MAX_PACKAGE_BYTES // (1024 * 1024)} MB"
        )
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise DataPackageError(f"this file is not a readable zip archive ({exc})") from exc

    with archive:
        if len(archive.namelist()) > MAX_ENTRIES:
            raise DataPackageError(f"the package holds more than {MAX_ENTRIES:,} entries")

        manifest_path, base = _find_manifest(archive)
        try:
            info = archive.getinfo(manifest_path)
            if info.file_size > MAX_MANIFEST_BYTES:
                raise DataPackageError("the manifest is implausibly large")
            raw = archive.read(manifest_path)
        except (KeyError, OSError, zipfile.BadZipFile) as exc:
            raise DataPackageError(f"the manifest could not be read ({exc})") from exc

        try:
            root = ET.fromstring(raw)
        except ET.ParseError as exc:
            raise DataPackageError(f"the manifest is not valid XML ({exc})") from exc

        if root.tag != _ROOT:
            raise DataPackageError(
                f"the manifest's root element is <{root.tag}>, but ATAK requires "
                f"<{_ROOT}>"
            )

        version = _text_attr(root, "version")
        if not version:
            raise DataPackageError(
                "the manifest has no version attribute, which ATAK requires"
            )
        if version != str(MANIFEST_VERSION):
            # Refused rather than warned about: ATAK deserialises this into an
            # int field that it then trusts, and a package written to an older
            # shape can parse yet behave differently once imported.
            raise DataPackageError(
                f"the manifest declares version {version}; ATAK's current format "
                f"is version {MANIFEST_VERSION}"
            )

        configuration = root.find("Configuration")
        if configuration is None:
            raise DataPackageError("the manifest has no <Configuration> element")
        contents_element = root.find("Contents")
        if contents_element is None:
            # Required by the schema even when it holds nothing.
            raise DataPackageError("the manifest has no <Contents> element")

        parameters = _parameters(configuration)
        missing_parameters = [p for p in (PARAM_NAME, PARAM_UID) if not parameters.get(p)]
        if missing_parameters:
            raise DataPackageError(
                "the manifest's <Configuration> is missing "
                + " and ".join(f"a {p!r} parameter" for p in missing_parameters)
                + ", both of which ATAK requires"
            )
        if len(parameters) < 2:
            raise DataPackageError(
                "ATAK requires more than one <Parameter> in the configuration"
            )

        contents: list[PackageContent] = []
        for content in contents_element.findall("Content"):
            entry = _text_attr(content, "zipEntry")
            if not entry:
                raise DataPackageError(
                    "a <Content> row has no zipEntry attribute, which ATAK requires"
                )
            contents.append(
                PackageContent(
                    zip_entry=entry,
                    ignore=(content.get("ignore") or "").strip().lower() == "true",
                )
            )

        present = {n.replace("\\", "/") for n in archive.namelist()}
        missing = tuple(
            c.zip_entry
            for c in contents
            if not c.ignore and f"{base}{c.zip_entry}".replace("\\", "/") not in present
        )

        return DataPackage(
            name=parameters[PARAM_NAME],
            uid=parameters[PARAM_UID],
            base_directory=base,
            manifest_path=manifest_path,
            contents=tuple(contents),
            missing=missing,
            parameters=parameters,
        )


def build(
    name: str,
    files: list[tuple[str, bytes]],
    *,
    uid: str | None = None,
    parameters: dict[str, str] | None = None,
) -> bytes:
    """Compile named files into a data package ATAK will import.

    `files` is `(entry name, bytes)`. Entry names are placed at the zip root
    beside the MANIFEST directory, which is the layout ATAK's own builder
    produces — the nested form is only tolerated, never generated.
    """
    label = (name or "").strip()
    if not label:
        raise DataPackageError("a data package needs a name")
    if not files:
        # ATAK would accept it — `Contents.isValid()` is unconditionally true —
        # but an empty package is never what an operator meant to build, and it
        # imports as a silent no-op on the device.
        raise DataPackageError("a data package needs at least one file")

    seen: set[str] = set()
    entries: list[tuple[str, bytes]] = []
    for entry_name, payload in files:
        safe = _safe_entry(entry_name)
        if safe in seen:
            raise DataPackageError(
                f"{safe!r} appears more than once; every file in a package needs "
                f"its own name"
            )
        seen.add(safe)
        entries.append((safe, payload))

    package_uid = uid or str(uuid.uuid4())
    manifest = _manifest_xml(label, package_uid, [e for e, _ in entries], parameters or {})

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        # Manifest first, as ATAK's builder writes it — its lookup scans entries
        # in order and stops at the first match, so leading with it is both
        # conventional and marginally cheaper on the device.
        archive.writestr(MANIFEST_NAME, manifest)
        for entry_name, payload in entries:
            archive.writestr(entry_name, payload)
    return buffer.getvalue()


def _safe_entry(entry_name: str) -> str:
    """A zip entry name that cannot escape the package or collide with MANIFEST."""
    cleaned = (entry_name or "").replace("\\", "/").strip().lstrip("/")
    parts = [p for p in cleaned.split("/") if p not in ("", ".", "..")]
    if not parts:
        raise DataPackageError(f"{entry_name!r} is not a usable file name")
    safe = "/".join(parts)
    if safe.upper().startswith(f"{MANIFEST_DIR}/"):
        raise DataPackageError(
            f"{safe!r} would sit inside the MANIFEST directory, which is reserved "
            f"for the manifest itself"
        )
    return safe


def _manifest_xml(
    name: str, uid: str, entries: list[str], extra: dict[str, str]
) -> str:
    """Serialise a manifest.

    Built by hand rather than with ElementTree so the output matches ATAK's own
    ordering and self-closing style, which is what every reference package in the
    wild looks like. The document is small and every value is escaped.
    """
    from xml.sax.saxutils import quoteattr

    parameters = {PARAM_UID: uid, PARAM_NAME: name, **extra}
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', f'<{_ROOT} version="{MANIFEST_VERSION}">']
    lines.append("  <Configuration>")
    for key, value in parameters.items():
        lines.append(f"    <Parameter name={quoteattr(key)} value={quoteattr(value)}/>")
    lines.append("  </Configuration>")
    lines.append("  <Contents>")
    for entry in entries:
        lines.append(f'    <Content ignore="false" zipEntry={quoteattr(entry)}/>')
    lines.append("  </Contents>")
    lines.append(f"</{_ROOT}>")
    return "\n".join(lines) + "\n"
