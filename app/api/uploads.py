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

"""Reading an upload without letting the sender choose how much memory we use.

`SEC_AUDIT.md` **M-1**.

⚠️ **The cap was already there and was already checked everywhere.** Every one of
the thirteen upload handlers compared `len(data)` against
`settings.max_upload_bytes` and returned 413. What none of them did was check it
*before* `data = file.file.read()` had already pulled the whole body into memory.
A 50 GB POST was refused — after 50 GB was resident, which is the part that takes
the management plane down, and with it every device check-in.

So this is not a new limit. It is the existing limit, enforced at a point where
it can still prevent something.

The residual is worth stating rather than leaving to be discovered: a *permitted*
upload is still materialised as `bytes` and then usually copied again into an
`io.BytesIO`, so one 2 GiB upload costs roughly 4 GiB. Bounding that properly
means handing the file object to `inspect_apk` and `dted.plan` instead of bytes —
a real refactor across both, not a line here. Until then the ceiling is the
setting, and the setting is what an operator should tune to their box.
"""

from __future__ import annotations

from typing import Protocol

#: How much is pulled from the stream at a time.
#:
#: The overshoot this allows is bounded by one chunk: the read stops as soon as
#: the running total passes the cap, so peak use is `limit + CHUNK_BYTES` rather
#: than whatever the sender felt like sending.
CHUNK_BYTES = 1024 * 1024


class UploadTooLarge(Exception):
    """Raised the moment an upload is known to exceed its budget.

    Carries `limit` so a handler can say what was exceeded. It deliberately does
    **not** carry how much was actually sent — that is not known, because the
    point is that the rest was never read.
    """

    def __init__(self, limit: int) -> None:
        super().__init__(f"upload exceeds {limit} bytes")
        self.limit = limit


class SyncStream(Protocol):
    def read(self, size: int = ..., /) -> bytes: ...


def read_capped(stream: SyncStream, limit: int) -> bytes:
    """Read a whole upload, or raise `UploadTooLarge` before it is all in memory.

    `stream` is the `SpooledTemporaryFile` behind FastAPI's `UploadFile.file`.
    Starlette has already spooled it to disk past 1 MB, so what this bounds is
    our own copy of it — which is the one that lives in the container's heap.
    """
    if limit < 0:
        raise ValueError("limit must not be negative")

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = stream.read(CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        # The check is inside the loop. That is the whole change: outside it,
        # this is `stream.read()` followed by `len(data) > limit`, which is what
        # every handler already did and which refuses a 50 GB body only once
        # 50 GB is resident. Whether the over-limit chunk is appended first is
        # cosmetic — one chunk either way.
        if total > limit:
            raise UploadTooLarge(limit)
        chunks.append(chunk)
    return b"".join(chunks)


class AsyncStream(Protocol):
    async def read(self, size: int = ..., /) -> bytes: ...


async def read_capped_async(stream: AsyncStream, limit: int) -> bytes:
    """`read_capped` for Starlette's `UploadFile`, whose `read` is a coroutine.

    Used by the two handlers that accept several files at once. They pass the
    budget *remaining* across the whole package rather than the per-file cap, so
    a package of many small files is bounded the same way one large file is.
    """
    if limit < 0:
        raise ValueError("limit must not be negative")

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await stream.read(CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise UploadTooLarge(limit)
        chunks.append(chunk)
    return b"".join(chunks)
