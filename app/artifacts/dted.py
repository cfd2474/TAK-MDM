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

⚠️ **The cells must sit at the root, and that is load-bearing.** ATAK unzips a
DTED archive **flat** into its `DTED` directory —
`FileSystemUtils.unzip(zip, dtedDir, true)` in `ElevationDownloader` — so a zip
that wraps its cells in a folder produces `atak/DTED/DTED/w115/…`, where ATAK
looks for nothing and finds it. The extraction succeeds, every file is present,
and no terrain appears; nothing is logged.

**W94: a nested archive is repacked rather than refused.** Right-clicking a DTED
folder in Windows produces exactly the nested form, so refusing it turned the
common case into homework. `plan_layout` finds cells at any depth and moves them
to the top; `repack` writes that out. It happens here, at upload, rather than on
the device, so the invariant holds: **what ATLAS stores is what lands on disk**,
and every already-fielded agent is correct without an update.

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
import shutil
import zipfile
from collections.abc import Iterable
from dataclasses import dataclass
from typing import BinaryIO

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

_COPY_CHUNK = 1024 * 1024


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


@dataclass(frozen=True)
class DtedLayout:
    """Where every entry of an archive has to land.

    Kept apart from the repack so the decision is testable without a zip at all:
    the input is a list of names and nothing else.
    """

    archive: DtedArchive
    #: ``(name in the source, path it must occupy)``, for everything kept.
    moves: tuple[tuple[str, str], ...]
    #: Folders the cells were buried under, so the operator can be told what moved.
    wrappers: tuple[str, ...]
    #: Entries kept at their original path because they are not terrain.
    carried: int

    @property
    def needs_repack(self) -> bool:
        """Would rewriting this archive change anything?

        False for an already-flat archive, which is then stored byte-for-byte as
        uploaded — no recompression, and no quiet edit of the operator's file.
        """
        return any(source != destination for source, destination in self.moves)


def plan_layout(names: Iterable[str]) -> DtedLayout:
    """Decide where each entry goes, flattening cells found at any depth."""
    moves: list[tuple[str, str]] = []
    cells: dict[str, int] = {}
    levels: set[int] = set()
    wrappers: set[str] = set()
    claimed: dict[str, str] = {}
    carried: list[str] = []

    for name in names:
        normalised = name.replace("\\", "/")
        if normalised.endswith("/") or is_archiver_junk(normalised):
            continue

        parts = normalised.split("/")
        match = _CELL_FILE.match(parts[-1]) if len(parts) >= 2 else None
        if match and _CELL.match(parts[-2]):
            destination = f"{parts[-2]}/{parts[-1]}"
            previous = claimed.get(destination.lower())
            if previous is not None:
                raise DtedError(
                    f"two entries would both become {destination!r}: {previous!r} "
                    f"and {normalised!r}. Flattening cannot keep both, and picking "
                    f"one would silently discard terrain. Split them into separate "
                    f"uploads, or remove the duplicate."
                )
            claimed[destination.lower()] = normalised
            if len(parts) > 2:
                wrappers.add(parts[0])
            cells[parts[-2].lower()] = cells.get(parts[-2].lower(), 0) + 1
            levels.add(LEVELS[f".{match.group(1).lower()}"])
            moves.append((name, destination))
            continue

        carried.append(normalised)
        moves.append((name, normalised))

    if not moves:
        raise DtedError("this zip is empty, or holds nothing but archiver metadata")

    if not cells:
        example = ", ".join(carried[:3])
        raise DtedError(
            "this zip holds no DTED cells. A DTED archive contains folders like "
            "'w115' or 'e007', each holding files like 'n33.dt2'"
            + (f" — this one starts with {example}" if example else "")
            + "."
        )

    return DtedLayout(
        archive=DtedArchive(
            cells=tuple(sorted(cells)),
            file_count=sum(cells.values()),
            levels=frozenset(levels),
        ),
        moves=tuple(moves),
        wrappers=tuple(sorted(wrappers)),
        carried=len(carried),
    )


def _open(data: bytes) -> zipfile.ZipFile:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise DtedError(f"this file is not a readable zip archive ({exc})") from exc
    if len(archive.namelist()) > MAX_ENTRIES:
        archive.close()
        raise DtedError(f"the archive holds more than {MAX_ENTRIES:,} entries")
    return archive


def plan(data: bytes) -> DtedLayout:
    """Read a zip as DTED and say where everything in it has to go."""
    with _open(data) as archive:
        return plan_layout(archive.namelist())


def inspect(data: bytes) -> DtedArchive:
    """What terrain a zip holds, once flattened."""
    return plan(data).archive


def repack(source: BinaryIO, destination: BinaryIO, layout: DtedLayout) -> None:
    """Write `source` out again with every cell at the top level.

    ⚠️ **Streams entry by entry on purpose.** The operator's sample is 726 MB
    compressed and 1.75 GB inflated; reading it whole to rewrite a few path
    strings would cost more memory than the rest of the server uses. Recompression
    is the expensive half either way (~34 MB/s measured, against 423 MB/s to
    inflate), which is why `needs_repack` exists to skip all of it.

    Archiver junk is dropped rather than copied — the agent's `isArchiverJunk`
    refuses to write it anyway, so carrying it would only add bytes to every
    download.
    """
    with zipfile.ZipFile(source) as reader:
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as writer:
            for name, target in layout.moves:
                original = reader.getinfo(name)
                rewritten = zipfile.ZipInfo(target, date_time=original.date_time)
                rewritten.compress_type = zipfile.ZIP_DEFLATED
                with reader.open(original) as inbound:
                    with writer.open(rewritten, "w") as outbound:
                        shutil.copyfileobj(inbound, outbound, _COPY_CHUNK)


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
