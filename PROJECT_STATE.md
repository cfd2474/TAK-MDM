# Project State

Running state file per [CLAUDE.md](CLAUDE.md). Read before starting any step;
update after every completed step.

**Last updated:** 2026-08-31

---

## Current status

**Phase:** Chunk 7 admin console complete. **Awaiting first agent run on hardware.**

- ✅ Requirements gathered
- ✅ Architecture written → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- ✅ **Chunk 1 complete** — policy stacking engine
- ✅ **Chunk 2 complete** — enrollment, device PKI, mTLS auth
- ✅ **Chunk 3 complete** — desired-state protocol, signed bundles, command queue
- ✅ **Chunk 4 complete** — content-addressed artifacts, APK/XAPK pipeline,
  resumable device download
- ✅ **Chunk 5 complete** — managed files, marketplace tier, bulk assignment, live
  propagation. **F1–F5 all satisfied server-side.** 200 tests passing.
- 🔨 **Chunk 6 built** — Kotlin Device Owner agent compiles and passes 9 unit tests;
  QR provisioning payloads now generate. **Unproven on hardware.**
- ✅ **Chunk 7 complete** — admin console at http://localhost:8000
- ✅ **Chunk 8 complete** — Authentik forward auth on the admin surface, closing R10
- ✅ **Chunk 9 complete** — any live token's QR can be re-displayed, with optional
  Wi-Fi credentials embedded. 254 tests passing.
- ⏸️ **Next: factory-reset the `SM-X520` and enrol it**, which is the only way to
  validate enrollment, install, file placement, and kiosk. Generate the QR from the
  Enrollment page and watch the device appear on the dashboard.

Chunks 1–3 plus the Docker stack are pushed to `origin/main`.

> **Chunk 5 is unblocked.** R6 and R1 are both retired by production evidence from
> the operator's existing deployments. Build toolchain confirmed present: JDK 17,
> Android SDK with the API 36 (Android 16) platform, build-tools 36.0.0, and `adb` at
> `%LOCALAPPDATA%\Android\Sdk\platform-tools`. The agent can be compiled and
> installed on the test tablet from this machine.

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
| `SM-X520` | Galaxy Tab S10 FE | Exynos 1580 | arm64-v8a | 10.9", S Pen, IP68. Shipped Android 15, **confirmed on One UI 8**. Primary test device. |

All three are Knox-capable enterprise-line devices (KME, KPE, E-FOTA eligible) on
One UI 8. Single ABI across the fleet — no ABI-split complexity in the artifact
model — but **three different SoC vendors** (Qualcomm, MediaTek, Exynos), so
firmware-level behaviour must be verified on each, never extrapolated from one.

### Operator feature requirements (stated 2026-08-31)

Behaviours to replicate, drawn from Hexnode and from commercial platforms in use:

| # | Requirement | Status |
|---|---|---|
| F1 | **Stacked policies per device** — compose several single-concern policies rather than one monolith | ✅ Built (Chunk 1) |
| F2 | **One-to-many assignment, policy-first** — open a policy, then select the devices it applies to | ❌ **Missing.** The API is assignment-centric: one policy to one target per call. Assigning to 50 devices means 50 calls. Needs a bulk `policy → targets` endpoint. |
| F3 | **Immediate propagation** — a policy edit reaches associated devices at once and is applied, including installs and blocklists | ❌ **Missing.** Devices poll on a ~15 min jittered interval, so a change can take that long. Needs a wake mechanism. |
| F4 | **User-selectable file installs from a marketplace app** — the admin curates a repo of files and their destinations; the *end user* chooses from an in-app catalog which ones to install | ❌ **Missing.** Everything today is mandatory desired state. Needs an optional/available tier alongside required, plus reporting of what the user took. |
| F5 | **Admin-controlled zip expansion** — a file entry may be a zip the admin marks for automatic extraction into a designated directory | ✅ Built (Chunk 5) |
| F6 | **Kiosk/launcher is optional, never the default** — the agent stays out of the way unless a policy asks for lockdown | ✅ Already modelled: `APP_CATALOG.kiosk_package` set means kiosk, unset means a background agent. Agent side lands in Chunk 6. |

F3 is the one that changes an existing decision. D7 made push a latency optimization
and never a correctness dependency; F3 makes low latency a product requirement. The
resolution is not to abandon D7 — polling stays the correctness floor for a fleet
that goes dark — but to add a best-effort wake channel on top of it.

F4 introduces a genuinely new concept: state the server *offers* rather than
*requires*. The desired-state model so far has been strictly mandatory, so
"available" items and a record of which the user accepted are both new.

### Evaluated: forking Headwind MDM as the project base (2026-08-31)

**Decision: no. Keep this server, write our own agent, mine Headwind as reference.**

Licensing was not the obstacle — the Community Edition is **Apache licensed**, so
borrowing code is legally clean (note the open-core caveat: Enterprise customers get
additional agent source in a private repository, so the public agent may not be
everything the commercial product ships).

Two architectural mismatches decided it, both on points the operator named as
requirements:

1. **Headwind applies one configuration per device group** — every device in a group
   retrieves the same configuration. That is precisely the "one policy fits all"
   model this project exists to replace (F1). Adopting it would mean gutting its core
   data model to fit stacked, ranked, per-field-merged policies, inside an unfamiliar
   Java/Tomcat/AngularJS codebase, against a moving upstream. Harder than building it.
2. **Their agent is a launcher** — owning the home screen is its central assumption.
   The operator wants kiosk available but *not* default (F6). Subtracting launcher
   behaviour from a launcher is a fight; adding kiosk to a background agent is a
   policy flag and two Android API calls.

Worth stating plainly: had the policy model matched, the right call would have been
to discard this server and adopt theirs. It doesn't, and sunk cost played no part.

#### Source review of `h-mdm/hmdm-android` (2026-08-31)

Cloned and read before committing to Chunk 6. It **corrected an earlier claim of
mine**: I had said the repo was worth mining for Knox and lockdown code. It is not —
those are not in the public repository.

| Finding | Detail |
|---|---|
| Licence | Apache 2.0 confirmed, in-tree |
| Language | 112 Java files, zero Kotlin |
| **Knox** | **Absent.** Two matches for "samsung" across the whole tree, both unrelated UI comments. No Knox SDK dependency, no `libs/`. |
| **Kiosk** | **Pro-gated.** `com.hmdm.launcher.pro.ProUtils` is a stub class: `isPro()` returns `false`, `kioskModeRequired()` returns `false`, header comment reads "In a free version, the class contains stubs". |
| SDK target | `targetSdkVersion 34`, `compileSdk 34` — not yet targeting Android 15/16 |
| Push | Eclipse Paho MQTT, i.e. a persistent broker connection rather than long-poll |
| Provisioning | `SystemUtils` writes `/data/system/device_owner_2.xml` and `device_policies.xml` directly — a **rooted or platform-signed** path, not a normal Device Owner one |

