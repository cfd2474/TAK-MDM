# Project State

Running state file per [CLAUDE.md](CLAUDE.md). Read before starting any step;
update after every completed step.

**Last updated:** 2026-08-30

---

## Current status

**Phase:** Chunk 1 complete. Awaiting review before Chunk 2.

- ✅ Requirements gathered
- ✅ Architecture written → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- ✅ **Chunk 1 complete** — policy stacking engine, 58 tests passing
- ⏸️ **Blocked on approval** to begin Chunk 2

Nothing is committed yet — `main` still has no commits. Review the working tree
before the first commit.

---

## Constraints

| Constraint | Value |
|---|---|
| Management mode | Android **Device Owner** (not managed enterprise / not work profile) |
| App source | Sideloaded APK / XAPK. **No managed Google Play.** |
| Primary hardware | Samsung; full Knox integration intended — see device matrix below |
| OS target | **One UI 8 / Android 16 (API 36)** on both models |
| Connectivity | Intermittent / offline-tolerant — devices dark for hours to days |
| Fleet size | 50-500 devices |
| Scope | Generic MDM core, with TAK/ATAK as a layered policy pack |
| Hosting | Self-hosted on a single server |
| Code style | SOLID (CLAUDE.md §5) |

### Device matrix (confirmed 2026-08-30)

| Model | Device | SoC | ABI | Notes |
|---|---|---|---|---|
| `SM-G736U1` | Galaxy XCover6 Pro (US unlocked) | Snapdragon 778G (Qualcomm) | arm64-v8a | Rugged enterprise line. **Programmable XCover/Top key** — KSP-configurable, natural ATAK PTT binding. POGO dock, removable battery. Shipped Android 12, now on One UI 8. |
| `SM-X828U` | Galaxy Tab S10+ (US carrier) | Dimensity 9300+ (MediaTek) | arm64-v8a | 12.4" WQXGA+, 5G, S Pen, IP68. Shipped Android 14, now on One UI 8. |

Both are Knox-capable enterprise-line devices (KME, KPE, E-FOTA eligible). Single
ABI across the fleet — no ABI-split complexity in the artifact model, though the
mixed Qualcomm/MediaTek SoC vendors mean firmware-level behavior must be verified
on **both** models, never just one.

**External dependency:** Samsung Knox partner/developer application is *pending*.
KME and KPE licensing are gated on it. The AOSP path must be fully functional
without Knox; Knox is strictly additive.

---

## Decisions made

| # | Decision | Rationale |
|---|---|---|
| D1 | Policies are **typed, single-concern, and stackable** via ranked assignments to device / group / tag | The core requirement — matches Hexnode's model, avoids monolithic one-policy-fits-all |
| D2 | Policy versions are **immutable once published** | Required to answer "what was actually on that device in March" during an incident |
| D3 | Merge strategy is declared as **Pydantic field metadata** | Schema *is* the merge contract; the two cannot drift out of sync |
| D4 | **Provenance on every resolved field**, from the first commit | Makes stacking debuggable rather than mysterious; cannot be retrofitted |
| D5 | **Desired-state reconciliation**, not a command stream | A device offline three weeks must converge, not replay a 500-command ordered backlog |
| D6 | Transient one-shots (reboot/lock/wipe/locate) keep a small TTL'd imperative queue | These genuinely are commands, not state |
| D7 | FCM is a **doorbell only**; correctness rests on polling | No hard push dependency given the offline requirement |
| D8 | Artifacts are **content-addressed by sha256**, downloaded direct from object storage with `Range` | Dedupe, integrity, resumable downloads on bad links |
| D9 | Policy bundles are **Ed25519-signed** independent of TLS | Cheap now; enables future LAN-relay / offline delivery with no redesign |
| D10 | Device identity is a **hardware-backed keypair + mTLS client cert**, not a bearer token | No token expiry while a device is dark for a month |
| D11 | Knox via **KSP + `setApplicationRestrictions`** primary, Knox SDK selectively | Reaches Knox breadth *without* managed Google Play — matches the sideload constraint |
| D12 | All OEM code behind an `OemPolicyApplier` interface with an AOSP no-op impl | Highest-risk seam; DIP applied where it actually pays |
| D13 | **XAPK unpacked server-side** into base + splits as separate artifacts | Server can validate package/version/signature at upload; less device CPU and storage |
| D14 | Stack: FastAPI + Postgres/SQLAlchemy 2.0/Alembic + MinIO + Postgres job table | 50-500 devices does not justify Celery or a CDN |

Full rationale in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Chunk plan

### ✅ Chunk 1 — Policy stacking engine (COMPLETE)

Server-side only, fully testable with zero devices.

1. ✅ SQLAlchemy 2.0 models + Alembic scaffolding → [app/db/models.py](app/db/models.py),
   [alembic/](alembic/). `alembic check` reports no drift; upgrade/downgrade round-trips.
2. ✅ Policy type registry with merge strategy declared as Pydantic field metadata →
   [app/policies/registry.py](app/policies/registry.py),
   [app/policies/specs/](app/policies/specs/). Types: `PASSWORD`, `RESTRICTIONS`, `APP_CATALOG`.
3. ✅ Pure resolver → [app/policies/resolver.py](app/policies/resolver.py),
   strategies in [app/policies/strategies.py](app/policies/strategies.py).
4. ✅ 27 resolver tests + 31 API tests → [tests/](tests/). All 58 pass.
5. ✅ REST API → [app/api/routers/](app/api/routers/), including
   `effective-policy`, `explain/{type}/{field}`, and `preview`.
