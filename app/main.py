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
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.security import admin_auth
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

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Give the change bus the serving loop.

    Writes happen in FastAPI's threadpool, but long-poll waiters are asyncio events
    on this loop, so notifications have to hop back onto it.
    """
    notifications.bus.bind_loop(asyncio.get_running_loop())
    admin_auth.warn_if_unprotected(get_settings())
    yield


app = FastAPI(
    title="ATLAS",
    summary="ATAK Tactical Lifecycle & Administration System",
    description="Self-hosted Android MDM with stackable, composable policies.",
    version="0.1.0",
    contact={"name": "TAK-Solutions LLC"},
    license_info={"name": "Apache 2.0", "identifier": "Apache-2.0"},
    lifespan=lifespan,
)

# --------------------------------------------------------------------------- #
# Device-facing. Never behind admin authentication: a tablet cannot perform an
# interactive login. These authenticate by mTLS client certificate, or by the
# enrollment token during provisioning.
# --------------------------------------------------------------------------- #
app.include_router(checkin.router)
app.include_router(artifacts.router)
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


@app.get("/healthz", tags=["ops"])
def healthz():
    return {"status": "ok"}