**R1, refined by real code.** Their automatic grant of `MANAGE_EXTERNAL_STORAGE`
(`SystemUtils.autoSetPermission`, app-op 92) reflects into
`AppOpsManager.setMode`, which needs `MANAGE_APP_OPS_MODES` — a
`signature|privileged` permission. Combined with the direct `/data/system` writes in
the same class, that whole path is for system-app or platform-signed builds. It is
**not available to a normally-installed Device Owner**, so it confirms the R1
analysis rather than dissolving it. Their ordinary path is
`Environment.isExternalStorageManager()` plus a one-time user grant — exactly the
fallback already planned.

**A real gotcha worth the whole exercise** (`Utils.getRuntimePermissions`): on
Android 11+, if a Device Owner pre-grants `WRITE_EXTERNAL_STORAGE` to an app, that
app is then **locked out of requesting `MANAGE_EXTERNAL_STORAGE`**. Their workaround
is to detect that an app declares `MANAGE_EXTERNAL_STORAGE` and deliberately *skip*
granting the legacy storage permissions to it. Our agent must do the same when
auto-granting permissions, or every all-files-access app we deploy — ATAK included —
silently loses the ability to ask for it. See R9.

### Prior art and design intent

The operator already runs **commercial MDM platforms and Headwind MDM in production
on this hardware**, installing apps successfully. The goal for this project is to
blend the behaviours worth keeping from each into one system: Hexnode's stackable
policy model, Headwind's provisioning and silent-install approach, and file/app
deployment without managed Google Play.

Following Headwind's provisioning method is therefore a deliberate choice, not just
a convergent one — it is a known-good path on these exact devices. Headwind is also
a Samsung Knox partner, which independently supports the Knox-forward direction in
D11.

**External dependency:** Samsung Knox partner/developer application is *pending*.
KME and KPE licensing are gated on it. The AOSP path must be fully functional
without Knox; Knox is strictly additive.

---

## Operational notes — read before debugging anything "impossible"

Traps that have each cost real time in this project. When a change appears to have
no effect, check this list before investigating the code.

### Docker: `up -d` alone is usually not enough

| Changed | Required command | Why |
|---|---|---|
| **Any Python source** | `docker compose up -d --build` | The source is `COPY`'d into the image at build time. Plain `up -d` restarts the container with the **old image**, so the change silently does not exist. |
| **`docker/nginx/*.conf`** | `docker compose restart proxy` | The file is bind-mounted, so the container's config is unchanged and Compose sees no reason to recreate it. nginx reads its configuration once, at startup. |
| **`pki/server.crt`** (e.g. after `scripts/setup_for_tablet.py`) | `docker compose restart proxy` | Same reason: nginx loads certificates at startup and keeps serving the old one. |
| **`.env`** | `docker compose up -d` | Environment variables are container config, so Compose does recreate. No rebuild needed. |

The failure mode is identical in all three cases and deeply misleading: the code is
correct, the test is correct, and the result is wrong. **Default to
`docker compose up -d --build`**, and restart `proxy` explicitly whenever anything
under `docker/nginx/` or `pki/` changes.

### Android build

* **`JAVA_HOME` must be JDK 17**: `C:\Program Files\Microsoft\jdk-17.0.20.8-hotspot`.
  Android Studio's bundled JBR is JDK 25, which Gradle 8.13 refuses — and it reports
  the failure as the bare string `25.0.2`, which explains nothing.
* Build: `cd agent && .\gradlew.bat assembleDebug` (`testDebugUnitTest` for tests).
* `adb` is not on `PATH`; it lives at
  `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe`.

### Shell

* The working directory **persists between tool calls and drifts across
  Bash/PowerShell**. A `cd` in one call silently relocates the next. Use absolute
  paths, or `Set-Location` explicitly at the top of each command.
* Raw control characters in source files defeat exact-match editing. Use escapes
  (`'\u000C'`) rather than literal bytes.

### Alembic

* Autogenerate emits bare `Text()` and `app.db.base.UtcDateTime` **without importing
  either**. `alembic/script.py.mako` now pre-imports both (D35), but check the
  generated file.
* Autogenerate never infers `server_default`, so a new `NOT NULL` column **fails on
  Postgres against a table that already has rows**. Add it by hand and verify by
  migrating a seeded database, not an empty one.
* The test suite runs on SQLite; Postgres-only failures surface solely in the
  container. Always run `alembic upgrade head` against the real stack too.

### Tests

* Test settings are built with `_env_file=None` (D60). The suite once read the
  developer's `.env` and broke when a real value was set locally. Keep it hermetic.

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

### Branding (2026-08-31)

| # | Decision | Rationale |
|---|---|---|
| D61 | Project is named **ATLAS — ATAK Tactical Lifecycle & Administration System**, developed by **TAK-Solutions LLC** (authorship / attribution / copyright). Product family reserved: ATLAS Console / Agent / Fleet / Provisioning. | Gives the system an identity and room to name components as they grow. See [docs/BRANDING.md](docs/BRANDING.md). |
| D63 | Licensed **Apache 2.0**, `Copyright 2026 TAK-Solutions LLC`. `LICENSE` + `NOTICE` at repo root; `FastAPI` `license_info` set; full boilerplate header on every `.py` / `.kt` / `.gradle.kts` source file (87 files) and the Alembic `script.py.mako` so generated migrations inherit it. New source files must carry the header. | Permissive, patent-grant, and the licence the operator's reference projects (Headwind CE, hmdm-android) already use — clean for mining and being mined. |
| D62 | The rename touches **user-facing surfaces only** — README, FastAPI/OpenAPI metadata, CLI help, architecture docs. Code identifiers (`org.takmdm.agent`, `TAKMDM_` env prefix, `takmdm` DB role, cert OU, internal constants) are left unchanged. | The agent package name is load-bearing for QR provisioning payloads and signature-checksum pinning (D53–D60); the env prefix and DB names are baked into deployments. A deeper identifier rename is its own chunk if ever wanted — not cosmetic, not free. |

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

### ✅ Chunk 2 — Enrollment and device identity (COMPLETE)

Turns an anonymous factory-reset tablet into a device the server can recognise
cryptographically, and lands it in the right policy stack from Chunk 1 on arrival.

1. **Enrollment tokens** — model + service. Secret stored hashed, with TTL, max
   uses, and revocation. Scoped to groups/tags so an enrolling device inherits its
   policy stack immediately rather than needing a second manual step.