6. ✅ Cache + invalidation + monotonic `state_version` →
   [app/services/effective_policy.py](app/services/effective_policy.py).

**Exit criteria met.** Stacked policies merge correctly, every field traces to its
source, conflicts are reported, and preview diffs a change before publish.

#### Decisions taken during implementation

| # | Decision | Rationale |
|---|---|---|
| D15 | Invalidation marks the cache row **stale** rather than deleting it | The retained payload is the baseline needed to tell a real change from a cosmetic one. Deleting it made every invalidation look like a change — caught by test, see changelog. |
| D16 | A never-computed device baselines at `{}`, not `None` | Otherwise its first read registers as a change and bumps `state_version` spuriously. |
| D17 | `state_version` compares **values only**, excluding provenance | A policy rename changes provenance but nothing the device should act on. |
| D18 | Explicit `null` in a spec is treated as unset | A null must not drag a merged value down to nothing. |
| D19 | Registry raises at import time if a field lacks exactly one `Merge` annotation | Adding a field and forgetting its merge rule would otherwise silently produce a field that never composes. |
| D20 | Archived policies and disabled assignments stop applying but are never deleted | Preserves the history of what a device once had. |

### Later chunks (sketch — to be detailed at approval time)

| # | Chunk | Notes |
|---|---|---|
| 2 | Enrollment + identity | Tokens, CSR → mTLS client cert, QR payload + KME profile generation |
| 3 | Check-in protocol | Desired-state endpoint, signed bundles, TTL'd transient command queue |
| 4 | Artifact store | Content-addressed storage, APK/XAPK upload, server-side split extraction, signature validation |
| 5 | Kotlin agent | Device Owner baseline, reconciler loop, `PackageInstaller`, file push |
| 6 | Knox layer | `OemPolicyApplier`, KSP restriction-bundle generation, KPE licensing, SDK fallbacks |
| 7 | TAK pack | ATAK policy type: data packages, `.pref` files, plugin sets, cert enrollment |
| 8 | Admin UI | Policy builder, stacking view, fleet dashboard |
| 9 | Offline / LAN relay | Only if required — D9 keeps the door open |

---

## Open questions / risks

| # | Item | Status |
|---|---|---|
| R1 | `MANAGE_EXTERNAL_STORAGE` is an app-op, not a runtime permission — `setPermissionGrantState` does not grant it. Blocks arbitrary `/sdcard` writes and OBB placement. Confirmed workaround is `adb shell appops set`, which does not scale. Knox `ApplicationPolicy` may cover it on these devices — **unverified**. | **Open. Validate on real hardware before Chunk 5** — highest-value early experiment. |
| R2 | OBB placement for XAPKs inherits R1 | Open |
| R3 | Knox partner application pending — gates KME and KPE | Tracking; AOSP path must not depend on it |
| R4 | `INTERSECT` on app allowlists is correct but counter-intuitive | Make configurable per policy; show resulting set before publish |
| R5 | Mixed SoC vendors (Qualcomm XCover6 Pro / MediaTek Tab S10+) on One UI 8 | Test every firmware-level behavior on **both** models |
| R6 | **Android 16 Advanced Protection Mode** disables "install unknown apps", blocking sideloading. User-toggleable, and Android Enterprise policy control over it does not arrive until **Android 17**, so it cannot be suppressed by policy on this fleet. Device Owner installs via `PackageInstaller` hold system install privilege and *should* be unaffected — **unverified**. | **Open. Test alongside R1** — if DO install is affected, it invalidates the whole delivery model. |
| Q1 | ~~Which Samsung models / One UI versions?~~ | ✅ **Answered** — see device matrix |
| Q2 | ~~Existing ATAK deployment to integrate with?~~ | ✅ **Answered** — no upstream integration; ATAK server is configured **on the EUD**, so the TAK pack is pure config push (Chunk 7) |

### Retired

- **Minimum installable `targetSdk`** — Android 16 holds at **API 24**, unchanged from
  Android 15 (it did not increment). Normal APKs including ATAK clear this easily.
  Not a blocker; the server should still validate `targetSdk >= 24` at upload so the
  failure is legible there rather than as `INSTALL_FAILED_DEPRECATED_SDK_VERSION` on device.

---

## Changelog

- **2026-08-30** — Requirements gathered; operating envelope decided (offline-tolerant,
  50-500 devices, generic core + TAK pack); architecture written; Chunk 1 planned.
- **2026-08-30** — Device matrix confirmed (XCover6 Pro `SM-G736U1`, Tab S10+
  `SM-X828U`, both One UI 8 / Android 16). Q1 closed. Retired the `targetSdk` concern
  (Android 16 holds at API 24). Added R6 (Advanced Protection Mode) and reframed R5
  around mixed SoC vendors. Corrected the Knox SDK deprecation rationale behind D11.
- **2026-08-30** — Q2 closed: ATAK server is configured on the EUD, no upstream
  integration needed.
- **2026-08-30** — **Chunk 1 complete.** 58 tests passing. Two caching bugs found and
  fixed by the tests before review: (a) invalidation deleted the cache row, destroying
  the baseline that distinguishes a real change from a cosmetic one, so every
  invalidation bumped `state_version` and would have woken the whole fleet on a
  no-op republish; (b) a never-computed device baselined at `None` rather than `{}`,
  so its first read bumped `state_version` spuriously. Both are now D15/D16.
