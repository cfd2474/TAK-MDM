from fastapi import FastAPI

from app.api.routers import (
    artifacts,
    assignments,
    checkin,
    commands,
    effective,
    enrollment,
    inventory,
    packages,
    policies,
    policy_types,
)

app = FastAPI(
    title="TAK MDM",
    description="Self-hosted Android MDM with stackable, composable policies.",
    version="0.1.0",
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


@app.get("/healthz", tags=["ops"])
def healthz():
    return {"status": "ok"}