2. **Internal CA** — generate or load an EC P-256 root; sign device CSRs. EC because
   Android Keystore and Samsung StrongBox handle it natively.
3. **Enrollment endpoint** — token + CSR + device attributes → device record, signed
   client certificate, CA chain, and server config.
4. **mTLS device authentication** — a dependency that verifies the proxy-forwarded
   client certificate against our CA (chain, validity window, revocation) and
   resolves it to a `Device`.
5. **Provisioning payloads** — QR JSON for Device Owner setup-wizard enrollment, and
   a Knox Mobile Enrollment profile payload.
6. **Authenticated check-in stub** — returns `state_version`, proving the Chunk 1
   policy engine and Chunk 2 identity connect. The full desired-state protocol is
   Chunk 3.
7. **Tests** — token lifecycle, CSR signing, re-enrollment, revocation, auth rejection.

**Exit criteria met.** A device presenting a valid enrollment token and a CSR
receives a client certificate, lands in its assigned groups/tags with its policy
stack already resolved, and authenticates a check-in by mTLS.

Delivered: [app/security/ca.py](app/security/ca.py),
[app/services/enrollment.py](app/services/enrollment.py),
[app/services/provisioning.py](app/services/provisioning.py),
[app/api/routers/enrollment.py](app/api/routers/enrollment.py),
[app/api/routers/checkin.py](app/api/routers/checkin.py), mTLS dependency in
[app/api/deps.py](app/api/deps.py). 86 tests passing.

#### Decisions taken during implementation

| # | Decision | Rationale |
|---|---|---|
| D21 | ~~Enrollment token stored as SHA-256 hash only~~ | ⚠️ **Partially reversed by D74.** The hash remains and is still the only thing authentication reads; a recoverable copy was added alongside it so a token's QR can be re-displayed. |
| D22 | EC P-256 throughout, RSA CSRs rejected | Native to Android Keystore and StrongBox, and far cheaper on the handshake every check-in performs. |
| D23 | The CSR's subject is discarded; the server builds the certificate subject itself | A CSR's subject is attacker-controlled. Only the public key is taken, after verifying the CSR signature for proof of possession. |
| D24 | Re-enrollment matches on **serial number** and re-adopts the existing device row | A wipe plus KME re-enroll is routine. A second row would orphan the device's history and silently drop the group membership driving its policy stack. Prior certificates are revoked on re-enroll. |
| D25 | Revocation is a `revoked_at` column checked during auth, not a CRL or OCSP responder | At 50-500 devices a database check is simpler to operate and strictly more current than a periodically published list. |
| D26 | Token group/tag scoping is **additive**, never replacing membership | Enrolling with a second token should add to a device's stack, not silently reset it. |
| D27 | `UtcDateTime` type decorator normalizes all timestamps to aware UTC | Postgres returns aware datetimes, SQLite naive ones; comparing them raises. Fixing it in the type removes a dialect-dependent landmine from every expiry check. |

#### Deployment prerequisite

mTLS terminates at the **reverse proxy**, which forwards the verified certificate in
`x-ssl-client-cert`. The app independently re-verifies issuer, signature, validity
window, and revocation — but possession of the private key is proven only by the TLS
handshake at the proxy. **That proxy must strip the header from inbound requests, and
the app must never be exposed directly.** Not yet enforced in code; see R7.

### ✅ Chunk 3 — Desired-state check-in protocol (COMPLETE)

The piece that makes the offline story real. A device dark for three weeks wakes,
receives one declarative desired state, and converges — rather than replaying an
ordered backlog it cannot safely reorder.

1. **Desired-state document** — a device-facing projection of the effective policy,
   stripped of provenance and conflicts. Admins get the "why"; devices get only what
   they must act on.
2. **Ed25519 bundle signing** — a signing key separate from the device CA, with
   canonical JSON serialization so the signature is reproducible byte-for-byte. The
   agent receives the public key at enrollment. Cheap now, and it is what makes a
   future LAN-relay or sneakernet delivery path possible without redesign (D9).
3. **Transient command queue** — `REBOOT`, `LOCK`, `WIPE`, `LOCATE`, `SCREENSHOT`,
   `CLEAR_APP_DATA`. Each with a TTL, delivered at-least-once and idempotent, expired
   rather than delivered when stale.
4. **Full check-in endpoint** — device sends its `state_version` and results; server
   returns the desired state **only when it has changed**, plus live commands and a
   jittered next-check-in hint to avoid a thundering herd.
5. **Convergence reporting** — devices report the version they actually applied and
   any failures. `Device.acked_state_version` separates "the server has v7" from
   "the device is running v7", which is the distinction a fleet dashboard lives on.
6. **Admin endpoints** — enqueue and inspect commands, view a device's desired state
   and convergence status.
7. **Tests.**

**Exit criteria met.** All of it, with 121 tests passing.

Delivered: [app/security/bundle.py](app/security/bundle.py),
[app/services/desired_state.py](app/services/desired_state.py),
[app/services/commands.py](app/services/commands.py),
[app/api/routers/checkin.py](app/api/routers/checkin.py),
[app/api/routers/commands.py](app/api/routers/commands.py).

#### Decisions taken during implementation

| # | Decision | Rationale |
|---|---|---|
| D28 | `Device.acked_state_version` is tracked separately from `state_version` | "The server has v7" and "the device is running v7" are different claims. Conflating them is how a console reports compliance it never verified. The gap between them *is* the fleet's convergence lag. |
| D29 | The signed bundle contains **no timestamp or nonce** — it is deterministic per `(device, state_version)` | Because `state_version` moves exactly when values move (D17), the same version always yields byte-identical JSON and the same signature. That makes a bundle a cacheable, relayable artifact, which is the entire point of signing independently of TLS (D9). Per-response data lives in the envelope. |
| D30 | The desired state is a **projection**: values only, no provenance, no policy names, no conflicts | Admins need the "why"; devices do not. Shipping it would put the fleet's policy structure and group topology on every tablet, including any that gets lost. |
| D31 | Commands are delivered **at-least-once** and must be idempotent; staleness is enforced **on read** | A device that dies mid-execution must get the command again — at-most-once silently drops actions on exactly the intermittent links this design exists for. Expiring on read means no window where a device collects a command the console already considers dead. |
| D32 | TTL defaults vary by command type | A `LOCATE` from three weeks ago answers a question nobody is still asking (6h); a `WIPE` on a lost device stays worth executing as long as it might reappear (30d). |
| D33 | The bundle signing key is separate from the device CA key | Different job, different blast radius, different rotation cadence. Rotating the bundle key re-signs bundles; rotating the CA key invalidates every device identity. |
| D34 | Command results are matched against `(device_id, command_id)`, never the id alone | Otherwise one enrolled device could acknowledge — and thereby cancel — another device's pending wipe. |
| D35 | `alembic/script.py.mako` pre-imports `Text` and `app.db.base`; new NOT NULL columns need an explicit `server_default` | Autogenerate emits both bare `Text()` and `app.db.base.UtcDateTime` without importing them, and infers no server default from a Python-side default — so a generated migration would `NameError`, or fail on Postgres against a table that already has rows. Verified by migrating a seeded database. |

