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

import asyncio
import logging
import sys
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.version import build_info
from app.security import admin_auth
from app.security import headers as security_headers
from app.security import keyfiles
from app.services import notifications
from app.web import routes as web_routes

from app.api.routers import (
    admin_settings,
    app_groups,
    artifacts,
    assignments,
    checkin,
    commands,
    device_logs,
    effective,
    enrollment,
    files,
    inventory,
    packages,
    policies,
    policy_types,
    profiles,
    wait,
)

log = logging.getLogger(__name__)


def _make_our_logs_visible() -> None:
    """Let this application's own INFO lines reach the container log.

    ⚠️ **Without this they are discarded.** Uvicorn configures the root logger at
    WARNING, so every `log.info` written anywhere under `app.` has been going
    nowhere since the beginning — the index warm-up's "index ready", the catalog
    backfill's progress, and (the reason this was noticed) the retention sweep's
    daily line. `docker compose logs` showed the server starting and nothing else,
    which reads as a quiet, healthy server rather than as a muted one.

    ⚠️ **Raising the level is not enough, and that is the whole trap.** Uvicorn
    configures handlers on its own `uvicorn.*` loggers and leaves the **root
    logger with none**. Records from `app.` therefore propagate to a root that
    cannot print them and fall through to Python's `logging.lastResort` handler —
    which is hard-wired to WARNING. That is why this server's warnings have always
    appeared while its INFO lines never have, and why a first attempt that only
    called `setLevel` changed nothing at all.

    So the `app` tree gets a handler of its own. Uvicorn's access log is left
    alone: a line per request would bury exactly the operational lines this exists
    to surface.
    """
    logger = logging.getLogger("app")
    logger.setLevel(logging.INFO)
    # Guarded, because lifespan can run more than once in a process (a reload, or
    # a test that builds the app repeatedly) and each pass would add another
    # handler, printing every line twice, then three times.
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(logging.Formatter("%(levelname)s [%(name)s] %(message)s"))
        logger.addHandler(handler)

