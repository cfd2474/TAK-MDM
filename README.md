# TAK MDM

Self-hosted Android MDM for Samsung devices in Device Owner mode, built around
**stackable policies**: small single-concern policies you compose per device,
rather than one monolithic profile per use case.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design and
[PROJECT_STATE.md](PROJECT_STATE.md) for current status.

## Getting started (Docker)

```bash
docker compose up -d --build
```

That brings up four services and applies migrations automatically:

| Service | Purpose |
|---|---|
| `db` | Postgres 16 |
| `init` | One-shot: creates the device CA, bundle signing key, and a dev TLS cert into `./pki` |
| `api` | The application, on `127.0.0.1:8000` — **loopback only, bypasses mTLS** |
| `proxy` | nginx on `:8443`, terminating TLS and verifying client certificates |

`init` runs first because nginx must read the device CA **at startup** to verify
client certificates — it cannot be created lazily on first request.

### Try it without an Android device

```bash
python scripts/dev_enroll.py --serial R5CN00TAK01
```

This runs the exact sequence the agent will: mint a token, generate an EC P-256
keypair, submit a CSR, receive a client certificate, and check in over real mTLS —
then verify the bundle signature using a **deliberately independent** canonical-JSON
implementation. That last part is the contract the Kotlin agent must reimplement; if
the two ever disagree, this script fails the same way a tablet in the field would.

It finishes by demonstrating two things about the proxy: that a forged
`X-SSL-Client-Cert` header is stripped at the edge (403), and that the direct API
port accepts that same forged header — which is precisely why port 8000 is bound to
loopback and why devices must always go through `:8443`.

Certificates land in `pki/devices/<serial>/`, so you can keep poking at it:

```bash
curl --cacert pki/server.crt \
     --cert pki/devices/R5CN00TAK01/device.crt \
     --key  pki/devices/R5CN00TAK01/device.key \
     -X POST https://localhost:8443/api/v1/device/checkin \
     -H 'content-type: application/json' -d '{}'
```

Reset everything with `docker compose down -v && rm -rf pki`.

## Getting started (without Docker)

```bash
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate elsewhere
pip install -r requirements.txt

export TAKMDM_DATABASE_URL="postgresql+psycopg://takmdm:takmdm@localhost:5432/takmdm"
alembic upgrade head
python -m app.cli init-pki

uvicorn app.main:app --reload
```

Health check: `curl http://localhost:8000/healthz`
Interactive API docs: <http://localhost:8000/docs>

Tests run against in-memory SQLite and need no database or containers:

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

## Enrollment

Create a token scoped to the groups and tags the device should join, and it arrives
with its policy stack already resolved:

```bash
curl -X POST localhost:8000/api/v1/enrollment-tokens \
  -H 'content-type: application/json' \
  -d '{"name":"Field Rollout","group_ids":["<group-uuid>"],"max_uses":50}'
```

The response carries the secret **once**, plus ready-made provisioning payloads —
the QR JSON for Device Owner setup-wizard enrollment, and the fields to paste into a
Knox Mobile Enrollment profile. Only a hash of the secret is stored.

The agent then generates an EC P-256 keypair in the Android Keystore (StrongBox on
Samsung), posts a CSR to `POST /api/v1/enroll`, and receives a client certificate.
Every later `POST /api/v1/device/checkin` authenticates by mTLS, so there is no
bearer token to expire while a device is dark for a month.

> **Deployment prerequisite.** mTLS terminates at your reverse proxy, which must
> forward the verified certificate in `x-ssl-client-cert` **and strip that header
> from inbound requests**. The app re-verifies issuer, signature, expiry, and
> revocation, but possession of the private key is proven by the TLS handshake at
> the proxy. Never expose the app directly.

The device CA is generated on first use under `pki/` (gitignored). That private key
can mint any device identity — treat it as the crown jewel.

## Check-in: desired state, not commands

The device says which version it holds; the server replies with the current
declarative state **only if that differs**, and the agent diffs and converges
locally.

```
POST /api/v1/device/checkin
  { state_version: 6, applied_state_version: 6, results: [...] }
→ { state_version: 7,
    desired_state: { schema_version, device_id, state_version, policy },
    signature: "<ed25519>",
    commands: [ { id, command_type, params, expires_at } ],
    next_checkin_seconds: 847 }
```

This is the core of the offline design. A device dark for three weeks receives one
document and catches up — it never replays an ordered backlog whose intermediate
steps have been overtaken. Bundles are Ed25519-signed over canonical JSON, verified
independently of TLS, and deterministic per `(device, state_version)` so they can be
cached or relayed.

Alongside it sits a small queue for genuinely momentary actions — `reboot`, `lock`,
`wipe`, `locate`, `screenshot`, `clear_app_data`. These are delivered at-least-once
until acknowledged, so they must be idempotent, and each expires on a per-type TTL
rather than surprising a device that resurfaces weeks later.

`Device.acked_state_version` records what the device confirmed it applied. The gap
between that and `state_version` is the fleet's convergence lag — "the server has v7"
and "the device is running v7" are different claims.

> FCM push is not wired up. Devices poll on a jittered ~15 minute interval. Push was
> always a latency optimization, never a correctness dependency, so adding it later
> changes no protocol.

## Layout

| Path | Contents |
|---|---|
| [app/policies/](app/policies/) | Merge strategies, spec schemas, type registry, and the pure resolver |
| [app/services/](app/services/) | Database ↔ resolver bridge, caching, invalidation |
| [app/api/](app/api/) | FastAPI routers and request/response models |
| [app/db/](app/db/) | ORM models |
| [alembic/](alembic/) | Migrations |