#### Deferred

FCM push is **not implemented**. Devices poll on a jittered ~15 min interval, which
is correct but means a command waits up to that long. FCM was always specified as a
latency optimization only (D7), never a correctness dependency — adding it later
changes no protocol, only how quickly a device notices.

### ✅ Chunk 4 — Artifact store and APK pipeline (COMPLETE)

Everything a device downloads, addressed by content hash. The server understands
what it is being handed rather than trusting the uploader's word for it.

1. **Content-addressed storage** — sha256-keyed blobs behind a storage interface,
   with a sharded local-filesystem backend. S3/MinIO slots in behind the same
   interface later without touching callers.
2. **Binary manifest (AXML) parser** — Android's `AndroidManifest.xml` is compiled
   binary XML, so package name, version code, and SDK levels cannot be read without
   decoding it. Resource-id fallback for APKs whose attribute name strings are empty.
3. **Signature extraction** — APK Signing Block v2/v3, falling back to the v1
   PKCS#7 block in `META-INF`. Modern APKs are frequently v2-only, so v1-only
   parsing would fail on exactly the builds we care about.
4. **Upload pipeline** — inspect, then **unpack XAPK/APKS server-side** into base +
   splits + OBB as separate content-addressed artifacts (D13), so the device opens
   one `PackageInstaller` session and writes parts it already has hashes for.
5. **Models and admin API** — packages, versions, files; upload, list, delete.
   **Signature pinning enforced at upload**: a new version whose signing certificate
   differs from the installed one *will* fail on device, so reject it here where the
   error is legible.
6. **Device-facing download** — mTLS, `Range` support for resumable transfer over
   bad links, and desired-state integration so a required app carries the hashes and
   sizes the agent needs to fetch and verify.
7. **Tests** — including a synthetic APK builder (real AXML, real v2 signing block)
   so the parsers are tested against actual binary structures.

**Exit criteria:** an APK or XAPK can be uploaded, is correctly identified, has its
signing certificate extracted, is stored content-addressed with splits separated,
is rejected if it would break signature pinning, and can be resumably downloaded by
an enrolled device that found it in its desired state.

**Exit criteria met**, with 168 tests passing and a full end-to-end run against the
Docker stack: an XAPK uploaded, unpacked into base + split + OBB, resolved into a
device's desired state, and downloaded over mTLS via interrupted-then-resumed range
requests with every hash verifying.

Delivered: [app/artifacts/](app/artifacts/) (storage, `axml`, `apk`, `bundles`),
[app/services/packages.py](app/services/packages.py),
[app/api/routers/packages.py](app/api/routers/packages.py),
[app/api/routers/artifacts.py](app/api/routers/artifacts.py),
[tests/apk_fixtures.py](tests/apk_fixtures.py).

**Bonus delivered:** the v2 signing certificate hash *is*
`PROVISIONING_DEVICE_ADMIN_SIGNATURE_CHECKSUM`, base64url-encoded. Uploading the
agent APK now returns it directly, unblocking the QR provisioning payloads that were
withheld in Chunk 2. Set it as `TAKMDM_AGENT_SIGNATURE_CHECKSUM` once the agent
exists (Chunk 5).

#### Decisions taken during implementation

| # | Decision | Rationale |
|---|---|---|
| D36 | AXML and signing-block parsers written by hand rather than depending on androguard | androguard is a large malware-analysis framework; this needs a few hundred lines of well-specified format handling. Tested against synthetic APKs built with real binary structures, not mocks. |
| D37 | Signature extraction tries **v2/v3 before v1** | Apps targeting modern SDK levels are routinely signed v2-only with no `META-INF` block at all, so a v1-first (or v1-only) implementation fails on exactly the builds this fleet cares about. |
| D38 | `state_version` tracks resolved **apps** as well as policy values | Uploading a new build changes what a device must do without changing a single word of policy. Comparing values alone would leave the fleet on the old version indefinitely. |
| D39 | A catalog change invalidates **every** device's cache | Working out precisely which devices reference a package means re-resolving every stacked policy. A blanket flag is cheaper at this fleet size and cannot miss one — and costs nothing spurious, since the recompute only bumps `state_version` where the resolved state actually moved. |
| D40 | Splits are classified by the manifest's `split` attribute, never by filename | Archives whose parts were renamed would otherwise be misclassified, and the base APK picked at random. |
| D41 | Artifact download is authorized by **enrollment**, not per-device | The digest is unguessable and the content is something an operator chose to publish. Scoping per device would also defeat the deduplication the store is built on. |
| D42 | Artifact deletion is reference-counted across versions | Two versions sharing an unchanged OBB must not have it deleted out from under one of them. |
| D43 | `refresh` returns the stored payload, not the resolver's object | Found by test: the resolver knows nothing about resolved apps, so returning its object silently dropped them on any cache miss. |

### ✅ Chunk 5 — Managed files, marketplace, bulk assignment, live propagation (COMPLETE)

Closes F2–F5. Deliberately ordered **before** the agent: the optional-items tier and
zip extraction change the agent's core data model rather than its edges, so building
the agent first would mean writing its reconciler and marketplace twice.

1. **Generic file upload** — arbitrary artifacts (zips, `.pref`, certs, map sources)
   into the content-addressed store, with a `ManagedFile` catalog entry. Distinct
   from the APK pipeline, which inspects and validates Android-specific structure.
2. **`FILES` policy type** — entries binding a managed file to a destination, marked
   `required` or `optional`, with admin-controlled zip extraction (F5) and an
   overwrite rule. Merged by file id so stacked policies compose.
3. **Desired-state resolution** — required files and an `available` catalogue, each
   carrying hash, size, URL, destination, and extraction instructions.
4. **User selections (F4)** — devices report which optional items they applied;
   the server records them per device so an admin can see what was actually taken.
5. **Bulk assignment (F2)** — policy-first `PUT /policies/{id}/targets`: open a
   policy, select many devices, groups, or tags in one call.
6. **Live propagation (F3)** — an in-process change bus plus an async long-poll
   `GET /api/v1/device/wait`, released the moment that device's state is
   invalidated or a command is queued. Wired in through a SQLAlchemy `after_commit`
   hook so no write path can forget to wake its devices. Polling remains the
   correctness floor (D7 stands); this is a doorbell on top of it.