#: How often the retention sweeper wakes. Daily, because retention is measured in
#: days — sweeping more often would delete the same rows a few hours earlier and
#: cost a query every time for nothing.
_RETENTION_INTERVAL_SECONDS = 24 * 60 * 60


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Give the change bus the serving loop.

    Writes happen in FastAPI's threadpool, but long-poll waiters are asyncio events
    on this loop, so notifications have to hop back onto it.
    """
    _make_our_logs_visible()
    notifications.bus.bind_loop(asyncio.get_running_loop())
    admin_auth.warn_if_unprotected(get_settings())
    # ⚠️ Looked at on every start, because the realistic way a private key becomes
    # world-readable is not this code — it is a restore, a `cp -r` that dropped
    # the mode, or a bind mount nobody tightened. None of those announce
    # themselves (SEC_AUDIT.md S-2).
    keyfiles.warn_on_exposed_keys(get_settings().pki_dir)
    _start_catalog_backfill(app)
    _start_index_warmup(app)
    _start_location_retention(app)
    yield


def _start_index_warmup(app: FastAPI) -> threading.Thread | None:
    """Parse the repository indexes before anyone searches (W103).

    ⚠️ **The first search after a restart took 11.4 seconds; the second took
    0.1.** The indexes are large — 59 MB for F-Droid, 111 MB for its archive,
    14 MB for IzzyOnDroid — and parsing them is the cost, which the disk cache
    does nothing for. An operator who searched moments after a deploy saw
    "Searching…" sit there long enough to look broken, which is exactly what
    happened.

    So the cost is paid at boot, on a worker thread, where nobody is waiting for
    it. A search arriving before this finishes is not broken, merely slow — the
    same 11 seconds it used to be — because `index()` is guarded and simply loads
    what is not yet loaded.

    ⚠️ Failures are logged and swallowed. A repository being unreachable at boot
    must not stop the server: the console has four other reasons to exist, and the
    search will report the problem itself when someone actually uses it.
    """

    # ⚠️ Resolved through `dependency_overrides`, for the reason the catalog
    # backfill gives above: a background task that reads the real settings is one
    # that reaches the real network in the middle of a test run. Calling
    # `get_settings()` here did exactly that — every test session spawned a thread
    # fetching 184 MB from F-Droid, swallowed as a warning so nothing failed.
    overrides = app.dependency_overrides
    settings = overrides.get(get_settings, get_settings)()
    if not settings.warm_indexes:
        return None

    def run() -> None:
        from pathlib import Path

        from app.services.app_sources import repos

        cache = Path(str(settings.cache_dir))
        for spec in repos.KNOWN:
            if spec.kind != "fdroid":
                continue
            try:
                source = repos.build(spec.name, cache)
                if source is not None:
                    count = len(source.index().get("packages") or {})
                    log.info("index ready: %s (%d packages)", spec.label, count)
            except Exception:
                log.warning(
                    "could not warm the %s index; search will load it on demand",
                    spec.label,
                    exc_info=True,
                )

    thread = threading.Thread(target=run, name="index-warmup", daemon=True)
    thread.start()
    return thread


def _start_location_retention(app: FastAPI) -> threading.Thread | None:
    """Delete location history past its retention window, once a day (W106 C5).

    ⚠️ **This host has no cron**, which is the whole reason the job lives inside
    the application. A retention policy that depends on someone remembering to
    install a timer is a retention policy that quietly does not run — and the
    failure is invisible, because a table that keeps growing looks exactly like a
    table that is being maintained until the day someone checks.

    Runs once at boot and then every 24 hours. Both matter: a server restarted
    often would never reach a daily tick, and one running for months must not wait
    for a restart.

    ⚠️ Failures are logged and swallowed, and the thread keeps its schedule. A
    purge that fails is a table that grows for another day; a purge that takes the
    process down with it is a fleet that stops being managed.
    """
    # ⚠️ Resolved through `dependency_overrides`, for the same reason the index
    # warm-up is: a background thread that reads the real settings is one that
    # touches the real database in the middle of a test run — and this one issues
    # DELETEs, which makes it considerably worse than a slow index fetch.
    overrides = app.dependency_overrides
    settings = overrides.get(get_settings, get_settings)()
    if not settings.purge_location_history:
        return None

    def run() -> None:
        from app.db.base import SessionLocal
        from app.services import locations as location_service

        while True:
            try:
                with SessionLocal() as session:
                    window = location_service.retention_days(session)
                    removed = location_service.purge(session)
                    session.commit()
                    # ⚠️ Logged every sweep, including the ones that delete
                    # nothing — which is almost all of them. A retention job that
                    # only speaks up when it deletes is indistinguishable from one
                    # that is not running at all, and the whole failure mode here
                    # is silent: a table that keeps growing looks exactly like a
                    # table being maintained, until someone checks. One line a day
                    # is what makes "is retention actually running" answerable.
                    log.info(
                        "location retention: %d point(s) removed, keeping %s",
                        removed,
                        "everything (window is 0)" if window <= 0 else f"{window} days",
                    )
            except Exception:
                log.warning("location retention sweep failed", exc_info=True)
            time.sleep(_RETENTION_INTERVAL_SECONDS)

    thread = threading.Thread(target=run, name="location-retention", daemon=True)
    thread.start()
    return thread


def _start_catalog_backfill(app: FastAPI) -> threading.Thread:
    """Fill in app names and icons that predate the code that reads them.

    ⚠️ This exists because `backfill_labels` had **no caller at all** — not in the
    app, not in a test. It was written for W51, never wired up, and so a library
    uploaded before names could be read stayed named by its package id forever.
    W53 added icons to the same pass and would have inherited the same fate.

    Runs on a worker thread: re-reading a base APK costs about a second for an app
    with a large resource table, and boot must not wait for the whole library.
    It only ever fills values that are **missing**, so running it in every worker
    of a multi-worker deployment duplicates work but cannot corrupt anything.

    ⚠️ Resolved through `dependency_overrides`, not by importing `SessionLocal`.
    `get_session_factory` says why in as many words: a background task that
    imports the factory directly is one that talks to the real database in the
    middle of a test run.
    """
    from app.api.deps import get_session_factory, get_storage

    overrides = app.dependency_overrides
    session_factory = overrides.get(get_session_factory, get_session_factory)()
    storage = overrides.get(get_storage, lambda: get_storage(get_settings()))()

    def run() -> None:
        from app.services import packages as package_service

        try:
            with session_factory() as session:
                filled = package_service.backfill_labels(session, storage)
                session.commit()
            if filled:
                log.info("catalog backfill: filled %d package(s)", filled)
        except Exception:
            # A convenience pass must never take the server down with it.
            log.exception("catalog backfill failed; the console is unaffected")

    # Returned so a test can join it instead of racing it. Nothing in the serving
    # path waits on this thread.
    thread = threading.Thread(target=run, name="catalog-backfill", daemon=True)
    thread.start()
    return thread


app = FastAPI(
    title="ATLAS",
    summary="ATAK Tactical Lifecycle & Administration System",
    description="Self-hosted Android MDM with stackable, composable policies.",
    # ⚠️ The running revision, not a number somebody must remember to bump —
    # "0.1.0" sat here through a hundred work items telling nobody anything (W102).
    version=build_info().revision,
    contact={"name": "TAK-Solutions LLC"},
    license_info={"name": "Apache 2.0", "identifier": "Apache-2.0"},
    lifespan=lifespan,
)

# Browser-facing constraints on every response, including the static mount and
# the error pages a router never sees (SEC_AUDIT M-6).
security_headers.install(app)

# --------------------------------------------------------------------------- #
# Device-facing. Never behind admin authentication: a tablet cannot perform an
# interactive login. These authenticate by mTLS client certificate, or by the
# enrollment token during provisioning.
# --------------------------------------------------------------------------- #
app.include_router(checkin.router)
app.include_router(artifacts.router)
app.include_router(artifacts.icons_router)
app.include_router(wait.router)
app.include_router(enrollment.device_router)
app.include_router(device_logs.router)

# --------------------------------------------------------------------------- #
# Administrative. Guarded here rather than per endpoint, so a new route is
# protected by default and forgetting the dependency cannot quietly expose one.
# --------------------------------------------------------------------------- #
# csrf_protected depends on admin_required, so this both authenticates and
# CSRF-checks. Applied at registration for the same reason authentication is: a new
# admin route is covered by default, and forgetting a decorator cannot quietly
# expose one (D70).
_admin = [Depends(admin_auth.csrf_protected)]

for admin_router in (
    policy_types.router,
    policies.router,
    profiles.router,
    inventory.router,
    assignments.router,
    assignments.targets_router,
    effective.router,
    enrollment.router,
    commands.router,
    device_logs.admin_router,
    packages.router,
    app_groups.router,
    admin_settings.router,
    admin_settings.device_router,
    files.router,
    files.selections_router,
    web_routes.router,
):
    app.include_router(admin_router, dependencies=_admin)


# Console CSS/JS. A mount, so it sits outside the admin guard (these assets are
# not sensitive) and outside the OpenAPI schema. Not exposed on the device port —
# nginx default-denies everything there that is not an explicit device endpoint.
app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).parent / "web" / "static")),
    name="static",
)


#: What this service calls itself when something asks. Stable: an orchestrator
#: matches on it to be sure it is talking to ATLAS and not to whatever else
#: happens to answer on that port.
SERVICE_NAME = "atlas-mdm"


@app.get("/healthz", tags=["ops"])
def healthz():
    """Liveness, plus the version actually running.

    ⚠️ The version here comes from the *running process*, which is the whole
    point. A deployment's checkout can say 1.2.2 while the container still
    serves 1.0.0 — `docker compose up -d` without `--build` keeps the old image,
    and that has bitten this project before. Reading the repo cannot tell the
    difference; reading this can.
    """
    return {"status": "ok", "service": SERVICE_NAME, "version": build_info().version or ""}


@app.get("/version", tags=["ops"])
def version():
    """The running version, for an orchestrator to verify a deploy against.

    Unauthenticated, like `/healthz`, because the thing that needs it runs
    beside the container rather than through the console's login. It discloses
    a version string and nothing else — the same string already printed in the
    footer of every page to anyone who can see the console at all.

    `revision` is included because a tag can move and a commit cannot; an
    orchestrator comparing releases wants `version`, a human chasing a specific
    build wants `revision`.
    """
    info = build_info()
    return {
        "service": SERVICE_NAME,
        "version": info.version or "",
        "revision": info.revision,
    }
