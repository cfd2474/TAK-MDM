# Project State

Running state file per [CLAUDE.md](CLAUDE.md). Read before starting any step;
update after every completed step.

**Last updated:** 2026-09-01

---

## Current status

**Phase:** ✅ **Chunks 10–14 complete.** F1–F6 all hardware-proven; R1, R11, R13
closed. **Enrollment is now a single persistent token with 15-minute signed QR
derivatives** (Chunk 14), verified live through real nginx — including that
retiring the primary kills an already-issued, still-time-valid QR immediately.
Agent **v41 (`0.10.1`)** running on `SM-X520` (compliant, serial `R5GL40MMHRN`),
delivered over the air by the agent-update channel — the first build on this
device that no one sideloaded.
**No hardware verification is outstanding** — W17, W23 and W24 all cleared
2026-09-02 (W25).
**W14 Wi-Fi, W15 quick wins, W16 allowlist, W18's granular password path and
W20's forced passcode all hardware-proven. W19 rebuilt the on-device UI as the
branded ATLAS MDM console (five sections + manual sync), hardware-proven. W17
closed R2** — a DO cannot place XAPK OBB
files (EACCES probed on hardware); the agent says so loudly and the Apps page
flags it. **W18 closed the policy→agent audit** — Wi-Fi
`auto_join`/`mac_randomization` dropped (`@SystemApi`), password
`min_letters`/`min_digits`/`min_symbols` implemented via the granular DPM family
and proven on the tablet (`passwordQuality` 0x20000→0x60000→0x20000 across a
publish/revert cycle, `errors=0`). **W20** added a forced screen-lock passcode
to the PASSWORD policy (`resetPasswordWithToken`, re-asserted every sync),
hardware-proven. **W21** made the composite the only kind of policy — a
migration converted every standalone policy — and rebuilt the editor to show
every category's fields with current values (no JSON), one save, and an
unsaved-change guard.
**✅ Web UI expansion (Chunks W1–W10, plus W4b) COMPLETE.** Eight-section ATLAS
console — Enroll, Manage, Policies, Apps, Content, Reports, Admin, Guides — on
server-rendered Jinja with no build step. **W10 replaced JSON-textarea policy
editing with generated typed forms** (dropdowns, tri-state controls, repeatable
rows; per-field merge hints). **W12 split each category's sub-topics into
navigable sub-pages** with green-check completion markers. **W13 wired the
Networks type; W14's Wi-Fi applier, W15's quick wins, W16's allowlist enforcement
and W18's granular password path are all hardware-proven on `SM-X520`. W17 closed
R2 (OBB placement) as not feasible, made loud; W18 closed the policy→agent audit
(Wi-Fi `@SystemApi` fields dropped, password character-class minimums
implemented and proven on the tablet). W19 rebuilt the DPC's on-device UI as the
branded ATLAS MDM console; W20 added a forced screen-lock passcode to the
PASSWORD policy, hardware-proven; W21 unified every policy into the composite
kind with a values-in-fields editor; W22 added quick archive from the list with
an impact modal; W23 hardened live push and added a "Check in now" button; W24
made the DPC show policy names and added console inline rename.**
464 server tests + 52 agent tests.

`adb` reaches the tablet over wireless debugging. **Ports rotate on every
restart**, so reconnecting means reading the current `IP:port` off the device —
`adb mdns services` finds it once paired, and the pairing itself survives.

> **`SM-X520` is enrolled, checking in, and applying policy over mTLS.** Live
> propagation measured against the tablet: publishing a policy version woke the
> parked long-poll in the *same second*, bundle delivered one second later.
> The server stack (Chunks 1–5) and the agent (Chunk 6) are proven together.

