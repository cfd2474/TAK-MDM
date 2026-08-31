import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.services import notifications

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
    title="TAK MDM",
    description="Self-hosted Android MDM with stackable, composable policies.",
    version="0.1.0",
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


@app.get("/healthz", tags=["ops"])
def healthz():
    return {"status": "ok"}
