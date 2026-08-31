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

from fastapi import FastAPI

from app.services import notifications
from app.web import routes as web_routes

from app.api.routers import (
    artifacts,
    assignments,
    checkin,
    commands,
    effective,
    enrollment,
    files,
    inventory,
    packages,
    policies,
    policy_types,
    wait,
)

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Give the change bus the serving loop.

    Writes happen in FastAPI's threadpool, but long-poll waiters are asyncio events
    on this loop, so notifications have to hop back onto it.
    """
    notifications.bus.bind_loop(asyncio.get_running_loop())
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

app.include_router(policy_types.router)
app.include_router(policies.router)
app.include_router(inventory.router)
app.include_router(assignments.router)
app.include_router(effective.router)
app.include_router(enrollment.router)
app.include_router(checkin.router)
app.include_router(commands.router)
app.include_router(packages.router)
app.include_router(artifacts.router)
app.include_router(files.router)
app.include_router(files.selections_router)
app.include_router(assignments.targets_router)
app.include_router(wait.router)
app.include_router(web_routes.router)


@app.get("/healthz", tags=["ops"])
def healthz():
    return {"status": "ok"}
