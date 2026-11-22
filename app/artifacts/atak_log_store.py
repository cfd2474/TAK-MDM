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

"""Where uploaded ATAK session logs live on disk (W416).

One gzip file per log, named by its database row id, in `<artifact_dir>/atak-logs/`.

⚠️ **Not the content-addressed artifact store.** That store deduplicates blobs
many devices download; a session log belongs to one device and one moment, is
replaced when its finished copy arrives, and ages out. Addressing it by digest
would need a reference count to delete safely.

⚠️ **Named by row id, so the files can be reconciled with the rows.** A device
can be deleted three different ways, and the database cascade removes its log
rows without anything here knowing. :meth:`sweep` deletes any file whose row is
gone, so no deletion path has to remember these files exist.

⚠️ **Inside `artifact_dir` deliberately.** It is the deployment's one persistent,
writable mount; a new mount would need every install to create the host folder
with the right owner. The store's own shard folders are two hex characters, so
`atak-logs` cannot collide with one, and nothing sweeps that directory.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import BinaryIO

_CHUNK = 1024 * 1024


class TooLarge(ValueError):
    """The upload passed its size limit."""


class AtakLogStore:
    def __init__(self, root: Path):
        self._root = Path(root)

    def _path(self, log_id: uuid.UUID) -> Path:
        # `uuid.UUID` only: a caller cannot pass a path through here.
        return self._root / f"{uuid.UUID(str(log_id))}.gz"

    def put(self, log_id: uuid.UUID, source: BinaryIO, *, max_bytes: int) -> int:
        """Store `source` for `log_id`, replacing any earlier copy. Returns its size.

        Written to a temp file and renamed into place, so a reader never sees
        a half-written log, and a refused upload leaves the earlier one intact.
        """
        self._root.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(dir=self._root, prefix=".incoming-")
        size = 0
        try:
            with os.fdopen(fd, "wb") as temp:
                while chunk := source.read(_CHUNK):
                    size += len(chunk)
                    if size > max_bytes:
                        raise TooLarge(f"the log is over {max_bytes} bytes compressed")
                    temp.write(chunk)
            os.replace(temp_name, self._path(log_id))
            return size
        except BaseException:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
            raise

    def move(self, source_id: uuid.UUID, target_id: uuid.UUID) -> None:
        """Put `source_id`'s file in place of `target_id`'s, atomically."""
        os.replace(self._path(source_id), self._path(target_id))

    def open(self, log_id: uuid.UUID) -> BinaryIO:
        return open(self._path(log_id), "rb")

    def delete(self, log_id: uuid.UUID) -> None:
        self._path(log_id).unlink(missing_ok=True)

    def ids(self) -> Iterator[uuid.UUID]:
        """Every log id with a file here."""
        if not self._root.is_dir():
            return
        for path in self._root.glob("*.gz"):
            try:
                yield uuid.UUID(path.stem)
            except ValueError:
                continue

    def sweep(self, keep: Iterable[uuid.UUID]) -> int:
        """Delete every file not in `keep`. Returns how many went."""
        wanted = set(keep)
        gone = 0
        for log_id in list(self.ids()):
            if log_id not in wanted:
                self.delete(log_id)
                gone += 1
        return gone