- ✅ Requirements gathered
- ✅ Architecture written → [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- ✅ **Chunk 1 complete** — policy stacking engine
- ✅ **Chunk 2 complete** — enrollment, device PKI, mTLS auth
- ✅ **Chunk 3 complete** — desired-state protocol, signed bundles, command queue
- ✅ **Chunk 4 complete** — content-addressed artifacts, APK/XAPK pipeline,
  resumable device download
- ✅ **Chunk 5 complete** — managed files, marketplace tier, bulk assignment, live
  propagation. **F1–F5 all satisfied server-side.** 200 tests passing.
- ✅ **Chunk 6 complete and hardware-validated** — Kotlin Device Owner agent
  enrols, checks in, applies policy, and wakes on the long-poll. Guided permission
  setup runs during provisioning.
- ✅ **Chunk 7 complete** — admin console at http://localhost:8000
- ✅ **Chunk 8 complete** — Authentik forward auth on the admin surface, closing R10
- ✅ **Chunk 9 complete** — any live token's QR can be re-displayed, with optional
  Wi-Fi credentials embedded. 254 tests passing.
**Everything is pushed to `origin/main`.**

### Not yet proven on hardware

Enrolment, check-in, policy application and live wake are verified. These are
written but have never actually run on a device:

| Unproven | Why it matters |
|---|---|
| ~~**App install** (`PackageInstaller`, split APKs)~~ | ✅ **Proven 2026-09-01**, including splits. Real ATAK (107 MB, single APK) and real Butterfly IQ (**XAPK → base + 6 splits**, 323 MB) both installed by the agent; Android lists all seven parts and records `installerPackageName=org.takmdm.agent`. Upgrade proven too (`versionCode 1 → 2`). |
| ~~**File placement and zip extraction**~~ | ✅ **Both proven 2026-09-01.** A map source pushed byte-identical to `/sdcard/atak/imagery`, and a DTED archive extracted into `/sdcard/atak/DTED/w125/` (~104 MB, hashes matching). Closes R1; F5 proven on hardware. |
| ~~**Marketplace**~~ | ✅ **Proven 2026-09-01** — offered not imposed, selected through the agent's real UI, placed immediately, and the selection reported back to the server. |
| ~~**Kiosk / lock task**~~ | ✅ **Proven 2026-09-01.** Engaged, held against HOME/RECENTS/launcher, and released by policy in ~15 s. |
| ~~**Transient commands**~~ | ✅ **Proven on `SM-X520`, 2026-09-01.** `lock`, `locate` and `collect_logs` all dispatched and succeeded at `attempts=1/5`. Was not implemented agent-side at all before Chunk 10. **`reboot` and `wipe` remain untried by choice** — they are the two whose deferred-result path (D90) cannot be rehearsed without actually rebooting or wiping the tablet. |
| ~~**StrongBox**~~ | ✅ **Answered 2026-09-01.** `SM-X520` has **no StrongBox**; the key is `TRUSTED_ENVIRONMENT (TEE), insideSecureHardware=true`. D56's fallback worked as designed and the key is hardware-backed, which is the property that matters. ⚠️ One model on one SoC — the other two must be asked separately (R5). |

### Housekeeping

* ✅ **Stale device records cleared, 2026-09-01.** `SM-X520-421929662296025e`
  (a failed enrolment that registered before erroring) and `VERIFY-LOGS-01` (Chunk
  10's verification run) are gone, via the new retire-then-delete flow. Verified no
  orphans remain in any of the six tables that reference `device`.
  `R5CN00TAK01` / `R5CN00TAK02` are left alone — they are `scripts/dev_enroll.py`
  simulations, not accidents.
* Build toolchain: JDK 17 at `C:\Program Files\Microsoft\jdk-17.0.20.8-hotspot`,
  Android SDK with API 36, build-tools 36.0.0, `adb` under
  `%LOCALAPPDATA%\Android\Sdk\platform-tools`.

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

**External dependency (corrected 2026-09-02 — see [docs/KNOX.md](docs/KNOX.md)):**
**KPE is not gated on a partner agreement.** KPE Premium is free and the *end
customer* generates their own key in the Knox Admin Portal; a Knox **developer**
account is needed only to download the SDK, at build time, by whoever compiles the
agent. Samsung express approval is being sought to settle whether a Knox-built APK
may be distributed to third parties. **Knox Mobile Enrollment** for a self-hosted
EMM remains genuinely open. The AOSP path must be fully functional without Knox;
Knox is strictly additive.

---

## Reference documents

| File | Read it when |
|---|---|
| [HANDOFF.md](HANDOFF.md) | Starting a new session — orientation, how to run it, what is unproven, and where to go next |
| **[docs/ANDROID_PLATFORM_REFERENCE.md](docs/ANDROID_PLATFORM_REFERENCE.md)** | **Before any change touching provisioning, the DPC, app installation, permissions, or file placement.** Android contracts traced to official sources, plus what is verified on our hardware. Consult it *every* iteration — three factory resets were spent on a failure the documentation states plainly. |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Design rationale for the server and agent |
| [docs/KNOX.md](docs/KNOX.md) | Before planning or writing Knox code, or answering what Knox will/will not allow. Licensing, distribution model, the assessed capability surface, and the walls Knox does **not** close. |
| "Operational notes" below | Before debugging anything that looks impossible |

## Operational notes — read before debugging anything "impossible"

Traps that have each cost real time in this project. When a change appears to have
no effect, check this list before investigating the code.

### Docker: `up -d` alone is usually not enough

| Changed | Required command | Why |
|---|---|---|
| **Any Python source** | `docker compose up -d --build` | The source is `COPY`'d into the image at build time. Plain `up -d` restarts the container with the **old image**, so the change silently does not exist. |
| **`docker/nginx/*.conf`** | `docker compose restart proxy` | The file is bind-mounted, so the container's config is unchanged and Compose sees no reason to recreate it. nginx reads its configuration once, at startup. |
| **`pki/server.crt`** (e.g. after `scripts/setup_for_tablet.py`) | `docker compose restart proxy` | Same reason: nginx loads certificates at startup and keeps serving the old one. |
| **`.env`** | `docker compose up -d` | Environment variables are container config, so Compose does recreate. No rebuild needed. ⚠️ **But only for variables `docker-compose.yml` actually passes through.** It enumerates them explicitly, so a new `TAKMDM_*` in `.env` reaches nothing until it is also added to the `environment:` block. This cost real time in Chunk 13: `TAKMDM_CONSOLE_ORIGIN` was set, the setting stayed empty in the container, and a security check silently did nothing while every test passed. |

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

### ✅ Chunk 6 — Kotlin Device Owner agent (COMPLETE, hardware-validated)

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

**Validated on `SM-X520` (Galaxy Tab S10 FE, Android 16 / One UI 8).** Agent v8.

```
POST /api/v1/enroll          201   okhttp/4.12.0, HTTP/2
POST /api/v1/device/checkin  200   compliant
GET  /api/v1/device/wait     200   woken in the same second as the policy publish
```

#### Six bugs only hardware could find

Every one passed the full test suite and every one was invisible from the server.
Recorded because the *shape* of them repeats.

| # | Bug | Why it was invisible |
|---|---|---|
| 1 | **Missing `GET_PROVISIONING_MODE` / `ADMIN_POLICY_COMPLIANCE` activities** — required from Android 12 | The system aborts with a bare "something went wrong" after a factory reset. Cost three resets. Found by reading the spec, not the symptom. |
| 2 | **`onProfileProvisioningComplete` never runs** on a modern device — `ADMIN_POLICY_COMPLIANCE` replaces it | Hidden behind #1. The agent would never have started even if provisioning had succeeded. |
| 3 | **Wrong admin component name** — a leading dot expands against the *package root*, so `.MdmDeviceAdminReceiver` missed the `.admin` segment | Identical failure message to #1 |
| 4 | **CSR signing pinned to the `AndroidKeyStore` provider**, which supplies no `Signature` implementations — they live in `AndroidKeyStoreBCWorkaround` | Failed *before any network call*, so the server saw nothing at all |
| 5 | **Device key restricted to `DIGEST_SHA256`** — a TLS handshake picks its own signature algorithm | Surfaced as an opaque `SSLHandshakeException` with no hint the key was at fault |
| 6 | **nginx killed the long-poll at 60 s** (`proxy_read_timeout`) while the endpoint holds for 300 | The agent silently fell back to polling; F3 appeared to work but did not |

**The pattern in 3, 4 and 5:** an over-specific constraint that looks careful and
instead guarantees failure, reported as something unrelated. Worth watching for in
the Knox work, where the same instinct will be tempting.

**What actually broke the deadlock:** making the agent report its own errors on its
own screen. Bugs 4 and 5 were found in one attempt each afterwards. Before that,
three rounds of server-side diagnosis found nothing, because a client that never
connects leaves no trace to diagnose.

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
| D79 | **The agent reports its own errors on its own screen** | Diagnosing a device that will not enrol otherwise needs USB debugging, which needs Developer Options on a device that may already be locked down — exactly when the information is hardest to get and most needed. This is what ended three rounds of blind guessing. |
| D80 | Enrolment failure inside `PolicyComplianceActivity` is **not fatal** | Provisioning cannot be repeated without another factory reset, so a network blip must not undo it. The activity reports and the agent retries. |
| D81 | Runtime permissions are **self-granted silently**; only app-ops are put to the operator | Prompting for something a Device Owner can grant itself would waste a tap on every device in the fleet. Only `MANAGE_EXTERNAL_STORAGE`, overlay and battery exemption genuinely need a human. |
| D82 | **The device key allows a broad set of digests**, including `DIGEST_NONE` | A TLS handshake picks its own signature algorithm; a key restricted to SHA-256 fails opaquely the moment anything else is negotiated. |
| D83 | **No provider is pinned when signing with a keystore key** | `AndroidKeyStore` supplies no `Signature` implementations. JCA's delayed provider selection resolves the right one from the key itself. |
| D84 | **`acked_state_version` advances even when apply errors occur** | It means "this version has been processed", not "processed perfectly" — quality is `compliance_status` (D28). Conflating them pinned a device a version behind forever over one missing permission, and made a genuinely stuck device indistinguishable from a slightly degraded one. |
| D85 | The agent offers **manual re-enrolment** with a pasted token | A device whose key or certificate is unusable would otherwise need a factory reset, because the token is deliberately cleared once used. That is a heavy price for a recoverable fault. |
| D86 | Bench configuration over `adb` is **debug-build only** | A receiver that can repoint an agent at an arbitrary server is a fleet-takeover primitive. Gated on `BuildConfig.DEBUG`. |

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

### ✅ Chunk 10 — Agent command layer and remote diagnostics (COMPLETE, hardware-validated)

Inserted ahead of the install proof, for a reason that only surfaced on inspection:
**the agent has no command handling at all.** The server queues six command types
and `claim_for_delivery` puts them in every check-in response; `ApiClient` and
`Reconciler` never read the `commands` array. They are delivered and dropped, and
because each delivery counts an attempt, the console reports
`EXPIRED — exceeded max attempts`: a device that received the command and failed,
rather than an agent that cannot execute one. A remote wipe today promises
something it cannot do.

The second driver is diagnostics. `adb` was unavailable when this chunk was
planned, and the install proof is expected to need several agent fixes (the
enrolment work needed six). **Investigated rather than assumed:** nothing in ATLAS
blocks `adb` — the tablet carries a single `PASSWORD` policy, no `RESTRICTIONS`
policy exists for it, and `PolicyApplier.applyRestrictions` skips absent fields
instead of applying defaults, so `DISALLOW_DEBUGGING_FEATURES` was never set.
Developer Options is simply off. `adb` is therefore recoverable *and* remote log
collection is still worth building, because it is the channel that works on a
fielded device where nobody can plug in a cable.

**Log collection deliberately does not scrape `logcat`.** `READ_LOGS` has been
restricted to privileged system apps since API 16, so the agent cannot hold it.
Whether an unprivileged app may still read *its own* lines is **not confirmed by
any official source** — a recollection that it can was checked and left unproven,
so nothing is built on it (CLAUDE.md §6). Android's own guidance settles it:
"Avoid logging to `logcat`. If you need more detailed logs, use internal storage
and manage your own logs directly." That is also the better design here, since
these logs now leave the device and redaction must be ours to control.

1. **Agent log store** — an `AgentLog` facade over a size-capped ring buffer on
   internal storage, recording timestamp, level, tag, message and throwable. Tees
   to `logcat` as well so `adb` stays useful when present. Never records token or
   key material.
2. **Command execution layer** — read `commands` from the check-in response and
   dispatch through a handler registry keyed by type, so adding a command type
   does not modify the dispatcher (OCP). Report results at the next check-in.
   Implement the existing six.
3. **`COLLECT_LOGS` command** — new type server-side (enum, TTL, validation, admin
   enqueue) and its agent handler.
4. **Log upload** — a device-facing mTLS endpoint with a hard size cap, a
   `DeviceLogBundle` model, and a migration. Separate from check-in: a log bundle
   has no business inflating a request that runs every two minutes.
5. **Console** — a device page section listing captures newest first, and a
   "Collect logs" button.
6. **Tests** — server: command type, upload cap, auth, retention. Agent:
   dispatcher, registry, redaction.
7. **Prove on hardware** — enqueue `COLLECT_LOGS`, watch the doorbell wake the
   device and the bundle arrive. Retires the transient-command item above.

#### Decisions taken during implementation

**Steps 1–6 complete. 271 server tests + 30 agent tests passing**, and the whole
path verified through real nginx and mTLS: command delivered at check-in, bundle
uploaded, result acknowledged, bundle read back byte-identical, size cap refused by
the application (not the edge), and an uncertified upload refused at the edge.
**Step 7 (hardware) is blocked on getting agent v9 onto the tablet — see below.**

#### The dropped-command bug, confirmed on hardware rather than assumed

A `COLLECT_LOGS` was queued against the live `SM-X520` while it was still running
agent v8:

```
collect_logs   expired   attempts=5/5   error=exceeded max attempts
```

The device was online and healthy throughout — the doorbell woke it in the same
second the command was queued (queued `:55.751`, check-in `:55.926`). It received
the command five times and dropped it five times, and the console reports a device
that would not answer. **That is indistinguishable from a device that tried and
failed**, which is the whole problem: the symptom names the wrong cause. Evidence
gathered before the fix, not inferred after it (CLAUDE.md §4).

#### Decisions taken during implementation

| # | Decision | Rationale |
|---|---|---|
| D87 | The agent keeps **its own log** rather than scraping `logcat` | `READ_LOGS` is unavailable to a normally-installed app, self-reading is unconfirmed by official sources, and Android's documentation explicitly recommends managing your own logs instead. It also puts redaction under our control, which matters once logs leave the device. |
| D88 | Command dispatch is a **registry keyed by type**, not a `when` block | Adding a command type must not require editing the dispatcher (OCP). The `when` would have been shorter and is exactly how the seventh type gets forgotten. |
| D89 | An **unknown command type is reported as unsupported**, never dropped | This is the bug that motivated the chunk, fixed structurally: the console must distinguish "this agent cannot do that" from "the device failed to do that". Silence made them identical. |
| D90 | `reboot` and `wipe` are **deferred**: the handler returns the effect, and it runs only after an immediate check-in has delivered the result | Both end the session that would report them. Run inline, the result never arrives, the queue redelivers, and the device reboots again on the next check-in — a loop ending only when attempts are exhausted. The agent flushes results first and executes second; if the flush fails it does *not* execute. |
| D91 | Command results are **persisted**, not held in memory | Delivery is at-least-once (D31), so a result lost to a process death means the command runs twice. For `clear_app_data` that destroys data the user recreated in between. |
| D92 | `AGENT_VERSION` is read from `BuildConfig.VERSION_NAME` | The literal in its place said `0.1.0` while the build was at `0.2.4`, so every device reported a version it was not running — and "which build is this?" is the first question asked of a misbehaving device. A constant that must be remembered separately will not be. |
| D93 | The test suite now sets `PRAGMA foreign_keys=ON` for SQLite | Without it SQLite ignores foreign keys entirely, so every `ON DELETE CASCADE` and `SET NULL` in the schema was a no-op under test while Postgres enforced it — the same dialect divergence as D27. Enabling it broke no existing test, so the rules were already consistent; they were simply never verified. |
| D94 | `device_log_bundle.command_id` is `ON DELETE SET NULL`, not `CASCADE` | A log bundle outlives the request that produced it. Tidying the command queue must not destroy the evidence. |
| D95 | **Self-granting runs on every sync**, not once at provisioning | A permission added in a later agent build was otherwise declared and never granted on any device already in the field — silently, and indefinitely. That is exactly what happened to `READ_PHONE_STATE`: the fix was committed, was correct, and did nothing. `setPermissionGrantState` is idempotent, so the repeat costs nothing. |
| D96 | The `ANDROID_ID` fallback identity is **reported as a compliance error**, not merely logged | A device on the fallback looks perfectly healthy until it is wiped, at which point it silently becomes a second record and loses its policy stack. The console has to be able to see that coming. |

#### Corrections to earlier claims in this file

* **Transient commands were described as "never dispatched to a real device"**,
  implying the agent side existed. It did not — see above.
* **"A stale duplicate device record … safe to delete from the console"** is
  **wrong**. There is no device deletion anywhere: not in the console, not in the
  API (`DELETE /api/v1/devices/{id}` returns 405). Two stale records
  (`SM-X520-421929662296025e`, and `VERIFY-LOGS-01` from this chunk's verification)
  cannot currently be removed without direct database access. Small gap, worth its
  own fix.

#### ✅ Step 7 complete — proven on `SM-X520`

`adb` was recovered by pairing over wireless debugging (the tablet was advertising
`_adb-tls-connect` but this host had never paired). Agent v9, then v10, installed
with `adb install -r`.

**The before-and-after sits in one table**, the same command against the same
device thirty minutes apart:

```
collect_logs   succeeded  attempts=1/5  result={'bytes': 512, 'lines': 6}   ← v10
collect_logs   succeeded  attempts=1/5  result={'bytes': 170, 'lines': 2}   ← v9
collect_logs   expired    attempts=5/5  error=exceeded max attempts         ← v7
```

Queue to settled was **7.3 seconds**, covering the doorbell wake, execution, upload
and result report. Two further commands confirm the layer is not log-specific:

```
locate   succeeded  attempts=1/5  {network provider, ~40 m accuracy, age_seconds: 483}
lock     succeeded  attempts=1/5
```

`reboot` and `wipe` are deliberately untried: their deferred-result path (D90)
cannot be rehearsed without actually rebooting or wiping the device.

#### A gap the hardware test exposed immediately

The first collected bundle contained **two lines**. `SyncService`, `AppInstaller`,
`PolicyApplier`, `FileDeployer` and `DeviceIdentity` were all still calling
`android.util.Log` directly — 49 direct calls against 12 through `AgentLog` — so
almost nothing an operator would want to read was reaching the collectable log. The
mechanism worked and collected nothing useful, which is a worse failure than not
building it: it invites trust it has not earned.

Migrated all 49 (v10), and the next capture carried the sync loop. **`AppInstaller`
was among them**, which matters directly: Chunk 11 exists to debug app installs, and
its diagnostics would have been invisible to the very channel built to collect them.

#### D24 investigated and partly repaired (2026-09-01)

Chased on request. **Root cause found, and it is not what the symptom suggested.**

`Build.getSerial()` was throwing `SecurityException: the uid does not meet the
requirements to access device identifiers`, so `serialNumber()` fell back to
`ANDROID_ID` — which Android documents as changing on factory reset, precisely the
event D24 exists to survive. Hence two records for one tablet.

**The permission was already declared, with a comment already describing this exact
bug.** `READ_PHONE_STATE` was added in `d13b630` along with a manifest comment that
diagnoses the problem correctly. It never took effect, because self-granting ran
**only inside `PolicyComplianceActivity`, which never runs again after
provisioning**. The tablet had been provisioned before that commit, so the
permission sat declared and ungranted, and the bug it fixed kept happening — with a
note in the tree saying it was solved.

**The general defect is larger than this permission:** any runtime permission added
to the agent in a later build was silently never granted on devices already in the
field. `ensureSelfPermissions()` now runs on every sync, before enrolment, and is
idempotent.

Verified by restoring the broken state and watching it heal:

```
revoke READ_PHONE_STATE          → granted=false
install v12, wait one sync       → "self-granting 1 permission(s): READ_PHONE_STATE"
                                 → granted=true, flags=[POLICY_FIXED|…]
Build.getSerial()                → 'R5GL40MMHRN'   (was: SecurityException)
```

`POLICY_FIXED` confirms the DPC granted it rather than the earlier `adb` probe.

**The fallback is now loud**, both in the log and as a reported `apply_error`, so a
device living on an unstable identity is visible in the console *before* a wipe
turns it into a duplicate rather than after.

⚠️ **Not yet resolved: the existing record.** `dd814571…` is still registered under
`SM-X520-6e5d7b239e5d39c3`. The agent will now report `R5GL40MMHRN`, so **the next
wipe-and-re-enrol still creates one final duplicate** — the fix prevents new
occurrences, it does not repair the row already written. Options are in the open
questions below.

#### Two more corrections from hardware

* **The tablet was on agent v7 (`0.2.3`), not v8** as this file claimed.
* **Its real serial is `R5GL40MMHRN`**, but the server has it enrolled as
  `SM-X520-6e5d7b239e5d39c3` — the `ANDROID_ID` fallback, meaning `Build.getSerial()`
  failed at enrolment. Since re-enrolment matches on serial (D24), a device that
  later reports its true serial would create a **second record** rather than
  re-adopting the first. That is a plausible explanation for the stale
  `SM-X520-421929662296025e` duplicate, and it means D24's guarantee is weaker in
  practice than written. **Not yet investigated** — worth doing before the fleet
  grows.

#### Superseded: getting a new agent build onto the tablet

Agent **v9 (`0.3.0`, versionCode 9)** is built and uploaded to the server, and its
signature pins cleanly against the existing package. It is not on the tablet.

`adb devices` is still empty. **Investigated, not assumed:** nothing in ATLAS blocks
it — the tablet's whole effective policy is one `PASSWORD` field, no `RESTRICTIONS`
policy is assigned to it, and `PolicyApplier.applyRestrictions` skips absent fields
rather than applying defaults, so `DISALLOW_DEBUGGING_FEATURES` was never set.
Developer Options is simply switched off on the device.

This is the constraint that matters most for Chunk 11: **that chunk is expected to
need several agent fixes** (enrolment needed six), and without a way to ship one it
stalls at the first. Routes, best first:

1. **Enable Developer Options → Wireless debugging on the tablet**, then
   `adb pair` / `adb connect`. Restores `logcat` as well.
2. **Sideload from the tablet's own browser** — the agent APK is served in plaintext
   at `:8080` precisely because provisioning needs it to be.
3. **Self-update through the install path** — circular: that is what Chunk 11 exists
   to prove, and it cannot be the way its own fixes are delivered.
4. Factory reset and re-provision by QR. Works, and costs the most.

### ✅ Chunk 13 — CSRF protection (COMPLETE, closes R11)

With forward auth (D67) the browser holds an Authentik session cookie, and that
cookie is sent on *any* request the browser makes — including one a hostile page
causes. Nothing today distinguishes a form the administrator submitted from one
submitted on their behalf. Today's retire and delete buttons made that sharper: the
console can now destroy records, not just create them.

**Scope is wider than "the console's forms".** An HTML form can only send
`GET`/`POST` with a form content type, so JSON API endpoints are already awkward to
reach cross-site and `DELETE` is unreachable. But **`POST /api/v1/devices/{id}/retire`
takes no body at all**, so a cross-site form can call it exactly as written. The
admin API is not automatically safe just because it is an API.

Two layers, each with one job:

* **A signed token on console forms** — the real defence, depending on nothing but
  our own key.
* **Origin validation on every unsafe admin request** — catches the API endpoints a
  form can reach, and costs scripts nothing, since a non-browser client sends no
  `Origin` at all.

1. **`CsrfGuard`** — HMAC-signed token bound to the admin's identity with an
   expiry, keyed from `pki/csrf.key` via the same `load_or_create` pattern as the
   token vault.
2. **Origin/Referer validation** against an **explicitly configured** console
   origin rather than one inferred from a proxy-set `Host` header — the same
   discipline as R7, where trusting a header the client can influence is the bug.
3. **Enforced at router registration** for unsafe methods, not per endpoint, so a
   new admin route is protected by default (the D70 principle). Fail closed.
4. **Token issued as a cookie** on console GETs and exposed to templates through a
   `csrf_field()` macro.
5. **Add the field to all eight existing forms.**
6. **Tests** — missing, forged, expired, and another user's token; cross-origin
   rejected; safe methods untouched; a script sending no `Origin` still works.
7. **Docs** — close R11, and record the deployment setting.

**Complete. 310 tests, and verified live against the running stack in
`forward_auth` mode:**

```
no proxy headers                        401
form POST, no token  (the R11 attack)   403
hostile origin, VALID token             403
legitimate form POST                    303
JSON API from a script                  201
hostile origin -> bodyless API POST     403
hostile origin -> JSON fetch            403
```

#### The live test earned its keep immediately

Every unit test passed and a hostile origin was still accepted against the real
stack. **`docker-compose.yml` enumerates environment variables explicitly**, so
adding `TAKMDM_CONSOLE_ORIGIN` to `.env` never reached the container;
`console_origin` was empty, `check_origin` returned early, and the check silently
did nothing. The tests passed because they set the value directly.

That is the *nginx trap in a new costume* — correct code, no effect, because of
config plumbing — and it is now the fourth instance this session of the pattern in
HANDOFF §10. A test now asserts the variable is present in `docker-compose.yml`.

**The startup warning named the bug.** Added an hour earlier on the D73 principle,
it fired on the very deploy that had the fault and said exactly what was wrong.

#### Decisions taken during implementation

| # | Decision | Rationale |
|---|---|---|
| D105 | The token is **signed over the administrator's username**, not a bare double-submit value | A plain double-submit token only proves the submitter could read a cookie. Binding it means a token minted for one account cannot be replayed against another — there is a test that a stolen token fails for a different user, which a bare double-submit would pass. |
| D106 | The token is demanded of **form-shaped requests only**; everything else is covered by the origin check | An HTML form can only send urlencoded or multipart, and always sets one — including the bodyless POST that reaches `/api/v1/devices/{id}/retire`. A form cannot send `application/json`, and a cross-origin `fetch` that does is stopped by a CORS preflight this app answers nothing for. Demanding tokens on JSON would break every script and close nothing. |
| D107 | `console_origin` is **configured explicitly**, never inferred from the `Host` header | Behind a proxy that header is whatever the proxy was told. Building a security check on a value the client can influence is precisely the R7 mistake. |
| D108 | A **missing** `Origin` is allowed | Browsers always send it on the cross-origin requests this defends against; `curl` and deployment scripts send none. Refusing those would break every automation while closing no hole. |
| D109 | Enforcement **follows authentication** — inert when `admin_auth_mode=disabled` | With no session to ride, the request could simply be made directly, so a token protects nothing and costs every local script a round trip. One claim: the admin surface is protected or it is not (D68). |

**Decided up front: CSRF enforcement follows authentication.** When
`admin_auth_mode=disabled` there is no session to ride and an attacker can simply
make the request directly, so a token would protect nothing and cost every local
`curl` a round trip. One coherent claim — the admin surface is protected or it is
not — rather than a third state nobody can reason about (D68).

### ✅ Housekeeping — device deletion (COMPLETE)

There was **no way to remove a device record at all** — not in the console, not in
the API. Retirement existed server-side but was never exposed in the UI, so the
console offered neither.

**Retire, then delete.** Two deliberate acts, and the split is a real distinction
rather than ceremony:

* **Retire** — this device served and is now out of service. Certificates revoked,
  history kept. The normal answer, and it matches the standing instinct to archive
  rather than destroy (D20).
* **Delete** — this record should never have existed: a failed enrolment that
  registered before erroring, or a test device. There is no history worth keeping.

Deletion is **refused with 409 unless the device is already retired**. That is what
stops one misplaced click removing a working tablet, and it means the certificates
are always revoked before the record goes — so no live identity ever outlives its
row. All nine tables referencing `device` cascade, verified against real Postgres
with an explicit orphan check across all of them afterwards.

A deleted device fails closed: its certificate is still cryptographically valid and
still chains to our CA, but it resolves to no device, so authentication returns 401.
Tested.

| # | Decision | Rationale |
|---|---|---|
| D103 | Deletion **requires prior retirement**, with no exception for never-enrolled records | One rule beats a special case nobody can reason about (the D68 instinct). It also guarantees certificates are dead before the row is, and makes removing a live tablet take two acts instead of one. |
| D104 | Retire stays the default and is described as such in the UI | Most records are worth keeping. Presenting delete as the ordinary action would invite destroying history that cannot be recovered. |

### ✅ Chunk 11 — Multi-identifier device identity (COMPLETE, hardware-validated, closes R13)

D24 matches a re-enrolling device on `serial_number` alone. That is one key, and a
device's reported identity is not guaranteed to stay constant — as this fleet has
already demonstrated twice. The fix is to stop treating identity as a single string.

**A device enrols with a *set* of identifiers**; the server matches on any one it
already knows, and records the rest. A device that moves from the `ANDROID_ID`
fallback onto its real serial then re-adopts its own record instead of forking a new
one, and any future identity source slots in without another protocol change.

1. **`DeviceIdentifier` model + migration**, backfilling every existing device's
   `serial_number` as a `legacy` identifier so today's matching behaviour is
   preserved exactly.
2. **Matching by any known identifier**, with a kind priority so an ambiguous match
   resolves deterministically. Ambiguity is **surfaced, never silently merged** —
   merging two device histories on a guess is not something to do automatically.
3. **Promote the display serial** when a stronger identifier arrives, so a record
   stuck on a fallback repairs itself rather than staying permanently mislabelled.
4. **Agent sends its identifiers** — real serial when available, `ANDROID_ID`
   always. Back-compatible: an agent sending only `serial_number` still works.
5. **Console** shows a device's known identifiers and flags a possible duplicate.
6. **Tests** — re-adopt via fallback, via serial, promotion, ambiguity, and an old
   agent that sends no identifier list at all.
7. **Prove on hardware.** `DebugConfigReceiver`'s `reset_identity` (D86) lets the
   tablet re-enrol without a factory reset, so this is directly testable: it must
   re-adopt `dd814571…` rather than create a fourth `SM-X520` row.

**✅ Complete and hardware-validated. 282 tests passing.**

#### Step 7 — proven on `SM-X520`

Agent v13 (`0.4.0`) installed, then `reset_identity` (D86) cleared the device's
key, certificate and device id, so it re-enrolled from nothing:

```
DebugConfigReceiver: device identity cleared
DebugConfigReceiver: configured: … enrolled=false deviceOwner=true
Reconciler:          enrolled as dd814571-4a09-4d57-bec3-f8d6fd329f19   ← the SAME record
```

| | before | after |
|---|---|---|
| device rows | 5 | **5** — no fourth `SM-X520` |
| `dd814571` serial | `SM-X520-6e5d7b239e5d39c3` | **`R5GL40MMHRN`** |
| identifiers | — | `legacy SM-X520-6e5d7b239e5d39c3`, `serial R5GL40MMHRN` |

It matched on the old fallback, recorded the real serial beside it, and promoted
the display name. **The policy stack came through intact** — `PASSWORD.min_length
13` from `Tablet Live Test`, `compliant`, `state 2 = acked 2`. That is the part
that matters: before this change the same re-enrolment produced an empty new record
with no policies, which is how a wiped tablet silently came back unmanaged.

Migration applied to real Postgres and the backfill verified — every existing
device now carries its own `serial_number` as a `LEGACY` identifier, so today's
matching is preserved exactly:

```
R5CN00TAK01              | LEGACY | R5CN00TAK01
SM-X520-6e5d7b239e5d39c3 | LEGACY | SM-X520-6e5d7b239e5d39c3
```

Without that backfill this migration would have orphaned every enrolled device on
its next re-enrolment — the precise failure the chunk exists to prevent.

#### Decisions taken during implementation

| # | Decision | Rationale |
|---|---|---|
| D97 | Identity is a **set of identifiers**, matched on any known one, rather than a single `serial_number` | A device's reported identity is not a constant — this fleet proved it twice. Single-key matching forks a new record every time the key moves, and the fork silently drops the group membership driving the policy stack. A set also absorbs a future identity source without another protocol change. |
| D98 | Matching resolves by **identifier kind priority**, not the order the agent listed them | A device reporting both a real serial and an old fallback must land on the same record every time, whichever way round it sends them. Order-dependence here would be a bug that only appears on some devices. |
| D99 | An ambiguous match is **reported, never merged automatically** | Two records matching one device means the fleet already holds duplicates, which wants a human decision. Merging two histories on a guess is not something to do as a side effect of a check-in, and it cannot be undone. |
| D100 | An identifier already held by another device is **never reassigned** | Silently moving it would change which record a third device resolves to. The fix for a genuine duplicate is a deliberate merge. |
| D101 | The migration **backfills every existing serial as a `LEGACY` identifier** | Preserves current matching exactly, whatever that string happens to be. Skipping it would orphan every enrolled device on its next re-enrolment. |
| D102 | `identifiers` is **optional** on the enrolment request, and unknown kinds are kept rather than rejected | A fleet whose devices go dark for weeks cannot be upgraded before it is allowed to enrol, and a newer agent reporting a source this server has not heard of is still supplying usable identity. |

### ✅ Chunk 14 — Single persistent enrollment token, short-lived QR (COMPLETE)

Operator requirement: exactly **one persistent enrollment token** exists at a time
(retire-and-replace when a new one is needed, never two live at once). The console
never displays that token's raw secret. Instead, "Generate QR" mints a **15-minute
signed derivative** of it — the only thing ever shown as a scannable code — so a
leaked QR image bounds the exposure to 15 minutes regardless of how long the
persistent token itself lives.

**Decided with the operator before implementation:**

| Decision | Choice | Rationale |
|---|---|---|
| Mechanism | **Stateless signed token** (Option B), not a database child row (Option A) | Mirrors `CsrfGuard`, already reviewed in this codebase. Zero new rows per "Generate QR" click, which will be clicked routinely for the system's life — Option A would grow `enrollment_token` forever. Revocation is automatic: verification re-checks the primary at the moment of use, not at mint time, so no cascade-revoke logic is needed. |
| Uses per QR | **Unlimited within the 15-minute window** | Matches enrolling a batch of tablets in one sitting. A leak is bounded by time, not device count. |
| Console scope | **Replace** the existing multi-token UI with a single active-token panel | Matches the operator's model exactly. The old CRUD endpoints and ad-hoc `EnrollmentToken` rows are untouched at the API/DB layer — `scripts/dev_enroll.py` and the test suite keep working unchanged — they simply stop being console-managed. |

**Property, not a question:** retiring the primary invalidates every QR derived from
it immediately, including one mid-scan. Verification re-validates the primary's
`is_usable()` on every use.

1. **Model + migration** — `EnrollmentToken.is_primary: bool`, with a **partial
   unique index** (`is_primary = true AND revoked_at IS NULL`) so "at most one live
   primary" is a database guarantee, not an application hope. New setting
   `enrollment_qr_ttl_seconds` (default 900), following the existing
   `checkin_interval_seconds` / `csrf` TTL pattern.
2. **`app/security/enrollment_qr.py`** — `EnrollmentQrGuard.load_or_create(pki_dir)`
   mirroring `TokenVault`/`CsrfGuard`'s key-file pattern exactly
   (`pki/enrollment_qr.key`, `0o600`). `issue(primary_id) -> str` produces
   `{primary_id}.{issued_at}.{signature}`; `verify(token, now) -> uuid.UUID` checks
   the signature and the 15-minute age, raising a typed error otherwise.
3. **Service layer** (`app/services/enrollment.py`) — `get_primary_token`,
   `retire_and_create_primary` (revokes any existing primary and creates the new one
   in one call, matching "it can be retired and a new one made"), and
   `mint_qr_secret`. `resolve_token` tries the QR-guard format first; on a format or
   signature mismatch it falls through to today's hash lookup **unchanged**, so every
   existing token, script and test keeps working.
4. **API** — `GET/POST /api/v1/enrollment-tokens/primary`,
   `POST /api/v1/enrollment-tokens/primary/qr`. The existing CRUD endpoints stay,
   for automation.
5. **Console** — `enrollment.html` rewritten to one panel: the active primary (or an
   empty state), a "Retire & create new" form, and "Generate enrollment QR", which
   mints a fresh secret and renders it through the existing QR-rendering code
   (`_render_token_qr`), stating the 15-minute expiry plainly.
6. **Tests** — `enrollment_qr.py` unit tests (issue/verify, expiry, tampered
   signature, wrong primary id, primary revoked mid-window); service tests (atomic
   retire-and-create, the partial-unique-index guarantee, unlimited use within the
   window, an expired QR rejected, legacy tokens unaffected); console tests (empty
   state, the two actions, the old multi-token form gone).
**370 server tests** (was 339), all new tests exercising real behaviour rather
than mocked internals, plus a full live pass against the running stack through real
nginx + TLS:

```
1. no primary exists            -> null
2. create the primary           -> expires_at 2076-08-20   (the +50y lifetime)
3. mint a QR secret             -> secret + 15-minute expires_at
4. enrol device A with the QR   -> 201
5. enrol device B, SAME QR      -> 201   (unlimited within the window, as decided)
6. use_count after 2 enrolments -> 2     (counted against the primary, for free)
7. retire the primary           -> 200
8. the SAME still-time-valid QR -> 401   (retiring kills a live QR immediately)
9. mint a QR with no primary    -> 409 "no active enrollment token; create one first"
10. primary is null again       -> confirms revoke, not merely "inactive"
11. create a fresh primary      -> retire-and-replace cycle complete, live
12. both devices appear         -> in /api/v1/devices, ready for policy assignment
```

Step 8 is the property the whole design rests on, proven against the real
database rather than only asserted in a unit test: the QR secret used in step 5
was still comfortably inside its 15-minute window when step 7 retired the primary,
and step 8 shows it dead anyway — because verification re-checks the primary's
`is_usable()` on every use, not at mint time. No cascade-revoke code exists, and
none was needed.

Expiry-by-time-elapsing itself is verified at the unit level
(`tests/test_enrollment_qr.py`, `EnrollmentQrGuard.verify(..., now=...)`) rather
than by a real 15-minute wait — the same approach already used for the CSRF
token's TTL.

Two of the three requirements needed no new work to confirm: **device visibility
for policy assignment already existed** (the dashboard and policy pages), and the
console's `.danger` button styling from the device-deletion feature was reused
as-is for "Retire without replacing".

### ✅ Kiosk / lock task (F6) — COMPLETE, hardware-validated

**Starting state: half-built.** `setLockTaskPackages` is called, so a kiosk app is
*permitted* to enter lock task — and nothing ever starts it. No `startLockTask`, no
`setLockTaskFeatures`, no launch-into-lock-task. Setting `kiosk_package` today
configures an allowlist and produces no visible effect.

**Kiosk is the one feature that can lock us out of the tablet**, and `adb` has
dropped five times today. So the order is inverted: prove the escape before the
entry, and never engage on ATAK first.

#### Contracts verified before writing code (§6)

| Fact | Consequence |
|---|---|
| `setLockTaskFeatures` defaults to **`GLOBAL_ACTIONS` only**; omitting a flag disables it | The power menu is already default. Notifications and keyguard must be passed *alongside* it, not instead. |
| From Android 14, **features and packages are one policy** — "a failure to apply one will result in a failure to apply the other" | On 16 both must succeed together; a partial apply is not a state to design for. |
| `ActivityOptions.setLockTaskEnabled(true)` + `startActivity` launches a **third-party** app into lock task | ATAK never has to cooperate or call `startLockTask` itself. |
| It throws `SecurityException` unless `isLockTaskPermitted(pkg)` | Check first, so the failure is a legible message rather than a crash. |
| **"Doesn't affect activities already running — relaunch to run in lock task mode"** | Permitting a running ATAK does nothing. It must be relaunched. |

#### Decisions taken with the operator, before implementation

| Decision | Rationale |
|---|---|
| The agent becomes the home screen **only while kiosk is active**, via `setPersistentPreferredActivity`, cleared when it is not | Without it, escaping lock task drops the user on the Samsung launcher with full access. Reversible, so D55/F6 hold: the agent is not a launcher, it is temporarily standing in as one. |
| Lock-task features: **`GLOBAL_ACTIONS` + `NOTIFICATIONS` + `KEYGUARD`** | The power menu keeps a field device recoverable without a hard reset; notifications matter because ATAK alerts do; the keyguard keeps a `PASSWORD` policy meaningful, which it would not be if the device never locked. Home and overview stay **off** — allowing them defeats the point. |
| Kiosk **re-engages after reboot** | A kiosk that stops being one after a restart is not a kiosk. |

**Proven on `SM-X520`, both directions.**

```
engage   mLockTaskModeState=LOCKED
         mLockTaskPackages u0:[org.takmdm.agent, org.takmdm.testapp]
         topResumedActivity org.takmdm.testapp/.MainActivity

escape   HOME            -> stays in the kiosk app
         RECENTS         -> stays in the kiosk app
         launch launcher -> stays in the kiosk app

release  mLockTaskModeState=NONE, allowlist empty, ~15 s
         HOME -> com.sec.android.app.launcher   (home preference cleared)
```

Released **by policy alone in about 15 seconds**, no `adb` needed — which is the
escape route that matters, because a stranded tablet in the field has no cable.

#### The constraint that reshaped the design

The first engage attempt failed, and the agent said exactly why:

```
kiosk: could not configure lock task -
  Cannot use LOCK_TASK_FEATURE_NOTIFICATIONS without LOCK_TASK_FEATURE_HOME
```

**Neither document consulted mentions this.** It looks like it forces a hole in the
kiosk — and it does not, *because* of the home-screen decision taken beforehand:
with `addPersistentPreferredActivity` pointing HOME at the kiosk app, enabling HOME
returns the user to the kiosk instead of the launcher. The two choices turned out to
depend on each other, and the ordering matters — home is pointed first, or there is
a window where HOME is live and still aimed at the system launcher.

Also confirmed on the same failure: features and packages really are one policy from
Android 14. The rejected feature set left `mLockTaskPackages` **empty** rather than
half-applied, exactly as documented.

#### Escape ladder, all verified

1. **Remove `kiosk_package`** — ~15 s, clears lock task, allowlist and home preference.
2. **`adb shell am task lock stop`** — "End the current task lock."
3. `adb shell dpm remove-active-admin <component>`.
4. Factory reset.

There is no remote `stopLockTask`; clearing the allowlist is what ejects a locked app.

1. **Prove the exit first**, on an unlocked device: clearing `kiosk_package` releases
   lock task and restores home, plus the documented `adb` fallback for a stuck
   tablet. Nothing gets locked until this is written down.
2. **Engage** — permit, set features, verify `isLockTaskPermitted`, then relaunch
   the app into lock task. Report clearly when the package is absent.
3. **Home takeover** — `setPersistentPreferredActivity` while kiosk is set,
   cleared when it is not.
4. **Disengage** — release lock task, clear the allowlist and the home preference.
   Tested in both directions, because one-way convergence has been the recurring
   bug all session.
5. **Persistence** — re-engage on boot and after the app is force-stopped.
6. **Tests** — server-side spec and merge, agent-side where it is testable.
7. **Prove on hardware** with `org.takmdm.testapp`. ATAK only once the exit path
   has been demonstrated twice.

### ✅ StrongBox question answered (2026-09-01)

Asked of the key itself rather than inferred from what generation attempted:

```
device key -> TRUSTED_ENVIRONMENT (TEE), insideSecureHardware=true
StrongBox present on this device = false
```

`SM-X520` (Exynos 1580) has no StrongBox — the feature list agrees, advertising
`hardware_keystore=300` and no `strongbox_keystore`. **D56 behaved exactly as
written:** StrongBox attempted, TEE used, and never a silent drop to a software
key. The key is inside secure hardware and non-exportable, which is the property
the design actually depends on.

`KeyInfo.getSecurityLevel()` is the only call that separates StrongBox from the
TEE; `isInsideSecureHardware()` answers the weaker "not software" question and
cannot distinguish them.

⚠️ **This is one model on one SoC.** `SM-G736U1` (Snapdragon) and `SM-X828U`
(MediaTek) are different silicon and must be asked separately — R5 exists precisely
to stop this being extrapolated. Nothing needs changing for a device that does have
StrongBox; it will simply be used.

### ✅ Marketplace (F4) and `persist` — both proven on hardware

**F4 end to end on `SM-X520`**, driving the agent's real UI rather than simulating
a selection:

| Step | Result |
|---|---|
| Optional entry appears under `available`, not `required` | ✅ |
| **Not** installed on its own | ✅ verified by collected log — the file id appears nowhere |
| User taps the offer | ✅ `placed …/atak/imagery/Google_Hybrid.xml (327 bytes)` |
| Server records what the user took | ✅ `Google Hybrid map source`, with `applied_at` |
| Untick | ✅ **file left in place** — deployment is write-only |
| Delete it, tick again | ✅ re-pushed, so the record was forgotten rather than the file abandoned |

**`persist` proven by differential test.** Both files deleted in the same breath,
one reconcile pass, opposite outcomes decided purely by the flag:

```
4de83813 already placed at /sdcard/atak/DTED; not persisted, leaving it
39c93edb is persisted but missing or incomplete at /sdcard/atak/imagery; replacing
  → placed …/atak/imagery/Google_Terrain_NOPOI.xml (388 bytes)
```

**F1–F6 are now all satisfied, and F1–F5 are hardware-proven.** Only F6 (kiosk)
remains unexercised on a device.

#### A display bug worth the fix

The catalogue rendered a 388-byte file as **"0 KB"** — integer division, and the
catalogue mostly carries small config files, so the common case read as "there is
nothing to download". Now `327 bytes` / `KB` / `MB`.

### ✅ Zip extraction into ATAK directories (COMPLETE, hardware-validated)

A DTED archive (12.5 MB compressed, ~104 MB unpacked) extracted by policy into
`/sdcard/atak/DTED`, landing in ATAK's expected layout:

```
/sdcard/atak/DTED/w125/n39.dt2  n40.dt2  n41.dt2  n42.dt2
  25,981,042 bytes each; sha256 of n41.dt2 identical to the archive entry
```

**F5 is now proven on hardware**, and the destination guard added an hour earlier
caught the path as given (`/atak/DTED`) and named the one that works.

#### Archiver metadata is skipped

`__MACOSX` resource forks extracted alongside the data. They are an artifact of the
tool that built the zip, not anything the operator chose to ship, and every data
package zipped on a Mac carries them — which for ATAK packages is most of them.
Now dropped, with the count logged rather than silently altering an archive's
contents:

```
extracted w125.zip into /storage/emulated/0/atak/DTED (skipped 5 archiver metadata entries)
```

#### Operational note earned the hard way, again

The destination guard did not fire on first use — **the container was running the
old image.** Python changes need `docker compose up -d --build`, which is the first
entry in the operational notes, and it still cost a wrong result and a confused
minute. The failure looks exactly like the code being wrong.

### ✅ File placement into ATAK directories (COMPLETE, hardware-validated) — closes R1

An ATAK custom map source pushed by policy to `/sdcard/atak/imagery`, landing
**byte-identical** on `SM-X520`:

```
-rw-rw---- 1 u0_a283 media_rw 388 Google_Terrain_NOPOI.xml
sha256 on device == sha256 on server
```

Into ATAK's own directory tree, created by ATAK. **R1 is settled by demonstration**:
with all-files access granted once at provisioning, the agent writes into another
app's external-storage directories. No Knox, no root, no `MANAGE_APP_OPS_MODES`.

#### Two bugs found by pushing on it

**A deleted file was never restored.** `applyFile` skipped whenever its own record
said the content had been placed, and never looked at the disk. Deleting the file
from the tablet left the MDM entirely unaware — device still `compliant`, required
file simply gone. That is the blocklist ratchet again in a different place: a record
of what once happened, presented as desired state. Now both halves are checked, and
verified on hardware:

```
39c93edb… was placed at /sdcard/atak/imagery but is gone; replacing
'/sdcard/atak/imagery' resolves to /storage/emulated/0/atak/imagery (all-files access: true)
placed /storage/emulated/0/atak/imagery/Google_Terrain_NOPOI.xml (388 bytes)
```

**`FileDeployer` had no logging at all** — the same gap as `AppInstaller`, and found
the same way: a remote log collection that should have explained a file push and
said nothing about it. Now logs the resolved path, whether all-files access is held,
and what is on disk *after* writing.

| # | Decision | Rationale |
|---|---|---|
| D121 | A file is redeployed when the **disk** disagrees, not only when the recorded hash does | Remembering that we placed a file is not the same as the file being there. A user deletes it, an app clears its directory — and a reconciler trusting its own memory reports compliant with the file missing. |
| D122 | Presence is checked by **existence and size**, not a full hash | Digesting every managed file on every check-in is real work on a tablet, and this already catches deletion and truncation. A content change still moves the recorded hash. |
| D123 | An absolute `dest_path` outside device storage is **rejected at publish**, naming the path that would work | `/atak/imagery` is how ATAK paths are written and resolves to the unwritable filesystem root. Caught on the server the operator is told immediately; caught on the device it is a permission error that explains nothing — the same reasoning as enforcing signature pinning at upload. |

### ✅ Blacklist: suppress apps that cannot be uninstalled (COMPLETE, hardware-validated)

Operator requirement: a blacklist that **uninstalls what it can and disables what it
cannot**, tested against Gmail, which this tablet only offers to "Disable".

Testing the existing `removed_packages` against it produced the sharpest failure of
the session. The agent logged **`com.google.android.gm removed`** — and Gmail was
still installed and still worked. `PackageInstaller` returned `STATUS_SUCCESS` for
what was really "the update was removed":

```
codePath     /data/app/~~i7dRm4g60Rnw…   →  /product/app/Gmail2
versionName  2026.08.10.963697514        →  2025.09.22.811856720
```

**The platform lied and the agent repeated it.** An operator would have believed
Gmail was gone from the fleet.

`blocked_packages` is now the blacklist proper:

| Package | Action |
|---|---|
| Ordinary app | uninstall, **verified afterwards**; if it survives, hide as fallback |
| Ships with the device | hide directly — skipping a downgrade that achieves nothing and reports success |

Verified on `SM-X520`, both directions:

```
blocking com.google.android.gm: ships with the device, hiding it
  → visible: 0   No activity found   installed=true hidden=true
no longer blocked, unhiding com.google.android.gm
  → visible: 1   com.google.android.gm/.ConversationListActivityGmail
```

#### Two further bugs found while proving it

**Blocking was a one-way ratchet.** Taking a package off the blocklist left it
hidden forever — there was no unhide anywhere. That is not desired state (D5), it is
a latch: every device that ever saw the policy stayed suppressed with nothing left
in the policy to explain why.

**A hidden package is invisible to the code managing it.** `getPackageInfo` throws
`NameNotFoundException` for a hidden app, so the loop that should have unhidden
Gmail could not find it and did nothing, silently. Suppression now queries with
`MATCH_UNINSTALLED_PACKAGES`.

| # | Decision | Rationale |
|---|---|---|
| D117 | System apps are **hidden, never uninstalled** | Uninstalling one strips its update, downgrades it, and reports success — a destructive no-op that also lies. Detecting `FLAG_SYSTEM` first avoids both. |
| D118 | **Every uninstall is verified** by re-querying afterwards | The status code is not the outcome. This is the specific mechanism by which the agent claimed Gmail was removed. |
| D119 | The agent unhides **only what it recorded hiding** | Something else may have hidden a package for its own reasons; unhiding it because our blocklist no longer mentions it would be undoing a decision that was never ours. |
| D120 | `removed_packages` **does not fall back to hiding** | Asking for removal and silently getting suppression is the same lie in a different place. The strict list reports failure so an operator who needs the storage back learns they have not got it. |

### ✅ App removal by policy (COMPLETE, hardware-validated)

Operator question: what happens when the MDM is told to remove an installed app?
Tested before building, and the answer was **not what an operator would expect**.

| Action | Result on `SM-X520` |
|---|---|
| Drop the app from `required_apps` | **Nothing.** Still installed — and correctly so: "no longer required" is not "must be gone". |
| Add it to `blocked_packages` | **Hidden, not removed.** Absent from `pm list packages`, still present in `pm list packages -u`. All 323 MB and its data stayed. |

So the only removal-shaped tool in the system silently kept the app. For reclaiming
storage or handing a device on, that is the wrong answer given quietly.

**Added `removed_packages`** to `APP_CATALOG` — uninstall outright, via
`PackageInstaller.uninstall` under Device Owner privilege, silently. Removed from
the tablet **~70 seconds** after the policy was published, gone from `pm list
packages -u`, device converged `state 11 acked 11 | compliant`.

| # | Decision | Rationale |
|---|---|---|
| D113 | Removal is **policy state, not a transient command** | "This device must not have X" is a property to converge on, so a tablet dark for three weeks removes it on return (D5). A command would fire once and be forgotten. |
| D114 | `removed_packages` is **separate from `blocked_packages`**, not a change to it | Hiding is reversible and preserves data; removing destroys it and reclaims storage. Collapsing them would mean an operator wanting a temporary restriction silently wiped the app. The spec now says outright that blocking does not remove. |
| D115 | Removals merge by **UNION** | Any one stacked policy saying "not this" is the restrictive answer. A strategy that let another policy drop the instruction would be a removal that silently never happens. |
| D116 | The agent **refuses to uninstall itself**, and refuses a package listed as both required and removed | Android would block the first anyway — an active device admin cannot be removed — but refusing in the agent names the reason instead of leaving an opaque platform failure. The second would otherwise install and remove the same app on alternate check-ins. |

### ✅ Chunk 12 — App install proven on hardware, including splits

**Installed and upgraded on `SM-X520`, by the agent, with no user interaction.**

```
installerPackageName  = org.takmdm.agent
initiatingPackageName = org.takmdm.agent
versionCode=1 -> versionCode=2      state 4 acked 4, compliant
```

The provenance is the proof: Android records the agent as both installer and
initiator, so this was `PackageInstaller` under Device Owner privilege and not an
`adb install`. The whole Chunk 4 pipeline ran end to end — upload, inspect,
content-address, resolve into desired state, download with hash verification,
session write, commit, report.

A disposable `org.takmdm.testapp` module was built for it (`agent/testapp/`):
single APK, no splits, `targetSdk 36`, showing its own version on screen so an
upgrade is confirmable by looking at the tablet rather than trusting a number.

#### Three findings, none of which the test suite could have produced

**1. An agent upgrade left the device unmanaged.** Replacing the APK kills its
processes and a foreground service does not come back; the agent handled
`BOOT_COMPLETED` but not `MY_PACKAGE_REPLACED`. Observed as **25 minutes of total
silence** after an `adb install -r` — and from the server that is indistinguishable
from a tablet that drove out of coverage. In the field this would have stopped
management on every device at the first agent update. Fixed, then **verified by
replacing the APK again and watching it revive itself**:

```
BootReceiver: restarting after android.intent.action.MY_PACKAGE_REPLACED
```

⚠️ A fetched summary claimed `MY_PACKAGE_REPLACED` is **not** exempt from Android
8's implicit-broadcast restrictions and would not reach a manifest receiver. **The
hardware says otherwise** — it is delivered only to the replaced app, so it is not
an implicit broadcast at all. Observation supersedes; see the platform reference.

**2. A successful install logged nothing.** The collectable log existed precisely
to explain installs on a device nobody can see, and the entire success path was
silent — "installed" and "skipped, already present" were indistinguishable. Now
logged, and it immediately paid for itself: `already at versionCode 2 (want 2);
skipping` is how the upgrade was confirmed as complete rather than stalled.

**3. Resumable download (D8) earned its keep.** Transfers were truncating around
1.15 MB during container churn; the agent resumed with `Range` and converged.
Verified the server was blameless first — a real mTLS client got the full artifact
with a matching hash, and a `Range` request at the agent's exact resume offset
returned bytes that reassembled to the correct digest. The design decision to make
downloads resumable was validated by a fault, not by a test.

#### ✅ Real applications, including a 7-part split install

The operator supplied genuine artifacts (`Test Files/`, gitignored — hundreds of
megabytes and not ours to redistribute). Both installed on `SM-X520`:

| App | Shape | Result |
|---|---|---|
| **ATAK 5.8.0.4** `com.atakmap.app.civ` | single APK, 107 MB, **v3**-signed, `targetSdk 35` | installed in **~75 s** |
| **Butterfly IQ 2.49.0** `com.butterflynetinc.helios` | **XAPK → base + 6 splits**, 323 MB | installed in **~420 s** |

Android's own record confirms every part landed:

```
splits=[base, config.arm64_v8a, config.en, config.xhdpi, dltools, firmware, quicktips]
installerPackageName=org.takmdm.agent
```

The agent's log narrates the whole thing, base verified first as the platform
contract requires:

```
installing com.butterflynetinc.helios versionCode 4595720
  base part verified (60651144 bytes)
  split part verified (29860146 bytes)   ... six splits ...
session 1992771275 opened for com.butterflynetinc.helios (7 part(s))
com.butterflynetinc.helios installed: versionCode 4595720 from 7 part(s)
```

**Three Chunk 4 decisions validated against real artifacts rather than fixtures:**
the hand-written AXML and signing-block parsers read production **v3**-signed APKs
(we had only ever seen v2); **D13**'s server-side XAPK unpacking split a real
308 MB archive into seven content-addressed parts; and content addressing meant the
already-installed apps were skipped rather than re-downloaded on every later pass.

⚠️ **The old `com.atakmap.app` entry is a synthetic fixture** — parts of
1,351 / 1,377 / 300 bytes from `tests/apk_fixtures.py`. The real package name is
**`com.atakmap.app.civ`**, so the two coexist without a signature-pinning clash.
Earlier notes implying ATAK was uploaded and installable referred to the fixture.

#### Decisions taken during implementation

| # | Decision | Rationale |
|---|---|---|
| D110 | The agent restarts itself on `MY_PACKAGE_REPLACED` as well as `BOOT_COMPLETED` | Without it an agent upgrade stops management until the next reboot, and the failure looks exactly like a device out of coverage — the worst kind to diagnose, because nothing is wrong at either end. |
| D111 | The install path logs its decisions, including the no-op | A diagnostic channel that goes quiet on success cannot distinguish "installed", "skipped" and "never attempted". It was built to explain installs and said nothing about them. |
| D112 | A disposable single-APK test app, rather than testing first with ATAK | ATAK is base + split + OBB, so a failure would have had three candidate causes. Isolating `PackageInstaller` meant the one bug found had one. |

### 🔜 Chunk 13 — Split-APK install (PLANNED)

The largest untested surface in the system, and the terminus of the entire Chunk 4
pipeline: upload → inspect → content-address → resolve into desired state →
download with hash verification → `PackageInstaller` session → commit → report.
Every stage of it is written, tested, and has never run on a device.

**Ordering decision: a small purpose-built APK first, ATAK second.** ATAK is already
uploaded and is the real target, but it is base + split + OBB — three variables at
once, one of which (OBB placement) is a known open risk (R2). Proving the install
path with a single-APK package isolates `PackageInstaller` from storage and split
handling, so a failure has one candidate cause instead of three.

1. **Pre-flight** — confirm the tablet is checking in, capture its current
   `state_version` / `acked_state_version`, and read the `apps` projection the
   server actually emits for it today. Establish the diagnostic channel before
   needing it (see below).
2. **Build a disposable test app** — a trivial second Gradle module producing a
   single-APK, no-splits, `targetSdk 36` package under our own control. Lets us
   choose the package name and version code, and re-publish a v2 to prove the
   *upgrade* path, which is a distinct behaviour from first install.
3. **Upload and verify server-side inspection** — package name, version code,
   `targetSdk >= 24`, signing certificate, and the content-addressed parts.
4. **Publish an `APP_CATALOG` policy requiring it**, assign to `SM-X520`, and
   confirm `state_version` bumps and the desired state carries hash, size and URL.
5. **Watch the install happen** — long-poll wake → check-in → download → session
   write → commit → `acked_state_version` advances and the app is on the tablet.
6. **Escalate to ATAK** — base + split in one session. Expect OBB to be absent;
   that is R2, not a regression.
7. **Record** — ✅ entries in `docs/ANDROID_PLATFORM_REFERENCE.md`, decisions and
   findings here, and update `HANDOFF.md`.

**Diagnostic channel, decided up front.** `adb` currently sees no device, so
`logcat` is not available. Unlike the enrollment work, that is survivable: the agent
already reports apply failures to the server (`apply_errors` → `compliance_detail`),
and `AppInstaller` puts the `PackageInstaller` status code and message into exactly
that field. So an install failure arrives as
`"<pkg>: status 4: INSTALL_FAILED_…"` on the next check-in. **This is the D79
principle paying off a second time** — the channel that ended the enrollment
deadlock is the one this chunk depends on. Restoring `adb` would still be strictly
better and should be taken if it is cheap.

**Hypotheses discharged before starting** (CLAUDE.md §4 — recorded so they are not
re-investigated):

* `AppInstaller.commitAndAwait` registers a `BroadcastReceiver` and blocks on a
  `CountDownLatch`. Receivers dispatch on the main looper, so a main-thread caller
  would deadlock and report every install as `"install timed out"` — precisely the
  misleading shape this project keeps hitting. **Checked: not present.**
  `SyncService` runs the reconciler on `Dispatchers.IO` and `SyncScheduler` in a
  `CoroutineWorker`; both are background threads and leave the main looper free.
* `Reconciler.reconcileApps` skips `role == "obb"` parts entirely — they are never
  downloaded and never placed. **Confirmed by reading, not a surprise:** this is R2
  still open, so ATAK will install without its OBB in step 6.

### 🔜 Web UI expansion — Chunks W1–W9 (PLANNED, 2026-09-01)

Operator request: build out the full console into eight top-level sections —
**Enroll, Manage, Policies, Apps, Content, Reports, Admin, Guides** — themed to the
ATLAS banner logo (dark navy ground, chrome-silver wordmark, electric-blue accent).

**Decisions taken with the operator before planning:**

| # | Decision | Rationale |
|---|---|---|
| DW1 | **Stay server-rendered Jinja + vanilla JS.** No Node, no build step (D61 upheld). Modals/tabs/filtering done with a small hand-written `atlas.js`. | The console must keep shipping with `docker compose up` and stay readable by anyone who can read the Python. The interactions the spec needs (modal, tab bar, client-side table filter) are a few hundred lines of vanilla JS, not a framework. |
| DW2 | **Policy creator is a UI shell now.** Full category navigation is built; the four implemented policy types (`PASSWORD`, `RESTRICTIONS`, `APP_CATALOG`, `FILES`) get working forms, every other category renders a visible "not yet available" placeholder. | Wiring Knox / VPN / SCEP / OS-updates / geofencing each needs a spec, merge strategy, resolver support, an agent applier and tests — that is many chunks of backend work, not a web-UI task. The nav is designed so a category lights up when its backend lands. |
| DW5 | **The creator builds one composite "policy" (a *profile*) with the categories as tabs**, not several loose policies. Internally a `PolicyProfile` owns one single-concern child `Policy` per configured category; the UI tabs edit those children, and the profile is assigned to devices as a unit. Decided with the operator, 2026-09-02, overriding the earlier "multiple policies + shared tag" proposal. | The operator's model — matching the commercial MDMs they run — is one named profile that bundles password + restrictions + apps + … , picked through an organised tabbed layout. Keeping the single-concern typed `Policy` + merge registry *underneath* means the resolver, stacking view, provenance and per-field merge all keep working unchanged; the profile is a bulk editor and bulk-assignment wrapper over them, not a replacement. Cost: a `PolicyProfile` table, a `ProfileAssignment` table, and resolver expansion — spread over W4 (model + creator + editor) and W4b (assignment + resolution). |
| DW3 | **New 8-section nav replaces the current one** (Devices / Policies / Enrollment). Existing pages move under the new sections and are restyled to the new shell; old routes 301/302-redirect to their new homes. | One console, not two. Reuse the working device/policy/enrollment/QR/log code rather than reimplement it. |
| DW4 | Shared CSS and JS move to `app/web/static/` served by `StaticFiles`; markup reuse via a `_macros.html` include. | The single inline `<style>` in `base.html` will not scale to eight sections. One stylesheet, one macro library, mounted once. |

**Resolved (DW5, 2026-09-02):** the creator builds one composite **profile**
(`PolicyProfile`) whose tabs are single-concern child `Policy` rows — see DW5
above. W4 covers the model, creator page and tabbed editor; W4b covers profile
assignment and resolver expansion.

**Cross-cutting rules for every W chunk:** all existing tests stay green (the
console suite in `tests/test_admin_ui.py` asserts on rendered text and nav labels —
update those assertions as pages move); every new route registered under the
`_admin` guard list in `app.main` (DW-inherits D70); every form carries
`csrf_field()`; SOLID — a page's data-gathering is a service function, the template
only renders (CLAUDE.md §5).

---

#### ✅ W1 — Console shell & ATLAS design system (COMPLETE)

**375 server tests (was 370).** Delivered:

- `app/web/static/atlas.css` — one stylesheet for the whole console. Light-default
  palette with a `prefers-color-scheme: dark` override, colours from the banner
  (navy `#0a1420` ground, silver `#c9d4e0` wordmark, electric-blue `#2f7fe0`
  accent, cyan `#3fc8f0` highlight). **Every legacy class name from the old inline
  `<style>` is preserved** (`.panel`, `.pill`, `.stat`, `.checks`, `.row`,
  `.banner`, `.mono`, `.sub`, `.logdump`) so the existing device/policy/enrollment
  templates render unchanged; new primitives added for tabs, modal, toolbar,
  left-rail layout, section stub.
- `app/web/static/atlas.js` — hand-written, zero dependencies (DW1). Opt-in via
  `data-` attributes: `data-modal-open`/`data-modal-close`, `data-tabs` +
  `data-tab-panel` (active tab persisted to the URL hash), `data-filter` table
  search, `data-sortable` column sort, `data-confirm` submit guard.
- `app/web/static/atlas-mark.svg` — the ATLAS delta mark, referenced with `<img>`
  not inline, so `"<svg"` in a response still unambiguously means "a QR rendered"
  (two enrollment tests depend on that).
- `app/web/templates/_macros.html` — `csrf_field`, `page_header`, `empty_state`,
  `stub`, `tabs`, `modal`.
- `base.html` rewritten: ATLAS brand bar, **eight-section nav** (Enroll, Manage,
  Policies, Apps, Content, Reports, Admin, Guides) with active-state, `StaticFiles`
  linked. Auth-disabled banner and `?error=` banner preserved verbatim.
- `StaticFiles` mounted at `/static` in `app.main` — a mount, so outside the
  `_admin` guard (CSS/JS are not sensitive) and outside the OpenAPI schema. Not
  reachable on the device port (nginx default-deny already covers it).
- Five new section routes (`/apps`, `/content`, `/reports`, `/admin`, `/guides`)
  render `section_stub.html`, each naming the W-chunk that will deliver it.
  Registered on `web_routes.router`, so they inherit the `_admin` auth+CSRF guard.
- Existing pages moved under the new nav: `devices.html`/`device_detail.html`/
  `device_log.html` → `manage`; `enrollment.html`/`token_qr.html` → `enroll`.
  Paths are unchanged (`/`, `/policies`, `/enrollment`) — a deviation from the
  plan's "redirect `/enrollment` → `/enroll`", taken to avoid churning ~20 passing
  enrollment tests for a cosmetic URL; revisit if the operator wants the tidy URL.

New tests (`tests/test_admin_ui.py`): all eight sections reachable, nav marks
exactly the active section, a pending section names its chunk, `atlas.css` /
`atlas.js` served.

⚠️ **Docker:** `app/` is `COPY`'d into the image (no bind mount), so seeing this
in the running stack needs `docker compose up -d --build` per the operational
notes.

##### Original plan

1. `app/web/static/atlas.css` — colour tokens from the logo (navy `#0a1522` ground,
   panel `#111f30`, silver ink, electric-blue `#1f6fd6` accent, cyan `#33c6f4`
   highlight; light-mode palette too), typography, panel/table/button/pill/tab
   primitives migrated out of `base.html`. Mount `StaticFiles` at `/static`.
2. `app/web/static/atlas.js` — `modal(id)`, tab-bar behaviour, `tableFilter(input,
   table)`, `confirmSubmit`. No dependencies.
3. Save the banner logo to `app/web/static/atlas-banner.png`; header uses it.
4. `app/web/templates/_macros.html` — `page_header`, `panel`, `stat_row`, `tabs`,
   `data_table`, `modal`, `empty_state`, `csrf_field`.
5. Rewrite `base.html`: ATLAS branding, eight-section top nav with active-state,
   identity/auth banner preserved, links to `atlas.css` / `atlas.js`.
6. Route map + redirects in `routes.py`: `/` → **Manage**, keep `/policies`,
   `/enrollment` → `/enroll` (302), add stub routes for `/apps`, `/content`,
   `/reports`, `/admin`, `/guides` rendering an empty section shell.
7. Update `tests/test_admin_ui.py` chassis assertions (brand string, nav labels);
   add tests that every section route returns 200 and the nav marks the right tab.

#### ✅ W2 — Enroll & Manage (COMPLETE)

**381 server tests (was 375).** Delivered:

- **`Device.name`** — nullable friendly name (migration `a1c3e5f7b9d2`, up/down
  verified on SQLite). `PATCH /api/v1/devices/{id}` (new, `DeviceUpdate` schema)
  and a console rename form (`POST /devices/{id}/rename`, blank clears it). The
  console falls back to the serial everywhere the name is unset.
- **`app/services/fleet.py`** — `fleet_rows(session)` returns one `FleetRow`
  (device + sorted names of every policy reaching it) per device, from two
  queries, excluding archived policies and disabled assignments to match what the
  resolver applies. The list view deliberately does not resolve the effective
  policy per device — it answers "which policies apply", not "what value won".
- **`manage.html`** (replaces `devices.html`) — the fleet table with the columns
  the operator asked for: **Name** (name, with serial as a mono sub-line when a
  name is set), **Serial**, **Model**, **OS / Agent**, **Policies** (count pill +
  names), **Convergence** (acked/target, D28), **Compliance**, **Last check-in**.
  Client-side search (`data-filter`) and column sort (`data-sortable`) from
  `atlas.js`.
- **`enroll.html`** (replaces `enrollment.html`) — restyled to the shell; the QR
  generator now carries the **Wi-Fi SSID / password / security fields inline**, so
  one action from the landing page produces the QR-with-Wi-Fi (still rendered by
  `token_qr.html`, unchanged). Retire / replace moved into a panel with
  `data-confirm`.
- `device_detail.html` — shows the friendly name as the heading (serial demoted to
  a sub-line), rename form at the top; everything else (stacking view, conflicts,
  apps, files, lifecycle, identity, logs) unchanged.

New tests: policy names appear in the fleet row, filter/sort markup present,
rename round-trips and clears, the PATCH endpoint, Wi-Fi fields on the enroll QR
form.

##### Original plan

1. **Enroll** (`enroll.html`, from `enrollment.html`): QR is the centrepiece —
   large panel, Wi-Fi SSID/password/security inline on the same page, primary-token
   status and retire/replace beneath. Restyle to the new shell.
2. **Manage** (`manage.html`, from `devices.html`): device table with the columns
   the operator asked for — **name** (model + serial, serial as the mono sub-line),
   **serial**, **model**, **policies** (count + names of policies reaching the
   device, from the effective-policy `considered` list), **OS / agent version**,
   plus state / convergence / compliance / last check-in already present.
3. Client-side search/filter box over the table (`atlas.js#tableFilter`), and
   column sort.
4. `app/services/fleet.py` — a `fleet_rows(session)` service that assembles the
   table (device + reaching-policy names) so the route stays thin.
5. **Device detail** (`device_detail.html`): restyle to the shell; keep stacking
   view, identifiers, logs, retire/delete exactly as they behave now.
6. Tests: new columns render, policy names show for an assigned device, filter box
   present, enroll page shows QR + Wi-Fi fields.

#### ✅ W3 — Policies list & New Policy modal (COMPLETE)

**387 server tests (was 381).** Delivered:

- **`Policy.is_template`** — bool, `NOT NULL DEFAULT false` (migration
  `b2d4f6a8c1e3`, explicit `server_default` per D35; up/down verified on SQLite).
  A template is a blueprint: the resolver (`gather_assignments`) and the fleet
  table both skip it, and both assignment endpoints + `create_assignment` now
  return **409** if handed one (`_reject_template`).
- **`app/services/policy_admin.py`** — `list_tab` (device / templates / archived),
  `clone` (copies type + description + latest spec into a fresh v1 — "save as
  template" and "use template" are the *same* operation, so editing one never
  changes the other), `archive`, `restore` (both invalidate caches).
- **API**: `POST /api/v1/policies/{id}/restore`, `POST /api/v1/policies/{id}/clone`
  (`PolicyClone` schema), `is_template` on `PolicyCreate`/`PolicyRead`. `archive`
  now delegates to the service.
- **`policies.html`** — three tabs (`data-tabs`), a **New Policy** button opening a
  modal with two choices: "Create from scratch" → `/policies/new`, "Use a
  template" → jumps to the Templates tab (new `hashchange` handler in `atlas.js`
  makes `href="#tab-templates"` switch the tab bar with no reload). Templates tab
  has a per-row "create a policy from this template" form; Archived tab has
  per-row Restore.
- **`policy_new.html`** — the create-from-scratch form (moved off the list page;
  W4 replaces it with the guided creator) with a "save as template" checkbox.
- **`policy_detail.html`** — template/archived badges; a template shows a
  "create a policy from this template" form instead of the assign panel; new
  **Manage** section with Archive/Restore and "Save as template".
- Console routes: `/policies/new`, `/policies/{id}/archive`, `/{id}/restore`,
  `/policies/clone` (takes `source_id` as a form field so the modal dropdown and
  the detail-page button share one endpoint).

New tests: three tabs + button present, create-from-scratch page renders, save-as-
template produces a flagged template, using a template yields an independent
policy with the copied spec, a template is refused for assignment (409), archive
removes a policy from the stack and restore brings it back.

##### Original plan

1. `policies.html`: three tabs — **Device policies**, **Templates**, **Archived**.
2. Model: `Policy.is_template: bool` + migration (archived already exists as
   `archived_at`). Templates are excluded from the effective-policy resolver.
3. **New Policy** button → `modal`: "Create from scratch" (→ W4 creator) or
   "Use a template" (pick a template → clones its latest spec into a new policy).
4. Archived tab: list archived policies, **Restore** action (clears `archived_at`);
   **Archive** action on the detail page (D20 — never delete).
5. Templates tab: list, "Save as template" action on a policy, "Use" action.
6. `app/services/policy_admin.py` — clone-from-template, archive, restore, list-by-tab.
7. Tests: tab switching, template clone produces an independent policy, archive/restore
   round-trip, archived policy stops reaching devices.

#### ✅ W4 — Composite policies (profiles): model, creator, editor (COMPLETE)

**398 server tests (was 387).** Delivered per DW5:

- **Model** — `PolicyProfile` (name unique, description, created_by, archived_at)
  + `Policy.profile_id` (nullable FK, `ON DELETE CASCADE`) + `Policy.profile_section`
  (the catalog category key). Migration `c3e5g7i9k1m3` uses `batch_alter_table` so
  the new FK on the existing `policy` table applies on SQLite too; up/down verified.
- **`app/policies/creator_catalog.py`** — the operator's full category tree (16
  categories, subtopics as display hints). Four wired to real types (`password`,
  `restrictions`, `app_management`, `file_management`); the rest carry
  `policy_type=None` and render as placeholders. Adding/lighting a category is a
  one-line change here (OCP).
- **`app/services/profiles.py`** — `create_profile` (one child `Policy` per
  non-empty wired section, named `"<profile> · <label>"`), `upsert_section`
  (publishes a new child version, no-ops if unchanged), `remove_section`,
  `archive`/`restore` (invalidate every section's caches).
- **API** — `app/api/routers/profiles.py`: `GET/POST /api/v1/profiles`,
  `GET /api/v1/profiles/{id}`, `PUT/DELETE …/sections/{key}`,
  `…/archive`, `…/restore`. `GET /api/v1/policies` now hides profile sections by
  default (`include_sections=true` to see them).
- **Console** — `/policies/new` is the guided creator (`profile_editor.html`,
  `mode="new"`): a left rail of categories (reusing the `data-tabs` machinery),
  one JSON spec box + live merge reference per wired category, placeholders for
  the rest, one "Create policy" submit. `/profiles/{id}` is the same template in
  `mode="edit"` — each category is its own save form (publish a section version),
  with per-section remove and profile archive/restore. `/policies/new/single`
  keeps the old single-concern form for advanced use.
- **Guards** — a profile section cannot be assigned directly (`_reject_template`
  now also covers `profile_id`, 409) and is excluded from the standalone policy
  list (`policy_admin.list_tab`, the API, and `effective_policy.gather_assignments`).
- **`policies.html`** — the Device policies tab lists profiles (badge
  `policy`) above single-concern policies, each linking to its editor.

New tests: creator lists every category, placeholder says "not available yet",
create-via-API and create-via-console-form, children made only for filled
sections, profile shown / children hidden on the list + API, edit publishes a
version, add-section-later, remove-section, section refused for direct assignment,
editor page renders with archive.

**W4b (profile assignment + resolver expansion) is the next chunk** — a profile
currently reaches no device because nothing assigns it yet.

##### Original plan

Per **DW5**: a "policy" the operator creates is a `PolicyProfile` bundling
single-concern child `Policy` rows, one per configured category, edited through a
tabbed layout. This chunk builds everything except assignment (that is W4b).

1. **Model + migration** — `PolicyProfile` (id, name unique, description,
   archived_at, created_at, created_by) and `Policy.profile_id` (nullable FK,
   `ON DELETE CASCADE`). A `Policy` with `profile_id` set is a *section* of a
   profile: hidden from the standalone policy list, managed only through the
   profile. `profile_id IS NULL` is today's standalone policy, unchanged.
2. `app/policies/creator_catalog.py` — declarative category/sub-topic tree exactly
   as the operator listed it (Password; Restrictions basic/advanced; Knox
   *placeholder*; Periodic sync; App Management → required apps,
   blocklist/allowlist, app catalog, app configs, app permissions, app
   notifications; Networks → wifi, vpn; Security → certificates, scep, global http
   proxy, web content filtering, os updates; Accounts → email, exchange
   activesync; Configurations → fonts, wallpaper, boot/shutdown animation;
   Customizations → support message, lock screen; Network data-use mgmt; App usage
   mgmt; File management; Tracking & fencing → location tracking, geofencing;
   Android Enterprise compliance *placeholder*; Troubleshooting → app logs, remote
   access). Each node maps to a real policy type (`PASSWORD`, `RESTRICTIONS`,
   `APP_CATALOG`, `FILES`) or is flagged `placeholder`.
3. `app/services/profiles.py` — `create_profile(name, sections)`,
   `upsert_section(profile, category, spec)` (publishes a new child-policy
   version), `list_profiles`, `archive`/`restore` (cascade to children).
4. `profile_creator.html` — full-page: left-rail category nav, main pane renders
   the registry-driven form for a wired category (fields + live merge-strategy
   reference, as `policy_detail.html` does) or the placeholder panel. Name field
   at the top. Save → `create_profile`.
5. `profile_detail.html` — the same left-rail/tabs, each tab editing its child
   policy (publish new version), an "Advanced (JSON)" escape hatch per section
   (D64), and Archive/Restore. The Assign panel is added in W4b.
6. Console + API: `/policies/new` → the profile creator; `/profiles/{id}` →
   editor; profiles listed in the Policies "Device policies" tab alongside
   standalone policies with a **Profile** badge. `GET/POST /api/v1/profiles`.
7. Tests: catalog renders every category, creating a profile makes the child
   policies for wired sections only, a placeholder section cannot be submitted,
   editing a section publishes a version, child policies are hidden from the
   standalone list, archive cascades.

#### ✅ W4b — Profile assignment & resolution (COMPLETE)

**406 server tests (was 398).** Delivered:

- **`ProfileAssignment`** model + migration `d4f6h8j0l2n4` (mirrors `Assignment`:
  scope, one of device/group/tag, rank, enabled; `ON DELETE CASCADE` on all four
  FKs; single-target check constraint). Up/down verified on SQLite.
- **Resolver** — `gather_assignments` now also calls `_gather_profile_assignments`,
  which expands each `ProfileAssignment` reaching the device into one
  `AssignmentInput` per non-archived section, all at the profile assignment's rank
  and scope. Assignment id `profile:{pa}:{section}` keeps each section a distinct
  contributor. Archived profile / archived section drop out.
- **Invalidation** — `devices_targeted_by_profile_assignment`,
  `devices_affected_by_profile`, `invalidate_for_profile`;
  `devices_affected_by_policy` now also follows a section up to its profile's
  assignments, so `profiles.upsert_section` / `remove_section` wake the right
  devices. All routed through the existing `after_commit` doorbell (F3).
- **Bulk assignment (F2)** — `PUT /api/v1/profiles/{id}/targets` (reuses
  `PolicyTargets` / `PolicyTargetsResult`, replace semantics) and a console form
  on `profile_editor.html` (edit mode) with device/group/tag checkboxes + rank.
- **Fleet table** — `fleet.py` adds the **profile name** (not each section) to a
  device's "Policies" column when a profile assignment reaches it.
- **Stacking view** — no code change needed: a section's snapshot name is already
  `"<profile> · <section label>"`, so `device_detail.html`'s "Policies reaching
  this device" and per-field provenance read e.g. `Kiosk Profile · Password`
  with the profile assignment's scope and rank.

New tests: a profile assignment resolves every section; a profile out-ranks a
standalone policy on a `HIGHEST_RANK` field; unassign clears the sections;
archiving an assigned profile stops it; removing a section stops that section;
editing a section bumps the assigned device's `state_version`; profile name in the
fleet table; the console assign form works.

##### Original plan

1. **`ProfileAssignment` model + migration** — (id, profile_id, scope, device_id/
   group_id/tag_id, rank, enabled, created_at), mirroring `Assignment`.
2. **Resolver** — `gather_assignments` also collects `ProfileAssignment` rows
   reaching the device and expands each into one `AssignmentInput` per
   non-archived child policy, at the profile assignment's rank/scope. Provenance
   carries the profile name.
3. **Invalidation** — `invalidate_for_profile`, `devices_targeted_by` extended for
   profile assignments, wired through the existing `after_commit` wake (F3) so a
   profile edit propagates immediately.
4. **Bulk assignment UI** (F2) on `profile_detail.html` — pick devices / groups /
   tags, replace semantics, one action. `PUT /api/v1/profiles/{id}/targets`.
5. **Stacking view** (`device_detail.html`) — values contributed via a profile are
   labelled "via profile ‹name› → ‹section›" so provenance stays legible.
6. Tests: a profile assigned to a device resolves all its sections; rank ordering
   against standalone policies; unassign removes them; a profile edit wakes the
   parked long-poll; archived profile / archived section drop out.

#### ✅ W5 — Apps (COMPLETE)

**413 server tests (was 406).** Delivered:

- **`AppPackage.store_listed`** (`NOT NULL DEFAULT false`) + **`AppGroup`** /
  `app_group_member` (ordered many-to-many to `AppPackage`). Migration
  `e5g7i9k1m3o5`, up/down verified on SQLite.
- **`app/services/app_groups.py`** — list / get / create / rename / `set_members`
  (order-preserving, de-duped, unknown ids rejected) / delete.
- **`app/services/packages.py`** — `delete_package` (gathers digests, one cascade,
  then frees unreferenced blobs — looping `delete_version` double-deleted and
  warned).
- **API** — `PATCH /api/v1/packages/{id}` (`label`, `store_listed`),
  `DELETE /api/v1/packages/{id}`, and `app/api/routers/app_groups.py`
  (`GET/POST /api/v1/app-groups`, `GET/PATCH/DELETE /{id}`, `PUT /{id}/members`).
  `store_listed` added to `PackageRead`.
- **`apps.html`** — three tabs. **Local apps**: upload form (multipart, reuses
  `package_service.ingest`), table with package / label / latest version / parts /
  signing hash, per-row add-to-store and delete. **ATLAS store**: the
  `store_listed` subset, remove button. **App groups**: create form with package
  checkboxes, per-group member editor and delete. `/apps` is now a real route
  (removed from the pending-section stubs).
- **App-group → policy wiring (light)** — the profile editor's **App Management**
  section shows an "Insert an app group into `required_apps`" control; each button
  calls `atlasInsertAppGroup` (new in `atlas.js`), which merges the group's
  package names into the section's JSON spec, de-duping by package name. A
  convenience over the JSON editor (D64), not a spec change.

New tests: three tabs, upload lists a package, add-to-store shows it in the store
tab, delete removes it, app-group create/members/delete round-trip, the API
rejects an unknown package id, the profile creator offers the app-group insert.

##### Original plan

1. `apps.html`: tabs — **Local apps**, **ATLAS store**, **App groups**.
2. Local apps: list `AppPackage` + versions (version code/name, size, signing
   hash, split parts), upload form (reuses `packages` service), delete.
3. `AppPackage.store_listed: bool` (+ migration) — the ATLAS store tab lists the
   apps shipped with the deployment; toggle from the local-apps list.
4. `AppGroup` model (name, description, ordered `AppPackage` members) + migration
   + `app/services/app_groups.py` CRUD.
5. App groups tab: create/edit a group, add/remove packages.
6. Wire app-group selection into the W4 App Management category (assign a group
   rather than listing packages one by one).
7. Tests: upload lists a package, store toggle, app-group CRUD, group usable in a policy.

#### ✅ W6 — Content (COMPLETE)

**418 server tests (was 413).** Delivered:

- **`ManagedFile` deployment defaults** — `default_dest_path`, `default_persist`,
  `default_extract`, `default_extract_to`, `default_overwrite` (all nullable,
  migration `f6h8j0l2n4p6`). These are *suggestions* the policy editor will
  pre-fill; the authoritative destination/persist/extract for a placement still
  live on the FILES policy's `FileEntry` (that is where the data model puts them).
- **`app/services/content_admin.py`** — `content_rows` reads every non-archived
  FILES policy's latest-version `entries` back and, per managed file, lists every
  deployment it is part of (policy name + link, dest_path, tier, persist, extract,
  overwrite). `references(file_id)` powers the delete guard.
- **API** — `PATCH /api/v1/files/{id}` (name / description / the five defaults);
  defaults added to `ManagedFileRead`.
- **`content.html`** — upload form; one panel per file with its metadata, a
  "Deployed by" table linking each referencing policy/profile, and a collapsible
  edit form for the name and deployment defaults.
- **Delete guard (console only)** — `POST /content/{id}/delete` refuses and names
  the policies when any live FILES policy still binds the file. The **API**
  `DELETE` stays permissive on purpose: `test_deleted_file_is_reported_not_dropped`
  depends on a dangling reference being surfaced, not fatal — the console is the
  safety layer, the API the escape hatch.

New tests: content page lists files, shows the deploying policy + destination,
console delete refused while referenced / allowed when not, edit defaults
round-trips.

##### Original plan

1. `content.html`: table of `ManagedFile` — name, original filename, size,
   destination path, **persistent** flag, **zip-expand** flag + `extract_to`,
   overwrite rule, and which policies reference it.
2. Upload form (reuses `files` service).
3. Edit destination / persist / extraction settings (new small form → `files`
   service update path).
4. Delete (reference-checked — refuse if a live policy still binds it, name the policy).
5. `app/services/content_admin.py` — rows with referencing-policy names.
6. Tests: upload lists a file, edit persists the flags, delete refused while referenced.

#### ✅ W7 — Reports (COMPLETE)

**423 server tests (was 418).** Delivered:

- **`app/services/reports.py`** — a `REPORTS` registry of six report builders,
  each `(session) -> (columns, rows)`: **Fleet inventory**, **Convergence &
  compliance**, **Policy deployment** (policies + profiles, target counts),
  **Command history**, **App inventory**, **Marketplace selections**. `to_csv`
  serialises any of them. Adding a report is one registry entry (OCP).
- **Console** — `/reports` (catalogue) and `/reports/{key}` (generic `report.html`
  with client-side filter + sort, or `?format=csv` → a `text/csv` attachment).
  No new model or migration.
- **Physical telemetry** (battery / storage / signal) is deliberately absent and
  the page says so — the agent does not report those fields, so it is an agent +
  schema change, not a reporting one. Fleet inventory covers what devices send.

New tests: catalogue lists the reports, a report renders a table, CSV export has
the right content-type / disposition / header row, command history reflects a
queued command, unknown report 404s. (The W1 "pending section" test moved from
`/reports` to `/guides`.)

##### Original plan

1. `reports.html` — report catalog: **Fleet inventory**, **Policy deployment /
   convergence**, **Compliance**, **Command history**, **App inventory**,
   **File deployment / user selections**.
2. Each report = a service function in `app/services/reports.py` returning rows +
   columns; one generic `report.html` renders any of them.
3. CSV export per report (`?format=csv`).
4. Physical-stats report: render the inventory fields that exist today (model, OS,
   agent version, last check-in); **note in the UI** that battery/storage/network
   telemetry needs new agent-reported fields (out of scope — flag as a follow-up).
5. Tests: each report renders, CSV export returns text/csv with a header row.

#### ✅ W8 — Admin (COMPLETE)

**429 server tests (was 423).** Delivered:

- **Models** — `AppSetting` (key/value store for operator-editable config),
  `CustomAttribute` (name / type / description), `DeviceAttributeValue`
  (per-device). Migration `g7i9k1m3o5q7`, up/down verified.
- **`app/services/settings_store.py`** — a declarative `GROUPS` map (EULA, SMTP,
  Active Directory, SMS, geofencing defaults) with per-field kinds. `save_group`
  leaves a **blank secret field untouched** so a stored password need not be
  retyped; secrets are never rendered back into a form. ⚠️ Secrets are stored
  **plaintext** in `app_setting` — noted in the module and folded into R8.
- **`app/services/custom_attributes.py`** — attribute CRUD, `values_for_device`,
  `set_value` (blank deletes the row).
- **API** — `app/api/routers/admin_settings.py`: `/api/v1/custom-attributes` CRUD,
  `GET/PUT /api/v1/devices/{id}/attributes`.
- **`admin.html`** — tabs: **Certificates** (CA summary + the `DeviceCertificate`
  list with per-cert revoke), one tab per settings group (form-generated from the
  `GROUPS` spec), **Custom attributes** (define + delete), **Integrations** (Knox
  / Android Enterprise placeholders), **Environment** (env-backed settings shown
  read-only with their variable names).
- `device_detail.html` — a Custom attributes section: one save form per defined
  attribute. `/admin` is a real route now.

New tests: admin sections present, a certificate is listed and revocable, SMTP
settings save without echoing the password, a blank password keeps the stored
one, custom-attribute define → set on device → read back → delete, the API
rejects a bad attribute type.

**Jinja gotcha fixed:** a context dict keyed `"values"` — `grp.values` in a
template resolves to `dict.values` (the method), not the key. Renamed to
`current`.

##### Original plan

1. `admin.html` — sub-sections: **Enrollment tokens** (link to Enroll),
   **Certificates** (CA subject/validity, device-certificate list with revoke),
   **Knox settings** *(placeholder)*, **Android Enterprise** *(placeholder)*,
   **EULA**, **Email / SMTP**, **Active Directory**, **SMS**, **Geofencing
   defaults**, **Custom attributes**.
2. `AppSetting` key-value model (+ migration) + `app/services/settings_store.py`
   for the DB-backed settings (EULA text, SMTP, AD, SMS, geofencing defaults).
   Env-backed settings shown read-only with their variable name.
3. `CustomAttribute` model (name, type, description) + per-device values
   (`DeviceAttributeValue`), + migration; surfaced on the device detail page.
4. Certificate view reuses `revoke_device_certificates`; lists
   `DeviceCertificate` rows with serial, issued/expiry, revoked state.
5. Forms for each editable settings group, one service, one template partial each.
6. Tests: setting round-trips, custom attribute CRUD + shows on device page,
   certificate list renders, revoke works.

#### ✅ W9 — Guides (COMPLETE)

**434 server tests (was 429).** Delivered:

- **`app/web/markdown_lite.py`** — a ~120-line Markdown renderer (headings, fenced
  and inline code, bold/italic, links, ordered/unordered lists, blockquotes,
  rules, paragraphs). HTML-escapes first, so a stray `<` in a guide renders as
  text. No new dependency and no Docker rebuild — same call as the hand-written
  AXML and canonical-JSON parsers.
- **`app/services/guides.py`** — reads `app/web/guides/{howto,faq}/*.md`; a file's
  title is its first `# ` heading, its slug the filename minus a leading sort
  number. `release_notes_html()` renders `guides/release-notes.md`.
- **Content** — six how-to articles (enrol, build a policy, stacking, upload an
  app, deploy content, kiosk), two FAQ files (general, troubleshooting), and
  release notes covering the W1–W9 console overhaul.
- **Console** — `/guides` (tabs: How-to, FAQ, Release notes) and
  `/guides/{category}/{slug}`. `.prose` styles for rendered Markdown. The W1
  placeholder-shell machinery (`section_stub.html`, `_PENDING_SECTIONS`) is
  removed — every nav entry now leads to a real page.

New tests: guides page lists how-to + FAQ, a guide renders its Markdown (heading +
list), release notes render, unknown guide/category 404, `markdown_lite` escapes
HTML.

##### Original plan

1. `guides.html` — three tabs: **How-to**, **FAQ**, **Release notes**.
2. Content as Markdown files under `app/web/guides/{howto,faq}/*.md`, rendered with
   `markdown` (add to `requirements.txt`) through a safe renderer; an index built
   from front-matter titles.
3. Release notes: a curated `app/web/guides/release-notes.md` (seeded from the
   `PROJECT_STATE.md` changelog), newest first.
4. Seed a starter set: enrollment how-to, policy-stacking explainer, app upload,
   content deployment, kiosk, troubleshooting FAQ.
5. Tests: guide index lists articles, an article renders its Markdown, release
   notes page renders.

#### ✅ W10 — Form-driven policy editing (COMPLETE)

**439 server tests (was 434).** Operator request (with a Hexnode screenshot):
build policies with **typed controls — dropdowns, number fields, repeatable rows —
not a JSON textarea.**

Delivered:

- **Field metadata on the four specs** — `title` / `description` /
  `json_schema_extra` (`ui_group`, `ui_true`/`ui_false`, `ui_unit`, `ui_control`).
  `RESTRICTIONS` grouped "Device functionality" / "Network & communication" /
  "Display" like the screenshot; `PASSWORD` into "Strength" / "Lockout & expiry".
  Metadata-only — no behaviour change.
- **`app/policies/form_schema.py`** — `FormField` + `grouped_fields(type)` derives
  every control (bool → tri-state, int → number with min/max, IntEnum → dropdown,
  str → text with pattern, list → repeatable rows) plus a plain-English **merge
  hint** per field, all from the registered spec (Pydantic fields + the `Merge`
  annotation). No parallel descriptor.
- **`app/policies/form_parse.py`** — HTTP form multidict → raw spec dict of the
  *managed* fields only (tri-state "" omits; blank number omits; list de-dupes;
  object-list rows built from `name__subfield` groups) → straight into
  `registry.validate_spec`. The form layer never validates.
- **`app/web/templates/_policy_form.html`** — grouped control renderer with the
  tri-state select ("Not managed" / Allowed / Blocked), number spinners, enum
  dropdowns, repeatable package / app / file rows (`atlas.js` gains
  `[data-rowset]` add/remove-row wiring and `atlasAddAppGroup`), per-field merge
  hint, and a collapsed read-only "resulting spec" panel.
- **Wired into** `profile_editor.html` (create + edit), `policy_new.html`
  (single-concern, type switcher), `policy_detail.html` (publish new version).
  The three console routes read the form via `parse_form`; **every JSON textarea
  is gone** from the console.
- **Emptying a profile section's form and saving removes the section** — the
  form's "no fields managed" state maps cleanly to "this policy no longer manages
  this category".
- Field names are globally unique across the four wired types, so the profile
  creator's single `<form>` carries all category sub-forms and `parse_form(type)`
  picks out each type's own fields.

Verified live: `/policies/new` renders the typed controls with merge hints;
submitting `min_length=12 / allow_camera=false / kiosk_package=…` created a
composite policy whose three sections held exactly the managed fields; the edit
form pre-selected the stored values; clearing the restrictions form to all "Not
managed" removed that section.

##### Decisions

| # | Decision | Rationale |
|---|---|---|

| # | Decision | Rationale |
|---|---|---|
| DW6 | **Override D64 for the editing surface.** The policy / profile-section editor becomes a generated form of typed controls. No JSON *typing* anywhere in the console. | D64 chose a JSON box because a generated form would "hide the thing that matters — that `min_length` merges by MAX". W10 keeps that visible: a plain-English **merge hint sits next to every control** ("strongest wins", "any policy blocking wins", "stacked allowlists yield only their overlap"), and a **read-only "resulting spec"** panel shows exactly what the form produces. The concern is answered without making operators type JSON. The API keeps its JSON `spec` object — that is a machine surface, not typing. |
| DW7 | **A boolean is tri-state in the UI:** *Not managed* / *Allowed* / *Blocked*. "Not managed" omits the field. | Our specs store only set fields (D3/D18) so a stacked policy composes. A plain checkbox is binary and would force every restriction into every policy — the one-config-per-group model D1 exists to avoid. The third state is the honest representation. |
| DW8 | **Field metadata (label, help, group, bool wording) lives on the Pydantic `Field`** via `title` / `description` / `json_schema_extra`. | Single source of truth, co-located with the merge rule. `model_json_schema()` already surfaces `title`/`description`; the form generator reads the rest. No parallel descriptor file to drift. |

##### Original plan

1. **Field metadata** — add `title`, `description`, `json_schema_extra` (`ui_group`,
   and `ui_true`/`ui_false` for allow-booleans) to the four spec files. Group
   `RESTRICTIONS` like the screenshot ("Device functionality", "Network",
   "Display"); `PASSWORD` into "Strength" / "Lockout & expiry". No behaviour
   change — existing tests stay green.
2. **`app/policies/form_schema.py`** — `FormField` (name, label, help, control,
   group, constraints, merge_hint) and `form_fields(policy_type)` deriving it all
   from `registry.get(type)` (Pydantic fields + the `Merge` annotation translated
   to plain English).
3. **`app/policies/form_parse.py`** — an HTTP form multidict → raw spec dict
   (managed fields only, list/object builders included), then straight through
   `registry.validate_spec` so the form never bypasses validation.
4. **`app/web/templates/_policy_form.html`** — grouped control renderer: tri-state
   select, number spinner with min/max, enum dropdown, text input with pattern
   hint, repeatable list/row builders, per-field merge hint, and a collapsed
   read-only "resulting spec" `<pre>`.
5. **Wire in + drop the JSON boxes** — `profile_editor.html` (new + edit),
   `policy_new.html`, `policy_detail.html` (publish new version); the three
   console routes switch from a `spec` string to `form_parse`. `atlas.js` gains a
   small add/remove-row helper.
6. **Catalogue-fed list controls** — `required_apps` rows pick a package from the
   uploaded `AppPackage`s (+ optional min version code); `files.entries` rows pick
   a `ManagedFile`, destination, tier, persist and extract. The app-group helper
   becomes "add this group's packages as rows".
7. **Tests** — every field renders with the right control and its constraints; a
   render → submit → stored-spec round-trip for each of the four types (including
   one list and one object-list); "Not managed" omits the field; an out-of-range
   value is refused with a legible message; the merge hint is present.

#### ❌ W11 — Periodic Sync policy type (BUILT, THEN REMOVED — 2026-09-02)

Built as a `PERIODIC_SYNC` policy type with a foreground/background dropdown, then
**removed at the operator's decision the same day**: the ATLAS agent always runs
the periodic check-in as a foreground service, and enforcing "background" was
never planned, so the setting offered a choice that does not exist. The
`periodic_sync` category is now gone from the creator catalog entirely (not a
placeholder — there is nothing to configure). `form_schema` / `form_parse` were
reverted to their W10 state; the generic string-enum handling and `ui_choices`
override go back in with the first real string-enum policy type.

Net effect on the tree: `app/policies/specs/periodic_sync.py` deleted, the
`periodic_sync` `Category` removed, W11 tests removed. 439 server tests, as after
W10.

##### Original plan

1. **`app/policies/specs/periodic_sync.py`** — `SyncBehavior` enum
   (`foreground` / `background`), `PeriodicSyncSpec.sync_behavior`
   (`Merge(HIGHEST_RANK)` — a single operational choice with no safety ordering,
   like `kiosk_package`; equal-rank clash surfaces as a conflict), form metadata
   (title, the screenshot's explanation condensed, `ui_choices` for the two
   labels). Register `PERIODIC_SYNC` in the registry.
2. **`form_schema.py` / `form_parse.py`** — `ui_choices` label override for enum
   dropdowns, and string-enum handling (today's only enum, `PasswordQuality`, is
   int-based).
3. **`creator_catalog.py`** — flip `periodic_sync` from placeholder to
   `policy_type="PERIODIC_SYNC"`.
4. **Tests** — spec validation, form round-trip, resolver stacking, the
   desired-state projection carries `PERIODIC_SYNC`.
5. **Agent applier is a follow-up.** The value reaches the device in the
   desired-state document immediately (the projection is generic), but the Kotlin
   agent does not read it yet — it already runs the foreground sync service by
   default, so "foreground" is the current behaviour regardless. Enforcing
   "background" is an agent change, tracked separately.

#### ✅ W12 — Sub-paged policy categories (COMPLETE)

**443 server tests (was 439).** A category's sub-topics are **separate sub-pages**
in the left rail now, each opening its own set of controls; a **green check** marks
a sub-page that has data and bubbles up to its parent category. Matches the
reference UI. Delivered:

- **A sub-page is a field `ui_group`** — the data model is unchanged (one section,
  one spec dict per category). `APP_CATALOG` regrouped so every field is its own
  sub-page (Required apps / Blocklist / Allowlist / Must-not-be-installed /
  Kiosk); `PASSWORD` → Strength / Lockout & expiry; `RESTRICTIONS` → its three
  groups; `FILES` stays one.
- **`form_schema.py`** — `sub_pages(type)` → `[SubPage(slug, label, fields)]`;
  `managed_group_slugs(type, spec)` → which sub-pages have a set field;
  `group_slug()`.
- **`_policy_form.html`** — `policy_subform(fields, spec, …)` renders one group;
  `resulting_spec(spec)` the read-only preview.
- **`_catalog_view`** — each wired category carries its sub-pages, a per-sub-page
  `has_data`, and a category `has_data`.
- **`profile_editor.html` / `policy_new.html` / `policy_detail.html`** — two-level
  rail (category header with check + disclosure triangle → sub-page links with
  checks). In edit mode **all of a category's sub-pages live in one `<form>`**, so
  saving from any sub-page keeps the rest (a hidden page's inputs are still
  submitted).
- **`atlas.js`** — a `[data-rail]` navigator: click a sub-page to show its panel,
  mark it and its category active, expand the category, address it in the URL
  hash (`#page-<cat>:<slug>`). A leaf category (1 group or placeholder) is a
  direct page link.
- **`atlas.css`** — nested rail, disclosure triangles, the circular green check.

Verified live: `restrictions.allow_camera` sets a check on the Device
functionality sub-page and on the Restrictions header; the Display sub-page (which
`screen_timeout_seconds` would fill) stays unchecked; both controls render in the
one Restrictions form.

**Design: a sub-page is a field `ui_group`.** The data model is unchanged — one
profile section (one child `Policy`) per category, one spec dict. The rail just
splits that spec's fields across pages by their declared `ui_group`, and a check
means "at least one field on this page is managed". A category with a single
group is a leaf (click it, get the form); 2+ groups expand to sub-pages.

##### Original plan

1. **Field metadata** — regroup `APP_CATALOG` so each field is its own sub-page
   ("Required apps", "Blocklist", "Allowlist", "Must-not-be-installed", "Kiosk"),
   matching the screenshot's granularity. `PASSWORD` keeps "Strength" / "Lockout
   & expiry"; `RESTRICTIONS` keeps its three groups; `FILES` stays one.
2. **`form_schema.py`** — `sub_pages(policy_type)` → `[(slug, label, [FormField])]`;
   `managed_groups(policy_type, spec)` → the set of group slugs with a set field.
3. **`_policy_form.html`** — render one group at a time (`policy_subform`); keep a
   read-only "resulting spec" on the category, not per page.
4. **`_catalog_view` (routes)** — each wired category carries its sub-pages, a
   per-sub-page `has_data` flag, and a category `has_data` flag.
5. **`profile_editor.html` / `policy_new.html` / `policy_detail.html`** — the rail
   becomes two-level: category header (with check + expand) → sub-page links (with
   checks). All sub-pages of a category live in one `<form>`, so saving from any
   sub-page preserves the others' fields.
6. **`atlas.js` + CSS** — nested rail navigation (expand/collapse, active on both
   levels, hash-addressable `#page-<cat>:<group>`), and the check marker.
7. **Tests** — sub-pages render, the check appears when a group's field is set and
   bubbles to the category, editing one sub-page and saving leaves the others
   intact.

#### ✅ W13 — Networks policy type: Wi-Fi + VPN (COMPLETE)

**448 server tests (was 443).** The **Networks** category is wired — **Wi-Fi** and
**VPN** are its two sub-pages, each a repeatable list of profiles. Delivered:

- **`app/policies/specs/networks.py`** — `WifiSecurity` / `MacRandomization` /
  `VpnConnectionType` enums, `WifiNetwork` (ssid, security, password, auto_join,
  hidden, mac_randomization; validates password length by security) and
  `VpnProfile` (name, connection_type, server, username, password, mppe) models,
  `NetworksSpec` (`wifi_networks` keyed by `ssid`, `vpn_profiles` keyed by
  `name`, both `MERGE_BY_KEY`). Registered `NETWORKS`.
- **`form_schema` / `form_parse`** — `wifi_list` / `vpn_list` controls and their
  positional row-builders. Row-level booleans render as Yes/No `<select>` (a
  checkbox does not submit when unchecked, which would break the positional
  parsing).
- **`_policy_form.html`** — `_wifi_row` / `_vpn_row` macros with the fields from
  the screenshots; passwords as `type="password"` (masked, value present so an
  edit round-trips).
- **`creator_catalog.py`** — `networks` flipped from placeholder to `NETWORKS`.

Verified live: the Networks category shows Wi-Fi / VPN sub-pages; a form submit
produces a `NETWORKS` section carrying one Wi-Fi network and one VPN profile with
every field.

##### Caveats

| # | Decision | Rationale |
|---|---|---|
| DW9 | **Wi-Fi and VPN passwords are stored in the policy spec in cleartext**, and travel in the signed bundle to the device. | The device genuinely needs them to connect, and a policy Wi-Fi config is persistent by nature (unlike the one-shot enrolment credential, D75). Widens the `pki/` + database exposure envelope (R8/R12); does not change what already had to be protected. Console shows them `type="password"`-masked. |

**The Kotlin agent does not apply Wi-Fi/VPN yet** — builder + storage only, applier
is a tracked follow-up (like Knox).

##### Original plan

**Wi-Fi entry:** SSID, auto-join, hidden network, MAC randomization
(persistent / non-persistent / none), security (open / WEP / WPA-PSK / WPA3-SAE),
password.
**VPN entry:** profile name, connection type (PPTP / L2TP-IPsec-PSK /
IPsec-Xauth-PSK), server, MPPE, username, password.

1. **`app/policies/specs/networks.py`** — the two enums, `WifiNetwork` /
   `VpnProfile` models, `NetworksSpec` (`wifi_networks` keyed by `ssid`,
   `vpn_profiles` keyed by `name`, both `MERGE_BY_KEY`). Form metadata:
   `ui_group` "Wi-Fi" / "VPN", `ui_control` "wifi_list" / "vpn_list". Register
   `NETWORKS`.
2. **`form_schema.py` / `form_parse.py`** — the two new list controls + their
   row-builders (`wifi_networks__ssid` etc.).
3. **`_policy_form.html`** — `_wifi_row` / `_vpn_row` macros with the fields
   above (password as `type="password"` — visually masked, value present so an
   edit round-trips).
4. **`creator_catalog.py`** — flip `networks` from placeholder to `NETWORKS`.
5. **Tests** — spec validation, sub-pages render (Wi-Fi / VPN under Networks),
   form round-trip for one Wi-Fi and one VPN entry, resolver stacking.
6. **Caveats, documented:** Wi-Fi/VPN passwords sit in the policy spec in
   cleartext (the device genuinely needs them; folded into R8/R12). The Kotlin
   agent does not apply Wi-Fi/VPN yet — builder + storage only, applier is a
   tracked follow-up.

#### ✅ W14 — Agent: apply the Networks (Wi-Fi) policy (COMPLETE, hardware-proven)

**447 server tests, 36 agent tests (was 30). Agent v29 (`0.8.1`).** Delivered:

- **VPN dropped** — `NetworksSpec.vpn_profiles`, the `_vpn_list` macro and control,
  and the VPN tests are gone. `NETWORKS` = `wifi_networks` only. (Android's
  built-in VPN profile API is private / unavailable to a DO; no VPN client app to
  point always-on at.)
- **`WifiPlan.kt`** (agent, pure) — parses `wifi_networks`, computes the removal
  set. Six unit tests.
- **`PolicyApplier.applyNetworks`** — one `WifiConfiguration` per entry
  (`NONE`/`WEP`/`WPA_PSK`/`SAE`), `addNetwork` → `enableNetwork`. Removes SSIDs it
  added that the policy dropped, by the **stored network id** (`getConfiguredNetworks`
  returns nothing for a DO on One UI 8 — see the reference).
  `AgentConfig.wifiByPolicy` + `wifiNetworkId(ssid)` track what the agent owns,
  mirroring `hiddenByPolicy`.
- Manifest: `ACCESS_WIFI_STATE` + `CHANGE_WIFI_STATE`.
- `docs/ANDROID_PLATFORM_REFERENCE.md` §6d — the DO Wi-Fi contract, and the
  `getConfiguredNetworks` gotcha, recorded from hardware.

**Hardware-proven on `SM-X520`, full cycle:**

```
assign:    PolicyApplier: wifi: configured ATLAS-Test (wpa_psk, id=2)   errors=0
           cmd wifi list-networks → ATLAS-Test listed
unassign:  PolicyApplier: wifi: removing ATLAS-Test (id=2, removed=true) errors=0
           cmd wifi list-networks → gone; the device's own LeckliterFIOS untouched
```

`getConfiguredNetworks()` returns nothing for the DO on One UI 8, so a first
version (v0.8.0) that looked the id up that way logged a successful removal while
the network stayed. v0.8.1 stores the id `addNetwork` returns and removes by it.

##### Plan

**Decided with the operator:** **VPN is dropped** — Android's built-in VPN
profile API is private and unavailable to a Device Owner, and there is no VPN
client app in the deployment to point always-on VPN at. `NETWORKS` becomes Wi-Fi
only; VPN returns if/when a concrete VPN client is deployed. **Wi-Fi is built
now and hardware-proven this session** (`SM-X520` paired for the test).

1. **Drop VPN** — `NetworksSpec.vpn_profiles`, the `_vpn_list` macro, the
   `vpn_list` control, and the VPN tests go. `NETWORKS` = `wifi_networks` only.
2. **`PolicyApplier.applyNetworks(spec)`** (agent) — `WifiManager.addNetwork(
   WifiConfiguration)` per entry (the deprecated config API is grandfathered for a
   Device Owner), security mapped from the enum, `allowAutojoin` for auto-join,
   failures collected not thrown. SSIDs the agent added and the policy no longer
   lists are `removeNetwork`'d — tracked in `AgentConfig.wifiByPolicy`, mirroring
   `hiddenByPolicy`.
3. Pure `WifiPlan` helper (spec JSON → desired SSIDs + removals) so the diff logic
   is unit-tested even though the `WifiManager` calls are not.
4. Manifest: `CHANGE_WIFI_STATE` + `ACCESS_WIFI_STATE` (both `normal`).
5. Wire into `PolicyApplier.apply`; record the contract in
   `docs/ANDROID_PLATFORM_REFERENCE.md`.
6. Agent unit tests for `WifiPlan`; adjust server tests (VPN removed).
7. Build the APK, push to `SM-X520`, prove a policy-pushed Wi-Fi network appears
   and connects.

##### Original plan (Wi-Fi + VPN)

The server-side `NETWORKS` type (W13) reaches the device in the desired-state
document but the Kotlin agent ignores it. This chunk adds `applyNetworks` to
`PolicyApplier`.

**Platform reality, checked against the DPM reference (CLAUDE.md §6):**

* **Wi-Fi** — a Device Owner adds networks with `WifiManager.addNetwork(WifiConfiguration)`.
  The API is deprecated (API 29) but grandfathered for DO/PO — a normal app gets
  `-1` back, a DO gets a real network id. This is the path Headwind and the
  commercial MDMs use. **Needs verification on `SM-X520`** — if it returns `-1`
  there, the fallback is `addNetworkSuggestions`, which the user can decline
  (weaker, reported as such).
* **VPN** — the built-in VPN profile (PPTP / L2TP-IPsec / IPsec-Xauth — the
  "Settings → VPN → +" kind) is `com.android.internal.net.VpnProfile` +
  `IVpnManager`, **not public and not available to a Device Owner**. PPTP was
  removed from Android entirely in Android 12. The only DO-supported VPN is
  `DevicePolicyManager.setAlwaysOnVpnPackage(admin, vpnAppPackage, lockdown)` —
  pointing at an installed VPN *client app*. **So the W13 VPN model (server /
  username / password / connection type) cannot be applied and must be reworked**
  — see the open question below.

1. `applyNetworks(spec)` in `PolicyApplier` — Wi-Fi via `addNetwork`, one
   `WifiConfiguration` per entry, security mapped from the enum, failures
   collected (never thrown). Networks the agent added but the policy no longer
   lists are removed (`removeNetwork`), tracked the same way blocklist hiding is.
2. Wire it into `PolicyApplier.apply` and the reconciler.
3. **Rework the VPN spec** per the open question.
4. VPN applier: `setAlwaysOnVpnPackage` when a package is configured.
5. Record the Wi-Fi contract in `docs/ANDROID_PLATFORM_REFERENCE.md` (📖 for the
   API, then ✅/❌ once tested on hardware).
6. Agent unit tests; server tests for the reworked VPN spec.
7. Prove on `SM-X520`: push a Wi-Fi network by policy, confirm it appears and the
   device can use it.

#### ✅ W15 — Agent policy-application quick wins (COMPLETE, hardware-proven)

**447 server tests, 40 agent tests (was 36). Agent v30 (`0.9.0`).** Three fields
that reached the device but the agent ignored, now applied — all verified on
`SM-X520`:

| Field | Agent | Hardware |
|---|---|---|
| `PASSWORD.history_length` | `dpm.setPasswordHistoryLength` (not deprecated at API 31 — checked) | `history_length: 6` → `dumpsys` shows `passwordHistoryLength=6` |
| `RESTRICTIONS.screen_timeout_seconds` | `dpm.setSystemSetting(SCREEN_OFF_TIMEOUT, ms)` (one of 3 DO-writable keys) | `screen_timeout_seconds: 45` → `settings get system screen_off_timeout` = `45000` |
| `APP_CATALOG.required_apps[].auto_update` | new pure `AppUpdatePlan.decide(installed, desired, autoUpdate)` — `false` means install-once, never chase a newer build | 4 unit tests (truth table); reconciler path exercised on hardware historically |

`AppUpdatePlan.kt` follows the `WifiPlan.kt` pattern — the decision is pure and
unit-tested, the framework calls are not. Platform contracts recorded in the
Android reference §6c.

**Consistent limitation, not new:** scalar settings (`history_length`,
`screen_timeout_seconds`, `expiration_days`, `lock_timeout_seconds`,
`max_failed_attempts_before_wipe`, password complexity) are applied when present
but **not reverted** when the field is dropped from the policy — only the boolean
`allow_*` restrictions revert, because the spec expresses both states. The escape
is to set the field to a permissive value (`history_length: 0`, a large timeout),
which the agent does apply.

> ✅ **Fixed for the PASSWORD fields in W26 (R14)** — they are now driven to a
> definite value every reconcile, absent meaning permissive. This paragraph still
> stands for `RESTRICTIONS.screen_timeout_seconds`, which W26 did not touch.

> 🐛 **R19 — CONFIRMED ON HARDWARE, 2026-09-03.** The hypothesis was right.
> `SM-X520` sat at the device default `1800000`; a policy with
> `screen_timeout_seconds: 45` drove it to `45000`; **removing that policy left it
> at `45000`** with the device converged and COMPLIANT (`60/60`). The agent's guard
> is `if (spec.has("screen_timeout_seconds"))`, so absent writes nothing and the
> last value stands. Restored by hand over adb — **there is no console action that
> can undo it**, which is exactly what made R14 severe.
>
> ⚠️ The W26 fix does **not** transfer. For passwords, "absent" has a well-defined
> permissive value (`0`), so driving the field every reconcile is correct. A screen
> timeout has no such value: the right behaviour is to restore *the user's own
> setting*, and the agent never recorded it before overwriting. So the fix is to
> capture the pre-policy value on first write and put it back when the field goes
> away — more than a one-line change, and a decision (restore-original vs a
> configured fleet default) rather than an obvious correction.
>
> ✅ **FIXED and verified on hardware, 2026-09-03 (agent v45).** `ScreenTimeoutPlan`
> records the value the *first* write displaces and puts it back when the field goes
> away. The original is captured **before** the write, so a crash between the two
> cannot leave the setting changed with nothing remembering what it replaced; and it
> is forgotten only **after** a successful restore, so a failure retries instead of
> losing it. A later policy changing 45s to 60s does not re-record — otherwise 45s
> would become "the user's setting" and 30 minutes could never come back.
>
> ⚠️ **The first fix was wrong, and only hardware showed it.** v44 remembered the
> value correctly and still never restored, because `PolicyApplier.apply` dispatched
> sections with `policy.optJSONObject("RESTRICTIONS")?.let { … }` — remove the last
> RESTRICTIONS policy and the section vanishes, so the code never ran. That is the
> same "absent means no work" mistake as R14 and R19 themselves, one level up.
>
> 🐛 **The same hole was in the W26 password fix.** Driving the minimums to
> permissive every reconcile only ever ran while *some* PASSWORD policy still
> applied. Remove them all and the section disappears and nothing resets — exactly
> the state R14 was raised for. PASSWORD and RESTRICTIONS now apply even when absent
> (as NETWORKS already did, for this reason); APP_CATALOG stays conditional on
> purpose, because "no policy requires apps" means leave them alone, not uninstall.
>
> Verified across three agent builds: v43 latched at 45 s, v44 latched still, v45
> restored to 1800000 the moment it landed. Device `64/64`, COMPLIANT,
> `minimumPasswordLength=0`.

**The policy→agent audit is closed (W18):**
* ~~XAPK **OBB** placement (R2)~~ — ✅ W17: not feasible for a normally-installed
  DO (EACCES probed on `SM-X520`); agent reports it loudly, Apps page flags it.
* ~~`PASSWORD.min_letters` / `min_digits` / `min_symbols`~~ — ✅ W18: the audit
  was wrong that these were dead. `setPasswordMinimum{Letters,Numeric,Symbols}`
  are deprecated but usable by a company-owned DO; the agent now wires them via
  the granular family. Hardware proof pending.
* ~~`NETWORKS.wifi_networks[].auto_join` / `mac_randomization`~~ — ✅ W18:
  genuinely dead (both `@SystemApi`), removed from the spec and form.

#### ✅ W16 — Agent: enforce `APP_CATALOG.allowed_packages` (COMPLETE, hardware-proven)

**447 server tests, 46 agent tests (was 40). Agent v32 (`0.9.2`).** The allowlist
("only these apps may run") now suspends every non-system user app not on it.

- **`AllowlistPlan.kt`** (agent, pure) — `(user apps, allowlist, required set,
  previously suspended) → (toSuspend, toUnsuspend, emptyAndIgnored)`. 6 unit
  tests including the empty-list and required-implicitly-allowed cases.
- **`AppInstaller.userInstalledPackages()`** — non-system, non-agent installed
  packages.
- **`PolicyApplier.setSuspended(packages, suspended)`** — wraps
  `setPackagesSuspended`, surfaces the packages the platform refused.
- **`Reconciler.enforceAllowlist`** — runs after `suppressUnwantedApps`. Inert
  unless a non-empty `allowed_packages` is present. Tracks
  `AgentConfig.suspendedByPolicy`; releases everything it suspended when the
  allowlist goes away.
- Empty resolved allowlist (R4) → logged + reported as an apply note, **not
  enforced** (operator decision).

**Hardware-proven on `SM-X520`, full cycle:** an allowlist excluding
`org.takmdm.testapp` suspended it; the agent, ATAK, GoodNotes, the launcher and
Android's own `clouddpc` were untouched; removing the allowlist un-suspended it.
`errors=0` throughout. Also confirmed: a **required** app is never suspended by
the allowlist.

##### Plan

**Decided with the operator:**
* An **empty** resolved allowlist (`[]` — two stacked lists that don't overlap,
  R4) is **treated as no allowlist**: suspend nothing, log it, and report an
  apply note. The publish preview already flags an empty INTERSECT.
* Scope: **non-system user apps** only. System apps (launcher, dialer, settings)
  are never touched — use the blocklist for those. `setPackagesSuspended` also
  protects the DPC, the active launcher, the package installer/uninstaller, the
  default dialer and the permission controller regardless.
* Suspend only (`setPackagesSuspended`), not hide — a "paused" dialog, reversible.

1. **`AllowlistPlan.kt`** (agent, pure) — `(installed user apps, allowlist,
   required set, previously suspended) -> (toSuspend, toUnsuspend)`. Unit-tested.
2. **`AppInstaller.userInstalledPackages()`** — non-system installed packages,
   excluding the agent.
3. **`PolicyApplier.setSuspended(packages, suspended)`** — wraps
   `dpm.setPackagesSuspended`, returns the packages it could not suspend.
4. **`Reconciler.enforceAllowlist`** — runs after `suppressUnwantedApps`. Inert
   unless `allowed_packages` is present and non-empty. Diffs, suspends/unsuspends,
   tracks `AgentConfig.suspendedByPolicy` (mirrors `hiddenByPolicy`). Unsuspends
   everything it suspended when the allowlist goes away.
5. Platform reference §5a — the `setPackagesSuspended` contract.
6. Agent unit tests for `AllowlistPlan`.
7. Hardware: allowlist that excludes `org.takmdm.testapp` → it suspends; remove
   the allowlist → it un-suspends. `org.takmdm.agent` and the launcher untouched.

#### 🔻 W17 — R2 (XAPK OBB placement): confirmed not feasible, made loud

**Finding (hardware, `SM-X520`, 2026-09-02).** A `probe_obb` debug action wrote,
read back and deleted a file under `/sdcard/Android/obb/org.takmdm.testapp/`:

```
I DebugConfigReceiver: obb probe /sdcard/Android/obb/org.takmdm.testapp ->
  FAILED: FileNotFoundException: .../atlas_obb_probe.txt: open failed: EACCES (Permission denied)
```

The agent holds `MANAGE_EXTERNAL_STORAGE` (all-files access, granted at
provisioning — the same grant that lets it write `/sdcard/atak`). Scoped storage
still blocks writing **another app's** `Android/obb/<pkg>/`. This is the same
class of limitation as VPN: a platform restriction a normally-installed Device
Owner cannot work around without Knox or root. **R2 is not feasible on this
device; the resolution is to stop failing silently.**

Before W17 `Reconciler.reconcileApps` did `if (role == "obb") continue` — the
OBB part was never downloaded and never mentioned. The XAPK's APK installs fine
and the app then fails at runtime with its assets missing, which is the hardest
possible failure to diagnose from the operator's seat.

##### Plan (7 steps)

1. **Agent — make it loud.** `Reconciler.reconcileApps`: when an app's `files`
   include a `role == "obb"` part, add an apply_error naming the package and the
   reason (device goes `DEGRADED`, operator sees it), keep skipping the download.
2. **Server — flag it at rest.** `AppPackageVersion.has_obb` property; Apps page
   shows an "OBB" pill on the Parts cell and a one-line caption that a Device
   Owner cannot place OBB expansion files on the device.
3. **Docs.** `docs/ANDROID_PLATFORM_REFERENCE.md` — new ❌-verified subsection
   under §6 (writing to `/sdcard`): the EACCES probe, what it means, that
   all-files access does not help. Keep it beside the ✅ R1 finding.
4. **Commit the probe.** `DebugConfigReceiver.probe_obb` is the evidence and the
   way to re-check on the Qualcomm / MediaTek devices (R5) — commit it.
5. **Agent version bump** (`0.9.3`, versionCode 33). No new unit test — the
   change is a branch in reconcile glue, not pure logic; note why.
6. **PROJECT_STATE.md** — close R2 in the risk table as "not feasible for a
   normally-installed DO, documented and loud"; changelog; this record.
7. **Server tests** — a version with an OBB part reports `has_obb` and the Apps
   page renders the pill. Full server + agent suites green.

##### Status: ✅ COMPLETE — 448 server tests, 46 agent tests, agent v33 (`0.9.3`)

- Agent: `Reconciler.reconcileApps` raises `"<pkg>: needs an OBB expansion file,
  which a Device Owner cannot place on this device …"` when a `role == "obb"`
  part is present (device → `DEGRADED`), still skips the download. No new unit
  test — it is a branch in reconcile glue, not pure decision logic.
- Server: `AppPackageVersion.has_obb`; Apps page shows an `OBB` pill on the Parts
  cell + a caption on the upload panel. New test
  `test_a_package_carrying_an_obb_is_flagged`.
- `docs/ANDROID_PLATFORM_REFERENCE.md` §6 — ❌-verified subsection with the
  `probe_obb` EACCES output and the R5 note to re-check on the other two SoCs.
- `DebugConfigReceiver.probe_obb` committed (evidence + R5 re-check tool).

#### 🔻 W18 — dead spec fields: implement the password ones, drop the Wi-Fi ones

The policy→agent audit's last item. Research (official DPM reference, 2026-09-02)
**corrected the audit's assumption**:

* **Wi-Fi `auto_join` / `mac_randomization` — genuinely dead.**
  `WifiConfiguration.macRandomizationSetting` and the per-network auto-join
  toggle are both `@SystemApi`, unavailable to a normally-installed Device Owner.
  → **remove** the fields.
* **Password `min_letters` / `min_digits` / `min_symbols` — NOT dead.**
  `setPasswordMinimumLetters/Numeric/Symbols` are `@Deprecated` but "company-owned
  devices (fully-managed …) are able to continue using" them. The agent simply
  never wired them. → **implement** them (operator's call, 2026-09-02).

**Contract that shapes the agent change** (DevicePolicyManager reference):
* `setPasswordMinimum{Letters,Numeric,Symbols}` **throw `IllegalStateException`**
  for an app targeting R+ unless `setPasswordQuality(PASSWORD_QUALITY_COMPLEX)`
  was set first. Default value of each is 1.
* `setPasswordQuality` **clears** any `setRequiredPasswordComplexity` (no throw on
  the primary instance for a DO — they just don't coexist).
* So the agent's password path moves **off** the complexity-bucket API and onto
  the granular deprecated family, which maps 1:1 to our spec fields.

##### Plan (7 steps)

1. **Specs.** `NetworksSpec`: drop `WifiNetwork.auto_join`, `.mac_randomization`,
   delete the `MacRandomization` enum. `PasswordSpec`: keep the three `min_*`
   fields; sharpen their `description` (they force Complex quality).
2. **Form.** `_policy_form.html` `_wifi_row` — remove the Auto-join and MAC
   controls. `form_parse.py` `wifi_list` — stop reading `__auto_join` /
   `__mac_randomization`.
3. **Agent — pure planner.** `PasswordPlan.kt`: `enum PwQuality`;
   `effectiveQuality(qualityOrdinal, minLetters, minDigits, minSymbols)` — maps
   the server's `quality` (0–6) to the enum and bumps to `COMPLEX` when any
   char-class minimum is > 0. Plain-JUnit unit tests (the `WifiPlan` pattern).
4. **Agent — applier.** `PolicyApplier.applyPassword` moves to the granular
   family: `setPasswordQuality(effectiveQuality → DPM const)`, then
   `setPasswordMinimumLength`, and `setPasswordMinimum{Letters,Numeric,Symbols}`
   guarded on the effective quality being `COMPLEX`. Each `runCatching`, failures
   collected. `history_length` / expiry / lockout paths unchanged.
5. **Agent — Wi-Fi cleanup.** Drop `autoJoin` from `DesiredWifi` /
   `WifiPlan.desired`; fix the stale `applyNetworks` comment; adjust
   `WifiPlanTest`.
6. **Docs.** `ANDROID_PLATFORM_REFERENCE.md` §6c — the granular password family
   contract (deprecated-but-live for a company-owned DO; the
   `PASSWORD_QUALITY_COMPLEX` precondition; the `setRequiredPasswordComplexity`
   clash). §6d — the Wi-Fi fields removed, and why.
7. **Tests + version.** Update `test_api.py` / `test_resolver.py` /
   `test_admin_ui.py` for the removed Wi-Fi fields and the password path; agent
   v34 (`0.9.4`); full server + agent suites green. **Then stop** — hardware
   verification on `SM-X520` (`quality: complex` + `min_digits: 2` → the device
   demands a complex passcode) is the checkpoint.

##### Status: ✅ COMPLETE and hardware-proven — 448 server tests, 52 agent tests, agent v34 (`0.9.4`) running on `SM-X520`.

- Specs: `WifiNetwork.auto_join` / `.mac_randomization` and the `MacRandomization`
  enum removed. `PasswordSpec` `min_*` descriptions sharpened; fields kept.
- Form: the Auto-join / MAC controls gone from `_wifi_row`; `form_parse` no longer
  reads them.
- Agent: new pure `PasswordPlan` (`effectiveQuality` + `charClassMinimumsApply`,
  6 unit tests). `PolicyApplier.applyPassword` rewritten onto the granular
  `setPasswordQuality` → `setPasswordMinimumLength` →
  `setPasswordMinimum{Letters,Numeric,Symbols}` family (guarded on COMPLEX).
  `DesiredWifi.autoJoin` dropped; `WifiPlanTest` adjusted (still 6).
- Docs: `ANDROID_PLATFORM_REFERENCE.md` §6c — the granular password family
  contract (deprecated-but-live for a company-owned DO; the
  `PASSWORD_QUALITY_COMPLEX` precondition; the complexity-bucket clash), marked
  ⏳ not-yet-re-verified. §6d — the two Wi-Fi fields removed and why.
- Tests: `test_wifi_form_round_trip` updated for the removed fields.

**Hardware-proven on `SM-X520` (2026-09-02, agent v34), full cycle:**

| Policy pushed | `dumpsys device_policy` (our admin) |
|---|---|
| `{min_length: 13}` | `passwordQuality=0x20000` (NUMERIC), `minimumPasswordLength=13` |
| `{min_length: 13, quality: 6, min_digits: 2}` | `passwordQuality=0x60000` (COMPLEX), `minimumPasswordLength=13`, `minimumPasswordNumeric=2` |
| revert to `{min_length: 13}` | quality fell to `0x20000`, `minimumPasswordNumeric` back to the `1` default |

`SyncService: sync: state=N applied=N errors=0` on all three. Both branches of
`PasswordPlan.effectiveQuality` (NUMERIC for a length floor, COMPLEX for a
character-class minimum) confirmed, and the quality field reverts.

**W17's OBB apply_error** — ✅ **hardware-verified 2026-09-02 (W25).** A synthetic
XAPK carrying an OBB (`tests/apk_fixtures.build_xapk(..., with_obb=True)`) was
uploaded and assigned to `SM-X520`. The agent raised exactly:

```
com.example.obbproof: needs an OBB expansion file, which a Device Owner cannot
place on this device (Android blocks writing another app's Android/obb). The APK
installs but the app may be missing assets.
```

`sync: state=47 applied=47 errors=2`, device went **DEGRADED**, and the message
surfaced in `compliance_detail` — the operator sees it, which was the whole point
of W17. (The second error was `INSTALL_PARSE_FAILED_NO_CERTIFICATES` — the test
fixture's APK is not validly signed for a real install. An artifact of the
fixture, not the product; the OBB error fired independently of it.)

⚠️ Wording nit found by the test: the message says "The APK installs but…", which
was not true here because the fixture APK failed to install. Correct for the real
case; consider softening to "the APK may install without its assets".

#### 🔻 W19 — DPC app UI: ATLAS MDM branding + a real status console

The agent's on-device UI is a monospace `TextView` dump plus four buttons
(`activity_main.xml`). This chunk makes it a proper status console and brands it
as **ATLAS MDM**, styled to the supplied icon (`Test Files/atlas icon.png` —
brushed-steel "A" chevron over a blue wireframe globe on dark navy).

**Sections the operator asked for:** Permissions · Available app downloads ·
Available file downloads · Policies (what's applied) · Device info (enrolment,
sync, server, device name, device ID) · a manual Sync.

**Interpretation notes:**
* "Available app downloads" = the managed apps from the desired state and their
  install status (installed vN / update pending / missing / failed). Every app
  the MDM pushes is mandatory — there is no user-choice app tier — so this is a
  status list, not a store. (Say so if a store tier is wanted.)
* "Available file downloads" = the existing marketplace (F4): `files.required`
  shown as *Automatic*, `files.available` with the Install/Remove toggle.
* "Policies" = a read-only pretty-print of the resolved `policy` object in the
  cached desired state (PASSWORD / RESTRICTIONS / APP_CATALOG / FILES / NETWORKS).

**Shape:** one `MainActivity` with a Material `BottomNavigationView` (Device /
Permissions / Apps / Files / Policies) over five toggled `ScrollView` sections,
a persistent header (banner + Sync action). No new Gradle deps — plain
Activity + programmatic row inflation, matching `PolicyComplianceActivity`.

##### Plan (7 steps)

1. **Brand assets + theme.** Adaptive launcher icon — `ic_launcher_foreground.xml`
   (flat vector reading of the mark: globe ring + steel-grey A chevron + blue
   inner arrowhead, content inside the 66dp safe zone), `ic_launcher_background.xml`
   (navy gradient + faint grid), `mipmap-anydpi-v26/ic_launcher.xml` +
   `_round.xml`. `atlas icon.png` → `res/drawable-nodpi/atlas_banner.png` for the
   in-app header. `colors.xml` (navy `#0A1A2F` / blue `#1E7BE8` / steel `#B7C0CC`
   palette), `themes.xml` → dark Material3 with the blue as primary.
   `strings.xml` `app_name` → **ATLAS MDM**; manifest `icon` / `roundIcon` /
   `label`.
2. **Shell.** Rebuild `MainActivity`: `BottomNavigationView` + menu resource +
   five section containers in a `FrameLayout`, visibility-toggled; header with
   `atlas_banner` and a Sync button; `onResume` re-renders the visible section.
3. **Device Info section + manual sync.** Enrolment state, device name, device
   ID (UUID), serial, server URL, agent version, last sync (relative + exact),
   state vs applied version, next check-in. "Sync now" with an in-progress state
   and the result/first-error. "Discard identity & re-enrol" kept here.
4. **Permissions section.** A card per `PermissionRequirement.ALL` — title,
   rationale, Granted / Needs a tap, and a Grant button for the app-op ones.
   Link out to `PolicyComplianceActivity` for the guided flow. Refreshes on
   resume (grants happen in Settings and the user comes back).
5. **Apps + Files sections.** Apps: a row per `cachedDesiredState.apps[]` —
   label (from `PackageManager` when installed, else package name), wanted
   version, status from `AppInstaller.installedVersionCode`, download size.
   Files: fold `MarketplaceActivity`'s logic in — `required` rows tagged
   *Automatic*, `available` rows with Install/Remove that trigger a sync. Retire
   `MarketplaceActivity` (or leave it as a thin alias — decide during build).
6. **Policies section + device name over the wire.** Render the resolved
   `policy` object as grouped key/value cards. Server: add `name: str | None`
   (= `device.name`) to `CheckinResponse`; agent caches `config.deviceName` on
   check-in. One server test. `docker compose up -d --build`.
7. **Build, restyle pass, install v35 (`0.9.5`) on `SM-X520`, screenshot every
   section, update `PROJECT_STATE.md` + changelog.** Stop for approval.

##### Status: ✅ COMPLETE and hardware-proven — 449 server tests, 52 agent tests, agent v35 (`0.9.5`) on `SM-X520`

- **Branding.** App renamed **ATLAS MDM**. Adaptive launcher icon built from the
  supplied tile (`ic_launcher_foreground` = the globe + steel-A mark cropped out
  of the tile, `ic_launcher_background` = navy + faint grid); the mark also
  serves as the in-app header logo. New `colors.xml` (navy / electric-blue /
  steel) and a committed dark Material3 theme.
- **Console.** `MainActivity` is now a `BottomNavigationView` over five
  visibility-toggled sections; no new Gradle deps, views built through a small
  `ConsoleViews` helper (card / kv-row / status-pill / divider).
  - **Device** — enrolment (green pill), device owner, **device name**, device
    ID, serial, server, agent version; last sync (relative + exact), policy vs
    applied version, last error / apply problems; a prominent Sync button and
    the re-enrol escape hatch.
  - **Permissions** — a card per `PermissionRequirement.ALL` with Granted /
    Needs-a-tap / Automatic status and a Grant button for the app-op ones; link
    to the guided `PolicyComplianceActivity`.
  - **Apps** — a row per managed app: label (resolved via `PackageManager`),
    package, target version, download size, Installed / Update pending / Missing.
  - **Files** — the marketplace, folded in: `required` rows tagged *Automatic*
    with Placed/Pending, `available` rows tagged *Optional* with Install/Remove
    that trigger a sync. `MarketplaceActivity` retired.
  - **Policies** — the resolved `policy` object rendered as grouped cards
    (Passcode / Restrictions / Apps & kiosk / Managed files / Networks), arrays
    summarised, with a policy-version footer.
- **Device name over the wire.** `CheckinResponse.name` (= `device.name`) added;
  agent caches `config.deviceName` each check-in (guarding Android's
  `optString`→`"null"` quirk). One server test (`test_checkin_echoes_the_device_name`).
- **Hardware (SM-X520, v35):** all five sections render correctly; naming the
  device on the server (`PATCH /devices/{id}`) showed up as "Ops Tablet 07" in
  the console after one sync; `sync: applied=40 errors=0` throughout.

Screenshots in the session scratchpad (`shots/01_device` … `05_policies`).

##### Not done / notes
* The launcher-icon mark is a **crop of the supplied tile**, not a redrawn
  vector — brushed-metal shading does not survive vectorisation, and the crop
  keeps the exact look. Legacy square `mipmap` PNGs generated for < API 26
  (moot at minSdk 33, kept for completeness).
* `ANDROID_PLATFORM_REFERENCE.md` unchanged — the console uses only documented
  APIs (`Build.getSerial()` behaviour already recorded in §identity).

#### 🔻 W20 — PASSWORD policy: set an exact passcode (not just require one)

**Operator ask:** on the PASSWORD policy, be able to *set* the device's screen-lock
passcode, and have the user unable to change it.

**Platform check (DPM reference, 2026-09-02):**
* A Device Owner sets a specific passcode with **`resetPasswordWithToken`** (API
  26+). It needs a reset token from **`setResetPasswordToken`** (≥32 bytes,
  CSRNG). The token **activates immediately only if the device has no passcode**;
  if one is already set, the user must confirm their current credential once
  (`KeyguardManager.createConfirmDeviceCredentialIntent`) before it activates.
  Un-activated tokens are memory-only and lost on reboot; an activated one
  survives reboots and password changes.
* The new passcode must satisfy the DPM quality/length constraints or
  `resetPasswordWithToken` returns `false`.
* **There is no AOSP API to stop the user changing the passcode.** Android's docs
  state the token "remains effective even if the user changes or clears the
  lockscreen password" — the DPC's only remedy is to set it back.

**Decision (operator, 2026-09-02):** "unchangeable" = **re-asserted every sync**.
The agent sets the policy passcode on each reconcile; a user change is undone at
the next check-in (seconds after a policy edit, otherwise the poll interval).
This is exactly the desired-state model everything else uses.

##### Plan (7 steps)

1. **Spec.** `PasswordSpec.set_password` — `Annotated[str | None,
   Merge(HIGHEST_RANK)]`, 4–16 chars, `ui_control: "password"`, `ui_secret`.
   A model validator: if set, it must be ≥ this policy's own `min_length`.
2. **Form.** `FormField.secret` (from `ui_secret`); `_password` macro +
   `_control` branch in `_policy_form.html`; `form_parse` `password` branch;
   mask secret fields in the `resulting_spec` preview and the read-only detail.
3. **Agent.** `AgentConfig.resetPasswordToken` (base64). `PolicyApplier.applyPassword`
   gains `ensurePasswordSet(desired)` — runs after the quality/length block:
   generate + persist a 32-byte token, `setResetPasswordToken` if not
   `isResetPasswordTokenActive`, report if activation needs the user,
   `resetPasswordWithToken(admin, desired, token, 0)`, report a `false` return.
   Re-asserted every reconcile. Agent v36 (`0.9.6`).
4. **DPC console.** Policies tab shows `set_password` as "•••••• (enforced)",
   never the value.
5. **Docs.** `ANDROID_PLATFORM_REFERENCE.md` §6c — the reset-password-token
   contract and the "no way to block a user change, re-assert only" finding.
6. **Tests.** Server: the `HIGHEST_RANK` merge contract, the validator, a form
   round-trip with the value masked in the preview. Agent: builds clean (DPM
   glue, no pure planner).
7. **Hardware (`SM-X520`).** Push `set_password` + `min_length`; confirm the lock
   screen adopts it; change it as the user; sync; confirm it reverts. Clear the
   passcode afterwards. **Stop for approval.**

##### Status: ✅ COMPLETE and hardware-proven — 452 server tests, 52 agent tests, agent v36 (`0.9.6`) on `SM-X520`.

**Hardware (`SM-X520`, 2026-09-02), full cycle:**
* Fresh device (no passcode) + `set_password: atlas1234` → `PolicyApplier: passcode
  set from policy (9 chars)`, `sync … errors=0`; `locksettings verify --old
  atlas1234` succeeded — the reset token activated immediately (no existing
  passcode).
* User changed the passcode → next sync re-asserted it: `atlas1234` verified
  again, the user's value rejected.
* `set_password` removed → the agent stopped re-asserting; the passcode was **not**
  cleared (W15 scalar behaviour). A known 14-char value was set for the bench
  device afterwards to keep it compliant with the restored `min_length: 13`.

**Known gap:** clearing a forced passcode needs the length/quality constraints
relaxed first, which the agent has no path for (W15). Undoing a `set_password`
today means also publishing a permissive `min_length`/`quality` — worth a small
follow-on that clears both when the passcode field goes away.

> ✅ **Closed by W26 (R14).** The constraints now release themselves: dropping a
> field from the policy pushes the permissive value, so no manual counter-policy
> is needed. This gap went on to cause a real failure before it was fixed — see
> R14.

- Spec: `PasswordSpec.set_password` (`HIGHEST_RANK`, 4–16 chars, `password`
  control, `ui_secret`) + a validator (must be ≥ this policy's own `min_length`).
- Form: `FormField.secret`; `_password` macro + `_control` branch;
  `form_parse` `password` branch; a `spec_json` Jinja filter that masks secret
  keys (`set_password`, `password`) in the version-history and resulting-spec
  `<pre>` views (the edit `<input>` still carries the value, as Wi-Fi does).
- Agent: `AgentConfig.resetPasswordToken`; `PolicyApplier.ensurePasswordSet` —
  32-byte token, `setResetPasswordToken` when not active, reports the
  confirm-credential requirement, `resetPasswordWithToken(admin, desired, token,
  0)`, reports a `false` return. Runs last in `applyPassword`; re-asserted every
  reconcile.
- DPC console: `set_password` shows as "•••••• (enforced)" on the Policies tab.
  (The admin web console shows it in the clear — W21.)
- Docs: `ANDROID_PLATFORM_REFERENCE.md` §6c — the reset-password-token contract
  and the "no AOSP way to block a user change, re-assert only" finding.
- Tests: `test_set_password_forces_an_exact_passcode`,
  `test_set_password_shorter_than_the_policy_minimum_is_rejected`,
  `test_set_password_round_trips_but_is_masked_in_the_spec_views`, and the
  `HIGHEST_RANK` merge-contract assertion.

**Hardware carries a lock-out risk** (the tablet currently has no screen lock) —
the test sets one, so it needs a known value and a clean-up step. Holding for a
go-ahead.

#### 🔻 W21 — the policy editor: one composite kind, values in fields, unsaved-change guard

**Operator asks:** (a) don't value-mask the passcode on the admin console; (b) for
any policy, show the set values in the builder's entry fields, not a JSON dump,
and warn before navigating away from unsaved edits; (c) every policy should show
**all** categories' fields when editing.

**Reality found:** the dev DB has **8 single-concern policies and 0 composites** —
the operator has only ever built single-concern policies, whose editor
(`policy_detail.html`) shows one category. **Decision (operator, 2026-09-02):**
composite is the only kind going forward; single-concern policies stay working
until touched, and become a composite the moment a second category is filled.
Keep the mask on the **on-device** console (a device user could read it there),
drop it on the admin console.

##### Plan (7 steps)

1. **Unmask on the web console.** Remove the `spec_json` / `_redact_secrets`
   filter; the admin console shows `set_password` in plain text. The DPC's
   `SECRET_POLICY_FIELDS` masking stays.
2. **Drop the JSON dumps.** Remove `resulting_spec()` from `profile_editor.html`
   and `policy_detail.html`; render the "Versions" history as a readable
   field: value list, not `<pre>` JSON. The edit form already populates fields.
3. **Unsaved-change guard** (`atlas.js`). Track edits on a policy `<form>`; on
   `beforeunload` and on an in-app nav click that leaves the page, warn. A
   successful submit clears the flag.
4. **"New Policy" is always composite.** Drop the "create a single-concern
   policy instead" links; `/policies/new/single` → redirect to `/policies/new`.
5. **Composite editor: every category, one save.** `profile_editor.html` edit
   mode swaps the per-category `<form>`s + "Save Password"/"Save Restrictions"
   buttons for one `<form>` → a new `POST /profiles/{id}` bulk upsert (parse
   every wired category, upsert/remove sections in one transaction). One "Save
   policy" button.
6. **Single-concern detail → full-category editor, promote on save.**
   `policy_detail.html` renders the composite editor's category rail with this
   policy's type pre-filled. Save publishes this policy's own version; if any
   *other* category has data, create a `PolicyProfile`, adopt this `Policy` as
   its section, add the new sections, convert its `Assignment` rows →
   `ProfileAssignment`, redirect to `/profiles/{id}`. Resolution is unchanged —
   a section produces the same `AssignmentInput` as a standalone assignment.
7. **Tests + regression.** New: bulk profile save, promote-on-save, guard
   present, password unmasked. Fix tests referencing `resulting_spec` /
   `/policies/new/single` / the W20 mask. Full suites; click-through on the
   running console.

##### Status: ✅ COMPLETE — 454 server tests; migration applied to the live DB; tablet unaffected.

Delivered a little differently from the plan — cleaner:
- **Unmasked on the web.** The `spec_json`/`_redact_secrets` filter is gone; a
  new `spec_rows` filter renders a spec as a readable label/value list. The
  `set_password` field is a plain `type="text"` input (was `password`), shown in
  the clear. The DPC console keeps its `SECRET_POLICY_FIELDS` mask.
- **No JSON in the editor.** `resulting_spec()` removed; the version history is
  a `<dl class="kv">` list. The form fields carry the values.
- **Unsaved-change guard** (`atlas.js`) — any `form[data-policy-form]` sets a
  dirty flag on input; `beforeunload` and in-app link clicks warn; a submit
  clears it. Marker on both the composite editor and the (template-only)
  `policy_detail` edit form.
- **One kind of policy.** Migration `h8j0l2n4p6r8` converts every standalone
  policy to a one-section composite and moves its `Assignment`s to
  `ProfileAssignment`s — **8 active + 4 archived converted, 0 standalone left,
  the tablet's effective policy byte-identical** (`state=42`, `errors=0` on the
  next sync). `GET /policies/{id}` for a section redirects to its composite.
- **Every category, one save.** The composite editor is one `<form>` →
  `POST /profiles/{id}` (bulk upsert: fill a category to add it, empty it to
  drop it). The per-category "Save Password"/"Save Restrictions" buttons are
  gone; "New Policy" only ever opens the composite creator
  (`/policies/new/single` still exists but is unlinked).

**Not done:** cloning a template still makes a standalone policy (there are 0
templates; low priority). The single-concern create route (`POST /policies`)
still works for the API and tests but has no UI entry point.

#### 🔻 W22 — quick archive from the policy list, with an impact modal

**Operator ask:** on the policy list, archive a policy in one step; an
intermediate modal first shows what the policy does and which devices it is on,
with confirm / cancel; archiving removes the policy from those devices.

**Today:** archiving is only reachable from inside the editor, and it flags the
profile (`archived_at`) but leaves the `ProfileAssignment` rows — the resolver
skips an archived profile, so the device does drop it, but the assignment set
lingers and `restore()` silently re-applies it. Archived profiles also do not
appear anywhere in the console.

##### Plan (6 steps)

1. **Service.** `profile_service.archive` also **deletes the profile's
   `ProfileAssignment` rows** (capturing the affected devices first, invalidating
   them after) — archiving genuinely removes the policy from devices. `restore`
   now brings back an unassigned policy; adjust its note.
2. **List data.** `list_policies` also loads archived profiles, and builds a
   per-profile preview: each section's category label + `spec_rows`, and the
   device display-names the profile currently reaches
   (`eff.devices_affected_by_profile` → `Device`).
3. **List UI.** `policies.html` Device-policies tab gets an **Archive** button
   per profile row → opens `modal("archive-<id>")`. The modal shows the
   what-it-does summary, the current device list (or "not assigned to
   anything"), and Confirm (posts `/profiles/{id}/archive`) / Cancel.
4. **Archived tab.** Show archived **profiles** there with a Restore button
   (today it only lists archived standalone policies).
5. **Route.** `archive_profile_form` → back to `/policies#tab-device`; the modal
   is the confirmation, so drop the old `data-confirm`.
6. **Tests + verify.** archive-from-list drops the assignments and the device's
   effective policy; the modal renders the summary + device names; an archived
   profile shows in the Archived tab and restores. Click-through on the console;
   archive + restore "Tablet Live Test" against `SM-X520`.

##### Status: ✅ COMPLETE and hardware-proven — 457 server tests.

- `profile_service.archive` now deletes the profile's `ProfileAssignment` rows
  (capturing the affected devices first, invalidating after). `restore` note
  updated — it comes back assigned to nothing.
- The policy list has a **Categories** column (real labels), an **On devices**
  count, and a per-row **Archive** button → `modal("archive-<id>")` showing the
  per-category `spec_rows` summary, the device names it currently reaches, and
  **Archive policy** / **Cancel**.
- The Archived tab now lists archived **profiles** with a Restore button.
- `_spec_rows` takes an optional `policy_type` so the summary uses the same
  field titles as the editor ("Minimum length", not "min length").
- **Hardware (`SM-X520`):** archiving "Tablet Live Test" (`min_length: 13`,
  assigned to the tablet) dropped `PASSWORD` from the effective policy — server
  `state 42 → 43`, the tablet synced and acked 43, `compliant`. Restore +
  re-assign brought it back (`state 44`, `min_length: 13`).

#### 🔻 W23 — confirm push propagation; add a per-device "Check in now" button

**Operator ask:** make policy changes push instead of waiting for a check-in;
and a button to make a device check in on demand.

**Finding:** policy changes **already push.** The agent parks a long-poll on
`GET /api/v1/device/wait` (agent `WAIT_SECONDS = 120`); the server rings it the
instant any write invalidates the device's state — wired to SQLAlchemy
`after_commit` in `notifications.py`, so no write path can forget. Verified live
right now: the tablet is parked at `state_version=44` and F3 was hardware-proven
in Chunk 5 and W20 (park woken in the same second, bundle 1 s later). Polling
stays the correctness floor for a device that goes dark. Single uvicorn worker —
fine for 50–500 devices; a multi-process deployment would need Postgres
`LISTEN/NOTIFY` or Redis (documented, not built). **No FCM** — the deployment has
no managed Google Play, and the doorbell already gives ~1 s latency.

##### Plan (6 steps)

1. **Verify** the wake latency with a timed test against `SM-X520` (publish a
   trivial change, measure park-return → apply).
2. **`notifications.wake_now(session, ids)`** — schedules the wake and returns
   the subset currently parked (`bus.waiter_count > 0`), so the UI can say
   whether it landed.
3. **Routes.** `POST /devices/{id}/checkin` (web → redirect with a flash) and
   `POST /api/v1/devices/{id}/checkin` (admin-auth → `{"woken": bool}`).
4. **UI.** "Check in now" on `device_detail.html` (with a result banner) and a
   per-row "Check in" on the fleet table. Banner distinguishes "connected —
   checking in now" from "not connected — will sync within 2 min".
5. **Tests.** the route wakes a simulated parked waiter and reports it; an
   offline device is a graceful no-op; the buttons render.
6. **Docs + hardware.** PROJECT_STATE + a short note in the architecture doc that
   push already exists (F3) and how the button uses it; click it against
   `SM-X520` and watch the sync fire.

##### Status: ✅ COMPLETE and hardware-proven — 461 server tests.

✅ **Live-confirmed 2026-09-02 (W25).** With `SM-X520` parked on its long-poll,
`POST /api/v1/devices/{id}/checkin` returned `{"woken": true}` and the device's
`last_checkin_at` moved **702 ms** later. (A `docker compose exec` reading of
`bus.waiter_count` shows 0 — that spawns a *separate* Python process and cannot
see the serving process's in-memory bus. The `woken` flag from the API itself is
the authoritative reading; the 702 ms check-in confirms it.)

**Answer to the ask:** policy changes **already push.** The agent parks a
long-poll (`GET /api/v1/device/wait`); the server rings it the instant any write
invalidates the device's state, wired to SQLAlchemy `after_commit` so no path can
forget. Latency is ~1 s (F3, proven Chunk 5 / W20).

**Gap found and fixed:** the doorbell ring could be *lost* — the notify runs in
the gap between one check-in finishing and the next park registering, or a
recompute lands while the request is parked. Before W23 a lost ring meant the
device waited the agent's full `WAIT_SECONDS = 120` park. `wait.py` now
**sub-parks in 10 s slices and re-reads the pending reason between them**, so a
lost ring costs ≤ 10 s. The session is closed between every check, so no
connection is ever held across a park. New test
`test_a_lost_doorbell_ring_still_releases_the_wait` monkeypatches the notify to a
no-op and confirms recovery within a slice.

**"Check in now":**
- `eff.request_checkin(session, ids)` — marks the cache stale (gives the
  long-poll's pending check a reason) + rings the doorbell; returns the parked
  subset. The recompute finds nothing moved, so `state_version` does not bump —
  a harmless no-op check-in that refreshes `last_checkin_at`.
- `POST /devices/{id}/checkin` (web → redirect `?checkin=now|queued`) and
  `POST /api/v1/devices/{id}/checkin` (→ `{"woken": bool}`).
- Buttons: "Check in now" on the device page (with a result banner) and a
  per-row "Check in" on the fleet table.

**No FCM** — the deployment has no managed Google Play and the doorbell already
gives ~1 s. Single uvicorn worker is fine for 50–500 devices; a multi-process
deployment would fan the notify through Postgres `LISTEN/NOTIFY` (documented in
`notifications.py`, not built).

#### 🔻 W24 — DPC Policies tab shows names; console device rename; OS device-name deferred

**Operator asks:** (a) the DPC app's Policies tab should list the applied policy
*names*, not the field contents; (b) the admin portal needs a way to name/rename
devices; (c) a rename should change the device name in the OS system settings.

**Platform finding on (c):** a normally-installed Device Owner **cannot** write
`Settings > About phone > Device name` (`Settings.Global.DEVICE_NAME`).
`setGlobalSetting` has a fixed whitelist that excludes it; a direct write needs
`WRITE_SECURE_SETTINGS`, which a DO cannot self-grant. Commercial MDMs
(ManageEngine, Hexnode) can't either. **Decision (operator, 2026-09-02): defer
to Knox.** Documented in the Android reference; nothing built for it now.

⚠️ **Correction (2026-09-02, later the same day):** the "Knox has a real API"
premise was wrong — I asserted it from expectation, not from the docs. There is
**no `setDeviceName` in the Knox SDK**; `custom.SettingsManager` is a fixed
allow-list of ~40 toggles and cannot write arbitrary secure/global settings.
Device naming is a **Knox Configure** feature — a separate Samsung provisioning
product, not KPE or the SDK. So this is not "deferred", it is **closed as not
achievable** by any path currently in scope. See [docs/KNOX.md](docs/KNOX.md) §4.2.

##### Plan (6 steps)

1. **Server → device: policy names.** `fleet.policy_names_for_device(session,
   device)`; `CheckinResponse.policy_names` populated from it (metadata, does not
   touch `state_version`, like `name` in W19).
2. **Agent caches it.** `AgentConfig.policyNames` from the check-in response.
3. **DPC Policies tab.** `renderPolicies` lists the names, one per row, with the
   policy-version footer — no field content, no per-category cards. Falls back to
   the cached bundle's category types if names haven't arrived yet. The
   now-unused `summarise`/`describeObject`/`SECRET_POLICY_FIELDS` helpers go.
   Agent v37 (`0.9.7`).
4. **Console device rename.** Inline rename on the fleet table (name field per
   row, "Save", `next=/` so it stays on the list) alongside the existing rename
   on the device page. `/devices/{id}/rename` gains a validated `next`.
5. **Docs.** Android reference §6c — the `setGlobalSetting` whitelist and the
   ❌ device-name finding; R3 note.
6. **Tests + hardware.** `policy_names` in the check-in response; the inline
   rename round-trips; the DPC tab shows names on `SM-X520`.

##### Status: ✅ COMPLETE and hardware-proven — 464 server tests, 52 agent tests, agent v37 (`0.9.7`) on `SM-X520`.

✅ **DPC verified on-device 2026-09-02 (W25).** With v37 installed and synced, the
Policies tab lists exactly three rows — *ATAK Imagery*, *Install Proof*, *Tablet
Live Test* — under "Applied policy", with the "Policy version 46 (applied 46)"
footer and **no field contents**. Screenshot in the session scratchpad
(`w25_policies.png`).

- Server: `fleet.policy_names_for_device`; `CheckinResponse.policy_names`. Test
  `test_checkin_lists_the_policy_names_reaching_the_device`.
- Agent: `AgentConfig.policyNames` cached from the check-in; `renderPolicies`
  lists the names (one "Policy" row each) + the version footer, nothing else.
  `summarise` / `describeObject` / `SECRET_POLICY_FIELDS` removed. Falls back to
  the cached bundle's category types if names have not arrived.
- Console: inline rename on every fleet-table row (name field + Save, `next=/`
  so it stays on the list), plus the existing rename on the device page.
  `/devices/{id}/rename` takes a validated `next` (offsite values ignored — new
  test).
- Docs: Android reference §6c — the `setGlobalSetting` whitelist and the
  ❌ "a DO cannot set the OS Device name" finding. (Originally logged as
  "deferred to Knox"; **corrected the same day — Knox cannot do it either**, see
  [docs/KNOX.md](docs/KNOX.md) §4.2.)
- The friendly name still only reaches the ATLAS console + the ATLAS MDM app's
  Device tab; the OS "About phone" name is unchanged, and stays that way.

#### 🔻 W26 — R14: release password scalars instead of latching them

**The bug, found in the wild (2026-09-02).** `applyPassword` only calls a DPM
setter when the field is *present* in the merged spec. Nothing ever pushes a
value when a field is *absent*, so every scalar it has ever set stays latched on
the device forever. On `SM-X520` this left `minimumPasswordLength=13` from a
policy that no longer applies, which then **rejected** a new policy's
`set_password: "6819"` — and there is no console-side way out. W15 documented
this as a limitation; W20 made it acute; it is now a live failure.

**The rule this restores.** Everywhere else in the desired-state model, absent
means "not managed", which on the device means "not enforced" — that is why the
boolean `allow_*` restrictions revert correctly. The password scalars are the
only place that silently breaks it. `applyPassword` becomes **fully declarative**:
every field it manages is driven to a definite value on every reconcile, and the
value for "absent" is the permissive one.

⚠️ **This is a deliberate behaviour change.** Removing a PASSWORD policy now
actually relaxes the device, where before it left the old constraint in place. The
old behaviour looked fail-secure but was really just un-clearable state, and it is
what produced a permanently DEGRADED device.

##### Plan (5 steps)

1. **`PasswordPlan.effectiveQuality` returns a non-null `PwQuality`** —
   `UNSPECIFIED` when nothing is asked, rather than null. The applier then always
   has a value to push. Update `charClassMinimumsApply`.
2. **`PolicyApplier.applyPassword` drives every field**, absent → permissive:
   quality always (`UNSPECIFIED` when unset) · `min_length ?: 0` ·
   `history_length ?: 0` · `expiration_days ?: 0` (no expiry) ·
   `max_failed_attempts_before_wipe ?: 0` (never wipe — **the most dangerous one
   to leave latched**) · `lock_timeout_seconds ?: 0`. Char-class minimums are only
   touched when the effective quality is `COMPLEX`, because below it they throw
   `IllegalStateException` (Android reference §6c) and are inert anyway; when it
   *is* COMPLEX, absent ones are pushed as 0.
3. **Agent unit tests** for the new `PasswordPlan` contract.
4. **Docs** — Android reference §6c gains the "absent means permissive" rule and
   why; close R14; retire the W15/W20 "scalars are not reverted" caveats.
5. **Agent v39; hardware-verify on `SM-X520`.** The stuck "Password Test" policy
   must go green and the device return to `compliant`; then prove the cycle both
   ways — add `min_length`, see it latch; remove it, see it released.

##### Status: ✅ COMPLETE and hardware-proven — 464 server tests, 54 agent tests, agent v39 (`0.9.9`) on `SM-X520`.

**The stuck device recovered.** Before v39: `minimumPasswordLength=13` latched,
`set passcode: rejected`, permanently DEGRADED. After:

```
PolicyApplier: passcode set from policy (4 chars)
SyncService: sync: state=54 applied=54 errors=0
dumpsys → passwordQuality=0x20000 (NUMERIC), minimumPasswordLength=0
locksettings verify --old 6819 → Lock credential verified successfully
```

**Latch-and-release proven both ways** on the live policy:

| Policy edit | `minimumPasswordLength` on device |
|---|---|
| add `min_length: 4` | **4** |
| remove `min_length` | **0** |

Device left `compliant`, "Password Test" restored to `{quality: 2,
set_password: "6819"}`.

⚠️ Note for whoever reads the server next: `compliance_detail` lags one check-in.
The agent reports the *previous* pass's `apply_errors`, so a device that has just
fixed itself still shows the old error until it checks in once more. That is by
design (D28 separates intent from reported reality) but it reads as a failed fix.

#### 🔻 W27 — DPC self-update: a first-class agent-update channel (Plan B)

**Why not Plan A.** Pushing the agent through a policy's `required_apps` works —
the spike proved the whole sequence on `SM-X520` — but it is *policy*, so the
updater can be un-assigned by accident, its ordering inside a reconcile pass is
uncontrolled, and there is no rollout control. A bad build reaches the entire
fleet at once, and **there is no rollback**: Android refuses a downgrade, so the
only cure is a new build with a higher `versionCode`. A canary gate is therefore
not a nicety, it is the whole point.

**What the spike already settled** (Android reference, `PackageInstaller`
self-install): the commit survives the caller's death, the result callback never
arrives so silence is success, `MY_PACKAGE_REPLACED` recovers in ~4.4 s, and
there is no update loop. The mechanism is proven; W27 adds *control*.

**Design, kept deliberately small.** No new release table and no status machine —
agent builds are already `AppPackageVersion` rows for `org.takmdm.agent`, which
is where the upload history and the content-addressed artifact already live. All
that is missing is which version is aimed at whom.

* One setting: `agent.current_version_code`, the build published to the fleet.
  Unset means the channel is inert.
* One device fact: `Device.agent_version_code`, reported at check-in — the gate
  needs the code, and today only the display `agent_version` string is reported.

**D33 — no canary tier; staging is a separate instance.** The first cut had a
`candidate` pointer and a `Device.is_agent_canary` flag, so a build could reach a
few devices before the fleet. Removed at the operator's direction: builds are
proven on a development ATLAS instance and only a build that has already been
through it is ever uploaded to production. Fleet segmentation would have been a
second, weaker copy of a control that already exists upstream — and it put an
"unproven build" concept into the production server, which has no business
holding one. A production server that has a build has been told to run it.

The per-device gates stay, because they are about the *device's* condition
rather than the build's, and nothing upstream can know them.

**Eligibility, per device, evaluated server-side at check-in.** Offer the
published build, and only when **all** hold:
1. it is newer than the device's reported `agent_version_code`;
2. the device is **not** `degraded`/`failed` — never stack an agent swap on a
   device that is already failing to apply things;
3. the device has completed at least one clean check-in **on its current agent
   version** — the settle rule, so a crash-looping build cannot churn.

##### Plan (7 steps)

1. **Model + migration.** `Device.is_agent_canary` (bool) and
   `Device.agent_version_code` (int|null). Alembic on top of `h8j0l2n4p6r8`.
2. **Service `agent_update.py`.** `offer_for(session, device) -> dict | None`
   implementing the three rules above, with the decision logic pure enough to
   unit-test without a device.
3. **Check-in wiring.** `CheckinRequest.agent_version_code`;
   `CheckinResponse.agent_update` = `{package_name, version_code, version_name,
   sha256, size_bytes, url}` or null.
4. **Agent.** Consume `agent_update`, compare against `BuildConfig.VERSION_CODE`,
   download via the existing resumable artifact path, install **last** in the
   reconcile pass and **only when that pass produced no errors**. Log loudly
   immediately before commit — that line is the last thing the dying process
   will ever write.
5. **Console.** Admin → *Agent updates*: the `org.takmdm.agent` version history,
   which build is published, how the fleet has actually landed on it, and
   Publish / Unpublish.
6. **Tests.** Eligibility truth table (newer/older, degraded, settle), the
   check-in contract, the console page.
7. **Hardware on `SM-X520`.** Bootstrap v40 by ADB, then deliver v41 over the
   air and watch it land.

##### Status: ✅ complete. All 7 steps, verified on hardware.

**Done.**

* `Device.agent_version_code`, migration `i9k1m3o5q7s9`, applied to the running
  stack (head confirmed, single column).
* `app/services/agent_update.py`. The gate is a pure `decide()` returning
  `Decision(offer, reason)` — every refusal names itself, because on this one
  feature a silent no-op and a silent disaster look identical from outside.
* Check-in carries `agent_version_code` up and `agent_update` down. The offer is
  built **after** `_record_convergence`, so the compliance gate reads the errors
  *this* check-in reported rather than the previous one's.
* Agent: `Reconciler.selfUpdate()`, called last in `applyDesiredState` and only
  when `errors.isEmpty()`. Logs the replacement immediately before commit.
* Console: Admin → *Agent updates*. Lists every uploaded agent build, publishes
  one, and reports the rollout as five separate numbers rather than a percentage
  — on the build / behind / never reported / **not healthy** / enrolled. The
  unhealthy count is the one that matters: a build that installs and then fails
  to apply policy reads as a completed rollout on any count of installs alone.
* 23 tests (`tests/test_agent_update.py`), suite 464 → **487 green**. Mutation-
  checked: neutering either the settle gate or the compliance gate fails 5.

**Three decisions worth knowing about.**

* *Settled* is computed as "the device reported the same `agent_version_code` it
  reported last time", evaluated **before** the column is overwritten. So the
  first check-in after any update never counts. A build that crashes after
  managing one check-in per launch therefore never gets offered a second update
  — it stays put and stays visible, which is the failure mode we can actually
  fix from the console.
* Publishing a build that is not in the library is **refused at the form**, and
  a published build that is later deleted is called out on the page. Either
  would otherwise make every check-in drop the offer in silence, which looks
  exactly like a fleet that is merely slow to come back.
* A corrupt `agent.current_version_code` makes the channel inert rather than
  raising. A hand-edited setting must not take every check-in in the fleet down
  with it.

##### Step 7 — hardware, `SM-X520`, 2026-09-02

`SM-X520` was on **v39, which predates this protocol**: it neither reports
`agent_version_code` nor consumes `agent_update`, so the gate correctly refused
it and it could never reach a protocol-speaking build over the air. Verification
was therefore three stages, not one:

1. **v40 (`0.10.0`) installed by ADB** — the last manual install. Reported
   `agent_version_code=40`, COMPLIANT, within seconds.
2. **v41 (`0.10.1`) uploaded and published** through the console form.
3. **The device replaced itself.** 3.6 s of management outage, one check-in
   later it reported 41 and COMPLIANT with no `compliance_detail`. Exactly one
   `agent update: replacing` line in the buffer — **no update loop**, and the
   offer stopped on its own once the new code was reported. No acknowledgement
   protocol was needed.

Console after the fact reads: published **41 / 0.10.1**, on this build **1**,
behind **0**, never reported **2**, not healthy **—**, enrolled **3**. The two
"never reported" are the stale `R5CN00TAK0x` test rows, and they demonstrate the
intended refusal rather than a bug.

Full log sequence and two traps are in the Android reference:
`VerificationCheck … Result: Fail(reason=DEVELOPER_FAULT)` appears mid-install
and means nothing (Play Protect allows it two seconds later), and a device on a
pre-`agent_update` build costs exactly one manual install to reach the channel.

⚠️ **The package library is not a record of what is deployed.** Before this it
held builds 38, 4, 3 while the device ran 39 — v39 was built and sideloaded
without ever passing through the server. Publishing 38 would have been a silent
no-op (the gate refuses a downgrade).

#### 🔻 W28 — Release signing for the agent

**Done.** `assembleRelease` used to emit `app-release-unsigned.apk` and say
nothing; that artifact cannot be installed and looks like a real build until a
device rejects it. Now:

* `agent/keystore.properties` (**gitignored**) or `ATLAS_KEYSTORE_*` environment
  variables supply the key. `agent/keystore.properties.example` is the committed
  template. The password is never in `build.gradle.kts` or in git.
* **A release build with no keystore fails**, with the message telling you which
  file to copy. Verified by moving the properties file aside: `BUILD FAILED in 1s`.
* Verified output: `app-release.apk`, one signer, `CN=Michael Leckliter`,
  RSA-2048, APK Signature Scheme **v2**.

**D34 — the signing key is graded with the device CA, not with build settings.**
Android refuses an update whose signing certificate differs from the installed
app's, and Device Owner privilege does not override it. Losing or changing this
key means a **factory reset** on every device that ever ran a build signed with
it — the agent is Device Owner, so it cannot be uninstalled and replaced. That
puts it in the same tier as `pki/ca.key` (R8), and it is why the password lives
outside the repo rather than in a convenience default.

##### ⚠️ Not migrated — this is a decision, not a task

`SM-X520` runs a **debug-signed** build. Moving the fleet to the release key is a
one-way door and costs a **factory reset + re-enrol per device**. Nothing has
been switched. When you decide to:

1. `TAKMDM_AGENT_SIGNATURE_CHECKSUM` must change in the same breath —
   `h5QFWJTb6y5MX0kxuTiEeP7-wzHaSizE5zgAT-PzWA4` (debug) →
   `IJS8zAVMaB9G2MgSN4wHZXzzOd19ToC1RgJrd6_yxkQ` (release). A QR with the wrong
   checksum fails provisioning with a generic message.
2. Delete the existing `org.takmdm.agent` package from the library, or the
   upload is refused — correctly. Attempting it produced:
   *"signing certificate for org.takmdm.agent does not match the stored one
   (have 8794055894dbeb2e…, got 2094bccc054c681f…)"*. **That guard is the reason
   a mis-signed build cannot silently become an undeliverable published build.**
3. Factory-reset and re-enrol each device.

**v42 (`0.11.0`) exists only as a release-signed artifact.** It is not uploaded
and cannot reach the current device. v41 remains the deployed build.

---

#### 🔻 W29 — TAK.gov plugin catalog (TPC Plugins)

**Ask.** A *TPC Plugins* tab in Apps, listing the TAK.gov plugin catalog;
authentication performed in Admin; the tab says so plainly when not linked.

**Source of truth:** `tpc.md` in the repo root. "Link EUD" is not device magic —
it is a stock **OAuth 2.0 Device Authorization Grant (RFC 8628)** against TAK.gov's
Keycloak (realm `TPC` at `auth.tak.gov`, public client `tak-gov-eud`, no secret).
A headless server can complete it and hold the credential indefinitely, because
`offline_access` yields a refresh token that does not idle out.

**Design decisions taken up front.**

* **D35 — one link, not a tenant table.** ATLAS is one instance per operator, so
  `tpc.md`'s per-tenant model collapses to a single row. Kept as a *table* rather
  than settings, because it needs typed fields, timestamps and a state machine,
  and because the refresh token must not sit in `app_setting`, which is plaintext.
* **D36 — the refresh token is sealed in the `TokenVault`.** It is a durable
  bearer credential to a named person's TAK.gov account and it never expires on
  its own. That is the same danger class as an enrollment token, so it gets the
  same treatment rather than a new one.
* **D37 — rotation is the whole risk.** Keycloak issues a **new** refresh token on
  every refresh and invalidates the old one. Crash between "received" and
  "persisted", or refresh twice concurrently, and the link is dead until a human
  re-enters a code at tak.gov. So: one lock around the whole refresh, persist
  before use, and keep the previous token as a one-step fallback. `tpc.md` names
  this the number one outage source and it is the part worth over-engineering.
* **D38 — CIV by default, and the licence difference is shown, not buried.**
  ATAK-CIV object code carries a distribution grant; **ATAK-MIL explicitly does
  not**, and GOV/MIL plugins carry access and export controls. The console
  defaults to `ATAK-CIV` and states this where the operator picks a product.
* **D39 — `eud_api` is undocumented and unversioned**, so it goes behind a thin
  adapter with contract tests, and every field is parsed defensively. A field
  rename upstream should degrade a column to "—", not take down the Apps page.

##### Plan (7 steps)

1. **Model + migration.** `TakGovLink` (single row): status, `device_code`,
   `user_code`, `verification_uri_complete`, sealed `refresh_token`, previous
   sealed token, cached `access_token` + expiry, linked-account label, timestamps,
   `last_error`.
2. **Client adapter** `app/services/tak_gov.py`: `start_link`, `poll_once`
   (RFC 8628 — handles `authorization_pending` and `slow_down` rather than
   ignoring them, which is where OpenTAKServer's implementation stops),
   rotation-safe `access_token()`, `list_plugins()`. Pure parsing split from I/O
   so the contract is testable without a network.
3. **Link lifecycle service** — start / poll / unlink, and the background poller.
   The admin starts a link, leaves for tak.gov, and comes back; the console must
   show progress without the operator holding the page open.
4. **Admin console** → *TAK.gov* tab: not-linked state with a Link button, pending
   state showing `user_code` + the verification URL (and a QR, which the console
   can already render), linked state showing the account and an Unlink.
5. **Apps console** → *TPC Plugins* tab: catalog table when linked; when not,
   an explicit "not linked" panel pointing at Admin → TAK.gov.
6. **Import** a catalog plugin into the local package library: download, verify
   `apk_hash` **before** it touches storage, then hand it to the existing
   `package_service` upload path so identity comes from the APK itself.
7. **Tests.** Device-flow state machine, rotation safety (including the crash
   window), defensive catalog parsing, both console surfaces. No live network.

⚠️ **Natural split** if this runs long: 1–5 + 7 (auth and read-only catalog — the
whole of the stated ask) as one checkpoint, then 6 (import) after.

##### Status: ✅ complete. All 7 steps, verified against the live service.

**Done.**

* `TakGovLink` (single row) + migration `j0l2n4p6r8t0`, applied to the running
  stack. Refresh token sealed in the `TokenVault`, never in `app_setting`.
* `app/services/tak_gov.py` — protocol and catalog, network confined to two
  helpers so every parser is testable offline.
* `app/services/tak_gov_link.py` — start / poll / unlink, and rotation-safe
  `access_token()`.
* Admin → **TAK.gov** tab: not-linked / pending (with the code to type) / linked /
  broken. Apps → **TPC Plugins** tab, which says plainly when nothing is linked
  and points at Admin.
* 45 tests, suite 487 → **532 green**. Both tabs smoke-tested against the live
  stack, not only in tests.

**Decisions taken during the build, worth knowing.**

* **The `TokenVault` is injected, not imported.** Reaching for `get_token_vault()`
  inside the service would bypass the test `dependency_overrides` — the same
  mistake that cost eight failures in W23. Services take a `TokenVault` argument.
* **Polling is a button, not a background task.** The device-code window is about
  three minutes and the operator is standing in front of the console, so "I have
  entered the code" is honest about what is happening and adds no long-lived task
  to babysit. Pressing it early is harmless — `authorization_pending` leaves the
  link untouched, and is deliberately *not* recorded as an error, or the normal
  path would show a red banner.
* **The catalog loads only when asked for** (`/apps?tab=tpc`). Fetching it on
  every visit to Apps would put a third-party call *and* a token rotation in front
  of unrelated work like uploading an APK.
* **Unbinding is the whole operation.** ⚠️ Corrected 2026-09-02: the panel used
  to say the operator should also revoke at tak.gov. **tak.gov offers a user no
  such control**, so that sent people looking for a page that does not exist —
  worse than saying nothing. The console now says nothing about tak.gov on that
  path at all — not a second step, and not a reassurance that there isn't one,
  because raising the question is what invites the doubt. It simply confirms the
  account has been unbound.

##### ✅ Verified against the live service, 2026-09-02

Linked `michael.leckliter@coronaca.gov`, pulled **86 ATAK-CIV 5.8.0 plugins**,
and downloaded one (`com.atakmap.android.oceusvpn`, 17 373 bytes) with a
SHA-256 matching the catalog. Link → catalog → verified download, end to end.

**Four things `tpc.md` had wrong or missing, now corrected there:**

1. **The verification URI.** Documented as `https://tak.gov/register-device`; the
   realm returns `https://auth.tak.gov/auth/realms/TPC/device`, and a code
   entered at the documented page does not work. We were saved only because the
   parser prefers the server's value — hardcoding the documented one, as the doc
   implies, would have sent the operator to a dead end. The *fallback* has been
   changed too, since a wrong fallback is worse than none.
2. **`eud_api` requires HTTP/2** — `421 HTTP/2 Required` over HTTP/1.1. This one
   is nasty: `auth.tak.gov` does not care, so **the link succeeds and only the
   catalog fails**, which reads as an entitlements problem and is not one. Fixed
   with `http2=True`; `h2` is now pinned in `requirements.txt`.
3. **The code TTL is ~3 minutes**, not the RFC default of 10.
4. **`identifier`** (e.g. `wave-5-8-0-civ`) is on every row, is the key both
   `apk_url` and `icon_url` are built from, and is absent from the doc's field
   table. It is now modelled. `os_requirement` also arrives as an int.

**The defensive parsing earned itself.** All 86 rows parsed with no error, and
`identifier` showed up in `Plugin.unknown_fields` on 86/86 — the design surfaced
an undocumented field instead of silently dropping it, which is exactly the
failure this was built to avoid. The only "missing" data was `tak_prerequisite`
on 10 rows, which are standalone apps rather than plugins.

`tests/test_tak_gov.py`'s fixture row is now field-for-field a real one, so it is
a contract test rather than a guess about the contract. 47 tests.

⚠️ **R16 — the refresh lock is process-local.** `threading.Lock` is correct for
the single-worker deployment this ships as. Under multiple workers two processes
could rotate concurrently and kill the link. Same constraint as the push
doorbell; both belong to the multi-worker work in Chunk 11.

##### Step 6 — import, and the console polish that went with it

An **Import** button per catalog row, and an `imported` pill on rows the library
already holds (matched on `revision_code` == `versionCode`, which is what
`tpc.md` says to key on and what Android's upgrade rule uses).

**D40 — the catalog is an ingest source, not an authority.** The APK is
downloaded, hash-checked, and then handed to the ordinary `package_service.ingest`
path, so package name, versionCode and signing certificate are read **from the
file**. A row that mislabels itself cannot smuggle a package in under the wrong
name, and every guard the manual upload already has — signature continuity,
minimum target SDK, duplicate versionCode — applies unchanged and for free. There
is a test that imports an APK whose real identity differs from the catalog row's
and asserts the file wins.

**D41 — the download streams to a temp file.** The largest current ATAK-CIV
plugin is **433 MB**; materialising that as a response body *and* again as bytes
for ingest is most of a gigabyte of peak memory inside one request. The SHA-256 is
computed over the same bytes as they are written, so there is never a window where
a complete-but-unverified APK sits on disk looking usable, and a mismatch deletes
the file before raising.

**Verified on the live service.** Imported `com.atakmap.android.oceusvpn` from
`oceus-vpn-5-8-0-civ`: recorded versionCode `1781188854`, versionName
`1.0 (ac165cf4) - [5.8.0]`, minSdk 21, targetSdk 34, signature scheme **v3** —
all read from the APK. Re-importing is refused with *"version code … is already
uploaded"*; an unknown identifier is refused by name. 6 further tests
(53 in the file, suite **540**), mutation-checked: removing the hash check or the
cleanup-on-mismatch each fail tests.

##### Console polish (same pass)

* A count above the table — "86 plugins for ATAK-CIV 5.8.0".
* ATAK version is a **closed dropdown** (5.1.0 – 5.8.0), not free text. An
  unrecognised version returns an empty catalog, which is indistinguishable from
  an account entitled to nothing — an expensive thing to debug over a typo.
* `Rev` column removed; `Size` no longer wraps.
* 🐛 Fixed while there: the size cell divided by 1024 twice, so **every plugin
  under a megabyte rendered as "0 MB"** — five of the current 86, including the
  very package used to verify the download path. Now `filesizeformat`.

#### 🔻 W30 — Plugin table, and imports you can watch

**Table.** Default sort by plugin name (server-side, so the order is the same
before JavaScript runs); `Package` and `Requires` columns removed with the package
name kept as a sub-line under the plugin name — it is the identity an operator
matches against the local library, so it loses its column but not its place.
`table-layout: fixed` gives the Plugin column the slack and stops the Import
button's column sizing itself past the panel edge.

**D42 — the import moved off the request, because the progress bar had to be
real.** A percentage that is not tied to bytes is worse than no percentage: it
keeps moving through a stall, which is exactly the moment an operator needs the
truth. So `POST /apps/tpc/import` now starts a job and returns `202` with an id,
`GET /apps/tpc/import/{id}` reports `{state, downloaded, total, percent}`, and a
modal polls it. `total` of 0 means the server sent no Content-Length, and the
console then shows bytes-so-far rather than a fabricated fraction.

`app/services/import_jobs.py` is deliberately tiny — no queue, no retry, no
persistence. An import is one operator pressing one button, and a job that dies
with the process is one they can press again. A status poll for an unknown job
answers "the server may have restarted. Press Import again" rather than 404ing
into a modal that spins forever.

**D43 — the session factory is a dependency now** (`get_session_factory`).
Background work cannot borrow the request's session, and the first cut imported
`SessionLocal` directly — which had a test's background thread connecting to the
**real Postgres** mid-run. Third time this shape has bitten (W23, W29); the
factory is injected and overridden in `conftest` like every other dependency.

✅ **Verified live:** imported **UAS Tool at 376.6 MB** from the 5.5.0 catalog.
Progress ran 0 % → 8 → 31 → 53 → 76 → 98 → 100 with byte counts matching, and
finished naming `com.atakmap.android.uastool.plugin` (versionCode 1787086923,
targetSdk 35, 394 892 123 bytes stored). 8 further tests, suite **548**.

##### ⏸️ PENDING — restrict the product dropdown to what the account is entitled to

**Blocked on the operator obtaining an ATAK-GOV account and an ATAK-MIL account
to test with.** Not started; do not implement from inference.

**What is already established** (live, 2026-09-02, CIV-only credential):

* The entitlement signal is the **`groups` claim**, available both in the access
  token body and at the standard OIDC `userinfo` endpoint. The account tested
  carries `Developers`, `Non Commercial`, `Standard SDK`, **`Website Civil Use`**,
  `Website Public`.
* **The catalog API does not enforce entitlement and cannot be used to detect it.**
  All three products answer `200`: CIV 86 rows, GOV 85, MIL 81 — and GOV and MIL
  contain **zero** entries that are not also in CIV. `product` filters the entitled
  set by ATAK-build compatibility rather than opening a tier. So the dropdown as it
  stands actively misleads: choosing ATAK-MIL shows 81 CIV plugins and looks like
  MIL entitlement.
* Downloads are not the enforcement point either — a fetch of the smallest entry
  under each product returned `200` with the same CIV artifact.

**Why this is not being built yet.** `Website Civil Use` → CIV is *verified*. The
GOV and MIL group names are **unknown**, and a sample of one cannot reveal them.
Guessing `Website Gov Use` / `Website Mil Use` is precisely the class of inference
that produced all four corrections at the top of `tpc.md`.

**The experiment to run** once a GOV and a MIL account exist: link each, read
`groups` from `userinfo`, and record the exact strings. Then compare each
account's `ATAK-MIL` catalog against its `ATAK-CIV` one — if a MIL account sees
entries a CIV account does not, that also confirms the subset behaviour above is
an entitlement effect rather than a catalog quirk.

**Design agreed in advance, to avoid re-litigating it:** persist `groups` on the
link row; show them **verbatim** in Admin → TAK.gov so an operator can always see
what their account carries; restrict the dropdown to mapped products; and **fail
open** — if no group matches anything recognised, show all products with a note
rather than locking the console out on a guess. Mark the GOV/MIL patterns as
inferred in code until evidence replaces them.

##### Remaining known gap

⚠️ Import progress lives **in the serving process** (R16 again, alongside the push
doorbell and the token-refresh lock). Under multiple workers a poll could land on
a worker that never heard of the job. Single-worker today; all three move together
in Chunk 11.

---

#### 🔻 W31 — Multiple versions of one package, and downgrades (PLANNED — not started)

##### What already works, so it does not get rebuilt

* **Multiple versions per package already coexist and are kept forever.**
  `AppPackage` → many `AppPackageVersion`, ordered by `version_code`. Uploading a
  different versionCode of an existing package **adds a row**; nothing is replaced
  and nothing is lost. Only a *duplicate* versionCode is refused.
* **Policies can already target a version**: `RequiredApp.min_version_code` is a
  floor, and `RequiredApp.artifact_sha256` pins one exact build.
  `packages.resolve_for_policy` picks the highest version at or above the floor.

##### Two parts of the request that do not survive contact with Android

* ⚠️ **"Create a separate package" is not implementable, and would not help.**
  `AppPackage.package_name` is `unique=True`, and must be: on Android the package
  name **is** the app's identity. Two library entries sharing one package name
  could never both be installed — the second would replace the first. The branch
  offers a choice that cannot exist.
* ⚠️ **"Replace the old one" does not do what it sounds like.** Deleting the older
  version from the library uninstalls nothing from any device, and breaks any
  policy pinned to that build. The library is a record of what *can* be deployed,
  not of what *is*.

So the prompt as described offers a choice between something impossible and
something that already happens automatically. **The question actually worth asking
at upload time is different: "should policies now deploy this build?"** — because
that is the only part of the upload that changes fleet behaviour.

##### What is genuinely missing

1. Upload says nothing about how the new build relates to the ones already held.
2. The Local apps list shows only the newest version, with no sign that others
   exist — the "remind me there is a duplicate" gap in the request.
3. The policy form exposes `min_version_code` as a **bare number box**. An
   operator cannot see which versions exist, let alone pick one, and
   `artifact_sha256` (exact pinning) has no UI at all.

##### Downgrading an app on a device — the hard part

📖 Verified contract (Android reference, W27): **Android refuses to install an
older `versionCode` over a newer one.** Device Owner does not override it;
`INSTALL_ALLOW_DOWNGRADE` / `setRequestDowngrade` are shell/system-only.

The only route is **uninstall, then install the older APK** — which the agent can
already do (`installer.uninstall`). ⚠️ **That destroys the app''s data.** For ATAK
that is configuration, certificates, data packages and mission state; in the field
that is plausibly worse than whatever the downgrade was meant to escape.

⚠️ **Today a downgrade is a silent no-op.** `AppUpdatePlan.decide` returns
`SKIP_UP_TO_DATE` whenever `installed >= desired`, so lowering a policy''s floor
changes nothing and says nothing. Safe, but invisible: the operator believes the
fleet moved and it did not. **Fixing the silence is worth more than adding the
capability**, and should land first.

**Proposed shape**, consistent with D5 (desired state, not commands) and D6:

* The floor going down must **never** trigger a wipe-and-reinstall as a side
  effect of editing a policy.
* The agent reports the refusal as an `apply_error`, naming both versions and the
  reason — the operator learns from the console instead of from a device.
* An actual downgrade requires an explicit per-app opt-in in the spec
  (`allow_destructive_downgrade`, default false) whose label states that app data
  is lost. Desired state still expresses the intent; the flag authorises the only
  transition that can reach it.

##### ⚠️ The finding that reframes this: uploading already deploys

Traced through the code and confirmed against the live database. `upload_app_form`
calls `eff.invalidate_all`, which marks every device''s cache stale **and rings the
doorbell for the whole fleet**. On recompute, `resolve_for_policy` returns the
highest version satisfying the policy''s floor — which is the build just uploaded.
`state_version` bumps and the device upgrades.

Every live policy uses a **floor** (`min_version_code`) and **none** pins an exact
artifact, because `artifact_sha256` has no UI. For example `Install Proof` holds
`com.atakmap.app.civ` at floor `1787255575`; uploading any newer ATAK-CIV build
pushes it to the tablet on the next check-in, with no confirmation anywhere.

So the request inverts. **"Replace with a newer version" is already the default and
the only behaviour** — the upload *is* the replace, and the policies do not need
updating because a floor already resolves to the newest build. What does not exist
is the opposite: **there is no way to add a build to the library without deploying
it.** An operator uploading something "to have it on hand" ships it fleet-wide.

The one case where policies genuinely need re-pointing is an **exact
`artifact_sha256` pin**, which today can only be set through the API.

##### ✅ "Enforce an exact version, including an older one" already works server-side

Probed against the resolver with two builds of one package (100 and 200):

| Policy says | Resolves to | |
|---|---|---|
| no floor, no pin | **200** | latest, as intended |
| `artifact_sha256` = the **100** build | **100** | ✅ an older build *is* enforceable today |
| `artifact_sha256` = a sha not in the library | **200** | 🐛 **R17** |
| `artifact_sha256` = another package''s artifact | **7**, declared as `com.probe` | 🐛 **R18** |

So the missing piece is **UI, not capability** — `artifact_sha256` has no control in
the policy form, so the distinction is reachable only through the API.

⚠️ **Two defects must be fixed before that UI ships**, because both defeat exactly
the feature being asked for:

* ✅ **R17 — FIXED 2026-09-03.** *(was: a pin to a missing artifact silently falls through to latest)*
  `effective_policy.resolve_required_apps` sets `version = None` when the pinned
  file is not found, and the next branch resolves the floor instead. For "hold this
  fleet at an older build" that is the worst possible failure mode: delete the
  artifact and the fleet **jumps to the newest build**, silently, which is the
  precise opposite of the operator''s intent. It must report `available: false`.
* ✅ **R18 — FIXED 2026-09-03.** *(was: a pin is not checked against its package)* The lookup
  is `AppPackageFile.artifact_sha256 == pinned` with no package constraint, so
  pinning another package''s artifact yields that package''s version while still
  being declared under the original `package_name`. The agent would fetch and
  install the wrong app, then never converge, because the named package is still
  absent. The lookup must be joined to the package.

**The fix, in `resolve_required_apps`:** a pin is now **absolute** — it never falls
back to the floor — and its lookup is **joined to the package** it hangs off. An
unhonourable pin reports `available: false`.

⚠️ **A reason now travels with every unavailable app.** The agent and the console
both hard-coded "nothing uploaded", which after this fix would be wrong for two of
the three ways an app can fail to resolve: an unsatisfied floor and a broken pin
read very differently from an app nobody has uploaded. Both consumers now show the
server''s reason, falling back to the old wording only for a server too old to send
one. `tests/test_app_version_pinning.py` — 12 tests, 5 of which fail against the
previous behaviour.

##### Enforcing it *on a device that already has newer* — the genuinely hard half

Pinning covers most of the need cheaply and safely: any device **without** the app,
or with an **older** build, converges on exactly the pinned version. New enrolments,
re-enrolments and wiped devices all land on it.

The hard case is only a device already running something **newer**. There Android
refuses the install outright, and today `AppUpdatePlan` returns `SKIP_UP_TO_DATE`
and says nothing — so the operator pins 5.5.0, sees the policy applied cleanly, and
never learns the device is still on 5.8.0. That silence is the bug worth fixing
first; the destructive uninstall-and-reinstall stays behind an explicit opt-in.

##### Revised strategy

**D44 — a version is `published` or it is not, mirroring the agent-update channel.**
`AppPackageVersion.published`; `resolve_for_policy` ignores unpublished builds.
This is deliberately the same concept, and the same word, as W27''s agent channel:
an operator already knows what "published to the fleet" means here, and a second
vocabulary for the same idea would be worse than the feature is worth.

That makes every case fall out of one rule:

| Upload | What the operator is told | Default |
|---|---|---|
| **Newer** than the deployed build | which policies reference it, which devices they reach, and the version each would move **from → to** | offer **Publish** (deploy) or **Hold in library** |
| **Older** than the deployed build | "this is older than the deployed X; it has been added to the library as a separate version and is **not** deployed" | held, never auto-deployed |
| **Same versionCode** | already refused today, unchanged | — |

⚠️ **Migration hazard:** `published` cannot default to false for existing rows or
the fleet loses its apps at the next recompute. The migration backfills all 18
existing versions as published, and the column defaults true for uploads until the
console flow lands — feature first, default second.

**Publishing an older build** is where this meets the downgrade problem: the
resolver returns it, the agent sees `installed > desired`, and today that is a
silent no-op (`SKIP_UP_TO_DATE`). Making that refusal loud is step 5 and is worth
more than the destructive capability.

##### Plan (7 steps)

1. **`AppPackageVersion.published`** + migration backfilling existing rows true.
   `resolve_for_policy` and the pinned-artifact lookup both skip unpublished.
2. **Compare on upload.** A service returning newer/older/same against the
   deployed build, the policies that reference the package, and the devices they
   reach — the "from → to" an operator needs to decide.
3. **Upload flow** presenting that comparison and asking **Publish or Hold**,
   with older uploads defaulting to held and saying so.
4. **Library UI.** Versions per package with a published badge, a duplicate-version
   marker on the package row, publish/unpublish per version, and deletion guarded
   against any policy pinning that artifact.
5. **Agent: make a refused downgrade loud.** `AppUpdatePlan` gains
   `REFUSED_DOWNGRADE`; the reconciler raises an `apply_error` naming both
   versions. Fixes today''s silent no-op.
6. **Re-point exact pins.** When publishing a newer build, offer to move any
   policy pinning the old `artifact_sha256` — an immutable new `PolicyVersion`
   (D2), which bumps `state_version` and wakes the device. ⚠️ Assignments carrying
   `pinned_version_id` will **not** follow a policy edit; that has to be surfaced,
   not discovered.
7. **Opt-in destructive downgrade** + hardware on `SM-X520`: refused by default and
   reported, then permitted with `allow_destructive_downgrade` and confirming that
   app data is lost.

⚠️ **Natural split**: **1–5** is the whole of "many versions, honestly reported",
ends with the fleet safer than it is today, and cannot lose data. **6–7** add pin
re-pointing and the destructive path.

##### Status: steps 1–5 done, plus the pin UI. Steps 6–7 open.

**Done.**

* `AppPackageVersion.published` + migration `k1m3o5q7s9u1`. All **18** existing
  versions backfilled true, verified against the live database — holding them
  would have emptied the resolver at the next recompute.
* `resolve_for_policy` skips held builds. **Only** automatic selection is gated;
  an explicit `artifact_sha256` pin still reaches a held build, because a pin
  names one exact build deliberately and a second gate with no separate meaning
  would just be R17 wearing a different hat.
* `compare_upload()` — relation, the build being replaced, the policies naming the
  package, and how many devices they reach — computed **before** anything is
  stored. `POST /apps/preview-upload` exposes it without side effects.
* `ingest(publish=...)`. Left unset it defaults by comparison: **newer publishes,
  older is held.** The asymmetry is deliberate — publishing is undone by
  publishing something else, but a fleet that has already upgraded cannot be
  walked back, because Android refuses downgrades.
* Upload now says what it did ("… was published, replacing 100 on 3 devices" /
  "… is being held — devices stay on 200"). It used to deploy fleet-wide in total
  silence.
* Library UI: a package holding more than one version links to a per-version list
  with published/held state and a publish/hold button each.
* **The version picker** (`__version_choice`): *Latest published* / *At least X* /
  **Exactly X, including a held or older build**. One select, because the three
  intents are mutually exclusive and two controls would let an operator express a
  contradiction the resolver then arbitrates silently. This is the "enforce an
  older version" distinction, and it previously had no control at all.
* Agent: `AppUpdatePlan.REFUSED_DOWNGRADE`. A device ahead of its policy raises an
  `apply_error` naming both versions instead of folding into `SKIP_UP_TO_DATE` and
  saying nothing.

✅ **Verified on the live stack with real data.** Imported UAS Tool from the
**5.8.0** catalog next to the **5.5.0** build already published — and 5.8.0''s
build carries the *lower* versionCode (`1787086761` vs `1787086923`). It was held
automatically, and `SM-X520` stayed at `state_version 56`, acked, COMPLIANT.

⚠️ **Worth knowing: a newer ATAK version does not imply a newer versionCode.** The
TAK.gov catalog ships per-ATAK-version builds whose codes do not track the ATAK
version, so "the 5.8.0 one must be newer" is wrong and an operator would
reasonably believe it. The publish/hold default protects against exactly this.

⚠️ **Found while testing: the app-list form parser had no test coverage at all.**
Rewriting the control broke nothing, which is how it was noticed. Now covered.

**Not done: steps 6 (re-point exact pins on publish) and 7 (opt-in destructive
downgrade + hardware).** Nothing so far can lose a user''s data.

##### ⚠️ D45 — an ATAK plugin''s target build is a *variant*, not a version

Raised by the operator, and it invalidates part of the model above. **An ATAK
plugin only loads in the ATAK build it was compiled against**: a 5.5.0 plugin will
not run under 5.8.0. ATAK enforces this itself.

But the two builds share **one Android package name**, so:

* they cannot be separate `AppPackage` rows — `package_name` is unique, and Android
  agrees: only one can be installed on a device;
* **`versionCode` ordering across ATAK lines is meaningless.** Proven on real data:
  UAS Tool for **5.8.0** is `1787086761`, *lower* than the **5.5.0** build''s
  `1787086923`. "Newer ATAK version" and "higher versionCode" are unrelated.

So `published`/`held` — which ranks by `version_code` — **is the wrong comparison
between two builds targeting different ATAK versions.** They are not older and
newer; they are alternatives, and which one is correct depends on the ATAK build
on the device. The current default happened to hold the 5.8.0 plugin, which is
right only if the fleet runs 5.5.0.

✅ **The discriminator is in the APK and needs no catalog lookup**, so it works for
manual uploads too. `AndroidManifest.xml` carries
`<meta-data android:name="plugin-api" android:value="com.atakmap.app@5.5.0.CIV">`,
and `app/artifacts/axml.parse_elements` already returns it — verified against both
imported builds. Nothing new has to be parsed, only kept.

**Proposed (not built):**

1. Store `plugin_api` on `AppPackageVersion`, read from the manifest at ingest.
2. **Never rank across different `plugin_api` values.** An upload targeting a
   different ATAK build is neither newer nor older — hold it and say *why*:
   "targets ATAK 5.8.0; the published build targets 5.5.0".
3. Show it everywhere a version is chosen, so "Exactly 1787086923" reads as
   "13.0.6 for ATAK 5.5.0" instead of an opaque number.
4. Badge a package holding builds for more than one ATAK line — that is the
   operator''s cue that these are variants, not a version history.
5. Selection stays **explicit**: one policy per ATAK line, pinning its plugins.
   That works today with the picker built above. Automatic matching against the
   device''s installed ATAK build is possible later, but it needs the agent to
   report ATAK''s version and would silently pick nothing when it could not match
   — worse than an operator choosing on purpose.

⚠️ Until this lands, **an operator can publish a plugin build that cannot load on
their fleet''s ATAK**, and nothing says so. The plugin installs and simply does not
appear in ATAK, which looks like an MDM failure and is not one.

---

#### 🔻 W32 — Plugin/ATAK compatibility warnings

**Operator's design, taken as given:** *warn, never forbid*; treat the **installed
ATAK as the concrete truth**; put the warning on the **plugin**, never on ATAK; and
**rank versions only within one ATAK line**, because that is the only place a build
sequence is meaningful.

##### The two truths, and why one costs more

* **A — the policy's own intent.** If a policy installs both ATAK and plugins, the
  mismatch is visible at edit time with no device involved. Cheap, immediate, and
  it is what "something in the policy builder" asks for.
* **B — what is actually on the device.** The stronger signal, and the operator's
  example ("UAS Tools 5.5.0, but ATAK 5.8.0 **is installed**"). ⚠️ The agent does
  **not** report installed app versions today — `userInstalledPackages()` exists but
  is used locally for allowlist decisions and never sent. So B needs an agent
  change and a device round-trip before it can say anything true.

Doing A first is not a shortcut: a warning that silently knows nothing (because no
device has reported yet) is worse than one that clearly reasons from the policy.

##### Plan (7 steps)

1. **`AppPackageVersion.plugin_api`** — read from `<meta-data android:name=
   "plugin-api">` at ingest (the existing axml parser already returns it), and
   backfill existing rows by re-reading their stored artifacts.
2. **Rank within an ATAK line only** — fixes the defect D45 identified in W31.
   Two builds with different `plugin_api` are neither newer nor older: hold the
   incoming one and say *why*.
3. **Compatibility service** — pure comparison of an ATAK version against a set of
   plugin targets, returning warnings. Testable without a device or a policy.
4. **Policy builder** shows them inline on the plugin row, non-blocking.
5. **Agent reports ATAK's installed version** at check-in; stored on `Device`.
6. **Device and fleet views** warn where a device's real ATAK does not match the
   plugins assigned to it — truth B.
7. **Tests**, plus a hardware check on `SM-X520`.

⚠️ **Split:** 1–4 + 7 is the policy-builder ask and needs no agent change. 5–6 add
the live truth and require a new agent build.

##### Status: complete. All 7 steps, verified on hardware.

**Done.**

* `AppPackageVersion.plugin_api`, read from the manifest at ingest; migration
  `l2n4p6r8t0v2`, plus `backfill_plugin_api()` for rows uploaded before it existed
  — **7 backfilled** on the live library.
* **Ranking now happens within one ATAK line only.** Two builds with different
  `plugin_api` are alternatives, not a sequence: the incoming one is held. This
  closes the defect D45 identified in what W31 shipped.
* `app/services/atak_compat.py` — pure comparison, no session, no device.
* Policy builder warns inline on the **plugin** row, never on ATAK, and never
  blocks. The version picker now labels each build with the ATAK it targets, so
  "Exactly 1787086923" reads as "— for ATAK 5.5.0".

✅ **The live library demonstrates the exact problem**, which is the best argument
for the feature:

| package | code | targets | published |
|---|---|---|---|
| `com.atakmap.app.civ` (ATAK) | 1787255575 | **5.8.0** | ✅ |
| `…uastool.plugin` | 1787086923 | **5.5.0** | ✅ ← mismatch |
| `…uastool.plugin` | 1787086761 | 5.8.0 | held |

The published UAS Tool is built for ATAK **5.5.0** while the published ATAK is
**5.8.0**. Assign both today and the plugin installs and never appears.

##### 🐛 Found on the way: two `PartRole` enums, and `is` silently lying

`app/artifacts/bundles.py` defined its own `PartRole` alongside the ORM's in
`app/db/models.py`. Both are `str` enums with the same three values, so `==`
matched while **`is` returned False** — code holding a database row and the copy
imported from `bundles` disagreed about a value that printed identically.
`packages.py` imports the `bundles` one, so every
`f.role is PartRole.BASE` over ORM rows in that module was quietly always False.

Caught because the new backfill returned 0 while the same loop worked inline.
Fixed by deleting the duplicate and re-exporting the ORM enum, so there is exactly
one object to be identical to. ⚠️ Worth remembering: a `str` enum makes this class
of bug invisible to `==`, and every other call site
(`enrollment.py`, `agent_update.py`, `routes.py`) happened to import the right one
by luck rather than design.

**Steps 5-7 done.**

* `AppInstaller.installedAtak()` finds ATAK by package prefix (the flavour is part
  of the name: `.civ`, `.mil`) and reports `(package, versionName)` at check-in.
* `Device.atak_package` / `Device.atak_version`, migration `m3o5q7s9u1w3`.
  WARNING: only overwritten **when reported**. An agent too old to send them would
  otherwise erase a good record on every check-in and silently stop the warnings,
  which is the exact failure this feature exists to prevent.
* `atak_compat.for_device()` reads the device's **resolved** apps, so it reflects
  what will actually be installed after floors and pins, not the raw policy.
* The device page names the ATAK it checks against, and says plainly when none has
  been reported. Unknown is not a clean bill of health and must not read as one.

##### One entry per package: refused, not warned about

Two entries for the same package in one policy is now **rejected** by
`AppCatalogSpec`. Unlike a plugin/ATAK mismatch, which has a plausible reason
behind it, this is incoherent: a package name *is* the app's identity on Android,
so one build occupies one slot and a second entry can never take effect.

The realistic mistake it closes is pinning one plugin to two ATAK lines to cover a
mixed fleet. Previously `_merge_by_key` kept the first and recorded a **conflict**
- language meant for two *policies* disagreeing, here a policy disagreeing with
itself - and the resolved state never said which build won. The message names the
remedy: separate policies, each assigned to the devices running that ATAK.

Validation errors also reach the console readable now: a bare `ValidationError`
string carries the model name, a `[type=value_error, ...]` suffix and a repr of the
whole input, which in a redirect banner is noise *and* the part most likely to
survive truncation while the useful sentence is cut.

##### BUG found while verifying live: every console form was returning 500

`_sync_form` did `import anyio` then `anyio.from_thread.run(...)`. **anyio 4.15's
lazy loader does not bind `from_thread` on bare attribute access**; 4.14 did. So
creating or editing any policy or profile through the console 500'd.

WARNING: no test could see it. The venv had 4.14.2 and the image 4.15.0, because
`anyio` arrives as an unpinned transitive dependency and a rebuild moved it. Fixed
by importing the submodule explicitly (correct under either version) and pinning
`anyio==4.14.2`.

WARNING: my first probe reported both environments healthy and was wrong - an
earlier `import anyio.from_thread` in the same process had registered the submodule,
so the later bare access succeeded. A clean process shows False in the container and
True in the venv. Probing a lazy import in a process that has already touched it
proves nothing.

##### Verified on `SM-X520`, 2026-09-03

Agent **v43 (`0.11.1`)** was published while the tablet was offline and it took the
update unprompted on reconnect - the update channel working with nobody watching.
It then reported `com.atakmap.app.civ` / `5.8.0.4 (174b425)[playstore]`, matching
`dumpsys` exactly.

Assigning the published UAS Tool - built for **5.5.0** - produced the warning
against the ATAK actually installed:

> built for ATAK 5.5.0, but the device has ATAK 5.8.0. ATAK loads only plugins
> built for its own version, so this one will install and then not appear.

The whole path - manifest, library, policy, device report, warning - works on real
data the fleet already had.

WARNING: the verification had a side effect worth keeping. The device began
installing the 394 MB plugin before the probe assignment was removed, and finished
afterwards. **Removing an app from `required_apps` does not uninstall it** - nothing
in the desired state says it should go - so it stayed until removed by hand. That is
correct (unrequiring is not forbidding), but it means a policy assigned by mistake
leaves an app behind that no later policy edit clears. `blocked_packages` is the
only thing that removes one.

Device left at `state_version 58`, acked, COMPLIANT, plugin removed.

##### Two verifications run while the device was connected, 2026-09-03

**✅ `REFUSED_DOWNGRADE` fires on hardware.** Built in W31 step 5 and until now only
unit-tested — the code path had never executed on a device. `org.takmdm.testapp`
was installed at versionCode **2**; a policy pinning versionCode **1** produced:

> `org.takmdm.testapp: installed versionCode 2 is newer than the required 1.`
> `Android refuses to install a downgrade, and removing it first would erase the`
> `app's data, so it was left alone.`

Device went **DEGRADED** with that in `compliance_detail`, and the app stayed at 2.
Before this change the same situation returned `SKIP_UP_TO_DATE` and said nothing,
so the device reported COMPLIANT while quietly ignoring the policy.

**🐛 `RESTRICTIONS.screen_timeout_seconds` latches — see R19 above.**

Device left at `state_version 62`, acked, COMPLIANT, screen timeout restored, all
probe policies archived and the probe package deleted.

---

#### 🔻 W33 — WALLPAPER policy

**Ask:** separate uploads for tablet and phone; either or both; the device gets the
one that fits its screen; if only one is uploaded that one applies regardless; and
a console preview showing portrait and landscape.

##### Decisions taken up front

* **D46 — the *device* chooses, not the server.** The desired state carries both
  images when both exist, and the agent picks using its own
  `smallestScreenWidthDp`. The device is the authority on its own screen, and this
  needs no new reporting, no server-side guess, and no re-resolve when a device's
  configuration changes. Only sha256 references travel; the agent downloads the one
  it will actually use.
* **D47 — 600dp is the tablet line.** Android's own resource-qualifier boundary
  (`sw600dp`), so the split matches what every app on the device already assumes
  rather than inventing a threshold.
* **Reuse `ManagedFile`.** A wallpaper is opaque uploaded content with an artifact,
  exactly what that table is for. The spec references files by id as `FILES` does.
* **Warn, never forbid, on aspect ratio.** A phone image on a tablet still applies;
  Android crops. The console says it will look wrong rather than refusing.

##### Plan (6 steps)

1. **Spec** `WallpaperSpec`: `tablet_file_id`, `phone_file_id`, both optional, plus
   `lock_screen` (apply to lock as well as home) and `prevent_user_change`. At least
   one file required, or the policy does nothing and should say so.
2. **Resolver** turns file ids into artifact references, exactly as `FILES` does,
   so a deleted file fails loudly rather than resolving to nothing.
3. **Agent** `WallpaperPlan` — a pure choice of tablet/phone/neither given the two
   ids and `smallestScreenWidthDp`, unit-tested off-device — plus the
   `WallpaperManager` apply. ⚠️ Needs `SET_WALLPAPER`, which the manifest does not
   currently declare.
4. **Console**: upload both slots, and a **preview** rendering the chosen image in
   portrait and landscape frames at phone and tablet aspect ratios.
5. **Tests** on both sides.
6. **Hardware on `SM-X520`** — a tablet, so it should take the tablet image; then
   with only a phone image uploaded, it should take that instead.

⚠️ **Unknown to settle on hardware, not by reasoning:** whether
`DISALLOW_SET_WALLPAPER` blocks the *agent* as well as the user. If it does,
`prevent_user_change` and the policy itself are mutually exclusive and the order of
operations matters. Recorded rather than assumed (rule 6).

##### Status: complete. Verified on `SM-X520`.

**Done.** `WallpaperSpec` (two slots + `lock_screen` + `prevent_user_change`),
resolution through `ManagedFile`, `WallpaperPlan` on the agent, the console control
with a portrait/landscape preview, 14 server tests and 6 agent tests.

✅ **Both rules verified on hardware.** With both images uploaded the tablet chose
correctly — `applying TABLET wallpaper (smallestScreenWidthDp=823)` — and with only
a phone image it took that instead: `applying PHONE wallpaper (…=823)`. The screen
confirmed it both times.

##### 🐛 The bug that 639 passing tests did not catch

Resolution worked, the effective-policy payload carried the wallpaper, every test
passed — and **the device was never told**. `desired_state.build` enumerates the
bundle's keys explicitly (`policy`, `apps`, `files`), so a new section is invisible
until it is named there. The device reported COMPLIANT throughout, because from its
point of view there was nothing to do.

⚠️ Worth generalising: **adding a section to the effective policy is two changes,
not one.** Tests that stop at the resolver will pass while the fleet does nothing.
There are now two tests asserting the wallpaper reaches the *signed bundle*, and
both fail if that line is removed.

⚠️ Also learned: **changing the bundle's shape does not bump `state_version`.**
Change detection compares the payload, and the payload was already correct — so a
converged device kept its cached state and never saw the new field until an
unrelated change moved it. Fine in practice (any policy edit pushes it) but it made
the fix look like it had failed.

✅ **Removing the policy reverts to the device default** (operator's call, agent
v47). `WallpaperManager.clear(FLAG_SYSTEM or FLAG_LOCK)` restores the factory
wallpaper, so unlike R19 there is nothing to remember — the user's own previous
picture is not recoverable from the platform in any case, and the factory default
is a definite state rather than a guess.

Two things it deliberately does **not** do, both the R19 lesson in mirror image:

* it never clears a wallpaper **the agent did not set** — that would replace a
  user's own choice with a default nobody asked for;
* it never clears when a slot is filled but its **file has left the library**. That
  is a broken policy, not a removed one, and wiping the screen would turn a
  reported error into a visible change.

`DISALLOW_SET_WALLPAPER` is lifted before the clear, since the restriction may
block the agent as well as the user — leaving it would strand the device on an
image no policy asks for and the user cannot change.

✅ Verified on `SM-X520`: with the policy gone and the blue image still on screen,
v47 logged *"no policy sets a wallpaper; restoring the device default"* and the
tablet returned to the stock Samsung wallpaper, byte-for-byte the baseline.

##### 🐛 Pre-existing: a single-page policy type rendered a blank edit form

`policy_detail.html` marked every page panel `hidden` but only drew the rail that
reveals them when a type had **more than one** page. `FILES` and `NETWORKS` are both
single-page, so their edit forms have been blank since the rail landed; `WALLPAPER`
is simply the type that made it obvious. The panel is now hidden only when there is
a rail to unhide it.

---

#### ⏸️ Hotspot configuration — asked for, and not possible on AOSP

**Ask:** default hotspot SSID, password, band, timeout.

**Finding (2026-09-03):** ❌ not available to a normally-installed Device Owner.
Confirmed three ways — `setSoftApConfiguration` is absent from the public SDK
(`javap` on `android.jar` shows only the local-only hotspot and a validator),
`DevicePolicyManager` exposes no tethering API at all, and the config is not in
`Settings.Global` so the DO's three-key `setGlobalSetting` allowance cannot reach
it. Full detail in the Android reference.

**What is available** is allow/forbid, via user restrictions the agent does not yet
wire: `DISALLOW_WIFI_TETHERING` (API 33+, and minSdk is 33), plus
`DISALLOW_CONFIG_TETHERING`, `DISALLOW_SHARING_ADMIN_CONFIGURED_WIFI`,
`DISALLOW_CHANGE_WIFI_STATE`, `DISALLOW_CONFIG_WIFI`, `DISALLOW_WIFI_DIRECT`,
`DISALLOW_ADD_WIFI_CONFIG`, `DISALLOW_NETWORK_RESET`.

**Not started — the operator's call**, because what can be delivered differs
materially from what was asked. Adding the tethering restrictions to `RESTRICTIONS`
is a small, well-understood change; setting the SSID is a vendor-layer feature that
belongs with VPN profiles and the all-files app-op. Recorded in `docs/KNOX.md` as **§4.1a — wanted, plausible, not yet verified**, a
table kept deliberately apart from the confirmed wins, and as **question 5** for
Samsung. `net.wifi` is the plausible home; three Knox capability claims in this
project have already proved wrong on inspection, so it stays a question until the
SDK is in hand.

---

#### 🔻 W34 — Rename the DPC to `com.taksolutions.atlasmdm`

**Operator's decision.** `org.takmdm.agent` was a working name; the product ships
as **ATLAS MDM** from **TAK-Solutions**, and the package should say so.

Hyphens are illegal in a package segment (each is a Java identifier), so
`tak-solutions` becomes `taksolutions` — Google's own guidance is to drop the
invalid character rather than substitute an underscore.

##### ⚠️ This is a one-way door, and this is the cheapest moment it will ever be

Android treats a renamed package as a **different app**. It is not an update: the
old agent stays installed and the new one is a stranger to it. Because the agent is
Device Owner it cannot be uninstalled, so every enrolled device needs a **factory
reset and re-enrolment**.

Today that is **one tablet**. After distribution it is every device every operator
has ever enrolled. There is no migration path to buy later.

⚠️ **Fold in the release-signing switch if it is wanted.** Chunk 11 already carries
a factory reset for the same class of reason (a signature change is equally
un-updatable). Doing both in one pass costs one reset instead of two. Left out of
this chunk unless the operator says otherwise.

##### What does *not* change

* **The signature checksum.** `EXTRA_PROVISIONING_DEVICE_ADMIN_SIGNATURE_CHECKSUM`
  is the SHA-256 of the *signing certificate*, not of the package, so it is
  untouched by a rename.
* **`versionCode` continuity.** Kept running (48 next) rather than restarting at 1.
  Nothing requires continuity across a package rename, but the changelog, the
  Android reference and the agent-update history all number builds this way, and
  resetting would make every existing note ambiguous.

##### Plan (6 steps)

1. **Agent sources.** Move `java/org/takmdm/agent/` → `java/com/taksolutions/atlasmdm/`,
   rewrite `package`/`import`, and set `applicationId` + `namespace`. Same for the
   test source set.
2. **Hardcoded identifiers**, which a directory move does not catch: the broadcast
   actions (`…CONFIGURE`, `…INSTALL_RESULT`, `…UNINSTALL_RESULT`) and the
   fully-qualified references inside `DebugConfigReceiver`. Internal and
   non-exported, so renaming them is safe and keeps them consistent.
3. **`testapp`** → `com.taksolutions.testapp`. A sibling, not a child: it is a
   separate app used to prove install/uninstall, and nesting it under the DPC's
   name would imply it ships as part of it.
4. **Server + docs.** `agent_package_name`, `agent_admin_receiver`, the guides, and
   the Android reference — keeping the old string where it records what was
   *observed at the time*, since rewriting history would falsify the evidence.
5. **Tests**, both suites, then a build.
6. **Hardware.** Factory-reset `SM-X520`, re-enrol under the new package, confirm
   Device Owner, check-in, and one policy applying end to end.

⚠️ **Split:** steps 1–5 are reversible and land nothing on a device. Step 6 is the
one-way door and needs a separate go-ahead.

##### Status: steps 1–5 done. Step 6 (factory reset) awaiting go-ahead.

**Done.** 44 agent sources moved with `git mv` (history preserved) to
`java/com/taksolutions/atlasmdm/`, `applicationId` and `namespace` set, the
broadcast actions and `DebugConfigReceiver`'s fully-qualified references renamed,
`testapp` → `com.taksolutions.testapp`, server defaults, the kiosk guide, the
instruction lines in the Android reference, and both test suites. Agent unit tests
pass, server suite **641 green**, and the built APK verifies through our own parser
as `com.taksolutions.atlasmdm`, declaring
`com.taksolutions.atlasmdm.admin.MdmDeviceAdminReceiver` — which is exactly what
`agent_admin_receiver` names, so the QR validation will pass.

**versionCode bumped 47 → 48 (`0.13.0`).** Not required — a rename makes a new
package and 47 would have been legal — but v47 already exists as a *different APK*
under the old name, and two artifacts sharing a versionCode across a rename is a
trap when reading update history. 48 marks the boundary.

⚠️ **`org.takmdm.*` still appears in the docs, deliberately.** Instructions and
current values were updated; **captured `logcat` and `dumpsys` excerpts were not**,
because they record what a device actually printed. Rewriting them would make the
evidence describe something that never happened. A note at the top of the Android
reference says so, so the mixture does not read as staleness later.

##### Step 6 — the operator is doing the reset; the server is ready for it

`SM-X520` still runs `org.takmdm.agent` as Device Owner. The new package is a
different app to Android, and a Device Owner cannot be uninstalled, so the device
needs a **factory reset and re-enrolment**. Nothing above has touched it, and the
device is **off the LAN**, so this could not be verified here.

**Prepared and verified server-side:**

* `com.taksolutions.atlasmdm` **48 (`0.13.0`)** uploaded and **published** to the
  agent-update channel.
* 🐛 **Caught while doing so:** `agent.current_version_code` was still `47`, and
  after the config change that number resolves against the *new* package name —
  which had no builds. The channel was pointing at nothing, silently. This is the
  exact shape `offer_for` drops without comment; it only surfaced because the
  rename forced a look. Now `48`.
* `/api/v1/provisioning/agent.apk` re-checked end to end: it serves the **renamed**
  build and declares `com.taksolutions.atlasmdm.admin.MdmDeviceAdminReceiver`,
  which is what `agent_admin_receiver` names — so the QR component validation
  passes. The enrollment page renders with no mismatch error.
* Primary enrollment token **active**.
* ✅ The provisioning **signature checksum is unchanged**
  (`h5QFWJTb6y5MX0kxuTiEeP7-wzHaSizE5zgAT-PzWA4`), confirming the prediction that
  it hashes the signing certificate rather than the package.

##### ⚠️ Re-enrolment cannot complete off-LAN

Both provisioning URLs are private addresses:

```
TAKMDM_SERVER_URL   = https://192.168.68.89:8443
TAKMDM_AGENT_APK_URL= http://192.168.68.89:8080/api/v1/provisioning/agent.apk
```

A QR carries both to the device, so a device that cannot reach `192.168.68.89`
fails at the APK download — and provisioning failure costs another factory reset
before the next attempt (§1 of the Android reference). **Reset freely; enrol only
when the device and this server are on the same network**, or after pointing both
variables at an address the device can actually reach.

The bench alternative needs USB, not the LAN:
`adb install -r app-debug.apk` then
`adb shell dpm set-device-owner com.taksolutions.atlasmdm/.admin.MdmDeviceAdminReceiver`
on a reset, account-free device.

⚠️ **`TAKMDM_` is still the server's environment-variable prefix**, deliberately.
It is the deployment interface — every `.env`, the compose file and the install
guide use it — and it has nothing to do with the Android package name. Renaming it
would break every existing deployment for cosmetic consistency, so it is left as a
separate decision rather than folded into this one.

⚠️ **Still worth folding in the release-signing switch** before the reset is spent
— it needs one for the same reason, and doing both together costs one reset instead
of two.

---

### Later chunks (sketch — to be detailed at approval time)

| # | Chunk | Notes |
|---|---|---|
| 7 | **Knox layer** | Planned in detail below |
| 8 | TAK pack | ATAK policy type: data packages, `.pref` files, plugin sets, cert enrollment |
| 9 | ~~Admin UI~~ | ✅ Delivered as W1–W24 |
| 10 | Offline / LAN relay | Only if required — D9 keeps the door open |
| 11 | **Hardening for distribution** | New, from the scope change below. Auth defaults, `pki/ca.key` at rest (R8), multi-worker push (R7-adjacent), a real install guide |

### Scope change (operator, 2026-09-02)

ATLAS is to be **published as a repo other people self-host** — not a single
private deployment. Two consequences:

* Knox has to work on a **bring-your-own-licence** basis, with no Samsung
  relationship required of the downstream operator.
* The current dev defaults become real risks for a stranger's deployment:
  `TAKMDM_ADMIN_AUTH_MODE=disabled` out of the box, an unencrypted CA key at
  `pki/ca.key` (R8), and a live-push bus that assumes a single uvicorn worker.
  Those belong in a deliberate **Chunk 11**, not as a surprise.

### Chunk 7 — Knox layer

**Read [docs/KNOX.md](docs/KNOX.md) first.** It carries the licensing model, the
distribution analysis, the assessed capability surface, and — importantly — the
walls Knox does **not** close, so they are not re-litigated.

**Settled by research (2026-09-02):**
* **SDK, not KSP.** KSP/OEMConfig requires managed Google Play; ATLAS has none by
  design (D11). The SDK path is Play-free end to end.
* **KPE Premium is free**, customer-generated in the Knox Admin Portal. No
  partner agreement needed for their key to work. R3 corrected accordingly.
* **`knoxsdk.jar` is `compileOnly`** — no Samsung code in the APK. Skip
  `supportlib.jar` (that one *is* packaged, and is only for Knox ≤ 2.7.1).
* **Build against what AE never attempted** — firewall, attestation, audit log,
  per-app VPN, cert provisioning. Anything resembling a nicer AE feature is being
  deprecated and is a bad bet.

##### Plan (5 steps)

1. **Flavours.** Gradle `aosp` / `knox` product flavours; `src/knox/kotlin/` and
   a gitignored `libs/knoxsdk.jar`. `assembleAospDebug` must stay the default and
   stay green on a fresh clone with no jar; the `knox` flavour fails with a clear
   message when the jar is missing. Both suites still pass.
2. **Licence plumbing.** `knox_license_key` admin setting → desired state →
   agent `activateLicense` + the `KNOX_LICENSE_STATUS` broadcast → activation
   state reported on check-in and surfaced on the device page and the ATLAS MDM
   app's Device tab. Failure falls back to AOSP, loudly.
3. **`KNOX` policy type** in the registry + the creator-catalog category wired
   (the placeholder already exists).
4. **Firewall first** — the highest-value capability with no AOSP equivalent —
   end-to-end through the existing `OemPolicyApplier` seam, proving it carries a
   real feature rather than a stub.
5. **Docs + release.** Promote `docs/KNOX.md` §5 into the README; publish both
   flavour APKs as release artifacts.

**Blocked on nothing** except that step 5's *published* `knox` APK depends on
Samsung's answer to KNOX.md §7 Q1. Steps 1–4 can proceed regardless; worst case
the `knox` flavour is build-it-yourself.

---

## Open questions / risks

| # | Item | Status |
|---|---|---|
| R1 | ~~Writing to `/sdcard/atak/` needs `MANAGE_EXTERNAL_STORAGE`~~ ✅ **CLOSED 2026-09-01, hardware-verified.** A map source was pushed by policy to `/sdcard/atak/imagery` and landed byte-identical in ATAK's own directory tree, with all-files access granted once at provisioning. No Knox, no root. Original concern: it needs `MANAGE_EXTERNAL_STORAGE`, an app-op that `setPermissionGrantState` does not grant. Matters for the TAK pack: ATAK config is not in a MediaStore collection, so shared-storage APIs do not reach it. | ✅ **Downgraded to an implementation choice, 2026-08-31.** The operator has seen a commercial MDM push files into ATAK directories on Device Owner devices with an MDM app as manager. So it is demonstrably achievable and no longer a design risk — only a question of which mechanism. On Samsung the overwhelmingly likely answer is Knox permission/app-op control, which is already the chosen path (D11). **Design response:** file push sits behind its own interface with a Knox implementation first and a one-time-grant fallback (Settings special-access, or a persisted SAF directory grant — one tap at provisioning, acceptable on a kiosk device). Costs nothing to build defensively, so no further investigation is warranted before Chunk 5. |
| R2 | OBB placement for XAPKs inherits R1 | ✅ **CLOSED 2026-09-02 — not feasible, made loud (W17).** A `probe_obb` write to `/sdcard/Android/obb/org.takmdm.testapp/` on `SM-X520` returned `EACCES` even with all-files access. Scoped storage blocks writing another app's `Android/obb/` for a normally-installed Device Owner (same class as VPN — needs Knox or root). Resolution: the agent raises an apply_error (device `DEGRADED`, operator sees it) instead of skipping silently; the Apps page flags any package carrying an OBB; recorded in the Android reference §6. **Re-check on `SM-G736U1` / `SM-X828U` (R5)** — the probe action ships for it. ⬇️ **Urgency downgraded 2026-09-02: no package we deploy carries an OBB.** ATAK 5.8.0.4 is one self-contained 112 MB APK (no OBB, no expansion-downloader library; its bulk is `lib/` at 128 MB of native geospatial code, and its map data goes to `/sdcard/atak/…`, which R1 covers). `butterfly-iq-2.49.0.xapk` is base + feature splits, also no OBB. The hardware verification used a **synthetic** `build_xapk(with_obb=True)` fixture, so the error path is proven but nothing real triggers it. Keep the loud failure; stop treating this as a Knox driver. |
| R3 | ~~Knox partner application pending — gates KME **and KPE**~~ | ⚠️ **Largely stale, corrected 2026-09-02 — see [docs/KNOX.md](docs/KNOX.md).** KPE is **not** gated on a partner agreement: **KPE Premium is free** and the *end customer* generates their own key self-service in the Knox Admin Portal. A Knox **developer** account is needed only to download the SDK, which is a build-time concern for whoever compiles the agent — and the jar is `compileOnly`, so no Samsung code ships in the APK. **What remains open:** (a) whether Samsung permits distributing a Knox-built APK to third parties (a licence-agreement question, in the express-approval conversation now); (b) **Knox Mobile Enrollment** for a self-hosted EMM — that part of R3 stands. AOSP path must still not depend on Knox. |
| R4 | `INTERSECT` on app allowlists is correct but counter-intuitive | Make configurable per policy; show resulting set before publish |
| R14 | ~~**Password scalars latch on the device and are never released.**~~ | ✅ **CLOSED 2026-09-02 by W26, hardware-verified.** `applyPassword` is now fully declarative — every field it manages is driven to a definite value on every reconcile, and absent means permissive (`0` / `UNSPECIFIED`). The stuck `SM-X520` recovered: `minimumPasswordLength` released 13 → 0, the operator's 4-digit passcode applied, device back to `compliant`. Latch-and-release proven both directions. ⚠️ **Deliberate behaviour change:** removing a PASSWORD policy now genuinely relaxes the device. The old behaviour looked fail-secure but was un-clearable state. Original text: the scalars were pushed when set and never cleared when dropped (W15's limitation, made acute by W20's `set_password`), which permanently DEGRADED a device with no console-side fix. |
| R15 | **The agent signing key is a fleet-wide single point of failure.** Android refuses an update signed with a different key, so losing it means no device can ever be updated again without re-provisioning. | Open. Same class as `pki/ca.key` (R8) and belongs in the same KMS/HSM answer. Called out now that OTA self-update is proven and will become the update path. |
| R5 | Mixed SoC vendors (Qualcomm XCover6 Pro / MediaTek Tab S10+) on One UI 8 | Test every firmware-level behavior on **both** models |
| R6 | ~~Advanced Protection Mode blocks Device Owner install~~ | ✅ **Downgraded to low, 2026-08-31.** The operator runs commercial MDMs and Headwind in production on this exact hardware and One UI 8, installing apps successfully. Device Owner `PackageInstaller` holds system install privilege and does not go through the user-facing "install unknown apps" gate — as predicted, now corroborated by production use rather than documentation. Residual risk is only a user *opting into* Advanced Protection, which a Device Owner can largely prevent by restricting Settings anyway. No lab work needed. |
| R7 | mTLS header trust: nothing in code stops the app being exposed directly, where a copied certificate in `x-ssl-client-cert` would authenticate without the private key | **Partly mitigated.** A reference nginx config now ships in [docker/nginx/nginx.conf](docker/nginx/nginx.conf) — it always overwrites the header, so a forged one is stripped, and rejects uncertified requests to `/api/v1/device/` at the edge. `scripts/dev_enroll.py` verifies both behaviours on every run, and demonstrates the direct port accepting the forged header. **Still open in code:** the app does not refuse to start when no trusted proxy is configured. |
| R10 | ~~The admin console has no authentication~~ | ✅ **Closed (Chunk 8).** Authentik forward auth with group-based authorization, failing closed, applied at router registration. `disabled` remains the local-development default and says so loudly at startup and in the UI. |
| R12 | **`pki/token_vault.key` now decrypts every enrollment token secret** (D74). Combined with a database dump it yields working enrollment credentials. | **Accepted, bounded.** It sits beside `ca.key`, which is strictly more dangerous, so it does not change what must be protected — only how much is lost if `pki/` leaks. Rotating it invalidates QR re-display for existing tokens but not the tokens themselves. Folded into R8's KMS/HSM answer. |
| R11 | ~~**No CSRF protection on the console's form posts.**~~ ✅ **Closed (Chunk 13).** Identity-bound signed tokens on the console's forms, plus origin validation on every unsafe admin request. Verified live in `forward_auth` mode. Original text: **No CSRF protection.** With forward auth, a signed-in administrator visiting a hostile page could have their browser submit a policy change or enrollment token. Authentik's session cookie would be sent with it. | ✅ **Closed.** Two layers: a token signed over the administrator's identity on form submissions, and origin validation covering the API endpoints a cross-site form can reach. Both applied at router registration, so a new admin route is protected by default (D70). Set `TAKMDM_CONSOLE_ORIGIN` in deployment — the app warns loudly at startup if authentication is on and it is not. |
| R9 | **Pre-granting `WRITE_EXTERNAL_STORAGE` locks an app out of `MANAGE_EXTERNAL_STORAGE`** on Android 11+. Auto-granting runtime permissions is otherwise the obvious thing to do as Device Owner, so this fails silently and looks like an unrelated storage bug. Confirmed in Headwind's source, where they work around it explicitly. | **Open, must be handled in Chunk 6.** When pre-granting permissions, detect apps declaring `MANAGE_EXTERNAL_STORAGE` and skip the legacy storage permissions for them. Affects ATAK directly. |
| R8 | CA private key is stored unencrypted at `pki/ca.key` (mode 0600, gitignored). Anyone holding it can mint a device identity. | **Open.** Acceptable on a single trusted host where the DB is equally exposed; move behind a KMS/HSM before that stops being true. |
| R13 | ~~**D24's re-enrolment matching is single-keyed and brittle.**~~ ✅ **Closed (Chunk 11), hardware-verified.** Identity is now a set; the tablet re-enrolled from a cleared identity into its own record and kept its policy stack. Original text: **D24's matching was single-keyed.** The server matches a re-enrolling device on `serial_number` alone. A device whose reported identity ever changes — as happens when it moves off the `ANDROID_ID` fallback onto its real serial, or after any identity-source change — creates a **new record** rather than re-adopting its own, orphaning history and group membership. Root cause of the fallback is fixed (D95), but `dd814571…` is still registered under its old fallback identity, so its next wipe produces one final duplicate. | ✅ **Closed.** Option (c) was taken: a device enrols with a set of identifiers and the server matches on any known one. `dd814571` matched on its old `ANDROID_ID` fallback, re-adopted its record, had its display serial promoted to `R5GL40MMHRN`, and kept `PASSWORD.min_length 13` from `Tablet Live Test`. The feared final duplicate never happened. |
| Q1 | ~~Which Samsung models / One UI versions?~~ | ✅ **Answered** — see device matrix |
| Q2 | ~~Existing ATAK deployment to integrate with?~~ | ✅ **Answered** — no upstream integration; ATAK server is configured **on the EUD**, so the TAK pack is pure config push (Chunk 7) |

### Retired

- **Minimum installable `targetSdk`** — Android 16 holds at **API 24**, unchanged from
  Android 15 (it did not increment). Normal APKs including ATAK clear this easily.
  Not a blocker; the server should still validate `targetSdk >= 24` at upload so the
  failure is legible there rather than as `INSTALL_FAILED_DEPRECATED_SDK_VERSION` on device.

---

## Changelog

- **2026-09-02** — **W26: R14 fixed — password scalars release instead of
  latching.** 464 server tests, 54 agent tests, agent v39 (`0.9.9`).
  `applyPassword` is now fully declarative: every field it manages is driven to a
  definite value each reconcile, with absent meaning permissive. The stuck
  `SM-X520` recovered — `minimumPasswordLength` released 13 → 0, the operator's
  4-digit passcode applied, device `compliant`. Latch-and-release proven both
  ways (add `min_length: 4` → 4; remove → 0). **Deliberate behaviour change:**
  removing a PASSWORD policy now genuinely relaxes the device. The most dangerous
  case this fixes is a stale `max_failed_attempts_before_wipe` — a device could
  have wiped itself for a policy long since unassigned.
- **2026-09-02** — **Spike: OTA agent self-update works; and a real password bug
  found.** Agent v38 (`0.9.8`). Pushing the agent to itself via a policy's
  `required_apps` upgraded `SM-X520` from v37 → v38 with a **~4.4 s** management
  outage, **no phantom error**, and **no update loop**. Contract recorded in the
  Android reference. **Incidentally exposed a real bug:** the operator's "Password
  Test" policy (`quality: 2`, `set_password: "6819"`) is rejected on-device because
  `minimumPasswordLength=13` is still **latched** from a policy that no longer
  applies — the W15/W20 "scalars are applied but never reverted" gap, now causing a
  user-visible failure rather than a theoretical one. See the risks table.
- **2026-09-02** — **W25: cleared every outstanding hardware verification.** No
  code; agent v37 installed on `SM-X520`. **W24** — the DPC Policies tab lists
  three policy *names* and no field contents. **W23** — the "Check in now" button
  returned `woken: true` and the device checked in **702 ms** later. **W17** — a
  synthetic OBB-carrying XAPK made the agent raise the OBB apply_error and the
  device go DEGRADED with it in `compliance_detail`. Test artifacts removed;
  tablet back to `state 48 acked 48 compliant`. Android reference §6 promoted the
  OBB apply_error path to ✅ verified. **Nothing is now built-but-unproven.**
- **2026-09-02** — **Knox assessed; scope changed to a published self-hosted
  repo.** No code. New [docs/KNOX.md](docs/KNOX.md) records the Knox research:
  the **SDK path is Play-free** (KSP is not, so it is out), **KPE Premium is free
  and customer-generated**, and **`knoxsdk.jar` is `compileOnly`** so no Samsung
  code ships in the APK — meaning a downstream operator needs neither a developer
  account nor the SDK. Three earlier optimistic claims corrected: Knox does **not**
  grant the all-files app-op (`applyRuntimePermissions` dead since Android 12),
  does **not** give built-in VPN profiles (still needs a vendor client app), and
  does **not** set the OS device name (no `setDeviceName`; that is Knox Configure).
  **R3 corrected** — KPE was never gated on a partner agreement; KME still is.
  Chunk 7 planned in detail; new Chunk 11 added for distribution hardening.
- **2026-09-02** — **W24: DPC shows policy names; console inline rename.** 464
  server tests, 52 agent tests, agent v37 (`0.9.7`). The ATLAS MDM app's Policies
  tab now lists the applied policy *names* (carried on the check-in via
  `CheckinResponse.policy_names`) instead of the field contents. Every fleet-table
  row gets an inline rename. **A normally-installed Device Owner cannot write the
  OS "About phone > Device name"** (`setGlobalSetting` whitelist; commercial MDMs
  can't either) — recorded in the Android reference. Logged that day as "deferred
  to Knox"; **corrected the same day — Knox cannot do it either** (no
  `setDeviceName` in the SDK; device naming is Knox Configure). The friendly name
  stays in the console + the app's Device tab.
- **2026-09-02** — **W23: reliable push + a "Check in now" button.** 461 server
  tests. Policy changes already pushed via the long-poll doorbell (F3); W23
  closes the lost-ring gap — `/device/wait` sub-parks in 10 s slices and
  re-reads, so a missed doorbell costs ≤ 10 s instead of the agent's 120 s
  park. New `eff.request_checkin` + `POST /devices/{id}/checkin` (web + API) and
  a per-device button on the device page and the fleet table that rings that
  device's long-poll and reports whether it landed. No FCM (no managed Play; the
  doorbell is ~1 s).
- **2026-09-02** — **W22: quick archive from the policy list.** 457 server tests.
  Each policy row gets an Archive button that opens an impact modal — the
  per-category summary, the devices it is on now, Archive / Cancel. Archiving
  deletes the assignments (not just flags the profile), so the policy genuinely
  leaves the fleet; archived profiles show in the Archived tab and restore
  unassigned. **Hardware-proven on `SM-X520`** — archiving the tablet's PASSWORD
  policy dropped it from the effective policy and the device acked the change.
- **2026-09-02** — **W21: one kind of policy; values-in-fields editor.** 454
  server tests. The console now has a single policy kind — the composite.
  Migration `h8j0l2n4p6r8` converted the 12 standalone policies to one-section
  composites and moved their assignments; the tablet's effective policy came out
  byte-identical. The editor shows **every category** with the current values in
  the form controls (no JSON dump anywhere), saves the whole policy in one
  action, warns on navigating away from unsaved edits, and shows a
  `set_password` in the clear (the mask stays only on the on-device app).
- **2026-09-02** — **W20: PASSWORD policy can set an exact passcode.** 452 server
  tests, 52 agent tests, agent v36 (`0.9.6`). New `PASSWORD.set_password` forces
  a specific screen-lock passcode; the agent applies it via `resetPasswordWithToken`
  (32-byte token in private prefs) and **re-asserts every reconcile** — AOSP has
  no way to stop the user changing it. **Hardware-proven on `SM-X520`:** the
  passcode was set on a fresh device, a user change was reverted on the next
  sync, `errors=0`. The value is masked (`••••••`) everywhere the console and
  DPC display a spec. Android reference §6c documents the token contract.
- **2026-09-02** — **W19b: web console banner logo.** The admin console header
  now uses the supplied `ATLAS.png` lockup (mark + "ATLAS MDM" + tagline) as a
  single `atlas-logo.png` image, with a matching `favicon.png` (the emblem) and a
  near-black brand bar so the logo's own dark ground blends seamlessly. The
  improvised inline mark + text spans and `atlas-mark.svg` are retired. 449 tests
  unchanged.
- **2026-09-02** — **W19: DPC app UI — ATLAS MDM console.** 449 server tests, 52
  agent tests, agent v35 (`0.9.5`). The agent's on-device screen went from a
  monospace dump to a five-section `BottomNavigationView` console (Device /
  Permissions / Apps / Files / Policies) with a manual Sync, branded **ATLAS
  MDM** and styled to the supplied icon (adaptive launcher icon + dark navy
  Material3 theme). New `CheckinResponse.name` plumbs the operator-assigned
  device name to the Device tab. `MarketplaceActivity` folded into the Files
  section. **Hardware-proven on `SM-X520`:** every section renders, the device
  name round-trips after a `PATCH`, `errors=0`.
- **2026-09-02** — **W18: dead spec fields resolved.** 448 server tests, 52 agent
  tests, agent v34 (`0.9.4`). Research corrected the audit: Wi-Fi `auto_join` /
  `mac_randomization` are genuinely `@SystemApi` (removed from the spec + form),
  but the password `min_letters` / `min_digits` / `min_symbols` fields are NOT
  dead — deprecated yet usable by a company-owned Device Owner. The agent's
  password path moved off the complexity buckets onto the granular
  `setPasswordQuality` → `setPasswordMinimum*` family (new pure `PasswordPlan`,
  6 tests: quality is derived as the strictest of the `quality` field, NUMERIC
  for a length floor, COMPLEX for any character-class minimum). Android reference
  §6c gets the family's contract (the `PASSWORD_QUALITY_COMPLEX` precondition,
  the `setRequiredPasswordComplexity` clash). **Hardware-proven on `SM-X520`
  (v34):** `{quality: complex, min_digits: 2}` moved the device to
  `passwordQuality=0x60000` + `minimumPasswordNumeric=2`; reverting dropped it to
  NUMERIC. `errors=0` throughout.
- **2026-09-02** — **W17: R2 (XAPK OBB placement) closed — not feasible, made
  loud.** 448 server tests, 46 agent tests, agent v33 (`0.9.3`). A `probe_obb`
  debug action wrote to `/sdcard/Android/obb/org.takmdm.testapp/` on `SM-X520`
  and got `EACCES` — a normally-installed Device Owner cannot place another app's
  OBB even with all-files access (Knox or root only; same class as VPN).
  `Reconciler.reconcileApps` now raises an apply_error naming the package instead
  of skipping the OBB part silently; the Apps page shows an `OBB` pill on any
  package that carries one. Android reference §6 gets the ❌-verified probe
  output; `DebugConfigReceiver.probe_obb` committed for the R5 re-check on the
  Qualcomm / MediaTek devices. **The policy→agent audit is now fully resolved
  except for dead spec fields (candidates for removal).**
- **2026-09-02** — **W16: agent enforces `allowed_packages`.** 447 server tests,
  46 agent tests, agent v32 (`0.9.2`). The app allowlist now suspends every
  non-system user app not on it (via `setPackagesSuspended`); required apps and
  the agent are implicitly allowed, system apps are out of scope, and an empty
  INTERSECT is reported-and-ignored. New pure `AllowlistPlan` (6 tests).
  **Hardware-proven on `SM-X520`:** an allowlist excluding `org.takmdm.testapp`
  suspended it, left the agent / ATAK / launcher / clouddpc alone, and removing
  the allowlist un-suspended it. Only OBB placement (R2) now remains from the
  policy→agent audit.
- **2026-09-02** — **W15: agent quick wins.** 447 server tests, 40 agent tests,
  agent v30 (`0.9.0`). Three fields the agent had been ignoring now apply, all
  hardware-proven on `SM-X520`: `PASSWORD.history_length` (`setPasswordHistoryLength`
  — checked, not deprecated at 31), `RESTRICTIONS.screen_timeout_seconds`
  (`setSystemSetting(SCREEN_OFF_TIMEOUT)` — one of three DO-writable keys), and
  `required_apps[].auto_update` (new pure `AppUpdatePlan` — false means
  install-once). Still open: `allowed_packages` enforcement, OBB placement (R2),
  and the dead `min_letters`/`min_digits`/`min_symbols` + Wi-Fi
  `auto_join`/`mac_randomization` fields.
- **2026-09-02** — **W14: agent applies Wi-Fi policy; VPN dropped.** 447 server
  tests, 36 agent tests, agent v29 (`0.8.1`). `PolicyApplier.applyNetworks`
  configures Wi-Fi networks from a `NETWORKS` policy via the deprecated-but-
  DO-grandfathered `WifiManager.addNetwork`. **Hardware-proven on `SM-X520`,
  full cycle:** assigning the policy configured the network, unassigning removed
  it, and the device's own Wi-Fi was untouched. `getConfiguredNetworks` returns
  nothing for a DO on One UI 8, so the agent removes by the id `addNetwork`
  handed back (v0.8.0 → v0.8.1 fix). VPN removed from `NETWORKS` entirely.
- **2026-09-02** — **W13: Networks policy type (Wi-Fi + VPN).** 448 tests. New
  `NETWORKS` spec with `wifi_networks` / `vpn_profiles` lists (models with the
  fields from the reference UI, `MERGE_BY_KEY` on ssid / name), `wifi_list` /
  `vpn_list` form controls, and the `networks` category wired. Passwords sit in
  the spec cleartext (DW9 — the device needs them). Agent applier deferred.
- **2026-09-02** — **W12: sub-paged policy categories.** 443 tests. A policy
  category's sub-topics are now separate sub-pages in the left rail (a sub-page =
  a field `ui_group`), each with its own controls, and a green check marks a
  sub-page / category that has data — matching the reference UI. `APP_CATALOG`
  regrouped so every field is its own sub-page. Data model unchanged; all of a
  category's sub-pages share one `<form>` so saving from any of them keeps the
  rest. New `[data-rail]` navigator in `atlas.js`.
- **2026-09-02** — **W11 built then removed.** A `PERIODIC_SYNC` policy type
  (foreground/background dropdown) was added, then reverted the same day: the
  agent always runs a foreground service and "background" was never going to be
  enforced, so the choice was not real. `periodic_sync` is no longer in the
  creator catalog. Back to 439 tests.
- **2026-09-02** — **W10: form-driven policy editing.** 439 tests. Overrides D64
  for the console (DW6): every policy JSON textarea is replaced by a generated
  form of typed controls — a tri-state select per restriction (Not managed /
  Allowed / Blocked, DW7), number spinners with the spec's own min/max, enum
  dropdowns, and repeatable package / app / file rows. `form_schema.py` derives
  it all from the registered spec (Pydantic fields + `Merge` annotation), with a
  plain-English merge hint beside every control so stacking stays legible;
  `form_parse.py` turns the submission back into a managed-fields-only spec dict
  and hands it to the existing validator. Field metadata (`title`, `ui_group`,
  bool wording) lives on the Pydantic `Field` (DW8). Verified live against the
  Docker stack. Migrations unchanged.
- **2026-09-02** — **W9: Guides. Web UI expansion (W1–W9 + W4b) complete.**
  434 tests. Hand-written `markdown_lite.py` (no new dependency), `guides.py`
  reading `app/web/guides/**/*.md`, six how-to articles + two FAQ files + release
  notes, and a `/guides` section with How-to / FAQ / Release notes tabs. Removed
  the W1 placeholder-shell machinery — all eight nav sections are now real pages.
- **2026-09-02** — **W8: Admin.** 429 tests. New `AppSetting` key/value store,
  `CustomAttribute` + `DeviceAttributeValue` (migration `g7i9k1m3o5q7`).
  `settings_store.py` drives form-generated tabs for EULA / SMTP / AD / SMS /
  geofencing (blank secret keeps the stored one; secrets never rendered back —
  plaintext at rest, folded into R8). `custom_attributes.py` + API. `admin.html`
  adds a certificate list with per-cert revoke, an env-settings read-only view,
  and Knox / Android Enterprise placeholders; device pages get a custom-attribute
  editor.
- **2026-09-02** — **W7: Reports.** 423 tests. `app/services/reports.py` — a
  six-report registry (fleet inventory, convergence & compliance, policy
  deployment, command history, app inventory, marketplace selections), each a
  `(session) -> (columns, rows)` function, rendered by one generic template or
  served as CSV via `?format=csv`. No schema change. Physical telemetry is
  explicitly out of scope (agent doesn't report it).
- **2026-09-02** — **W6: Content.** 418 tests. `ManagedFile` gains nullable
  deployment-default fields (migration `f6h8j0l2n4p6`); `content_admin.py` reads
  every FILES policy's entries back so `content.html` shows, per file, which
  policies place it and where. `PATCH /api/v1/files/{id}` for name/description/
  defaults. Console delete refuses (and names the policies) while a file is
  referenced; the API delete stays permissive by design.
- **2026-09-02** — **W5: Apps.** 413 tests. `AppPackage.store_listed` + `AppGroup`
  (migration `e5g7i9k1m3o5`), `app/services/app_groups.py`, `packages.delete_package`,
  `PATCH`/`DELETE /api/v1/packages/{id}`, `/api/v1/app-groups` CRUD. `apps.html`
  with Local apps / ATLAS store / App groups tabs and an upload form. The profile
  editor's App Management section gets an "insert app group into required_apps"
  helper (`atlasInsertAppGroup`).
- **2026-09-02** — **W4b: profile assignment & resolution.** 406 tests. New
  `ProfileAssignment` (migration `d4f6h8j0l2n4`); the resolver expands a profile
  assignment into one input per section at that rank, so a profile stacks against
  standalone policies exactly as its sections would. `invalidate_for_profile` +
  `devices_affected_by_policy` following a section up to its profile keep the F3
  doorbell correct. `PUT /api/v1/profiles/{id}/targets` and a console bulk-assign
  form. Fleet table shows the profile name; the stacking view reads
  `‹profile› · ‹section›` for free from the child naming.
- **2026-09-02** — **W4: composite policies (profiles).** 398 tests. Per DW5 a
  "policy" the operator builds in the creator is a `PolicyProfile` bundling
  single-concern child `Policy` rows (one per category tab) — the resolver, merge
  registry and stacking view are untouched underneath. New `PolicyProfile` +
  `Policy.profile_id`/`profile_section` (migration `c3e5g7i9k1m3`, batch mode for
  SQLite), `app/policies/creator_catalog.py` (16 categories, 4 wired),
  `app/services/profiles.py`, `app/api/routers/profiles.py`, and a guided
  `profile_editor.html` used for both create (`/policies/new`) and edit
  (`/profiles/{id}`). Sections cannot be assigned or listed standalone.
  Assignment + resolution is W4b.
- **2026-09-02** — **W3: Policies list & New Policy modal.** 387 tests. Added
  `Policy.is_template` (migration `b2d4f6a8c1e3`) — a blueprint the resolver and
  fleet table skip and assignment endpoints refuse (409). New
  `app/services/policy_admin.py` (list-by-tab, clone, archive, restore); "save as
  template" and "use template" are the same clone operation, so the two never
  drift. `policies.html` gets three tabs (Device / Templates / Archived) and a
  New Policy modal; the from-scratch form moved to `/policies/new`. API gains
  `/policies/{id}/restore` and `/policies/{id}/clone`.
- **2026-09-02** — **W2: Enroll & Manage.** 381 tests. Added `Device.name` (a
  nullable operator-assigned friendly name; migration `a1c3e5f7b9d2`, `PATCH
  /api/v1/devices/{id}` + a console rename form). New `app/services/fleet.py`
  assembles the Manage table — every device plus the names of the policies
  reaching it — in two queries, without resolving the full stack per device.
  `manage.html` (was `devices.html`) has the operator's columns (name / serial /
  model / OS+agent / policies / convergence / compliance / last check-in) with
  client-side filter and sort. `enroll.html` (was `enrollment.html`) puts the
  Wi-Fi SSID/password/security fields directly on the QR generator so one action
  produces the QR-with-Wi-Fi.
- **2026-09-02** — **W1: ATLAS console shell.** 375 tests. Web UI expansion
  begins (Chunks W1–W9, plan in the chunk section above). Migrated the console's
  single inline `<style>` to `app/web/static/atlas.css` served via `StaticFiles`,
  added a dependency-free `atlas.js` (modal / tabs / table filter / sort /
  confirm), a `_macros.html` library, and rebuilt `base.html` with the ATLAS
  brand bar and the eight-section nav (Enroll, Manage, Policies, Apps, Content,
  Reports, Admin, Guides). The five not-yet-built sections have routes that name
  the chunk delivering them. Every legacy CSS class preserved, so existing pages
  render unchanged; the logo is an `<img>` not inline SVG so `"<svg"` still means
  "a QR rendered" for two enrollment tests. Stayed on Jinja + vanilla JS, no
  build step (DW1).
- **2026-09-02** — **Chunk 14: single persistent enrollment token, 15-minute
  signed QR.** 370 server tests. Replaced the free-for-all multi-token console
  with the operator's model: one standing enrollment credential, retired and
  replaced rather than multiplied, whose raw secret is never displayed. Every
  "Generate QR" click instead mints a stateless, HMAC-signed 15-minute derivative
  — `{primary_id}.{nonce}.{issued}.{signature}`, mirroring the existing
  `CsrfGuard` pattern rather than inventing a new one — so a leaked QR image is
  bounded by 15 minutes regardless of the primary's own lifetime. No database row
  is created per QR generation. Verified live through real nginx: two devices
  enrolled from one QR within its window (unlimited use, by design), and —  the
  property the whole design rests on — retiring the primary refused a still
  time-valid QR immediately, because verification re-checks the primary's
  `is_usable()` on every use rather than at mint time, so no cascade-revoke logic
  exists or was needed. "At most one live primary" is a database guarantee (a
  partial unique index on `is_primary WHERE revoked_at IS NULL`), not an
  application-level hope. Every existing ad-hoc token, script and test keeps
  working unchanged: a QR-shaped secret is tried first and falls through to the
  original hash lookup on any shape or signature mismatch.
- **2026-09-01** — **UI/UX Pro Max skill installed** (out of band, at user
  request; not a project chunk). Vendored `github.com/nextlevelbuilder/ui-ux-pro-max-skill`
  into `.claude/skills/` by replicating what `uipro init --ai claude` does (npm
  global install was blocked): rendered `SKILL.md` from the CLI's base template
  with the local script path, and copied the `data/`, `scripts/`, and the six
  sibling skills (banner-design, brand, design, design-system, slides,
  ui-styling). `.claude/skills/` is gitignored — per-developer tooling, not
  project source. Search tool verified with `python` (Windows has no `python3`).
  Bundled tests: `git clone` ran with `core.autocrlf=true`, so every data file
  was checked out CRLF and the SHA-256 snapshot digests in `catalog-summary.json`
  (computed on LF upstream) no longer matched — renormalized all 171 text files
  to LF. Deleted two orphaned maintainer test modules (`test_catalog_refresh`,
  `test_relevance_evaluator`) that import upstream-only `scripts/*.py` never
  shipped in the package. `python -m unittest discover` on ui-ux-pro-max now
  passes 130/130. Sub-skill suites (brand, design-system, ui-styling) are
  pytest-based and need `pip install pytest` to run; not run here.
- **2026-09-01** — **Chunk 13: CSRF protection. R11 closed.** 310 tests. Tokens
  signed over the administrator's identity on the console's forms, plus origin
  validation on every unsafe admin request — which is what covers the admin API's
  bodyless endpoints, since a cross-site form *can* reach
  `POST /devices/{id}/retire`. JSON requests are deliberately exempt from the token
  so scripts keep working; a form cannot send JSON and a cross-origin `fetch` that
  does is stopped by a CORS preflight. Verified live in `forward_auth` mode, which
  immediately caught what the unit tests could not: `docker-compose.yml` enumerates
  env vars, so `TAKMDM_CONSOLE_ORIGIN` never reached the container and the origin
  check silently did nothing. The nginx trap in a new costume. The startup warning
  added an hour earlier named the fault on the deploy that had it.
- **2026-09-01** — **Housekeeping: device deletion.** 291 tests. There was no way
  to remove a device record anywhere, and retirement — which did exist — was never
  exposed in the console. Added retire-then-delete: deletion is refused with 409
  unless the device is already retired, so removing a working tablet takes two
  deliberate acts and the certificates are always dead before the row is. Cleared
  the two stale records the housekeeping note had been carrying, and verified zero
  orphans across all six tables referencing `device`.
- **2026-09-01** — **Chunk 11 complete, hardware-validated. R13 closed.**
  282 tests. A device now enrols with a *set* of identifiers and the server matches
  on any it already knows, so a device that changes identity source re-adopts its
  own record instead of forking a new one and losing its policy stack. Matching is
  by kind priority rather than list order; an ambiguous match is reported and never
  merged automatically; an identifier held by another device is never reassigned.
  The migration backfills every existing serial as a `LEGACY` identifier —
  verified against real Postgres — which is what preserves current matching and
  avoids orphaning the whole fleet on its next re-enrolment. **Proven on the
  tablet:** with its identity fully cleared it re-enrolled into the *same* record
  `dd814571…`, promoted its display serial from the `ANDROID_ID` fallback to
  `R5GL40MMHRN`, and kept `PASSWORD.min_length 13` — where the same sequence would
  previously have produced an empty new record with no policies, which is how a
  wiped tablet came back silently unmanaged.
- **2026-09-01** — **Chunk 10 complete, hardware-validated.** `adb` recovered by
  pairing over wireless debugging; agent v10 (`0.3.1`) installed on `SM-X520`.
  `lock`, `locate` and `collect_logs` all succeeded at `attempts=1/5`, against the
  same `collect_logs` that had expired at 5/5 on the old build half an hour
  earlier — 7.3 s from queue to settled. The hardware test immediately exposed
  something the suite could not: the first collected bundle held **two lines**,
  because 49 of the agent's 61 log calls still went straight to `android.util.Log`
  and never reached the collectable log — `AppInstaller` among them, which is
  precisely what Chunk 11 needs to debug. Migrated all of them. Also found the
  tablet was on v7 not v8, and that its enrolment used the `ANDROID_ID` fallback
  rather than its real serial `R5GL40MMHRN`, which weakens D24's re-enrolment
  guarantee and may explain the stale duplicate record.
- **2026-09-01** — **Chunk 10 steps 1–6.** Agent command layer and remote
  diagnostics. 271 server tests + 30 agent tests. Found by inspection that the
  agent **never read the `commands` array at all** — the server dispatched, counted
  an attempt, and the device dropped it, so a remote wipe promised something it
  could not do. Confirmed on the live tablet before fixing: a queued `COLLECT_LOGS`
  went to `EXPIRED — exceeded max attempts` while the device was online and
  answering the doorbell in the same second. Built the dispatcher as a type-keyed
  registry (D88), unknown types now report as unsupported rather than vanishing
  (D89), and `reboot`/`wipe` defer their effect until the result is delivered (D90).
  Log collection deliberately does **not** scrape `logcat`: `READ_LOGS` is
  unavailable to a normally-installed app, self-reading is unconfirmed by any
  official source, and Android recommends keeping your own logs instead (D87).
  Two corrections caught by checking sources rather than reasoning: `wipeDevice` is
  **API 37** and would not have compiled against `compileSdk 36`, and the SQLite
  test engine was ignoring every foreign key in the schema (D93). Also fixed
  `AGENT_VERSION`, hardcoded at `0.1.0` while the build was `0.2.4` (D92).
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
- **2026-09-01** — **First hardware enrolment.** `SM-X520` enrolled over mTLS,
  checks in, applies policy, and is woken by the long-poll in the same second as a
  policy publish. Six bugs found that the 254-test suite could not see; three of
  them shared one shape — an over-specific constraint that looked careful and
  guaranteed failure. The turning point was making the agent report its own errors
  on its own screen (D79). Chunks 6–9 complete; agent v8.
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