7. **Tests.**

**Exit criteria met**, with 200 tests passing and an end-to-end run against the
Docker stack doing exactly that sequence. Measured wake latency through nginx with a
real mTLS client: **18 ms** from bulk assignment to the device being released.

F1–F5 are now all satisfied server-side.

Delivered: [app/policies/specs/files.py](app/policies/specs/files.py),
[app/services/files.py](app/services/files.py),
[app/services/notifications.py](app/services/notifications.py),
[app/api/routers/files.py](app/api/routers/files.py),
[app/api/routers/wait.py](app/api/routers/wait.py), bulk targets endpoint in
[app/api/routers/assignments.py](app/api/routers/assignments.py).

#### Decisions taken during implementation

| # | Decision | Rationale |
|---|---|---|
| D44 | The wake is queued inside `invalidate()` and fired from a SQLAlchemy `after_commit` hook | A write path cannot invalidate without waking, and cannot wake before the data it describes is durable. Putting the call in each router would have made both mistakes possible. |
| D45 | The wake is a **contentless doorbell** — "check in now", not what changed | A missed wake then costs latency and nothing else. Carrying state would make delivery load-bearing and quietly undo D7's guarantee that polling is the correctness floor. |
| D46 | `/device/wait` is `async` and releases its DB session before parking | A parked request must hold neither a worker thread nor a pooled connection; a few hundred waiting tablets would exhaust both. |
| D47 | No second database read after waking | The version in the wake response is advisory; the check-in that follows establishes it. Re-reading meant either holding a connection across the park or reaching around dependency injection for a new engine — which is exactly the bug the tests caught. |
| D48 | Required and optional files are split **server-side** into two lists | Keeps the "offer vs require" distinction out of the agent's parsing, where getting it wrong would silently install something the user declined. |
| D49 | A device's selection report replaces the stored set rather than appending | The device is authoritative about what it actually has. Appending would leave a record claiming an item is installed after the user removed it. |
| D50 | `extract_to` defaults to `dest_path` **and is marked explicitly set** | Making the admin repeat the path invites a mismatch. Marking it set is essential: `exclude_unset` persistence would otherwise drop the derived value and ship `extract_to: null` to the device. Found by test. |
| D51 | Bulk assignment `mode="replace"` describes the policy's complete target set, removals included | Otherwise unassigning needs a second pass and the two can drift. `mode="add"` stays available for purely additive rollouts. |
| D52 | Waiters live in one process | Correct for a single uvicorn worker, which is ample at 50-500 devices. Scaling out needs the notification fanned through Redis or Postgres `LISTEN/NOTIFY`. Documented rather than pre-built. |

### ▶ Chunk 6 — Kotlin Device Owner agent (IN PROGRESS)

Implements the contract Chunks 1–5 defined. Built from scratch rather than forked,
for the reasons recorded above.

1. **Gradle scaffolding** — `agent/` module, `MdmDeviceAdminReceiver`, manifest.
   `minSdk 33` so `Ed25519` is available from the platform provider rather than
   bundling BouncyCastle; every device in the fleet is on Android 16, and a
   fleet-specific Device Owner agent has no reason to support ancient hardware.
2. **Identity** — read provisioning extras, generate an EC P-256 key in the Android
   Keystore (StrongBox where present), submit a CSR, install the returned chain
   against the same alias, and build an mTLS OkHttp client from it.
3. **Sync loop** — foreground service holding the long-poll doorbell, with a
   WorkManager periodic check-in as the guaranteed floor. Bundle signature verified
   against the pinned Ed25519 key over an independently implemented canonical JSON.
4. **Reconciler** — diff desired state against reality, converge, report. Resumable
   content-addressed downloads with hash verification before anything is applied.
5. **Appliers** — `DevicePolicyManager` for passcode and restrictions; permission
   pre-granting that **skips legacy storage permissions for apps declaring
   all-files access (R9)**; kiosk via lock-task *only* when `kiosk_package` is set
   (F6). Knox behind `OemPolicyApplier` with an AOSP no-op implementation.
6. **File deployment and marketplace** — required files placed and archives
   extracted per policy; optional files offered in a simple in-app catalogue with
   selections reported at check-in (F4).
7. **Build, install on the Tab S10 FE, and verify** against the running server.

**Status: built, compiles, unit-tested. NOT yet run on hardware.**

Done: the APK builds (21.5 MB, `org.takmdm.agent`, minSdk 33 / targetSdk 36), nine
agent unit tests pass, and QR provisioning payloads now generate complete and
verified. **Outstanding: nothing has run on a physical device.** Enrollment,
install, file placement, and kiosk are written but unproven, and that requires a
factory-reset tablet.

#### Verified along the way

* **Canonical JSON matches the server byte for byte.** The agent's encoder is
  independent of the server's; the test expectations were generated by running the
  Python implementation, so a divergence fails in CI rather than as unexplained
  signature failures on tablets.
* **The Chunk 4 APK parser agrees with Google's `apksigner`.** Uploading the agent
  produced signing hash `879405…580e`, identical to what `apksigner` reports —
  independent validation of the hand-written v2 signing-block parser.
* **QR provisioning is unblocked.** The upload's `provisioning_checksum`
  (`h5QFWJTb…PzWA4`) is exactly what Android verifies against, closing the gap left
  open in Chunk 2. A generated payload carries server URL, token, TLS CA, and a
  download URL serving the exact bytes that were built.

#### Decisions taken during implementation

| # | Decision | Rationale |
|---|---|---|
| D53 | `minSdk 33` | Puts `Ed25519` in the platform provider instead of bundling BouncyCastle for it. Every device in the fleet is on Android 16; a fleet-specific Device Owner agent has no reason to carry ancient-device support. |
| D54 | BouncyCastle included anyway, for PKCS#10 only | Android has no public CSR builder, and hand-rolling DER for a security-critical structure is not worth the saved megabyte. Android's own copy is namespaced `com.android.org.bouncycastle`, so there is no collision. |
| D55 | The agent declares no `category.HOME` | Not a launcher (F6). Kiosk engages only when a policy sets `kiosk_package`, via `setLockTaskPackages`. Adding kiosk to a background agent is two API calls; subtracting launcher from a launcher is a rewrite. |
| D56 | StrongBox attempted, TEE fallback on failure | StrongBox is a separate chip and not on every model. The fallback is deliberate and logged — never a silent drop to a software-backed key. |
| D57 | A custom `X509KeyManager` rather than `KeyManagerFactory` | The private key is non-exportable and lives in the AndroidKeystore provider, which the default factories do not reliably handle. |
| D58 | `/api/v1/provisioning/agent.apk` is **unauthenticated** | Android's setup wizard downloads it before the device has any identity, so mTLS is impossible there by definition. Exposure is the agent binary every managed device gets anyway, and Android verifies it against the signature checksum, so a substituted APK is rejected by the device. |
| D59 | `server_ca_pem` travels in the provisioning extras | A self-signed development server cannot otherwise be trusted by the agent, and provisioning happens long before it could be told separately. Omitted automatically when no local certificate exists. |
| D60 | Test settings are built with `_env_file=None` | The suite was reading the developer's `.env`; setting a real agent checksum locally broke a test asserting behaviour when none is configured. Tests must describe the code, not the workstation. |

