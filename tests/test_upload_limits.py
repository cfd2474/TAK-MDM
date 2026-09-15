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

"""`SEC_AUDIT.md` M-1 — the cap has to bite *during* the read.

⚠️ **The 413 was already correct before this work item.** Every upload handler
compared `len(data)` against `max_upload_bytes` and refused. What none of them
did was refuse before the body was resident, so a 50 GB POST was rejected only
once 50 GB had been read into the container's heap.

That makes the status-code assertions in this file nearly worthless on their own:
they passed against the old code too. `test_the_read_stops_at_the_cap` is the one
that distinguishes the fix from what it replaced — it measures how much the
server actually took before saying no.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.api import uploads

ADMIN = {"x-authentik-username": "limits", "x-authentik-groups": "takmdm-admins"}


#: How much a flooding sender is allowed to be in these tests.
#:
#: ⚠️ Bounded rather than truly endless, and deliberately: a reader that
#: consumes everything must **fail** this suite, not hang it. An unbounded stream
#: would turn the regression into a test run that never finishes, which nobody
#: diagnoses as "the upload cap regressed".
FLOOD_BYTES = 64 * 1024 * 1024


class FloodStream:
    """A sender with far more to give than the cap allows.

    Reports how much was actually taken, which is the only way to tell a reader
    that stops at the cap from one that measures after the fact — both return the
    same status code to a client.
    """

    def __init__(self, total: int = FLOOD_BYTES) -> None:
        self.remaining = total
        self.served = 0

    def read(self, size: int = -1) -> bytes:
        count = self.remaining if size is None or size < 0 else min(size, self.remaining)
        self.remaining -= count
        self.served += count
        return b"\0" * count


class CountingStream:
    """A finite stream that reports how much of itself was consumed."""

    def __init__(self, payload: bytes) -> None:
        self._buffer = io.BytesIO(payload)
        self.served = 0

    def read(self, size: int = -1) -> bytes:
        chunk = self._buffer.read(size)
        self.served += len(chunk)
        return chunk


# --------------------------------------------------------------------------- #
# The reader
# --------------------------------------------------------------------------- #


def test_an_upload_under_the_cap_comes_back_whole():
    payload = b"terrain" * 1000

    assert uploads.read_capped(CountingStream(payload), len(payload)) == payload


def test_the_cap_is_inclusive():
    """Exactly at the limit is allowed. Off by one here rejects a legal upload
    on a boundary nobody would think to test by hand."""
    payload = b"x" * 64

    assert uploads.read_capped(CountingStream(payload), 64) == payload
    with pytest.raises(uploads.UploadTooLarge):
        uploads.read_capped(CountingStream(payload), 63)


def test_the_read_stops_at_the_cap():
    """⚠️ The assertion this whole work item exists for.

    A reader that materialises the body and measures afterwards takes all 64 MB
    and then refuses it. One that measures as it goes takes the cap plus at most
    one chunk. Both answer 413 — which is why the status code cannot tell them
    apart and this can.
    """
    stream = FloodStream()
    limit = 4 * uploads.CHUNK_BYTES

    with pytest.raises(uploads.UploadTooLarge):
        uploads.read_capped(stream, limit)

    assert stream.served <= limit + uploads.CHUNK_BYTES, (
        f"took {stream.served} bytes to refuse an upload capped at {limit} — the "
        f"cap is being applied after the body is already in memory."
    )


def test_the_exception_names_the_limit_and_not_the_size():
    """The size is genuinely unknown — the rest of the body was never read — and
    a message inventing one would be a lie an operator could act on."""
    with pytest.raises(uploads.UploadTooLarge) as raised:
        uploads.read_capped(CountingStream(b"x" * 10), 4)

    assert raised.value.limit == 4
    assert "4 bytes" in str(raised.value)


def test_an_empty_upload_is_empty_rather_than_an_error():
    """Zero bytes is a form field the operator left blank, not an attack."""
    assert uploads.read_capped(CountingStream(b""), 10) == b""


def test_a_zero_cap_refuses_everything_but_nothing():
    assert uploads.read_capped(CountingStream(b""), 0) == b""
    with pytest.raises(uploads.UploadTooLarge):
        uploads.read_capped(CountingStream(b"x"), 0)


def test_a_negative_cap_is_a_programming_error_not_a_silent_pass():
    """⚠️ A bug in a caller's budget arithmetic arrives here as a negative
    number. `ValueError` makes it a traceback naming this function; treating it
    as "no room" would make it an upload silently refused, and treating it as
    unlimited would make it one silently allowed past the cap."""
    with pytest.raises(ValueError):
        uploads.read_capped(CountingStream(b"x"), -1)


@pytest.mark.anyio
async def test_the_async_reader_rejects_a_negative_cap_too():
    """⚠️ This is the one that matters, and testing only the sync reader missed
    it: the multi-file handlers pass `max_upload_bytes - total`, and they are the
    handlers that call the **async** reader. The arithmetic guard has to be on
    the function that actually receives the arithmetic.
    """
    class Stub:
        async def read(self, size: int = -1) -> bytes:
            return b""

    with pytest.raises(ValueError):
        await uploads.read_capped_async(Stub(), -1)


@pytest.mark.anyio
async def test_the_async_reader_behaves_the_same():
    class FloodAsyncStream(FloodStream):
        async def read(self, size: int = -1) -> bytes:  # type: ignore[override]
            return FloodStream.read(self, size)

    stream = FloodAsyncStream()
    limit = 2 * uploads.CHUNK_BYTES

    with pytest.raises(uploads.UploadTooLarge):
        await uploads.read_capped_async(stream, limit)

    assert stream.served <= limit + uploads.CHUNK_BYTES, (
        f"took {stream.served} bytes to refuse a package capped at {limit}"
    )


# --------------------------------------------------------------------------- #
# The handlers
# --------------------------------------------------------------------------- #


@pytest.fixture
def tiny_cap(settings):
    """A cap small enough to exceed in a test without allocating anything."""
    settings.max_upload_bytes = 2048
    return settings.max_upload_bytes


OVERSIZE = b"\0" * 4096


@pytest.mark.parametrize(
    "path,field,expected",
    [
        ("/api/v1/files", "file", 413),
        ("/api/v1/packages", "file", 413),
        ("/policies/image", "file", 413),
        ("/apps/preview-upload", "file", 400),
        ("/policies/file/upload", "file", 413),
        ("/policies/dted/upload", "file", 413),
        ("/policies/data-package/upload", "file", 413),
    ],
)
def test_an_oversize_upload_is_refused(
    client: TestClient, tiny_cap, path, field, expected
):
    response = client.post(
        path,
        files={field: ("big.bin", OVERSIZE, "application/octet-stream")},
        headers=ADMIN,
    )

    assert response.status_code == expected, response.text
    assert str(tiny_cap) in response.text


@pytest.mark.parametrize("path", ["/apps/upload", "/content/upload", "/content/data-package/upload"])
def test_an_oversize_upload_to_a_form_redirects_with_the_reason(
    client: TestClient, tiny_cap, path
):
    """These answer a browser form, so the refusal is a redirect carrying the
    message rather than a status code the operator would never see."""
    response = client.post(
        path,
        data={"name": "x"},
        files={"file": ("big.bin", OVERSIZE, "application/octet-stream")},
        headers=ADMIN,
        follow_redirects=False,
    )

    assert response.status_code in (302, 303), response.text
    assert "exceeds" in response.headers["location"]


def test_several_small_files_cannot_add_up_past_the_cap(client: TestClient, tiny_cap):
    """⚠️ Ten files of 300 MB is the same denial of service as one file of 3 GB.

    The per-file budget is what remains of the package's, not the whole cap.
    """
    half = b"\0" * 1500
    response = client.post(
        "/policies/data-package/create",
        data={"name": "Big"},
        files=[
            ("files", ("a.bin", half, "application/octet-stream")),
            ("files", ("b.bin", half, "application/octet-stream")),
        ],
        headers=ADMIN,
    )

    assert response.status_code == 413, response.text
    assert str(tiny_cap) in response.text


def test_a_package_within_the_cap_is_still_built(client: TestClient, tiny_cap):
    """The other half: a limit that refuses legitimate work is not a fix."""
    response = client.post(
        "/policies/data-package/create",
        data={"name": "Small"},
        files=[
            ("files", ("a.txt", b"alpha", "text/plain")),
            ("files", ("b.txt", b"bravo", "text/plain")),
        ],
        headers=ADMIN,
    )

    assert response.status_code == 200, response.text


def test_an_empty_upload_still_reports_as_empty_not_as_too_large(
    client: TestClient, tiny_cap
):
    """⚠️ The size check now runs first. An empty file must not come back as
    'exceeds 2048 bytes', which would send an operator hunting for a large file
    they never attached."""
    response = client.post(
        "/policies/image",
        files={"file": ("empty.png", b"", "image/png")},
        headers=ADMIN,
    )

    assert response.status_code == 422, response.text
    assert "empty" in response.text
