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

"""Content-addressed blob storage.

Every artifact is keyed by the SHA-256 of its bytes (D8). That buys three things at
once: identical uploads deduplicate for free, the agent can verify what it received
without trusting the transport, and a device that already holds a hash can skip the
download entirely — which matters when the link is metered and intermittent.

The interface is deliberately narrow so an S3/MinIO backend drops in behind it
without any caller changing. Local disk is enough for a single self-hosted server at
50-500 devices.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path
from typing import BinaryIO

_CHUNK = 1024 * 1024


class ArtifactNotFound(KeyError):
    pass


class ArtifactStorage(ABC):
    """Stores and retrieves blobs by their SHA-256 digest."""

    @abstractmethod
    def put(self, source: BinaryIO) -> tuple[str, int]:
        """Store a stream. Returns ``(sha256_hex, size_bytes)``."""

    @abstractmethod
    def open(self, digest: str) -> BinaryIO:
        """Open a stored blob for reading. Raises :class:`ArtifactNotFound`."""

    @abstractmethod
    def exists(self, digest: str) -> bool: ...

    @abstractmethod
    def size(self, digest: str) -> int: ...

    @abstractmethod
    def delete(self, digest: str) -> bool:
        """Remove a blob. Returns whether it was there."""

    def read_range(self, digest: str, start: int, end: int) -> Iterator[bytes]:
        """Yield bytes ``[start, end]`` inclusive, for HTTP Range responses."""
        remaining = end - start + 1
        with self.open(digest) as handle:
            handle.seek(start)
            while remaining > 0:
                chunk = handle.read(min(_CHUNK, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk


class LocalArtifactStorage(ArtifactStorage):
    """Filesystem backend with a two-level shard, to keep directories small."""

    def __init__(self, root: Path):
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, digest: str) -> Path:
        digest = digest.lower()
        if len(digest) != 64 or not all(c in "0123456789abcdef" for c in digest):
            # Guards against a caller passing user input straight through and
            # escaping the storage root.
            raise ValueError(f"not a sha256 hex digest: {digest!r}")
        return self._root / digest[:2] / digest[2:4] / digest

    def put(self, source: BinaryIO) -> tuple[str, int]:
        digest = hashlib.sha256()
        size = 0

        # Hash while streaming to a temp file, then rename into place. The digest is
        # not known until the whole stream is read, and a rename is atomic, so a
        # crash mid-upload can never leave a partial blob at a valid address.
        fd, temp_name = tempfile.mkstemp(dir=self._root, prefix=".incoming-")
        try:
            with os.fdopen(fd, "wb") as temp:
                while chunk := source.read(_CHUNK):
                    digest.update(chunk)
                    size += len(chunk)
                    temp.write(chunk)

            hex_digest = digest.hexdigest()
            destination = self._path(hex_digest)
            destination.parent.mkdir(parents=True, exist_ok=True)

            if destination.exists():
                os.unlink(temp_name)  # already stored; identical by definition
            else:
                shutil.move(temp_name, destination)
            return hex_digest, size
        except BaseException:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
            raise

    def open(self, digest: str) -> BinaryIO:
        path = self._path(digest)
        if not path.exists():
            raise ArtifactNotFound(digest)
        return path.open("rb")

    def exists(self, digest: str) -> bool:
        try:
            return self._path(digest).exists()
        except ValueError:
            return False

    def size(self, digest: str) -> int:
        path = self._path(digest)
        if not path.exists():
            raise ArtifactNotFound(digest)
        return path.stat().st_size

    def delete(self, digest: str) -> bool:
        path = self._path(digest)
        if not path.exists():
            return False
        path.unlink()
        return True