### ✅ Chunk 7 — Admin portal (COMPLETE)

Moved ahead of the hardware test, deliberately. Everything demonstrated so far was
verified by scripts whose output the operator had to take on trust; a portal is how
they check the work rather than believe it. Watching a device appear during
enrollment is also far more useful than reading a terminal.

Server-rendered Jinja templates inside the existing FastAPI app: no Node, no build
step, no extra container. `docker compose up` and it is there.

1. **Chassis** — Jinja setup, base layout, plain CSS, device list for navigation.
2. **Enrollment and QR** — create a token scoped to groups/tags, render a scannable
   QR on screen instead of JSON in a terminal.
3. **Policy stacking view** — for one device: every policy reaching it in rank
   order, the resolved effective policy, and per-field provenance. The
   differentiating feature made visible.
4. **Policy editor** — create, publish new versions, archive; spec edited as JSON
   beside a live reference of each field's type and merge strategy from the registry.
5. **Bulk assignment (F2)** — pick a policy, select many devices/groups/tags, apply.
6. **Harden the edge** — nginx must stop proxying admin routes. Adding a UI to a
   path already reachable at `:8443` would publish an unauthenticated console to the
   LAN. Only device-facing endpoints stay exposed.
7. **Tests.**

**Exit criteria met**, with 222 tests passing. Console at
**http://localhost:8000** — devices, policy editor with live merge-strategy
reference, bulk assignment, scannable enrollment QR, and a stacking view naming the
winning policy, the strategy that chose each value, and what it overrode.

#### Decisions taken during implementation

| # | Decision | Rationale |
|---|---|---|
| D61 | Server-rendered Jinja inside the existing app | No Node, no build step, no second container. The console ships with `docker compose up` and stays readable by anyone who can read the Python. |
| D62 | **nginx now default-denies and opts back in** | The console lives at `/` on the same application already proxied at `:8443`, so adding it silently published an unauthenticated admin surface to the LAN. Verified: every admin path returns 403 on the device port while `/api/v1/device/`, `/api/v1/enroll`, the agent APK, and `/healthz` still work. |
| D63 | Admin routes are excluded from the OpenAPI schema | They are a human surface, not an API. Listing them invites treating them as one. |
| D64 | Policy specs are edited as JSON beside a generated merge-strategy reference | A form generated from each type's schema would be prettier and would hide the thing that matters — that `min_length` merges by `MAX` and `allowed_packages` by `INTERSECT`. Operators need to predict stacking, so the reference is the feature. |
| D65 | QR codes render as inline SVG | No image library, no external requests. The console may well run on an isolated network. |
| D66 | The console shows a standing "no authentication" banner | It is the only thing between this and an open admin surface until SSO exists (R10). |

### ✅ Chunk 8 — Authentik OIDC for the admin surface (COMPLETE)

Closes R10. The operator runs Authentik, and the console is to sit behind it,
restricted to admin users.

**Integration shape: forward auth, not a native OIDC client.** "Behind Authentik"
means an Authentik proxy provider terminates the login flow and forwards identity
headers; the application reads them. That keeps the entire OIDC dance — discovery,
PKCE, token exchange, refresh, session cookies — out of this codebase, where it
would be a large amount of security-critical code duplicating a solved problem.

The trust model is identical to the mTLS one already in place: the proxy is
authoritative, the proxy must strip inbound copies of the headers, and the app must
never be directly reachable. That discipline already exists and is already tested,
so this reuses it rather than inventing a second one. A native OIDC client stays
possible later behind the same interface if the app ever needs to stand alone.

**The device surface stays untouched.** Devices cannot perform an interactive login,
so `:8443` keeps mTLS with no Authentik in the path. The nginx split built in
Chunk 7 is what makes this separation clean.

1. **Identity model** — `AdminIdentity` (username, email, display name, groups) and
   an `admin_required` dependency.
2. **Forward-auth mode** — read Authentik's headers, require membership of a
   configured admin group, **fail closed** when enabled and headers are absent.
3. **Explicit modes** — `disabled` for local development (loud startup warning) and
   `forward_auth` for deployment. No silent middle ground.
4. **Apply to every admin route** — split the enrollment router so device-facing
   `/enroll` and the agent APK stay open while token administration is protected.
5. **Attribution** — record who published a policy version and who minted an
   enrollment token, now that there is an identity to record.
6. **Deployment config** — an nginx admin server block using `auth_request` against
   an Authentik outpost, plus documentation for wiring it to an existing instance.
   Authentik itself is not bundled: it is a multi-service stack of its own.
7. **Tests.**

**Exit criteria met**, with 246 tests passing and verified live against the
container in both modes:

```
forward_auth        /  /policies  /api/v1/*      no headers  → 401
                    /api/v1/devices              wrong group → 403
                    /                            admin       → 200, names the user
device surface      agent.apk, mTLS check-in                 → 200 (unaffected)
```

#### Decisions taken during implementation

| # | Decision | Rationale |
|---|---|---|
| D67 | **Forward auth, not a native OIDC client** | Discovery, PKCE, token exchange, refresh and session handling are a large amount of security-critical code solving a problem Authentik already solves. The trust model is identical to the mTLS one already in place, so both surfaces share one discipline instead of inventing a second. |
| D68 | Exactly two modes: `disabled` and `forward_auth` | "Is the console protected right now?" must have a yes/no answer. A partial mode is one nobody can reason about. |
| D69 | **Fail closed** when enabled and the header is absent | Treating a missing header as anonymous would make a misconfigured proxy silently equivalent to no protection. |
| D70 | The guard is applied at **router registration**, not per endpoint | A new admin route is protected by default; forgetting a decorator cannot quietly expose one. |
| D71 | The enrollment router is **split** into admin and device halves | `/enroll` and the agent APK must stay open — a tablet in its setup wizard cannot perform an interactive login. Separate routers make that boundary structural rather than a per-endpoint detail. |
| D72 | Attribution columns are **nullable** | Versions published before authentication existed genuinely have no author. An honest gap in the audit trail beats a fabricated name. |
| D73 | A loud startup warning when auth is disabled | Silence is how a console ends up open. The UI banner disappears once auth is on, so it does not train operators to ignore it. |

