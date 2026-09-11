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

"""Plugin imports that run off the request, so their progress can be watched.

A catalog plugin can be 433 MB. Downloading that inside the request means the
operator stares at a blank tab for minutes with no way to tell a slow download
from a hung one — so the work moves to a thread and the console polls for
progress.

Deliberately small. There is no queue, no retry, no persistence: an import is one
operator pressing one button, and a job that dies with the process is a job the
operator can simply press again. Anything more would be a scheduler, and this is
not the place to grow one.

⚠️ **Progress lives in this process only** (R16, same constraint as the push
doorbell and the token-refresh lock). Under multiple workers the poll could land
on a worker that never heard of the job. Single-worker today; when that changes
this needs to move into the database along with the rest.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

#: Finished jobs are dropped this long after they end. Long enough for the page
#: to see the final state; short enough that nothing accumulates.
_RETENTION = timedelta(minutes=10)


@dataclass
class ImportJob:
    id: str
    identifier: str
    label: str
    state: str = "running"  # running | done | failed
    downloaded: int = 0
    #: 0 means the server never said how big it is — render an indeterminate bar
    #: rather than a percentage of nothing.
    total: int = 0
    package_name: str | None = None
    error: str | None = None
    finished_at: datetime | None = None

    @property
    def percent(self) -> int:
        if not self.total:
            return 0
        return min(100, int(self.downloaded * 100 / self.total))

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "state": self.state,
            "label": self.label,
            "downloaded": self.downloaded,
            "total": self.total,
            "percent": self.percent,
            "package_name": self.package_name,
            "error": self.error,
        }


_JOBS: dict[str, ImportJob] = {}
_LOCK = threading.Lock()


def get(job_id: str) -> ImportJob | None:
    with _LOCK:
        return _JOBS.get(job_id)


def start(
    session_factory,
    vault,
    storage,
    *,
    identifier: str,
    label: str,
    product: str,
    product_version: str,
    runner=None,
) -> ImportJob:
    """Begin an import in the background and return the job to poll.

    ``session_factory`` is passed in rather than imported: the thread cannot use
    the request's session, but a test still has to be able to hand it one.
    ``runner`` likewise, so the whole thing can be driven synchronously in a test
    without threads making the outcome depend on timing.
    """
    job = ImportJob(id=uuid.uuid4().hex, identifier=identifier, label=label)
    with _LOCK:
        _prune_locked()
        _JOBS[job.id] = job

    def work() -> None:
        _run(job, session_factory, vault, storage, product, product_version)

    (runner or _thread)(work)
    return job


def _thread(work) -> None:
    threading.Thread(target=work, daemon=True).start()


def _run(job, session_factory, vault, storage, product, product_version) -> None:
    from app.services import tak_gov_link

    def progress(written: int, total: int) -> None:
        job.downloaded = written
        job.total = total

    session = session_factory()
    try:
        result = tak_gov_link.import_plugin(
            session,
            vault,
            storage,
            job.identifier,
            product=product,
            product_version=product_version,
            on_progress=progress,
        )
        session.commit()
        job.package_name = result.package.package_name
        job.state = "done"
    except Exception as exc:  # noqa: BLE001 - the message is the whole point
        session.rollback()
        # Reported verbatim. These are download failures, hash mismatches and
        # ingest refusals, all of which name the specific problem; paraphrasing
        # them into "import failed" would throw away the only useful part.
        job.error = str(exc) or exc.__class__.__name__
        job.state = "failed"
        logger.warning("plugin import %s failed: %s", job.identifier, job.error)
    finally:
        job.finished_at = datetime.now(timezone.utc)
        session.close()


def start_repo(
    session_factory,
    storage,
    *,
    source,
    version,
    label: str,
    runner=None,
) -> ImportJob:
    """Begin a third-party repository import in the background (W97).

    Sibling of [start] rather than a parameter on it: the tak.gov import needs a
    token vault, a product and a product version, and none of those mean anything
    to a repository that simply serves files. Sharing the *job* machinery is the
    part worth reusing — the console polls one route either way.
    """
    job = ImportJob(
        id=uuid.uuid4().hex,
        identifier=f"{source.name}:{version.package_name}",
        label=label,
        # The catalogue usually states the size, so the bar is a real percentage
        # from the first byte rather than an indeterminate spinner.
        total=version.size or 0,
    )
    with _LOCK:
        _prune_locked()
        _JOBS[job.id] = job

    def work() -> None:
        _run_repo(job, session_factory, storage, source, version)

    (runner or _thread)(work)
    return job


def _run_repo(job, session_factory, storage, source, version) -> None:
    from app.services import repo_import

    def progress(written: int, total: int) -> None:
        job.downloaded = written
        # ⚠️ Only ever widen what is known. The catalogue may have stated a
        # size the source cannot confirm mid-stream (apkeep reports no total at
        # all), and letting a 0 overwrite a real figure would turn a working
        # percentage into a byte counter halfway through (W127).
        if total:
            job.total = total

    session = session_factory()
    try:
        imported = repo_import.import_version(
            session, storage, source, version, label=job.label, progress=progress
        )
        session.commit()
        job.package_name = imported.package.package_name
        job.downloaded = job.total
        job.state = "done"
    except Exception as exc:  # noqa: BLE001 - the message is the whole point
        session.rollback()
        # Verbatim, for the same reason as the tak.gov path: these are hash
        # mismatches, signature refusals and ingest errors, each of which names
        # the specific problem. "Import failed" would throw that away.
        job.error = str(exc) or exc.__class__.__name__
        job.state = "failed"
        logger.warning("repo import %s failed: %s", job.identifier, job.error)
    finally:
        job.finished_at = datetime.now(timezone.utc)
        session.close()


def _prune_locked() -> None:
    cutoff = datetime.now(timezone.utc) - _RETENTION
    for key in [
        k for k, j in _JOBS.items() if j.finished_at and j.finished_at < cutoff
    ]:
        del _JOBS[key]
