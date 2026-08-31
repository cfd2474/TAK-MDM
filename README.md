# TAK MDM

Self-hosted Android MDM for Samsung devices in Device Owner mode, built around
**stackable policies**: small single-concern policies you compose per device,
rather than one monolithic profile per use case.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design and
[PROJECT_STATE.md](PROJECT_STATE.md) for current status.

## Getting started

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate elsewhere
pip install -r requirements.txt

export TAKMDM_DATABASE_URL="postgresql+psycopg://takmdm:takmdm@localhost:5432/takmdm"
alembic upgrade head

uvicorn app.main:app --reload
```

Health check: `curl http://localhost:8000/healthz`
Interactive API docs: <http://localhost:8000/docs>

Tests run against in-memory SQLite and need no database:

```bash
pytest
```

## How stacking works

A policy is typed and single-concern (`PASSWORD`, `RESTRICTIONS`, `APP_CATALOG`).
You assign policies to a **device**, a **group**, or a **tag**, each with a `rank`.
The resolver merges everything reaching a device into one effective policy, per
field, using the strategy that field declares:

| Strategy | Example field | Behaviour |
|---|---|---|
| `MOST_RESTRICTIVE` | `allow_camera` | any `false` denies |
| `MAX` / `MIN` | `min_length` / `lock_timeout_seconds` | strictest number wins |
| `UNION` | `blocked_packages` | accumulates |
| `INTERSECT` | `allowed_packages` | only what every policy permits |
| `MERGE_BY_KEY` | `required_apps` | union by package, rank breaks collisions |
| `HIGHEST_RANK` | `kiosk_package` | top rank wins, conflict reported |

A policy that does not set a field contributes nothing to it — which is what lets a
narrow policy stack on a broad one without clobbering it.

### Key endpoints

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/policy-types` | Schema and merge rules for each policy type |
| `GET /api/v1/devices/{id}/effective-policy` | Merged policy, with provenance and conflicts |
| `GET /api/v1/devices/{id}/effective-policy/explain/{type}/{field}` | Why this field holds this value |
| `POST /api/v1/devices/{id}/effective-policy/preview` | Dry-run an assignment change, with a diff |

Every resolved field carries where it came from, which strategy chose it, and what
it overrode — so "why is this tablet's password length 12?" is always answerable.

## Layout

| Path | Contents |
|---|---|
| [app/policies/](app/policies/) | Merge strategies, spec schemas, type registry, and the pure resolver |
| [app/services/](app/services/) | Database ↔ resolver bridge, caching, invalidation |
| [app/api/](app/api/) | FastAPI routers and request/response models |
| [app/db/](app/db/) | ORM models |
| [alembic/](alembic/) | Migrations |
