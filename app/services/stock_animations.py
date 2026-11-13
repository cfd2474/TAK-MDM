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

"""The stock ATLAS boot and shutdown animations (W491).

Operator, 2026-11-13: *"include them as a stock qmg in atlas. There will be
portrait and landscape versions of the bootup, bootloop, and shutdown
sequences. they should be labeled atlas_portrait_boot,
atlas_landscape_bootloop, atlas_portrait_shutdown, etc."*

The six `.qmg` files ship in `dist/animations/` (mounted at `/seed`, like the
bundled apps) and are added to Content at start, named as the maker names its
own (`<name>_boot`, `_bootloop`, `_shutdown`), so the policy offers them with
no special case.

* **Added only when the name is free.** A file of that name in Content — the
  stock one from an earlier start, or the operator's own — is never replaced
  or duplicated. So a deleted stock animation comes back at the next start.
* **The landscape shutdown is already turned 90° clockwise**, as the maker's
  "Landscape tablet" switch does (✅ SM-X520 held landscape). Its description
  says so, because turning it again would show it on its side.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.artifacts.storage import ArtifactStorage
from app.db.models import ManagedFile
from app.services import files as file_service
from app.services.animation_maker import MEDIA_TYPE

#: Where the files live inside the seed directory.
SUBDIRECTORY = "animations"
ORIENTATIONS = ("portrait", "landscape")
#: Suffix → what the description calls it.
PARTS = (("boot", "bootup animation"), ("bootloop", "boot loop"), ("shutdown", "shutdown animation"))
_QMG = b"QM"


@dataclass(frozen=True)
class Stock:
    """One stock animation: its library name and what Content says about it."""

    name: str
    description: str

    @property
    def filename(self) -> str:
        return self.name + ".qmg"


def _describe(orientation: str, suffix: str, label: str) -> str:
    text = f"Stock ATLAS {label}, {orientation}"
    if orientation == "landscape" and suffix == "shutdown":
        text += ", already turned for a landscape tablet"
    return text


#: The six, in the order Content lists a name's parts.
STOCK: tuple[Stock, ...] = tuple(
    Stock(f"atlas_{orientation}_{suffix}", _describe(orientation, suffix, label))
    for orientation in ORIENTATIONS for suffix, label in PARTS
)


@dataclass(frozen=True)
class Outcome:
    """What happened to one stock file."""

    name: str
    status: str  # "added", "present", "missing" or "refused"


def seed(session: Session, storage: ArtifactStorage, seed_dir: Path) -> list[Outcome]:
    """Add each stock animation whose name Content does not hold yet.

    The caller commits. Never raises for a missing or bad file: the start of
    the server must not depend on it.
    """
    directory = Path(seed_dir) / SUBDIRECTORY
    taken = set(session.scalars(
        select(ManagedFile.name).where(ManagedFile.name.in_([s.name for s in STOCK]))))
    outcomes = []
    for stock in STOCK:
        if stock.name in taken:
            outcomes.append(Outcome(stock.name, "present"))
            continue
        path = directory / stock.filename
        if not path.is_file():
            outcomes.append(Outcome(stock.name, "missing"))
            continue
        data = path.read_bytes()
        if not data.startswith(_QMG):
            outcomes.append(Outcome(stock.name, "refused"))
            continue
        file_service.ingest_file(
            session, storage, data, name=stock.name, original_filename=stock.filename,
            description=stock.description, media_type=MEDIA_TYPE, in_library=True)
        outcomes.append(Outcome(stock.name, "added"))
    return outcomes