**Deployment:** [docker/nginx/admin.conf.example](docker/nginx/admin.conf.example)
carries the `auth_request` server block for an Authentik outpost on a **separate
admin port**, keeping humans and devices on different front doors. Authentik itself
is not bundled — it is a multi-service stack of its own, and the operator already
runs one.

### ✅ Chunk 9 — Re-displayable QR codes with Wi-Fi (COMPLETE)

Operator request: pull up the QR for any previous token, and embed Wi-Fi
credentials into it. 254 tests passing, verified live.

#### Decisions taken during implementation

| # | Decision | Rationale |
|---|---|---|
| D74 | **Token secrets are now recoverable**, encrypted with a key in `pki/` — a deliberate, bounded reversal of D21 | Re-displaying a QR requires recovering the secret, so one-way storage was no longer possible. Bounded three ways: the key never touches the database, so a dump alone still yields nothing and **two** things must leak; the SHA-256 hash is kept and remains the only thing authentication reads, so enrollment matches an indexed hash and never decrypts; and only enrollment tokens are stored this way — already scoped, expiring and use-limited, a far smaller blast radius than the CA key beside them. The alternative was operators saving secrets elsewhere, which in practice means photographing the QR — worse than ciphertext behind a key file. |
| D75 | **Wi-Fi credentials are never persisted** | Used for one render only. Storing them would put a live Wi-Fi password in the database as a second recoverable secret, and the tablet needs it exactly once, to reach the server during provisioning. |
| D76 | The QR is **refused** for a revoked, expired, or used-up token | Handing someone a scannable code that cannot enrol costs them a factory reset before they discover it. The page says which of the three it is. |
| D77 | Creating a token redirects to its QR page | One place renders QR codes whether the token was made a second ago or last week, so there is no "you should have saved it" path through the UI. |
| D78 | `TokenVault.open()` returns `None` rather than raising | Two cases are expected in normal operation — a token predating the vault, and one sealed under a replaced key. Neither is an error; the page simply says a QR cannot be offered. |

### Later chunks (sketch — to be detailed at approval time)

| # | Chunk | Notes |
|---|---|---|
| 7 | Knox layer | `OemPolicyApplier`, KSP restriction-bundle generation, KPE licensing, SDK fallbacks |
| 8 | TAK pack | ATAK policy type: data packages, `.pref` files, plugin sets, cert enrollment |
| 9 | Admin UI | Policy builder, stacking view, fleet dashboard |
| 10 | Offline / LAN relay | Only if required — D9 keeps the door open |

---

## Open questions / risks

| # | Item | Status |
|---|---|---|
| R1 | Writing to `/sdcard/atak/` needs `MANAGE_EXTERNAL_STORAGE`, an app-op that `setPermissionGrantState` does not grant. Matters for the TAK pack: ATAK config is not in a MediaStore collection, so shared-storage APIs do not reach it. | ✅ **Downgraded to an implementation choice, 2026-08-31.** The operator has seen a commercial MDM push files into ATAK directories on Device Owner devices with an MDM app as manager. So it is demonstrably achievable and no longer a design risk — only a question of which mechanism. On Samsung the overwhelmingly likely answer is Knox permission/app-op control, which is already the chosen path (D11). **Design response:** file push sits behind its own interface with a Knox implementation first and a one-time-grant fallback (Settings special-access, or a persisted SAF directory grant — one tap at provisioning, acceptable on a kiosk device). Costs nothing to build defensively, so no further investigation is warranted before Chunk 5. |
| R2 | OBB placement for XAPKs inherits R1 | Open |
| R3 | Knox partner application pending — gates KME and KPE | Tracking; AOSP path must not depend on it |
| R4 | `INTERSECT` on app allowlists is correct but counter-intuitive | Make configurable per policy; show resulting set before publish |
| R5 | Mixed SoC vendors (Qualcomm XCover6 Pro / MediaTek Tab S10+) on One UI 8 | Test every firmware-level behavior on **both** models |
| R6 | ~~Advanced Protection Mode blocks Device Owner install~~ | ✅ **Downgraded to low, 2026-08-31.** The operator runs commercial MDMs and Headwind in production on this exact hardware and One UI 8, installing apps successfully. Device Owner `PackageInstaller` holds system install privilege and does not go through the user-facing "install unknown apps" gate — as predicted, now corroborated by production use rather than documentation. Residual risk is only a user *opting into* Advanced Protection, which a Device Owner can largely prevent by restricting Settings anyway. No lab work needed. |
| R7 | mTLS header trust: nothing in code stops the app being exposed directly, where a copied certificate in `x-ssl-client-cert` would authenticate without the private key | **Partly mitigated.** A reference nginx config now ships in [docker/nginx/nginx.conf](docker/nginx/nginx.conf) — it always overwrites the header, so a forged one is stripped, and rejects uncertified requests to `/api/v1/device/` at the edge. `scripts/dev_enroll.py` verifies both behaviours on every run, and demonstrates the direct port accepting the forged header. **Still open in code:** the app does not refuse to start when no trusted proxy is configured. |
| R10 | ~~The admin console has no authentication~~ | ✅ **Closed (Chunk 8).** Authentik forward auth with group-based authorization, failing closed, applied at router registration. `disabled` remains the local-development default and says so loudly at startup and in the UI. |
| R12 | **`pki/token_vault.key` now decrypts every enrollment token secret** (D74). Combined with a database dump it yields working enrollment credentials. | **Accepted, bounded.** It sits beside `ca.key`, which is strictly more dangerous, so it does not change what must be protected — only how much is lost if `pki/` leaks. Rotating it invalidates QR re-display for existing tokens but not the tokens themselves. Folded into R8's KMS/HSM answer. |
| R11 | **No CSRF protection on the console's form posts.** With forward auth, a signed-in administrator visiting a hostile page could have their browser submit a policy change or enrollment token. Authentik's session cookie would be sent with it. | **Open.** Needs a per-session token on the form posts. Lower severity than R10 was — it requires an authenticated victim and a targeted attack — but it is the natural next gap now that sessions exist. |
| R9 | **Pre-granting `WRITE_EXTERNAL_STORAGE` locks an app out of `MANAGE_EXTERNAL_STORAGE`** on Android 11+. Auto-granting runtime permissions is otherwise the obvious thing to do as Device Owner, so this fails silently and looks like an unrelated storage bug. Confirmed in Headwind's source, where they work around it explicitly. | **Open, must be handled in Chunk 6.** When pre-granting permissions, detect apps declaring `MANAGE_EXTERNAL_STORAGE` and skip the legacy storage permissions for them. Affects ATAK directly. |
| R8 | CA private key is stored unencrypted at `pki/ca.key` (mode 0600, gitignored). Anyone holding it can mint a device identity. | **Open.** Acceptable on a single trusted host where the DB is equally exposed; move behind a KMS/HSM before that stops being true. |
| Q1 | ~~Which Samsung models / One UI versions?~~ | ✅ **Answered** — see device matrix |
| Q2 | ~~Existing ATAK deployment to integrate with?~~ | ✅ **Answered** — no upstream integration; ATAK server is configured **on the EUD**, so the TAK pack is pure config push (Chunk 7) |

