# Branding

## Developer

**TAK-Solutions LLC** — developer and publisher of ATLAS. Use this name for
authorship and attribution (README, API `contact` metadata, package author
fields, `LICENSE` copyright line).

## License

Apache License 2.0. Copyright line: `Copyright 2026 TAK-Solutions LLC`. The
[`LICENSE`](../LICENSE) and [`NOTICE`](../NOTICE) files live at the repo root;
keep the `NOTICE` attribution intact in any redistribution.

Every `.py`, `.kt`, and `.gradle.kts` source file carries the full Apache
boilerplate header. **New source files must include it** — the Alembic
`script.py.mako` template already does, so generated migrations are covered.
XML resources, `.md` docs, and config files are not headered.

## Name

**ATLAS** — **ATAK Tactical Lifecycle & Administration System**

A self-hosted Android MDM built around Device Owner mode, sideloaded APK/XAPK
deployment, Samsung Knox integration, and stackable composable policies, with
ATAK/TAK support as a first-class policy pack rather than a bolt-on.

- Full name on first use: *ATLAS (ATAK Tactical Lifecycle & Administration System)*.
- Short name thereafter: *ATLAS*.
- Not stylised in all-caps prose beyond the acronym itself — write "ATLAS", not
  "Atlas" and not "A.T.L.A.S.".

## Product family

The name scales to a family of components as the system grows:

| Component | Role |
|---|---|
| **ATLAS Console** | Admin web UI — policy builder, stacking view, fleet dashboard |
| **ATLAS Agent** | On-device Kotlin Device Owner agent |
| **ATLAS Fleet** | Fleet inventory, health, and convergence reporting |
| **ATLAS Provisioning** | Enrollment, QR / Knox Mobile Enrollment payloads, device PKI |

These are naming conventions for later work, not modules that all exist today. Use
them when a component grows large enough to warrant its own name; until then the
server is just "ATLAS".

## Scope of the rename

User-facing surfaces carry the ATLAS name: README, API metadata (`FastAPI` title
and OpenAPI docs), CLI help text, and architecture docs.

Code identifiers are deliberately **not** renamed:

- `org.takmdm.agent` — the agent package name is baked into built APKs, QR
  provisioning payloads, and signature-checksum pinning (D53–D60). Changing it
  invalidates provisioning and forces a re-sign.
- `TAKMDM_` environment prefix, `takmdm` Postgres role/database — changing these
  breaks existing deployments and needs a migration + ops runbook.
- Internal constants (`takmdm_wake_devices`, cert OU `takmdm-device`).

A deeper identifier rename can be scoped as its own chunk if it is ever wanted; it
is not free and it is not cosmetic.

## Repository name

The repo directory is still `TAK-MDM`. Renaming it is optional and out of scope
here — it only affects local checkout paths and the remote slug.
