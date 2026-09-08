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

"""Recognise an ATAK DTED archive (W93).

Terrain elevation ships as a zip of **longitude cells**, which must land
directly in `atak/DTED/`::

    w115/n32.dt2
    w115/n33.dt2
    w116/n33.dt2

⚠️ **The cells sit at the root of the archive, and that is load-bearing.** ATAK
unzips a DTED archive **flat** into its `DTED` directory —
`FileSystemUtils.unzip(zip, dtedDir, true)` in `ElevationDownloader` — so a zip
that wraps its cells in a folder produces `atak/DTED/DTED/w115/…`, where ATAK
looks for nothing and finds it. That is refused here with the reason, because it
is invisible on the device: the extraction succeeds, the files are present, and
no terrain appears.

⚠️ **Weaker provenance than the data-package reader, stated plainly.** ATAK has
no single "is this a DTED archive" function to mirror, the way
`MissionPackageExtractorFactory.HasManifest` exists for packages. What is
encoded here is the layout ATAK's own hemisphere archives use
(`dted_ne_hemi.zip` and friends), its extension list from `Dt2ElevationData`, and
the operator's sample. If a real archive is ever refused wrongly, that is where
to look first.

⚠️ **macOS pollution is everywhere in these files.** The operator's sample
carries `__MACOSX/` and an AppleDouble `._n33.dt2` beside *every* real file.
`FileDeployer.isArchiverJunk` already drops those on the device; detection has to
ignore them too, or a cell holding nothing but AppleDouble stubs reads as real.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass

#: Extensions ATAK recognises, from `Dt2ElevationData`: DTED level 0 through 3,
#: at 1000 m, 100 m, 30 m and 10 m post spacing.
LEVELS = {".dt0": 0, ".dt1": 1, ".dt2": 2, ".dt3": 3}

#: Where the cells must end up. `ElevationDownloader` builds exactly this.
DTED_DEST = "/sdcard/atak/DTED"

#: A longitude cell: hemisphere letter plus three degrees, e.g. `w115`, `e007`.
_CELL = re.compile(r"^[we]\d{3}$", re.IGNORECASE)

#: A latitude file within a cell, e.g. `n33.dt2`, `s07.dt1`.
_CELL_FILE = re.compile(r"^[ns]\d{2}(?:\(\d+\))?\.(dt[0-3])$", re.IGNORECASE)

MAX_ENTRIES = 200_000


class DtedError(ValueError):
    """An archive that is not usable DTED, in words an operator can act on."""


@dataclass(frozen=True)
class DtedArchive:
    """What a DTED archive holds."""

    cells: tuple[str, ...]
    file_count: int
    #: DTED levels present, e.g. {2} for a .dt2-only set.
    levels: frozenset[int]

    @property
    def cell_count(self) -> int:
        return len(self.cells)

    @property
    def summary(self) -> str:
        levels = ", ".join(f"DTED{level}" for level in sorted(self.levels)) or "no levels"
        return (
            f"{self.cell_count} cell{'' if self.cell_count == 1 else 's'}, "
            f"{self.file_count} file{'' if self.file_count == 1 else 's'} ({levels})"
        )


def is_archiver_junk(name: str) -> bool:
    """Metadata an archiver added, not content.

    Mirrors `FileDeployer.isArchiverJunk` on the agent — the same rule on both
    sides, so what detection counts is what the device will actually write.
    """
    normalised = name.replace("\\", "/")
    leaf = normalised.rsplit("/", 1)[-1]
    return (
        normalised.startswith("__MACOSX/")
        or "/__MACOSX/" in normalised
        or leaf == ".DS_Store"
        or leaf.startswith("._")
    )


def _real_entries(archive: zipfile.ZipFile) -> list[str]:
    return [
        name.replace("\\", "/")
        for name in archive.namelist()
        if not is_archiver_junk(name) and not name.endswith("/")
    ]


def inspect(data: bytes) -> DtedArchive:
    """Read a zip as DTED, refusing anything that would not work on the device."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise DtedError(f"this file is not a readable zip archive ({exc})") from exc

    with archive:
        if len(archive.namelist()) > MAX_ENTRIES:
            raise DtedError(f"the archive holds more than {MAX_ENTRIES:,} entries")
        entries = _real_entries(archive)

    if not entries:
        raise DtedError("this zip is empty, or holds nothing but archiver metadata")

    cells: dict[str, int] = {}
    levels: set[int] = set()
    stray: list[str] = []
    wrapped: set[str] = set()

    for name in entries:
        parts = name.split("/")
        if len(parts) == 2 and _CELL.match(parts[0]):
            match = _CELL_FILE.match(parts[1])
            if match:
                cells[parts[0].lower()] = cells.get(parts[0].lower(), 0) + 1
                levels.add(LEVELS[f".{match.group(1).lower()}"])
                continue
        # A cell one level deeper than it should be — the wrapped case.
        if len(parts) >= 3 and _CELL.match(parts[-2]) and _CELL_FILE.match(parts[-1]):
            wrapped.add(parts[0])
            continue
        stray.append(name)

    if not cells and wrapped:
        folders = ", ".join(sorted(wrapped)[:3])
        raise DtedError(
            f"the cell folders are inside {folders!r} rather than at the top of "
            f"the zip. ATAK unpacks a DTED archive flat into its DTED directory, "
            f"so these would land in DTED/{sorted(wrapped)[0]}/… where nothing "
            f"reads them — and it fails silently, with the files present and no "
            f"terrain shown. Re-zip the w### folders themselves, not the folder "
            f"holding them."
        )

    if not cells:
        example = ", ".join(stray[:3])
        raise DtedError(
            "this zip holds no DTED cells. A DTED archive contains folders like "
            "'w115' or 'e007', each holding files like 'n33.dt2'"
            + (f" — this one starts with {example}" if example else "")
            + "."
        )

    return DtedArchive(
        cells=tuple(sorted(cells)),
        file_count=sum(cells.values()),
        levels=frozenset(levels),
    )


def looks_like_dted(data: bytes) -> bool:
    """Is this a DTED archive, well-formed or not?

    The counterpart of `mission_package.has_manifest`: it answers *"was this meant
    to be DTED"*, so the General Files path can refuse it and name the sub-topic
    that handles it properly. A **wrapped** archive answers yes — it was plainly
    meant as DTED, and the DTED tool is where its real problem gets explained.
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        return False
    with archive:
        if len(archive.namelist()) > MAX_ENTRIES:
            return False
        for name in _real_entries(archive):
            parts = name.split("/")
            if len(parts) >= 2 and _CELL.match(parts[-2]) and _CELL_FILE.match(parts[-1]):
                return True
    return False