### Retired

- **Minimum installable `targetSdk`** — Android 16 holds at **API 24**, unchanged from
  Android 15 (it did not increment). Normal APKs including ATAK clear this easily.
  Not a blocker; the server should still validate `targetSdk >= 24` at upload so the
  failure is legible there rather than as `INSTALL_FAILED_DEPRECATED_SDK_VERSION` on device.

---

## Changelog

- **2026-08-31** — **Branding added.** Project named ATLAS (ATAK Tactical Lifecycle
  & Administration System); product family reserved (Console / Agent / Fleet /
  Provisioning) in new [docs/BRANDING.md](docs/BRANDING.md). Rebranded user-facing
  surfaces only: README H1 + tagline, `FastAPI` title/summary, CLI description,
  ARCHITECTURE.md header, the firewall-rule name printed by `setup_for_tablet.py`.
  Code identifiers deliberately untouched (D61, D62). Developer/publisher recorded
  as **TAK-Solutions LLC** — README footer, `FastAPI` `contact`, BRANDING.md.
  Licensed **Apache 2.0** (D63): `LICENSE` + `NOTICE` at repo root, `FastAPI`
  `license_info`, README License section, and the full boilerplate header
  prepended to all 87 `.py` / `.kt` / `.gradle.kts` sources plus the Alembic
  migration template. 200 tests still pass.
- **2026-08-30** — Requirements gathered; operating envelope decided (offline-tolerant,
  50-500 devices, generic core + TAK pack); architecture written; Chunk 1 planned.
- **2026-08-30** — Device matrix confirmed (XCover6 Pro `SM-G736U1`, Tab S10+
  `SM-X828U`, both One UI 8 / Android 16). Q1 closed. Retired the `targetSdk` concern
  (Android 16 holds at API 24). Added R6 (Advanced Protection Mode) and reframed R5
  around mixed SoC vendors. Corrected the Knox SDK deprecation rationale behind D11.
- **2026-08-30** — Q2 closed: ATAK server is configured on the EUD, no upstream
  integration needed.
- **2026-08-31** — **Chunk 5 complete.** 200 tests passing. F1–F5 all satisfied
  server-side: a `FILES` policy type with a marketplace tier and admin-controlled zip
  extraction, policy-first bulk assignment, and live propagation via a long-poll
  doorbell wired to `after_commit`. Measured 18 ms from policy change to device wake
  through nginx with a real mTLS client. Two bugs caught by tests: the wait endpoint
  reached around dependency injection for a database engine, and `exclude_unset`
  persistence silently dropped a validator-derived `extract_to`.
- **2026-08-31** — **R1 retired too.** The operator has seen a commercial MDM push
  files into ATAK directories on Device Owner devices, so file push is demonstrably
  achievable and reduces to picking a mechanism — Knox on Samsung, with a one-time
  grant as fallback. Both hardware risks that were gating Chunk 5 are now closed by
  field evidence rather than lab work. Android build toolchain confirmed present.
- **2026-08-31** — **R6 retired, R1 narrowed.** The operator runs commercial MDMs and
  Headwind in production on this hardware, installing apps successfully, which
  settles the Advanced Protection question I had flagged as load-bearing and
  unverified. R1 stands, because app install and arbitrary file writes are different
  capabilities. Recorded prior art and the intent to blend Hexnode's policy model
  with Headwind's provisioning. Added `SM-X520` (Tab S10 FE, Exynos) to the matrix —
  a third SoC vendor.
- **2026-08-31** — **Chunk 4 complete.** 168 tests passing, plus an end-to-end run
  against the Docker stack. Hand-written AXML and APK-signing-block parsers, so the
  server reads identity, version, and signing certificate out of an upload rather
  than trusting the uploader. Signature pinning and the API 24 `targetSdk` floor are
  enforced at upload, where the error is legible, instead of failing opaquely on a
  tablet. XAPKs unpack server-side into content-addressed base/split/OBB parts, and
  device download supports `Range` so an interrupted transfer resumes. Uploading the
  agent APK now yields the provisioning checksum that had blocked QR payloads.
- **2026-08-31** — **Local Docker stack** added (out of band, at user request):
  Postgres + API + nginx mTLS terminator, with a one-shot PKI init because nginx
  must read the device CA at startup. All three migrations verified against real
  Postgres, not just the SQLite suite. `scripts/dev_enroll.py` simulates a device
  end to end and verifies the bundle signature with an independent canonical-JSON
  implementation — the contract the Kotlin agent must match. R7 partly mitigated.
- **2026-08-31** — **Chunk 3 complete.** 121 tests passing. Desired-state check-in
  over mTLS: signed Ed25519 bundles sent only when the state changed, a TTL'd
  at-least-once command queue, and convergence tracking that separates server intent
  from device reality. Caught three migration defects before they shipped —
  autogenerate emitted `Text()` and `app.db.base.UtcDateTime` without importing
  either, and added NOT NULL columns with no `server_default`, which fails on
  Postgres against a table with existing rows. Fixed the Alembic template so the
  import half cannot recur (D35).
- **2026-08-30** — **Chunk 2 complete.** 86 tests passing. Device identity is a
  hardware-backed EC P-256 keypair with an mTLS client certificate from an internal
  CA; enrollment tokens are hashed at rest and scope a device into its groups/tags so
  it arrives with its policy stack already resolved. Added R7 (mTLS header trust) and
  R8 (CA key at rest). Fixed a dialect-dependent timestamp comparison bug with a
  `UtcDateTime` type decorator (D27).
- **2026-08-30** — **Chunk 1 complete.** 58 tests passing. Two caching bugs found and
  fixed by the tests before review: (a) invalidation deleted the cache row, destroying
  the baseline that distinguishes a real change from a cosmetic one, so every
  invalidation bumped `state_version` and would have woken the whole fleet on a
  no-op republish; (b) a never-computed device baselined at `None` rather than `{}`,
  so its first read bumped `state_version` spuriously. Both are now D15/D16.
