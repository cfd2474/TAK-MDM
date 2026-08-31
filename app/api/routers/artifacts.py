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

"""Device-facing artifact download.

`Range` support is not a nicety here. These are the links the whole design assumes:
intermittent, metered, and prone to dropping halfway through a 200 MB XAPK. Without
resumption a device on a bad connection can burn its data allowance repeatedly and
never complete a single install.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import authenticated_device, get_db, get_storage
from app.artifacts.storage import ArtifactNotFound, ArtifactStorage
from app.db.models import Artifact, Device

router = APIRouter(prefix="/api/v1/device/artifacts", tags=["device"])

_RANGE_PATTERN = re.compile(r"^bytes=(\d*)-(\d*)$")


def _parse_range(header: str, size: int) -> tuple[int, int]:
    """Resolve a single byte range against a known size, per RFC 7233."""
    match = _RANGE_PATTERN.match(header.strip())
    if not match:
        raise HTTPException(
            status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, "malformed Range header"
        )

    raw_start, raw_end = match.group(1), match.group(2)

    if not raw_start and not raw_end:
        raise HTTPException(
            status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, "malformed Range header"
        )

    if not raw_start:
        # "bytes=-500" means the final 500 bytes, not "from 0 to 500".
        length = int(raw_end)
        if length == 0:
            raise HTTPException(
                status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, "zero-length suffix range"
            )
        start = max(0, size - length)
        end = size - 1
    else:
        start = int(raw_start)
        end = int(raw_end) if raw_end else size - 1
        end = min(end, size - 1)

    if start >= size or start > end:
        raise HTTPException(
            status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            f"range not satisfiable for a {size}-byte artifact",
        )
    return start, end


@router.get("/{digest}")
def download_artifact(
    digest: str,
    request: Request,
    device: Device = Depends(authenticated_device),
    session: Session = Depends(get_db),
    storage: ArtifactStorage = Depends(get_storage),
) -> Response:
    """Stream an artifact to an enrolled device, honouring Range requests.

    Any enrolled device may fetch any known artifact. The digest is unguessable and
    the content is an installable an operator chose to publish, so the useful
    boundary is enrollment rather than per-device authorization — and scoping it per
    device would break the shared-artifact deduplication the store is built on.
    """
    artifact = session.get(Artifact, digest.lower())
    if artifact is None or not storage.exists(digest):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown artifact")

    size = artifact.size_bytes
    headers = {
        "Accept-Ranges": "bytes",
        # Content-addressed, so the body can never change under a given URL.
        "ETag": f'"{artifact.sha256}"',
        "Cache-Control": "public, max-age=31536000, immutable",
        "X-Content-SHA256": artifact.sha256,
    }

    range_header = request.headers.get("range")
    if not range_header:
        try:
            handle = storage.open(digest)
        except ArtifactNotFound:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown artifact") from None
        return StreamingResponse(
            handle,
            media_type=artifact.media_type,
            headers={**headers, "Content-Length": str(size)},
        )

    start, end = _parse_range(range_header, size)
    return StreamingResponse(
        storage.read_range(digest, start, end),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=artifact.media_type,
        headers={
            **headers,
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Content-Length": str(end - start + 1),
        },
    )
