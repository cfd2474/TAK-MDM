# Project State

Running state file per [CLAUDE.md](CLAUDE.md). Read before starting any step;
update after every completed step.

**Last updated:** 2026-09-06

---

## Current status

**Latest (2026-09-09).** W94–W108 complete and deployed. Location tracking,
geofencing, the map and history page, retention, find-my-device, remote lock, and
battery/IMEI/phone on the device page. Agent **0.50.0 (versionCode 95)** published
fleet-wide; `SM-X520` is on it and reporting. **1273 server tests, 38 agent JVM
tests.** Alembic head `h4j6l8n0p2r4`.

**What is actually waiting** — nothing is blocked on code:

| | |
|---|---|
| Handtevy `4001269` from Play | Would be the first import exercising **signature continuity** against a package already in the library (`4001247`). |
| Disenroll (W104) | Never run on hardware. Suggest `SM-X828U` — not `SM-X520`, which carries the kiosk profile. |
| Geofence `wifi: off` and `password_enforced` | Deliberately not hardware-tested. See W106 C4 for why Wi-Fi off is a one-way door on a Wi-Fi-only tablet. |

⚠️ **The migration did not run automatically on the W108 deploy.** `alembic
upgrade head` had to be run by hand after `docker compose up -d --build api`.
Worth watching whether that recurs — a schema change that silently does not apply
is the kind of thing that surfaces later as an unrelated-looking bug.

---

**Phase:** ✅ **Chunks 10–14 complete.** F1–F6 all hardware-proven; R1, R11, R13
closed. **Enrollment is now a single persistent token with 15-minute signed QR
derivatives** (Chunk 14), verified live through real nginx — including that
retiring the primary kills an already-issued, still-time-valid QR immediately.
Agent **v41 (`0.10.1`)** running on `SM-X520` (compliant, serial `R5GL40MMHRN`),
delivered over the air by the agent-update channel — the first build on this
device that no one sideloaded.
**No hardware verification is outstanding.** W90's ATAK Config was proven on `SM-X520` on 2026-09-07 — ATAK itself shows a setting only the pushed document could have set, applied without an ATAK restart and without an agent release (R16 closed). W17, W23 and W24 cleared 2026-09-02 (W25).
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
1034 server tests + 206 agent tests.

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

### ⚠️ The local stack is not the one devices check into (2026-09-07)

**Two ATLAS servers exist and it is easy to diagnose the wrong one.**

| | |
|---|---|
| **The real deployment** — where `SM-X520` checks in | `209.182.235.108:8443`, cert `CN=209.182.235.108` |
| **The local dev stack** — `docker compose` on this machine | `127.0.0.1:8000` console, cert `CN=192.168.68.89` |

⚠️ **The local database is therefore not the fleet's.** Reading
`http://127.0.0.1:8000/api/v1/devices` shows `SM-X520` with a `last_checkin_at`
of 2026-09-04 and looks exactly like a device that has stopped reporting. It has
not: it reports to the remote host, and this row simply has not moved since the
last time it talked to *this* machine. **A stale `last_checkin_at` here is not
evidence of anything.** Check the remote server before concluding a device is
dark.

⚠️ **This machine's local `.env` is stale in two ways**, which matters only if
someone enrols a device against the dev stack:

* `TAKMDM_SERVER_URL=https://192.168.68.89:8443`, but this machine's Ethernet
  address is now **`192.168.68.104`** — the DHCP lease moved.
* `192.168.68.89` is now **a Google Chromecast**
  (`O=Google Inc, OU=Cast, CN=AP3YREI FA8FCA710CC2`). It answers on 8443, so the
  address is not merely dead — something replies with a certificate that is not
  ours, which fails differently and later than a refused connection.

The local server certificate still carries `CN=192.168.68.89` / SAN
`IP:192.168.68.89` only, so the dev stack cannot serve a device at its own
current address either. Both would need answering together before enrolling
anything locally — see W35 for what that involves.

**Identify which server you are looking at in one command:**

```
openssl s_client -connect <host>:8443 </dev/null 2>/dev/null \
  | openssl x509 -noout -subject
```

`CN=209.182.235.108` is the real deployment; `CN=192.168.68.89` is this laptop's
dev stack; anything else has taken the address.

### ⚠️ Provisioning fails opaquely when `.env` describes another deployment (W76)

`SM-X828U` reached *"Something went wrong"* after downloading the DPC. Nothing
about it appeared in this server's logs, because the QR did not point at this
server. `/opt/atlas/.env` held a different deployment's values:

| Setting | Was | Should be |
|---|---|---|
| `TAKMDM_SERVER_URL` | `https://192.168.68.89:8443` | `https://209.182.235.108:8443` |
| `TAKMDM_AGENT_APK_URL` | `http://192.168.68.89:8080/…` | `http://209.182.235.108/…` |
| `TAKMDM_AGENT_SIGNATURE_CHECKSUM` | `h5QFWJTb…` | `IJS8zAVMaB…` |

⚠️ **The checksum alone is fatal.** Android verifies the downloaded APK's signing
certificate against it and aborts on a mismatch — and `h5QF…` is a different
signing key from the one every agent build here uses. There is no message beyond
"Something went wrong", and the device asks for a factory reset.

⚠️ **Three independent faults, any one of them fatal**, which is why the symptom
is worthless as a diagnostic: wrong download host, wrong signing key, and a
`server_ca_pem` (this server's cert, valid only for `209.182.235.108`) that could
never have matched an enrolment at `192.168.68.89`.

✅ **Check it with `verify_qr`, not by provisioning a tablet.** The payload can be
checked against the APK the URL actually serves and the cert the agent is handed,
in seconds, on the server. Burning a factory reset to learn "something went
wrong" is the expensive way to find a typo.

⚠️ `docker compose up -d` **recreates the container and wipes its `/tmp`.** Scripts
copied in with `docker compose cp` disappear; a watch loop left polling one of
them reports nothing and looks like a device that stopped checking in.

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

### ✅ W115 — Provisioning let the operator past ungranted permissions (2026-09-09, `eb34e9e`)

Operator, after re-enrolling both devices: *"it allowed me to proceed with device
provisioning without accepting all permissions. the proceed button should be
blocked until all permissions have been granted"*.

The button was labelled **"Continue without the rest"** — skipping was designed
in, not a bug. But `PolicyComplianceActivity`'s own docstring says why that is
wrong: *"This is the one moment the operator is already holding the device …
Everything requiring a human tap is collected here, so a deployed tablet never
later turns out to be silently missing a capability."* Skipping defeats the
entire purpose of the screen.

#### Blocked on the *required* set, not on everything

`PermissionRequirement` already draws that line and the reasons hold:

| Required — blocks | Optional — does not block |
|---|---|
| File access, Display over other apps, Unrestricted battery, Location | Background location, Notifications, ATLAS power menu |

The power menu is optional *by design* on a device that will not be locked down,
and blocking setup over it would strand provisioning for something nobody needs.

#### ⚠️ The override stays, and deliberately contradicts the literal ask

The operator asked for the button to be blocked until **all** permissions are
granted. It is blocked, but there is still a way through, because
`finishProvisioning`'s existing warning is load-bearing: **provisioning cannot be
repeated without another factory reset.** A required permission that cannot be
granted on some future OEM — a Settings screen that does not exist, an intent
resolving to nothing — would otherwise trap the operator on a dead button with a
factory reset as the only escape. That trade is worse than the one being fixed.

So: a plain secondary button, hidden unless something required is missing, behind
a dialog naming what will break, logging the decision. **Say the word and the
override comes out** — it is a deliberate deviation, not an oversight.

#### State

Agent **0.56.0 (versionCode 101)** published; fleet pointer → 101.

⚠️ **Only reachable during provisioning**, so upgrading does not exercise it and
does not retroactively fix an already-enrolled device. Verifying needs a factory
reset and a fresh enrol.

✅ **Fleet is clean and needed no cleanup**: three devices, distinct serials, all
`COMPLIANT` with no warnings — so whatever was skipped has since been granted.
`R5GL40MMHRN` (SM-X520) re-attached to its **existing** record after the W114
wipe rather than creating a duplicate, which answers the open question from that
entry: D24 identity matching works, and there is no orphan row to remove.

### ✅ W114 — W104 disenroll never worked (2026-09-09, commit `9c6b2d1`)

Operator: *"the disenrolled device did not factory reset. it now just says sync
failed, certificate is not known"*.

**Diagnosed from the proxy log, not assumed** — the API container's logs had been
destroyed by my own W113 deploy an hour earlier, so the evidence came from the
proxy, which survived:

| 02:40:42 | `wait?state_version=20` → 200 | state changed |
| 02:40:42 | `checkin` → 200 (501 b) | wipe command delivered |
| 02:40:43 | `checkin` → 200 (293 b) | **the agent acknowledged** |
| 02:40:43 → | everything → **401** | certificate revoked, record removed |

So the server did its half exactly as designed. The agent acked and then failed
to wipe.

**Root cause**: `wipeData(int, CharSequence)` throws `IllegalStateException` for
an app targeting `UPSIDE_DOWN_CAKE`+ calling from the primary user, and names
`wipeDevice` as the replacement. We are a Device Owner on the primary user at
`targetSdk 36` — so this was **every wipe on every device**. W104 had never once
worked; it had simply never been run on hardware until tonight.

The comment being replaced asserted `wipeDevice` was **API 37** and unavailable
against `compileSdk 36`, and kept the throwing call on that basis. `javap`
against the installed stubs says it is present in android-34, -35 and -36. Full
contract in `ANDROID_PLATFORM_REFERENCE.md`, including that the two halves key
off *different* SDK levels — `wipeData`'s throw off **our `targetSdk`**,
`wipeDevice`'s existence off **the device's API**.

Fixed in agent **0.55.0 (versionCode 100)**, published; fleet pointer → 100.

✅ **Verified on `SM-X520`, 2026-09-09.** Tested with a *plain* wipe rather than a
disenroll: identical params (`wipe_external_storage: True`), so the same
`WipeCommandHandler` and the same `wipeDevice` call, but with no `disenroll`
marker — `disenroll.acknowledged()` therefore did not match, `complete()` was
never reached, and the record and certificate survived. The point being that a
second failure would have been *reportable* instead of orphaning the tablet
again.

Command acknowledged `SUCCEEDED` on attempt 1; the tablet factory reset,
confirmed by the operator at the device and corroborated by check-ins stopping
dead (113 → 233 s since contact, from a device polling every ~60 s).

⚠️ **The full disenroll flow has still not been run end to end.** Both halves are
proven separately — the server's ack → revoke → remove worked correctly on
2026-09-09 even while the wipe was failing, and the wipe works now — but not
together.

#### ⚠️ Open risk: a deferred effect cannot report its own failure

This is the part worth more than the one-line fix. The throw landed in
`runCatching` inside a **deferred** effect, which by design runs only *after* the
acknowledgement reaches the server — and the server revokes the certificate on
that acknowledgement. The single component that knew the wipe had failed had, by
that moment, permanently lost the ability to say so.

The W104 docstring anticipated the state (*"recoverable only by a manual factory
reset at the device"*) but treated it as a rare hardware failure rather than the
guaranteed outcome it was.

**A deferred effect whose failure is unreportable needs its precondition checked
*before* the acknowledgement, not after.** Left as a design question for the
operator rather than redesigned unilaterally.

#### The orphaned tablet

Device Owner still installed, certificate revoked, `deps.py` answering
*"certificate is not known"*. Two ways back:

* **Manual factory reset at the device** — Settings → General management →
  Reset, or recovery mode (Vol Up + Power). ⚠️ Factory Reset Protection may then
  demand the Google account that was previously signed in. Certain, and wipes.
* **Re-admit its certificate** — nginx already accepts the cert at the TLS layer
  (signed by our CA, unexpired); only the `device_certificate` serial lookup
  rejects it. Re-creating the `Device` + `DeviceCertificate` rows would bring the
  tablet back with no data loss. Needs the serial, capturable by adding
  `$ssl_client_serial` to the nginx log format. ⚠️ Deliberately re-admitting a
  revoked certificate is a security-relevant live mutation — operator's call, not
  taken unilaterally.

**Verifying the fix does not depend on recovering that tablet**: any device on
0.55.0 can be disenrolled to prove it, which is worth doing on a tablet that is
due a reset anyway.

### ✅ W134 — The device name on the lock screen, via a token

Operator, 2026-09-11: *"lets find a way to add the device name as a lock screen
message"* — recovering the surface W133 gave up.

#### ⚠️ There is exactly one lock-screen slot, and it was already taken

`setDeviceOwnerLockScreenInfo` is the only way to put text there, and
CUSTOMIZATIONS' **`lock_screen_message` already owns it**. A separate "show the
device name on the lock screen" switch would have been two features writing to
one field: whichever applied last would win, and neither would say so.

So it is a **token inside the existing field**. Write `{device}` anywhere in the
message and each device substitutes its own name — or its serial if unnamed,
the same fallback the on-screen label uses. One policy labels a whole fleet,
and the operator writes the line rather than accepting ours.

The same token works in the two support messages, because special-casing one
field would be the surprise.

#### ⚠️ Substituted on the device, not on the server

Renaming a device **does not invalidate its cached effective policy** —
`rename_device_form` just sets the name and commits. A name baked in
server-side would therefore stay stale until something unrelated happened to
change the policy. The agent is told its name on every check-in. There is a
test that fails if `{device}` ever appears under `app/services`.

#### ⚠️ An unresolved token is left visible rather than blanked

Substituting an empty string would turn *"Property of {device}"* into
*"Property of "*, which reads as a bug on a device nobody has named yet. The
token stays, and says what it is.

The blank rule still governs: an operator who empties the box gets the field
cleared, not a lock screen reading `{device}`.

#### Tested where it can actually run

Five new cases in `CustomizationsPlanTest` — **10 tests, 0 failures** in
`testReleaseUnitTest`. `CustomizationsPlan.message` is pure, so these execute
the substitution rather than grepping for it, which is the difference that
caught the literal-dollar bug in W131 only after hardware did.

Suite **1446 passed, 1 skipped**. Agent **0.67.0 (versionCode 112)**.

### ✅ W133 — Drop the drawn label, keep the widget

Operator, 2026-09-11: *"that worked, now remove the wallpaper version, keeping
the widget version."*

`DeviceIdLabel.kt` is gone, along with the composition step, the temp PNG and
the label's place in the wallpaper's identity key.

#### The two features stop being tangled

While the name was *drawn into* the bitmap, the label had to reach into the
wallpaper logic in three places: `shouldClear` had to treat a label-only policy
as "names an image" or it would wipe the screen instead of labelling it; the
identity key had to carry the device name or a rename redrew nothing; and the
composition had to run between download and apply. All three are now gone —
they exist only because one feature was implemented inside another.

⚠️ **One test is inverted on purpose.** `test_the_label_alone_does_not_clear_the_wallpaper`
asserted the opposite of what is now correct. A policy naming no image *should*
restore the default wallpaper; the label is a window and shows regardless.

#### ⚠️ The lock screen is given up, knowingly

`TYPE_APPLICATION_OVERLAY` sits below the keyguard, so **a locked tablet now
shows no label at all**. That was the drawn version's only remaining
justification, and the operator weighed it against a label the system kept
moving. The policy help says so plainly, since it is the one limit an operator
cannot discover by looking at an unlocked device.

#### Devices clean themselves up

A device still carrying a labelled bitmap has an identity key that cannot match
the plain sha, so it redraws the clean image once. A label-only policy now
trips `shouldClear` and restores the default wallpaper. Neither needed a
migration.

Suite **1443 passed, 1 skipped**. Agent **0.66.0 (versionCode 111)**.

### ✅ W132 — The label becomes an overlay, like the clock

Operator, 2026-09-11, after two attempts at wallpaper geometry: *"a bit better,
but its always centered initally, then shifted with the rotation. What about
the idea of making it like a widget, similar to the clock?"*

#### ⚠️ The wallpaper was the wrong surface, and no amount of geometry fixes it

Two rounds of this have now failed, and the reason is structural rather than
arithmetic. **The system owns the wallpaper's placement** — it decides the crop,
the pan and the parallax, per orientation, per launcher, and OEM shells vary it
further. The agent supplies pixels and has no say in where they land. W131's
square canvas made the two orientations *consistent* with each other, which is
why it got "a bit better", but consistent is not *placed*.

The clock does not have this problem because it is **not painted into the
wallpaper** — it is a view the window manager lays out, and re-lays out on
every rotation. The operator's instinct is right.

#### ✅ The agent already does exactly this, twice

`NightOverlay` and `AlertOverlay` are `TYPE_APPLICATION_OVERLAY` windows with
`FLAG_NOT_TOUCHABLE or FLAG_NOT_FOCUSABLE`, driven from `PolicyApplier` by
`set(...)` / `remove(...)`. **"Display over other apps" is already a *required*
permission in the provisioning wizard**, so every provisioned device has the
capability granted. This is not new ground.

A window is laid out by the platform, so it reflows on rotation with no
geometry of ours involved at all. That is the whole fix.

#### ⚠️ It cannot appear on the lock screen, and that is not solvable here

`TYPE_APPLICATION_OVERLAY` sits **below the keyguard**. Showing above it needs a
system-signature window type the agent cannot have. So:

| Surface | Overlay | Wallpaper label |
|---|---|---|
| Home screen, and over apps | ✅ placed exactly | ⚠️ wherever the system puts it |
| Lock screen | ❌ never | ✅ |

**So the wallpaper label stays**, as the only thing that identifies a locked
tablet, and the overlay handles everything else. One policy flag drives both —
the label appears wherever it can, drawn by whichever mechanism can reach that
surface.

#### ⚠️ Never takes a touch

Copied from `NightOverlay`'s warning, because the failure is the same and
worse: an overlay that swallowed input would be a bricked tablet recoverable
only by removing the policy.

#### Chunk 1

1. `DeviceIdOverlay` — a small non-touchable window, top-centre, mirroring
   `NightOverlay`'s lifecycle and its permission check.
2. Driven from the wallpaper reconcile alongside the existing drawing: shown
   when the policy asks for the label, removed when it stops.
3. Re-asserted each reconcile so it survives a process restart, and updated in
   place on a rename rather than removed and re-added.
4. Tests for the contract: non-touchable, permission-checked, removed when the
   policy drops it.
5. Build, publish, verify on hardware — rotation is the whole point and no test
   can judge it.

#### ✅ Done (2026-09-11) — agent 0.65.0 (versionCode 110)

Suite **1452 passed, 1 skipped**. `DeviceIdOverlay` is a `WRAP_CONTENT`
`TYPE_APPLICATION_OVERLAY` window, positioned by **gravity rather than
coordinates** — a pixel offset would drift exactly as the wallpaper did — and
re-laid out by the platform on every rotation.

⚠️ **Driven above the wallpaper's idempotence check.** That check exists to skip
rewriting an unchanged bitmap, and a window has nothing to do with it. Placed
after it, a device whose wallpaper had not changed would have had no label at
all once its process restarted. There is a test pinning the ordering, because
it is the kind of thing a later tidy-up moves.

The drawn wallpaper label is **kept**: the overlay sits below the keyguard, so
it is the only thing that can identify a locked tablet. Deleting it as
redundant would have quietly lost the lock screen.

### ✅ W131 — The label survives rotation

Operator, 2026-09-11: *"when I rotate the screen, it is no longer in position…
applied in landscape, rotating to portrait puts it significantly to the left,
mostly cut off. Applied in portrait, rotating removes it from the screen
altogether."*

#### My geometry was wrong in two ways

**One bitmap serves both orientations** — the system re-crops it — and I drew
onto a canvas the size of the *current* display. Anything not at the centre
moves or leaves the screen when the device turns.

📖 `WallpaperManager.getDesiredMinimumWidth`: callers *"should check this value
beforehand to make sure the supplied wallpaper respects the desired minimum
width"*. It is routinely **wider than the display** so a launcher can pan, and
I ignored it — a bitmap narrower than the minimum is *positioned* rather than
centred, which is exactly the sideways shift.

Now: a **square** canvas whose side satisfies every stated minimum. A square is
symmetric, so whatever the system does to it, it does the same in both
orientations. The label sits inside the central `min(W,H)/max(W,H)` band — the
only region guaranteed on screen either way, which is why it is nearer the
middle than reads ideally.

#### ⚠️ A generator wrote Kotlin's literal-dollar escape into the source

`"${'$'}{context…}"` is Kotlin for the *literal text* `${context…}`, not the
value. So the identity string was a constant, and `label:${'$'}it` was the
literal `$it` — **the name never entered the key at all**, meaning the
rename-redraw claimed in W129 never worked.

⚠️ **A test asserted `'label?.let { "label:'` and passed against that.** Source-text
assertions cannot tell a template from a constant. There is now a test that
fails on any literal-dollar escape in the file, which is the property that was
actually broken.

#### Existing devices are forced to redraw

The key carries `v2:`. A device already labelled with the old geometry matches
on image, name and screen, so without it the reconcile would decide there was
nothing to do and leave the broken placement on screen for ever.

Suite **1445 passed, 1 skipped**. Agent **0.64.0 (versionCode 109)**.

⚠️ Still unverified on hardware, and rotation is precisely what a test cannot
judge — the whole point of this round.

### ✅ W129 — Device ID label on the wallpaper

Operator, 2026-09-11: *"can we add 'Device ID Label' that when selected, would
overlay the Device Name/friendly name from the web portal onto the wallpaper?
Even if a custom wallpaper isn't selected. This could be a scalable widget, but
it needs to be large enough to serve as a clear device identifier."*

#### ✅ The foundation is already there

The agent receives the operator-assigned name on **every check-in**
(`Reconciler.kt:403`, stored as `config.deviceName`), so a rename in the portal
already reaches the device. Nothing new is needed to know what to draw.

#### ⚠️ Drawn on the device, not on the server

The obvious implementation — composite the text server-side and ship the
result — quietly destroys the wallpaper's sharing. Images live in a
**content-addressed** store: one file, one sha, fetched by every device that
needs it. A name burned in per device turns that into **one artifact per
device**, each downloaded separately.

The agent has the name, knows its own screen, and already downloads the image.
It composes locally.

#### ⚠️ Never compose from the wallpaper currently on screen

Reading the live wallpaper and drawing on it would stack a label every
reconcile, each pass drawing over the last. The base is always either the
**policy image** or a **generated background** — never what is already set.

#### ⚠️ The idempotence key has to include the name

`reconcileWallpaper` skips the write when `config.appliedWallpaperSha == sha`,
because re-setting a wallpaper flickers. With a label the applied identity is
*(image sha, label text, screen size)* — keyed on the sha alone, **a rename
would never reach the screen**.

#### ⚠️ The spec currently refuses a policy with no image

`_at_least_one_image` rejects an empty wallpaper policy, on the good reasoning
that it would be inert. A label-only policy is *not* inert, so the rule becomes
"at least one image **or** the label", and the message has to say so.

#### On "scalable widget"

Taken as **text scaled to the screen**, not an Android `AppWidget`. A real
widget is placed by the user, can be dragged off, and needs launcher support —
it would not be a dependable identifier. A wallpaper overlay appears on every
launcher and cannot be removed without changing the policy. Say the word if an
actual widget is wanted; it is a different build.

#### Chunk 1 — server

1. `device_id_label` on `WallpaperSpec`; relax `_at_least_one_image`.
2. `resolve_wallpaper` carries the flag even when no slot is filled.
3. Console copy that says what it draws and that it needs no image.
4. Tests: a label-only policy validates and reaches the device; an empty one is
   still refused; the flag survives with and without images.

#### Chunk 2 — agent

5. Compose: policy image or generated background, label sized to the screen,
   legible over any image.
6. Idempotence keyed on image + name + screen; a rename re-renders.
7. Build, publish, verify on hardware.

#### ✅ Both chunks done (2026-09-11) — agent 0.62.0

Suite **1438 passed, 1 skipped**.

`DeviceIdLabel.render` composes onto the policy image, or onto a generated
background sized to the display when the policy names none. Text is a fraction
of the shorter edge (a fixed point size is legible on a phone at arm's length
and useless on a tablet across a room), on a translucent plate because the
image underneath is an operator's photograph and may be white, busy or both.

⚠️ **A long name shrinks rather than truncating.** *"Field Tab…"* is a worse
identifier than smaller text that reads in full, and telling two tablets apart
is the entire point.

⚠️ **An unnamed device falls back to its serial** (operator, W130). The first
version reported an error, on the reasoning that "unnamed" on every tablet is
worse than nothing. The operator's correction is the better call and the
reasoning was simply misapplied: **a serial is not a placeholder.** It is
unique, so it does the exact job the label exists for — telling two tablets
apart. Only a value identical on every device would have been worth refusing.

⚠️ That identity is **cached in `AgentConfig.deviceSerial`**. `serialNumber()`
logs a warning every time it takes the ANDROID_ID fallback, and the label asks
for an identity on every reconcile — uncached, the log fills with the same line
on any device lacking `READ_PHONE_STATE`.

⚠️ Not yet verified on hardware — the bitmap work is the part a test cannot
judge. Worth a look at legibility and placement on the SM-X520 before trusting
it across a fleet.

### ✅ W128 — Download a stored build from the console

Operator, 2026-09-11: *"In the local apps section, give me a download button
next to each app that would allow me to download the apk/xapk from the
browser."*

`GET /apps/versions/{id}/download`, admin-authenticated, with a button on every
app row (its latest build) and on every row of the versions drill-down.

#### ⚠️ A version is not always one file

A split app is several — Chrome arrives from Play as four. Serving only the base
would hand back something Android refuses as `INSTALL_FAILED_MISSING_SPLIT`
while looking like a perfectly good download. So one part is served as the APK
it is, and several are zipped into the **`.xapk` shape `inspect_bundle` already
reads on the way in** — what comes out can go back in.

#### ⚠️ The bug the round-trip test caught and the other test did not

The first version streamed the zip out of a `BytesIO` that was truncated
between parts, to avoid holding hundreds of megabytes in memory. But `zipfile`
records member offsets from `fp.tell()`, so resetting the buffer made **every
offset in the central directory wrong**. The archive still listed its names —
`test_a_split_build_comes_back_whole` passed — and only failed when something
tried to *read* a member back out.

Assembled on a temp file now, streamed in 1 MB chunks, unlinked after. Memory
stays bounded and the offsets are real.

**`namelist()` is not proof an archive works.** The test that mattered was the
one that fed the download back into `ingest`.

#### A test expectation of mine that was simply wrong

Re-ingesting is *refused* — "already uploaded; bump versionCode" — and I had
asserted it would succeed. The refusal is the stronger proof: ingest can only
name the package and versionCode by opening the archive and reading the
manifest out of the base APK inside it.

Suite **1426 passed, 1 skipped**. No agent change.

### ✅ W127 — Real download progress, and drop the held pill

Operator, 2026-09-11: *"can we query the download size so we get an accurate
download status? it currently stays blank. also, get rid of the bubble (held —
publish to deploy)."*

#### Why it is blank: nothing reports progress at all

`_run_repo` sets `total=version.size or 0` and then calls
`repo_import.import_version`, which calls `source.download(version)` — a single
blocking call that returns the finished bytes. **`downloaded` is never updated
until the job ends**, when it is set to `total` in one jump. No source streams:
F-Droid does `response.content`, Play shells out to `apkeep`.

So the bar has never moved for any repo import. Play is simply the case where it
is most obvious, because Play states no size either, leaving `total=0` and the
text at *"downloading…"*.

#### ⚠️ Play can report bytes, but not a percentage — and that is the honest answer

Play downloads run through `apkeep`, which writes into a temp directory and
prints nothing this code can rely on. There is no HTTP response to read a
`Content-Length` from. **Watching the temp directory gives real bytes
downloaded; the total remains genuinely unknown.**

So Play gets *"12.7 MB so far"* rather than a percentage — which is exactly what
the tak.gov importer already does when a server omits `Content-Length`
(*"Downloading — size unknown"*). Inventing a denominator to make the bar move
would be a worse answer than no bar.

HTTP sources do better: streaming gives a real percentage, and
`Content-Length` supplies a total even when the catalogue omitted the size.

#### ⚠️ The held pill: the stated reason is not quite right

*"we dont execute that behavior on any other app download"* — we do.
`repo_import` never publishes **any** import: F-Droid, APKPure, third-party
repos and tak.gov plugins are all held exactly like Play. The pill only ever
appeared when a package had nothing published, which until now meant a
freshly imported one.

Removing the bubble is still the operator's call and it goes. But the column is
headed *latest version* and means **the build devices are offered**, so a held
build rendered identically to a published one would misreport what the fleet
gets. It keeps a plain muted *held* after the version — no badge, no colour.

**If the real intent is for imports to publish automatically, that is a
different change** and worth saying out loud rather than approximating: it
would aim every device asking for "latest" at whatever was just downloaded.

#### Chunk 1

1. Optional `progress(downloaded, total)` on the `AppSource.download` contract,
   defaulting to nothing so a source that cannot report stays valid.
2. F-Droid and APKPure stream, reporting bytes and adopting `Content-Length` as
   the total when the catalogue gave none.
3. Play watches its temp directory and reports bytes with no total.
4. `import_version` and `_run_repo` thread the callback into the job.
5. Console: show *"N MB so far"* when the total is unknown, mirroring the plugin
   importer, instead of a bare "downloading…".
6. Drop the pill; keep a muted *held*.

#### ✅ Done (2026-09-11)

Suite **1420 passed, 1 skipped**.

`AppSource.download` now takes an optional `progress(downloaded, total)`.
F-Droid streams and adopts `Content-Length` as a total the catalogue may not
have stated; the two apkeep sources (Play, APKPure) run a watcher thread over
their temp directory and report bytes with **no** total, because there is no
stream to count and nothing dependable on apkeep's stdout.

⚠️ **A zero total never overwrites a known one.** The catalogue can state a
size the download cannot confirm mid-stream, and letting apkeep's 0 land would
turn a working percentage into a byte counter halfway through.

The console now shows `12.7 MB so far — size unknown` where it used to freeze
on "downloading…", and the bar simply does not move for a source that cannot
state a size — an honest answer rather than a fabricated denominator.

⚠️ **Two of my own test mistakes, both the same shape as before.** One asserted
`"downloading…"` was absent from the whole script, which fails on the comment
explaining its removal *and* on other importers that legitimately use it — now
scoped to the watcher and to the assignment rather than the word. The other
raised inside a fake downloader without catching it. Fixed rather than
loosened.

### ✅ W126 — One import, one success message

Operator, 2026-09-11, with both dialogs side by side: *"This should just be an
import success, and should mimic the tpc plugins behavior upon success."*

The tak.gov plugin importer finishes with **Imported** / *"…is in the local
library"* and a full progress bar. The repo/Play one announced the **hold**
instead, and replaced the whole modal body so the bar vanished at the moment it
should have read 100%. Identical behaviour — every import is held — reported as
a confirmation on one tab and a caveat on the other.

⚠️ **The hold belongs where it is acted on.** It is the normal result of every
import, not a qualification on this one, so it is stated on the Apps page
(W125's *held — publish to deploy*) rather than in the line confirming the
download worked.

⚠️ **The app name is now set with `textContent`**, not interpolated into
`innerHTML`. It arrives from a third-party search result, so whatever the source
chose to call the app was going into the DOM.

⚠️ **Deliberately *not* copied: the plugin importer's `location.reload()` on
close.** That list is server-rendered, so a reload is how a row gains its
"imported" pill. A repo search is ephemeral — reloading would throw away results
the operator may still be importing from. Say the word if the refresh matters
more than the results.

Suite **1416 passed, 1 skipped**. No agent change.

### ✅ W125 — Play imports go straight in, and "held" is not a fault

Operator, 2026-09-11: *"there is no sense in showing a version button and then
showing a list with no version. It should be a straight download. also, its
showing in my list as 'none published' still."*

#### A picker over one blank row

Play cannot enumerate versions — the source returns a single placeholder whose
code, name and architecture are all unknown until the file is read. So the
Versions button opened a table with one empty row and an Import button in it.
The search row now shows **Import** for such a source and skips the dialog.

⚠️ **The client is told, not left to guess.** `picks_version` is sent explicitly
by *both* kinds of source rather than inferred from a missing key — otherwise
the next source added would silently lose its version picker.

⚠️ **The direct import still asks the server for the version** rather than
fabricating one. The placeholder carries the download URL and source name the
import endpoint needs, and inventing those in the browser would put a
server-side URL scheme into the client.

#### "none published" was reporting a success as a fault

Held is the *designed* outcome of an import: `repo_import` never publishes,
because publishing aims every device asking for "latest" at a build and that has
to be an operator's deliberate act. Rendering it in warning orange said the
opposite. Now a package with a held build shows a neutral **held — publish to
deploy** with the version, and only a package with *nothing in it* warns
(**nothing uploaded**) — a distinction with its own test, since softening both
would hide a package that really has nothing to install.

**The behaviour is unchanged**: imports are still held. Only the reporting of it
is fixed.

#### A guard that could not read block comments

`test_the_script_does_not_reintroduce_hints` flags `placeholder` in
script-built fields, skipping `//` comments. A JSDoc line using the word in
prose was therefore reported as a field missing its tip. Fixed in the guard —
it now skips `*` continuation lines too — rather than by rewording around it,
because the gap would have caught the next person the same way.

Suite **1412 passed, 1 skipped**. No agent change.

### ✅ W124 — A held import has to look imported

Operator, 2026-09-11, after importing Chrome from Google Play: *"it shows no
versions in the list, download says imported and held, but says not imported."*

#### The import was fine; the console lied about it twice

Checked first: `com.android.chrome`, version_code **797708204**, version_name
**152.0.7977.82**, four splits, `published=False`. Exactly what "imported and
held" means. Two separate reporting faults made it read as a failure.

**1. `Importing Google Chrome null…`** — `atlas.js` interpolated
`version.version_code`, and **Google Play publishes no version code before the
download**. The source returns a single placeholder (`version_code=None`,
`version_name="latest"`) because Play cannot enumerate versions; both fields are
read from the file once it arrives. So the `—` / `latest` / `not stated` row in
the picker is correct and stays — only the progress line was wrong.

**2. `none published`, and nothing else.** That phrase is equally true of a
package holding four freshly imported splits and of one containing nothing. The
row now names what is held (`797708204 (152.0.7977.82) held`). The "versions in
the library" link was also gated on `> 1` version, so the **first** import of
any app had no way through to it at all.

#### ⚠️ Third time for the same test mistake

The library-link assertion failed because my markup wrapped the line between
`{{ n }}` and `version`, rendering `1
   version in the library`. That is the
same line-wrapped-template-breaks-the-assertion trap as twice before. Fixed in
the template rather than by loosening the test, since the wrap was also wrong
for the output.

Suite **1407 passed, 1 skipped**. No agent change.

### ✅ W123 — Remove tags

Operator, 2026-09-11: *"Lets remove tags all together"* — one day after the Tags
tab was built, having seen what it actually offers.

#### ✅ Nothing is at stake on this host — checked, not assumed

| | rows |
|---|---|
| `tag` | 0 |
| `device_tag_member` | 0 |
| `assignment` with `tag_id` | 0 |
| `profile_assignment` with `tag_id` | 0 |
| `enrollment_token_tag` | 0 |

So the migration destroys nothing here. Groups carry every grouping this
deployment actually uses.

#### ⚠️ The migration ships to installs that are not this one

This is the part worth stating before it is written. The operator has said they
want the project usable by other deployers, and **a deployer who uses tags
would lose every tag, membership and tag-scoped assignment on upgrade — and
their devices would lose those policies with no warning at all.** Tags reach
devices exactly the way groups do.

That is an accepted consequence of removing a feature, not a bug, but it is not
something to discover from a changelog. `downgrade()` recreates the schema; it
cannot recreate the data, and the migration says so.

#### ⚠️ The enum value and the columns have to go together

`AssignmentScope` is stored as a string, and `scope` is mapped through the Python
enum. Dropping `TAG` from the enum while any row still says `"tag"` makes that
row **unloadable** — a 500 on the resolver rather than a tidy absence. So the
migration deletes tag-scoped rows *before* the enum loses the value, and the two
land in the same release. Removing the surface first and the schema later is
only safe in that order, never the reverse.

⚠️ `ck_assignment_single_target` names `tag_id` and has to be rewritten rather
than dropped — otherwise an assignment could be created targeting nothing.
SQLite needs batch mode for that.

#### W122's generality collapses back

`_CONTAINERS` exists to drive groups and tags through one implementation. With
one kind left, a dispatch table of one entry is noise that invites the next
reader to wonder what the other cases were. It goes back to plain group
handling — the day-old refactor is undone deliberately, not forgotten.

✅ **No agent change.** The agent never knew about tags; this is server-only, so
no APK.

#### Chunk 1 — the surface

1. Console: Manage keeps Devices and Groups tabs; tag routes, the tag half of
   the container machinery, and the tag inputs on Enroll and the profile editor
   go.
2. API: `POST /api/v1/tags`, `PUT /api/v1/tags/{id}/devices`, and `tag_ids` on
   enrollment-token creation and profile targets.
3. `enrollment.py` stops scoping tokens to tags and stops placing devices in
   them.
4. Tests: delete `test_tags_console.py`; fix the fixtures and cases that pass
   `tag_ids`.
5. Deploy — a state where tags are unreachable but the columns still exist, so
   nothing can half-break.

#### ✅ Chunk 1 done (2026-09-11)

Suite **1403 passed, 1 skipped**. Tags are unreachable: no console surface, no
API, no token scoping, no device placement. The columns and `AssignmentScope.TAG`
remain, so any row that still says `"tag"` continues to load and resolve.

⚠️ **Removal is not the same shape of work as building.** Deleting the schema
field first broke 345 tests at once, because four call sites still passed
`tag_ids` into functions that no longer took it. That is the ordinary cost of
pulling a thread through a codebase — but it is also why chunk 2 is separate:
had the migration been in the same pass, the fleet would have been mid-deploy
with a half-applied removal.

Three tests changed rather than being deleted, because each was testing
something that still matters with two scopes instead of three: token scoping
lands *every* target on the device, bulk assignment mixes target kinds, and
policies stack across scopes.

#### Chunk 2 — the schema

6. Drop `Tag`, `device_tag_member`, `enrollment_token_tag`, `assignment.tag_id`,
   `profile_assignment.tag_id`, `AssignmentScope.TAG`, and the resolver's `tag`
   specificity tier; rewrite the CHECK constraint; migration with `alembic
   heads` checked first.

#### ✅ Chunk 2 done (2026-09-11) — `c0e2g4i6k8m0`

Operator: *"no one has deployed yet, so there are no effects on others at this
time"* — which removes the only argument for keeping the schema.

Suite **1403 passed, 1 skipped**. `alembic heads` checked before writing the
revision, per the lesson that cost an API outage the day before.

⚠️ **Two orderings inside the migration are load-bearing.** Tag-scoped rows are
deleted *before* `AssignmentScope.TAG` leaves the model, because `scope` is
mapped through that enum and a surviving `"tag"` row would become unloadable —
a 500 in the resolver, not a tidy absence. And
`ck_assignment_single_target` is **rewritten rather than dropped**: it enforces
"exactly one target", so removing it would let an assignment point at nothing,
which the resolver would silently skip. SQLite needs batch mode for that.

One thing the earlier grep missed and the type checker would not have caught:
`fleet.py` still iterated `device.tags` after the relationship was gone. Found
by reading the leftovers rather than by a test, because the fleet page is
rendered in tests that were passing for unrelated reasons — worth remembering
that "imports OK" is not "works".

### ✅ W122 — Manage tabs: Devices, Groups, Tags

Operator, 2026-09-11: *"On the manage page, I want tabs for devices, groups, and
tags."*

#### ⚠️ Two of the three tabs have somewhere to go; the third has nothing at all

Devices is the existing `/fleet` table. Groups got its pages in W119/W120. **Tags
have no console surface whatsoever** — the model, the API (`POST /api/v1/tags`,
`PUT /api/v1/tags/{id}/devices`) and tag-scoped `Assignment`s have all existed
from early on, and nothing has ever exposed them.

So a Tags tab is not a tab. Listing tags that cannot be created, populated or
assigned to would be a dead end, and a visibly empty third tab is worse than
none. **Tags reach parity with groups in this chunk** — that is what the tab
has to contain to mean anything.

#### One implementation, parameterised, rather than a second copy

The group routes and the tag routes differ only in a model class and the string
`"group"` / `"tag"`. The service layer is *already* general:
`_apply_membership` is typed `DeviceGroup | Tag`, and `create_assignment` takes
the scope as a parameter. Duplicating the console half would leave two copies to
drift — which is exactly how W118 shipped a cache bug. A small descriptor
(model, scope, url prefix, label) drives both.

⚠️ `Tag` has **no `description`**, unlike `DeviceGroup`. The shared template has
to tolerate that rather than assume the richer shape.

#### Existing links must keep working

`/groups` is linked from Fleet and from the group detail page, and W121's QR
page points at it too. It redirects to `/fleet#tab-groups` rather than 404ing —
the tab bar already reads `#tab-<name>` from the hash, so a deep link lands on
the right tab.

#### Chunk 1

1. Descriptor + shared handlers for group/tag detail, membership, assignment
   add/remove and delete.
2. `/fleet` gains the three tabs; Groups and Tags panels hold their create forms
   and lists.
3. `/tags/{id}` detail, mirroring the group page.
4. `/groups` and `/groups/{id}` keep working — the list redirects to the tab, the
   detail page stays.
5. Tests: the tabs exist; a tag can be created, populated, and its assignment
   reaches a member's desired state; W119/W120's group tests still pass
   unchanged, which is what proves the parameterisation did not quietly alter
   the group behaviour.
6. Deploy.

#### ✅ Done (2026-09-11)

Suite **1414 passed, 1 skipped**. The five group handlers became
`_render_container_detail` / `_set_container_devices` /
`_assign_policy_to_container` / `_remove_container_assignment` /
`_delete_container`, driven by a `_CONTAINERS` descriptor; the group and tag
routes are now thin wrappers, and `group_detail.html` became
`container_detail.html`.

✅ **Every W119/W120 group test passed unchanged through the refactor**, which
is the only reason a rewrite of just-shipped code was reasonable to attempt.

One assertion did change, correctly: Fleet no longer *links* to `/groups`
because the list is a tab on the page. `/groups` redirects to
`/fleet#tab-groups` rather than 404ing, and there is now a test for that
redirect — Fleet, the detail page and W121's QR page all pointed at it.

⚠️ **The tag tests assert the desired state, not the rows.** Everything here
shares code with groups, so the plausible failure is a tag page quietly writing
`group_id`; `test_the_assignment_is_scoped_to_the_tag_not_a_group` and the
check-in assertions are what would catch it. Two negative tests keep the shared
template honest about `Tag`'s thinner shape: no description field, and no
enrollment-token warning, since only a group can scope a token and a caution
that is never true trains the reader to skip the ones that are.

### ✅ W121 — Pick a group when generating the provisioning QR

Operator, 2026-09-11: *"I want to be able to assign a group during the
provisioning process via the QR code. Set the group when adding the wifi details
so that device automatically joins selected group and receives associated group
policies"*.

#### Almost all of this already exists

An enrollment token can be scoped to groups (`enrollment_token_group`), and
enrolment already applies them — `enrollment.py:336`,
`device.groups.extend(g for g in token.groups …)`. A device enrolled with a
group-scoped token lands in the group and inherits its policy stack with no
second step. **What is missing is only the choosing.**

#### ⚠️ The QR is a derivative of the *primary* token, which is what makes this
#### a design question rather than a form field

`mint_qr_secret` issues a signed 15-minute secret resolving to **the** primary
token, so today a QR always carries the primary's groups. Two ways to let an
operator pick:

| | Cost |
|---|---|
| **Encode the groups in the signed QR payload** | Changes the `{id}.{nonce}.{issued}.{signature}` format and `resolve_token`'s contract — it returns a token, and would now need to return a token plus overrides. Security-sensitive surface, touched for a UI convenience. |
| ✅ **Issue the QR against a group-scoped token instead of the primary** | No change to enrolment, auth or crypto at all. |

The second works because of something worth stating plainly: **`resolve_token`
verifies the QR signature, loads that token id and checks `is_usable()` — it
never requires `is_primary`.** The QR machinery is already general over tokens;
only the minting helper was specific to the primary.

So: **get-or-create one standing token per group**, named for it, and issue the
same 15-minute derivatives against that. One extra row per group rather than
one per QR, revocable on its own, and the whole short-lived-signed-QR property
is retained rather than re-implemented.

#### ⚠️ A QR that silently enrols into the wrong group is the failure to avoid

The QR is a picture; nothing about it says what it will do. The page must state
the group beside the code, and the "no group" case must stay visibly distinct
from "some group I forgot I picked" — a sticky selection would be worse than no
feature.

#### Chunk 1

1. `enrollment.token_for_group(session, group)` — get-or-create the standing
   group token, non-primary, long-lived, scoped to exactly that group.
2. Group select on both Wi-Fi forms (`enroll.html`, `token_qr.html`), defaulting
   to "No group".
3. `/enrollment/qr` accepts `group_id` and mints against that token.
4. The QR page names the group beside the code, or says plainly that no group
   is attached.
5. Tests: a device enrolled with a group QR lands in the group **and** receives
   its policies; no group selected behaves exactly as today; the group token is
   reused rather than multiplied; revoking it does not disturb the primary.
6. Deploy.

#### ✅ Done (2026-09-11)

Suite **1402 passed, 1 skipped**. No change to enrolment, the QR guard or the
signed payload — the group select resolves the code to a different token, and
everything downstream was already general over tokens.

⚠️ **A test-harness trap worth recording.** Three tests failed for a reason
unrelated to the feature: without `agent_signature_checksum` the QR payload
raises, and the page renders an error banner *instead of* the block holding the
pill and the secret — so every assertion about the QR fails identically whether
the feature works or not. The fixture that configures it must depend on
`client`: as a bare autouse fixture it ran **before** `client`, which then reset
`dependency_overrides` and silently undid it. The existing example in
`test_admin_ui.py` sidesteps this by setting the override inside the test body.

### ✅ W120 — Delete a group, and manage its assignments

Operator, 2026-09-11: *"build deleting a group, and editing group assignments
from the group page"*. The two pieces W119 deliberately left out.

#### Assignments belong here, unlike on the device page

W118 refused to remove a group assignment from a *device* page, because the
click would change every device in the group while looking like a per-device
tidy-up. On the **group's own** page that is exactly what the operator means, so
the button belongs here — labelled with how many devices it reaches, so the
scale is visible at the moment of the click rather than discovered afterwards.

Both actions delegate to the API's `create_assignment` / `delete_assignment`
rather than building `Assignment` rows here. Those already validate the policy,
reject templates, resolve pinned versions and call
`invalidate_for_assignment` — and one implementation cannot drift from itself.
W118 shipped a cache bug precisely by hand-rolling the second copy.

#### ⚠️ Deleting a group cascades four ways, and one of them is silent

`device_group.id` is referenced with `ondelete="CASCADE"` from four places:

| Cascade | Consequence |
|---|---|
| `device_group_member` | Devices leave the group |
| `Assignment.group_id` | **The group's policies stop reaching those devices** |
| `ProfileAssignment.group_id` | Same, for profile assignments |
| `enrollment_token_group` | ⚠️ **Enrollment tokens lose their scoping** |

The last one is the trap. A token scoped to this group stays live and keeps
working — it just quietly stops putting devices into the group. A tablet
enrolled with it afterwards lands with none of the policy stack the operator
expects, and nothing anywhere says why. **The delete panel therefore counts the
tokens that reference the group and says what will happen to them**, because
that consequence is invisible everywhere else.

#### ⚠️ Invalidate before the cascade, not after

The member list has to be captured *before* the delete: once the cascade runs,
`device_group_member` is gone and there is no way to know whose effective policy
just changed. Same shape as the API's delete resolving `devices_targeted_by`
before removing the row.

#### Typing the name to confirm

Consistent with disenroll, and for the same reason: this changes policy on every
member device at once and breaks token scoping invisibly. Unassigning a single
policy stays a plain click — it is reversible and affects one thing. Ceremony
should track consequence, not just destructiveness.

#### Chunk 1

1. Group page: assign a policy (select + rank), delegating to the API.
2. Group page: remove an assignment, labelled with the device count.
3. Delete panel: impact counts, typed-name confirmation.
4. Delete route: capture members → delete → invalidate them.
5. Tests: assigning reaches members; removing stops reaching; deleting a group
   both strips its policies from members *and* is refused without the name; the
   token-scoping warning appears when a token references the group.
6. Deploy.

#### ✅ Done (2026-09-11)

Suite **1394 passed, 1 skipped** — the group tests passed first run, which is
the payoff for delegating to `create_assignment` / `delete_assignment` instead
of writing a third copy of assignment handling.

Both directions are asserted against the **desired state**, not against rows:
assigning from the group page reaches a member's tablet, removing stops
reaching it, and deleting the group strips its policies from members. Two
refusals are pinned as well — another group's assignment cannot be removed via
a hand-edited URL, and the delete is refused unless the name matches exactly.

The token warning has a negative test beside it, so it still means something
when it appears.

### ✅ W119 — Device groups in the console

Operator, 2026-09-11: *"in the manage section, i want to be able to create
groups. I should be able to create the group, then go to the group details and
associate devices."*

#### The backend already exists; this is console-only

`DeviceGroup`, the `device_group_member` join, group-scoped `Assignment`s and
group scoping on enrollment tokens have all been there since early on, and the
API has `POST /api/v1/groups`, `GET /api/v1/groups` and
`PUT /api/v1/groups/{id}/devices`. **Nothing in the console ever exposed them**,
so every group in this deployment was made by hand or by test code.

✅ **`_apply_membership` already invalidates both the previous and the new member
sets** — the exact mistake W118 made an hour ago, already handled here. Reusing
it rather than writing membership code is the whole reason this is small.

#### ⚠️ Membership is *replace*, not add

`PUT /groups/{id}/devices` sets `container.devices = devices` wholesale. A
checkbox list of the fleet with one Save button maps onto that honestly — what
you see ticked is what the group will contain. An "Add device" button would
imply incremental semantics the endpoint does not have, and would silently drop
members if a second operator was editing at the same time.

⚠️ At fleet scale a checkbox list stops being reasonable. Fine for three
devices; noted so nobody is surprised later.

#### This is where W118 sends people

W118 put *"via group Field Tablets"* on the device page for policies an operator
cannot remove there. That text is only useful if the group has a page to go to,
and it does not yet. The group detail page therefore shows **which policies are
assigned to the group and how many devices they reach** — read-only for now, so
the loop is closed informationally without adding a second fleet-wide delete
button in the same day.

#### Chunk 1

1. `GET /groups` — list with member counts, and a create form.
2. `GET /groups/{id}` — name, description, membership checkboxes, and the
   group's policy assignments with the number of devices each reaches.
3. `POST /groups` and `POST /groups/{id}/devices`, both CSRF-guarded, delegating
   to the same service the API uses so cache invalidation cannot diverge.
4. Link it from the Fleet page, under the Manage nav.
5. Tests: create; membership replaces rather than appends; a group assignment
   starts reaching a newly added device's desired state; the device page's
   *"via group"* note now links somewhere real.
6. Deploy.

**Not in scope, deliberately:** deleting a group, and editing group assignments
from this page. Both are worth having and neither was asked for.

#### ✅ Done (2026-09-11)

Suite **1386 passed, 1 skipped**. `/groups` (list + create), `/groups/{id}`
(membership checkboxes + the group's assignments), linked from Fleet.

The membership POST delegates to the API's own `_apply_membership` rather than
setting the relationship itself, so the cache invalidation cannot drift between
the two entry points — the W118 mistake made structurally hard to repeat.

Two tests earn their keep beyond the obvious:
`test_joining_a_group_brings_its_policies_to_the_device` and its inverse assert
the **desired state** changes, not that a checkbox ticked. The reverse direction
is the one that depends on invalidating the *previous* members, which is the
half easiest to forget.

### ✅ W118 — Unassign a policy from the device page

Operator, 2026-09-11: *"I want the ability to remove policies from device
management section in the device info page. listed policies should be able to be
unassigned to the device with a simple click"*.

#### ⚠️ Only some of those rows *can* be unassigned here, and that is the design

"Policies reaching this device" lists everything the resolver considered, and
they arrive by four different routes. A single Remove button on every row would
be wrong in three of the four cases:

| Row | Removable here? | Why |
|---|---|---|
| **Device-scoped assignment** | ✅ yes | It exists solely to bind this policy to this device. Deleting it affects nothing else. |
| **Group assignment** | ❌ no | The assignment belongs to the *group*. Deleting it would silently unassign the policy from **every device in that group** — a one-click fleet change dressed up as a per-device tidy-up. |
| **Tag assignment** | ❌ no | Same, for every device carrying the tag. |
| **Profile section** | ❌ no | Not an `Assignment` row at all: its id is the synthetic `profile:{pa.id}:{section.id}`. There is nothing to delete, and detaching the profile is a different act. |

So the button appears **only on device-scoped rows**, and the other three say
where the policy comes from instead — which is the actionable information, since
the operator's real next step is to edit the group, the tag, or the profile.

⚠️ **The server must enforce this, not just the template.** A hidden button is
not a control: the route re-checks that the assignment it is about to delete is
device-scoped *and* targets **this** device, for the same reason
`_DEVICE_ACTIONS` is an allowlist — *"letting the path segment select any
command in the enum would put `wipe` one crafted URL away from a button that
says Play sound"*. Here the equivalent mistake would unassign a policy from a
whole group via a hand-edited URL.

#### "Simple click" — no confirmation dialog

Deliberate, and the opposite of the disenroll button two sections down. Removing
an assignment is **reversible** — re-assign it and the device converges back on
the next check-in — so a confirmation step would be friction without a payoff.
Disenroll types the serial because a factory reset is not reversible. Different
risk, different ceremony.

#### Chunk 1

1. Enrich the `considered` rows in the device route with: whether this row is a
   device-scoped `Assignment`, and a human origin ("via group *Field Tablets*",
   "section of profile *Standard*") for the ones that are not.
2. `POST /devices/{id}/assignments/{assignment_id}/remove` — CSRF, re-checks
   scope and target server-side, deletes, redirects with a banner.
3. Template: a Remove button on removable rows; the origin text on the rest.
4. Tests: a device assignment goes; a **group** assignment is refused even when
   the id is posted directly; a profile id is refused; the device's effective
   policy actually changes afterwards.
5. Deploy.

#### ✅ Done (2026-09-11)

Suite **1373 passed, 1 skipped**.

⚠️ **One bug the tests caught that a simpler test would not have.** The first
version of the route deleted the assignment and committed — and the device went
on serving a **stale cached effective policy**. The row vanished from the table
and nothing reached the tablet. The API delete does three things and I had done
one: resolve the affected devices *before* the row is gone, delete, then
`eff.invalidate`.

The test that caught it asserts the **desired state changes**, not that the row
disappeared. Asserting the row would have passed against the broken version, and
the feature would have shipped looking like it worked — the same shape of
mistake as W112 C2 (a mechanism that works reaching nothing that consumes it).

### ✅ W116 — Disenroll clears Factory Reset Protection

Built and deployed in agent 0.58.0 (`42b6ea9`); the disenroll path sends
`wipe_reset_protection`, an ordinary lost-device wipe does not.

#### ✅ What the 2026-09-11 run on `SM-X828U` did prove

* **W114 again, on a current agent.** Command delivered, acknowledged and the
  record removed inside one second — and the tablet then actually reset. That
  ack-plus-wipe pairing is exactly what failed the first time disenroll was ever
  run, so seeing both on 0.60.0 matters.
* **`wipeDevice` accepts the combined mask.**
  `WIPE_EXTERNAL_STORAGE | WIPE_RESET_PROTECTION_DATA` was not rejected.

#### ❌ What it did not prove, and why the result looked like a pass

The tablet came up with **no Google account challenge** — but **no Google account
was signed in**, so FRP was never armed and the flag had nothing to clear.

⚠️ **The pass condition and the no-op condition are indistinguishable from the
outside.** "Setup asked for nothing" is what you see whether the flag worked or
whether the protection was never on. The precondition was flagged twice before
the run and not confirmed until after, which is the process lesson: **for a test
whose failure mode is invisible, confirm the precondition before firing, not
after.**

**A valid run needs a Google account signed in on the device before the
disenroll.**

#### ✅ Redone properly, 2026-09-11 — verified

With a Google account signed in first: the device disenrolled, reset, and
**re-provisioning proceeded without ever asking for that account**. FRP was
armed, and `WIPE_RESET_PROTECTION_DATA` cleared it.

So the feature does what the console promises — a handed-back device comes up
ready for whoever receives it, rather than gated on credentials belonging to
whoever held it last — and **FRP clearing is not a Knox dependency** on One UI.

Both halves of the lost-vs-handed-back distinction are now real: a disenroll
clears the protection, an ordinary wipe leaves it armed.

### ✅ W117 — A master bypass PIN for the provisioning permission block

Operator, 2026-09-10: *"let's build in a bypass button that requires a pin code.
I want a 6 digit pin that is generated by the web portal upon install of the
service. this code will be unique to each server install, but will remain fixed
on the server. this code will be visible in the admin section. it will include a
note that this is a master bypass code to skip permissions in provisioning
step."*

Replaces W115's plain "Continue anyway" confirmation dialog, which could be
tapped by someone in a hurry who did not read it — roughly the situation that
produced the bug in the first place.

#### ⚠️ The PIN is verified by the server, and it has to be

The tempting design is to ship the PIN — or a hash of it — in the provisioning
extras so the agent can check it offline. **That leaks the master code.** Six
digits is 10⁶ candidates, so a hash in a QR that gets displayed on screens and
passed around is brute-forced instantly; a salted KDF only changes how long
"instantly" is. The QR is the one artefact of this system most likely to be
photographed.

So the agent POSTs the PIN and the server answers. What authenticates that call
is the **enrollment token the device already holds** at that moment
(`config.enrollmentToken`, seeded from the provisioning extras) — the same
credential enrollment itself uses, which limits guessing to people already
authorized to provision a device.

⚠️ **Consequence, stated rather than discovered later: the bypass now needs the
network.** W115's escape hatch existed for a permission that cannot be granted on
some unknown OEM, and it worked offline. This one does not. Acceptable because
`finishProvisioning` immediately calls `Reconciler.sync()` — a device that cannot
reach the server cannot meaningfully finish provisioning anyway — but it is a
real narrowing of the escape, and the dialog says so when the call fails.

#### ⚠️ Two interpretations of the brief, both deliberate

1. **"Generated upon install" is implemented as get-or-create on first read.**
   Generating only in the `init` container would leave every *existing* install
   — including this one — permanently without a PIN, and therefore with a
   bypass button nobody can use. Get-or-create is idempotent, covers fresh and
   upgraded installs alike, and still yields one fixed value per install.
2. **Stored in plaintext in `app_setting`**, alongside the SMTP/AD/SMS secrets
   that already live there (`settings_store` documents that, folded into R8). It
   *must* be displayable to satisfy "visible in the admin section", so hashing is
   not available. Sealing it with `TokenVault` was considered and rejected as
   theatre: the vault key sits on the same host, and the thing being protected
   only defeats a provisioning-time control on a device the holder is already
   authorized to provision.

#### What the PIN can actually do, so nobody over-trusts it

Skip the permission grants while provisioning a device you already hold a valid
enrollment token for. The result is a *less* capable managed device, not a
compromise of the fleet or of the server. It is an administrative control, and
the admin page should not dress it up as more than that.

Brute-force resistance still matters, because a fixed per-install code will be
treated as a master secret whatever the note says. Hence a per-token attempt cap
rather than an elaborate rate limiter — proportionate to a secret whose worst
outcome is a badly provisioned tablet.

#### Chunk 1 — server

1. `bypass_pin` get-or-create in `settings_store`: six digits from `secrets`,
   stored in `AppSetting`, stable thereafter.
2. Migration adding `enrollment_token.bypass_attempts` (integer, default 0).
3. `POST /api/v1/provisioning/bypass-pin` — enrollment token + PIN, constant-time
   compare, attempt cap, failures logged.
4. Admin console: read-only display with the note the operator asked for, plus
   what it does *not* grant.
5. Tests: the PIN is six digits, stable across reads, and different per install;
   a wrong PIN is refused; the cap is enforced; and — the one that matters — the
   PIN appears in **no** device-facing payload (QR, provisioning extras, desired
   state).
6. Deploy.

#### ✅ Chunk 1 done and deployed (2026-09-10, `98a05a7`)

PIN, endpoint, admin display, migration. **This install's PIN is `478416`.**

✅ **Verified end to end through the real proxy on the device port**, using a
throwaway enrollment token since revoked: a wrong PIN returned
`{"accepted":false,"attempts_remaining":9}` and the right one
`{"accepted":true,"attempts_remaining":10}` — the counter spending down and the
allowance being restored on success, both as designed.

⚠️ **nginx had to be told about it.** The device port default-denies `/` and opts
paths back in one at a time; without a `location = /api/v1/provisioning/bypass-pin`
the proxy refuses the call and the application never sees it. Needs
`docker compose restart proxy`, not just a rebuild.

#### ⚠️ I took the API down for ~20 minutes doing it (2026-09-10)

The migration's `down_revision` pointed at the wrong parent, branching the
history; the api container runs `alembic upgrade head` on start and refused to
boot with *"Multiple head revisions are present"*.

**Cause: I chose the parent from `ls alembic/versions | tail -3`, which sorts
alphabetically, not chronologically.** `z6b8d0f2h4j6` merely sorted last and
already had a child; the real head was `h4j6l8n0p2r4`. **`alembic heads` answers
this in one command — run it before writing a migration**, and note that the
existing filenames are *not* in chronological order.

Impact, checked rather than assumed: the last device request was three hours
before the deploy and there were **zero 5xx** in the window, so no device saw
it; the console was down for those twenty minutes.

#### ✅ Chunk 2 done (2026-09-10) — agent 0.59.0 (versionCode 104)

PIN entry replaces the confirmation dialog. `ApiClient.checkBypassPin` uses
**`enrollClient`**, not `mtlsClient`: this runs in the setup wizard before the
device has any identity, the same position `enroll` is in.

⚠️ **Three outcomes, deliberately distinguished** — accepted, refused (with
attempts left), and could-not-reach-the-server. Collapsing the last two into
"failed" hides the one the operator can actually act on. Only an explicit
`accepted` calls `finishProvisioning`; a test pins that there is exactly one
such call and that it sits under the accepted branch.

⚠️ **The PIN is never persisted or logged.** It is fixed for the life of an
install, so a copy in a preference file or a collectable log bundle outlives the
moment it was needed.

Server suite **1358 passed, 1 skipped**.

#### ⚠️ Two bugs found on hardware, both mine (2026-09-10)

**1. The credential does not survive enrolment.** The check was authorized by the
enrollment token, and `Reconciler.kt` deletes that token the instant enrolment
succeeds — *"keeping it would leave a usable enrollment credential on the
device"*. The permission screen is normally reached **after** enrolment, so the
common case had no credential and the operator saw *"no server is configured"*
on a device whose server URL was fine. Fixed by giving an enrolled device its own
path, `POST /api/v1/device/bypass-pin`, authenticated by the client certificate,
with `device.bypass_attempts` alongside the token's counter. The agent chooses on
`config.isEnrolled`.

**2. The agent's body did not match the schema.** `secret` was required; the
enrolled path has none, so the agent sent `{"pin": …}` and got a **422**, which
the agent reports as "could not reach the server". Found in one line of the proxy
log, not from the device.

⚠️ **23 tests passed through bug 2**, because every one of them sent
`secret: ""` — the body *I imagined* the agent sends. **A test that constructs
its own request only checks the server against the author's idea of the client**,
which is exactly the disagreement that was wrong here. The replacement reads the
JSON keys out of `ApiClient.kt` and builds its body from those, and it was
checked against the old schema to confirm it actually fails.

#### ✅ Verified on hardware — `SM-X828U` / `R5GL80RJYHK`, 2026-09-10

A real provisioning run with three required permissions ungranted:

* the block held, and the code box appeared;
* **`478416` was accepted** — `POST /api/v1/provisioning/bypass-pin → 200`,
  `bypass PIN accepted for token gymodM4x`;
* the device enrolled and now reports exactly what the admin page promised —
  `DEGRADED`, detail *"missing permission: all_files_access; …
  display_over_other_apps; … battery_exemption"*, so `agent_update` will offer
  it nothing until they are granted;
* the optional `power_menu` sits in `compliance_warnings` and does **not** touch
  the status, which is the invariant `PermissionRequirement` insists on.

#### ✅ Both paths now verified on hardware — `SM-X828U`, 2026-09-11

The first run exercised the **pre-enrolment** path (token). A second run was
steered deliberately onto the **mTLS** path by waiting on the permission screen
until the device had enrolled before tapping, which nulls the token:

```
POST /api/v1/device/bypass-pin  200   x3
bypass PIN rejected for device R5GL80RJYHK (attempt 1 of 10)
bypass PIN rejected for device R5GL80RJYHK (attempt 2 of 10)
bypass PIN accepted  for device R5GL80RJYHK
```

`device.bypass_attempts` back to 0 afterwards — counted per **device**, and the
allowance restored on success.

⚠️ **The two paths are chosen by a race, not by configuration.**
`MdmDeviceAdminReceiver.onEnabled` starts `SyncScheduler` as soon as device
admin is enabled, so enrolment runs concurrently with the permission screen and
whichever finishes first decides which credential still exists. That is why the
same tablet produced "no server is configured" on one run and a working code box
on the next. **To test a particular path deliberately: tap immediately for the
token path, or wait until the device appears in the fleet for the mTLS path.**

#### Wording fixed (agent 0.61.0)

The rejection message named the enrollment token — *"…before this enrollment
token is locked out"* — which is the credential on only one of the two paths,
and not the one an operator normally hits. On an enrolled device the counter is
on the device, so the message pointed at the wrong thing and implied a wrong
remedy ("use a new enrollment token"). Now neutral: *"…attempt(s) left before
the bypass locks out"*, and the locked message says to grant the permissions,
which is the remedy on both paths.

#### Follow-up worth doing

The agent reports every non-200 as "could not reach the server", which turned a
422 into a network story and cost a round trip to diagnose. **A response that
arrived is not a connection failure**, and saying so on the device would have
made bug 2 self-evident.

### ✅ W113 — Remove Trusted certificates, SCEP, Global HTTP proxy

Operator, 2026-09-09: *"lets just remove trusted certs, SCEP, global HTTP proxy"*.

**Why**: W112 C2 established that a client certificate reaches no consumer on
this fleet without EAP Wi-Fi support that does not exist, and the operator has no
enterprise Wi-Fi or VPN to test against. The proxy is advisory by Android's own
javadoc. Rather than carry three things that either do nothing or cannot be
proven, they come out. **Web content filtering and OS updates stay** — both
still wanted, and OS updates is the one with real value here.

#### ⚠️ The order is forced, and getting it wrong strands a CA on a tablet

`CertificateApplier`'s contract is **absent means removed**, and that is a
security property: the agent removes an anchor when policy stops naming it. So
the agent is the only thing that can clean up after this feature.

**Policy `5064a51b` ("W112 trust check") is assigned to a device**, which is
therefore trusting the test CA right now. Deleting the server spec *and* the
agent applier together would leave that anchor installed with nothing left able
to remove it — and if `DISALLOW_CONFIG_CREDENTIALS` were ever re-applied, not
removable by hand either.

**So: server first, verify the device drops it, agent second.** No live data is
touched — dropping the server-side resolution makes the desired state carry
`certificates: []`, and agent 0.54.0 (still deployed) removes what it installed
on the next check-in, exactly as designed. The orphaned policy rows stay put and
are ignored: `effective_policy` already skips unknown types
(*"unknown type, e.g. a rolled-back deployment: ignore, don't crash"*), so there
is no migration and nothing breaks.

#### Chunk 1 — server

1. Delete `app/policies/specs/certificates.py`; unregister from `registry.py`.
2. `creator_catalog.py`: Security category loses its `CERTIFICATES` type (becomes
   a stub-only category like Accounts); drop the `scep` and `global-http-proxy`
   stubs; keep `web-content-filtering` and `os-updates` and drop their now-dangling
   `after="trusted-certificates"`.
3. `effective_policy.py` — drop `payload["certificates"] = …`; **keep
   `desired_state.py` emitting `certificates: []`** deliberately, so the deployed
   agent removes the anchor.
4. `app/services/files.py` — remove `resolve_certificates`.
5. Replace `tests/test_certificates.py` with a small removal-contract test: the
   empty key still ships, and the type is no longer offered.
6. Keep `allow_credential_configuration` under Restrictions — it blocks the
   credentials screen and is useful independently — but drop its cross-reference
   to the deleted page.
7. Full test run, deploy.

**Then verify on hardware that the test CA disappears from the tablet.** That
verification is the gate on chunk 2.

#### ✅ Chunk 1 done and deployed (2026-09-09, commit `ad314fe`)

Registry, spec, catalog entry, `resolve_certificates` and the console panels are
gone; `certificates: []` still ships. Suite **1335 passed, 1 skipped** — exactly
1346 − 17 removed + 6 new — plus the known sqlite teardown flake in
`test_packages.py`, which passes in isolation and touches nothing here.

Verified on the host after the API answered: `registry.get("CERTIFICATES")`
raises `PolicyTypeError`, `resolve_certificates` is gone, Security reports
`wired=False`, and **both remaining devices resolve `certificates: []`**.

⚠️ **The gate on chunk 2 was overtaken by events, and not by me.** The device
holding the test CA (`60ac55cf`) was **disenrolled from the console at 02:40 UTC**
— W104's first run on hardware. Deleting the device cascaded its assignments
away, which is why the certificates assignment vanished between two of my own
queries. Chased it through the proxy logs rather than assuming, because an
assignment disappearing on its own would have been a much worse finding.

So no enrolled device is carrying a policy-installed anchor any more:

| Device | Agent | Last check-in (UTC) | State |
|---|---|---|---|
| `R5GL40MMHRN` TEST TAB | 0.54.0 | 02:52:08 — **after** the deploy | ✅ received `certificates: []` and swept |
| `R5CX10FCY5D` Phone Test | 0.53.0 | 00:21:09 — before the deploy | Will sweep on next check-in |
| `60ac55cf` | — | — | Disenrolled |

⚠️ **One thing left open, for the operator rather than for code:** whether that
disenrolled tablet actually completed its factory reset. If it did, its CA went
with it. If the reset did not run and the tablet is merely unmanaged, the anchor
is still installed with no agent left to remove it — removable by hand in
Settings, since the credentials restriction is unassigned, but worth an eyeball.
Not determinable from the server.

#### ✅ Chunk 2 done (2026-09-09) — W113 complete

`CertificateApplier.kt` and `CertificatePlan.kt` deleted; `caCertsInstalled`,
`rememberCaCert`, `rememberedCaCert`, `forgetCaCert` and their two preference
keys removed from `AgentConfig`; the applier call and `downloadCertificateBytes`
unwired from `Reconciler`; and the server stopped sending `certificates`
entirely.

**Dropping the key was safe in either order**, which is why it could wait a
chunk: an agent still carrying the applier reads a missing key as
`optJSONArray("certificates") ?: JSONArray()` — an empty array — which means
"remove the anchors you installed". An old agent meeting a new server still
cleans up rather than holding a stale anchor for ever.

Nothing needed cleaning up in the field regardless: the only device that ever
held a policy-installed anchor was `SM-X828U`, which has since been factory
reset, and no other device was ever assigned the policy.

Server suite **1336 passed, 1 skipped** (1335 + one new test asserting the agent
code is really gone — a *half*-removal is the bad state, an agent still sweeping
anchors against a key the server no longer sends). The `test_packages.py` sqlite
teardown flake did not recur.

Agent **0.57.0 (versionCode 102)**.

⚠️ **The W112 platform findings are kept**, in `ANDROID_PLATFORM_REFERENCE.md`,
with a note at the top saying the feature is gone so nobody hunts for
`CertificateApplier`. They were verified on hardware and are exactly what a
future attempt would otherwise have to rediscover — `installCaCert` returning
`false` rather than throwing, `uninstallCaCert` identifying a certificate by its
content, `uninstallAllUserCaCerts` being the trap, and a user being able to
delete a policy-installed anchor.

A side effect worth noting: `reconcileWallpaper`'s docstring had been stranded
two functions above it, separated by the certificate one. Removing the
certificate block put it back on its own function.

### ✅ W104 — Device details, and disenroll as a factory reset

Operator, 2026-09-08: a details page per device — serial and device details,
location history (later), the policies reaching it, and a disenroll that factory
resets the device. The agent must acknowledge receipt **before** resetting, and
the server removes the device once that acknowledgement arrives.

#### Most of this already exists, which changes the shape of the work

| Asked for | State |
|---|---|
| A details page, reached by clicking a device | ✅ `/devices/{id}`, linked from the Fleet page |
| Serial and device details | ✅ on that page |
| The policies reaching the device | ✅ `considered`, **in resolver order**, so it shows real precedence |
| Location history | ❌ to build (placeholder this chunk) |
| Disenroll → factory reset | ❌ to build |
| Agent acks before resetting | ✅ **already implemented** |

⚠️ **The acknowledgement-before-reset requirement is already met, exactly.**
`WipeCommandHandler` returns `CommandOutcome.okAfterReporting`, and the reconciler
runs deferred effects only after `flushCommandResults()` succeeds — if the result
cannot be delivered, the wipe does *not* run and is retried on a later cycle. The
existing comment gives the reason in the operator's own terms: *"there is no next
check-in after a factory reset in which to report anything."* **No agent change,
and therefore no APK release.**

#### ⚠️ What the acknowledgement actually means

It means *"received, and about to reset"* — not *"reset completed"*. Nothing can
report the latter, because the device that would report it has just been erased.

So a device whose reset fails *after* acking is removed from the server while
still being a managed Device Owner, holding certificates the server has revoked.
It cannot check in again, and recovering it means a manual factory reset. That is
an acceptable outcome and arguably the right one — but it is a real consequence of
removing on ack rather than on completion, and it is written down rather than
discovered later.

#### Chunk C1

1. `disenroll` on the device page: a distinct, strongly-confirmed action that
   queues a `wipe` command. Separate from the existing delete, which refuses
   anything not already retired.
2. On the acknowledgement, the server retires or removes the device and revokes
   its certificates — one place, in `record_results`, so it happens however the
   result arrives.
3. A location-history section on the page, honestly empty for now.
4. The device page states what disenroll does before it is pressed, in the words
   that matter: this factory resets the tablet and cannot be undone.
5. Tests: the ack path removes the device; a *failed* wipe does not; a disenroll
   already in flight is not queued twice.
6. Deploy. No APK.

###### ✅ Complete (2026-09-08) — 1176 server tests, server-side only

**Operator chose deletion**, knowing the record's logs, identifiers, attributes and
command history go with it. Retiring and hiding was offered as the alternative that
preserves the audit trail; delete is what was asked for and what was built.

⚠️ **No agent change and no APK.** The acknowledgement-before-reset ordering was
already implemented — `okAfterReporting` plus a reconciler that runs deferred
effects only after `flushCommandResults()` succeeds. A device that cannot deliver
its acknowledgement does **not** reset, and retries later.

⚠️ **A disenroll wipe is marked as one.** An ordinary `wipe` — a lost or stolen
device — must not delete the record an operator still needs, so only a wipe
carrying `disenroll: true` removes anything. There is a test for each direction.

⚠️ **Typing the serial is the confirmation.** A dialog dismissed by reflex is not
proportionate to erasing a tablet, and naming the specific device cannot be done by
accident on the wrong row. Pressing twice queues one reset, not two — the device
would take the first and vanish, orphaning the second.

⚠️ **The record is deleted mid-check-in, so the reply is deliberately empty.**
Everything after that point would be computed from a row that no longer exists.
The device is erasing itself; there is nothing left to ask of it.

⚠️ **What the acknowledgement is not.** It means *received, resetting now* —
never *reset completed*, because nothing can report that. A reset failing after
acking leaves a tablet still owned by this agent, holding revoked certificates,
recoverable only by a manual reset at the device.

**Location history is a placeholder that says so.** An empty map would have an
operator waiting for points nothing is collecting; the panel states that the
`locate` command exists but no history is recorded.

### ✅ W109 — Pick a geofence on a map, and find it by address

Operator, 2026-09-09: *"in the policy creator under the geofencing, I want to make
it to where we can select a point on a map and then set a radius and be able to
see it visually, not just type in coordinates. I also want to be able to type in
an address in addition to coordinates."*

Typing `33.6236, -117.1270` and a radius of 500 and hoping is not a way to draw a
boundary. A fence you cannot see is one nobody can check.

#### ⚠️ The address box is a disclosure decision, and a different one from C3's

C3 declined **reverse** geocoding: it sent *device positions* to a third party
automatically, on every page view, for every device an operator looked at. This is
**forward** geocoding, and the differences matter in both directions:

* **Better:** it fires only when the operator asks, on a string they typed, once.
  No automatic traffic, and nothing about where the fleet actually is.
* **Worse in one specific way:** what gets sent is *where you are about to set up
  a geofence* — planning, not history. For some deployments that is the more
  sensitive of the two.

So it is built the careful way: **server-side** (the browser never talks to the
geocoder, so an operator's own IP is not disclosed either), **only on an explicit
Find press** — never as-you-type, which would leak every keystroke — and against a
**configurable endpoint**, so a deployment with its own geocoder or none at all is
not forced onto a public one. The console says where the query goes.

###### ✅ C1 — Trust anchors (2026-09-09), agent 0.52.0, 1341 server tests

The Security category is wired and live, with **Trusted certificates** working and
the other four sub-topics as scoped stubs *after* it — the W106 lesson about stubs
sorting ahead of the page that does something.

**A dedicated `ca_list` control, not `file_list`.** The FILES control carries a
destination path, extraction and persistence, and none of them mean anything for a
trust anchor — asking an operator where to put one is asking a question with no
correct answer. Asserted: the panel contains no `dest_path` and no `extract`.

⚠️ **The console says this is not what configures ATAK**, because that is the
mistake the category invites. ATAK reads `.p12` files from `/sdcard/atak/…` named
by its own preferences; a TAK server CA installed here will not make it connect,
and without the warning that failure has no visible cause.

**Integrity comes from the existing machinery.** An anchor travels as a sha256,
not as bytes: the bundle is signed and carries the hash, the artifact store is
keyed by it, and `downloadArtifact` verifies it before the bytes are used. A
certificate cannot be swapped in transit without breaking the signature or the
hash — which matters more here than for any other file, because these bytes decide
what the device will trust.

⚠️ **`uninstallAllUserCaCerts` is not used, and a test enforces that.** It is the
convenient call and the wrong one: it removes every user-installed anchor,
including ones a person added for their own reasons. Removal works from a record
of what ATLAS installed, keyed by sha256 — the rule `hiddenByPolicy` follows for
packages.

⚠️ **The certificate bytes are kept on the device**, because `uninstallCaCert`
names a certificate **by its content** rather than by an alias. Without them there
is no way to remove one specific anchor — only the API that removes everybody's.

⚠️ **An empty list is sent, never a missing key.** The agent has to be *told* to
trust nothing so it can remove what it installed; a missing section would read as
"no instruction" and leave a revoked authority in place. The applier therefore
runs on every reconcile, like the trackers.

#### ⚠️ C2 as scoped would build something nothing accepts (2026-09-09)

The mechanism is sound and mostly assembly — `generateKeyPair` under a policy
alias, a CSR from the existing `createCsrPem` helper, `setKeyPairCertificate` to
install the issued chain against the key that never left the device. All four APIs
confirmed present, and `installKeyPair` is not even needed.

**The problem is the issuer, not the mechanism.** A certificate signed by *our*
CA is meaningless to the things that ask a device for one:

* **Wi-Fi EAP** wants a certificate the RADIUS server's CA issued.
* **A corporate service** wants one its own CA issued.
* **ATAK** reads `.p12` files from disk, not the Android keystore — so even a
  perfect keystore certificate is invisible to it (`ARCHITECTURE.md`).

Our CA authenticates devices *to this server*, and a policy-issued certificate
would not even do that: `deps.py` looks the serial up in `device_certificate` and
rejects anything unregistered, so there is no privilege leak — but equally, no
consumer. **We would ship a feature whose output nothing on the network accepts.**

**The three real options, and only one of them is new work worth doing:**

| | What it gives | Cost |
|---|---|---|
| **SCEP** | Enrols against the **operator's own** CA, key generated on the device and never leaving it | A SCEP client in the agent — it is HTTP, and the CSR half already exists |
| **PKCS#12 upload** | Works with any existing CA today | ⚠️ Private key material transits and rests on this server — R8 multiplied by every certificate |
| **Our CA** | Useful only for services we control | Small, and currently nothing consumes it |

**Operator chose PKCS#12** (2026-09-09), knowing the key-handling cost: their
certificates come from a TAK admin as `.p12` files, not from a CA that speaks
SCEP.

#### ⚠️ A PKCS#12 must not go through the artifact store

The artifact endpoint's own docstring says why it is safe, and the reasoning does
not survive contact with a private key:

> Any enrolled device may fetch any known artifact. The digest is unguessable and
> the content is **an installable an operator chose to publish**, so the useful
> boundary is enrollment rather than per-device authorization.

That is right for an APK or a wallpaper and wrong for key material. Any enrolled
device — or anyone who compromises one — could fetch another device's private key
given the digest, and digests travel in bundles. **So certificates get their own
per-device path**, checked against that device's effective policy, rather than
riding the shared store.

Nor does it belong inline in the desired-state bundle: the agent *caches* the
bundle (`cachedDesiredState`), so the key would sit in the agent's preferences
long after it was installed into the keystore where it belongs.

#### The design

1. **At rest**: the `.p12` is sealed with `TokenVault` (Fernet), the same
   mechanism protecting enrollment token secrets (D74) — and inheriting R12's
   caveat, that `pki/token_vault.key` plus a database dump opens both.
2. **The password is sealed separately** and never stored beside the blob in
   plaintext.
3. **Delivery**: `GET /api/v1/device/certificates/{id}` — mTLS, and the server
   confirms *this* device's resolved policy actually names that certificate. The
   agent fetches, installs, and keeps nothing.
4. **On the device**: `installKeyPair(admin, privateKey, chain, alias, …)` — the
   one place `installKeyPair` is the right call rather than
   `setKeyPairCertificate`, because here the key really does arrive from outside.
5. **Removal**: `removeKeyPair` for aliases this agent installed, driven
   declaratively like the trust anchors, and re-asserted with `hasKeyPair` for the
   reason C1 learned on hardware — the user can undo it.

⚠️ **This is the largest new exposure in the system**, and it is worth stating
plainly rather than burying: before this, the only private keys here were the
CA's and each device's own, generated on the device and never transmitted. This
puts operator-supplied keys on the server. The mitigations above are real, but
the honest summary is that **R8's blast radius now includes every uploaded
certificate**, and SCEP remains the version of this that has no such cost.

✅ **SCEP is the same key-safety story as C2 against a CA that actually matters**,
and it was already the next sub-topic. **Recommendation: make SCEP the client
certificate story and drop "our CA" from the plan.** Raised before building
rather than after, because the mechanism working says nothing about anyone
accepting the result.

✅ **Verified on hardware (`SM-X828U`, agent 0.52.0), install *and* removal.** A
throwaway CA was generated — private key held in memory and never written, so the
anchor is inert — uploaded, assigned, removed and re-instated. The device's log:

```
13:45:09 I/CertificateApplier: trusted CA installed: ATLAS W112 Verification CA
13:48:58 I/CertificateApplier: trusted CA removed: 479243d5ce1218b6…
```

Compliant with **no apply errors** throughout, which is what says both platform
calls returned true. Recorded in the Android reference §6.

✅ **Operator checked the device (2026-09-09):** the certificate installed,
Android showed a *"CA cert installed"* notification, and **the user can remove it
from Settings**.

⚠️ **That third answer found a real bug**, and it is the kind no test here would
have caught. The applier skipped anything already in its own `installedByUs`
record — so a user deleting the anchor would have left ATLAS believing trust was
in place while the device had dropped it, with the policy silently not holding.
Fixed in agent 0.53.0: `hasCaCertInstalled` asks the **device** on every reconcile
and restores what has gone, the same self-healing the passcode has and for the
same reason — the platform gives the user a way to undo it. The console now says
trust is **maintained rather than enforced**, and that a device can be without an
anchor for up to a check-in cycle.

✅ **The self-heal is confirmed on hardware.** The operator deleted the CA from
Settings and it came back on the next check-in.

✅ **And the window can be closed outright, without Knox.**
`DISALLOW_CONFIG_CREDENTIALS` is an ordinary Device Owner user restriction —
*"Specifies if a user is disallowed from configuring user credentials"* — now
exposed as **Restrictions ▸ Credential configuration** (agent 0.54.0). Denying it
stops the user reaching the credentials screen at all, so a policy anchor cannot
be deleted rather than merely being restored a cycle later.

⚠️ **It is not a per-certificate lock**, and the field says so: it blocks the
whole credentials screen, so the user cannot manage their own certificates
either. The Certificates page points at it rather than duplicating the control —
an operator asking "can I stop them deleting it" is looking at Certificates, and
the answer lives under Restrictions.

⚠️ **Left installed for the operator to inspect**, labelled *"Delete me after
testing"* and expiring in two days regardless. Policy `5064a51b`, file
`d1bf9815`. What still needs a human's eyes: whether Android shows a
*"network may be monitored"* notice, and whether the user can delete the anchor
from Settings — neither is visible from the server.

#### Steps

1. `app/services/geocoding.py` — forward lookup, configurable endpoint, a real
   `User-Agent` (Nominatim's usage policy requires one), a short timeout, and a
   cache so repeat searches do not re-ask.
2. An admin setting for the endpoint, beside the existing tile setting.
3. A console endpoint the editor calls, so the browser never reaches the geocoder.
4. The editor: one shared map under the fence rows showing **every** fence as a
   circle, the selected row highlighted; click the map to place the selected
   fence; the circle follows the radius field live.
5. Address box with a **Find** button, filling the coordinates of the selected row.
6. Tests, deploy, verify.

⚠️ **One map for all rows, not a map per row.** Per-row maps would mean N Leaflet
instances in one form, each measuring itself wrong while its row is hidden behind
a tab — the grey-box failure `atlas-map.js` already carries a note about. A single
map that follows the selected row also answers the question an operator actually
has, which is whether their fences overlap.

### ⏳ W112 — Security ▸ Certificates (C1 ✅ trust anchors)

Operator, 2026-09-09, after asking which of the Security sub-topics need Knox:
scope Certificates as the next chunk. Four of the five need no Knox at all
(recorded in the Android reference); this is the one worth building first,
because the machinery already exists and ATAK deployments actually need it.

#### This section is general MDM, not ATAK

Operator, 2026-09-09: *"the section for: certificates · scep · global http proxy ·
web content filtering · os updates would be for general MDM, not ATAK."*

So the target is ordinary fleet management — Wi-Fi EAP, browser and app trust,
VPN, and apps that ask Android for a client certificate. ATLAS is a device
management product that happens to be good at ATAK, and this category is one of
the places that distinction is real.

⚠️ **One footnote, kept because it will otherwise be discovered the hard way.**
ATAK does *not* read the Android trust store: `docs/ARCHITECTURE.md` records that
its `.p12` certs "are all file pushes into `/sdcard/atak/…`", pointed at by ATAK's
own preferences — which FILES and ATAK_CONFIG already deliver today. Nothing in
this chunk changes that, and the console should not let anyone infer otherwise:
installing a TAK server CA here and expecting ATAK to trust it produces a device
that looks configured and an ATAK that cannot connect, with nothing saying why.

#### The APIs, confirmed present in the framework source

`installCaCert`, `uninstallCaCert`, `getInstalledCaCerts`, `hasCaCertInstalled`,
`uninstallAllUserCaCerts`, `installKeyPair`, `removeKeyPair`, `generateKeyPair`,
and `setDelegatedScopes(DELEGATION_CERT_INSTALL)` for handing installation to
another app.

⚠️ **`uninstallAllUserCaCerts` is the trap in that list.** It is the convenient
call and it is the wrong one: it removes every user-installed anchor, including
the ones a person put there themselves. Release has to work from a record of what
*we* installed — the rule `hiddenByPolicy` already follows for packages, and
`getInstalledCaCerts` plus `hasCaCertInstalled` make it checkable rather than
remembered.

#### ⚠️ Two ways to get a client certificate onto a device, and they are not equal

* **Upload a PKCS#12.** The operator supplies a `.p12` and its password; the
  server stores both and the agent calls `installKeyPair`. **Private key material
  transits and then rests on this server** — the thing R8 already says about
  `pki/ca.key`, now multiplied by every device certificate an operator uploads.
* **Generate on the device.** `generateKeyPair` makes the key in hardware, the
  agent sends a CSR, our CA signs it, `installKeyPair` installs the chain. **The
  private key never leaves the device**, and this is not new ground —
  `DeviceIdentity.kt` already does exactly this for the agent's own identity,
  StrongBox included.

**The second is strictly better and mostly built. The first is what an operator
with an existing enterprise CA will need anyway.** Recommendation: build
generate-on-device first and treat PKCS#12 upload as a separate, later decision
with its own security note — not as the default path.

#### Steps

1. **Verify on hardware before designing around it**: that a Device-Owner
   `installCaCert` actually lands in the trust store on `SM-X520`, whether the
   user can remove it, and what warning Android shows. The reference records
   nothing about this yet, and §6 says not to reason from recollection.
2. `CERTIFICATES` policy spec: trust anchors (PEM/DER, from the Content library)
   and client certificates (generate-on-device, named by alias and purpose).
3. Server: issue device certificates from the existing CA on CSR, reusing
   `app/security/ca.py` rather than a second issuing path.
4. Agent: `installCaCert` / `uninstallCaCert`, `generateKeyPair` +
   `installKeyPair`, all driven declaratively.
5. Console: the Security category wired, said plainly as device-level trust —
   with a line making clear it is not what configures ATAK.
6. Tests both sides, then build, deploy, verify.

⚠️ **Absent must mean removed, and it matters more here than anywhere.** Every
other latching setting in this system leaves a stale *configuration* behind; a
trust anchor left installed by a policy that no longer applies is a device that
still trusts a CA the operator revoked. `getInstalledCaCerts` makes the current
state readable, so the applier can drive it declaratively the way `applyPassword`
does (R14) — and the same rule applies: only remove what **we** installed, never
everything currently present, or ATLAS starts deleting the user's own anchors.

⚠️ **A device certificate is an identity, so its lifecycle is not a policy's.**
Unassigning a policy should stop *issuing*, but revoking what was issued is a
separate act with separate consequences. Worth settling before building, not
after: the same distinction W104 drew between retiring a device and wiping it.

### ✅ W111 — A trusted area that really does suspend the passcode

Operator, 2026-09-09: *"can we have it remove a password policy that was placed by
the web portal? if we set the standard password policy, could this setting not
disable the same policy?… can it suspend a previous DPC set password policy, then
re-enable it when the geofence policy has been breached?"*

⚠️ **This reframing is what made it possible.** My first answer was no, and it
was right about the wrong question: `setKeyguardDisabled` cannot bypass a PIN, and
Knox cannot either (both recorded). But **suspending the policy we ourselves set**
is a different act, and AOSP allows it:

> Calling with a `null` or empty password will clear any existing PIN, pattern or
> password **if the current password constraints allow it**.

So: relax the constraints, *then* clear. Reverse the order and the clear is
refused and returns `false`.

✅ **The risk that would have bricked the fleet is ruled out.** The device identity
key is built with `setUserAuthenticationRequired(false)`, so it is **not** bound to
the lock credential and survives the passcode being cleared and restored. Had that
been `true`, the first fence to fire would have destroyed every device's identity.
Checked before answering, not after building.

✅ **Restoring is free.** `applyPassword` is declarative (R14) and re-asserts
`set_password` on every reconcile, so leaving the fence puts the passcode back
with no new code — the same mechanism that already fights the user changing it.

#### Conditions, each of which the console must enforce

1. **ATLAS must own the passcode.** Only a profile whose PASSWORD policy sets
   `set_password` may carry an *off* fence — that is the only case where the agent
   knows what to restore. Clearing a passcode the *user* chose would lock them out
   of their own credential with nothing to put back.
2. **The reset token must be active**, which §6c says happens cleanly only when it
   is provisioned before any passcode exists — i.e. at enrolment.
3. `FEATURE_SECURE_LOCK_SCREEN`, which these tablets have.

#### ⚠️ Three windows where a device could sit unlocked outside the zone

All three fail **secure** — the cost is a device that occasionally re-locks when it
need not, against the alternative of a tablet unlocked somewhere we cannot place.

| Window | Answer |
|---|---|
| Leaving the zone | The passcode returns on the next fix, so up to one reporting interval late. The per-fence interval override exists for this. |
| **GPS lost inside the zone** | A stale fix is treated as **outside**. If we cannot confirm the device is in the trusted area, the passcode comes back. |
| Reboot | No fence is active until the first fix, so the policy's passcode applies. |

###### ✅ Complete (2026-09-09) — agent 0.51.0 (versionCode 96), 1329 server tests

Live: the editor offers **Not managed / Off — trusted area / On — require a
lock**, and a lone trusted fence is refused with *"suspends the passcode, so this
profile's Password policy has to set one."*

**How suspension actually works, and why the order is load-bearing.** An *off*
fence hands `applyPassword` an **empty** spec — which is not "skip it". R14 made
that applier declarative: every field is driven to a definite value each reconcile
and absent means permissive, so an empty spec is what actively *releases* the
constraints. Only then can the passcode be cleared, because AOSP clears one
*"if the current password constraints allow it"*. `clearPasscodeForTrustedArea`
therefore runs **after** `apply`, in the same reconcile, and a test asserts that
ordering by index rather than by hope.

**Restoring needed no code at all.** `applyPassword` re-asserts `set_password` on
every reconcile — the same mechanism that already fights a user changing it — so
leaving the fence puts the passcode back by itself.

⚠️ **`ON` beats `OFF` beats `NONE`.** Overlapping a trusted area with a fence that
requires a lock is exactly how a secure zone would be silently unlocked by a
neighbouring one. Asserted, and asserted order-independent.

⚠️ **A stale fix is treated as outside.** Every other fence action is safe to hold
on an old position — a radio stays off and the worst case is inconvenience.
Suspending a passcode is not: a device that lost GPS indoors, or left the zone in
a bag, would sit unlocked on a fix from hours ago with nothing looking wrong in
the console. Ten minutes, **deliberately not the reporting interval** — a long
interval set for battery must not buy a longer unlocked window.

⚠️ **An unreadable stored state reads as `NONE`.** The safe end: a device whose
setting cannot be parsed keeps its passcode.

⚠️ **The old boolean is still read.** Stored specs are not migrated when a model
changes, and every fence written before this would otherwise have failed
validation on its next resolve — surfacing as a device that cannot get its policy,
with nothing in the error mentioning geofences. Covered on both sides.

**Gated where it must be:** *off* is accepted only on a profile whose PASSWORD
policy **sets a passcode**, because that passcode is the thing restored. Removing
that Password section is refused while a fence depends on it — the W106 C4a trap,
one level subtler.

#### Steps

1. Spec: `password_enforced` (bool) becomes `password` (none/off/on), reading the
   old boolean so stored policies keep working.
2. Resolve most-restrictive: **on beats off beats none**.
3. `fence_rules`: *on* needs a PASSWORD policy; *off* needs one that sets a
   passcode.
4. Agent: an *off* fence blanks the PASSWORD spec and clears the passcode; the
   stale-fix guard; restore happens by itself.
5. Tests both sides, then build, deploy and verify on hardware.

### ✅ W110 — Address suggestions as you type

Operator, 2026-09-09: *"some mapping services have a system where it will popup
matching addresses as you type… is this a service that we can implement that is
provided at no cost? i dont want anything hosted locally."*

✅ **Yes: komoot's public Photon instance.** Free, keyless, hosted, and type-ahead
is its headline feature — which is precisely what Nominatim's usage policy
forbids, and why W109 shipped a button instead.

###### ⚠️ W110c — the suggestions stop at the street (2026-09-09)

*"its still not getting the numerics."* Picking a suggestion placed *Upper Drive,
Corona* rather than *110 Upper Drive*.

✅ **The house number is in OpenStreetMap. Only Photon's index lacks it.** Checked
rather than assumed, and the two services genuinely disagree about what they hold:

| | |
|---|---|
| Photon, `Upper Drive Corona California` | 3 features, **no house numbers at all** |
| Nominatim, `110 upper drive, corona` | `110, Upper Drive, Corona, Riverside County, California, 92882` at `33.8351825, -117.5786927` |

So the Find button was already returning the exact address; the *suggestion* path
was the one stopping at the street, and clicking a suggestion is what an operator
naturally does.

✅ **A pick now upgrades itself.** The street is placed immediately — no waiting —
and then one Nominatim lookup runs to see whether it can do better. That is a
single request on an explicit click, which is a press rather than autocomplete and
so stays inside Nominatim's usage policy. Nothing is substituted silently: the
marker moves only if the answer really begins with the number that was typed, and
the message says where it ended up. A failed refinement is swallowed — the street
placement is already visible on the map and is not worth a complaint.

⚠️ **`"1100 Main St"` starts with the characters of `"110"`.** A plain `indexOf`
prefix check would have decided the suggestion already carried the number and
skipped the refinement entirely — the exact case the feature exists for.

⚠️ **And the first version of that check was broken by escaping.** Building a
regex from a string needs `"\D"` to mean `\D`; written with one backslash it
silently becomes the letter *D*, so `^110(D|$)` would have matched almost nothing.
The file carried that for one commit. It is now character comparison, which cannot
be escaped wrong — and a test forbids `RegExp` in that function.

**A second over-broad assertion, of the same shape as W109a's.** A test banned the
*word* "nominatim" from the picker script to prove the browser never calls it
directly — and then failed on a comment explaining which service holds what. It
now checks the fetch **URLs** are same-origin, which is the thing that matters.
A test that bans a word bans talking about it.

**1319 server tests.**

###### ⚠️ W110b — Ontario for a California address (2026-09-09)

*"110 w upper dr, corona ca"* suggested **Upper Canada Drive, Kitchener,
Ontario**. Diagnosed by isolating the tokens rather than guessing, all inside one
southern California box:

| Typed | Photon |
|---|---|
| `w upper dr corona` | ✅ Upper Drive, Corona CA |
| `110 upper dr corona` | ✅ Upper Drive, Corona CA |
| `upper dr corona ca` | ✅ Upper Drive, Corona CA — so **"ca" was never the problem** |
| **`110 w upper dr corona`** | ❌ **nothing at all** |

⚠️ **Photon requires every token to match.** Corona has an *Upper Drive* and an
*East Upper Drive* but no *West* one, so no record holds both `110` and `w`. The
house number alone is fine; the directional alone is fine; together they
over-constrain to zero.

⚠️ **The wrong answer came from my fallback, not from the box.** W110a made the
empty box fall straight through to a worldwide search — which found Upper Canada
Drive and presented it confidently at the top of the list. **A precise-looking
answer on the wrong continent is worse than no answer**, because the operator
reads the first row as the result.

✅ **Fixed by ordering: loosen the query before widening the map.** The ladder is
now (1) query in the box, (2) query minus a leading house number, still in the
box, (3) query with no box, (4) both loosened. Step 2 is what rescues this, and it
never leaves southern California to do it. Dropping the number costs nothing that
matters: a geofence has a radius in the hundreds of metres, so street-level
placement is already finer than the fence itself.

Verified live: the operator's exact string now returns *East Upper Drive, Corona,
California* and *Upper Drive, Corona, California*; `"Berlin Germany"` inside a
California box still reaches Berlin.

**1315 server tests.**

###### ⚠️ W110a — unreadable, and answering Nova Scotia (2026-09-09)

A screenshot from the operator. Two faults, one of which no test could ever have
caught and one of which every test had already been told about.

**1. White text on a near-white panel.** The suggestion list was illegible. The
global `button` rule sets `color: var(--accent-ink)` — white — for the filled blue
buttons everywhere else; the new rule overrode the *background* to a pale panel
and never touched the foreground. ⚠️ **A control that changes its background must
set its foreground.** No test can see, so this could only ever arrive as a
screenshot; there is now one asserting the rule sets both.

**2. The suggestions really were answering with Nova Scotia**, exactly as W110
documented and shipped anyway. Documenting a weakness is not the same as
accepting it, and seeing it in front of the operator made that obvious.

✅ **A bounding box fixes what the bias could not.** `lat`/`lon` bias left
`"110 w upper d"` returning Nova Scotia at every `location_bias_scale` up to 5.
The same query inside the visible map's box returns only southern California. The
browser now sends `map.getBounds()` with every suggestion.

⚠️ **And the box is dropped when it finds nothing.** Constraining to the visible
map is right until somebody searches for a place they are not looking at:
`"Berlin Germany"` inside a California box returns **exactly zero** from Photon —
measured. A chooser that says "no matches" for a real city is worse than one that
answers less locally. Verified live: Berlin still resolves while a California box
is applied.

⚠️ **I walked into my own trap again.** The first verification ran `curl` right
after `docker compose up --build`, against a container still starting, and
reported both fixes missing. W109a records this exact lesson three entries above.
The deploy check now polls the endpoint until it answers `200` rather than
checking that a file exists inside the image — a file being present is not a
service being up.

**1311 server tests.**

#### ⚠️ Two services, because measurement said so

Photon was tested against the operator's own address before being adopted:

| Typed | Photon | Nominatim |
|---|---|---|
| `Cor` | ✅ Corona, California (with bias) | ✗ policy forbids type-ahead |
| `Upper Dr Corona` | ✅ three Upper Drives in Corona CA | ✅ |
| `110 W Upper` | ❌ **Nova Scotia**, at every `location_bias_scale` up to 5 | ✅ |

Photon lets a house number dominate a partial street name, and no amount of bias
fixes it. So **Photon answers while you type, Nominatim answers the press** — each
where it is strong. A single service for both would be worse at one of the jobs.

⚠️ **Bias is what makes suggestions useful at all.** Unbiased, `"Cor"` returns a
global list; biased to the map's current centre it returns Corona, California. The
browser sends the map centre with every suggestion request.

#### What the type-ahead does about being type-ahead

It is more disclosure than a button — partial strings, not just finished ones —
and it is treated as such rather than waved through:

* **Debounced at 300 ms**, so it is a few requests rather than one per keypress.
  komoot's terms are *"please be fair — extensive usage will be throttled"*.
* **A three-character floor.** Two characters match half the planet, and every one
  of them is a query somebody else sees.
* ⚠️ **Sequence-guarded.** Replies arrive out of order, and without it a slow
  answer for `"Cor"` lands after the fast one for `"Corona"` and replaces it.
* **Silent on failure.** It runs on almost every keystroke; an error banner per
  character would bury the form in complaints about a convenience. The Find button
  is where a broken lookup is reported, once, where it can be read.
* **Still proxied**, so the browser never contacts komoot and the operator's own
  address is never disclosed to it.

⚠️ **No availability guarantee.** komoot calls it a demo service and reserves the
right to change or withdraw it. Suggestions failing costs convenience only:
`Find` still works, and coordinates stay typeable. `Admin → Location → Address
suggestions URL` points it elsewhere, or at something unreachable to turn it off.

**A W109 test was rewritten rather than deleted.** It asserted the picker never
searches while typing. That rule was really *"never send type-ahead to the service
that forbids it"*, which is still true — so the test now asserts the suggest path
never reaches the Nominatim-backed endpoint.

⚠️ **GeoJSON is `[longitude, latitude]`** — the reverse of every other coordinate
in this codebase. Read the other way round, anywhere in the Americas lands in the
sea off West Africa. Tested with numbers chosen so a swap is unmistakable.

**1306 server tests.** Verified live: `"Upper Dr Coro"` → three Upper Drives in
Corona, California; `"Cor"` → Corona; `"Co"` → asks nobody.

###### ⚠️ W109a — the field found it in an hour (2026-09-09)

Operator: *"I typed in an address of 110 West upper Corona California, when I
clicked find nothing happened and it said you must enter address in the form
first."* Three separate faults behind one report.

**1. Find refused when there were no fence rows.** A new policy has none, so the
first thing anyone does is type an address — and got *"Add a geofence row
first."* That is the form's internal order of operations leaking out as an
instruction; nobody opens the panel intending to press **Add**, then type. Find
and a map click now create the first row themselves, by clicking the existing Add
button rather than cloning the template, so one code path still knows how a row is
built. **This is the whole bug the operator hit** — the other two were waiting
behind it.

**2. That address does not geocode.** `110 West upper Corona California` returns
nothing; `110 W Upper Dr, Corona CA` finds Upper Drive. Nominatim wants the street
*type*. The no-match message now says so with that exact shape, rather than the
useless *"try a simpler form"* it had.

**3. ⚠️ Several places matched, and the first was taken silently.** `Upper Dr,
Corona CA` returns more than one Upper Drive. The original code placed the fence
at `results[0]` and mentioned *"best of N matches"* in passing — which is how a
geofence lands on the right-named road in the wrong town, with **nothing
downstream able to flag it**, because the coordinates are perfectly valid. More
than one match is now offered as a list to choose from. A found place also names
an unnamed fence, and never overwrites a name the operator typed.

⚠️ **Two verification lessons, both mine.** A `grep -c` returning 0 exits non-zero
and killed a `set -e` deploy script mid-check. And an immediately-following `curl`
caught the container mid-restart and reported the new script as missing when it
was fine — the second run showed 3 matches and a byte-identical size. A check run
against a service that is still coming up is not a check.

**1296 server tests.**

###### Geocoding provider: settled 2026-09-09

The operator asked to "continue with the reverse geocoding — type in address and
hit submit and have it register those coordinates on the geofence", and raised not
wanting to pay for a service, suggesting `openaddresses.io`.

Three things resolved it, and none of them was new code:

1. **It already existed.** That description is *forward* geocoding, which W109
   shipped. Verified live: `1600 Pennsylvania Avenue NW` → `38.8976387,
   -77.0365525`. *Reverse* geocoding — coordinates to address, on the device map —
   remains deliberately unbuilt (C3), for the disclosure reason recorded there.
2. **Nothing is being paid.** Nominatim needs no key, account or billing. Its
   constraints are a usage policy, which is why the lookup is a button rather than
   an autocomplete.
3. ⚠️ **`openaddresses.io` cannot do this job.** It is a *downloadable dataset*,
   not a hosted API — "parse & import into a database... or use for geocoding".
   There is no endpoint to query, so it is not a swap for Nominatim; it is raw
   material for a geocoder you run yourself.

**Decision: stay on Nominatim.** Self-hosting was offered (Photon is lightest;
Pelias is the one that ingests OpenAddresses) and declined — *"no. as is will
work"*. If that changes, **no code change is needed**: `Admin → Location → Address
lookup URL` already points the console anywhere.

###### ✅ Complete (2026-09-09) — 1289 server tests, verified live

`"Denver Colorado"` → `39.7392364, -104.984862` through the console's own
endpoint, and the editor renders with the picker, Leaflet and the deployment's
real tile configuration.

⚠️ **A Jinja macro imported from another template cannot see the render
context**, and this cost the most time here. `geofence_tiles` was in the context,
in the caller and in `policy_subform` — and still rendered empty, because the
dispatch that calls `_geofences` lives two macros deeper (`_control` →
`_live_control`). That is exactly why `app_packages` is threaded as a parameter
through the same chain; the existing code already had the answer and it took a
wrong theory about macro scoping to see it. **A new control needing page data must
be threaded the whole way down, not merely into `policy_subform`.**

⚠️ **The mistake that nearly hid a working feature.** A first verification
reported the picker, the tiles *and the pre-existing kiosk app list* all missing.
The page was fine — a shell variable had come back empty inside plink's nested
quoting, so every `grep -c` ran against nothing. The tell was that something known
to work reported as broken too; a check that says an untouched feature has
vanished is a check that is lying. Direct `curl | grep` per line, no variables.

⚠️ **The address box searches on a press, never as you type.** An autocomplete
would send a query per keystroke — "f", "fo", "for" — leaking far more than the
finished string, and Nominatim's usage policy forbids exactly that. Bound to the
button and to Enter, and Enter is intercepted so it does not submit the whole
policy form, which is what a lone text input in a form does by default and would
be a surprising way to publish a half-finished policy. Asserted in a test that
reads the script.

⚠️ **Proxied through the server, not called from the browser.** The operator's
own address is never disclosed to the geocoder — only this server's — and the
endpoint stays a deployment setting rather than something baked into a script.
Admin-only: it spends a shared, rate-limited third-party service.

**Unreachable and not-found stay distinct.** "The service is down" and "that
address does not exist" send an operator to entirely different places; collapsing
them has someone retyping a perfectly good address five times.

**One map for every fence**, with the selected row's circle highlighted and only
that one draggable — dragging an unselected fence would move something the
operator is not looking at. The fields remain the source of truth: the map writes
into them and reads back, so typing, dragging and finding all converge, and the
form submits exactly what is drawn.

**Chrome: closed, not an issue** (operator, 2026-09-09). For the record, the
package row `com.android.chrome` ("Chrome (Play)") still exists with no version
behind it, so it appears in pickers with nothing installable. The operator is not
concerned; do not raise it again.

⚠️ **The geocoder must not become a required dependency.** Coordinates stay
typeable, and a failed or unconfigured lookup leaves the form exactly as it was
with a message — an operator with no internet must still be able to draw a fence.

### ✅ W108 — Battery, IMEI and phone number on the device page

Operator, 2026-09-08: *"on the device details, I want to see battery level, imei
(if available, imei 1 and 2), and phone number (if available)."*

**Reported attributes, not identifiers.** `IdentifierKind` exists to *match* a
device to a record across re-enrolment (D24); putting IMEI in there would change
matching semantics for every device. These belong beside `supported_abis` and
`sdk_int` — things a device tells us about itself at check-in (W96).

✅ **The permission question is already settled.** §6a-ii records that a Device
Owner holding **ordinary `READ_PHONE_STATE`** reads device identifiers on
Android 16, verified on `SM-X520` — contradicting the widely repeated claim that
`READ_PRIVILEGED_PHONE_STATE` is required. The agent already declares and
self-grants it, so IMEI needs no new permission.

#### ⚠️ Three kinds of "no IMEI", and they are not the same thing

The operator's *"if available"* is doing real work here, and a single blank would
throw away the distinction:

| What is true | What the page must say |
|---|---|
| The device has no cellular radio — `SM-X520` is Wi-Fi-only | **No cellular radio.** Definitive; stop looking. |
| It has one, but the value could not be read | **Not readable**, which is a permission or platform problem worth chasing. |
| An agent too old to report any of this | **Not reported**, which is an agent version problem. |

So the agent reports whether the device has telephony **at all**, separately from
the values. Without that flag the first two are indistinguishable, and an operator
would go hunting for a permission bug on a tablet that simply has no modem.

#### Steps

1. Migration and model: `battery_level`, `battery_charging`, `imei2`,
   `phone_number`, `has_telephony`.
2. Check-in schema and handler — absent still means "said nothing", never "erase"
   (the W32 rule that `atak_version` and `supported_abis` already follow).
3. Agent: battery from `BatteryManager`, IMEI per SIM slot, line number.
4. Device page: show them, and distinguish the three absences above.
5. Tests, build, deploy, verify.

⚠️ **A phone number is very often absent even on a cellular device**, because it
lives on the SIM only if the carrier provisioned it there. That is normal, not a
fault, and the page should not imply otherwise.

###### ✅ Complete (2026-09-08) — agent 0.50.0 (versionCode 95), 1273 server tests

`SM-X520` reported `battery=65 charging=False telephony=False`, and the page shows
**65%** with an "as of" and **"No cellular radio"** — with neither of the other two
messages present. That is the design working: a Wi-Fi-only tablet is the exact
case the third state exists for, and it is what most of this fleet is.

⚠️ **`is not none`, not truthiness, for the battery.** A flat device reports `0`,
and `{% if device.battery_level %}` would render that as "not reported" — hiding
precisely the reading somebody is looking for when they ask why a device stopped
checking in. Tested with a real 0.

⚠️ **Battery is the one field where the newest report always wins.** Everything
else here follows the W32 rule (absent means "said nothing", never "erase") so a
downgraded agent cannot blank an IMEI the operator can act on. Battery is volatile
and a fall to 0 is the most important reading it will ever send.

⚠️ **No new permission was needed for IMEI**, and §6a-ii is why: a Device Owner
holding **ordinary `READ_PHONE_STATE`** reads device identifiers on Android 16 —
verified on hardware in W23 against the widely repeated claim that
`READ_PRIVILEGED_PHONE_STATE` is required. `READ_PHONE_NUMBERS` was added for the
line number, which API 30 split out of `READ_PHONE_STATE`.

⚠️ **Each SIM slot is read in its own `runCatching`.** `getImei(slot)` throws for
a slot that does not exist, and one exception must not cost the other slot's value
— a read that gave up after slot 0 failed is how a single-SIM device would report
nothing at all.

⚠️ **`BATTERY_PROPERTY_CAPACITY` returns `Integer.MIN_VALUE`, not `-1`,** when
the device has nothing to give. A `level >= 0` guard would pass garbage straight
through; the check is `in 0..100`.

**A flaky test to be aware of, not caused by this work:**
`test_upload_records_identity_read_from_the_file` errored once in a full run and
passed alone, in its own file, and on a clean re-run. Nothing here touches
packages. It looks like a Windows temp-directory teardown race — recorded so the
next session does not chase it as a regression from W108.

⚠️ **Battery is only meaningful with an "as of".** It is shown against
`last_checkin_at` rather than as a bare number — a device that has been dark for a
day reporting 4% is a different situation from one reporting 4% a minute ago, and
the bare figure reads as current.

### ✅ W107 — Find my device, and lock the screen

Operator, 2026-09-08: *"let's add the ability to remotely ping the device with
'find my device' type call. this should be a button in the device profile on the
webUI. I also want a 'lock screen' button in the webUI. both are features in the
GitHub repo that the tracker was from."*

In `EUD_Remote_Assist_Portal` these are an **Actions** panel on the device page:
*Play Sound on Device* (`TRIGGER_PING`) and *Lock Device* (`LOCK_DEVICE`, behind a
confirm modal).

#### Half of this already exists

| Piece | State |
|---|---|
| `CommandType.LOCK` | ✅ already in the enum |
| Agent `LockCommandHandler` — `lockNow()`, registered in the dispatcher | ✅ |
| A button for it in the console | ❌ |
| Ping — command type, agent handler, button | ❌ all of it |

So **lock is a console change only, no agent release**, and ping is the real work.

#### Steps

1. `CommandType.PING`, and whatever allowlist the command API enforces.
2. Agent `PingCommandHandler`.
3. An **Actions** panel on the device page: *Play sound*, *Lock screen*, and the
   existing *Locate* which is currently reachable only through the API.
4. Tests both sides.
5. Build, publish, deploy, verify on hardware.

⚠️ **A find-my-device sound has to be loud on a silent device, and stoppable by
whoever finds it.** Those pull in opposite directions and both matter:

* Played on the normal media stream it is inaudible on exactly the device someone
  is hunting for — silenced, in a bag. So: `STREAM_ALARM`, which rings through
  silent mode, with the volume raised for the duration and **put back afterwards**.
* Left to ring indefinitely it is a tablet screaming in a drawer that nobody can
  stop without the password. So: a bounded duration, and an on-screen way to stop
  it. `AlertOverlay` already exists for this kind of thing.

###### ✅ Complete (2026-09-08) — agent 0.49.0 (versionCode 94), 1263 server tests

Verified on `SM-X520`, end to end:

```
23:27:00 I/CommandDispatcher: executing ping (9a76cf7e…)
23:27:00 I/DeviceAnnouncer:   ping: alarm volume 11 -> 15
23:27:00 I/DeviceAnnouncer:   ping sounding
23:27:00 I/AlertOverlay:      alert overlay shown: Locating this device
23:27:30 I/DeviceAnnouncer:   ping finished; alarm volume restored to 11
```

⚠️ **The restore line is the one that matters.** Raising the alarm stream and
leaving it raised would mean an operator's ping silently reconfigured the device
— the next alarm the user set would go off at full volume, and nothing on the
tablet or in the console would connect the two. It goes back to exactly the 11 it
came from, on the timer *or* on the Stop button, whichever happens first.

⚠️ **`STREAM_ALARM`, not the media or notification stream.** The tablet somebody
is hunting for is the one that is silenced and in a bag; a notification tone is
precisely what that device suppresses. The console says so beside the button,
because an operator pressing it on a silenced tablet would otherwise doubt it
worked.

⚠️ **Bounded and stoppable, both.** 30 seconds on a timer, plus an overlay whose
button ends it — a tablet ringing indefinitely in a drawer, unstoppable without
the password, is worse than one that is merely lost. `AlertOverlay.show` gained an
`onDismiss` callback for this, and it fires **once** (the button and the
auto-dismiss timer both route through it; running the cleanup twice would restore
a volume that had already been restored, over whatever the user had since chosen).
It also fires when the overlay cannot be drawn at all — otherwise a device without
the overlay permission would ring with no way to stop it.

⚠️ **The action route is an allowlist, not a `CommandType` lookup.** These are
form posts from a page an admin is already on; if the path segment named any
command in the enum, `wipe` would be one crafted URL away from a button captioned
"Play sound", and the request would look identical to a legitimate one in every
log. `POST /devices/{id}/action/wipe` returns **404**, asserted for five commands.

⚠️ **A ping expires in an hour — the shortest TTL in the table, asserted as
such.** It answers "where is this thing while I am standing in the room".
Delivered later it is a tablet shrieking in a bag with nobody nearby who knows
why, answering a question the operator settled long ago. Every other command here
is worth doing late; this one is not.

**Lock needed no agent work at all** — `CommandType.LOCK` and
`LockCommandHandler` already existed and were already registered; only the button
was missing. The page says plainly that on a device with no password this is
**only a swipe**, rather than implying a lost tablet has been secured.

**No migration:** `command_type` is a plain `varchar(24)` with no CHECK
constraint, so a new enum value needs none — confirmed against the live table
rather than assumed.

⚠️ **`lockNow()` on a device with no password is close to a no-op.** It drops to
the lock screen, which a swipe dismisses. The button should say so rather than
implying a device has been secured — the same honesty the geofence lock needed.

### ✅ W106 — Location tracking, geofencing, and a map

Operator, 2026-09-08: under **Tracking and fencing**, two sub-categories —
**Device location tracking** (reporting interval in minutes, 0 = disabled) and
**Geofencing** (a coordinate + radius; behaviour type Entry/Exit; password
enforced yes/no; wifi on/off/not managed; bluetooth on/off/not managed;
reporting interval override, 0 = no override). On the device page, a map showing
device location, duplicating how
[EUD_Remote_Assist_Portal](https://github.com/cfd2474/EUD_Remote_Assist_Portal)
displays locations. *"lets start with device location tracking."*

#### What already exists — more than expected

| Piece | State |
|---|---|
| `tracking_fencing` category with both sub-topics | ✅ already in `creator_catalog.py`, unwired placeholder |
| `ACCESS_FINE_LOCATION` / `_COARSE_LOCATION` in the manifest | ✅ |
| `PermissionRequirement.Location`, silently granted by the Device Owner | ✅ |
| `LocateCommandHandler` — lat, lon, accuracy, provider, fix time, **age** | ✅ on demand |
| Turning **Wi-Fi** on and off as Device Owner | ✅ verified on `SM-X520` (W72) |
| Turning **Bluetooth** on and off as Device Owner | ✅ `DeviceControls.setBluetoothEnabled` |
| Periodic reporting, storage, history, map, geofence evaluation | ❌ to build |

So every action the geofence needs is already reachable from code on the device.
What is missing is a **schedule**, somewhere to **put** the points, and a **map**.

#### ⚠️ What the reference project actually does — read before duplicating it

I read its source rather than its README, which does not cover this.

* **`web/src/components/DeviceMap.tsx`** — Leaflet, OpenStreetMap tiles, one
  marker, popup with a label, `zoom 14`, scroll-wheel zoom **off**.
* **`web/src/components/DeviceLocationPanel.tsx`** — above the map: reverse-geocoded
  **address**, **coordinates** to 5 decimal places, **GPS accuracy** as `±N m` or
  *"Not reported by device"*; below it a **Location history** link.
* **`web/src/pages/DeviceLocationHistory.tsx`** — a **From/To** range where
  **From is the *newer* bound** (`Now` or a calendar date) and **To is further
  back**, both at local midnight; `To` must be on or before `From`. Default range
  is now → 48 hours ago. Then a map of **numbered** markers, and a **Records**
  table (`#`, date/time, coordinates, accuracy) where clicking a row flies the map
  to that point at zoom 16 and highlights the marker. Empty range says
  *"No location points in this range."*; no records at all says *"no records"*.
  **Export all history** pulls the full unsampled set as CSV.
* **`server/src/services/locationHistory.ts`** — the downsampling, which is the
  part worth copying exactly:

  | Age of point | Kept |
  |---|---|
  | ≤ 2 h | **every point** |
  | ≤ 6 h | newest per 15 min |
  | ≤ 48 h | newest per 1 h |
  | ≤ 96 h | newest per 6 h |
  | older | newest per 24 h |

⚠️ **The reference project has no retention and deletes nothing.** Its
`telemetry_history` table has no purge, no TTL, and no cleanup job — I checked
`migrate.ts` and the whole `server/src` tree. The tiers above are a **display
downsample**, not a retention policy: every raw point is kept for ever and merely
*drawn* thinly once it is old. Duplicating the display is the operator's ask and
is worth doing; duplicating the storage behaviour is not, because a fleet
reporting every 15 minutes writes ~35k rows per device per year and the thing
being accumulated is *a year of where a named person went*. **This chunk adds a
real retention window with a default; the display tiers are copied exactly.**

⚠️ **Its reverse geocoding sends device coordinates to `nominatim.openstreetmap.org`**,
a third party, on every panel view (24 h in-memory cache). Map tiles go to
`tile.openstreetmap.org`, which reveals the viewport the same way. For a tactical
fleet this is a disclosure decision, not a detail — so tiles are configurable and
**reverse geocoding is off unless switched on**, rather than on by default.

#### Design decisions this chunk commits to

* **Points ride the check-in as a batch.** The device buffers fixes at its
  interval and flushes the backlog on the next check-in, so an offline device
  keeps its history instead of dropping it. Check-in is already 900 s — the same
  15 minutes the reference project uses as its default.
* **`recorded_at` and `received_at` are both stored.** The first is the device's
  fix time and can be wrong or stale; the second is ours. `LocateCommandHandler`
  already reports fix **age** for exactly this reason.
* **Entry/Exit is a *state*, not an edge.** The operator's words: *"Entry will be
  when the device is inside the geofence, exit is when device is outside."* So the
  actions hold while the condition holds and revert when it stops — which is also
  the only version that survives a reboot or a missed transition.
* **Geofences are evaluated on the device.** A fence that only works with a
  network is not a fence.

#### Chunk plan

| | | |
|---|---|---|
| **C1** | Storage, the tracking policy, and check-in ingestion | server only |
| **C2** | Agent: periodic reporting on the policy's interval | agent, needs an APK |
| **C3** | Console: the map on the device page, and the history page | server only |
| **C4** | Geofencing: policy spec + on-device evaluation | both |
| **C5** | Retention window, purge, and the admin setting | server only |

#### ✅ C1 — Storage, the tracking policy, and ingestion

1. Verify against `docs/ANDROID_PLATFORM_REFERENCE.md` (§6) how a Device Owner
   gets **background** location on API 36 — `ACCESS_BACKGROUND_LOCATION` vs a
   `foregroundServiceType="location"` service. **This gates C2, so it is answered
   before anything is built on the assumption that C2 is possible**, and written
   into the reference either way.
2. `device_locations` table + migration: device FK (cascade), lat, lon,
   `accuracy_m`, provider, `recorded_at`, `received_at`, `source`
   (`periodic` / `command` / `geofence`), indexed `(device_id, recorded_at DESC)`.
   Denormalised `last_*` columns on `devices` so the fleet list needs no join.
3. `LOCATION_TRACKING` policy spec — `reporting_interval_minutes`, 0 = disabled;
   wire the `tracking_fencing` category and put **location tracking above
   geofencing**, matching the operator's ordering elsewhere.
4. Extend `CheckinRequest` with an optional batch of points — absent means "an
   older agent said nothing", never "erase what we know" (the W32 rule).
5. Ingest service: reject impossible coordinates, clamp a batch size, update the
   denormalised `last_*`, and record `locate` command results as points too, so
   the existing on-demand command starts building history immediately.
6. Tests, then deploy. No agent change and no APK in C1.

###### ✅ Complete (2026-09-08) — 1201 server tests, server-side only

**Step 1 answered C2 in advance: periodic reporting is viable, with two gates, not
one.** Recorded in `docs/ANDROID_PLATFORM_REFERENCE.md` §6. A `location`-typed
foreground service is the documented way to read location without the background
permission — but the agent's sync service *starts at boot*, and Android refuses to
create a `location` FGS from the background without `ACCESS_BACKGROUND_LOCATION`.
So C2 needs **both**: the service type plus that permission. The permission is
`dangerous`, so `ensureSelfPermissions()` self-grants it the moment the manifest
declares it — the operator's *"we can do this during provisioning"* is exactly
right, and needs no new code. 📖 **Documented, not hardware-verified**: no Google
page says in so many words that a DO may grant *background* location, and the
failure mode is silent — the grant reports nothing wrong and fixes never arrive
while the screen is off. Bonus: `setLocationEnabled` lets the DO switch the
device's master location setting on, removing the other silent-failure path.

**Two deviations from the approved plan, both deliberate.**

1. **No denormalised `last_*` columns on `device`.** The plan said add them so the
   fleet list needs no join. With `(device_id, recorded_at)` indexed, the latest
   point is an index seek, and nothing today draws a fleet map — so the columns
   would have bought nothing and introduced a second copy of a fact that can drift
   from the first. `locations.latest()` is the single source.
2. **One `TRACKING_FENCING` spec, not two policy types.** In this console a
   sub-page *is* a `ui_group` (W12), so "Device location tracking" and
   "Geofencing" are two groups in one spec. Two policy types would have produced
   two categories, which is not what was asked for.

⚠️ **Stub sub-pages sorted first, which silently reversed the requested order.**
Geofencing would have rendered *above* Device location tracking. `StubPage` now
takes `after`, naming the sub-page it follows; the default is unchanged, so ATAK
Config's "Plugin behavior" still leads. Both orders are asserted — the second
because fixing one category by breaking another is the obvious way to get this
wrong.

⚠️ **`0` means off, and `HIGHEST_RANK` is why it can.** Under `MIN` — the
instinctive choice for an interval — a policy that disables tracking would win
every contest and silently turn it off fleet-wide; under `MAX`, off could never
win and no device could be exempted. `0` is not a smaller interval, it is a
different kind of answer, and only rank lets an operator say either thing.

⚠️ **A `bigint` key needs `.with_variant(Integer, "sqlite")`.** SQLite
auto-assigns a rowid only for a column declared exactly `INTEGER PRIMARY KEY`, so
a `BIGINT` key is an ordinary column that stays NULL — every insert failed under
the suite while being correct for Postgres. The migration carries the variant too.

**What the ingest refuses**, each because it is believed rather than checked
later: impossible coordinates (and NaN specifically, which passes any range test
written the obvious way), fixes stamped in the future (a wrong clock otherwise
pins a device to the top of every history view for ever), and points already
stored (a lost response makes a correct agent re-send, so duplicates would corrupt
the track exactly when coverage is worst). Every drop is counted and logged.

**`locate` results are stored as points too**, so history begins filling for
devices with no tracking policy and before C2 ships — which is also what will give
C3's map something to draw. The agent says `accuracy_metres` / `fixed_at_millis`
where the wire schema says `accuracy_m` / `recorded_at`; one function knows both,
rather than renaming either and breaking a released agent.

**Not done, deliberately:** nothing purges yet. Retention is C5, and until it
lands this table only grows.

#### ✅ C4 — Geofencing

**Both open questions answered by the operator, 2026-09-08.**

* **Password enforced = require *and* lock now.** The requirement is set and
  `lockNow()` is called, so the rule takes effect immediately rather than at the
  next lock. ⚠️ On a device with no password this makes Android prompt whoever is
  holding it to create one — chosen knowingly.
* **Conflicts resolve most-restrictive.** Off beats on, enforced beats not, the
  shorter interval wins.

1. Spec: a `Geofence` model and a `geofences` list on `TRACKING_FENCING`, in a
   **Geofencing** `ui_group` declared *after* the tracking field so it keeps
   sitting below it. Retire the stub page. Merged `MERGE_BY_KEY` on name, so
   stacked policies extend the set and can override one fence by name.
2. `GeofencePlan` — pure: haversine distance, inside/outside per trigger, and the
   most-restrictive fold. JVM-tested, like every other plan here.
3. `GeofenceEnforcer` — the Android half: Wi-Fi, Bluetooth, password, interval
   override, and **releasing each one** when no fence asks for it any more.
4. Wire into the sampler, so a fence is evaluated against every fix.
5. Console: an editor for the fence list.
6. Tests both sides.
7. Build, publish, deploy, verify on hardware.

⚠️ **The release path is where this will go wrong, not the apply path.** Every
password setter in this system *latches* (W41): whatever was last written stays
until something writes over it, and survives the policy being unassigned. A fence
that sets a requirement on entry and merely stops setting it on exit leaves the
device permanently locked down by a rule nobody can see in the console. So leaving
a fence must **actively push the permissive value**, and that is the case worth
testing hardest — an apply that fails is visible, a release that never happens is
not.

⚠️ **A geofence needs positions, so it cannot depend on tracking being on.** If
an operator sets a fence but leaves the reporting interval at 0, the fence would
never evaluate and would look broken rather than unconfigured. Fences therefore
imply sampling, falling back to the existing `geofencing.poll_interval_s` admin
setting — which until now has been inert.

###### ✅ Complete (2026-09-08) — agent 0.48.0 (versionCode 93), 1236 server tests

**The whole lifecycle verified on `SM-X520`**, apply *and* release:

```
22:20:24 I/GeofenceEnforcer: geofence set bluetooth off
22:20:24 I/GeofenceEnforcer: geofences now active: Bench
22:20:25 I/LocationTracker:  location reporting interval: 5 -> 2 minute(s)
22:21:23 I/GeofenceEnforcer: bluetooth restored to on (was ours)
22:21:23 I/GeofenceEnforcer: no geofence applies now
22:23:24 I/LocationTracker:  location reporting interval: 2 -> 5 minute(s)
```

⚠️ **"was ours" is the load-bearing part of that log line.** A radio the fence
turned off is recorded together with what it was before, and only that is put
back — the rule `hiddenByPolicy` already follows. "Everything currently off" is
not the same set as "everything we turned off", and restoring the former would be
the agent reversing a decision that was never its own.

⚠️ **The password requirement is folded into the PASSWORD spec, not applied
beside it.** `applyPassword` drives every password field to a definite value on
*every* reconcile, pushing the permissive value when the policy is absent (R14) —
so a geofence calling `setPasswordQuality` itself would have been undone by the
next sync, minutes later, silently. Folding keeps one writer and makes release
automatic: when no fence asks, the floor is simply not added. This was found by
reading `applyPassword` before writing the enforcer, not by watching it fail.

⚠️ **`lockNow()` fires on the transition, never on every evaluation.** Re-locking
each time a fence was evaluated would relock the tablet every couple of minutes
for as long as it stayed inside — not enforcement, an unusable device.

⚠️ **The password control is a yes/no select, not a checkbox.** An unchecked
checkbox submits nothing at all, so positional pairing would shift every later
fence's setting onto the wrong row — the bug the kiosk favourites note records.
A first version used a hidden companion field to work around that; the codebase
already had `_yesno`, which removes the hazard instead of managing it.

**Geometry is haversine.** A degree of longitude is 111 km at the equator and
55 km at 60°, so a flat approximation is correct in testing and wrong in the
field by a factor that depends on where the fence is. The `asin(min(1.0, …))`
guard matters too — without it a device standing perfectly still computes NaN,
which compares false against every radius and reads as *outside every fence*.

**A fence missing its geometry is skipped, not defaulted to 0,0** — a real place
in the Atlantic that every device is permanently outside, which would silently
apply whatever an exit trigger carried.

**22 JVM tests** for `GeofencePlan`, plus server-side tests for the form
round-trip, the ordering, and the refusals (a fence tighter than 25 m would flap
between inside and outside while a device sat still).

⚠️ **Two actions were deliberately NOT tested on hardware, and the reason is a
real operational hazard rather than caution.**

* **`wifi: off`** — `SM-X520` is a Wi-Fi-only tablet. Turning the radio off takes
  it fully offline, and because a fence is evaluated *on the device*, a stationary
  tablet never leaves the fence and so can never be told the fence was removed.
  It would be stranded until someone physically touched it. **This is a property
  of the feature, not of the test**: an entry fence with Wi-Fi off, on a
  Wi-Fi-only device that stays put, is a one-way door. The console warns beside
  the field; it is worth an operator knowing before they use it.
* **`password_enforced`** — would lock the tablet and, having no password set,
  prompt for one on a device nobody can reach. The code path is unit-tested and
  the fold is verified; the on-device half awaits a tablet someone is holding.

⚠️ **Wi-Fi off can strand a device.** Turning the radio off inside a fence also
cuts the path the agent uses to be told to turn it back on. The device keeps
evaluating locally, so leaving the fence restores it — but a device that is
switched off inside the fence and moved comes back with the radio off until it
next gets a fix. Worth stating in the console next to the field.

#### ✅ C4a — A geofence lock needs a password policy beside it

Operator, 2026-09-08: *"can we mandate that it be tied to the password policy if
enabled? as in it requires a password policy be set in the same policy before it
allows the geofence lock? it could grey out the setting unless a password policy
was set."*

⚠️ **The hole this closes.** A fence's requirement is a *floor* — quality
`SOMETHING`, "any lock at all". With a PASSWORD policy beside it, that floor is
the operator's own rule. Without one it is the only thing in play, so the device
asks whoever is holding it to invent a PIN — and what they invent becomes the
fleet's password policy. The operator has enforced a lock and specified nothing
about it.

⚠️ **"The same policy" means the same profile**, and the strict reading is
deliberate. A `PASSWORD` policy assigned separately would also reach the device —
the resolver merges everything assigned — but it can be unassigned on its own,
leaving the fence demanding a lock with no rule behind it. That is exactly the
state being prevented, so the two travel together or not at all. A **standalone**
`TRACKING_FENCING` policy therefore cannot carry a lock at all.

Enforced at **six** points, having found two more while wiring the four planned:

| Where | Why it is not redundant |
|---|---|
| `create_profile` | The obvious one. |
| `upsert_section` | Judged against the profile as it *will* be — reading the section back from the database checks the previous version and lets the new one through. |
| `remove_section` | ⚠️ The rule is satisfied once and then the Password tab is deleted. Fires from a different tab, minutes later, with the thing it protects nowhere on screen. |
| `POST /api/v1/policies` | A standalone policy has no sibling. |
| `POST /policies/{id}/versions` | Publishing a new version of an existing section — checked against its *actual* sibling, so a legitimate profile section is not falsely refused. |
| `POST /profiles/{id}/sections/{key}/remove` | ⚠️ **The button an operator would actually use**, and the one path that did not catch `ProfileError` — it would have raised a 500 on the very check protecting the lock. |

⚠️ **Upserts now run before removals in a whole-profile save.** Catalog order puts
Password before Tracking and fencing, so one submission that both cleared the
Password section *and* released the fence needing it would delete the section
while the fence still demanded one — refusing a change whose end state is
perfectly legal. Writing what is kept before deleting what is not makes the check
see the state the operator is actually asking for.

⚠️ **`section.latest_version` is stale immediately after `upsert_section`.**
It reads the relationship collection, and `upsert_section` adds a `PolicyVersion`
by id rather than appending to `child.versions`. So a fence released a moment
earlier still read as demanding a lock, and removing the Password section was
refused on the strength of a spec that was no longer current. The removal check
queries the newest version directly. Found by the test that releases and then
removes — not by reasoning about it.

**Greyed, never `disabled`.** A disabled `<select>` submits nothing, and fence
rows pair by position, so disabling one would shift every later fence's password
setting onto the wrong row — the same trap the kiosk favourites carry a note
about, arriving as a fence demanding a lock nobody set. The control is greyed by a
CSS class and forced to *No*, and keeps submitting. The greying is a convenience;
the server is the enforcement, because a greyed control is a suggestion to anyone
with developer tools. The JS test is deliberately the server's test — "does the
Password panel hold any value at all" — because an untouched password section
parses to `{}`, which is what the server treats as no policy.

**1250 server tests.**

#### ✅ C5 — Retention: the table stops only growing

Operator, 2026-09-08: *"default to 30 days, but have a setting in admin to adjust
retention."*

1. `location.retention_days` in the existing **Location** settings group,
   defaulting to **30**.
2. `purge(session, days)` in the locations service — a bulk delete by age,
   returning what it removed so the log says so.
3. A periodic sweeper, following `_start_index_warmup`'s shape: a daemon thread
   resolved through `dependency_overrides` and gated by a setting, so it cannot
   run inside the test suite. **The host has no cron** — this is why the job lives
   in the app rather than in a timer someone has to remember to install.
4. Run it once at boot and then daily. A deployment that is restarted often should
   still purge; one that runs for months must not wait for a restart.
5. Tests, deploy, verify against the real track.

⚠️ **`0` means keep for ever, and the polarity is the risk.** The tracking
interval next door uses `0` for *off*, so someone could read `0` here as "no
retention" meaning "keep nothing" and erase the fleet's history. The field is
labelled unmistakably — but the deciding argument is which way the misreading
fails: read as "keep for ever" it costs disk, read as "delete everything" it costs
data that cannot be recovered. It fails safe in the direction it is being given.

###### ✅ Complete (2026-09-08) — 1227 server tests, running on the host

Default **30 days**, adjustable at **Admin → Location**. The sweeper runs at boot
and every 24 h, in-process, because **this host has no cron** — a retention policy
that depends on someone remembering to install a timer is one that quietly does
not run, and the failure is invisible: a table that keeps growing looks exactly
like a table being maintained until the day somebody checks.

Confirmed on the host:

```
INFO [app.main] location retention: 0 point(s) removed, keeping 30 days
```

⚠️ **A nonsense setting falls back to 30, never to 0.** The row is a text column
an operator types into; reading `"thirty"` as `0` would compute a cutoff of *now*
and take the entire table. Tested against `"thirty"`, `""`, `"12.5"`, `"-1"` and
`"30 days"`.

⚠️ **Deleted on `recorded_at`, not `received_at`.** A point delivered late is
still as old as the console says it is; retaining by delivery time would keep a
point the page shows as three months old because it happened to arrive yesterday,
and nothing on that page would explain it.

---

### ⚠️ Operational note: this server's INFO logs went nowhere for months (W106 C5)

Found while trying to confirm the retention sweep had actually run.

**Uvicorn configures handlers on its own `uvicorn.*` loggers and leaves the root
logger with none.** Records from `app.` propagated to a root that could not print
them and fell through to Python's `logging.lastResort` handler — which is
hard-wired to WARNING. So this server's warnings have always appeared and **not
one of its INFO lines ever has**: the index warm-up's `index ready`, the catalog
backfill's progress, every `logger.info` in every service.

⚠️ **`setLevel` alone does not fix it**, which cost a deploy to learn: the level
was never the thing stopping them. The `app` logger needed a handler of its own.

The visible symptom was a server that started and then said nothing, which reads
as quiet and healthy rather than as muted. If a past session concluded some
background job "was not running" because nothing appeared in `docker compose
logs`, that conclusion is worth revisiting — the evidence for it did not exist.

⚠️ **Deleting is the point, so it needs the most care in this whole feature.**
Everything else here is additive; this is the one piece that destroys operator
data on a timer, unattended, for ever. The purge is bounded to `device_location`
by an explicit age filter, never a bare delete, and it is tested for the case that
matters most: a misconfiguration must not take the table with it.

#### ✅ C3 — The map, and the history page

Duplicating `EUD_Remote_Assist_Portal`'s display, which was read from its source
rather than its README (the README does not cover it).

1. **Vendor Leaflet** (1.9.4, BSD-2-Clause — compatible with Apache-2.0) into
   `static/vendor/`. The reference loads it from unpkg; a console that stops
   working when a CDN does is not what a fleet tool should be. Marker images are
   avoided entirely by using `divIcon` for both maps, so there are no image assets
   to vendor or to 404.
2. **Port the downsampling tiers exactly**, as a pure function: all points under
   2 h, then newest-per-15 min to 6 h, per-hour to 48 h, per-6 h to 96 h, per-day
   beyond. Numbered oldest→newest the way the reference numbers them.
3. **Device page**: replace the W104 placeholder with coordinates to 5 decimals,
   accuracy as `±N m` or *"Not reported by device"*, the **fix age**, and a map of
   the last position with an accuracy circle. A *Location history* link below it.
4. **History page** `/devices/{id}/location-history`: the reference's inverted
   range (**From is the newer bound**, `Now` or a date; **To is further back**),
   defaulting to now → 48 h ago; numbered markers; a Records table where clicking a
   row flies the map to that point; *Export all history* as CSV of the full
   unsampled set.
5. **Tile source as a setting**, defaulting to OpenStreetMap, so a deployment
   without internet can point at its own tile server instead of showing a blank
   map with no explanation.
6. Tests, then deploy and check against the real track `SM-X520` is now laying
   down.

###### ✅ Complete (2026-09-08) — 1218 server tests, drawn against a real track

**Leaflet 1.9.4 vendored** into `static/vendor/`, BSD-2-Clause (compatible with
Apache-2.0), recorded in `NOTICE` with the licence text kept beside the files. The
reference portal loads it from unpkg; a console that stops working when a CDN does
is not what a fleet tool should be. Marker images are avoided by using `divIcon`
for both maps — the icons are CSS — so nothing depends on Leaflet's image assets
resolving, which is the usual way a vendored copy breaks quietly after a move.
(The images are bundled anyway, for the rules we do not hit.)

**The downsampling tiers are an exact port**, asserted against the original
formula at every boundary rather than approximately: the operator asked for a
duplication of that portal's display, so a tier that is nearly right is a wrong
answer, not a near one.

⚠️ **The page says when it is showing a thinned track.** A thinned stretch looks
exactly like a device that was reporting less often, and an operator who mistakes
one for the other concludes the agent is failing. The panel names both numbers,
and the CSV export deliberately ignores both the range and the thinning — a button
saying *"Export all history"* that quietly did neither would hand someone a file
they believe is complete.

⚠️ **A device with no position says *which* silence it is.** "Nothing is
collecting" sends an operator to the policy; "collecting, nothing has arrived yet"
sends them to the device. A single "no data" would send them to neither.

⚠️ **The fix age is on the page, not just the timestamp**, and a stale one is
called out. A position from yesterday drawn on a map is indistinguishable from one
from a minute ago — which is the whole reason the agent reports last-known rather
than pretending to a live fix. An unreported accuracy reads *"Not reported by
device"*, never `±0 m`.

⚠️ **A backwards range is refused, not silently swapped.** Swapping would answer
a question the operator did not ask while the form went on showing the one they
did, and the result would be read as the answer.

**Deliberately not built: reverse geocoding.** The reference shows a street
address above the map, fetched per view from `nominatim.openstreetmap.org` — so
every time an operator opens a device page, that device's coordinates go to a
third party. For a fleet whose positions are the sensitive thing, that is a
disclosure decision rather than a convenience, and it is the operator's to make.
Tiles raise the same question one step smaller, so the source is a setting
(**Admin → Location map**) defaulting to OpenStreetMap, which also covers a
deployment with no internet — where the default would otherwise show an empty map
with no explanation.

**Verified live** against the track `SM-X520` is laying down: assets 200, map
present, `±5 m`, *"70 seconds ago"*, 9 history rows, and a CSV of real GPS fixes.

⚠️ **No reverse geocoding.** The reference shows a street address above the map,
fetched per view from `nominatim.openstreetmap.org` — which means every time an
operator opens a device page, that device's coordinates go to a third party. For a
fleet whose positions are the sensitive thing, that is a disclosure decision, not
a convenience. The panel shows coordinates instead. If the operator wants
addresses, it should be a setting that is off until switched on, and that is worth
asking about rather than assuming.

 Fetching tiles tells
the tile server roughly where the operator is looking. OSM is the sane default and
the setting exists so it need not be.

#### ✅ C2 — The agent reports on the policy's interval

1. Confirm `TRACKING_FENCING` actually reaches the device in the desired-state
   bundle. It should, since `policy` is passed through whole — but nothing else in
   this chunk works if it does not, so it is checked rather than assumed.
2. Manifest and permissions: `ACCESS_BACKGROUND_LOCATION`,
   `FOREGROUND_SERVICE_LOCATION`, and `foregroundServiceType="specialUse|location"`
   on `SyncService` (the attribute is a bitmask, so the existing type stays). Add
   the requirement to `PermissionRequirement` so the compliance screen shows it,
   and call `setLocationEnabled` so the master switch cannot be the silent cause.
3. `LocationSamplingPlan` — a **pure** object: is a sample due, what does the
   buffer hold after appending, which points go in the next batch. No Android
   types, so it is testable on the JVM like every other `*Plan` here.
4. `LocationTracker` — the thin Android shell: `reconcile(section)` persists the
   interval (absent section = off, the `DataUsageTracker` pattern), `sampleIfDue()`
   reads the last known fix and appends.
5. Wire it: `Reconciler` puts `locations` on the check-in and clears the buffer
   **only after the server accepts**, and `SyncService` samples every loop
   iteration — not inside `sync()`, so a device with no network keeps recording
   the track it is buffering.
6. JVM tests for the plan, and Python tests for the bundle.
7. Build, publish, deploy, verify on hardware.

⚠️ **Step 7 is where 📖 becomes ✅ or does not.** Whether a Device Owner may
self-grant *background* location is documented-by-assembly, not stated outright,
and it fails silently: the grant call reports nothing wrong and fixes simply never
arrive while the screen is off. The check is therefore "points arrived from a
device whose screen has been off", not "the permission shows as granted".

###### ✅ Complete (2026-09-08) — agent 0.47.0 (versionCode 92), verified on `SM-X520`

✅ **A Device Owner *can* self-grant `ACCESS_BACKGROUND_LOCATION`.** This was the
open 📖 from C1, and the tablet settled it. From its own log:

```
20:16:21 I/PolicyApplier: self-granting 1 permission(s): android.permission.ACCESS_BACKGROUND_LOCATION
20:17:56 I/LocationTracker: location reporting interval: 0 -> 1 minute(s)
20:19:56 I/LocationTracker: location sampled (gps, 1s old); 1 buffered
20:19:56 I/SyncService: foreground service now claims the location type
```

⚠️ **The fix *age* is the verification, not the arrival.** A device denied
background location does not fail loudly — `getLastKnownLocation` keeps returning
something, just steadily staler. "Points arrived" would have looked identical.
Ages of 1–2 s across a run of samples are a live GPS session, and that is what
proves both the grant and the service type took.

⚠️ **The change that could have bricked the fleet, and did not.** Android throws
`SecurityException` when a foreground service type's runtime prerequisites are
unmet, which per Google "might cause a running foreground service to be removed
from the foreground process state, and might cause your app to crash" — and the
service in question is the one that manages the device at all. Claiming `location`
unconditionally would have taken every tablet down at boot to add a feature most
fleets will not switch on. The manifest declares `specialUse|location` (a bitmask,
so the original type is kept), `startForeground` is passed a type computed from
what is actually granted, and the claim is upgraded once tracking turns on. A
failed upgrade is logged and swallowed: losing the type costs tracking, throwing
would cost the device its management. Confirmed in the APK as `0x40000008`
(`SPECIAL_USE | LOCATION`), and confirmed on hardware by the device continuing to
check in after taking the update.

⚠️ **Sampling is in the sync loop, not in `sync()`.** An offline device still
records — which is the entire point of buffering, and putting it inside the
reconcile would have produced a gap exactly where the track mattered.

⚠️ **The buffer is a JSON array, not a `StringSet`.** Every other buffer in
`AgentConfig` uses `putStringSet`, which is right for them and wrong here: a set
has no order, and a track delivered out of order is not a track. It would also
merge two genuinely distinct fixes that happened to serialise identically.

⚠️ **Delivery drops exactly what was sent, not the whole buffer.** Sampling runs
on the same loop, so points can be added while a check-in is in flight; clearing
wholesale would discard fixes the server never saw, invisibly.

Other decisions worth keeping: a clock that jumps backwards reads as "due now"
rather than suspending tracking until it catches up; a full buffer drops oldest
first (a track is read from the recent end) and says so in the log;
`setLocationEnabled` turns the master switch on, since otherwise a perfectly
permissioned agent reports nothing and no log anywhere explains it.

**16 JVM tests** for `LocationSamplingPlan`, **1203 server tests**.

**Live on `SM-X520` now** at a 5-minute interval (`W106 location test` policy),
left running deliberately so C3's map has real track to draw. Set the interval to
0, or unassign the policy, to stop it.

⚠️ **Sampling rides the sync loop rather than a new scheduler.** The loop already
wakes at least every 120 s (`waitForChange` parks server-side and returns), already
holds a foreground service, and already has the battery exemption that took work
to get. A second scheduler would be a second thing to keep alive across reboots and
app replacement, for granularity no policy here needs — the interval is in minutes.

**Open question for C4, not C1:** two fences whose conditions both hold and whose
actions disagree (one says Wi-Fi on, one says off) need a defined precedence, and
"password enforced" needs scoping — requiring a password the device does not have
puts a lock-screen setup in front of whoever is holding it, which is a different
thing from toggling a radio.

### ✅ W105 — Manage went to Enroll

Operator, 2026-09-08: *"when I click manage, it takes me to enroll"*.

**My own W100 change caused it.** The 443 server block for
`mdm.tak-solutions.com` ends with `location = / { return 302 /enrollment; }` —
that hostname exists to hand a device to someone enrolling it, so its bare root
sends them there. The Manage nav link was `href="/"`. On the IP and on port 80 it
worked; on the hostname the redirect swallowed it.

⚠️ **A nav link names the page it opens.** Relying on what `/` happens to mean
is relying on which host the console is being read from, and that now varies by
design. The dashboard answers on **`/fleet`** as well as `/`, the nav and the
brand logo both point at `/fleet`, and the post-delete redirect goes there too.
`/` still serves the dashboard, so nothing that bookmarked it breaks.

⚠️ **A Jinja comment cannot go inside the `{% set sections = […] %}` list.**
That is one expression, not a block of statements, and a `{# … #}` inside it is a
`TemplateSyntaxError` at *every* page render — caught here only because the footer
test loads four pages. The explanation sits above the block instead.

Two regression tests in `tests/test_build_version.py`: the rendered page carries
`href="/fleet"` and no nav link depends on the root, and both paths answer 200.

**1178 server tests. Console-only — no agent change, no APK.**

### ✅ W102 — The running build, in a footer

Operator, 2026-09-08: keep the active web UI build listed in a footer for quick
reference.

⚠️ **A version string somebody must remember to bump is worse than none.**
`main.py` carried `version="0.1.0"` through a hundred work items, telling every
reader something false. The question a footer answers is *"is this server running
the code I think it is"*, and only the revision can answer it — so the footer
shows the commit, its date, and whether the tree was modified.

⚠️ **The deploy tarball excludes `.git`**, so the host cannot ask git anything.
`scripts/write_build.py` stamps a `BUILD` file at pack time and that ships inside
the tarball. Resolution order: `TAKMDM_BUILD` env, the `BUILD` file, local git
(development), then nothing.

⚠️ **With no source it says `build unknown`, never a guess.** A plausible
build number is *believed*, and sends someone debugging code that is not running;
a missing one is merely unhelpful. Two tests exist for that refusal alone,
including a half-written `BUILD` file, which must not read as an answer.

⚠️ **A dirty tree is reported as modified.** Deploying uncommitted work is
ordinary here; labelling it with the last commit's hash alone would make the
footer claim something untrue.

Injected in `_render`, for the reason the CSRF token is: every page needs it, and
a page that forgot would render nothing rather than fail, so nobody would notice.
`BUILD` is gitignored — it is per-deploy, and committing it would ship a stale
value. **1167 server tests.**

### ✅ W101 — Google Play on its own tab, searchable by name

Operator, 2026-09-08: a Google Play tab between TPC Plugins and 3rd party repo,
one bar taking an app name or a package id, and Play out of the repository search.

⚠️ **Play gets a tab rather than a row because a result costs a credential.**
Every other source is free to query; a Play row needs a linked Google account and
carries terms the others do not. Behind a shared bar that difference disappears.

#### ⚠️ Two bugs found by the operator's own test choices, not by mine

**The split app, found by testing Outlook.** `download()` took `max(files,
key=size)`. apkeep writes a bundle as separate parts, so that kept the base and
discarded the ABI split — an app Android refuses as `INSTALL_FAILED_MISSING_SPLIT`
which then reported `abis = ()`, *"runs anywhere"*. The missing bytes were the
lesser harm: **it was a lie in the one field W96 exists to make true**, and it
would have passed the preflight built to catch exactly that. Chrome had it too and
looked fine, because its base happened to carry the arm64 code. Outlook, cleanly
split by ABI, made it visible. Both apkeep sources now share `collect_output`,
which keeps every part and wraps them in the container shape `inspect_bundle`
already reads. The incomplete Chrome was deleted from the library.

**The two layouts, found by searching "microsoft".** Play renders list rows whose
anchor carries the app name, *and* a grid for broad or brand queries whose anchors
carry no name at all. The first version matched only the former: `outlook` and
`handtevy` worked, `microsoft` and `esri` returned **nothing** — which reads as
"Play has no Microsoft apps" rather than as a parser missing. Both layouts are
handled and both are tested.

⚠️ **I had called the first version robust**, contrasting it with the class-based
scrapers rejected in the survey. It was anchored on stable things and still only
covered half the cases, because the queries tested happened to share a layout.

**The package id is load-bearing, the name is not.** The id comes from a URL and is
what a fetch needs; the title is taken from the anchor label, else the card's first
visible text, else the id itself. A redesign that hides titles degrades a row to
something plainer — never to something wrong, never to nothing.

⚠️ **A test was reaching Google.** The first name search called `httpx.get`
directly with no injectable client, so the suite silently depended on a third
party being up. The client is injected now and search is tested against a stub,
including a 503 — which must read as *unreachable*, not as *no results*.

**One panel's worth of code, wired twice.** The repository and Play panels differ
only in which search endpoint they call, so `atlasWireAppSource` is called for
each. Element lookups moved from `#repo-*` ids to panel-scoped data attributes:
two panels cannot share an id, and `getElementById` could not have said which
panel's progress bar it had found.

**1161 server tests.** Verified live: `microsoft` returns the Microsoft family,
`esri` returns 14 ArcGIS apps, an exact id skips the lookup.

### ✅ W100 — `mdm.tak-solutions.com` on 443, with a real certificate

Operator, 2026-09-08: an A record for `mdm.tak-solutions.com` should reach the
enrollment page.

#### What was already true

    mdm.tak-solutions.com → 209.182.235.108           ✓ A record live
    https://…:9443/enrollment → 401 Basic "ATLAS console"  ✓ already answers
    https://…/ (443)          → connection refused          ✗ nothing listening
    http://…/ (80)            → 403 from nginx              ✓ reachable, APK-only

The 9443 block is `server_name _`, so the hostname *already* reaches the console.
Only the bare name on 443 was missing.

⚠️ **`/enrollment` is an admin page, not a device-facing one.** It sits behind
`admin_required` and mints 15-minute credentials that let a device join the fleet.
So this publishes the **console** under a public name. The auth boundary does not
change — HTTP Basic, as on 9443 — but **443 is vastly more discoverable** than
9443, which scanners essentially never touch. Worth a strong Basic password; there
is no rate limiting in front of it.

#### Order is forced by the certificate

nginx will not start with a server block naming a certificate that does not exist,
so this cannot be done in one pass:

1. Serve `/.well-known/acme-challenge/` from a webroot on the existing port 80
   block, and mount it. Deploy — nginx is still happy, nothing else changes.
2. Issue the certificate with certbot in webroot mode against that path.
3. Add the 443 block for the hostname, publish 443, redirect `/` → `/enrollment`.
   Deploy.
4. Renewal on a timer, with a reload hook.
5. Verify from outside: a real chain, and the redirect landing on the login.

**9443 is left exactly as it is**, so nothing that works today depends on this
succeeding.

###### ✅ Complete (2026-09-08), verified from outside

    GET https://mdm.tak-solutions.com/          -> 302 -> /enrollment
    GET .../enrollment                          -> 401 Basic "ATLAS console"
    9443                                        -> 401, unchanged
    cert: mdm.tak-solutions.com, Let's Encrypt, to 2026-12-07

Checked **with TLS verification on**, not bypassed — a self-signed certificate
would have passed a `verify=False` test and failed every browser.

⚠️ **The auth boundary was factored into `console-proxy.inc`, shared by both
listeners.** Those `proxy_set_header X-Authentik-*` lines *are* the security
model: the app trusts that header completely, so everything rests on only the
proxy being able to set it. Two copies could drift, and the copy that got weakened
would still look like a working console. One file cannot drift from itself.

⚠️ **Renewal is a systemd timer, because this host has no cron** — `crontab` is
not on the PATH, which also explains the note elsewhere that the SQL backups are
all manual. `certbot renew --dry-run` was run: the whole path works, rather than
merely being scheduled.

⚠️ **Registered with no email contact**, so there are **no expiry warnings from
Let's Encrypt** and the timer is the only safety net. The operator's address is
for identifying them here, not for handing to a third party; `certbot
update_account` adds one if wanted.

### ✅ W99 — Google Play as a source, via an operator-supplied token

Operator, 2026-09-08: *"continue with apkeep Google play using the token method…
add a token entry field in the admin section, along with instructions."*

#### The flow, from apkeep's own documentation

The operator signs in at Google's embedded setup page with devtools open and
copies a **one-time** `oauth_token` (it starts `oauth2_4/`). That is spent once to
mint a **long-lived AAS token**, which every later download uses. apkeep performs
the exchange itself, so ATLAS can take the one-time value, mint the durable one
server-side, seal it, and never show it again.

#### Why this fits without inventing anything

`TakGovLink` is the precedent almost exactly — its docstring already says why such
a credential *"must not sit in `app_setting`, which is plaintext"*. `TokenVault`
(Fernet, key at `pki/token_vault.key`) is the seal. The Admin → TAK.gov tab is the
interaction. A `GooglePlayLink` is the same object with fewer fields: no
device-authorization dance, because the operator pastes the code themselves.

#### ⚠️ Decisions that are about safety, not preference

* **Credentials go in a `0600` `apkeep.ini`, never on the command line.** An AAS
  token passed as `-t …` is visible in the process list to anything that can read
  `/proc` on that host. apkeep documents the ini file; this uses it.
* **The device profile is pinned and recorded.** Play serves *device-matched*
  builds, so the profile decides the architecture that arrives. Default `px_9a` is
  arm64 and suits this fleet — but leaving it implicit would be R19 through a
  different door.
* **`--accept-tos` accepts Google's terms on the account's behalf.** ATLAS would
  be clicking "I agree" for the operator, so the tab says so plainly.
* **The token is sealed and never rendered back**, and Unlink destroys it.
* `split_apk=true`, so what arrives is the base + splits shape `inspect_bundle`
  already handles.

⚠️ **Untestable from here.** There is no Google account on this side, and the
token must never travel through a chat. The operator enters it in the admin field;
what can then be verified is that the exchange succeeded, a download completed,
and the architecture that arrived is the one asked for.

#### Chunk C1

1. `GooglePlayLink` (singleton, sealed token, pinned profile) + migration.
2. `google_play_link.py` — exchange, seal, status, unlink.
3. `GooglePlaySource` — apkeep with the ini file, joining the unified search.
   Play takes an exact package id, like APKPure, so the bar's existing rule holds.
4. Admin → Google Play tab: instructions, email + one-time token, unlink.
5. Tests with apkeep stubbed — including that the token never reaches argv.
6. Deploy; the operator links; a real download is then verified.

###### ✅ Built (2026-09-08) — 1154 server tests, awaiting a linked account

Migration `d0f2h4j6l8n0`. **No row is created**: absent means unlinked, so the
feature costs every existing deployment nothing until someone chooses it, and an
unlinked instance reports no failure on searches for a source it does not have.

⚠️ **The AAS token never touches a command line.** apkeep documents an
`apkeep.ini`, and it is written with `os.open(..., 0o600)` — the mode requested at
*creation*, not applied by a later `chmod`, because between the two the file is
world-readable. A test captures the mode argument, which holds on any platform;
the mode assertion itself is POSIX-only and skipped on Windows, where the server
does not run.

⚠️ **The one-time oauth token *does* go on the command line, deliberately.** It is
spent by that single call and worthless afterwards; the durable secret is the one
worth keeping out of `/proc`.

⚠️ **A failed exchange says the token is spent.** Google issues it for one use, so
an operator retrying the same value would conclude the feature is broken rather
than that they need a fresh one.

⚠️ **Unlink destroys the stored token and says it does not revoke anything at
Google.** Implying otherwise would leave someone believing they had closed a door
that is still open.

**The device profile is stored on the link, not defaulted at call time**, because
Play serves device-matched builds — the profile *is* the architecture, and a build
must be explicable after the fact. `px_9a` is arm64, which suits this fleet.

**Not yet verified:** there is no Google account on this side and a token must
never travel through a chat. The operator links in the admin tab; what can then be
checked is that the exchange succeeded, a download completed, and the architecture
that arrived is the one asked for.

### ✅ W98 — One search bar, and APKPure as a fourth source

Operator, 2026-09-08: *"include as a source. find a way to integrate into single
tab of 3rd party that we already have. I want one search bar for all sources."*

#### Two honest constraints, neither of which may be papered over

⚠️ **apkeep cannot search by name.** It answers `-l -a <exact.package.id>` and
nothing else. So one bar cannot query APKPure the way it queries F-Droid: APKPure
can only contribute a row when the query *is* a package id. The UI must say so —
an operator typing "osmand" and seeing no APKPure result deserves to know it is a
property of the source, not an outage.

⚠️ **APKPure states version *names*, not versionCodes** — `5.4.4`, not `5404`.
`SourceVersion.version_code` is a required int today, used for preflight and for
the import lookup. Inventing a code would be a lie in a field the library keys on,
so the model changes instead: `version_code` becomes optional and a `version_key`
carries whatever the *source* needs to fetch that build. The real versionCode is
read from the downloaded file, where it was always authoritative.

#### The unified search

One bar, every source queried, results merged and each row labelled with where it
came from. ⚠️ **A failing source must not empty the page** — each is caught
separately and reported beside the results that did arrive.

Ordering is a recommendation, as the repository picker's was: verifiable sources
first (F-Droid and friends, which publish a digest), APKPure last (which does not).

#### Chunk C1

1. `SourceVersion.version_code` optional + `version_key`; F-Droid fills both, and
   its behaviour is unchanged.
2. `app_sources/apkpure.py` — an `AppSource` shelling out to apkeep. ⚠️ The arch
   is **pinned explicitly** (`-o arch=…`), because the default returned a 32-bit
   build for an arm64 fleet on the very first real fetch. Package ids validated
   against a pattern; no shell.
3. The binary in the image: fetched at build with a **pinned sha256**, and a clear
   "not installed" error rather than a stack trace if it is absent.
4. One search bar across all sources, per-source failures isolated and shown.
5. Tests with apkeep stubbed — including the 32-bit trap: a fetched build whose
   real ABI contradicts the fleet must still be caught by preflight.
6. Deploy.

###### ✅ Complete (2026-09-08) — 1144 server tests

⚠️ **A performance trap found while wiring the fan-out.** Sources were built per
request, so one unified search would have re-parsed **59 MB + 111 MB + 14 MB** of
index JSON every time. The disk cache does not help — parsing is the expensive
half. Instances are now cached per process behind a lock, since sync routes run in
a threadpool and two searches arriving together would each build their own.

⚠️ **`cache/` reached 176 MB locally and was one `git add` from being committed.**
Now ignored.

⚠️ **I truncated `tests/test_app_sources.py`, twice.** A generator script called
`io.open(path, "w", newline="\n")`; Python truncates the file *before* rejecting
the illegal newline value, so the write never happened and the file was left
empty. Restored from git both times and the approach abandoned — the APKPure tests
live in their own file, written directly. **A script that writes a file it has not
finished computing can destroy it**; compute first, open last, or do not generate
at all.

**Two tests changed because their guarantee moved**, not because they broke: the
tab's copy (the per-source picker is gone) and the search contract (one bar, all
sources, per-source failures reported beside the results that arrived).

### ✅ W97 — 3rd Party App Repo

Operator, 2026-09-07: *"i want to add a '3rd Party App Repo' to the apps section
… a place to lookup apps and download apk/xapk files into the mdm library"*, with
`github.com/anishomsy/apkpure` offered as prior art.

#### On the prior art: take the technique, not the dependency

Apache 2.0 (compatible), Python, `requests` + `beautifulsoup4`, 12 stars, 38
commits. It scrapes APKPure HTML — `div.first`, `p.p1`, `p.p2`, `div.detail_banner`
— and downloads from `https://d.apkpure.com/b/APK/{pkg}?versionCode={code}`.

Most of it is CSS selectors that break when APKPure restyles a page. The two
durable parts — that download URL pattern and the shape of the version list — are
a page of code. **A dependency this small and this brittle is a maintenance
obligation, not a saving.** It also performs no signature or checksum check of any
kind, which is the one thing that matters most when the output is installed on a
managed fleet.

⚠️ **Operator decisions, both recorded here because they were deliberate.**
*Source*: F-Droid first, APKPure second. *Anti-bot*: use `cloudscraper` to work
around APKPure's 403s, as the prior art does. I flagged that this circumvents an
access control the site put there on purpose and that APKPure's ToS restricts
automated processes; the operator chose it knowingly, and it applies to the
APKPure source only — F-Droid needs nothing of the kind.

#### What already exists, and must not be rebuilt

`tak_gov_link.import_plugin` is the same shape as this feature: browse a remote
catalogue, download, ingest. Its docstring states the rule to follow —
*"deliberately thin … identity is read from the file itself rather than believed
from the catalog"*. So a mislabelled catalogue row cannot smuggle a package in
under the wrong name.

⚠️ **`packages.ingest` already refuses a signing-certificate change** on an
existing package. Every third-party import inherits that guard for free; it does
not need reinventing, and it must not be bypassed.

The console's **TPC Plugins** tab is the UI precedent: search, pick a version,
`POST /apps/tpc/import` returning a job, then poll — because a large download held
open in a request tells the operator nothing.

#### ⚠️ F-Droid publishes exactly what W96 taught us to want

Verified against the live index (58.9 MB, 4335 packages, fetched in 2.8s):
`entry.json` carries the index's own `sha256` and **it matched**, so the chain
*entry → index → per-APK hash* is verifiable end to end. One version entry holds:

    file.sha256                    -> verify the download
    manifest.nativecode            -> ['arm64-v8a','armeabi-v7a','x86','x86_64']
    manifest.usesSdk.minSdkVersion -> 24
    manifest.signer.sha256         -> the signing certificate

So for F-Droid the console can answer *"will this run on my devices"* **before**
importing, by comparing upstream `nativecode` against the `supported_abis` those
devices now report (W96 C2). R19 cannot repeat through this path.

APKPure offers none of that: no upstream hash, no declared ABIs. Its imports are
therefore verifiable only *after* download, by reading the file — which is what
`inspect_apk` already does. That difference is a property of the source and the UI
must show it rather than flatten it.

#### ✅ Chunk C1 complete (2026-09-07) — F-Droid only

**1119 server tests** (14 new). The APKPure half is **not built**, for the measured
reason above; the source interface stays, because it is what makes a second source
cheap if one ever becomes reachable.

⚠️ **No test touches the network.** The index is served from a stub transport —
which is not only for determinism: it is the only way to *arrange* the failures
worth testing. A tampered index, a download that does not match its published
digest, and a listing that names the wrong package cannot be produced by asking
the real repository nicely.

**Found while testing, and it is the deferred resolution argument in miniature:**
OsmAnd publishes `531003` as `arm64-v8a` and `531002` as `x86, x86_64` — adjacent
version codes for different architectures. `max(version_code)` picks correctly
here by luck of ordering. Reverse them and it picks x86 for an arm64 fleet, which
is R19 exactly.

**Preflight answers "should I fetch this" while it is still free to say no**:
a signer that differs from the one pinned on the package blocks the import (Android
would refuse the update anyway), as does a versionCode already held. Devices that
cannot run the build are a *warning*, not a refusal — it is the operator's fleet —
and devices that have never reported their architecture are **counted in the
message**, because silence must not read as approval.

#### Chunk C1 — the sources and the import

1. `app_sources/base.py`: `SourceApp`, `SourceVersion`, and the `AppSource`
   protocol. Pure value types, so search results are testable without a network.
2. `app_sources/fdroid.py`: `entry.json` → verify index hash → cache → search and
   versions; download verified against `file.sha256`.
3. `app_sources/apkpure.py`: search and versions by scraping, download from
   `d.apkpure.com`, `cloudscraper` on 403. Reports **no** upstream hash — flagged,
   never faked.
4. `repo_import.py`: download to a temp file, verify where a hash is offered, then
   hand to `packages.ingest` with **`publish=False`**. ⚠️ A fetched build must
   never auto-publish: publishing is fleet-wide and is an operator's act.
   Provenance (`source`, `source_url`) on `AppPackageVersion`, with a migration.
5. Tests against recorded fixtures — no network in the suite — including a
   mislabelled catalogue row and a hash mismatch.
6. Deploy.

#### ✅ Chunk C2 complete (2026-09-07)

**1126 server tests** (21 in `test_app_sources.py`). Deployed; migration
`b8d0f2h4j6l8` applied after a backup.

⚠️ **The live smoke test is the feature's own argument.** Against the real fleet,
OsmAnd publishes three builds of the *same version*:

| Build | ABIs | Preflight |
|---|---|---|
| `531003` | `arm64-v8a` | no compatibility warning |
| `531002` | `x86, x86_64` | **2 of 2 reporting devices cannot run this** |
| `531001` | `armeabi-v7a` | **2 of 2 reporting devices cannot run this** |

The last row is R19's exact shape — a 32-bit build that would fail permanently —
named by device serial *before a byte is downloaded*, instead of surfacing days
later as a DEGRADED tablet. The third device, silent since yesterday, produced the
line that matters just as much: *"1 of 3 devices have not reported their
architecture yet, so they are not covered by the checks above."*

**The version is re-read from the index at import**, never taken from the form:
everything the browser holds is the catalogue's word relayed through a page, and
re-asking means the download URL and digest come from the source at the moment of
import. A build already blocked is refused *before* the download, since every
reason is knowable from the listing.

`start_repo` is a sibling of `start` rather than a parameter on it — the tak.gov
import needs a vault, a product and a product version, none of which mean anything
to a repository that just serves files. The job machinery is what was worth
sharing; the console polls one route either way.

⚠️ **`cache_dir` is deliberately not inside `artifact_dir`.** That directory is
addressed by digest and swept; a 59 MB index living there would look like an
unreferenced blob to anything tidying up. Losing the cache costs one re-fetch.

#### Chunk C2 — the console

7. A fourth tab on `/apps`, following the TPC pattern: search, versions, import
   job, polling modal.
8. Before import, show what is known: ABIs, minSdk, signer, and whether the source
   offers a hash at all — plus, for F-Droid, which enrolled devices could not run
   it.
9. Tests, deploy.

#### ⚠️ APKPure is not reachable programmatically (measured 2026-09-07)

Tested before building, and it settles the question:

| Endpoint | plain `httpx` | `cloudscraper` |
|---|---|---|
| `apkpure.com/search?q=` | 403 | **403** — Cloudflare "Just a moment…" |
| `apkpure.com/…/versions` | 403 | **403** |
| `d.apkpure.com/b/XAPK/…` | 403 | 200 once, **403 on every retry** |

⚠️ **The one success was a clearance that had lapsed within the minute.** Re-run
immediately afterwards, all four endpoints — including the download that had just
returned 25.9 MB — answered 403.

`cloudscraper` no longer defeats what APKPure runs. The prior art dates from an
older Cloudflare; the current one serves a managed challenge that a requests-level
shim cannot pass. **The operator's choice to use it was made on the premise that
it works, and that premise is false**, so the APKPure source is not built rather
than built broken. A source that succeeds occasionally and fails opaquely is worse
than no source: it teaches an operator to retry instead of to act.

Manual upload already covers this case — `/apps/upload` takes an APK or XAPK, and
the operator's own test files are APKPure downloads made by hand. What ATLAS adds
on top of that is the part it is good at: reading the file and saying what it is.

#### ⚠️ APKMirror: the same wall, one level deeper (measured 2026-09-07)

Evaluated next, via `github.com/tanishqmanuja/apkmirror-downloader` (TypeScript,
MIT, 88 stars — so a port, never a dependency, from a Python server). Its own
README warns that downloads *"can fail at random … due to rate limit protection by
APKMirror using Cloudflare"*.

| APKMirror | Result |
|---|---|
| home, search, app pages | **200** — open and parseable, 50 clean result rows |
| release / variant / download pages | **403** — `server: cloudflare`, "Just a moment…" |

⚠️ **Deterministic, not rate limiting.** Two rounds three seconds apart returned
byte-identical responses: search 200 both times, the release page 403 both times
at exactly 6032 bytes. The protection sits on precisely the pages that lead to a
file.

So APKMirror offers a searchable catalogue with no reachable download. **That is
worse than no tab**: it teaches an operator to hunt and then hit a wall. Not built,
for the same reason APKPure was not.

#### ✅ What does work: any F-Droid-format repository

`FDroidSource` already takes a `repo` argument, and the format is not F-Droid's
alone. Both of these answered on first contact, in the same format, publishing the
same digests:

| Repository | Index | Packages |
|---|---|---|
| IzzyOnDroid | 13.9 MB | 1394 |
| F-Droid archive | 111.3 MB | 5030 — older builds of F-Droid apps |

No scraping, the same verification chain, and roughly double the catalogue —
plus, via the archive, the ability to fetch a *specific older build*, which is
exactly the situation R19 ended in (a 32-bit newest, a working older one).

###### ✅ Chunk C3 complete (2026-09-07) — three repositories

**1131 server tests** (5 new). Deployed, no migration. Verified live on the host:

| Repository | Packages | Search |
|---|---|---|
| F-Droid | 4335 | `net.osmand.plus`, newest `531003` (`arm64-v8a`) |
| F-Droid archive | 5030 | reached, older builds |
| IzzyOnDroid | 1394 | reached, no OsmAnd — it is in official F-Droid |

⚠️ **A shared cache filename would have been a real bug, caught before shipping.**
`_index_path()` returned a fixed name, so a second repository's index would have
overwritten the first's. Each index is verified against *its own* `entry.json`, so
the collision would have surfaced as a digest mismatch — or worse, as the wrong
catalogue answering a search. Now keyed by repository name, confirmed on the host:
three separate files.

⚠️ **`name` moved from the class to the instance**, because it is stored as
provenance. A build fetched from IzzyOnDroid and recorded as `fdroid` would be a
lie in the one field that exists to answer where something came from.

⚠️ **The repositories are not equally trusted, and each says so in the picker.**
Official F-Droid builds from source on its own infrastructure; IzzyOnDroid is a
third party shipping mostly developer-provided binaries. Both legitimate, not the
same decision — and listing them side by side without a word would have implied
otherwise.

###### The prior art surveyed, and why only one route survived (2026-09-07)

Four projects were scoped at the operator's request. Recorded so none of this is
re-derived.

| Project | Licence | Verdict |
|---|---|---|
| `anishomsy/apkpure` | Apache-2.0, Python | ✗ APKPure 403s everything; cloudscraper no longer passes the challenge |
| `tanishqmanuja/apkmirror-downloader` | MIT, TypeScript | ✗ search open, **release/download pages 403** — deterministic, byte-identical across rounds |
| `arghya339/apkdl` | **GPL-3.0**, Bash, archived 2026-09-04 | ✗ licence alone bars it: GPL-3.0 cannot enter an Apache-2.0 codebase |
| `StefanescuCristian/Aptoide-Downloader` | **GPL-3.0**, shell | ✗ same licence bar |
| `danieliu/play-scraper` | MIT, Python, archived 2026-03-11 | ✗ **metadata only — cannot download APKs** |

⚠️ **Licence is a first-class filter here, not an afterthought.** Apache-2.0 code
may be used in a GPL-3.0 project; the reverse is not true. Two of the five were
unusable before a line was read.

⚠️ **Cloudflare has settled this category — for the *websites*.** APKPure,
APKMirror and APKCombo all answer 403 to a server. This is not a gap to engineer
around; it is the mirrors deciding they do not serve robots.

⚠️ **Refined 2026-09-08, and the distinction matters.** APKPure also runs a
**mobile app API** at `api.pureapk.com`, which is a different endpoint from the
site that was measured. It answers **200 with no challenge** — it is protobuf,
Cloudflare-fronted but not gated. A hand-rolled request was rejected with
`INVALID_COMMAND`, which says the request was wrong, not that the door is shut.
`EFForg/apkeep` targets exactly this endpoint. So the earlier conclusion holds for
scraping the website and does **not** extend to the app API, which is untested.

**What was learned that has value:**

* Aptoide *does* run a real API and publishes a malware rank and the true signing
  certificate DN (Mozilla's, verified). It was judged more harshly than deserved
  at first — the "decade-old build" was a bad search row, not the catalogue. It is
  still declined: **MD5-only integrity** against ATLAS's SHA-256 design, a
  SHA-1 certificate that cannot be compared with the stored `signature_sha256`,
  `signature_validated: unknown`, and arbitrary user stores as publishers.
* **Mirrors lag the vendor.** Play had Firefox at `155.0.1` while Aptoide offered
  `153.0.4` — a small, concrete argument for vendor-published sources.
* The route worth taking next, if more breadth is ever wanted, is
  **GitHub/GitLab/Codeberg releases**: the vendor's own repository over TLS, an
  API rather than a scrape, and where ATAK plugins actually live. Play is not the
  channel of record for ATAK; tak.gov is, and the TPC tab already reaches it.

###### 🔎 `EFForg/apkeep` — the best-engineered candidate found (2026-09-08)

MIT, Rust, **2049 stars**, maintained by the EFF, **1.0.0 released 2026-04-30**
after 0.17 (2024) and 0.18 (2025). Ships **18 prebuilt release binaries**, so it
integrates as a **subprocess, not a library** — no dependency conflict with this
project's Python stack at all, which every other candidate would have caused.

Read from its source rather than its README:

| | |
|---|---|
| Sources | APKPure (`api.pureapk.com`), F-Droid, Google Play, Huawei AppGallery |
| Integrity | `sha256` ×39, `verify` ×19 across the Rust sources |
| Re-signing | **none** — no `apksigner`, no keystore, no merge |

⚠️ **Its unique value is the APKPure app API**, because everything else it offers
is already covered: F-Droid is built (W97), and its Play path carries the same
Google-account exposure as `gplaydl`. If that path works it is the only licit-ish
route to the proprietary apps; if it does not, apkeep adds nothing this console
lacks.

###### ✅ Tested end to end, with the operator's authorisation (2026-09-08)

The published Windows binary was fetched and its SHA-256 matched the digest GitHub
publishes. *(That proves the transfer, not the provenance — each asset also ships
a `.sig`, which would need EFF's public key to check.)*

**It works, and APKPure's app API is live.** `apkeep -l -a net.osmand` returned 34
real versions including **5.4.3 and 5.4.4 — newer than F-Droid's 5.3.10**. One
download: a **188 MB XAPK in 3.7 seconds**.

**ATLAS ingests its output natively.** `inspect_bundle` parsed it in 1.7s:

    package net.osmand  5.4.4 (code 5404)   label OsmAnd
    minSdk 24  targetSdk 36   signer v3 d192f4ff…
    base 134.6 MB + config.armeabi_v7a.apk 52.5 MB + config.xhdpi.apk 0.8 MB

⚠️ **The very first file it fetched would have broken the fleet — and was caught.**
`abis = ('armeabi-v7a',)` on an **arm64-only** fleet: R19's exact shape. The W96/W97
machinery reads it and preflight would say *2 of 2 reporting devices cannot run
this build*. The guard did its job against a real file from a real source on the
first try.

⚠️ **The architecture must be pinned explicitly — the default is not trustworthy.**
`USAGE-apkpure.md` documents the default as `arch=arm64-v8a;armeabi-v7a;…`, arm64
first. Listing with `-o 'arch=arm64-v8a'` shows 5.4.4 **is** available for arm64.
The download without `-o` still returned armeabi-v7a. Any integration must pass
`-o 'arch=…'` and then verify the result by reading the file, never trust the
ordering. *(The arm64 variant was listed but not downloaded — one download was
what had been authorised.)*

⚠️ **APKPure publishes no hash**, unlike F-Droid, so verification is post-download
by reading the file — which is what `inspect_apk` does anyway. Provenance is a
mirror, not the vendor.

**Verdict: viable.** The only surveyed route that reaches proprietary apps without
a Google account, a copyleft licence, or re-signing. It integrates as a subprocess
whose output goes through the existing ingest path, so identity and signature
continuity are still read from the file.

###### 💡 Deferred: filling in app details (operator, 2026-09-07)

*"keep this in mind if we find a method to pull APK files. this could be a good
way to fill in app details."* — on `play-scraper`, whose metadata is its only
useful half.

**Most of that value does not need Play, and is already in hand.** The F-Droid
index this console parses carries, per app: `name`, `summary`, `description`,
`icon`, `screenshots`, `categories`, `license`, `sourceCode`, `authorName`,
`changelog`, `issueTracker`. Only name and summary are read today; the rest is
parsed and thrown away. Enriching the **ATLAS store** tab for anything in the
three repositories is therefore a parsing change, not a new source — and it costs
no extra request, because the index is already cached.

Where Play would genuinely add something is the **proprietary** apps: ATAK,
Handtevy, ArcGIS, Chrome. For those, note before building:

⚠️ **Store descriptions and screenshots are the publisher's copyrighted content.**
Reading them to decide something is one matter; re-serving them inside an ATLAS
store shown to device users is republication, and that is a licensing question
rather than a technical one. Worth answering before it is built, not after.

⚠️ **`play-scraper` is archived (2026-03-11) and Play's payload is obfuscated and
unstable.** Measured: a version string was extractable for Firefox and not for
ATAK or Chrome, from a 1.2 MB page. Anything built on it inherits that.

⚠️ **The APK already answers some of this.** `inspect_apk` reads the label and
extracts the icon (W51, W53), so the gap is description, category and
screenshots — not identity.

The order that makes sense, if this is ever picked up: use the index metadata that
is already downloaded, then decide whether the proprietary apps justify the rights
question.

###### 🔎 Google Play routes surveyed — one kept open (2026-09-08)

Unlike the mirrors, these speak Play's own protobuf API and pull from Google's
servers: no Cloudflare, no scraping. The obstacles are licence, signing and terms.

| Project | Licence | Last push | Verdict |
|---|---|---|---|
| `yeriomin/YalpStore` | **GPL-2.0** | 2022-09-27 | ✗ Java app; GPL-2.0 is *mutually* incompatible with Apache-2.0 |
| `yeriomin/play-store-api` | GPL-3.0 | 2020-11-16 | ✗ the reusable half, six years stale |
| `whyorean/AuroraStore` | GPL-3.0 | 2026-08-24 | ✗ maintained successor, same copyleft bar |
| `alltechdev/gplay-apk-downloader` | GPL-3.0 | 2026-07-05 | ✗✗ **actively harmful** — see below |
| **`rehmatworks/gplaydl`** | **MIT** | current (`main`) | 🔎 **possible — kept open** |

⚠️ **`gplay-apk-downloader` is the one to refuse outright**, quite apart from its
licence. Its `gplay-downloader.py` carries 177 references to `split`, 70 to
`merge`, 12 to `APKEditor` and — decisively — `apksigner`, `keystore` and
`debug.keystore`. It merges an app bundle and **re-signs the result with a debug
key**. Everything this project has built then breaks by design: `ingest` refuses
the changed certificate, Android refuses the update
(`INSTALL_FAILED_UPDATE_INCOMPATIBLE`, permanently unretryable since W96), and any
app that verifies its own signature fails — which includes ATAK plugins checking
ATAK's. It also commits a 7 MB prebuilt `APKEditor.jar` into the repository.

#### 🔎 `gplaydl` — the candidate, and what must be answered before adopting it

Verified from the repository rather than the README: **MIT, © 2021 Rehmat Alam**,
Python 3, and no signing calls in the package. It downloads base APKs, splits, OBB
and asset packs, and **explicitly does not merge or re-sign** — so the vendor's
signature survives, which is the property everything else here depends on.

It also lands in a shape ATLAS already speaks: `inspect_bundle` handles base +
splits + OBB as `PartRole`s today.

**Open questions, to answer before it becomes a source rather than a bookmark:**

* ⚠️ **The Google account risk is borne by every self-hosting operator.** Its own
  README warns Google may flag, lock or restrict accounts used with it. Unlike
  YalpStore's shared credentials this is an account the operator chooses — better,
  but it is still ToS §3.3, and in a product it becomes a support burden and a
  question at every customer's security review.
* **Token lifecycle**: a companion Android app on a phone mints the token, which is
  then cached on the server. Someone must keep that path alive to re-link.
* ⚠️ **`cloudscraper==1.2.71` is among its `main` dependencies** — the library
  measured on 2026-09-07 as failing against Cloudflare's current challenge on
  three separate sites. Not proof it fails here, but understand what it is for
  before depending on it.
* **Install from `main`, never `master`.** The `master` line is the old 1.3.5
  release pinning `cryptography==2.9` (2020) and `gpapidl`. `main` is small and
  modern: `typer`, `rich`, `httpx`, `cloudscraper`.
* **Pin conflict**: it wants `httpx==0.28.1`; this project pins `0.27.2`.

**It pairs with deferred work, not with today's.** Play serves *device-matched*
builds, which is elegant — and only pays off alongside device-aware resolution,
since resolution currently picks one build per package for the whole fleet.

#### The sanctioned alternative, if Play apps ever become a requirement

**Managed Google Play**, via Google's EMM programme / Android Management API. It
exists for exactly this, carries no terms risk, and is what commercial MDMs use.
It is a project rather than a chunk: EMM registration with Google and an enrolment
model beside the current AOSP Device Owner approach.

⚠️ **Keep the need in proportion.** The apps this fleet depends on — ATAK and its
plugins — come from tak.gov, already integrated. Play would add Chrome, which the
tablets ship newer than anything fetchable, plus Handtevy and ArcGIS, which reach
the library perfectly well by hand.

**Dependencies added:** `httpx` only, already present. `beautifulsoup4` and
`cloudscraper` are **not** added — nothing left to scrape.

### ✅ W96 — Will this build even run here? (R19)

Operator, 2026-09-07, after R19 left the SM-X520 permanently DEGRADED: *"how can
we address R19 for system sustainability when we may not know the architecture of
the deployed device?"*

#### What was actually true before starting

| Fact | State |
|---|---|
| ABIs an APK carries | **never read** — `apk.py` does not look at `lib/` |
| A device's supported ABIs | **never known** — no column, the agent never reports it |
| `min_sdk` per build | **recorded at ingest, then ignored** |
| Version choice | `max(version_code)` among published — **no device parameter** |

⚠️ **This is not an ABI gap, it is a missing compatibility gate.** The identical
bug sits unfired behind `min_sdk`: publish a build needing API 34, hand it to an
API 33 tablet, and `INSTALL_FAILED_OLDER_SDK` loops exactly as Chrome does — with
the data already in the database and nothing consulting it. So the fix is one
predicate over "can this build run on this device", not an ABI special case.

#### R19's root cause, found by probing the real files

`com.android.chrome.apk` inside `Google+Chrome_152.0.7977.82_APKPure.xapk` carries
**`armeabi-v7a` only** — a 32-bit build. The SM-X520 is 64-bit-only, so the native
libraries genuinely cannot be extracted. That is `res=-113` exactly.

⚠️ **Two traps a naive `lib/` scan falls into**, both found in the operator's own
test files:

* The Chrome `.xapk` has **no top-level `lib/` at all** — it is a bundle of four
  split APKs, and a naive scan calls it *universal*, which is the opposite of
  true.
* `ATAK-Plugin-uastool` **does** hold inner APKs, at `assets/apks/DJI/ATAKGo.apk`
  — payloads it ships, not splits it installs. Counting those would misreport the
  ABIs of every ATAK plugin.

So: splits at the archive root count; anything under `assets/` does not.

Known-good answers to test against, all from `Test Files/`:

| File | Expected |
|---|---|
| `ATAK-5.8.0.4` | `arm64-v8a` only |
| `GoTAK-Launcher-1.2.0` | universal — no native libs at all |
| `Microsoft Outlook` | four ABIs |
| `ArcGIS Field Maps` | arm64-v8a + armeabi-v7a |
| `Chrome .xapk` | `armeabi-v7a`, from the split — **not** universal |
| `ATAK-Plugin-uastool` | its own two ABIs; the `assets/` APKs ignored |

#### Chunk C1 — make it visible where it is cheap to fix

Ordered so the payoff comes first: step 1 alone turns an invisible fault into a
line the operator reads *while holding the file*, and touches no resolution.

1. `apk.py` reports the ABIs a build carries — root splits unioned, `assets/`
   ignored, no `lib/` meaning universal.
2. `AppPackageVersion.abis` + a hand-written migration; ingest records it.
3. The console says so on the app and version pages: "any architecture", or the
   list, so `armeabi-v7a` on a 64-bit fleet is legible before it deploys.
4. Tests against every real file above, plus the two traps as their own cases.
5. Full suite, then deploy.

#### Chunk C2 — the device's half, and stopping the pointless retry

5b. **Backfill** `abis` over stored artifacts, so the existing library is
   answerable too — without it C1 helps only future uploads, and the operator's
   own 32-bit Chrome stays unflagged. ⚠️ Reads **every part**, and writes nothing
   for a version whose blobs are all unreadable: "" would claim universal.
6. The agent reports `Build.SUPPORTED_ABIS` and `SDK_INT`; `Device` gains both,
   with a migration.
7. Structural install failures (`NO_MATCHING_ABIS`, `OLDER_SDK`) are reported once
   and **not** retried — the same install cannot succeed, and re-attempting every
   reconcile is noise that hides real failures. Transient ones keep retrying.
8. Agent APK published.

#### Deferred, deliberately

Device-aware resolution (thread the device into `resolve_required_apps`, pick the
newest *compatible* build) and publish-time warnings. Both need C1 and C2's facts
to exist first, and the second changes what "the build this package deploys" means
in the console — a modelling change, not plumbing, and worth its own chunk.

**Chrome needs none of this today**: it is preinstalled as a system app, so
dropping it from required apps and keeping the kiosk tile removes the failure now.
That stays the operator's call.

###### ✅ Chunk C1 complete (2026-09-07)

**1099 server tests** (17 new), deployed, migration `x4z6b8d0f2h4` applied after a
`pg_dump` backup. Every existing row is NULL — "nobody looked" — exactly as
designed.

⚠️ **Migrations do not run themselves on this host.** The `init` container only
builds PKI; `docker compose up -d --build` left `alembic current` one revision
behind head, silently. It took an explicit `alembic upgrade head`. Worth
remembering: the deploy reports success either way.

**All six real files read correctly**, including both traps — the Chrome bundle as
`armeabi-v7a` rather than universal, and the ATAK plugin's `assets/apks/` payloads
ignored.

⚠️ **Two tests failed first, and both were the test being wrong, not the code.**
`build_xapk`'s splits are named `config.arm64_v8a` but carry no `lib/` at all, so
asserting against it would have passed against a base-only read and proved
nothing — the bundle is now assembled with a split that really holds native code.
And the console's version table renders only for the package named in
`?versions=`, which is how a row expands.

**Not done, and worth deciding before C2:** existing library rows stay "not
scanned" until something re-reads them, so the operator's own 32-bit Chrome is
*not* yet flagged in the console. A backfill over stored artifacts would fix that
— `backfill_plugin_api` is the pattern — but it was not in this chunk's plan.

###### ✅ Chunk C2 complete (2026-09-07)

**1105 server tests** and **216 agent tests**. Migration `z6b8d0f2h4j6` applied
after a backup; **agent 0.46.0 (versionCode 91) published**.

#### ⚠️ The backfill answered R19 outright

Run over the real library, it found the operator already holds a Chrome that
works:

| Build | versionCode | Installs on |
|---|---|---|
| Chrome 139.0.7258.158 | 725815833 | `arm64-v8a, armeabi-v7a` |
| Chrome 152.0.7977.82 | 797708200 | **`armeabi-v7a` only** |

`resolve_for_policy` takes `max(version_code)`, so it picks 152 — the one that
cannot install on a 64-bit-only tablet. **Holding 152 makes 139 the answer and
fixes the SM-X520 with no upload at all.** Left to the operator: holding a build
is fleet-wide.

This is also the clearest possible argument for the deferred device-aware
resolution. The right build was in the library the whole time; nothing was capable
of preferring it.

#### What the device now says, and what it stops doing

`Build.SUPPORTED_ABIS` is stored **in the platform's own order**, because that
order is the device's answer to "which of these suits you best" — sorting it would
throw that away. `sdk_int` is separate from `os_version`, which holds a marketing
name ("14") that cannot be compared with an APK's `min_sdk`.

⚠️ **Giving up on a build is not going quiet.** `InstallRetryPlan` stops the
download and the install attempt for a failure that is a property of the build —
ABI mismatch, older SDK, downgrade, signature clash — but the error is still
reported every cycle and the device stays non-compliant. The app really is
missing. A fault that stops being mentioned is a fault nobody fixes.

⚠️ **Unknown failures are retried.** The strings come from `PackageManager` and
are matched as text; treating an unfamiliar one as permanent would strand an app
over a full disk or a truncated download, which is the worse mistake.

⚠️ **The skip is keyed on package *and artifact digest*.** Keyed on the package
alone, a device that rejected one APK would go on rejecting the good one that
replaced it — making the operator's fix invisible, which is precisely the failure
mode this whole work item is about.

**Deferred, unchanged:** device-aware resolution and publish-time warnings. Both
facts now exist to build them on.

### ✅ W95 — Multi-app kiosk: the dock, activities, and where the section sits

Operator, 2026-09-07: *"The multi-app kiosk mode is not allowing more than 1
application into the dock… i expect to be able to put up to 4 icons in the dock.
when adding an app to the multi-app kiosk, i expect a dropdown for the specific
activity to populate based on the selected app. lets also move the subcategory
order so multi app is below single app."*

#### ⚠️ The dock bug is in a layout file, and every layer above it was innocent

Traced before touching anything, because four layers could each have dropped a
favourite and only one had:

| Layer | Four dock apps survive? |
|---|---|
| `form_parse` → spec | ✅ all four, matched by package |
| Save → DB → re-render | ✅ all four checkboxes come back `checked` |
| `LauncherConfigPlan` → `bundle_array` | ✅ one bundle per tile |
| Launcher `LauncherConfig.favorites` | ✅ filters the app list |
| **`item_app_tile.xml`** | ❌ **`layout_width="match_parent"`** |

The dock and the grid share one adapter and therefore one item layout.
`match_parent` is *correct* in the grid — a `GridLayoutManager` reads it as one
column's width. The dock is a **horizontal** `LinearLayoutManager`, where the same
value means the full width of the RecyclerView: tile one fills the dock and tiles
two, three and four are laid out off-screen to the right.

⚠️ **Nothing was lost, so nothing could report a fault.** All four favourites were
in the bundle and on the device the whole time. This is why no test caught it and
no log said anything: the data was right and only the pixels were wrong.

#### Chunk C1

1. `item_dock_tile.xml` at `wrap_content`, and `AppAdapter` takes the layout it
   should inflate. The grid keeps the layout it has — its `match_parent` is right.
2. A test that could actually have caught this: the launcher's JVM tests read the
   two layout files and assert the widths, since a layout bug is invisible to
   every test that only exercises Kotlin.
3. Per-row activity dropdown in the multi-app control, fed by the existing
   `/policies/app-activities` the single-app kiosk already uses. Saved values are
   preserved before the fetch lands, the same way `_activity_choice` does it.
4. Move `multi_app_packages` so **Multi app** follows **Single app**. Group order
   is field declaration order (`grouped_fields`, first-seen), and the two kiosk
   modes currently have four unrelated sub-topics between them.
5. Server tests for the dropdown and the ordering; agent tests run.
6. Deploy the server; build and publish the launcher APK (`versionCode` bumped —
   Android refuses a downgrade).

⚠️ **The dock fix needs a new launcher APK, not just a deploy.** Unlike W92–W94
this one cannot reach a device from the server alone: the layout is compiled into
`com.taksolutions.atlaslauncher`, which ships as its own APK.

**Not doing without being asked:** capping the dock at four. "Up to 4" reads as
the capacity expected, not a limit wanted, and a new refusal would reject policies
that save today.

###### ✅ Chunk C1 complete (2026-09-07)

**1082 server tests** (5 new) and **209 agent tests** (3 new). Deployed, and
**launcher `0.5.0` (versionCode 5) published** — policies now resolve to it.

⚠️ **This one needed an APK, unlike W92–W94.** The width is compiled into the
launcher, so no server deploy could have fixed it. Devices pick it up as they
reconcile, because the kiosk policy already requires the launcher package.

**The layout guard is the unusual part.** `TileLayoutTest` reads the two layout
files off disk and asserts their root widths — the dock's `wrap_content`, the
grid's `match_parent`. Reading XML in a unit test is not how this project tests
anything else, and it is here because the alternative for one attribute is
Robolectric or an instrumented device. Every Kotlin-level test passed while the
dock was broken, and always would have.

**Verified live:** sub-pages now read `Single app, Multi app, Background apps`,
and `resolve_for_policy` returns launcher 5.

###### ✅ Verified on hardware, and it took three launcher builds (2026-09-07)

`R5GL40MMHRN` · SM-X520, profile **W95 dock check**: ATAK, Chrome, uasready,
Handtevy docked; ATAK2M3T on the grid only. Operator confirmed each step by eye,
which is the only instrument that could see any of these.

| Build | What the operator saw | What was actually wrong |
|---|---|---|
| `0.5.0` | four icons, but **bunched in the bottom-left** | a horizontal `LinearLayoutManager` lays tiles from the start and stops |
| `0.6.0` | dock spread evenly across the base ✅ | — |
| `0.7.0` | rows still **stacked close** (12dp added) | the gap was a guess, not a measurement |
| `0.8.0` | ✅ accepted | — |

⚠️ **The first fix was right and insufficient, which is its own lesson.**
`wrap_content` tiles made all four *visible* — that was a real bug and a real
fix — but visible is not arranged. The dock is now a `GridLayoutManager` with one
column per docked app (`DockLayout.spanFor`), so each tile owns an equal share of
the width and centres its icon in it.

That made the separate dock tile layout obsolete, so it was **deleted**:
`match_parent` is correct again now that *both* RecyclerViews are grids, meaning
"fill one cell" to each. The old bug returns the moment anything hands this
adapter a linear manager again, and `TileLayoutTest` says so in as many words.

⚠️ **`grid_row_gap` is the gap you would measure, not the number the decoration
gets.** The tile's own padding is already part of what the eye sees, so
`RowSpacing.extraFor` subtracts it and a test asserts the round trip
(`extraFor(gap, padding) + 2 × padding == gap`). Without that the resource would
be a figure matching nothing on screen, and the next person changing it would be
guessing exactly as 0.7.0 did.

⚠️ **Row spacing is a decoration on the grid, never padding on the tile.** The
dock draws that same tile, so padding there would grow the bottom bar too. This
is the whole reason the mechanism is worth a comment: the obvious fix has an
invisible second effect.

**9 launcher tests**, up from 3. Every one of them reads a layout or a pure
function, because nothing in Kotlin could see any of these faults — no data was
lost and nothing was logged in any of the three rounds.

#### ✅ R19 — resolved 2026-09-07 (Chrome could not install on the SM-X520)

`com.android.chrome` `152.0.7977.82` (code `797708200`) fails with
`INSTALL_FAILED_NO_MATCHING_ABIS … res=-113` — the APK in the library carries no
native libraries for this device's ABI. It leaves the device **DEGRADED** on every
reconcile.

**Not caused by the kiosk, and not fixed here.** The device was compliant only
because nothing had asked it to install that APK; any policy requiring Chrome hits
this. The kiosk's Chrome *tile works*, because Chrome is present as a system app
and the tile opens that one — so the fault is invisible from the home screen and
shows only in compliance.

Fix is the operator's call: upload an arm64-v8a build, or drop Chrome from
required apps and rely on the preinstalled one.

##### How it actually ended, which is not what was predicted

**Chrome `152.0.7977.82` is held.** Policies now resolve Chrome to
`139.0.7258.158`, which carries `arm64-v8a`. `SM-X520` is **COMPLIANT**, no
errors, stable across three minutes of sampling.

⚠️ **The 139 install was never exercised, because the device did not need it.**
The tablet already carries Chrome `733920733` — newer than *both* library builds —
so the agent installed nothing, kept what was there, and filed a warning, which by
design never moves compliance (W50):

> *the device has versionCode 733920733, newer than the 725815833 this policy
> installs. The newer build satisfies the requirement and was kept.*

So the loop stopped because the 32-bit build left the selection, not because a
working build replaced it. At the time this was written the digest-keyed skip in
`InstallRetryPlan` was **unproven on hardware** — no install had been attempted,
and it had been claimed as exercised in the moment when it was not.

###### ✅ Both confirmed on hardware by the operator (2026-09-08)

* **The multi-app kiosk dock** — four icons, spread across the base, rows at 56dp.
  Closes the last row of the W95 build table.
* **The digest-keyed install skip** — `InstallRetryPlan` exercised on the device,
  closing the gap named directly above.

⚠️ **Recorded as an operator observation, not a captured artefact.** No agent log
line or `apply_errors` payload was collected for either, so the evidence here is
the operator's own confirmation rather than something a later session can re-read.
That is enough to call both verified; it is not enough to reconstruct *what* was
seen, which is why the distinction is written down rather than smoothed over.

⚠️ **The device settled the ABI question itself.** On agent 0.46.0 it reports
`supported_abis = 'arm64-v8a'` — no 32-bit support at all — and `sdk_int = 36`. The
whole diagnosis now rests on data the server holds rather than on inference.

**The honest lesson for the library**: requiring Chrome by policy achieves nothing
on this fleet, since the devices ship a newer one than anything uploaded. The
warning says so on every check-in.

### ✅ W93 — ATAK DTED

The last File-management sub-topic. Terrain elevation, shipped as a zip of
longitude-cell folders that must land **directly** in `atak/DTED/`.

#### Ground truth

From `atak-civ` and from the operator's own sample,
`Test Files/DTED.zip` (693 MB, 226 entries):

| | |
|---|---|
| Root of the archive | `w115/` … `w125/` — eleven longitude cells, **no wrapping folder** |
| Inside a cell | `n32.dt2`, `n33.dt2`, … |
| Extensions ATAK knows | `.dt0` `.dt1` `.dt2` `.dt3` — `Dt2ElevationData`, at 1000 m / 100 m / 30 m / 10 m |
| Destination | `atak/DTED/` — `ElevationDownloader` writes `FileSystemUtils.getItem("DTED/" + file)` |
| How ATAK unpacks its own | `FileSystemUtils.unzip(zip, DTED_dir, true)` — **flat into DTED**, then deletes the zip |

⚠️ **I did not find a single "is this a DTED archive" function in ATAK to
mirror**, unlike `HasManifest` for data packages. The detection here is built
from the layout ATAK's own hemisphere archives use, its extension list, and the
sample — stated plainly because it is a weaker provenance than §11's.

⚠️ **The sample is full of macOS pollution**: `__MACOSX/`, and `._n33.dt2`
*inside* the real cell folders. `FileDeployer.isArchiverJunk` already drops
these, proven by the existing extraction path — so detection must ignore them
too, or a cell that holds only AppleDouble files would look real.

#### Decisions

⚠️ **A wrapped archive is refused, not silently fixed.** If the cells sit under a
folder — `DTED/w115/…`, which is what right-clicking a DTED directory in Windows
produces — a flat extract into `atak/DTED` yields `atak/DTED/DTED/w115` and ATAK
finds nothing. The agent's `extract` writes entries at their own names and cannot
strip a prefix, so supporting it would cost an agent release. **The operator's
own sample has no wrapper**, so the cheap, honest move is to refuse with a
message saying exactly what to re-zip. Stripping can be added if a real archive
turns up needing it.

⚠️ **Size is the real risk, and it is not solved here.** The sample is 693 MB and
the upload path reads the whole file into memory — the same shape that carries a
130 MB APK today, five times bigger. Worth watching on the first real upload;
the fix, if needed, is streaming ingest, which is its own piece of work.

##### Chunk C1 (6 steps)

1. `app/artifacts/dted.py` — recognise a DTED archive and describe it: cells,
   file counts, the levels present. Junk-aware; refuses a wrapped one with the
   reason.
2. `dted_archives` on the FILES spec, and the sub-page replacing the D94 stub.
3. Resolution: destination `/sdcard/atak/DTED`, `extract: true`. ⚠️ **`persist`
   stays true**, unlike a data package — ATAK reads DTED from disk forever, so a
   deleted cell should come back. Nothing re-imports, so there is no loop to
   avoid.
4. **General Files refuses a DTED archive** and names this sub-topic, exactly as
   it now does for data packages.
5. Upload with a validation modal on the sub-page, reusing the package pattern.
6. Tests against the real sample, then deploy.

Hardware verification is separate, and cheap: R1 already proved a zip extracting
into `/sdcard/atak/DTED` on `SM-X520` — that was literally the DTED case.

###### ✅ Chunk C1 complete (2026-09-07)

**1066 server tests** (17 new in `tests/test_dted.py`). File management now has
three real sub-topics and no stub.

**Against the operator's own 693 MB sample:** 11 cells `w115`–`w125`, **68
terrain files out of 226 zip entries** — the other 158 are macOS metadata.
Inspection is instant because it reads the zip's central directory only; the size
never has to be decompressed to answer the question.

⚠️ **`persist: True` for terrain, the opposite of a data package.** The two ATAK
file types look alike — both zips, both ATAK-specific, both with a fixed
destination — and behave oppositely. A package must never be re-sent, because
re-writing it makes ATAK import again; terrain is read off the disk forever and
nothing re-imports it, so a cell someone deleted should come back.

⚠️ **A test caught the design contradicting itself.**
`test_an_ordinary_zip_is_still_accepted`, written during B7, uploaded
`w125/n32.dt2` under the name "DTED w125" as its example of a harmless archive.
W93 correctly began refusing it — it really was terrain. The fixture became a
bundle of imagery, which is the honest example of what General Files is still
for.

**Three tests changed rather than being deleted**, each because its guarantee
moved: the DTED stub assertion (the stub is gone by design), the General Files
note (it now names both ATAK types), and the one above.

⚠️ **A fourth "change" was an accident, caught before the deploy.** Rewriting the
tail of `test_data_packages_ui.py` to replace the stub assertion truncated the
file, taking the whole B4 section with it — 13 tests covering
`/policies/data-package/upload` and `/create`, which were then not covered by
anything. The suite still passed, at 1052, because deleted tests do not fail.
A green run says nothing about tests that are no longer there; the diff stat is
what showed it (`5 insertions, 177 deletions` for a one-test edit). Restored, and
the real total is 1066.

---

### ✅ W94 — DTED: unpack nested archives instead of refusing them

Operator, 2026-09-07: *"i need the dted installer to recognize presence of dted
folders and files and have the abilty to unpack appropriately, even if the
uploaded zip has nested folders."*

This **reverses W93's wrapped-archive refusal**. W93 was right that the layout
matters and right that the device cannot report it; it was wrong to stop at
saying no, because the archive an operator actually has — right-click a DTED
folder in Windows — is the nested one, and re-zipping it by hand is work ATLAS
can just do.

#### Where the fix goes, and why not in the agent

The agent could flatten at extraction time, and that reads as the natural home
for it. It was rejected: it needs an APK, and until every device has taken it, a
device on the old build handed a nested archive places the terrain wrong **and
says nothing** — the exact silent failure this feature exists to prevent. There
is no way to make an unknown key fail loudly on an old agent.

Repacking at upload keeps the invariant that **what ATLAS stores is exactly what
lands on disk**. The agent stays dumb, and every fielded device is correct the
moment the server deploys — the same server-only reach that made D92 and the data
packages cheap.

**Measured before choosing**, on the operator's 726 MB sample: 226 entries,
1.75 GB uncompressed, and a full repack costs ~56s — 34 MB/s recompressing,
which is all of it; decompression runs at 423 MB/s. That fits the admin route's
330s proxy timeout with room. It is also paid **only when the archive is
nested**: a flat one is stored byte-for-byte as uploaded.

#### Chunk C2

1. `dted.plan_layout()` — pure: map every entry to where it must land, flatten
   cells found at any depth, drop archiver junk, and refuse a genuine conflict
   (two different files claiming one cell path) with both paths named.
2. `dted.repack()` — stream entry by entry to a destination stream, so 1.75 GB
   never lands in memory at once.
3. `files.ingest_stream()` — store from a stream; `ingest_file` becomes a thin
   wrapper, so the repacked temp file is not copied into memory a second time.
4. `/policies/dted/upload` accepts nested, repacks when needed, and reports what
   it did. Still refused: no cells at all, not a zip, conflicts.
5. The check modal says the archive was re-packed and what moved. General Files
   still refuses terrain and names the sub-topic — unchanged.
6. Tests, including the real sample nested inside a folder, then deploy.

⚠️ **W93's tests assert the old contract and will be changed deliberately** —
`test_a_wrapped_archive_is_refused_with_the_reason` and its upload twin. They
were correct for the design they were written against; the design moved. Editing
them is not the same as the accidental truncation above, and the diff stat gets
checked either way.

###### ✅ Chunk C2 complete (2026-09-07)

**1077 server tests** (28 in `tests/test_dted.py`, up from 17). Server-only
deploy — no APK, no migration.

**Verified at real scale, not just on toy zips.** The operator's 726 MB sample
repacked in **46.4s**, with **68 of 68 CRCs unchanged**, every terrain path at
depth 1, and the 158 archiver-junk entries dropped. Toy fixtures would not have
exercised zip64 or the streaming path at all.

**What still gets refused**, so the tool has not become permissive: a zip with no
cells anywhere, something that is not a zip, and — the only new one — a genuine
collision, where two entries would both become `w115/n32.dt2`. Picking a winner
there would silently discard terrain.

⚠️ **The repack is a change to the operator's file, so the modal says so** and
stays open to say it. The stored archive is not the one they uploaded; someone
comparing checksums later deserves the reason. A flat archive is stored
byte-for-byte and pays none of this.

**Planning is separate from repacking** (`plan_layout` takes names, nothing
else). That is what lets the real sample be tested against the nested case
without a minute of recompression per run.

### ✅ W92 — Field tips instead of placeholders, sitewide

Operator, 2026-09-07: remove placeholders from text fields and use a visible tip
above or below the field instead.

⚠️ **The reason is not tidiness.** A placeholder renders as grey text *inside*
the box, which reads as a value the field already holds. An operator leaves it
and saves — and for the General Files destination the spec then refuses the entry
for having no destination, so the hint meant to help is what caused the
rejection. It is also invisible the moment anyone types, which is exactly when a
format hint is most wanted.

#### The 41 placeholders are not one thing

Surveyed before touching any: they fall into groups that deserve different
answers, and a blanket removal damages two of them.

| Group | Example | Decision |
|---|---|---|
| **State** | `not managed`, `not set` | ✅ **Kept** (operator, 2026-09-07) |
| **Filter / search** | `Filter by name, serial, model…` | Tip below |
| **Example values** | `com.example.app`, `/sdcard/atak/imagery` | Tip — the harmful group |
| **Optionality** | `Label (optional)`, `extract to (opt)` | Tip |
| **Instructions** | `leave blank for an open network` | Tip |

⚠️ **"not managed" is kept because it is not a hint — it is the field's state.**
Blank genuinely *means* unmanaged in W10's tri-state design, so the placeholder
describes what is true rather than suggesting what to type, and nobody can leave
it and save the wrong thing. A tip above it would repeat what the empty box
already says.

##### Plan (6 steps)

1. **One `.field-tip` class** in `atlas.css` — muted, small, sitting tight under
   its field. One class, so the console does not grow three shapes of hint.
2. **A `tip()` macro** in `_macros.html` for template use, so a tip is one call
   rather than a hand-rolled `<p class="muted">` each time.
3. **Convert the harmful groups** — example values, optionality, instructions —
   across the 13 templates.
4. **Filters and searches** get a tip below, since their placeholder was their
   only label.
5. **The General Files destination** moves from the `title=` tooltip added an
   hour ago to the same `.field-tip`, so the console has one idiom rather than
   two. ⚠️ That supersedes the tooltip, deliberately.
6. Tests asserting no `placeholder=` survives outside the state group, and that
   each converted field kept its guidance. Then deploy.

⚠️ **Placeholders set from `atlas.js` count too** — four of them, on rows the
script builds. A rule that holds only in Jinja is a rule that decays the moment a
row is added at runtime.

###### Done (2026-09-07)

**36 placeholders removed across 13 templates and 2 in `atlas.js`**; 3 state
placeholders kept. **1041 server tests** (5 new in `tests/test_field_tips.py`).

⚠️ **The rule is enforced at source, not by rendering.** Checking pages would
only cover the handful a test happens to fetch, and the next placeholder would
land in whichever template nobody asserts against. `test_field_tips.py` reads the
templates and the script directly.

⚠️ **`test_wallpaper.py` already recorded this bug once**, for one field: an
enrolment placeholder reading `TAK-Field` was kept by an operator as if it were a
real SSID. W92 is that fix generalised, and the test moved to the new markup
rather than being deleted — its guarantee never changed.

⚠️ **Two script placeholders were kept and commented**, both of the form
"default: X" / "not set". They say *what happens if you leave this blank*, which
is state and cannot be mistaken for something the operator typed.

⚠️ **A self-inflicted regression worth recording.** The first pass tidied the
whitespace left by the removal with `[ 	]{2,}` before an attribute — which also
collapsed the **indentation of every continuation line**, 55 of them across the
templates. Reverted with `git checkout` and redone with a pattern that takes only
the single space before `placeholder=`. ⚠️ A cleanup regex that is not anchored
to what it is cleaning will find something else to match.

### 🚧 W91 — File management: General Files, ATAK Data Packages, ATAK DTED

Operator, 2026-09-07: split the File management category into sub-topics. The
current file setup becomes **General Files**; **ATAK Data Packages** and **ATAK
DTED** are new. DTED is explicitly deferred until data packages are done, so it
ships as a D94 stub sub-page — the mechanism ATAK Config already uses for
*Plugin behavior*.

#### Ground truth from the ATAK source, before any code

Read out of `atak-civ` (`com/atakmap/android/missionpackage/`), not recalled.

**A data package is a zip containing `MANIFEST/manifest.xml`**
(`MissionPackageBuilder.MANIFEST_PATH = "MANIFEST"`). The document is:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<MissionPackageManifest version="2">
  <Configuration>
    <Parameter name="uid" value="…"/>
    <Parameter name="name" value="…"/>
  </Configuration>
  <Contents>
    <Content ignore="false" zipEntry="path/inside/the/zip.kml"/>
  </Contents>
</MissionPackageManifest>
```

**What ATAK actually requires**, from the `isValid()` chain:

| Rule | Source |
|---|---|
| `version` attribute, `2` | `@Attribute(name="version", required=true) private int VERSION = 2` |
| `<Configuration>` and `<Contents>` both present | both `@Element(required = true)` |
| Configuration has **more than one** parameter, **and** `name`, **and** `uid` | `MissionPackageConfiguration.isValid()` |
| Every `<Content>` carries `zipEntry` | `@Attribute(name="zipEntry", required=true)`; `isValid()` is `!isEmpty(_manifestUid)` |
| The manifest is found by **`entry.getName().endsWith("MANIFEST/manifest.xml")`** | `MissionPackageExtractorFactory.HasManifest` — which is exactly why nesting works |
| `<Contents>` may be **empty** | `MissionPackageContents.isValid()` returns `true` unconditionally |

⚠️ **Content paths are relative to the MANIFEST directory, not the zip root.**
`<zip>/MANIFEST/manifest.xml` requires `<zip>/test.kml`, but
`<zip>/mydata/MANIFEST/manifest.xml` requires `<zip>/mydata/test.kml` — ATAK
supports the nested form because that is what a Windows right-click "compress
folder" produces. A validator that only looks at the zip root will reject
perfectly good packages.

#### ⚠️ The destination in the request does not match the source

The request says push to `tools/datapackage/incoming`. The source says that is
the wrong directory, and says so twice:

| Directory | What `MissionPackageFileIO` does with it |
|---|---|
| `atak/tools/datapackage/` | **Watched.** Comment: *"watch missionPackageDir, auto-import any .zips found there (e.g. received or **manually placed**), no HTTP serving, **no auto-cleanup**"* |
| `atak/tools/datapackage/incoming/` | **`// no watch`**, and registered with `DirectoryCleanup`, which **deletes anything older than 2 hours** |

Every use of `incoming` in the tree is a landing area for **network** transfers —
`MissionPackageReceiver` writes a `UUID.randomUUID()` temp file there and the
downloader processes it explicitly afterwards. Nothing scans it for manually
placed files.

So a package pushed to `incoming` is likely to be **silently deleted two hours
later having never been imported** — the "fails green" shape this project keeps
running into. The watched parent directory is what the source says to use for a
manually placed zip.

✅ **Settled with the operator, 2026-09-07: `atak/tools/datapackage/`** — the
watched directory the source points to. Asked rather than guessed, because the
operator has hardware experience here and their ATAK build could have differed
from the source; it did not.

⚠️ **The operator's core instruction stands regardless, and matters more in the
watched directory**: the watcher imports whatever appears, so a package the MDM
keeps re-writing is a package ATAK keeps re-importing.

⚠️ **ATAK itself accepts a zip with no manifest** — `GetExtractor` falls back to
`PlainZipExtractor`. Rejecting those is a deliberate **MDM-side** rule the
operator asked for, not ATAK's: a plain zip is extracted with none of the
manifest's placement or `onReceiveImport` semantics, so what lands where is far
less predictable. Worth saying out loud in the rejection message so nobody
concludes ATAK cannot read their file.

#### ✅ Deliver-once is `persist: false`, and it is already hardware-proven

⚠️ **Corrected 2026-09-07. The earlier claim here — that data packages needed a
new agent mechanism — was wrong**, and it was wrong in the way this project's own
documentation warns about: `FileDeployer.isDeployed` was read, its
presence-based docstring taken at face value, and the **caller never opened**.

`Reconciler.applyFile` consults `isDeployed` **only when `persist` is true**:

```kotlin
if (config.appliedFileHash(key) == sha) {
    val persist = entry.optBoolean("persist", true)
    if (!persist) { …; return emptyList() }        // never re-pushed, absent or not
    if (deployer.isDeployed(entry, size)) { …; return emptyList() }
    // persisted but missing → replace
}
```

So `persist: false` already means **placed once, remembered by content hash, and
never re-pushed even when the file is gone** — exactly what a data package needs,
because ATAK consumes the zip and absence is the *expected* end state.

**Proven on `SM-X520`, 2026-09-01**, by a differential test where two files were
deleted in the same breath and one reconcile pass produced opposite outcomes
decided purely by the flag:

```
4de83813 already placed at /sdcard/atak/DTED; not persisted, leaving it
39c93edb is persisted but missing or incomplete at /sdcard/atak/imagery; replacing
```

⚠️ **And the re-download primitive already exists too.** The marketplace's untick
calls `config.forgetAppliedFile(FileDeployer.stateKeyFor(entry))` so the user can
take a file again — hardware-proven in the same run ("delete it, tick again →
re-pushed, so the record was forgotten rather than the file abandoned").

**What actually remains for B3 is therefore much smaller**: resolve
`data_packages` into FILES entries server-side (fixed destination,
`persist: false`) the way ATAK Config resolves into `app_configs` (D92), and add
the device-side affordance below.

##### ✅ Chunk B1 complete (2026-09-07) — the manifest contract and the sub-topics

**983 server tests pass** (26 new, in `tests/test_mission_package.py`); no
existing test changed behaviour.

1. ✅ `app/artifacts/mission_package.py` — `inspect()` applies ATAK's own
   `isValid` chain and refuses with a reason worth showing an operator.
2. ✅ `build()` — name + files → a conforming package. A package it builds
   round-trips through its own validator, which is the property that makes
   *Create Data Package* and *upload* the same thing to a device.
3. ✅ File management now splits **General Files** / **ATAK Data Packages**;
   `form_parse` and a list control follow.
4. ✅ **ATAK DTED** is a D94 stub sub-page, the same mechanism *Plugin behavior*
   uses in ATAK Config.
5. ✅ Tests written against ATAK's requirements rather than this module's
   conveniences — including the nested-MANIFEST layout, the empty-Contents case
   ATAK allows, and the traversal and MANIFEST-shadowing refusals.
6. ✅ Recorded as **§11** of `docs/ANDROID_PLATFORM_REFERENCE.md`, with sources.

⚠️ **`DataPackageEntry` deliberately has none of `FileEntry`'s controls** — no
`dest_path`, `persist`, `overwrite` or `availability`. ATAK watches one
directory, so there is no destination to choose; and every one of the others
expresses some form of *"put it back if it goes away"*, which is the single
instruction that must never reach a device here. The spec refuses them rather
than ignoring them.

⚠️ **Refusing a manifest-less zip is ATLAS's rule, not ATAK's** (§11c), so the
rejection says ATAK would have taken it. Otherwise the operator goes hunting for
a fault in a file that does not have one.

##### ✅ Chunk B2 complete (2026-09-07) — upload and create, in the console

A data package is an ordinary `ManagedFile` — same artifact store, same dedupe,
same reference counting and delete. What it needs is to be **distinguishable**,
so the policy picker can offer packages rather than arbitrary zips.

⚠️ **`is_archive` is the precedent, and its comment is the argument**: *"detected
at upload, so the policy layer can refuse a non-archive for extraction instead of
failing on the device."* Same reasoning, same shape.

1. **`managed_file.is_data_package`** — boolean, `server_default false`, set at
   ingest by running the B1 validator. Hand-written migration: autogenerate never
   infers `server_default`, and a `NOT NULL` column added without one fails on
   Postgres against a table with rows (Operational notes).
2. **Upload path** — validate on the data-package route and reject with the B1
   reason verbatim. An ordinary Content upload is unaffected; a zip is still just
   a zip there.
3. **Create Data Package** — a modal taking a name and several files, building
   the zip server-side with `mission_package.build`, and ingesting the result. It
   round-trips through the same validator an upload does.
4. **Content page** — show a package as one: manifest name, uid, how many
   entries, and any the manifest names but the zip lacks.
5. **The policy picker** offers only validated packages.
6. Tests, and update this file.

⚠️ **Two uploads of identical bytes dedupe to one artifact but two
`ManagedFile` rows.** That is existing behaviour and fine for content; it becomes
a question for B3, where "have I delivered this?" needs an identity. Noted here so
the B3 decision is deliberate rather than inherited.

**1001 server tests pass** (18 new, in `tests/test_data_packages_ui.py`). The
migration was applied to a **seeded** database and rolled back again, per the
Alembic note — not to an empty one, where a missing `server_default` would not
have shown.

###### Two bugs worth keeping, both silent

⚠️ **`fastapi.UploadFile` is a *subclass* of `starlette`'s, and
`request.form()` yields the base class.** So `isinstance(u, UploadFile)` against
the FastAPI import matched **nothing**, every attached file was discarded, and
the route reported *"a data package needs at least one file"* while the operator
looked at the files they had just attached. The isinstance check now names
`starlette.datastructures.UploadFile` explicitly, with the reason.

⚠️ **Jinja macros do not inherit the page context** — the trap already documented
for `atak_target` — so `data_package_files`, dutifully added to `_form_catalogs`,
was Undefined inside the macro and the picker rendered empty with no error.
Fixed by *deleting* that plumbing: `managed_files` is already threaded through
every control and carries `is_data_package`, so the macro filters the list it
already has. One list, one source, nothing to keep in step.

⚠️ A third, caught by a test rather than by reading: the "manifest names files
this zip lacks" warning first landed **inside** the *Deployed by* table's `else`
branch, so it only rendered for packages a policy already used — the least likely
case to be looked at.

##### ✅ B7 (2026-09-07) — General Files refuses a data package outright

Operator, 2026-09-07: the steering note is not enough — refuse it and point at
the tool.

⚠️ **The failure it prevents is total silence.** Accepted as an ordinary file a
package goes wherever the destination says, which is not a directory ATAK
watches: no import, no error, nothing in any log, and a policy that looks
perfectly healthy. The note beside the control only helps an operator who reads
it, and the one who needs it is the one who did not.

**The test is ATAK's own.** `mission_package.has_manifest` mirrors
`MissionPackageExtractorFactory.HasManifest` — `endsWith("MANIFEST/manifest.xml")`
and nothing more.

⚠️ **Deliberately laxer than `inspect`.** A zip with a *broken* manifest is
refused here too. `inspect` asks "is this a good package"; `has_manifest` asks
"was this meant to be one", and the second is the right question when deciding
which path an upload belongs in — a zip somebody built as a package does not
become an ordinary file by being malformed. Refusing it sends them to the tool
that can say what is actually wrong with it, which this route cannot.

⚠️ **An ordinary zip is still accepted**, because the refusal keys on the
manifest rather than on being an archive — a DTED archive or a bundle of imagery
is exactly what this section is for.

**1049 server tests.**

##### ✅ B6 (2026-09-07) — General Files: upload in place, packages kept out

Operator, 2026-09-07. Three changes, one of them a deliberate omission.

**Upload from the section**, the same shape as the data-package one: posts by
script, reports inline, returns an id the unsaved form holds. `in_library` is
**true** — a file deployed to devices is fleet content, unlike W46's wallpaper.
The new row lands with an **empty destination** on purpose: where a file belongs
is the operator's decision, there is no sensible default, and the spec refuses an
entry without one, so a forgotten destination fails at save rather than on a
device.

⚠️ **Data packages are filtered out of the General Files picker.** Placed through
this section a package would carry a hand-typed destination and a `persist`
control, and either one set wrongly is a package ATAK re-imports on every sync.
The ATAK Data Packages sub-topic fixes both, which is the entire reason it is a
separate field.

⚠️ **A package a policy *already* places still renders**, matched by
`entry.file_id`. Filtering a picker must not silently drop a selection: an older
policy that placed a package through General Files stays visible and editable
instead of losing its file on the next save.

⚠️ **The omission is explained where it happens.** A picker that quietly leaves
something out teaches nothing — the section says data packages belong in their
own sub-topic, and why.

⚠️ **No manifest check on this route, deliberately.** It carries a `.pref`, a
certificate, a map source, a zip to extract. Nothing stops a package going
through it; what makes a package work is the delivery settings, not the bytes,
and those are what the other sub-topic fixes.

**1034 server tests.**

##### ✅ B5 (2026-09-07) — the upload reads as an action, and the check has a surface

Operator, after testing B4: a real package was accepted, a plain zip refused, and
Create worked. Two things to fix, both about where the operator's attention is.

⚠️ **The upload control was styled text, not a button.** It was written as
`<label class="ghost">`, and `button.ghost` is the styled selector — `label`'s own
rule (block, muted, 12.5px) wins, so it rendered as grey clickable text that did
not read as an action. Now a real `<button>` clicking a hidden file input.

⚠️ **A refusal was a line of muted text beside the control.** On a page holding an
entire policy that is easy to miss, and the refusal is the *whole point* of
checking here — a package ATAK will not import fails on a tablet as nothing at
all. Uploading now opens a modal that shows the check running and keeps it open
on failure with the reason.

**Accepted packages close the modal immediately** and let the new row be the
confirmation, rather than making an operator dismiss a dialog to see what they
just added. The status line carries the manifest's content count, so it says
*what* was accepted — which is how someone notices they picked the wrong file.

The "ATAK would have taken this" note shows **only** for the manifest refusal.
For that one it is reassurance; on any other failure it would be noise.

**1026 server tests.**

##### ✅ Chunk B4 complete (2026-09-07) — upload and create from inside the policy

**Operator, 2026-09-07:** the ATAK Data Packages sub-page should let an operator
**upload a package zip** (manifest-checked) or **create one** through the modal,
without leaving the policy. The result lands in the Content section like any
other package.

⚠️ **The picker stays.** An earlier reading of "none of the file managers should
pull already-uploaded data" would have removed it; the operator said to disregard
that. This chunk is purely **additive**.

The precedent is W46's in-policy image upload: post the bytes, get an id back,
and let the still-unsaved form hold it. `in_library` differs deliberately — a
wallpaper is `False` because picking an image for one policy is not publishing a
fleet asset, whereas here the operator explicitly asked for the package to reach
Content.

1. **`POST /policies/data-package/upload`** — JSON in, JSON out, reusing
   `data_packages.ingest_upload`. Returns `{id, name}` or `{error}` with the
   validator's own words.
2. **`POST /policies/data-package/create`** — the same, over
   `data_packages.create`, taking a name and several files.
3. **The sub-page**: an upload control and a *Create data package* button beside
   the existing list, which already removes rows.
4. **The modal**, matching the Content page's — name, description, repeatable
   file rows.
5. **JS**: post, then append a row from the returned id. ⚠️ Errors render
   **inline**; a redirect would throw away every unsaved change on a page that
   holds the whole policy.
6. Tests, state file, deploy.

⚠️ **Both routes must go through `data_packages`, not re-implement it.** The
console would otherwise have two definitions of "is this a data package", and the
one an operator hit would decide whether their file was accepted.

**1022 server tests pass** (10 new). Both routes call `data_packages`, and a test
takes a package built through the policy editor and runs it back through the
upload validator — the property that stops the two paths drifting into "works
when built here, refused when uploaded".

⚠️ **The modal is mounted outside the sub-page and posted by script.** HTML
forbids a nested `<form>` and this markup sits inside the policy's own, so the
fields are gathered with `FormData` instead. Submitting normally would post the
*policy* — every category of it, half-filled.

⚠️ **Nothing here redirects.** The editor holds an entire unsaved policy, so a
failed upload reports inline and a successful one hands back an id the form keeps
until the operator saves. The wallpaper upload (W46) answers the same way for the
same reason; the difference is `in_library`, left **true** here because the
operator asked for packages to reach the Content section — a package is fleet
content someone may reuse, not an asset private to one policy.

##### ✅ Chunk B3 complete (2026-09-07) — deliver once, re-download on demand

**Operator's design, 2026-09-07:** the policy delivers a package once; it then
lives in the DPC's Files section with a **Re-download** button that sends it
again on demand. That turns re-delivery into a deliberate act on the device
instead of a policy that loops — and it lands almost entirely on machinery that
already exists and is hardware-proven (see the corrected note above).

1. **Resolve `data_packages` into the files payload**, in
   `files.resolve_files`, alongside `entries`. Fixed
   `dest_path = /sdcard/atak/tools/datapackage`, `persist = false`,
   `overwrite = always`, `extract = false`. Same move as ATAK Config resolving
   into `app_configs` (D92): **no new delivery path and no new device contract**,
   so the agent's existing reconcile carries it unchanged.
2. **Flag the entry** `data_package: true` in the resolved payload. The agent
   needs it only to render the card differently — the delivery decision is
   already `persist`.
3. **Agent: the card.** ⚠️ A delivered package would otherwise render with the
   presence-based **"Pending"** pill, which becomes permanently wrong the moment
   ATAK consumes the zip — the file is *supposed* to disappear. It reads
   **Delivered** instead, decided by the applied-content record rather than by
   looking at the disk.
4. **Agent: Re-download**, calling `config.forgetAppliedFile(stateKeyFor(entry))`
   then a sync — the same primitive the marketplace's untick already uses and
   that hardware already proved re-pushes.
5. **Tests** both sides: the server's resolution and its fixed destination; the
   agent's card decision as a pure function, so it is testable off-device.
6. **Agent release** (version bump, build, publish through the update channel)
   and a server deploy.
7. **Hardware verification** on `SM-X520`: the package lands in
   `tools/datapackage`, ATAK imports it, the file goes away, the card still says
   Delivered and **does not** re-push, and Re-download sends it again exactly
   once.

⚠️ **"Delivered" is the strongest claim ATLAS can honestly make.** Whether ATAK
then *imported* the package is not observable from here — the watcher leaves no
trace the MDM can read, and the zip vanishing is equally consistent with import
and with a user deleting it. Saying "Imported" would assert something unknown,
which is the failure this codebase keeps designing against. The same distinction
as W90's `applied N config keys` proving the Bundle was set and nothing more.

⚠️ **Re-download is per device and per file id.** The state key is
`file_id|dest_path`, so a package re-uploaded to the library as a new row is a
new identity and delivers again on its own — two levers, both explicit, neither
requiring new schema.

###### ✅ On hardware — `SM-X520`, 2026-09-07

The agent's own log, device-local:

```
14:03:36 I/Reconciler:   deploying 0e53d351… to /sdcard/atak/tools/datapackage
14:03:36 D/FileDeployer: resolves to /storage/emulated/0/atak/tools/datapackage
                         (all-files access: true)
14:03:36 I/FileDeployer: placed …/tools/datapackage/atlas-test-overlay--w91.zip (674 bytes)
14:06:06 D/Reconciler:   already placed …; not persisted, leaving it
```

| Claim | Result |
|---|---|
| Lands in the watched directory | ✅ |
| **Not re-pushed on the next reconcile** | ✅ `not persisted, leaving it`, 2½ minutes later |
| ATAK imports it | ✅ operator confirmed the overlay in ATAK |
| The zip survives the import | ✅ — and **contradicts what this file first claimed**, see below |
| **Re-download** re-sends it | ✅ operator confirmed |
| `incoming/` also imports | ✅ **unexpectedly** — see R17 |

⚠️ **Both directories work, and only one of them should.** A second package was
delivered to `tools/datapackage/incoming/` as an experiment, with a Los Angeles
placemark against the first package's San Diego one so the outcome could not be
misread. It imported. The source says it cannot: that directory is `// no watch`,
the parent's watcher is provably non-recursive, and nothing else in `com/atakmap`
touches it. **The mechanism is unidentified** — R17.

The destination is now `incoming/` by operator decision, for the one advantage
the source does support: `DirectoryCleanup` sweeps it after two hours, where the
watched parent keeps every package ever delivered. ⚠️ That sweep is **expected,
not observed**, and if it turns out not to happen the reason for the choice
evaporates — also R17.

The tablet had already self-updated to **0.45.0** over the agent-update channel
by the time the package arrived, so the Delivered pill and the button were live
without anyone sideloading anything.

⚠️ **Cosmetic flaw the run exposed:** the file landed as
`atlas-test-overlay--w91.zip` — `" ("` is two characters and each became its own
hyphen. `_slug` now collapses runs. It is the name an operator reads in ATAK's
own directory, so it is worth the two lines.

###### Built (2026-09-07)

**1012 server tests + 206 agent tests pass** (11 and 8 new). Agent **0.45.0
(90)** built and staged; server and agent deployed together to
`209.182.235.108`.

* `files.DATA_PACKAGE_DEST` = `/sdcard/atak/tools/datapackage`, and a test
  asserts the destination does **not** contain `incoming` — the mistake the
  request originally carried, kept as a regression guard rather than a memory.
* `resolve_files` folds `data_packages` into the same `required` list as ordinary
  files with `persist: false`, `overwrite: always`, `extract: false`. **No new
  device contract**, so the agent's proven reconcile carries it.
* `FileCardPlan` decides what a card claims, as a pure object testable off-device
  — the `*Plan` convention this codebase uses wherever a *judgement* hides inside
  a rendering.
* `MainActivity.redownloadPackage` drops the applied-content record and syncs.

⚠️ **The card reads the record, not the disk.** `deliveredOnce` compares
`config.appliedFileHash(stateKey)` against the entry's sha; the presence check is
never consulted for a package. The disk cannot answer the question: the file
being gone is not a failed delivery, and re-writing it is what makes ATAK import
the package a second time.

⚠️ **Corrected by hardware, 2026-09-07.** This section first said "ATAK consumes
the zip, so absence is the expected end state". It does not — ATAK imported the
package and **left the file in `tools/datapackage/`**, exactly as that
directory's `no auto-cleanup` note implies. The consuming behaviour belongs to
`incoming/`, and was assumed onto the watched directory. **The design is
unchanged and the reason is different**: deliver-once matters because re-writing
a watched file re-imports it, not because the file disappears.

⚠️ **Re-download is offered only after delivery.** Before that the reconciler is
still going to place the package by itself, and a button racing the reconciler is
a button that sometimes appears to do nothing.



### ✅ W89 — sweeping the backlog W88 could not reach

W88 stopped the artifact cache growing, but left everything already on the three
fielded devices. The reason is structural: a device only revisits an app's files
when it has something to install, and an app already installed never gets that
far. The cleanup had to come from the other direction — asking of each cached
file *is there a remaining reason to keep this?*

⚠️ **"Unreferenced" is the wrong question, and getting it wrong keeps the whole
backlog.** A spent APK is still named by the very policy that installed it, so a
sweeper testing references first deletes almost nothing. `ArtifactSweepPlan`
tests **spent** first: an app the device already has, decided by `AppUpdatePlan`
rather than by comparing version codes a second time. Every outcome except
INSTALL and UPGRADE means nothing will ever be installed from those files —
including REFUSED_DOWNGRADE and SKIP_PINNED, where the reconciler has already
decided it will not use them.

⚠️ **The references are found by walking the bundle, not by reading the fields we
know about.** A sweeper enumerating *apps, files, wallpaper…* would quietly start
deleting live artifacts the day the server grew a new kind, and the symptom would
land on a fielded device as something that re-downloads forever. Anything shaped
like a sha256 is treated as referenced; at worst it keeps a file it needn't.

⚠️ **`MIN_AGE_MILLIS` (6 h) is load-bearing, not a tidy default.** It is the only
thing protecting the store-install window: `installFromStore` runs from the Apps
screen while a sync runs, and holds a verified download for as long as the user
takes to confirm. Nothing else visible to the sweep can see that happening. The
backlog is days old, so it is eligible on the first sweep regardless.

Also guarded: `lastModified` returning 0 for an unstattable file, which as an age
would read as 1970 and delete it — treated as brand new instead.

12 tests. Confirmed by mutation that both non-obvious rules are load-bearing:
dropping the spent test fails two tests, dropping the age guard fails one. (A
first attempt at mutating the branch order turned out to be logically equivalent
and proved nothing — noted because it looked like a passing check.)

Agent **89 / 0.44.0** published (fleet pointer 89). The backlog clears on each
device's first sync after it takes the update; the reclaimed total is in the
agent log as `cache sweep: reclaimed N KB`.


### ✅ W90 — ATAK Config category (the TAK pack's pref half, Chunk 8)

The long-planned Chunk 8 "TAK pack" row, narrowed to the part that pays now:
**ATAK Config** in the policy creator, with three sub-topics —
*Plugin behavior* (stub), *ATAK Core Pref Config*, *Plugin Pref Config*.

Reference: the operator's own [TAK_pref_configurator](https://github.com/cfd2474/TAK_pref_configurator).
Its analysis method is adopted wholesale (discover preference XML by **content**,
resolve `@string`/`@array` references, infer the control from the widget class,
keep `entries`/`entryValues` paired by index). Its *static schema* is not — see
the decisions below.

#### Ground truth established before planning (2026-09-06)

Measured with this project's **own** parsers against
`Test Files/ATAK-5.8.0.4-174b425-civSmall-release.apk`, and against
`atak-civ`'s `PreferenceControl.java`. Nothing here is inferred from behaviour.

| Finding | Evidence |
|---|---|
| ATAK's resource names are **shrunk** (`res/-v.xml`, `res/0P.xml`) | 1006 `res/**/*.xml`; no name-based lookup could ever find them. Content-based discovery is the only route — the same conclusion `app_restrictions` reached for `res/Kt.xml` (W49). |
| **65** `PreferenceScreen` documents → **505** keys | `axml.parse_elements` over every `res/` XML |
| **477 / 477** title references resolved | `app_icon.read_table` + `arsc.ResourceTable.string` |
| **46 / 47** `entries`/`entryValues` pairs resolved to real label→value dropdowns | e.g. `pref_grid_type` → MGRS / Decimal Degrees / DMS; `auth_flow_trust_model` → `BAKED_IN` / `PRECONFIGURED` / `SYSTEM` |
| ATAK declares exactly **6** managed-configuration keys | `enterpriseConfigurationDataPackage` slots 1–5, plus `enterpriseConfigurationPreferences` |

⚠️ **`enterpriseConfigurationPreferences` is the delivery mechanism, and it is
ATAK's own.** `PreferenceControl.processEnterpriseConfigurationPreferences()`
reads it from `RestrictionsManager.getApplicationRestrictions()` — precisely what
a Device Owner's `setApplicationRestrictions` writes — and:

* takes the `.pref` XML as **plain text**, *not* base64. (The *data package*
  slots beside it **are** `Base64.decode`d. Two adjacent keys, two encodings;
  getting this backwards produces no error, just a config that never applies.)
* writes it to `filesDir/defaults` and calls `loadSettings(f)`, then deletes it;
* **de-dupes by MD5** — re-pushing identical content is a genuine no-op, so an
  idempotent reconcile costs nothing;
* reloads on `ACTION_APPLICATION_RESTRICTIONS_CHANGED`, so **no ATAK restart**;
* is capped near **64 KB** by the Binder transaction, which ATAK's own key
  description states outright.

This route needs **no `MANAGE_EXTERNAL_STORAGE`, no file push, and no Knox** —
it rides the `setApplicationRestrictions` path the agent already proved in W49.
It therefore sidesteps R1 entirely rather than depending on it.

`loadSettings` switches on the `class` attribute verbatim
(`class java.lang.String` / `Boolean` / `Integer` / `Float` / `Long`), and maps
the legacy group names `com.atakmap.{app,civ,fvey}_preferences` onto
`<packageName>_preferences`.

#### Decisions

| # | Decision | Rationale |
|---|---|---|
| D91 | **The pref schema is scanned from the uploaded ATAK build**, not from a bundled JSON file | Same reasoning as `declared_config` (W49): a schema read from the APK being deployed cannot drift from it. The reference project ships static JSON because it has no APK to read; this console has one. Cost, accepted: the sub-page shows an "upload an ATAK build first" state until one exists. |
| D92 | **ATAK_CONFIG resolves into the `app_configs` channel server-side**, in the desired-state builder | ATAK Config and an operator-authored App-Management config for `com.atakmap.app.civ` both end at `setApplicationRestrictions` for the *same package*, and that call **replaces the whole Bundle**. Merged at one deterministic seam on the server, the collision cannot happen; left to the agent it would be a silent last-writer-wins that wipes whichever the operator looked at last. **No new agent applier, no new agent release.** |
| D93 | Value types are derived from the **widget class**, not guessed from the value | `PanCheckBoxPreference` → Boolean, `PanListPreference`/`PanEditTextPreference` → String, `SeekBarPreference` → Integer. An `EditTextPreference` holding a port is a **String** even though it looks numeric — that is what a real EUD export contains, and what `getString` on the device expects. Guessing "looks numeric → Integer" produces a `ClassCastException` inside ATAK. |
| D94 | A **wired** category may declare *stub* sub-pages | "Plugin behavior" must sit alongside two working sub-pages. Today a category is all-stub or all-wired, and sub-pages derive only from `ui_group`. One optional field on `Category`, rendered by the existing stub panel. |

#### Out of scope, deliberately

* **CoT connections** (`cot_inputs` / `cot_outputs` / `cot_streams`). Separate
  preference groups with their own `connectString` grammar, count-indexed
  entries and `.p12` handling — and TAK-server enrolment touches PKI. A chunk of
  its own; the generator is built so the groups can be added without reshaping it.
* **Plugin behavior** — stub only, per the operator.

⚠️ **Only what the plugin declares in `res/xml` is visible.** Code-only settings
and custom stores (`NWSharedPreferences`) cannot be scanned, and the console must
say so rather than imply the list is complete.

⚠️ **A plugin can only be scanned if its APK is in the library.** "Select from
the installed apps" resolves to the uploaded app packages — the same picker App
Management already uses — because a plugin seen only in a device's reported
inventory has no bytes here to read. Apps declaring `plugin-api` are flagged as
plugins (`atak_compat` already reads it), but any app may be picked: plugins have
no naming convention to filter on.

##### ✅ Chunk A1 complete (2026-09-06) — scanner and generator, no UI

All six steps done. **890 server tests pass** (35 new, in
`tests/test_atak_prefs.py`); no existing test changed behaviour.

1. ✅ `app/artifacts/pref_screens.py` — discovery by content, ARSC-resolved
   titles/summaries/options, `PreferenceCategory` sections. Mirrors
   `app_restrictions.discover_in` and **reuses** its resource reader
   (`app_icon.read_table`) rather than carrying a second one.
2. ✅ Plugin preference-group detection from the dex, defaulting to
   `com.atakmap.app.civ_preferences`.
3. ✅ `app/services/atak_pref.py` — the `.pref` document, byte-for-byte against a
   real EUD export, with per-class validation and the 64 KB refusal.
4. ✅ `build_preference_axml` / `pref_field` / `pref_category` added to
   `tests/apk_fixtures.py`; real-ATAK assertions skip when `Test Files/` is absent.
5. ✅ Recorded as **§10** of `docs/ANDROID_PLATFORM_REFERENCE.md`, with sources.
6. ✅ This file.

**Measured on ATAK 5.8.0.4** (112 MB APK, ~0.7 s): 65 `PreferenceScreen`
documents, 48 of them carrying storable settings, **293 settings**, **292 of 293
titles** resolved, **46 of 47 dropdowns** resolved to real label→value pairs.

Three defects the real APK caught that a fixture never would have, each fixed and
now regression-tested:

⚠️ **A case-insensitive group regex matched a platform constant.** Carried over
from the reference project, `[a-z…]+_preferences/i` also matches
`android.intent.category.NOTIFICATION_PREFERENCES` — which is what ATAK's own
scan returned as its "plugin-specific preference group". Every plugin that posts
a notification would have had its settings written into a store named after an
intent category. A SharedPreferences name is a package name; the pattern is now
case-sensitive.

⚠️ **`endswith("Preference")` swallowed the custom widgets that store values.**
Every preference class ends in "Preference", so a suffix deny-list aimed at
action rows also dropped ATAK's `SMSNumberPreference` and
`CredentialsPreference`. Now matched on the final class-name segment against
`{Preference, PanPreference}` exactly; an unrecognised widget is offered as free
text, because one visible spare row beats a setting that silently cannot be
configured.

⚠️ **Checkbox defaults arrived as `1` / `0`.** Binary XML stores a boolean as an
int, so all 160 of ATAK's checkboxes reported a default in a vocabulary the
control does not speak. The same trap `app_restrictions` documents, met again in
a different reader.

**Deliberate divergence from `app_restrictions`:** that scanner stops at the
**first** matching document, because an app has one restrictions schema. This one
keeps **every** screen — ATAK has 48, and stopping at the first would surface a
handful of keys out of 293 and read as an app with barely any settings.

##### ✅ Chunk A2 complete (2026-09-06) — policy type and desired state

All six steps done. **925 server tests pass** (27 new, in
`tests/test_atak_config_policy.py`); no existing test changed behaviour.

1. ✅ Scanner refinements the real plugin forced — see below.
2. ✅ `ATAK_CONFIG` registered: `core_prefs` (MERGE_BY_KEY on `key`, so a network
   baseline and a display baseline **compose setting by setting**) and
   `plugin_prefs` (MERGE_BY_KEY on `package_name`, matching App Management's
   "one configuration per app").
3. ✅ `atak_config` category with D94's stub sub-page for *Plugin behavior*,
   which now sits above the two working sub-topics.
4. ✅ `app/services/atak_config.py` renders the document and folds it into
   `APP_CATALOG.app_configs`; `desired_state.build` calls it **before**
   `_with_declared_types`.
5. ✅ Bounded LRU keyed on the base APK's sha — the result, never the bytes.
6. ✅ `form_parse` handles both controls, so the policy round-trips.

⚠️ **Ordering is load-bearing and is now asserted.** ATAK declares
`enterpriseConfigurationPreferences` in its own schema, so merging *before* the
type enrichment gives the generated document its declared type
(`RestrictionEntry.TYPE_STRING`) with no second place that has to know it.
Reversed, `types` comes back empty and the agent has to guess — and a guess here
is a Bundle the app cannot read.

⚠️ **Nothing in this path may raise into a check-in.** `render` runs inside the
device's own request, so a policy it cannot express degrades to "no ATAK
configuration" plus a warning. A value that cannot be its declared type, no ATAK
build in the library, and two ATAK builds with nothing to choose between them are
all warnings, never exceptions. The operator is told in the console; the tablet
is not punished for a policy it did not write.

**Ambiguity is refused, not guessed.** A device holds one ATAK but a library can
hold CIV and MIL. The target is the ATAK build this policy *requires* if it names
one, else the only one in the library, else nothing — with a warning naming both
candidates.

###### What the real UAS Tool plugin taught (2026-09-06)

`Test Files/ATAK-Plugin-uastool-13.0.6-74628a10-5.8.0-civ-release.apk`, 395 MB:
**23 screens, 158 settings, all 158 titled, 11 dropdowns**, scanned in 0.45 s. It
writes into `com.atakmap.app.civ_preferences` — **ATAK's own store**, which is
the assumption D92 rests on, now checked rather than reasoned about.

⚠️ **Categories are not always the parent of their fields.** Android documents a
`PreferenceCategory` as containing its fields and ATAK writes them that way. UAS
Tool does not: its categories are **empty elements used as separators**, with the
fields following them as *siblings at the same depth*. Read only as nesting, all
158 of its settings landed under one heading and **all 30 real headings were
thrown away** — "DJI v5 Settings", "Indago Settings", "Trillium/Orion Settings"
all lost. Both idioms are now handled, decided per category by what the document
has actually shown: once a field has appeared *inside* a category the document is
nested and a same-depth field belongs to nobody; until then a same-depth field is
the flat idiom.

⚠️ **`PanPreferenceCategory` was being offered as a setting.** The category check
was an exact name match, so ATAK's subclass fell through to the unknown-widget
branch and became a **free-text field named after a heading** — UAS Tool's "AR
OVERLAY" and "OBJECT DETECTION" rows, both of which carry a key. Categories are
now matched on the suffix like every other widget. Two fewer settings, both of
them fictional.

⚠️ **A heuristic was removed for want of evidence.** A first pass derived a
heading from the longest common key prefix (`uastool.mavlink.mirror`) for screens
with no title and no categories. Once the flat-category idiom was handled, no
screen in either real APK reached it — so it was deleted rather than kept as
machinery that fires only in a case nobody has seen.

###### Settled for chunk A3 (operator, 2026-09-06)

**A paged table, 50 settings per page.** 293 core settings across 48 screens is
past what a rail of sub-pages can carry.

##### ✅ Chunk A3 complete (2026-09-06) — the console

All six steps done. **946 server tests pass** (21 new, in
`tests/test_atak_config_ui.py`); no existing test changed behaviour.

1. ✅ `GET /policies/pref-schema` — **one** endpoint for both tables. No
   `package` answers for the library's ATAK build; a `package` answers for that
   plugin. They differ only in which APK is scanned, and two routes would mean
   two copies of the same shaping code drifting apart.
2. ✅ `atak_core_prefs` — a filtered, **paged table, 50 rows a page**.
3. ✅ `plugin_prefs` — app picker → scan → the same table in a wide modal → one
   row per plugin, carrying its values as JSON. Apps ATAK recognises as plugins
   are marked, but any app may be picked: plugins have no naming convention.
4. ✅ Stub sub-page panel for *Plugin behavior* (D94).
5. ✅ Rail completion checks: the table's controls are ordinary named inputs, so
   the existing generic check works — with one addition, an `input` event fired
   after the async build, because the rail's first pass runs long before the
   fetch resolves.
6. ✅ Tests and this file.

⚠️ **The saved settings are hidden inputs before the script runs, and are
removed only once the table has been built from them.** The table is assembled in
the browser, so if the schema fetch fails — the ATAK build deleted, the request
500s — settings that lived only inside the table would submit nothing and saving
would **wipe the whole category with no error anywhere**. Rendering them first
means a failed fetch costs the operator the ability to *add* settings, never the
ones they already had. Asserted in
`test_a_saved_policys_settings_are_in_the_page_before_any_script_runs`.

⚠️ **Rows off the current page are hidden, never removed or disabled.** A hidden
input still submits; a removed one drops that page's values the moment the
operator turns a page, and a disabled one drops them on save. `render()`
therefore reclaims *every* row into an off-screen holder before repainting the
window — clearing the tbody without that orphans the rows that were on screen,
and with them everything typed into them.

⚠️ **The plugin picker's table submits nothing.** It is rendered *inside* the
policy form, so named inputs there would post a hundred-odd stray pairs on every
save — and into `core_prefs`, the one field whose names they would match. Its
values are read back through `collect()` instead.

⚠️ **A setting the policy carries that the scanned build no longer declares is
kept, marked, and still editable.** ATAK renames and retires keys between
releases; discarding one quietly would change a live policy just because somebody
opened it. They sort to the top, because they are the ones needing a decision.
The same applies to a *value* the build no longer offers — it stays selectable,
or opening the policy would silently set it to unmanaged.

**Two states are answers, not errors.** "No ATAK build is uploaded" and "this app
declares no settings" come back as `200` with a warning to render. A `404` would
put the explanation in a console nobody has open. An unknown *package* is still a
404 — the picker only ever offers apps that exist.

###### Run against the live dev stack (2026-09-06)

Rebuilt (`docker compose up -d --build api`) and driven through real HTTP, not
only `TestClient`.

**The core table, from the ATAK build already in the dev library:** 293 settings,
83 sections, **6 pages** at 50 a page, no warnings. 160 checkboxes, 45 dropdowns,
86 text, 1 multi-select, 1 slider.

**Every real plugin in the library, scanned live:**

| Plugin | Settings | Sections |
|---|---|---|
| UAS Tool | 158 | 30 |
| AR Video Overlay | 2 | 1 |
| ADSB Direct | 0 | — |
| Air Overlays | 0 | — |
| Oceus VPN | 0 | — |
| Beartooth MKII | 0 | — |

⚠️ **Most ATAK plugins declare no preference XML at all** — four of the six here.
Checked rather than assumed: ADSB Direct has **654** `res/**/*.xml` files and not
one `PreferenceScreen` among them; its settings, if any, are built in code. So
"declares no settings" is the true answer far more often than not, and the
console has to say it plainly or the scanner reads as broken. It does.

⚠️ **The plugin marker in the picker never appeared, and nothing failed.**
`plugin_api` lives on `AppPackageVersion`, not `AppPackage`; Jinja resolves a
missing attribute to Undefined, which is falsy, so the marker was simply never
true — on a library that is almost entirely plugins. Now read through a
`plugin_api` filter off the deployed version: **7 of the 11 apps in the dev
library mark correctly.** Regression-tested, because the failure mode is a
template that renders perfectly while showing nothing.

⚠️ The `plugin_api: None` this first looked like was a red herring — the
packages API does not serialise that field, and the column was populated all
along. The marker is still **best-effort** in the copy, because a build uploaded
before the column existed does have it NULL until `backfill_plugin_api` runs, and
an unmarked app must not read as "not a plugin".

**The scan cache earns its place:** a cold core scan is **1.35 s**, a warm one
**0.009 s** — the 112 MB APK is parsed once per artifact hash, and the settings
sub-page is opened far more often than ATAK is re-uploaded. The core schema is
75 KB on the wire, one plugin's 33 KB.

###### A coupling test, on purpose

`test_the_core_panel_carries_every_hook_the_script_looks_for` and its two
siblings assert that the rendered markup carries every `data-` attribute
`atlas.js` queries, and that the picker's script-built copy of the table markup
matches the Jinja one. ⚠️ A renamed attribute breaks the table **silently** —
the fetch succeeds, `querySelector` returns null, and the operator sees a panel
that never finishes loading, with nothing in any log. Nothing else in the suite
can see that, because nothing else runs the script.

##### ✅ Chunk A4 complete (2026-09-07) — the wire, and a runbook for the tablet

**957 server tests pass** (11 new — 8 in `tests/test_atak_config_wire.py`, 3 in
`tests/test_atak_config_ui.py`). Steps 1–3 and 5 done; step 4 is the runbook
below. **The tablet remains unverified and that is the one claim W90 cannot yet
make (R16).**

⚠️ **A promise the code had made and not kept.** `atak_config.render` produces
warnings, and both the service and this file claimed "the operator is told in the
console" — while nothing displayed them. They now render on the category's own
panel in the policy editor. This matters more than an ordinary missing feature:
the same checks run again at check-in, inside the device's own request, where
they may only degrade to "no ATAK configuration" because a device must not fail
to check in over a bad policy. A warning that does not reach the editor reaches
**nobody**, and the policy quietly does nothing forever.

⚠️ **Hardware verification is blocked, and not on this code.** `SM-X520` last
checked in **2026-09-04 00:46 UTC** — three days before this chunk — and answers
neither `adb devices` nor `adb mdns services`. It is also one state version
behind (`acked 69` / `state 70`), so it already has a pending change it has never
taken. Nothing about ATAK Config can be proven on it until it is switched on.

⚠️ **No policy has been assigned to it, deliberately.** The tablet is offline;
assigning an ATAK configuration now would mean it applies one nobody asked for
the moment it wakes. Standing authorisation here covers deploying the server and
the agent, not changing what the fleet is told to do.

What *can* close without the tablet is the last untested seam: A2 proved
`render` and `merge_into_policy` directly, but **nothing exercises the whole
chain** — a real assignment resolved through `desired_state.build` into the
signed bundle. That is the "does it actually reach the wire" question, and it is
answerable here.

1. End-to-end: real ATAK APK → library → an `ATAK_CONFIG` profile → assigned to a
   device → `build_signed`, asserting the `.pref` arrives in the bundle.
2. The agent's own contract: it lands in `APP_CATALOG.app_configs` with `types`
   populated — the exact shape `PolicyApplier.applyAppConfigs` reads.
3. Idempotence on the wire: the same policy builds byte-identical bytes, so
   ATAK's MD5 dedupe makes a re-push a genuine no-op.
4. A hardware runbook: precisely what to do and what to look for when the tablet
   is back, so the verification is a checklist rather than a fresh investigation.
5. Update this file and the risk table.

###### ✅ On hardware — `SM-X520` **and `SM-X828U`**, 2026-09-07

Run against the real deployment at `209.182.235.108`, not the workstation's dev
stack. ⚠️ **They are different servers with different databases** — see the
operational note above; the local one had not seen this device since 2026-09-04
and reading it looked exactly like a dark tablet.

**The fleet, all on agent 0.44.0 and all compliant:** `SM-X520` (`R5GL40MMHRN`),
`SM-X828U` (`R5GL80RJYHK`) and `SM-G736U1` (`R5CX10FCY5D`) — the full device
matrix. ATAK `5.8.0.4 (174b425)[playstore]` is installed on the two tablets,
**the same build the settings schema was read from**.

| Step | Result |
|---|---|
| Scanner, against the host's own ATAK build | **293 settings, 48 screens**, group `com.atakmap.app.civ_preferences` |
| `atakControlBluetooth` | `control=bool`, `class java.lang.Boolean`, default `false` |
| `chatPort` | `control=str`, **`class java.lang.String`**, default `17012` |
| Policy → assigned → resolved | `deliverable=True`, target `com.atakmap.app.civ`, **no warnings** |
| Document | 299 bytes, both entries, correct classes |
| Device took it | `state 54 → acked 54`, **compliant**, no `compliance_detail` |
| Agent's own log | `I/PolicyApplier: applied 1 config keys to com.atakmap.app.civ` then `sync: state=54 applied=54 errors=0` |

The agent's log, device-local (its clock is UTC-7; the bundle collected at
18:10:50 UTC ends at 11:10:51 local, which is what establishes the offset rather
than assuming it):

```
11:06:19 I/SyncService:   sync: state=53 applied=53 errors=0
11:06:58 W/Reconciler:    wait failed: HTTP 502          <- the api rebuild
11:07:14 I/SyncService:   sync: state=53 applied=53 errors=0
11:08:00 I/PolicyApplier: applied 1 config keys to com.atakmap.app.civ
11:08:00 I/SyncService:   sync: state=54 applied=54 errors=0
11:10:00 I/PolicyApplier: applied 1 config keys to com.atakmap.app.civ
11:10:00 I/SyncService:   sync: state=54 applied=54 errors=0
```

⚠️ **`applied 1 config keys` proves `setApplicationRestrictions` succeeded and
nothing more.** Whether ATAK then *read* the document is a separate claim, and
not one the MDM can make about itself.

✅ **ATAK ingested it — confirmed on the device by the operator, 2026-09-07.**
ATAK → Settings → Bluetooth shows **Bluetooth Support on**, and Chat → Chat Port
shows **17012**. **No ATAK restart was involved**, which is the
`ACTION_APPLICATION_RESTRICTIONS_CHANGED` path behaving as
`PreferenceControl` says it should.

⚠️ **Of the two, only Bluetooth was decisive.** ATAK's own default for
`atakControlBluetooth` is `false`, so "on" can only have come from this document.
`chatPort`'s default *is* `17012`, so seeing it proved the document did no harm
but not that it wrote anything — a setting agreeing with its default is not
evidence. Step 7 was run for exactly that reason: `chatPort` moved to **17013**,
a value ATAK would never choose on its own, publishing section v2 and taking the
device to `state 55`.

⚠️ **A stale read that looked like a failed write, and was not.** The step-7
script published v2 and then re-rendered the document **in the same session**,
which came back unchanged — so the run reported `changed: False` with
`state_version` still 54. The database had v2 all along
(`v1: chatPort 17012`, `v2: chatPort 17013`), and a fresh session showed
`state 55` and the new document immediately. Read policy back in a **new
session** after publishing, or the identity map answers with what you already
had.

✅ **Step 7 — a changed value re-ingests.** `chatPort` moved 17012 → **17013**,
publishing section v2 and taking the device to `state 55`. The agent's log,
device-local:

```
11:25:07 I/PolicyApplier: applied 1 config keys to com.atakmap.app.civ
11:25:07 I/SyncService:   sync: state=55 applied=55 errors=0
11:27:04 I/PolicyApplier: applied 1 config keys to com.atakmap.app.civ
11:27:08 I/SyncService:   sync: state=55 applied=55 errors=0
```

Both directions of ATAK's MD5 dedupe are therefore observed on hardware: an
unchanged document re-applies without ATAK re-reading it, and a changed one
produces a new hash and is ingested again.

✅ **Verified on the MediaTek device too, which R5 requires rather than allows to
be extrapolated.** `SM-X828U` (Dimensity 9300+, `R5GL80RJYHK`) was assigned the
same policy and took it — `state 4 → acked 4`, compliant:

```
11:33:46 I/PolicyApplier: applied 1 config keys to com.atakmap.app.civ
11:33:46 I/SyncService:   sync: state=4 applied=4 errors=0
11:35:47 I/PolicyApplier: applied 1 config keys to com.atakmap.app.civ
```

and the operator confirmed ATAK on that tablet showing the pushed values. **Two
of the three SoC vendors in the matrix are therefore covered** — Exynos 1580 and
Dimensity 9300+. `SM-G736U1` (Snapdragon) has **no ATAK installed**, so it has
nothing to configure and is not a gap this feature can close.

The 502s are worth keeping: they are the api container restarting mid-deploy, and
the agent retried and recovered on its own rather than reporting a policy failure.

The second application two minutes later is the applier's latch re-asserting on
every sync, which is correct — and free, because ATAK de-duplicates the document
by MD5 and re-reads nothing.

⚠️ **No agent release was needed, and that is D92 being right rather than
lucky.** The devices already run 0.44.0, which is the same version in this tree,
and its `applyAppConfigs` already reads the `types` map. ATAK Config resolving
into `app_configs` meant a **server-only deploy** reached a live fleet — had it
been given its own applier, every tablet would have needed an agent update first.

⚠️ **The type came from the build, and it matters here specifically.** `chatPort`
holds `17012` and is a **String**; typed as an Integer because it looks numeric,
`loadSettings` would throw inside ATAK part way through the document. The scan of
the deployed APK is what prevents that, on the exact build the tablet is running.

###### ✅ The revert, run the same way (2026-09-07)

Done in the two phases §10c-ii requires, not by archiving and hoping:

1. **Published ATAK's own declared defaults** — `atakControlBluetooth=false`,
   `chatPort=17012` — read out of the APK by the scanner at revert time rather
   than remembered from the start of the session, so they cannot be a stale
   guess at what ATAK considers default. Both devices took it.
2. **Then archived the policy**, at which point the agent clears the managed
   configuration and ATAK, correctly, does nothing with the cleared key.

⚠️ **Archiving first would have looked identical in the console and left both
tablets on the test values.** That is the whole reason this order is written
down.

###### ⚠️ Reverting an ATAK Config policy takes two steps, not one

Confirmed from `PreferenceControl` source, 2026-09-07. `loadRestrictions`
returns **null** for a key that is absent *or empty*, and the consumer guards on
`if (ecp != null)` — so clearing `enterpriseConfigurationPreferences`, which is
what the agent does when a policy stops naming the app, does **nothing inside
ATAK**. Every setting the last document wrote stays written; they live in ATAK's
own `SharedPreferences` and nothing reads them back.

⚠️ **This is the opposite of every other policy type in this project.** PASSWORD
relaxes when removed (R14), managed configuration is cleared, kiosk releases.
ATAK Config is **write-only from ATAK's side** — the same asymmetry FILES has,
where the MDM never deletes what it placed.

**To actually revert: publish the old values as a document, let the devices take
it, and only then archive the policy.** Archiving alone leaves both tablets
exactly as the last push left them, with nothing in the console to say so. The
defaults for this are read from the APK by the scanner rather than remembered, so
they cannot drift from what ATAK itself considers default.

###### Hardware runbook — ATAK Config on `SM-X520`

Everything below is ready; only the tablet is missing. Written as a checklist so
the verification is not a fresh investigation three weeks from now.

**Preconditions.** The tablet on and checking in (its last check-in was
2026-09-04 and it is one state version behind), and an ATAK build in the app
library — `com.atakmap.app.civ` 5.8.0.4 already is.

1. **Make the policy.** Policies → New → **ATAK Config → ATAK Core Pref Config**.
   Pick two settings whose effect is visible in ATAK's own settings screen and
   whose types differ, so the type path is exercised rather than assumed:
   * `atakControlBluetooth` (Boolean) — Settings → Bluetooth → *Bluetooth Support*
   * `chatPort` (String) — Settings → Chat → *Chat Port*
2. **Assign it** to `R5GL40MMHRN`, then **Check in now** on the device page.
3. **Server side.** The device page should show `acked_state_version` catching up
   to `state_version` and compliance staying `compliant`. An `apply_error`
   mentioning `com.atakmap.app.civ config` means the Bundle was refused — that is
   the agent's own report and it names the key.
4. **Agent side, without adb.** Send `COLLECT_LOGS` and read the agent log for
   `applied N config keys to com.atakmap.app.civ`. ⚠️ That line proves
   `setApplicationRestrictions` **succeeded**; it says nothing about ATAK having
   read it. The two are separate claims and only the first is the MDM's.
5. **ATAK side — the claim that actually needs the tablet.** Open ATAK and look
   at the two settings. ATAK ingests on
   `ACTION_APPLICATION_RESTRICTIONS_CHANGED`, so **no restart should be needed**;
   if the values only appear after a restart, that is a finding worth recording.
6. **Prove the no-op.** Check in again without changing the policy. ATAK
   de-duplicates by MD5, so nothing should be re-read — and the document is
   byte-stable by construction (asserted in `test_atak_config_wire.py`).
7. **Prove a change lands.** Flip `atakControlBluetooth`, re-publish, check in.
   The MD5 changes, so ATAK should ingest again.

⚠️ **What to watch for, from ATAK's own source.** A value that cannot be its
declared type makes `loadSettings` throw **part way through**, applying every
entry before it and none after, and the MD5 is written *after* the parse — so it
retries forever, silently. The server refuses such a value at publish, so this
should be unreachable; if a setting ever half-applies on the tablet, that is the
symptom and the server-side validation is where the gap is.

⚠️ **`adb` is not required for steps 1–4** and was not available when this was
written (`adb devices` and `adb mdns services` both empty). Step 5 needs eyes on
the device either way.

**Hardware verification is still outstanding** and is not covered by any of the
three chunks: nothing here has yet been applied to `SM-X520`. The server side is
proven against two shipping APKs, but no tablet has taken a generated `.pref`.

~~No real ATAK plugin APK is present in `Test Files/`~~ — ✅ **closed
2026-09-06.** UAS Tool 13.0.6 supplied by the operator; it corrected two
scanner defects that no fixture would have caught (A2 below).

### ✅ W88 — installer APKs were kept forever after the app was installed

Every APK the agent downloaded stayed in `cacheDir/artifacts/<sha>` for the life
of the device. `PackageInstaller` copies what it is handed into the system's own
store, so from the moment an install succeeds our copy is dead weight — and an
APK is the largest thing the agent writes. A tablet accumulated one copy of every
app it had ever been sent, plus one of every agent build it had ever taken.

**Three install sites, all now covered.** Policy-driven installs
(`reconcileApps`) and store installs (`installFromStore`) discard their parts as
soon as the install reports success.

⚠️ **Only on success.** The cache is what a retry resumes from: a download that
passed its sha check is byte-correct, so re-fetching it would buy nothing and
cost the whole transfer again over whatever connection a fielded device has. A
failed install is retried next sync and finds its parts still there.

⚠️ **Only files that install owns — never a sweep of the cache.** `installFromStore`
runs from the Apps screen while a sync runs, so a sweep would delete a store
install's parts between the download verifying and `PackageInstaller` opening
them.

**The self-update is the one install nothing can clean up after itself.** Handing
the agent's own APK to `PackageInstaller` kills this process part-way through, so
no line after that call ever runs — and at ~21 MB per build it is the bulk of the
cache. `selfUpdate` now records the sha *and the versionCode it was fetching*
before dying; the build that starts next reads the note and discards the file.
The version is what separates an update that landed from one that did not: below
it, the download is kept for the retry.

`InstallerCachePlan` holds both decisions, because the self-update sequence
cannot be observed on a device at all — the process that makes the decision is
not the process that made the download. `selfUpdateFinished` is `>=`, not `==`:
two updates landing between syncs would otherwise strand the first APK forever,
with nothing that ever runs again able to match its version. Confirmed the
boundary test fails when it is weakened to `>`.

⚠️ **Leftovers already on the fielded devices are not swept.** This changes what
happens from build 88 onward; the APKs those three devices accumulated before it
stay until something removes them. A one-time sweep is possible but needs an age
guard to avoid the store-install race above — not built, not asked for.

Agent **88 / 0.43.3** published (fleet pointer 88).


### ✅ W87 — the download icon reverted to the app icon, and the artwork was never the problem

Reported on build 86: *"it showed the new icon for a brief second, then reverted
back to the app icon while downloading a new app"* — the same symptom W84 was
supposed to have fixed by replacing the `animation-list` with a static PNG.

**The static PNG was fine.** The agent was posting **two** notifications: the
foreground service's permanent "keeping this device up to date" notice (id 1001,
`ic_stat_atlas`) and the install notice beside it (id 1002, `ic_stat_download`).
Two notifications from one package are auto-grouped, and the group's status-bar
entry is drawn from the **app launcher icon** — the full-colour logo with its
wordmark. The download arrow showed for the moment before grouping settled.

Two different causes, one identical wrong picture. That is why the second one
read as the first one not having been fixed.

**Fix: the agent posts exactly one notification.** `AgentNotification` owns all
three states — idle, downloading, installing — on the single id 1001.
`InstallNotifier` swaps the state on that id instead of adding one, and
`SyncService` hands over the notification it starts foreground with.

⚠️ **`clear()` re-posts; it does not cancel.** 1001 is the foreground service's
notification, so cancelling it drops the service out of the foreground and
Android kills it. The mirror case matters too: when no service holds the id (a
`SyncWorker`-only download), an `ongoing` notification left behind cannot be
dismissed by hand, so *that* path must cancel. `SyncService` sets
`AgentNotification.serviceIsForeground` at both ends of its life and `rest()`
branches on it.

`DataUsageTracker`'s threshold warning is a third notification, but it fires only
on a breach, never during a download, so it is left alone.

**Not verified from here.** The grouping behaviour is One UI's, observed on the
operator's hardware and not reproducible on this machine. Agent **87 / 0.43.2**
is published (fleet pointer 87); the operator confirms whether the arrow now
stays put for a whole download.


### ⚠️ W84 — the animated icon became the app icon; now a static arrow

The animation attempt failed exactly where I said it was unverified. On the
device the download notification showed **the ATLAS launcher icon, wordmark and
all** — Android substituted the app icon rather than rendering the
`animation-list`, silently and with no log line.

Replaced with the operator's `downloadicon.png` as a static silhouette at all five
buckets, built like `ic_stat_atlas`. The frames and the animation-list are gone;
leaving them would leave a resource whose only effect is to summon the app icon.

⚠️ Recorded in the platform reference: an `animation-list` is not a usable
notification small icon, and the fallback is *worse* than a still image because
the app icon is a full-colour logo with text that means nothing at 24dp.

### ✅ W83 — the download icon falls, Play Store style (superseded by W84)

⚠️ **Our own frames, not `android.R.drawable.stat_sys_download`.** That is a hidden
system resource whose artwork differs by OEM — on a Samsung it is not the glyph
this was designed against — so referencing it ships whatever the vendor drew.

Four frames on a 24dp grid at all five densities: an arrow falling toward a fixed
tray, then a frame with **no arrow at all**. The gap is what makes it read as
something falling repeatedly rather than a shuttle going up and down, and the
fixed tray gives the eye something still to measure the movement against.

⚠️ **Nothing in the app starts the animation.** `StatusBarIconView` starts an
`AnimationDrawable` it is handed — that is how the platform's own download glyph
moves — and no app can reach that view to call `start()` itself. So this depends
on the OEM's SystemUI doing what AOSP does; **unverified on One UI**.

The notification *shade* shows a single static frame regardless. The progress bar
there is what carries the detail.


### ✅ W82 — "Single app" was ticked on every new policy

Reported as *kiosk › single app showing active with no app selected*.

⚠️ **The tick came from a presentational control.** The rail recomputes "what have
I filled in?" from the form, and its content test counted any checked radio:

```js
if (el.type === "checkbox" || el.type === "radio") return el.checked;
```

The Single app panel holds `__kiosk_mode`, the radio pair choosing *Select app* vs
*Select app with activity*. One is checked the instant the page renders, so the
page reported content before an app existed. That code's own comment says it
"deliberately mirrors what `parse_form` keeps" — and `parse_form` never reads
`__kiosk_mode` at all.

Controls whose name **starts with** `__` no longer count. Prefix, not substring:
`multi_app_packages__package_name` is a real field with a double underscore in the
middle.

⚠️ **The saved state was never wrong** — production profiles marked exactly the
right pages, and a bare policy stored `{}`. Only the live in-browser hint lied,
which is why it took rendering the page to find rather than reading the model.

`scripts/check_rail_checks.js` drives the real creator page in jsdom and pins both
halves: nothing ticked untouched, Single app ticked once an app is chosen. It
asserts the presentational radio *is* checked, so the first half cannot pass for
the wrong reason. Confirmed it fails without the fix — `["kiosk:single-app"]`.


### ✅ W81 — a stalled enrolment is flagged, not deleted

Asked as *"can we automate the removal of device records that fail?"* — after I
had wrongly said the failed phone's record needed deleting before re-enrolment.

⚠️ **It does not.** `resolve()` matches a re-enrolling device on a *set* of
identifiers and readopts the existing record;
`test_reenrollment_readopts_the_device_and_revokes_the_old_certificate` pins that
a wipe-and-reprovision keeps the same `device_id`, keeps group membership, and
revokes the old certificate on the way through. The need I described was one I
invented.

⚠️ **Automatic deletion would also be wrong.** "Failing" and "offline" are the
same thing from the server: a tablet on a boat for three weeks looks exactly like
a broken one, and those are the devices this exists for. The record also carries
the policy stack — deleting it turns a device that would have come back
configured into one an operator must set up again.

What *was* missing is the signal. The console said "never" in Last seen, which is
equally true of a device enrolled ten seconds ago. A device that **enrolled and
then never checked in at all** is unambiguous, and now shows a red *never checked
in* pill whose tooltip names both causes that have actually happened — a
certificate that does not match the key (W80), or a server URL it cannot reach
(W76) — and says the record survives a reset, so nobody deletes it trying to help.

`STALLED_AFTER` is 10 minutes: generous, because a healthy device syncs seconds
after provisioning, so anything past it is stuck rather than slow.


### ⚠️ W80 — enrolling twice at once bricks a device's identity

`SM-G736U1` enrolled and then failed every sync with *"Failure in SSL library"*.
nginx said what the phone could not: `SSL_do_handshake() failed (error:0A00007B:
bad signature)`.

**What happened.** Two `POST /api/v1/enroll` calls landed in the same second and
two certificates were issued; the second revoked the first. `enrollIfNeeded` does

```
generateKeyPair()      // replaces the keystore entry
api.enroll(csr)        // network
installCertificate()   // replaces the certificate
```

and both steps write to **fixed slots**. Interleaved, the device ends up holding
one attempt's certificate and the other attempt's private key. The certificate's
public key then cannot verify what the private key signed, which is precisely
"bad signature".

⚠️ **Nothing was serialising them.** At provisioning `PolicyComplianceActivity`
runs a sync directly *and* `MdmDeviceAdminReceiver` starts the scheduler, and each
builds its own `Reconciler` — so an instance-level guard would have serialised
nothing. The lock is on the **companion object**.

⚠️ **It is unrecoverable over the air.** The device cannot complete a handshake,
so it cannot check in to be told anything — including about a fixed agent. Its
enrollment token was consumed and cleared, so it cannot re-enrol either. **Factory
reset and re-provision is the only route back.**

Also added: `installCertificate` refuses a certificate whose public key is not the
one this device holds. That turns a permanent silent bricking into a visible
enrollment failure with the previous identity left intact.

Fixed in agent **0.42.1 (84)**.


### ✅ W79 — Peripheral restrictions merged into Peripheral Settings

The operator read the two sub-pages as duplicates. Four of the seven restrictions
were: Bluetooth, Wi-Fi, volume and brightness each asked the same question twice —
once as *may the device do this*, once as *does a control appear* — and an
operator had to set both, in agreement, on two pages. W71 created that split; this
undoes it.

**One field per peripheral, three meanings:**

| | restriction | control |
|---|---|---|
| not managed | left alone | absent |
| user can change | cleared | shown |
| blocked | applied | absent |

⚠️ **"Blocked", not "Hidden", on the four with a restriction behind them.** Their
false case forbids the device to change the thing *by any route, including the
hardware keys* — an operator reading "Hidden" would be surprised by a volume
rocker that stopped working.

✅ **Brought across, because they have no control to merge into:** camera, screen
capture and airplane mode. No app can toggle airplane mode at all, and camera or
screen capture on a kiosk is a lockdown decision rather than a user preference.

⚠️ **A regression the merge nearly shipped.** `_device_settings_need_a_launcher`
refused any `device_setting_*` without a multi-app kiosk — which after the merge
would have removed a **single-app** kiosk's ability to block Bluetooth, Wi-Fi,
volume or brightness at all. Only *showing* a control needs a home screen;
blocking one is enforcement the OS applies everywhere. Caught by an existing test
failing, not by review.

⚠️ **Lost on purpose, and narrow:** explicitly *allowing* one of the four on a
single-app kiosk. Not setting the field leaves the restriction alone, which is
the same outcome unless a Restrictions policy blocked it and kiosk was expected to
override that.

Two validators deleted rather than updated — the contradiction they caught (a
control shown while the restriction forbids it) is now unrepresentable.


### ✅ W75 — notification icons, and progress while apps install

Operator: the permanent notice used the platform download glyph, which reads as a
transfer that never finishes; and a device downloading apps said nothing.

⚠️ **A notification small icon is an alpha mask.** Android discards the colours
and tints what is left, so the full-colour logo would be a white blob.
`atlasicon-cutout.png` is pure white on transparent, which is what makes it
usable — and the reason the answer was not "point it at the app icon".

Generated at all five buckets (24/36/48/72/96 px for 24dp), inset to 22/24 so it
does not crowd the status bar, and **rebuilt as pure white with the source's
alpha** rather than merely resized: a scaled edge pixel can carry a fractional
colour, and since Android tints by alpha a stray dark pixel shows as a notch.
Verified by content that every bucket survived into the APK — resource names are
obfuscated in release, so matching on the alpha channel is the only way to know.

**The download symbol now means only what it says**, on a new `InstallNotifier`
that shows *Downloading <app> 42%* then *Installing <app>* and clears.

⚠️ **Progress is aggregated across parts.** A split app downloading three parts
would otherwise fill and reset the bar three times, which reads as three failed
attempts.

⚠️ **Updates are throttled to ~4/s.** Android drops notification posts faster than
that, and a fast local download calls back far quicker — the bar would jump and
stall rather than move. The final 100% is always allowed through, so a download
does not finish showing 97% and vanish.

⚠️ **A cache hit reports completion before returning**, or an app already cached
shows nothing at all and the device looks idle through the part where it is about
to install something.

⚠️ **Installing is indeterminate on purpose.** `PackageInstaller`'s session
progress jumps to near-complete immediately and sits there, so a bar driven by it
looks stuck at 90% for the part that actually takes time.

⚠️ **The agent's own update posts "Installing" and never clears it** — `install`
replaces the process and nothing after it runs. The new build's first reconcile
clears it, and until then the notice is true: the install really is still
happening.


### ⚠️ W73 — an optional permission must never report itself as a failure

Found while answering "assign the accessibility on provisioning". W72 chunk 3
added `PowerMenu` to `PermissionRequirement.ALL`, and `outstanding()` feeds the
reconciler's **errors** — which set compliance DEGRADED, which
`agent_update.decide()` treats as *"not applying its policy cleanly"* and refuses
to offer updates to.

⚠️ **So agent 79 shut its own update channel on any device without an
accessibility grant** — which is every device until someone gives it. Observed on
`SM-X520`: `DEGRADED — missing permission: power_menu`. It cleared shortly after,
almost certainly because the grant was then given by hand; the hazard was real
for every future enrollment regardless.

⚠️ **`optional` already existed on the base class and `outstanding()` ignored
it** — `Notifications` has been marked optional all along and was being reported
as an error too. It only ever passed because that permission is granted silently.
So this was a latent bug that W72 merely made reachable.

Fixed in agent **0.39.1 (80)**: required permissions are errors, optional ones
are warnings, and the base declaration now says plainly what the flag decides.

⚠️ **The server-side gate was left alone on purpose.** Refusing to stack an agent
swap on a device that is failing to apply policy is correct; weakening it to work
around an agent bug would trade a real safeguard for a symptom.


### 🔨 W72 — Device Settings, second round (IN PROGRESS)

From testing W71 on the tablet. ✅ Wi-Fi works; ✅ the "no flashlight" message was
correct on hardware.

**Operator decisions:**

| Question | Answer |
|---|---|
| Wi-Fi picker | **Full picker** — scan and join any network |
| Airplane mode | Not achievable; a **"Radios off"** control instead |
| Power off | **Accessibility-backed power menu** only |

⚠️ **The full Wi-Fi picker was chosen over the provisioned-only list with the
consequence stated**: it puts credential entry on a locked device and lets a
kiosk user attach the device to a network they control. Recorded once here; it is
the operator's call, not a defect.

⚠️ **Power off has no fallback by choice.** Without the accessibility grant on a
device there is no power control at all — `dpm.reboot()` was offered as a
grant-free alternative and declined. The screen must therefore make a missing
grant *visible* rather than simply omitting the row.

#### ✅ Chunk 1 — the tile's own identity, Bluetooth, Radios off (COMPLETE)
1. A gear icon and the label "Settings" on the activity.
2. ⚠️ The real bug behind the wrong icon: `AppCatalog` reads the **application's**
   label and icon even when the tile names an activity.
3. Bluetooth on/off — API 33 deprecated `enable()` **for ordinary apps**; device
   owners are exempt, which is why this is in after all.
4. A Radios off control.
5. Policy fields and tests.

⚠️ **The wrong icon was a real bug, not a missing attribute.** `AppCatalog` read
the **application's** label and icon even when the tile named an activity — and
the console and Device Settings are the same package, so both tiles came out
identical with no way to tell them apart. It now prefers the activity's own, and
falls back to the application's, which is strictly better: an activity declaring
neither inherits them anyway.

⚠️ **Bluetooth is achievable after all.** API 33 deprecated
`BluetoothAdapter.enable()` **for ordinary apps**; device owners and profile
owners are exempt. Chunk 2 of W71 recorded it as impossible; that was wrong.

⚠️ **Bluetooth does not settle synchronously.** `isEnabled` straight after an
accepted call still reports the old value, so an accepted call returns what was
asked for and the switch corrects itself on the next draw. Reading it back the way
Wi-Fi does would make every successful toggle look like a refusal.

⚠️ **Radios off has its own validator** because it is the only control touching
*two* restrictions, which `_CONTROL_NEEDS_PERMISSION` cannot express — and the
message names both, or the operator fixes one and hits the refusal again.

✅ **The gear was rendered and looked at** — and my first renderer painted holes
with the background colour, which hid the light hub ring and nearly had me delete
a correct element. On Android that hole is transparent and the ring shows
through. 844 server tests.
#### ✅ Chunk 2 — the Wi-Fi picker (COMPLETE, not yet deployed)

⚠️ **Scan results are empty without location services, and Android says nothing
about why.** `getScanResults()` just returns an empty list — indistinguishable
from "no networks here" while standing in a building full of them. The screen
names the reason instead.

⚠️ **`startScan` is throttled to four calls per two minutes** for ordinary apps
since Android 9; a Device Owner is exempt, which is the only reason a live
refreshing list is worth having.

⚠️ **WPA3 transitional advertises both `SAE` and `WPA2-PSK`.** Testing PSK first
joins it as WPA2 — which *works*, and silently gives up the WPA3 the network
offered. `EAP` is tested before everything, or an enterprise network gets a
password box it can never satisfy. Both have tests.

⚠️ **One row per SSID, strongest access point winning.** A site with four APs on
one network scans as four results, and showing all four looks broken.

⚠️ **`joinWifi` reuses `buildWifiConfig`**, so a network joined by hand is
configured exactly as one pushed by policy — a second builder would drift, and the
difference would surface as one working on an OEM where the other failed. It is
deliberately **not** recorded in `wifiByPolicy`: that set is what the agent removes
when policy stops naming a network, and a network the user added was never the
policy's to take away.

⚠️ **The picker refuses to draw unless the policy offers Wi-Fi**, and is not
exported. A settings screen reachable on a device whose operator never offered
Wi-Fi would be a way round policy rather than an expression of it.

⚠️ **The operator's stated trade:** a kiosk user can attach the device to any
network they can see, including one they control. Chosen over the
provisioned-only list with that consequence stated.

#### ✅ Chunk 3 — the power menu (COMPLETE, not yet deployed)

⚠️ **The grant cannot be given from inside a kiosk.** Enabling an accessibility
service means visiting `com.android.settings`, which lock task blocks — so it has
to be switched on **before** the device is locked down, or the device taken out
of kiosk to do it. The field says so, the wizard lists it last, and the settings
screen explains itself rather than offering a button that would do nothing.

⚠️ **The service observes nothing.** `accessibilityEventTypes` is **omitted**, not
set to a "none" value — there is no `typeNotSet` flag and aapt rejects it; leaving
the attribute out is how you subscribe to nothing. Naming any type would start
delivering the user's activity to this process for no reason, and an accessibility
service on a managed device can otherwise see everything.

⚠️ **Availability is "enabled **and** bound", not either.**
`ENABLED_ACCESSIBILITY_SERVICES` can name a service that has not bound yet, and a
live instance can outlast the setting — either alone would give the user a row
that does nothing when tapped.

⚠️ **`device_setting_power` is refused when `keep_power_menu` is false.** With
`LOCK_TASK_FEATURE_GLOBAL_ACTIONS` off the platform suppresses the dialog, so the
row is tapped, the accessibility action *reports success*, and nothing appears —
the most confusing failure available, because every part of it looks like it
worked.

##### Two build traps worth remembering

⚠️ An **apostrophe** in a string resource must be escaped, and `&apos;` resolves
to a bare one. aapt rejects it with *"Invalid unicode escape sequence"*, naming
neither the character nor the rule. Reworded round it.

⚠️ My terminal renders UTF-8 as cp1252, so `…` and `—` in a file read back as `�`
and looked like corruption. **They were fine.** Check bytes before believing a
console.

848 server tests.

#### Chunk 4 — deploy and verify on the tablet


### 🔨 W71 — Device Settings on the launcher (IN PROGRESS)

Operator's requirement, with Hexnode's *Peripheral Settings* screens as the
model: a **Device Settings** tile on the kiosk launcher opening a list of
settings the user may change, matching a new Kiosk sub-topic, and feeling like
native OS settings.

**Operator decisions:**

| Question | Answer |
|---|---|
| Controls in v1 | Night mode, brightness, screen timeout, volume, flashlight, Wi-Fi — all four groups |
| Gating | A **new** *Peripheral Settings* sub-topic with an explicit toggle per control, **default off** |

⚠️ **The screen lives in the agent, not the launcher.** The launcher holds no
permissions; the agent is Device Owner and already holds `CHANGE_WIFI_STATE`,
`SYSTEM_ALERT_WINDOW` and the `setSystemSetting` allowlist. The launcher opens it
as a tile pointing at `com.taksolutions.atlasmdm/<activity>` — a shape the app
list already supports, and the agent is already lock-task permitted. No IPC, no
new permission, nothing to keep in sync.

⚠️ **Default off, and a validator against contradictions.** A kiosk shows nothing
the operator did not ask for. Where a control overlaps an existing `kiosk_allow_*`
restriction, showing it while the restriction forbids it would be a slider that
cannot move — refused rather than shipped.

⚠️ **What Android will not allow, whatever the screenshots show.** Airplane mode
cannot be set by any app. `setSystemSetting` permits **exactly three** keys
(`SCREEN_BRIGHTNESS`, `SCREEN_BRIGHTNESS_MODE`, `SCREEN_OFF_TIMEOUT`) — already
verified on `SM-X520`. `setWifiEnabled` is blocked for ordinary apps since
Android 10 and permitted for a Device Owner, but that is **unverified on our
hardware** and is the control most likely to fail. Bluetooth on/off is worse
still (API 33 deprecated `enable()` in favour of a user-consent intent) and is
deliberately not in v1.

#### ✅ Chunk 1 — the vertical slice (COMPLETE, not yet deployed)

1. `KioskSpec`: a *Peripheral Settings* group with one `device_setting_*` toggle
   per control, default off.
2. Validators: refuse a control the peripheral restrictions forbid; refuse the
   whole section without a multi-app kiosk, since the tile needs a launcher.
3. Catalog: the eleventh sub-topic.
4. Agent: `DeviceSettingsActivity`, reading the stored policy, rendering only the
   controls the policy enables, in the console's own visual language.
5. Night mode and brightness working end to end — enough to prove the whole path.
6. `LauncherConfigPlan`: the tile, added only when at least one control is on.
7. Tests both sides.

⚠️ **Two sub-pages cannot share a name.** The operator named the new one
*Peripheral Settings*; the existing page — what the **device** is allowed to do —
is now *Peripheral restrictions*. Renaming the older one was the smaller change
than renaming the thing they asked for.

⚠️ **De-duplication keyed on the package, and had to stop.** One app meant one
tile until the agent needed two — its console and its Device Settings screen are
the same package — and the package-level key silently dropped whichever came
second. Both sides now key on package *and* activity. `withAgent` matches on a
**null** activity for the same reason: matching the package alone would have seen
the settings tile and decided the console was already there, leaving a kiosk with
settings and no console.

⚠️ **Offering a control is a promise that the answer sticks.** Policy is
re-applied every two minutes, so the user's night-mode choice is stored and wins
while the control is offered — otherwise they switch it off and watch it come
back, which is worse than never offering it. Withdrawing the control forgets the
override, or an old answer would go on overriding policy where nobody can see it.
Verified by deletion: removing the offered-gate fails that test.

839 server tests, agent suite green.

#### ✅ Chunk 2 — the remaining controls (COMPLETE, not yet deployed)

Screen timeout, volume, flashlight, Wi-Fi. Rendered and looked at.

⚠️ **The screen timeout is owned by another policy section**, which drives it back
to the policy value on every reconcile. The user's stored override is what
suspends that, and its *presence* is the whole rule — so it exists only while the
control is offered, and the kiosk applier clears it when the operator stops. The
clearing runs after `applyScreenTimeout` in the same cycle, so a withdrawn
control is honoured from the **next** reconcile rather than that one.

⚠️ **The torch cannot be read**, only written — Android offers no getter without
registering a callback. The switch therefore starts at off every time, which is
honest: claiming a state the screen cannot know would be worse than the oddity.

⚠️ **`setWifiEnabled` returns false rather than throwing** when refused, so the
control reads the state back instead of trusting the call. Still unverified on
`SM-X520`.

**Deliberately absent, though the Hexnode screens show them:** airplane mode
cannot be set by any app; Bluetooth on/off lost `BluetoothAdapter.enable()` in
API 33 in favour of a user-consent intent, which is not something to raise from a
locked kiosk. A control that silently did nothing would be worse than its absence.

⚠️ **A near miss worth recording.** The edit that added all four sections was in a
shell heredoc that died on a quoting error and never ran. The build still
succeeded, the tests still passed, and the strings and `DeviceControls` were all
in place — nothing referenced them. It was caught only by going back to adjust
the layout. **A green build is not evidence that an edit landed**; check the
symbols exist.

#### ✅ Chunk 3 — deployed and verified on `SM-X520`

Agent **0.38.0 (78)**, launcher **0.3.0 (3)**. The launcher moved too: its
de-duplication now keys on package *and* activity, without which the second agent
tile would have been dropped silently.

✅ **The tile is there.** `kiosk: launcher configured with 5 apps` — three policy
apps, the console, and Device Settings.

✅ **Night mode works from the device, and the override holds.**

```
15:30:03  NightOverlay: night mode on (alpha 77)
15:30:32  NightOverlay: night mode off
15:30:47  kiosk: launcher configured with 5 apps   (no re-enable)
15:30:51  ... 15:31:54  ... still off
```

That is the whole W71 rule proven on hardware: the user turned the tint off and
policy did **not** turn it back on at the next three reconciles.

⚠️ **Wi-Fi remains unproven, and the log could not answer it.** `setWifiEnabled`
logged only refusals, so a successful toggle said nothing — silence meant either
"it worked" or "nobody tried it". There is an `ENETUNREACH` at 15:30:34 that is
consistent with Wi-Fi being switched off from the screen, and that is an
inference, not evidence. Now logged **either way**, so the next device answers it
from its own log.

⚠️ Brightness, timeout, volume and flashlight are likewise unconfirmed — they are
visible to whoever is holding the tablet, and nothing reaches the log unless they
fail.


### ✅ W70 — the ATLAS console is always a tile in a multi-app kiosk

Operator's requirement. In a multi-app kiosk the launcher is the only way to
anything, so without a tile there is no route from the device to sync,
permissions or its own state — and the person standing at a misbehaving tablet is
exactly who needs it. It was already lock-task permitted; it was only ever
missing a tile.

⚠️ **`Plan.withAgent` is separate from `from` on purpose.** `from` reports what
the *policy* asks for, and two other decisions read it: whether this is a
multi-app kiosk at all, and whether the launcher should be uninstalled. Appending
the console inside `from` would make every **single-app** kiosk look like a
multi-app one and lock the device to a launcher nobody asked for. There is a test
for exactly that.

Appended, never moved: an operator who placed the console themselves has said
where they want it, and a favourite they set stands. Verified by deletion —
removing the already-present guard fails two tests.


### ✅ W69 — removing a kiosk policy gives the launcher back

Reported by the operator: removing the policy did not revert to the stock
launcher. Two separate causes, and the first predates W68.

⚠️ **The HOME takeover was never undone, on any kiosk.**
`clearPackagePersistentPreferredActivities(admin, packageName)` matches on the
package the preference **points at** — AOSP compares
`pa.mComponent.getPackageName()` — and the agent passed *its own* package while
the preference pointed at the kiosk app. It removed nothing, ever, and reported
success. Single-app kiosk had this too; it was invisible because a kiosk app
looks like a kiosk. The agent now records the package it pointed HOME at and
clears that one, plus the launcher unconditionally for devices upgraded from a
build that recorded nothing.

⚠️ **Clearing the preference is not enough by itself.** With the launcher still
installed the device has two home apps and no default, so HOME raises the
"Complete action using…" chooser rather than going to the stock launcher.

⚠️ **Uninstall, not hide.** A hidden package still exists but reads as missing to
`getPackageInfo`, so the reconciler would decide it needed installing again on
the very next kiosk — a limbo both halves of the agent disagree about. Gone is a
state they can agree on, and re-entry re-downloads it through the required-app
path that exists for exactly that.

The rule is `LauncherConfigPlan.shouldRemoveLauncher`, pure and tested, including
that a policy naming the launcher in `required_apps` keeps it — otherwise the
agent would remove it every two minutes while the policy reinstalled it.


### 🔨 W68 — ATLAS Launcher (IN PROGRESS)

Decided with the operator 2026-09-06, closing
[DECISION-atlas-launcher.md](docs/DECISION-atlas-launcher.md) on **Option B**.
Modelled on `Test Files/GoTAK-Launcher-1.2.0.apk` (`com.gotak.launcher` 1.2.0),
which the operator supplied as the shape to aim at: a small View-based grid
launcher whose own classes are `AppAdapter`, `AppInfo`, `Gestures`, `NightMode`,
`Prefs`, `Updater`, and whose resource names show the feature set — `grid_columns`,
`tile_rows`, `large_icon`, `night_hue`/`night_level`/`night_opacity`, `clock_zulu`,
`lock_orientation`, `swipe_*`, `double_tap_sleep`.

**Operator decisions:**

| Question | Answer |
|---|---|
| Packaging | **Separate APK**, `com.taksolutions.atlaslauncher` |
| Console layout UI | **Ordered app list + column count + preview** — not Hexnode's drag-onto-device designer, no pages, no per-orientation layouts |
| v1 features | Night mode, Zulu clock, orientation lock, search + favourites — **all four** |

⚠️ **Config travels as managed configuration**, not a private protocol. The agent
is Device Owner, so `setApplicationRestrictions` is a channel it already has and
already tests; the launcher reads its own `RestrictionsManager` bundle. No
exported service, no custom permission, no IPC to get wrong.

⚠️ **The wallpaper does not travel that way.** Managed config is for small values,
not images. The Device Owner sets the system wallpaper through `WallpaperManager`
and the launcher draws over it — the picture never passes through the config.

⚠️ **The recovery path is what Option B buys.** Removing `kiosk_package` removes
the launcher's claim on HOME, so "unassign the profile" still recovers a device
without physical access. That is the property to check every change against.

#### ✅ Chunk 1 — module, config contract, grid (COMPLETE)

1. `:launcher` Gradle module, same keystore as the agent, own `applicationId`.
2. Manifest: `category.HOME` + `DEFAULT` + `LAUNCHER`, `singleTask`,
   `stateNotNeeded`; `<queries>` for `MAIN`/`LAUNCHER` (a non-DO app cannot see
   installed packages on Android 11+ without it); `WRITE_SETTINGS` for Chunk 2.
3. `LauncherConfig` — a pure parser from the restrictions `Bundle` to a typed
   model, with unit tests for absent, malformed and unknown-package input.
4. `res/xml/app_restrictions.xml` declaring the schema, so the console's existing
   APK scanner can read it and the contract is self-documenting.
5. Grid of app tiles: icon, label, launch on tap.
6. Build, sign, verify.

**Built:** `com.taksolutions.atlaslauncher` 0.1.0 (1), 7.08 MB, v2-signed with the
agent's key. 13 config tests green.

⚠️ **`apps` is a `bundle_array`, not a `multi-select`.** Multi-select is for a
*fixed* choice set and the platform requires `entries`/`entryValues` enumerating
it — which cannot exist when the choices are whatever apps the operator picked.
Lint refuses it (`ValidRestrictions`). The better reason is that `favorite` then
lives on the record, so there is no second list to disagree with the first: a
dock tile that lock task would refuse to open is now unrepresentable.

⚠️ **The parser reads a `Source`, not a `Bundle`.** Under plain JVM unit tests
`Bundle` is a stub returning defaults, so tests written against one would pass no
matter what the parser did — the salvage rules would be exactly the code never
exercised. Same trap as `isReturnDefaultValues` generally.

✅ **The console already reads the contract out of the built APK** — the existing
`discover_in` scanner returns all nine keys with their types, so the schema has
one home and it is the launcher's own manifest.

**A defect the tests caught:** `/some.Activity` has its slash at index 0, and the
`slash <= 0` branch made the whole string the package name — a tile that could
never open anything. No package before the slash now drops the record.

#### ✅ Chunk 2 — the four v1 features (COMPLETE)

⚠️ **Night mode moved to the agent.** It is the one feature that cannot live in
the launcher: the overlay permission is an **app-op a person grants**, no Device
Owner can grant it, and the agent already holds it. More to the point, what a
user reads by night light is ATAK's map — a tint drawn by the launcher would stop
at its own edges and vanish the moment they opened the app it was for. The
`night_*` keys are gone from the launcher's config schema and belong to
`KioskSpec` (Chunk 4). `NightOverlay` caps alpha at 190/255: "100" has to mean
"as dark as is still usable", because a policy that can blank a field device is
one someone sets by accident.

⚠️ **Orientation needs two mechanisms and only one always works.**
`setRequestedOrientation` pins the launcher, always. Pinning *every* app needs
`WRITE_SETTINGS` — a special permission a person grants through Settings, which
no Device Owner can grant. Attempted, and its absence logged rather than treated
as a failure.

⚠️ **Search does not match package names.** It read as a free extra until the
tests showed `com.atakmap.app.civ` and `com.example.bloomap` both contain "map",
so every package match undid the word-prefix rule beside it. The person who
searches by package is at the console, not the kiosk.

✅ **Rendered and looked at, which caught a real fault.** A default `EditText` on
this transparent wallpapered window drew as a **white slab** — the brightest
thing on screen, and under the night wash a glaring red panel, the exact opposite
of what night mode is for. It now has its own dark translucent background.

Search hides itself below 8 tiles: a filter box above four apps is furniture.

#### ✅ Chunk 3 — agent side (COMPLETE)

**Nothing here installs the launcher.** It is an ordinary *required app*: the
server adds it to the required list (Chunk 4) and the reconciler installs it
before kiosk is applied, exactly as W63 made it do for a single kiosk app. The
applier refuses with a sentence and the next check-in succeeds.

⚠️ **Multi-app wins over `kiosk_package`.** Both set is a policy that cannot be
honoured two ways, and locking to one app would silently discard the list an
operator arranged.

⚠️ **The tiles must be lock-task permitted too**, not just the launcher — else
every tile opens onto a refusal, which reads as a broken launcher rather than a
broken allowlist. `applyKiosk` gained `alsoPermitted` for exactly this.

⚠️ **`LauncherConfigPlan` accepts both wire shapes** — plain package strings and
objects with activity/favourite. Agent and launcher are separate APKs on separate
update schedules, so neither may assume the other's version; refusing old-shape
input would turn a working kiosk into one with no apps, which looks like a broken
launcher rather than an old policy. Verified by deletion: removing the string
branch fails five tests.

⚠️ **Both the wash and the launcher config are undone in `releaseKiosk`.** Both
latch. A tint left behind would redden a device nobody has told about it, curable
only by re-applying and removing a kiosk policy; a config left behind would leave
a home screen full of apps the device may no longer open.

139 agent tests, 12 of them the new plan's.

**Not yet on hardware:** `<queries>`, the overlay, orientation and the whole
multi-app path first touch a device after Chunk 4 ships the console side.

⚠️ **Kiosk wallpaper is deferred to Chunk 4** — `launcher_wallpaper_file_id` needs
the server's file plumbing, and the agent's existing `applyWallpaper` is what it
will route through.

#### ✅ Chunk 4 — server and console (COMPLETE)

**Ten sub-topics now**, all populated: night mode earned its own, because the
tint is drawn by the agent over *every* app and so applies to a single-app kiosk
too — it cannot live under "Launcher".

⚠️ **`launcher_wallpaper_file_id` was deleted, not implemented.** There is already
a WALLPAPER policy, and the launcher's window is transparent so it shows through.
A second field would have been two policies writing one device setting, and the
loser would lose silently.

⚠️ **`_kiosk_settings_need_a_kiosk_app` knew only about `kiosk_package`.** Left
alone it would have rejected every multi-app kiosk as unconfigured. There are two
ways to have something to lock to now.

⚠️ **Favourites are matched by package, not by index.** An unchecked checkbox does
not submit at all, so three rows with only the last ticked send *one* value —
positional pairing would put that favourite on the **first** app, and a wrong
favourite looks deliberate rather than broken. Verified by deletion: switching to
positional pairing fails the test.

⚠️ **Enum parsing was int-only.** Every enum reaching this form was an IntEnum, so
`_int_or_none` was harmless — until W68 added string-valued ones, where it would
have returned None and dropped the operator's choice in silence. Both directions
are now tested.

✅ **Checked in a real DOM** (jsdom, against the rendered page with real packages
seeded — an empty test DB gives empty selects and a meaningless pass): favourite
value follows the select, move-up reorders, the top row cannot escape the list,
one preview tile per row showing the label not the package, and the column count
drives the preview grid.

826 → 834 server tests.

##### ✅ On hardware — `SM-X520`, agent 0.35.0 (75)

First multi-app kiosk applied end to end, with nothing hand-fed to the device:

```
13:53:11  installing com.taksolutions.atlaslauncher versionCode 1
13:53:42  base part verified (7,428,238 bytes)
13:53:44  com.taksolutions.atlaslauncher installed
13:53:51  kiosk: launcher configured with 3 apps
13:53:51  kiosk: launched com.taksolutions.atlaslauncher into lock task
13:55:52  kiosk: already in lock task; brought to front
13:57:52  kiosk: already in lock task; brought to front
```

Proven by this run: the launcher is pulled in as a required app the operator
never named, installs, receives its managed configuration, and the device locks
to it — and **W67's fix is confirmed on hardware**, because the first apply says
*launched* and every one after says *brought to front*, where before it said
*launched* every two minutes.

✅ **Apps appear on the tablet** — so `<queries>` is right, which was the risk
that would have failed silently.

##### Clock: two rows, local on top (operator, 2026-09-06)

Local 24-hour on top, Zulu beneath, and `launcher_clock_zulu` now decides whether
the *second row* appears rather than which single time is shown — both are wanted
at once, so it was never a choice between them.

⚠️ The Zulu row keeps TAK's separator-less form (`141530Z`) beside the local
row's `10:15:30`. Rendered with colons on both, it reads as the same clock
printed twice with a stray Z; the differing form is what tells them apart at a
glance. Monospace on both, or the digits shift the line width every second.

##### Superseded

⚠️ **Not proven by the first run: whether the grid has anything in it.** The agent's
log cannot see the launcher's own screen, and an empty grid from a wrong
`<queries>` looks exactly like a working one from here — package-visibility
filtering is indistinguishable from "not installed". That needs eyes on the
tablet or logcat.


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
| D20 | Archived policies and disabled assignments stop applying but are never deleted | Preserves the history of what a device once had. ⚠️ **Narrowed by D124 (W48):** an *archived* policy can now be deleted deliberately, from the archive only. Archiving is still the one-click default and still never deletes. |

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

#### 🔻 W35 — Deploy to a reachable server (`209.182.235.108`)

**Why:** the device is no longer on the LAN, and both provisioning URLs are private
addresses (W34 step 6). A device that cannot reach the server fails at the APK
download, and a failed provisioning costs another factory reset before the next try.

⚠️ `209.182.235.108` is **not this machine** — this box's public address is
`47.146.244.101`. Probed: **port 22 open, 80/443/8080/8443 closed**. So it is a
remote host with nothing deployed, and reaching it needs SSH credentials the
project does not have.

##### ✅ The architecture is already built for public exposure

Checked rather than assumed. `docker/nginx/nginx.conf` **default-denies** on the
device port and opts back in per-location:

* **:8443** — `location / { return 403 "not exposed on the device port" }`. Only
  `/api/v1/enroll`, the provisioning APK, `/healthz`, and `/api/v1/device/*`
  (the last two behind a client certificate) are reachable.
* **:8080** — serves **only** `/api/v1/provisioning/agent.apk`; everything else
  403s. It is plain HTTP on purpose: the setup wizard downloads the APK against the
  **system trust store**, before the DPC exists, so a self-signed HTTPS URL fails
  there (§4 of the Android reference).
* **The admin console is on neither.** It binds `127.0.0.1:8000` only.

That last point is what makes `TAKMDM_ADMIN_AUTH_MODE=disabled` survivable on a
public host: the console is not reachable from outside and would be used over an
SSH tunnel. ⚠️ It is still worth stating plainly — **anyone with a shell on that
box has full control of the fleet**, and R8 (`pki/ca.key` unencrypted, mints any
device identity) and R12 (`token_vault.key` decrypts every enrollment secret) both
get materially worse on a machine other people can log into.

##### Plan (6 steps) — blocked on access

1. **Access + host survey.** SSH in; confirm OS, Docker and Compose, and that
   nothing else wants 8080/8443.
2. **Fresh PKI for the new address.** The device CA and server certificate are
   issued for `192.168.68.89`; the agent pins the CA it is handed at provisioning
   (`server_ca_pem` in the admin extras), so both must be regenerated with
   `--hostname 209.182.235.108`. ⚠️ A regenerated CA invalidates every existing
   device certificate — which is moot here, since the one device is being factory
   reset anyway.
3. **Config**: `TAKMDM_SERVER_URL=https://209.182.235.108:8443`,
   `TAKMDM_AGENT_APK_URL=http://209.182.235.108:8080/api/v1/provisioning/agent.apk`,
   `TAKMDM_LAN_ADDRESS=209.182.235.108`.
4. **Firewall**: open 8080 and 8443 inbound; leave 8000 closed.
5. **Deploy**: repo across, `docker compose up -d --build`, migrations to head,
   upload and publish agent 48, mint an enrollment token.
6. **Verify from outside**: `/healthz` over 8443, the APK over 8080, and a QR whose
   component validates — then the operator enrols the reset tablet against it.

⚠️ **Open decision: fresh database or migrate the existing one.** A fresh start is
cleaner given the package rename and the reset, but loses the policies, profiles,
content and TAK.gov link built up here. Not assumed either way.

##### Status: ✅ deployed and reachable. Awaiting the operator's enrolment.

**Host.** Ubuntu 24.04, 4 cores / 16 GB / 293 GB free, Docker 29.6.2, Compose
5.3.1, UFW active. Was **completely empty** — no containers, no compose projects,
nothing in `/root`, `/opt`, `/srv`. A `cachetrak-deploy` key and open 9443/8501
rules are leftovers from something long gone, so nothing was disturbed.

**Access.** `root@209.182.235.108`, key auth. ⚠️ The existing `id_ed25519` is
**passphrase-protected** and there is no ssh-agent, so `BatchMode` could never
unlock it — which is why key auth kept failing despite the key being installed. A
dedicated passphrase-less **`~/.ssh/id_ed25519_atlas_deploy`** was generated for
this host and added to `~/.ssh/config` as **`atlas-prod`**.

**Deployed** to `/opt/atlas`: fresh database, fresh PKI, migrations at
`m3o5q7s9u1w3` (head). Server certificate issued `CN=209.182.235.108` with SANs
`localhost, 127.0.0.1, 209.182.235.108` — the agent pins this at provisioning.

✅ **Verified across the public internet, from a different machine:**

| Check | Result |
|---|---|
| `https://…:8443/healthz` | **200** |
| `https://…:8443/` (console) | **403** — correctly not exposed |
| `http://…:8080/api/v1/provisioning/agent.apk` | **200**, 24 358 090 bytes; parsed back as `com.taksolutions.atlasmdm` 48 declaring the admin receiver |
| `http://…:8080/` (anything else) | **403** — correctly refused |
| QR payload | 6 provisioning keys, carrying `209.182.235.108`, `com.taksolutions.atlasmdm/.admin.MdmDeviceAdminReceiver`, and the checksum |

Agent **48** uploaded and published; primary enrollment token active.

##### 🐛 Two traps hit while deploying, both worth keeping

* **`--exclude='artifacts'` in `tar` is not anchored.** It matched `app/artifacts/`
  as well as the top-level data directory, so the API booted into
  `ModuleNotFoundError: No module named 'app.artifacts'`. Anchored excludes
  (`./artifacts`) fix it; the fix was confirmed by comparing a hash of the package
  tree on both sides rather than by eye.
* **Bind-mounted directories must exist and be owned by uid 1000.** `./pki` and
  `./artifacts` were excluded from the copy, so Docker created them root-owned and
  the unprivileged container died on `PermissionError: '/pki/ca.crt'`.

##### ⚠️ Security posture of a public host

* ✅ **Password login disabled, root password rotated** (2026-09-05). Verified
  both directions: key auth still works, and a password attempt is refused with
  *"No supported authentication methods available (server sent: publickey)"*. The
  operator's own key was confirmed present **before** the change, so nobody was
  locked out. Rescue password is in the session scratchpad for provider-console use.

  ⚠️ **Ubuntu trap worth keeping:** `sshd_config.d/50-cloud-init.conf` ships
  `PasswordAuthentication yes`, and OpenSSH takes the **first** occurrence of a
  keyword — so a `99-`-prefixed hardening file is read *after* it and silently
  loses. `sshd -T` reported `passwordauthentication yes` while the drop-in plainly
  said `no`. Renamed to `00-atlas-hardening.conf`. Always confirm with `sshd -T`
  rather than by reading the file you just wrote.
* The console is loopback-only and unauthenticated — reach it with
  `ssh -L 8000:127.0.0.1:8000 atlas-prod`. **Anyone with a shell on that box has
  full control of the fleet**, and R8 (`pki/ca.key` mints any device identity) and
  R12 (`token_vault.key` decrypts every enrollment secret) are both materially
  worse here than on a laptop.

---

#### 🔻 W36 — The console, reachable from a browser (+ two console refinements)

**Ask:** reach the admin console directly on the web rather than through an SSH
tunnel.

##### ⚠️ Why it cannot simply be exposed

The console is `admin_auth_mode=disabled` — **no authentication whatsoever**.
Publishing it as-is hands anyone who port-scans the address: enrollment tokens
(enrol their own devices), remote **wipe** of every device, arbitrary policy, the
app library, and the TAK.gov credential. Exposure and authentication have to land
in the same change; there is no safe interim.

##### The design

`forward_auth` already exists for exactly this shape — it trusts a proxy to
identify the caller — and Authentik is not needed to satisfy it. **nginx does the
authenticating** on a console-only TLS port and passes the result inward:

* A new **9443** server block (already open in UFW from the host's previous life),
  TLS with the same certificate, **HTTP Basic** over it.
* nginx injects `X-Authentik-Username: $remote_user` and the required group.
* ⚠️ **The whole design rests on those headers being unforgeable.** The app fails
  closed without them, but it trusts them absolutely when present — so if the app
  were reachable directly, anyone could send `X-Authentik-Username: admin` and be
  an administrator. Two things prevent it: the app binds `127.0.0.1:8000` and is
  published on no external interface, and `proxy_set_header` **overwrites** any
  client-supplied value rather than appending. This must be tested by forging the
  header, not assumed.
* `console_origin` set so the CSRF guard and the `Secure` cookie work over HTTPS.

The device ports are untouched: **8443** stays mTLS-only for devices and **8080**
stays the single-file APK endpoint.

##### Plan (6 steps)

1. nginx console block on 9443: TLS, `auth_basic`, header injection, and an
   explicit clear of every inbound `X-Authentik-*`.
2. Generate the htpasswd credential.
3. `.env`: `TAKMDM_ADMIN_AUTH_MODE=forward_auth`,
   `TAKMDM_CONSOLE_ORIGIN=https://209.182.235.108:9443`.
4. Deploy and confirm the console answers over 9443 and **401s without credentials**.
5. **Forge `X-Authentik-Username` from outside and confirm it is refused.** The
   single test that decides whether this is safe.
6. Confirm a form still submits (CSRF + `Secure` cookie over HTTPS) and that 8443
   and 8080 are unchanged.

##### Status: ✅ done and verified from outside.

**Console:** `https://209.182.235.108:9443` — Basic auth over TLS, user `atlas`.
Credential in the session scratchpad. The certificate is self-signed, so a browser
warns once; that is the same certificate the agent pins, not a problem to fix by
weakening anything.

✅ **Verified across the internet, from a different machine:**

| Check | Result |
|---|---|
| no credentials | **401** |
| wrong password | **401** |
| correct credentials | **200** |
| **forged `X-Authentik-Username: attacker` + valid Basic auth** | app reports **`atlas` / `takmdm-admins`** — the forgery is overwritten, not honoured |
| app reachable directly on `:8000` | **unreachable** (published on no external interface) |
| form POST with CSRF over HTTPS | **200**, `Secure` cookie set |
| 8443 healthz / console / 8080 non-APK | **200 / 403 / 403** — device ports untouched |

The forgery test is the one that decides this is safe: `forward_auth` trusts the
header absolutely, so the guard is entirely "only nginx can set it". Two things
hold it up and both were checked rather than assumed — the app is published on no
external interface, and `proxy_set_header` **overwrites** a client-supplied value
instead of appending.

##### ✅ Incidentally proved: the identity plumbing records who acted

The operator linked TAK.gov through the new web console, and the row came back
`linked_by = 'atlas'` — the Basic-auth username, carried inward as
`X-Authentik-Username` and stored by the app. On a fresh database with 0 devices
and 0 policies that was briefly alarming; it is in fact `forward_auth` working end
to end, attributing an action to the person who took it rather than to "anonymous".

⚠️ **A consequence worth stating:** the TAK.gov **offline refresh token now lives
on an internet-facing host**. It is a durable bearer credential to a named person's
TAK.gov account that does not idle out (W29/D36). It is sealed with
`pki/token_vault.key` — which sits beside it on the same disk, so the sealing
protects against a stolen database dump, not against someone with a shell. R12
applies here with more force than it did on a laptop.

##### 🐛 Trap: nginx could not read its own password file

The htpasswd file was written `640` owned by uid 1000 (the API user), but **nginx
workers run as uid 101**, so every request 500'd on
`open() "/pki/console.htpasswd" failed (13: Permission denied)`. Wrong passwords
returned 500 as well, which reads like a broken hash rather than a permissions
problem — the error log was the only thing that said so. Fixed by giving the file
to uid 101 rather than widening the mode; the API never reads it.

⚠️ That ownership is coupled to the `nginx:alpine` image's uid. If the base image
ever changes it, the console 500s again with the same misleading symptom.

##### Console refinements shipped alongside

* **Enrollment SSID placeholder** → *"Enter Network Name"*. ⚠️ There were **two**
  fields with the old `TAK-Field` placeholder — `enroll.html` and `token_qr.html`
  — and only the first was obvious. A value-shaped placeholder reads as something
  to keep rather than an example of what to type.
* **TPC plugin filter**, live as typed, matching across plugin name, package name
  and description together: an operator hunting "video" should not have to know
  which of the three the word lives in. Multiple words all have to match, so
  "uas 5.8" narrows rather than widening. It filters rows already on the page —
  the catalog is fetched once, so there is nothing to ask the server for between
  keystrokes — and renders only when there is something to filter.
* 🐛 **Fixed while there: a test was calling the real tak.gov on every run.** The
  import route starts a genuine background thread, so
  `test_starting_an_import_returns_a_job_to_poll` reached out to somebody else's
  server each time the suite ran. Stubbed. Its assertion also pinned the job to
  `state == "running"`, which was a race the stub exposed — the contract is *202
  with a job id*, not how far the job got.

---

#### 🔻 Enrolment stuck at "Getting your tablet ready" — 2026-09-05

**Evidence first, before changing anything.** The proxy log shows **zero requests
for `agent.apk`, ever**, and `select count(*) from device` is **0**. The only
traffic was the operator's browser on 9443, this machine's `curl`, and two internet
scanners. So the tablet **never reached the server at all** — it is stuck *before*
the download, not during it.

That rules out the server: the APK, the checksum, the admin component and the QR
were all verified end to end from a different machine minutes earlier.

**Most likely cause: the device's network, not ours.** The download URL was
`http://209.182.235.108:8080/…`, and **outbound 8080 is exactly what guest Wi-Fi,
hotel, and corporate networks block**. The setup wizard cannot say so; it sits on
"Getting your tablet ready".

**Change made:** the APK-only endpoint now also listens on **port 80**, and
`TAKMDM_AGENT_APK_URL` points there. Nothing else is served on that listener —
every other path still 403s — so widening the port widens no surface. Verified over
the internet: **200, 24 358 090 bytes** on both 80 and 8080, and a freshly generated
QR carries the port-80 URL.

⚠️ **Still to confirm by the operator**, because it cannot be tested from here:
that the tablet's network reaches the box at all. From a phone **on the same Wi-Fi
as the tablet**, opening
`http://209.182.235.108/api/v1/provisioning/agent.apk` should download 24 MB. If
that fails, the network is the problem and no server change will fix it.

⚠️ A failed provisioning costs another factory reset before the next attempt
(§1 of the Android reference), so the download is worth proving from that network
*before* re-scanning.

---

#### 🔻 W37 — Moved to the demo host `208.87.130.181`; old host pruned

**`209.182.235.108` is gone.** `docker compose down -v`, `/opt/atlas` removed,
`docker system prune -af --volumes` — 1.9 GB reclaimed, zero containers, volumes
and images left. Two deliberate non-reversions: the SSH hardening stayed (pruning
ATLAS is not a reason to re-open root password login on a public address), and the
`atlas-deploy` key was removed from a box no longer being managed. The operator's
own key and the pre-existing `cachetrak-deploy` key are untouched.

⚠️ **The TAK.gov link died with it.** It lived only in that database, and the
credential is per-instance, so the demo host needs its own link — a fresh
3-minute device-code flow at Admin → TAK.gov.

##### ⚠️ The new host is *not* empty — it serves a live site

`208.87.130.181` (`evanserver`) already runs **`evan.leckliter.net`** on system
nginx :80/:443, plus a node app on :3001 and python on :8787. ATLAS takes none of
those. The plain-HTTP APK endpoint was moved to **8081** and the compose port made
configurable (`TAKMDM_APK_HTTP_PORT`, still defaulting to 80 for an ordinary host).
The site was re-checked after deployment and still answers.

##### 🐛 A 56-day hung `apt-get` blocked the Docker install

`apt-get -qq -y update` had been running since **early July** holding the lists
lock, so `get.docker.com` could not proceed. Killing it left
`/var/lib/apt/lists/partial` corrupted, which then failed differently
(`pkgAcqTransactionItem::TransactionState-stat`) — the second error looked
unrelated to the first and was caused by the fix for it. Clearing the lists
directory and recreating `partial` resolved it. Docker 29.8.0 / Compose 5.5.1.

##### Deployed and verified from the public internet

| Check | Result |
|---|---|
| `https://208.87.130.181:8443/healthz` | **200** |
| `https://208.87.130.181:8443/` | **403** — console not on the device port |
| `http://208.87.130.181:8081/…/agent.apk` | **200**, 24 358 090 bytes |
| `https://208.87.130.181:9443/` without credentials | **401** |
| `evan.leckliter.net` after deployment | **still serving** |

Agent **48** published, primary enrollment token active, migrations at head.

⚠️ **Console writes now need CSRF *and* an Origin match.** With `forward_auth` on,
scripted `curl` against `127.0.0.1:9443` fails twice over — 401 without Basic auth,
then **403** because the CSRF guard compares `Origin` against
`TAKMDM_CONSOLE_ORIGIN`, which names the public address. Automation has to fetch a
token with a cookie jar and post to the real origin. Worth knowing before assuming
a write silently failed.

---

#### 🔻 W38 — Deploy to a freshly reimaged `209.182.235.108`

**Why:** the operator handed over a new root password for this address, calling it
a fresh dev server, and said security is not a concern here. This is the **same
address** W35 deployed to and W37 later pruned (`docker compose down -v`,
`/opt/atlas` removed, SSH hardening left in place, deploy key removed) — so the
first job is confirming this is genuinely a clean reimage and not that hardened
box answering differently than expected.

**Survey (2026-09-04), password auth via `plink -pw`:** hostname `taksolutions`,
Ubuntu 24.04.3 LTS, **uptime 4 minutes**, only `sshd` listening (no 8080/8443/9443,
no ufw installed), no Docker installed, 15 GB RAM / 297 GB free disk. This is a
clean reimage, not the old hardened host — confirmed rather than assumed.

Because the operator explicitly waived security for this box, this deployment
**deliberately skips** the hardening W35 did on the same address last time:
staying on root **password** auth throughout (no dedicated deploy key), and not
touching `sshd_config` (password login stays open, root password left as given).
`docker-compose.yml`'s 9443 console block still hard-requires `auth_basic` against
`/pki/console.htpasswd` regardless of app-level `TAKMDM_ADMIN_AUTH_MODE` — that
file still has to exist or nginx 500s every console request — so a Basic-auth
credential is created anyway, just not treated as a real security boundary here.

Not touching `atlas-demo` (`208.87.130.181`) — this is a separate target, not a
move.

##### Plan (6 steps) — ✅ all done

1. ✅ **Access + host survey** (above).
2. ✅ Docker 29.8.0 + Compose plugin installed from `get.docker.com`, clean run.
3. ✅ Repo copied to `/opt/atlas` via `tar`/`pscp` with anchored excludes (verified
   `app/artifacts/` survived and top-level `./pki`, `./artifacts` did not — no
   repeat of W35's unanchored-exclude trap). `pki/` and `artifacts/` created and
   `chown 1000:1000` **before** first `compose up`, so Docker never auto-created
   them root-owned (W35's other trap). Console credential `atlas` / (rotate before
   any real use) written to `/pki/console.htpasswd`, owned `101:101` for the nginx
   image (W36's permission trap).
4. ✅ `.env` written exactly as planned.
5. ✅ `docker compose up -d --build` — clean build, `init` issued a dev cert for
   `localhost, 127.0.0.1, 209.182.235.108`, migrations ran unattended to
   `m3o5q7s9u1w3` (head), all four ports (`80, 8080, 8443, 9443`) bound on first try.
6. ✅ **Verified from this machine over the public internet:**

   | Check | Result |
   |---|---|
   | `https://…:8443/healthz` | **200** |
   | `https://…:8443/` (console) | **403** — correctly not exposed |
   | `https://…:9443/` no credentials | **401** |
   | `https://…:9443/` with `atlas` credentials | **200** |
   | `http://…/api/v1/provisioning/agent.apk` (port 80) | **404** — route matches, nothing uploaded yet |
   | `http://…:8080/api/v1/provisioning/agent.apk` | **404** — same |
   | `http://…/` (anything else, port 80) | **403** |

   No firewall step was needed — the box had no ufw/iptables rules, and every
   port was reachable on the first check.

**Deliberately out of scope this pass:** uploading an agent build and minting an
enrollment token. The checked-in release APK at
`agent/app/build/outputs/apk/release/app-release.apk` predates the
`com.taksolutions.atlasmdm` package rename (925c941) and several feature commits
since; publishing it would silently ship a stale, pre-rename agent. No device
enrollment is imminent, so this is left for a follow-up chunk once a current
release build exists (`cd agent && .\gradlew.bat assembleRelease` at the JDK 17
toolchain) rather than shipping something known-stale now.

---

#### 🔻 W39 — Decommissioned the demo host `208.87.130.181`

**Why:** ATLAS now lives on freshly reimaged `209.182.235.108` (W38); the operator
asked to break down the demo host deployment. Full removal, confirmed with the
operator given it permanently destroys the DB (enrolled devices, policies, the
TAK.gov link) with no stated backup — same shape as W37's decommission of the
previous `209.182.235.108` instance.

**Survey before touching anything** (rule: gather evidence, don't assume on a
shared box): `docker ps -a` showed exactly ATLAS's 4 containers
(`takmdm-proxy-1`, `takmdm-api-1`, `takmdm-db-1`, `takmdm-init-1` exited) under
compose project `takmdm` at `/opt/atlas`. Everything else on this box is
non-Docker: system `nginx` (`evan.leckliter.net`, 80/443), `evan-api.service`,
`gamenight-backend.service`, a bare `node` on 3001, a bare `python3` on 8787 —
all systemd/host-managed, none touched by anything below.

##### Plan (5 steps) — ✅ all done, 2026-09-05

1. ✅ Host survey (above) — confirms Docker on this box is ATLAS-only.
2. ✅ `docker compose down -v` — all 4 containers, `takmdm_default` network, and
   the `pgdata` volume removed.
3. ✅ `docker system prune -af --volumes` — reclaimed 1.04 GB. Incidentally
   removed one unrelated dangling `httpd:alpine` image found already sitting
   unused on the box; consistent with `-af`'s documented scope and harmless
   since nothing referenced it.
4. ✅ `/opt/atlas` removed.
5. ✅ **Verified:** `ss -ltnp` shows 8080/8081/8443/9443 gone entirely; `8443`
   and `9443` externally refuse connections. `evan-api`, `gamenight-backend`,
   `nginx` all still `active`, and `https://evan.leckliter.net/` still answers
   **200**.

`208.87.130.181` is now exactly as it was before ATLAS ever touched it.

---

#### 🔻 W40 — Fixed QR generation on `209.182.235.108`: no agent build was ever uploaded

**Symptom:** the operator hit `agent_signature_checksum is not configured; Android
will reject provisioning without the base64url SHA-256 of the agent signing
certificate` when generating a QR.

**Root cause, not assumed — traced in code.** `app/services/provisioning.py`
raises exactly this string when `settings.agent_signature_checksum` is empty.
`app/config.py` shows this is a **pure env-var setting** (`TAKMDM_AGENT_SIGNATURE_CHECKSUM`,
no DB-backed override) — nothing sets it automatically when a build is uploaded.
W38's `.env` for this host never included it, deliberately: no current release APK
existed (the checked-in one predates the `com.taksolutions.atlasmdm` rename), so
agent upload was explicitly deferred. This is that deferred work, now needed.

⚠️ **[docs/ANDROID_PLATFORM_REFERENCE.md](docs/ANDROID_PLATFORM_REFERENCE.md)
§Signature checksum records two different values for two different keys** — the
debug keystore's `h5QFWJTb6y5MX0kxuTiEeP7-wzHaSizE5zgAT-PzWA4` (this is what sits
in the local dev `.env`) and the release keystore's
`IJS8zAVMaB9G2MgSN4wHZXzzOd19ToC1RgJrd6_yxkQ`. Copying the dev `.env` value here
would have "fixed" the error message while shipping a checksum for the wrong key —
exactly the trap that doc section warns about. The value actually deployed must be
re-verified against whatever APK gets uploaded, not assumed from either recorded
constant.

##### Plan (6 steps)

1. Build a current release APK from source (`cd agent && .\gradlew.bat
   assembleRelease`, JDK 17), signed with the local `agent/keystore.properties`
   key — reflects the package rename and every feature commit since the stale
   checked-in build.
2. Verify the built APK's signing certificate SHA-256 (`apksigner verify
   --print-certs`) before trusting it — confirms which of the two documented
   checksums (or a third, if the key ever changed) actually applies.
3. Copy the APK to `209.182.235.108` and upload it through the admin API/console
   so the server records it as an agent build and returns `provisioning_checksum`.
4. Cross-check step 3's returned checksum against step 2's independently-derived
   one — they must match byte-for-byte.
5. Add `TAKMDM_AGENT_SIGNATURE_CHECKSUM` (the confirmed value) to `/opt/atlas/.env`
   and `docker compose up -d` to recreate `api` with it.
6. Publish the build, mint an enrollment token, and confirm a QR generates
   without error.

##### Status: ✅ done, 2026-09-05

1. ✅ Built `app-release.apk` at `versionCode 48` / `versionName 0.13.0`
   (`com.taksolutions.atlasmdm`) from current source.
2. ✅ `apksigner verify --print-certs` → cert SHA-256
   `2094bccc054c681f46d8c812378c07657cf339dd7d4e80b546026b77aff2c644` — the
   documented **release** key, not the debug one.
3. ✅ Uploaded via `POST /api/v1/packages`, hitting the app directly on the box's
   own `127.0.0.1:8000` with hand-set `X-Authentik-Username`/`X-Authentik-Groups`
   headers rather than real Basic auth over 9443 — legitimate here since a root
   shell on this box already has that trust level (documented in W35's security
   posture), and it sidesteps re-deriving Basic auth just for a one-off upload.
   Server independently reported `provisioning_checksum:
   "IJS8zAVMaB9G2MgSN4wHZXzzOd19ToC1RgJrd6_yxkQ"`.
4. ✅ Cross-checked: `base64url(SHA-256(cert DER))` computed independently from
   the digest in step 2 gives the same string. Matches
   [docs/ANDROID_PLATFORM_REFERENCE.md](docs/ANDROID_PLATFORM_REFERENCE.md)'s
   recorded release-key value byte-for-byte.
5. ✅ Appended `TAKMDM_AGENT_SIGNATURE_CHECKSUM=IJS8zAVMaB9G2MgSN4wHZXzzOd19ToC1RgJrd6_yxkQ`
   to `/opt/atlas/.env`; `docker compose up -d` recreated `api` with it.
6. ✅ Published build 48 (`POST /admin/agent/publish`), created the primary
   enrollment token (`POST /enrollment/primary`) — none existed yet, W38 having
   deliberately deferred this. The returned page renders a QR `<svg>` carrying
   the correct checksum and **no trace of the earlier error.**

Handled the console's CSRF requirement (W36/W37: form-shaped POSTs need a
matching cookie + `x-csrf-token`) by `curl -c cookiejar` against a GET page first,
then replaying that cookie's value as both the cookie and the token on each
subsequent POST — same double-submit shape the browser does automatically.

`209.182.235.108` is now fully enrollment-ready: a device scanning the current
primary QR gets `com.taksolutions.atlasmdm` build 48, correctly checksummed.

---

#### 🔻 W41 — Removed the on-device re-enrol escape hatch; fixed a first-sync password crash on fresh devices

**Two operator reports, both in the DPC app.**

**1. Remove "Discard identity and re-enrol."** The Device tab's re-enrol card
(`MainActivity.renderDevice`, `reEnroll()`, and the `action_reenroll` /
`reenroll_rationale` / `reenroll_hint` strings) let anyone with the device in hand
wipe its identity and enter an arbitrary token, no server-side gate. Removed the
card, the handler, and the strings; dropped the now-unused `EditText` and
`DeviceIdentity` imports from `MainActivity.kt`. `DebugConfigReceiver`'s adb-only
`reset_identity` broadcast extra is untouched — that is a bench tool reached over
`adb shell am broadcast`, not a control an operator or device holder can tap.

**2. Password crash on a freshly imaged tablet with no policy at all.**
`password min length: password quality should be at least 131072 for
setPasswordMinimumLenght, but i have no policies applied`.

**Root cause, traced in code before touching anything (rule 4).**
`PolicyApplier.applyPassword` calls `dpm.setPasswordMinimumLength(admin, ... ?: 0)`
**unconditionally** — the R14/W26 "release absent fields to permissive" design.
On a device that has never had a policy, effective quality is `UNSPECIFIED`
(`PasswordPlan.effectiveQuality`), and the platform throws
`IllegalStateException` calling `setPasswordMinimumLength` at *any* quality below
`NUMERIC` — **including a release to 0.** Not the same throw as the documented
Letters/Numeric/Symbols-require-COMPLEX rule (Android reference §6c); a
previously-unknown sibling constraint, found live because it fired on the very
first sync a device ever does.

⚠️ **[docs/ANDROID_PLATFORM_REFERENCE.md](docs/ANDROID_PLATFORM_REFERENCE.md)
updated** in both places this touches: the setter table (new row) and the
"setters latch" section, which had stated the unconditional-push rule as safe —
correction added alongside the original text rather than silently rewritten (per
CLAUDE.md §6), marked **not yet re-verified on hardware**.

**Fix:** new `PasswordPlan.minLengthApplies(quality) = quality >= NUMERIC`,
mirroring the existing `charClassMinimumsApply` gate at `COMPLEX`; `PolicyApplier`
now only calls `setPasswordMinimumLength` when it holds. Below `NUMERIC` a stale
length is inert — same reasoning already accepted for the char-class fields — so
nothing is lost by leaving it latched there. Added
`minLengthApplies only at NUMERIC or above` to `PasswordPlanTest`. Full agent
`testDebugUnitTest` suite passes.

**Shipped:** bumped `versionCode 48 → 49` (`0.13.1`) — 48 was already uploaded to
`209.182.235.108` in W40, and the server refuses a duplicate versionCode. Built,
verified the signing certificate is still the same release key (no re-derivation
of the checksum needed — that only changes with the key, not the version),
uploaded, and published 49 so the tablet's next check-in self-updates onto the
fix. The password error will keep recurring each sync **until that self-update
lands** — it is cosmetic/re-asserted, not a stuck state, and does not block
check-in or the update decision itself.

✅ **Done, 2026-09-05:** v49 uploaded to `209.182.235.108` (`provisioning_checksum`
unchanged, `IJS8zAVMaB9G2MgSN4wHZXzzOd19ToC1RgJrd6_yxkQ` — same key, only the
version moved) and published via `/admin/agent/publish`. Not yet confirmed on the
tablet itself — that needs its next check-in/self-update cycle, which was not
triggered from here.

##### 🐛 Follow-up: the operator hit "Sync now" and nothing happened

**Not a fluke — traced to a real deadlock, confirmed against the live DB before
acting (rule 4).** `select ... from device` showed
`compliance_status = DEGRADED`, `agent_version_code = 48`, `compliance_detail`
exactly the password error. `app/services/agent_update.py:decide()` explicitly
refuses to offer an update when `compliance in (DEGRADED, FAILED)` ("never stack
an agent swap on a device already failing to apply what it has"). Sound rule in
general — but here it deadlocks: the bug that degrades the device is the same bug
v49 fixes, so every sync re-confirms DEGRADED and re-blocks the very update that
would clear it. `settled` was not the blocker; compliance was.

**Unblocked without touching the safety gate** (operator's choice over a raw DB
edit): created profile `93c3e6b8-ceda-4e2e-bf03-03f70c6e4446` ("Temp: unblock v49
self-update") with a `password` section (`{"quality": 2}` — NUMERIC, no
length/complexity floor) and assigned it to `R5GL40MMHRN`
(`85a69e0f-51a7-43c0-92a4-e5f2cb09a24b`). This alone stops the **v48** crash too:
once quality is actually NUMERIC on-device, `setPasswordMinimumLength` satisfies
Android's own requirement without needing the code fix present, so the next sync
should report zero apply errors, flip to COMPLIANT, and unblock the self-update
gate for v49 on the sync after that. ⚠️ **Not yet confirmed** — needs the
operator's next "Sync now" (twice: once to clear DEGRADED, once more to actually
receive v49) to verify. Visible side effect while this profile is assigned: the
tablet now requires *some* numeric lock-screen PIN be set. Worth removing this
profile once v49 is confirmed running, since v49 no longer needs it.

**Caught along the way:** the profile-creator API takes the catalog's lowercase
key (`"password"`), not the registry policy type (`"PASSWORD"`) used everywhere
else in specs/payloads — `POST /api/v1/profiles` silently drops an unrecognized
section key rather than rejecting it (`creator_catalog.get(key)` returns `None`,
`profile_service.create_profile` just skips it), so the first attempt returned
`201` with `"sections": []` and no error at all. Worth a look: `PolicyProfile`
creation raising or warning on an unmatched section key would have caught this in
one round trip instead of two.

✅ **Confirmed, 2026-09-05:** DB shows `agent_version_code 49`, `agent_version
0.13.1`, `compliance_status COMPLIANT`, no `compliance_detail` — the tablet
self-updated cleanly and the crash is gone. Archived the temporary unblock
profile (`93c3e6b8…`); per W22, archiving deletes the assignment outright, so the
forced numeric PIN requirement leaves with it, and this time the device's next
reconcile releases the quality back to `UNSPECIFIED` under the **fixed** v49 code
path, which no longer throws.

**Open design question, not acted on:** the DEGRADED-blocks-update gate has no
escape hatch for "the operator knows this specific build fixes this specific
degradation." Worth an admin override (e.g., "offer this build to this device
regardless of compliance") if this pattern recurs — not built now since it is a
real design decision (how does an operator assert that, and should it be
per-device or per-build), not a bug fix.

---

#### 🔻 W42 — Wire the Customizations category: support message + lock screen

**Ask:** build out the `customizations` category and its two sub-sections.
*Support message* carries **"Disabled setting message"** and **"Admin app custom
description"**; *Lock screen* carries a **custom message shown on the device's
lock screen**. The category already exists in `creator_catalog.py` as a
**placeholder** (`Category("customizations", ..., None, subtopics=("support
message", "lock screen"))`) — this lights it up.

##### Platform contracts, read from the SDK source before writing anything (rule 6)

The Android reference had **nothing** on these three, so they were read from
`sources/android-36.1/android/app/admin/DevicePolicyManager.java` — the same
authority §hotspot used — rather than from recollection:

| API | Contract |
|---|---|
| `setShortSupportMessage(admin, msg)` | *"displayed to the user in settings screens where functionality has been disabled by the admin"* — **exactly** the operator's "Disabled setting message". **>200 chars may be truncated.** `null` clears. `SecurityException` if not an active admin. |
| `setLongSupportMessage(admin, msg)` | *"displayed to the user in the device administrators settings screen"* — the operator's "Admin app custom description". **>20000 chars may be truncated.** `null` clears. |
| `setDeviceOwnerLockScreenInfo(admin, info)` | Owner info on the lock screen. ⚠️ *"overrides any owner information manually set by the user and **prevents the user from further changing it**"*. `null`/empty clears **and restores the user's own info**; whitespace-only blanks it *and still locks the user out of it*. DO only. |

⚠️ **All three latch**, so `applyCustomizations` must run **even when the section
is absent** and push `null` — the same rule as PASSWORD/RESTRICTIONS/NETWORKS in
`PolicyApplier.apply()` (R14/R19). Unlike the W41 min-length trap, all three
accept `null` unconditionally, so there is no gating hazard here.

##### Plan (6 steps)

1. Record the three contracts in
   [docs/ANDROID_PLATFORM_REFERENCE.md](docs/ANDROID_PLATFORM_REFERENCE.md).
2. **Server spec** — `app/policies/specs/customizations.py`: `CustomizationsSpec`
   with `disabled_setting_message` + `admin_app_description` (`ui_group`
   "Support message") and `lock_screen_message` (`ui_group` "Lock screen"), all
   `HIGHEST_RANK` (two stacked policies cannot concatenate a message; one has to
   win, and rank is how this project already breaks that tie). Register
   `CUSTOMIZATIONS`; flip the catalog `Category` from placeholder to wired. The
   `ui_group`s *are* the sub-pages — W12 derives them, so no separate wiring.
3. **Console** — add a `text` (textarea) control to `form_schema` /
   `_policy_form.html`; a 200-character support message in a single-line input is
   the wrong shape. `max_length` on the fields so the operator is stopped at the
   console rather than silently truncated on the device.
4. **Agent** — `PolicyApplier.applyCustomizations`, dispatched unconditionally
   from `apply()` alongside the other latching families.
5. **Tests** — server: registry/spec validation, HIGHEST_RANK stacking, the
   generated form's two sub-pages. Agent: the pure blank/absent → `null`
   normalisation.
6. Build both, run both suites, bump the agent version, ship to
   `209.182.235.108`, and confirm on `SM-X520`.

##### Status: ✅ built and shipped, 2026-09-05 — hardware confirmation outstanding

1. ✅ Contracts recorded in the Android reference (§"Operator-facing text").
2. ✅ `CustomizationsSpec` + `CUSTOMIZATIONS` registered; catalog entry flipped
   from placeholder to wired.
3. ✅ New `text` (textarea) control with a live character counter.
4. ✅ `PolicyApplier.applyCustomizations`, dispatched unconditionally; the
   blank/null rule extracted to `CustomizationsPlan` (the codebase's `*Plan`
   convention) so it is unit-testable.
5. ✅ **654 server tests** (10 new) and the full agent suite (5 new) pass.
6. ✅ Agent **v50 (`0.14.0`)** built, signature re-verified as the same release
   key, uploaded and published; server rebuilt on `209.182.235.108` with
   `CUSTOMIZATIONS` confirmed live in `/api/v1/policy-types`.

**Verified on the running server, not just locally:** a profile carrying all
three fields round-trips through `POST /api/v1/profiles`, and the editor renders
**two sub-pages** (`customizations:support-message`, `customizations:lock-screen`)
with three textareas carrying `maxlength` 200 / 20000 / 200 and their counters.

⚠️ **Not yet hardware-proven.** `SM-X520` is `COMPLIANT` on **v49** and will take
v50 on its next check-in (the compliance gate that deadlocked W41 is clear this
time). No CUSTOMIZATIONS policy was assigned from here — the messages are the
operator's own words to write, and inventing text to push onto their device is not
this chunk's call to make. The DPM calls are proven the moment a policy carrying
them lands and the device checks in `COMPLIANT`; a failure would surface as an
`apply_error` naming the exact field.

##### 🐛 Fixed in passing: string length bounds never reached any form control

`form_schema._bounds` read only the numeric comparisons (`ge`/`gt`/`le`/`lt`).
Pydantic delivers a string's `min_length`/`max_length` as `annotated_types.MinLen`
/ `MaxLen`, which carry neither — so `FormField.minimum`/`maximum` were always
`None` for strings, and **every `minlength`/`maxlength` the templates rendered off
them was a silent no-op**. Visible now: the passcode field's `maxlength="16"`
started working the moment the fix landed, having never worked before. Found only
because the 200-character support-message cap depended on it.

---

#### 🔻 W43 — Network data use management: the half AOSP can actually do

**Ask:** build the `network_data_use` category with two sub-sections — *Data usage
restrictions* and *App-wise restrictions* — modelled on Hexnode's screens
(tracking toggles, network-blocking radios, threshold notification/restriction
rows, daily/monthly reset windows, and per-app rules).

##### ⚠️ Researched before writing anything — the ask splits cleanly in two

| Hexnode control | Reachable by a normally-installed AOSP Device Owner? |
|---|---|
| Enable data usage tracking, per-app + total, mobile vs Wi-Fi | ✅ **Yes, and with no grant to beg for.** `NetworkStatsManager`'s own javadoc: *"Device owner apps and carrier-privileged apps likewise get access to usage data for all users on the device."* No `PACKAGE_USAGE_STATS` prompt, unlike a third-party app. |
| Threshold notifications, daily/monthly reset windows | ✅ Yes — our own accounting on top of those stats. |
| **Block Wi-Fi data / mobile data / all connections** | ❌ **No such API.** The `DISALLOW_*` family governs *configuration* (`no_config_wifi`, `no_change_wifi_state`, `no_config_mobile_networks`), not data flow. `DISALLOW_DATA_ROAMING` blocks roaming only. |
| **Per-app network restriction** ("app-wise") | ❌ **No.** The API Settings itself uses for per-app metered-data policy, `NetworkPolicyManager.setUidPolicy`, is `@hide` + `@SystemApi(client = MODULE_LIBRARIES)` — unreachable by a DO. |

Hexnode reaches the blocking half through **Knox** on Samsung, which their own
sidebar gives away ("Knox Configurations", "APN (Knox)"). [docs/KNOX.md](docs/KNOX.md)
§4.1 had already landed in the same place independently: `net.firewall.Firewall`
is *"per-app and device-wide allow/deny… **The single biggest win**"*, and Chunk 7
step 4 is already written as *"Firewall first — the highest-value capability with
no AOSP equivalent."* So the blocking controls in the screenshots **are** the Knox
work, not a gap in this implementation.

**Operator's call (2026-09-05): build the tracking half now; render the blocking
controls disabled and labelled as needing Knox** — rather than shipping controls
that save cleanly and change nothing, which is the failure mode this codebase
already refuses elsewhere (`test_a_policy_with_no_image_is_refused`).

##### Plan (6 steps) — server + console only

1. Record the capability finding in
   [docs/ANDROID_PLATFORM_REFERENCE.md](docs/ANDROID_PLATFORM_REFERENCE.md), both
   halves: the free-for-a-DO stats access and the two walls.
2. `NetworkDataUseSpec` — enforceable fields (`track_usage`, notification rules,
   reset window) and Knox-gated ones (`network_restriction`, restriction rules,
   per-app blocking), split across the two `ui_group`s that become the sub-pages.
3. A general **`ui_requires`** marker: `FormField.requires` surfaces it, the form
   renders that control **disabled with a badge**, and the spec **refuses** a value
   for it with a message naming Knox. Gated-but-inert is the one outcome not
   allowed — an operator must never save something that does nothing.
4. A repeatable-row control for the threshold rules (`period` / `metric` /
   `threshold_mb`), and an app-wise variant whose first column picks from the
   uploaded application list.
5. Register the type, flip the catalog `Category` from placeholder to wired, and
   test: spec validation, the Knox refusal, both sub-pages, row parsing, stacking.
6. Full suite + deploy the server. **The agent applier is deliberately its own
   chunk** — querying `NetworkStatsManager`, holding accounting windows across
   reboots, evaluating thresholds and raising notifications is a 5-7 step piece of
   Android work in its own right, and it is the half that needs hardware proof.

##### Status: ✅ server + console done and deployed, 2026-09-05

**668 server tests** (14 new). `NETWORK_DATA_USE` live in
`/api/v1/policy-types` on `209.182.235.108`. Verified on a real profile through
the running console: both sub-pages render
(`network_data_use:data-usage-restrictions`,
`network_data_use:app-wise-restrictions`), all four rule row-sets are present, the
app-wise rows carry the uploaded-app picker, saved values round-trip into the
rows, and the three Knox-gated controls render inside `<fieldset disabled>` with a
"needs Knox" badge — **3 disabled controls, 3 badges**, matching exactly the
fields marked `ui_requires`.

The gate is enforced twice on purpose: a disabled fieldset submits nothing, and
the spec's validator refuses the value anyway for a request that bypasses the
form. Its message names every offending field at once and says "needs Knox", so
one save produces one actionable error rather than three round trips.

##### 🐛 Fixed in passing: `UNION` crashed on a list of objects

`_merge_union` de-duplicated via a `set` of the items themselves, typed
`Sequence[Hashable]` — written for lists of scalars (package names, SSIDs). The
first spec to union a list of *objects* (a usage-threshold row) hit
`TypeError: unhashable type: 'dict'` **from inside the merge**, which surfaces as
a server fault rather than a policy problem. Now de-duplicates on sorted-key JSON
for unhashable items, so two identical rules written in a different field order
collapse to one. Scalars keep their old fast path.

##### ⚠️ Nothing reaches the device yet — by design, and worth stating plainly

The agent has **no `NETWORK_DATA_USE` applier**, so `PolicyApplier.apply()` never
reads the section. Assigning one of these policies today is silent: no apply
error, device stays `COMPLIANT`, and no data is tracked. That is the same
"saves cleanly, does nothing" shape this chunk refused for the *blocking* fields —
tolerated here only because the applier is the very next chunk rather than a
capability that may never arrive. **It should not be left in this state**, and an
operator should not be told tracking works until W44 lands.

---

#### 🔻 W44 — The data-usage tracker on the device

**Approved 2026-09-05.** Makes W43's tracking half real: the agent reads usage,
holds accounting windows, and warns the device user when a threshold is crossed.

##### API contracts, read from the SDK source first (rule 6)

| Fact | Consequence |
|---|---|
| The `NetworkTemplate` overloads of `querySummaryForDevice` / `queryDetailsForUid` are **`@SystemApi(MODULE_LIBRARIES)`** | We are **required** to use the `int networkType` overloads, whose `ConnectivityManager.TYPE_MOBILE` / `TYPE_WIFI` constants are themselves deprecated. Deprecated-but-mandatory; not a smell to clean up. |
| `subscriberId` is *"guarded by additional restrictions"* from API 29 | Pass **`null`** — documented to mean "all mobile networks", and avoids needing privileged subscriber access. |
| `querySummaryForDevice` is `@WorkerThread` and *"may take a long time"* | Only ever called from the sync worker, never the UI thread. |
| Returns *"Bucket object or **null** if permissions are insufficient"* | A null return is the signal that the DO-gets-it-free claim is wrong on this hardware — reported as an apply error, not treated as zero bytes. **Zero and unknown must not look alike.** |
| Existing notification channel is `IMPORTANCE_LOW` (foreground-service sync) | A data-usage warning needs its own **`IMPORTANCE_DEFAULT`** channel, or it lands silently in a tray nobody opens. |
| `POST_NOTIFICATIONS` already in the manifest | Nothing new to request; a DO can self-grant it (it is a `dangerous` runtime permission). |

##### Plan (6 steps)

1. Record those contracts in the Android reference under §W43.
2. **`DataUsagePlan`** (pure, tested): the accounting window for a period given
   `reset_daily_at` / `reset_monthly_on_day` and "now"; which rules a usage figure
   crosses; and a stable **once-per-window key** so a crossed threshold warns once
   rather than at every sync.
3. **`DataUsageTracker`** (hardware): per-transport device totals and per-UID
   figures via the int-overload queries, package→UID through `PackageManager`, and
   a null return surfaced as an error rather than a zero.
4. A `IMPORTANCE_DEFAULT` notification channel and the warning itself.
5. Wire into `Reconciler` alongside the other reconcile steps, failures collected
   the same way.
6. Build, both suites, ship **v51**, and prove on `SM-X520` — including the claim
   §W43 records as documented-but-unverified: that a Device Owner reads other
   apps' usage with no grant.

##### Status: ✅ **hardware-proven on `SM-X520`, 2026-09-05**

```
I/Application:      agent starting (v0.15.0)
I/BootReceiver:     restarting after android.intent.action.MY_PACKAGE_REPLACED
I/DataUsage:        data usage warning raised: device total_data monthly 1MB at 552.5 MB
I/SyncService:      sync: state=3 applied=3 errors=0
I/SyncService:      sync: state=3 applied=3 errors=0     ← no repeat warning
I/SyncService:      sync: state=3 applied=3 errors=0     ← nor here
```

Four things proven in six lines:

1. **The Device Owner stats exemption is real on One UI 8** — 552.5 MB read with
   `PACKAGE_USAGE_STATS` never granted. §W43's documented-but-unverified note is
   now ✅ verified; the manifest declaration is a fallback nobody needed.
2. **v51 arrived by self-update** (`MY_PACKAGE_REPLACED`), not by sideload.
3. **The threshold fired**, and `errors=0` on that sync and every one since.
4. **The once-per-window dedupe works on hardware** — warned once at 07:49:10 and
   stayed silent across the syncs at 07:51, 07:53 and onward. Without it this
   would have re-warned every two minutes.

##### 🐛 Diagnosis note: apply errors lag one check-in

Chasing "no notification appeared" produced a false reading first. `Reconciler`
puts `config.lastApplyErrors` on the **check-in request** and only *then* applies
the new desired state, so a check-in reports the *previous* cycle's errors. A
COMPLIANT status read immediately after assigning a policy therefore says nothing
about that policy — the first reading was quoted as proof and had to be retracted.
Wait for the *second* check-in after an assignment before believing a verdict.

##### ⚠️ What was actually wrong: nothing. The notification was invisible, not missing.

The warning posted correctly; the operator was watching a fullscreen video and an
`IMPORTANCE_DEFAULT` channel does not raise a heads-up banner over one — it landed
silently in the shade.

##### 🔧 v52 — raised to `IMPORTANCE_HIGH`, which needed a **new channel id**

Operator asked for high importance. Editing the constant would have been a no-op:
`createNotificationChannel` documents that *"the importance of an existing channel
will only be changed if the new importance is **lower** than the current value"*,
and deleting first does not help — *"if you create a new channel with this same
id, the deleted channel will be un-deleted with all of the same settings"*. So the
one build that mattered, the one already on the tablet, would have ignored the fix
entirely. Checked against the SDK source before editing rather than after shipping.

`takmdm_data_usage` → **`takmdm_data_usage_v2`** at `IMPORTANCE_HIGH`, created in
`AtlasMdmApplication.onCreate` beside the sync channel, with the legacy id deleted
so the app's settings do not show a dead duplicate. Recorded in the Android
reference as its own trap — importance ratchets downwards only, so **pick it when
the channel is born**.

✅ **v52 re-verified on `SM-X520`, 2026-09-05.** Fresh policy at a **2 MB**
threshold (deliberately different from v51's 1 MB, so the once-per-window key
could not collide with the old one and produce a false silence):

```
09:57:43 I/DataUsage:   data usage warning raised: device total_data monthly 2MB at 854.4 MB
09:57:43 I/SyncService: sync: state=5 applied=5 errors=0
09:59:43 I/SyncService: sync: state=5 applied=5 errors=0     ← still no repeat
```

The reading moved **552.5 MB → 854.4 MB** across the two runs, which is worth
noting on its own: the figures are live from the platform, not a cached or stubbed
number that happened to look plausible once.

⚠️ **The banner itself remains operator-confirmed only.** The log proves `warn()`
ran and posted to the new `IMPORTANCE_HIGH` channel; whether Android actually drew
a heads-up over the foreground app is a visual fact no log records. Do not mark
the heads-up "verified" on the strength of these lines alone — that conflation is
exactly what produced the false "no notification" diagnosis in the first place.

##### 🧹 Test policy archived

Profile `62609ee3-…` ("W44 data usage proof", 1 MB threshold) archived at the
operator's request now that it has served its purpose; `profile_assignment` is
back to **0 rows**, so nothing is assigned to `R5GL40MMHRN`. No data-usage policy
is live, and none should be until the operator writes one with a real threshold.

1. ✅ Contracts recorded in the Android reference (§W43, "How to actually call
   the stats API").
2. ✅ `DataUsagePlan` — windows, threshold crossing, once-per-window keys.
   **15 unit tests**, including the ones that catch the off-by-ones: a daily reset
   at 10:00 read *before* 10:00 belongs to yesterday's window; a monthly cycle
   pinned to the 31st lands on Feb 28 rather than skipping the month; consecutive
   windows are half-open so no byte is counted twice.
3. ✅ `DataUsageTracker` — per-transport device totals, per-UID app figures,
   `package → uid` via `PackageManager`.
4. ✅ Its own `IMPORTANCE_DEFAULT` notification channel (the sync channel is
   `LOW` and deliberately silent, so a warning on it would never be seen).
5. ✅ Wired into `Reconciler` after the other steps, unconditionally.
6. ✅ **95 agent tests** pass; **v51 (`0.15.0`)** built, signature re-verified,
   uploaded and published.

**The decisive test is set up and waiting.** Profile
`62609ee3-d351-4968-a284-6fbcd5a0bd6a` ("W44 data usage proof") is assigned to
`R5GL40MMHRN` with `track_usage` on and a **1 MB monthly total-data** threshold —
low enough that it must trip immediately on a tablet that has been downloading
20 MB APKs.

⚠️ **The compliance status *is* the experiment.** §W43 records the Device Owner
stats exemption as documented-but-unverified, and the tracker deliberately raises
an apply error rather than reading a null bucket as "0 bytes used". So:

* **COMPLIANT** → the exemption holds on One UI 8, and a usage warning should be
  on the tablet's screen.
* **DEGRADED**, detail *"querySummaryForDevice returned null — the Device Owner
  stats exemption does not apply on this firmware"* → it does not, and the
  fallback is the `PACKAGE_USAGE_STATS` grant now declared in the manifest.

At the time of writing the device is on **v50**, `COMPLIANT`, and was not parked
on the long-poll (`woken: false`), so it takes v51 on its next ordinary poll.
`PACKAGE_USAGE_STATS` was added to the manifest as that fallback — declared, not
required, and harmless if the exemption holds.

**Deferred to W45 on purpose:** reporting usage *back to the console*. It needs a
migration, a check-in field and a console view, and this chunk is already the
device half. Hardware proof here comes from the agent log via the existing
`collect_logs` command, which is already proven, so nothing is blocked by the
deferral. Until W45, the operator sees thresholds fire on the device, not in the
console.

---

##### Original W44 sketch

1. `NetworkStatsManager` read path (`querySummary` per transport, `queryDetails`
   per UID), proving the DO-gets-it-free claim on `SM-X520` first — §W43 records
   it as documented-but-unverified.
2. Accounting windows that survive reboot (daily at HH:MM, monthly on day N),
   stored the way `ScreenTimeoutPlan` stores displaced state.
3. Threshold evaluation as a pure `DataUsagePlan` + tests, per the `*Plan`
   convention.
4. Notification channel on the device for a crossed threshold.
5. Report usage back on check-in so the console can show it.
6. Hardware proof on `SM-X520`, then unblock the tracking fields' claim.

---

#### 🔻 W45 — A full-screen alert the operator's user cannot miss

**Ask:** the heads-up banner works (v52, confirmed on `SM-X520` — the operator saw
it pop) but is *"very small"*. Wanted: something aggressive and large.

##### The permission is already there, and already dishonest

`SYSTEM_ALERT_WINDOW` is declared, and `PermissionRequirement.DisplayOverOtherApps`
is in the setup wizard with the rationale *"Lets the agent show lockdown and
compliance messages over whatever is on screen."* **Nothing in the tree has ever
drawn an overlay** — `Settings.canDrawOverlays` is read only to tick the wizard's
box. So the agent asks every operator for a capability it never uses. This chunk
makes that ask honest.

✅ **Already granted on `SM-X520`.** `Reconciler` turns every ungranted
requirement into an apply error, and the device reports `errors=0`, so the
permission is live and no user action is needed to start using it.

##### Platform contract (`WindowManager.LayoutParams`, SDK source)

> Application overlay windows are displayed above all activity windows […] but
> below critical system windows like the status bar or IME.
> […]
> **The system may change the position, size, or visibility of these windows at
> anytime** to reduce visual clutter to the user and also manage resources.

⚠️ That last sentence is why the notification **stays**. An overlay is a
best-effort attention grab the platform may move or hide at will; the notification
is the durable record that survives in the shade. Replacing one with the other
would trade a small-but-reliable message for a large-but-revocable one.

##### Plan (5 steps)

1. `AlertOverlay` — a large centred card over a dimmed scrim via
   `TYPE_APPLICATION_OVERLAY`, shown on the main looper (the tracker runs on a
   worker thread).
2. **Dismissible, deliberately.** An un-clearable overlay on a device running ATAK
   in the field could obscure the map at the worst possible moment; the alert
   demands one tap rather than trapping the user. That is the aggression the
   operator asked for without the failure mode they did not.
3. Fall back to notification-only when `canDrawOverlays` is false, so the message
   is never simply lost on a device where the grant was skipped.
4. Keep posting the notification as well — see the contract note above.
5. Ship **v53**, verify on `SM-X520`, and only then call the delivery settled.

##### Status: ✅ **hardware-proven on `SM-X520`, 2026-09-05**

Operator confirmed at agent **v53 (`0.16.0`)**: *"large card over a dimmed
background with acknowledge button"*. The full chain — read → threshold → overlay
— now works end to end on real hardware, and the `SYSTEM_ALERT_WINDOW` grant the
wizard has always asked for is finally spent on something.

Test profile archived; `profile_assignment` is back to **0 rows**, so no
data-usage policy is live on the tablet.

`AlertOverlay` draws a centred card on a dimmed scrim with an **Acknowledge**
button; `DataUsageTracker.warn` posts the notification *and* the overlay, logging
`(overlay=true|false)` so the log says which delivery actually happened. Falls
back to notification-only when `canDrawOverlays` is false. v53 confirmed installed
on `SM-X520`; a fresh **4 MB** threshold is armed for the test.

##### 📓 What the banner episode actually taught

Two corrections were needed before this was understood, both from reading absence
as evidence:

1. **"COMPLIANT means the policy applied cleanly"** — false. Apply errors lag one
   check-in, so the first status after an assignment describes the *previous*
   state.
2. **"No banner appeared, so IMPORTANCE_HIGH failed"** — false. A heads-up shows
   for about five seconds; the operator looked minutes later and found it in the
   shade, which is what a *successful* banner also looks like after the fact. A
   controlled re-test (fresh threshold, operator watching, manual sync) showed the
   banner working. **v52 was never broken** — only unobserved.

The rule both point at: an on-device UI claim needs someone watching at the moment
it fires. A log line proves the code ran; it says nothing about what a person saw.

---

#### 🔻 W46 — Upload a wallpaper from inside the policy builder

**Ask:** upload the image in the wallpaper policy itself. Not via the Content
page first, and the picker should not be a list of Content files either.

##### The shape of the change

Today `WallpaperSpec.tablet_file_id` / `phone_file_id` use the `image_file`
control: a `<select>` over every `image/*` row in the Content library, with the
operator expected to have uploaded there first. Two clicks in the wrong place and
a mental model ("content" vs "policy asset") the operator does not share.

⚠️ **What must not change: the delivery path.** `resolve_wallpaper` turns a file
id into a sha the agent downloads, and that is hardware-proven. So an inline
upload still creates an ordinary `ManagedFile` + content-addressed `Artifact` —
the *only* new idea is that it does not belong to the browsable library.

##### Plan (6 steps)

1. **Migration + model:** `ManagedFile.in_library` (bool, NOT NULL,
   `server_default=true`). ⚠️ The server default is load-bearing — the operational
   notes record that autogenerate never infers one, so a NOT NULL column fails on
   Postgres against a table that already has rows. Existing content stays
   `in_library`.
2. `ingest_file(..., in_library=True)`, so the one ingest path serves both callers
   rather than growing a second.
3. `POST /policies/image` — ingest an `image/*` upload as `in_library=False` and
   return its id as JSON, for the form to hold until the policy is saved.
4. **Exclude non-library rows from every listing**, not just the Content page:
   the files API, the dashboard count, and the policy form's own file pickers.
   Missing one would leak wallpapers into the FILES picker as deployable content.
5. New `image_upload` control — hidden id input, file picker, live preview, no
   Content dropdown. `WallpaperSpec` switches to it and the dead `image_file`
   macro goes. An id already set still renders its preview, so **existing
   wallpaper policies keep working** whichever way their image arrived.
6. Tests, then deploy. No agent change: the device cannot tell the difference,
   which is the point.

##### Status: ✅ done and deployed, 2026-09-05

**675 server tests** (7 new). Migration `n4p6r8t0v2x4` applied on
`209.182.235.108`; `in_library boolean not null default true` confirmed on the
live column.

Verified end to end against a running console, not just in tests:

| Check | Result |
|---|---|
| `POST /policies/image` | `{"id": …, "name": "w_test"}` — named from the filename, not a uuid |
| Wallpaper form | the `<select>` over Content is **gone**; hidden id + file picker + Remove in its place |
| Saving a policy with the uploaded id | **200**, and the editor re-renders with the image |
| `GET /api/v1/files` (the library) | **absent** — 0 matches |
| `GET /content/{id}/raw` | **200** — still previewable by id, just not catalogued |
| `resolve_wallpaper` on the uploaded id | `available: true` with a sha — reaches a device exactly like Content did |

The last two rows are the pair that matters: **hidden from the library, identical
to the device.** Filtering the delivery path by mistake would have broken
wallpapers; filtering nothing would have leaked them into the FILES picker as
deployable content.

⚠️ **One listing was deliberately *not* filtered.** `_managed_file_names` maps id
→ name for policy summaries, and it is exactly where a policy-uploaded wallpaper
needs to be found; filtering it "for consistency" would put a raw uuid back on the
screen this feature exists to keep it off.

##### 🐛 The empty preview frames were a four-year-old CSS bug, not new

Operator asked for the preview panels to be hidden with nothing selected. They
already carried `hidden`, and the JS already set `preview.hidden = true` — but
`.wallpaper-preview { display: flex }` is a **class** selector, which outranks the
browser's own `[hidden] { display: none }`. The attribute had never worked there,
so two empty frames rendered whenever a slot was empty.

The stylesheet had already been patched for this **three times** —
`.tab-panel[hidden]`, `.modal-backdrop[hidden]`, `.tpc-table tbody tr[hidden]` —
each a local fix for the same root cause. Rather than add a fourth, a single
global `[hidden] { display: none !important; }` now sits at the top of
`atlas.css`. The three older patches are left in place: they are harmless and
subsumed, and ripping them out would be an untested change to modals and tabs for
no behavioural gain.

Also removed the "not added to the Content library" note under the picker, as
asked — the behaviour is right, the explanation was just noise on the form.

🐛 **Not a bug, but it cost a diagnosis:** the first live upload attempt returned
`000` with *no request in the API log at all*. Windows `curl` cannot resolve an
MSYS `/tmp/...` path, so the request was never made. When a call fails with no
server-side trace, suspect the client before the server.

---

#### 🔻 W47 — Category checkmarks that reflect what you have actually typed

**Ask:** a green check beside a category in the policy maker's rail when that
category has content.

##### The markers already existed — and could never appear where it mattered

W12 built them; `profile_editor.html` renders `row.has_data` on both category
heads and sub-pages. The reason the operator had never seen one:

* `/policies/new` — **the policy maker** — renders the rail with
  `_catalog_view()` and **no profile**, so every spec is `{}` and `has_data` is
  false for every category. While building a new policy the checks were
  structurally unreachable.
* In the editor they only ever refreshed on save-and-reload, so they were stale
  the moment anyone typed.

So the fix is not "add a checkmark" but "make it reflect the live form".

##### What was built

The server still decides the *initial* state; the marker is now always rendered
and toggled with `hidden` (which only works at all because W46 added the global
`[hidden]` rule — the previous element-by-element patches would not have covered
it). `atlas.js` then recomputes on every `input` / `change` / `click`.

"Has content" mirrors what `parse_form` keeps, so a check promises a field that
will really be saved:

* a control outside a repeatable row counts when non-empty — every "Not managed"
  option is the empty string, so untouched fields score zero;
* a row rendered by the server always counts (it came from saved data);
* a row the operator just added counts only when something in it is **non-empty
  and changed from its default**. Without that last clause the pre-selected
  "Monthly / Mobile data" on a blank threshold row would claim content that
  saving is about to discard.

##### ✅ Verified by running the real script against the real page

No JS test harness exists in this project, and the last few chunks have shown
what assuming-instead-of-checking costs — so `atlas.js` was loaded into `jsdom`
against the live `/policies/new` HTML (throwaway, in the session scratchpad, no
dependency added to the repo):

| Case | Check visible |
|---|---|
| At load, nothing typed | `false` |
| After typing a Password `min_length` | **`true`** |
| An untouched category, same moment | `false` |
| After clearing the field again | `false` |
| After "Add rule" — blank row, non-empty `period`/`metric` defaults | **`false`** — the false positive this was designed against |
| After typing `500` into that row's threshold | **`true`** |

**676 server tests.** Two existing tests were updated rather than deleted: the
contract changed shape (the span is now always present, `hidden` when empty) but
not meaning, so `_VISIBLE_CHECK` / `_HIDDEN_CHECK` assert the same intent
precisely. Added `test_the_policy_maker_starts_with_every_check_hidden` to pin the
case that made the feature look missing in the first place.

---

#### 🔻 W48 — Delete an archived policy permanently

**Ask:** archived policies should be deletable from the archive — a button in the
Archived list and one on the archived policy's own detail page, with warnings that
it is permanent.

**This is a deliberate carve-out from D20** ("archived policies are never
deleted"). D20's rationale — preserving the record of what a device once had —
still holds as the *default*, which is why archiving stays the one-click action
and deleting is gated behind it. What D20 did not anticipate is the operator's
real bin problem: policies created while learning the console, or by a
mis-clicked template clone, that never reached a device and whose history answers
nothing.

⚠️ **Two traps found by reading the schema before writing anything:**

1. `Assignment.pinned_version_id` → `policy_version` is **ON DELETE RESTRICT**,
   while `Assignment.policy_id` and `PolicyVersion.policy_id` are both ON DELETE
   CASCADE. Deleting a policy therefore cascades into two tables whose order the
   database does not promise; if `policy_version` goes first, the RESTRICT fires
   and the delete raises. The fix is to clear the assignment rows explicitly in
   the service, before the policy row goes.
2. A *profile section* is a `Policy` row too. It must not be deletable on its own
   — that would leave a profile with a hole in it — so the standalone delete
   refuses any row with a `profile_id`.

**The gate is also what makes the delete inert for the fleet.** An archived
policy is already skipped by the resolver, so no device's effective state can
change when it goes; there is nothing to invalidate and no reason to wake
anybody. Deleting a *live* policy would have needed all of that, which is a
second argument for the gate beyond "two deliberate acts".

##### Plan (7 steps)

1. `policy_admin.delete()` — refuse unless archived, refuse a profile section,
   clear assignments, then delete (versions go by ORM cascade).
2. `profiles.delete()` — refuse unless archived; clear every section's
   assignments, then delete the profile (sections and their versions go by
   cascade). Profile archiving already dropped the *profile* assignments.
3. Console routes `POST /policies/{id}/delete` and `POST /profiles/{id}/delete`,
   redirecting back to the Archived tab.
4. REST `DELETE /api/v1/policies/{id}` and `DELETE /api/v1/profiles/{id}`, 409 on
   a policy that is not archived — same shape and same wording as the existing
   retire-before-delete refusal on devices.
5. Archived-tab list view: a Delete column for both profile and standalone rows,
   `confirm()`-guarded and naming what is destroyed.
6. Detail pages: a delete action on `policy_detail.html` and `profile_editor.html`
   shown **only when archived**, next to Restore.
7. Tests, then update this file. No agent change and no migration — nothing about
   the device contract moves.

##### Status: ✅ done, 2026-09-05

**694 server tests** (18 new, in [tests/test_archive_delete.py](tests/test_archive_delete.py)).
No migration, no agent change.

| # | Decision | Rationale |
|---|---|---|
| D124 | **Deleting an archived policy is permitted — a scoped exception to D20** | D20's reason (what a device once had stays answerable) is real for a policy that ran, and worthless for one that never left the console. The dev instance had 13 archived test profiles and 6 `ZZ …` probe policies whose history answers nothing. Archiving stays the one-click default; deleting is reachable only from the archive. |
| D125 | **Delete is gated on `archived_at`, the same shape as retire-before-delete on a device** | Two jobs, not one. It makes deletion two deliberate acts, **and** it makes the delete inert for the fleet — the resolver already skips an archived policy, so no device's effective state can move and there is nothing to invalidate or wake. Deleting a live policy would have needed all of that. |
| D126 | **Assignments are deleted in the service, not left to the database cascade** | `Assignment.pinned_version_id` → `policy_version` is ON DELETE **RESTRICT** while `Assignment.policy_id` and `PolicyVersion.policy_id` are both CASCADE, so one `DELETE FROM policy` fans out into two tables in an order no database promises. |
| D127 | **A profile section refuses to be deleted on its own** | A section is a `Policy` row, so the endpoint would otherwise accept one and leave the profile with a hole its editor cannot render. Delete the profile instead. |

**The RESTRICT trap was found by reading the schema, not by a failing test.** The
test that covers it (`test_a_pinned_assignment_does_not_block_the_delete`) was
written to prove the reading was right, and it does: with the `drop_assignments`
call removed it fails with `sqlite3.IntegrityError: FOREIGN KEY constraint
failed` on `DELETE FROM policy_version`.

##### Verified against the running Docker stack, not just the suite

Real Postgres, because the cascade-ordering hazard is a live-database concern
SQLite can only approximate:

| Check | Result |
|---|---|
| `DELETE /api/v1/policies/{id}` on a **live** policy | **409**, policy still there |
| Same on an archived policy | **204**, then **404** on re-read |
| Archived policy with an assignment **pinned to v1** and a published v2 | **204** — the RESTRICT path, clean |
| Console `POST /policies/{id}/delete` (real CSRF double-submit) | **303 → `/policies#tab-archived`**, gone from the page |
| Console `POST /profiles/{id}/delete` | **303**, gone from the page |
| Archived tab markup | Delete column present for both profile and standalone rows, each with its own `data-confirm` naming the policy |
| A live policy's detail page | offers Archive, and contains no `/delete` at all |

⚠️ **Deleting a device group is still not possible** — there is no
`DELETE /api/v1/groups/{id}` endpoint at all. Noticed while clearing test data
(the group had to go out of `psql` by hand). Out of scope here, but it is the
same gap this work just closed for policies.

---

#### 🔻 W48 — The DPC's Apps section, split into Available / Installed / Updates

**Ask:** three tabs on the device app's Apps section. *Available* = offered by
policy but not installed; *Installed* = installed by policy; *Updates* = installed
with a newer build waiting.

##### The data is already there — this is a sorting problem, not a plumbing one

`renderApps` already computes exactly these states for its status pill, from the
desired state's `apps` array and `installer.installedVersionCode(pkg)`:

| Condition | Tab |
|---|---|
| `available` and not installed | **Available** |
| installed `>=` wanted | **Installed** |
| installed `<` wanted | **Updates** |
| `available == false` | **Available**, keeping its loud error pill |

That last row is a judgement call worth stating: an app whose policy resolves to
**no published build** ("nothing uploaded for it") is not installable at all. It
belongs in Available rather than being hidden, because the current UI shouts about
it and dropping it would quietly lose the only signal the device gives that a
policy is broken.

⚠️ Every entry is a **required** app (`APP_CATALOG.required_apps` — the marketplace
tier is files, not apps), so "Available" means *"policy wants this here and it is
not here yet"*, i.e. pending install rather than an opt-in catalogue. Worth being
precise about in the empty-state wording so it does not read as a shop.

##### Plan (5 steps)

1. An `AppsTab` enum plus a selected-tab field, following the section pattern
   already in `MainActivity` (`currentNav` + `render()`), rather than introducing
   a `TabLayout` and a second navigation idiom.
2. A segmented control of three buttons carrying **live counts** — the count is
   the part that is useful at a glance, and it is what makes "Updates" worth
   looking at before tapping it.
3. Bucket the existing per-app card rendering behind the filter; keep the card
   itself unchanged so the status pill, version and size still read the same.
4. A per-tab empty state, each saying something true about *that* tab rather than
   one generic "no apps".
5. Build, ship **v54**, and confirm on `SM-X520`.

##### Status: ✅ shipped as v54 (`0.17.0`), ⏳ awaiting the operator's eyes

**102 agent tests** (7 new). Uploaded and published; the tablet takes it on its
next poll.

The bucketing lives in **`AppsTabPlan`**, not in `MainActivity`, for the reason
the `*Plan` convention exists: misfiling an app is a *silent* failure — it simply
is not where someone looked — and an Activity cannot be unit-tested. The rendering
stayed in the Activity; only the decision moved.

Two decisions the tests pin down, both of which could reasonably have gone the
other way:

* **An app installed at a *newer* build than the policy wants counts as
  Installed, not an Update.** There is nothing to fetch, and Android refuses a
  downgrade regardless — filing it under Updates would advertise an action that
  cannot be taken.
* **An app with no publishable build stays in Available**, carrying its existing
  "nothing uploaded for this app" error pill, rather than being filtered out for
  tidiness. It is the only place the device admits a policy is broken, and the
  three tabs are now the whole surface: anything filed nowhere is invisible, and
  invisible is indistinguishable from not deployed.

⚠️ Wording matters here and is easy to get wrong: every managed app is
**required** by policy (the marketplace tier is files, not apps), so *Available*
is a **queue, not a shop** — "nothing waiting to install", not "browse apps". The
empty states say so.

---

#### 🔻 W49 — App configurations (Android managed configurations)

**Ask:** a new sub-section under App Management. Scan uploaded APKs for the
managed-configuration profiles they declare, let the operator pick an app, open a
frame to fill in its keys, and save it into a list — several per policy.

##### ✅ Feasibility settled first, because the obvious route is closed

An app declares its config schema with
`<meta-data android:name="android.content.APP_RESTRICTIONS"
android:resource="@xml/app_restrictions"/>`. That is a **resource reference**, and
`app/artifacts/axml.py` says in its own comment that it does not parse
`resources.arsc` — it returns references symbolically (`@0x7f120001`). Resolving
the id would mean writing an `.arsc` parser robust enough for every APK an
operator uploads.

**So discovery is by content, not by id:** scan `res/**/*.xml`, parse each with the
AXML reader already in the tree, and keep the ones whose **root element is
`<restrictions>`**.

Proven against the real thing before planning anything further — ATAK 5.8.0.4
declares six keys:

```
res/Kt.xml   ← obfuscated by resource shrinking
  enterpriseConfigurationDataPackage    (restrictionType 6 = TYPE_STRING)
  enterpriseConfigurationDataPackage2..5
  enterpriseConfigurationPreferences
```

That filename is the argument for this approach: **`res/Kt.xml` is unguessable**,
so a name-based lookup would have found nothing, and an id-based one needs the
parser we do not have. Content-based discovery found it in one pass.

⚠️ **The titles come back unresolved** — `@0x7f0f1488` — for exactly the same
reason. So the operator sees the **key** as the field label, which for these six
is the more useful string anyway. Where a `TYPE_CHOICE` app's `entries` /
`entryValues` are likewise unresolvable, the field degrades to free text rather
than showing an empty dropdown.

##### Platform contract (SDK source, verified not recalled)

`RestrictionEntry`: `TYPE_NULL 0, TYPE_BOOLEAN 1, TYPE_CHOICE 2,
TYPE_CHOICE_LEVEL 3, TYPE_MULTI_SELECT 4, TYPE_INTEGER 5, TYPE_STRING 6,
TYPE_BUNDLE 7, TYPE_BUNDLE_ARRAY 8`. `setApplicationRestrictions(admin, package,
Bundle)` is DO/PO only, `@WorkerThread`, and *"performs disk I/O and shouldn't be
called on the main thread"* — the agent applies from the sync worker, so that is
already satisfied. D11 already established this works without managed Google Play.

##### Plan — chunk 1 of 2 (server + console)

1. Record the contracts and the arsc limitation in the Android reference.
2. `app/artifacts/app_restrictions.py` — discover a package's declared keys from
   its stored artifact, cached by artifact sha (content-addressed, so a cache can
   never go stale).
3. Spec: `APP_CATALOG.app_configs`, a list of `{package_name, values{}}`, merged
   by package so two policies cannot half-configure the same app.
4. Console: the **App configurations** sub-page — saved configs listed, "Add"
   opens a frame offering only apps that actually declare restrictions, fields
   rendered by type, saving appends to the list.
5. Tests, including one built from the real ATAK APK so the parser is pinned
   against a shipping app rather than a fixture I wrote to pass.
6. Deploy.

##### Status: ✅ chunk 1 done and deployed, 2026-09-05

**706 server tests** (12 new). Verified through the running console against the
**real ATAK build**, not a fixture:

```
GET /policies/app-config-schema?package=com.atakmap.app.civ  → 200
  enterpriseConfigurationDataPackage    control=str
  enterpriseConfigurationDataPackage2..5
  enterpriseConfigurationPreferences
```

An app that declares nothing answers `200` with an explicit note rather than an
error — most apps declare nothing, and that is not a fault to go hunting for.

🐛 **Caught only by calling it: `/policies/{policy_id}` was swallowing the new
route.** FastAPI matches in declaration order, so `app-config-schema` was parsed
as a UUID and 422'd. The static route now sits ahead of the parameterised one.
Tests would never have found this — they call functions, not URLs.

⚠️ **A saved configuration still reaches no device.** The agent has no
`setApplicationRestrictions` applier yet, so `APP_CATALOG.app_configs` travels in
the desired state and nothing reads it. That is chunk 2, below.

##### ✅ Butterfly IQ is the reference case, and it found a design gap

The operator's actual target is third-party installs, not ATAK. **Butterfly IQ
2.49.0** — a real enterprise app, already uploaded as `com.butterflynetinc.helios`
— declares three keys, confirmed through the live endpoint:

| Key | Type | Control |
|---|---|---|
| `ApprovedEnterpriseDeviceSecret` | `TYPE_STRING` | text |
| `ButterflyDomain` | `TYPE_STRING` | text |
| **`InactivityTimeoutSeconds`** | **`TYPE_INTEGER`** | **number** |

It exercises two things ATAK cannot: an **integer** key, and titles the app
**inlined as literal strings** ("Butterfly Enterprise Subdomain") rather than
`@string` references — which proves the key-fallback is a fallback and not
masking titles that were there all along.

✅ **XAPK handling confirmed by measurement:** the schema is in `base.apk` and in
**none** of the six splits, which is what makes scanning `PartRole.BASE` correct
rather than merely convenient. Now asserted in a test, because if a split could
carry one, every multi-part app would silently appear to declare nothing.

##### ✅ Chrome 152 is the scale case, and changed two decisions

`Google+Chrome_152.0.7977.82_APKPure.xapk` declares **231 keys** in 0.08 s:

| Type | Count |
|---|---|
| `TYPE_BOOLEAN` | 93 |
| `TYPE_STRING` | 93 |
| `TYPE_CHOICE` | 39 |
| `TYPE_INTEGER` | 3 |
| `TYPE_MULTI_SELECT` | 3 |

Three things it proved that the smaller apps could not:

* **The base part is not always called `base.apk`** — Chrome's is
  `com.android.chrome.apk`. Discovery runs on whichever part the server recorded
  as `BASE`, so this works; a filename convention would have failed.
* **All 231 titles are unresolved references**, so the key-fallback is carrying
  the entire UI here. Chrome's keys are self-describing
  (`AdditionalDnsQueryTypesEnabled`), so it reads well — but it confirms the
  fallback is the normal case, not the exception.
* **No bundles at all**, so the unsupported-type path stays untested by a real
  app. Kept, but it has still never fired outside a unit test.

**Two changes it forced:**

1. **`choice` and `multi_select` are now their own controls**, not `str`. Their
   options live in `android:entries` / `entryValues` resource arrays —
   `AdsSettingForIntrusiveAdsSites` carries `entries=@0x7f040008` — which are
   references we cannot resolve. A plain text box would imply any value is
   acceptable; the editor now says the app defines the valid values, and shows
   the **literal `defaultValue`** (Chrome ships those uncompiled: `1`) as the one
   real clue available.
2. **The frame filters its keys** once there are more than a screenful. 231
   fields in a modal is not a form, it is a wall.

##### 🐛 Gboard found a **real bug**: nesting was being read flat

Gboard declares a `preferences` key of `TYPE_BUNDLE` with **43 keys nested inside
it**, alongside 82 genuine top-level keys. `axml.parse_elements` decoded only
start elements and threw the end elements away, so the document came back as a
flat list and **all 125 read as top-level**.

The consequence was the worst kind: setting `config_theme` would have written it
to the top of the Bundle, where Gboard never looks. **No error, no effect,
nothing to see in the console** — and the operator would have had no way to tell
a nested key from a real one, because the editor offered them identically.

**Fix:** `AxmlElement` now carries `depth`, tracked from the `END_ELEMENT` chunks
the reader had been ignoring, and discovery takes only `depth == 1`. Gboard now
reports **82 keys, not 125**, with `preferences` flagged as a bundle this flat
editor cannot express.

⚠️ **This also means Gboard is barely configurable through ATLAS** — its
interesting settings are the nested ones. That is a real limitation, and it is now
visible rather than fictional. Supporting bundles properly is a future decision,
not a bug to fix quietly.

✅ Gboard is also the **first real app to exercise the unsupported-type path** —
after Chrome, that branch had still never fired outside a unit test.

##### ✅ Outlook — the well-behaved case, and one last detail

`Microsoft+Outlook_5.2606.0` declares **44 flat keys** (33 boolean, 11 string) in
0.13 s: no nesting, no bundles, and 43 of 44 titles inlined as real strings. The
closest thing to a normal enterprise rollout, and the first fixture that found
nothing wrong.

One detail it did surface: **binary XML stores a boolean as `0`/`1`**, so
`BlockExternalImagesEnabled` arrives with `default="0"`. Beside a True/False
control that reads as a different setting entirely, so a boolean default is now
reported in the control's own language. The one unresolved title,
`com.microsoft.intune.mam.AllowedAccountUPNs`, falls back to its key — which is
perfectly descriptive, and exactly what the fallback is for.

##### ✅ Messages — the many-splits case, no bugs

Google Messages ships **22 parts: one base and 19 config splits** (languages,
density, ABI). The schema is in the base and in none of the splits, which is the
strongest confirmation yet that scanning the recorded `BASE` part is right rather
than lucky.

Only two keys — `disable_rcs` (boolean) and `messages_archival` (string) — but
both defaults are the awkward shapes: `defaultValue=0` as a **bare integer**
(read as `false`, via the normalisation Outlook prompted) and `defaultValue=""`
as an **empty string** (read as *no default*, not as an empty value an operator
might mistake for one). Same obfuscated filename as Gboard, `res/Ktm.xml` — the
two Google apps share a build toolchain.

##### ✅ ArcGIS Survey123 and Field Maps — same vendor, opposite builds

The most instructive pair, and directly relevant to field operations
(`portalURL`, `locationSharingMode`, `requireSignIn` are exactly the settings a
fleet would be issued).

* **Survey123** (10 keys) is the **textbook case**: schema at the canonical
  **`res/xml/restrictions.xml`**, every title and default inlined
  (`portalURL` → *"Portal URL"*, default `https://www.arcgis.com`). It is the
  **only fixture where a name-based lookup would have worked** — which is exactly
  why it earns a place: content-based discovery has to handle the tidy layout as
  well as the obfuscated ones it was built for.
* **Field Maps** (11 keys) is its opposite twin from the same vendor: schema at
  the obfuscated `res/Kt.xml`, **not one title resolved**, yet integer defaults
  still literal (`locationSharingUploadLKLFrequency` → `60`).

Two apps from one publisher landing on opposite sides of the design's central
assumption is the strongest evidence yet that neither path could have been
assumed.

##### Eight fixtures, eight different failure modes

| App | Keys | What it proves |
|---|---|---|
| **Butterfly IQ** | 3 | The reference case: XAPK, an integer key, titles inlined as real strings |
| **ATAK** | 6 | Obfuscated schema path (`res/Kt.xml`), every title an unresolvable reference |
| **Chrome** | 231 | Scale, base part not named `base.apk`, unreadable choice options |
| **Gboard** | 82 | Nesting — the one that broke the parser |
| **Outlook** | 44 | Flat Intune-style schema; booleans default as `0`/`1` |
| **Messages** | 2 | 19 splits carrying nothing; integer and empty-string defaults |
| **Survey123** | 10 | The canonical `res/xml/restrictions.xml` path, everything inlined |
| **Field Maps** | 11 | Same vendor, obfuscated path, no titles, literal int defaults |

Between them: three XAPKs and five APKs; 2 to 231 keys; canonical and obfuscated
schema paths; resolved and unresolved titles; nested and flat; five of the nine
restriction types. Every one a real shipping build — which is how the nesting bug
surfaced at all, and why the discovery half can now be called done.

**The last three apps found nothing new.** The risk has moved entirely to the
agent, where the type coercion below is still unbuilt.

##### 🐛 Design gap Butterfly exposed: a string value cannot satisfy an int key

`AppConfig.values` is `dict[str, str]`, which is right for editing. But
`InactivityTimeoutSeconds` is `TYPE_INTEGER`, and an app reading it calls
`getApplicationRestrictions().getInt(...)`. **A Bundle holding the String "300"
returns 0 from `getInt`** — the app silently falls back to its default and nothing
anywhere reports a failure. This is the exact shape of bug this project keeps
finding: correct-looking config, no error, no effect.

⚠️ **The agent cannot fix this alone** — the desired state carries values but not
types, and inferring "looks numeric → send an int" would corrupt a *string* key
whose value happens to be digits. `ApprovedEnterpriseDeviceSecret` is precisely
the kind of key that could be all digits.

**So the type has to travel.** The server already holds the APK it is about to
deploy, so the cleanest answer is to resolve each key's declared type when
building the desired state, from that exact build — no stored copy that can drift
from the app it claims to describe.

##### ✅ Chunk 2 — the agent applier. Shipped as v56 (`0.19.0`), 2026-09-05

**726 server tests, 109 agent tests** (7 new). Migration `r8t0v2x4z6b8` applied on
`209.182.235.108`.

**1. The declared type now travels.** Scanned once at upload into
`app_package_version.declared_config`, and attached to each configured key when
the desired state is built. Stored rather than re-read because the desired state
is rebuilt on every check-in for every device, and rescanning a 130 MB Chrome APK
each time to recover three integers is not a trade worth making. Safe to store
because **a version row is immutable** — its bytes never change, so the copy
cannot drift from the build it describes. `NULL` means *not scanned* and is
backfilled lazily; an empty object means *scanned, declares nothing*, and the code
depends on the difference.

✅ **Proven end to end against the real Butterfly XAPK**, through the actual
device payload:

```json
"app_configs": [{
  "package_name": "com.butterflynetinc.helios",
  "values": {"InactivityTimeoutSeconds": "300", "ButterflyDomain": "ops.example.org"},
  "types":  {"InactivityTimeoutSeconds": 5,     "ButterflyDomain": 6}
}]
```

Type 5 is `TYPE_INTEGER`, 6 is `TYPE_STRING` — so the agent builds
`putInt(…, 300)` and `putString(…)`. Butterfly predates the column, so this also
exercised the lazy backfill.

**2–3. `AppConfigPlan` coerces, and refuses rather than guessing.** A value that
cannot be its declared type is reported as an apply error naming the key; it is
never sent as a best guess, because a wrong type reads as the app's own default
and is indistinguishable from never having tried. An **unknown** type is refused
for the same reason — sending a string would be right for a string key and
silently wrong for every other.

**4. Configurations are cleared when a policy stops naming an app.**
`setApplicationRestrictions` latches like every other DPM setter, so the agent
remembers which packages it configured.

**5. Presence, not provenance (the W50 requirement).** The applier checks the
package is *installed*, not that the DPC installed it — so an app left alone
because the device already had a newer build still gets its configuration. Tying
config to "we installed this" would have skipped exactly the devices an operator
is most likely to be looking at.

##### 🐛 A 500 reached the operator: `entry.values` in Jinja is a **method**

Saving a policy with a Chrome downgrade and a managed configuration returned an
internal server error. The save itself was fine — re-rendering the editor blew up:

```
_policy_form.html, line 307:  value="{{ entry.values | tojson }}"
TypeError: Object of type builtin_function_or_method is not JSON serializable
```

**Jinja resolves attributes before items.** `entry` is a plain dict, so
`entry.values` finds `dict.values` — the built-in **method** — rather than the
`"values"` key, and `tojson` tried to serialise it. `entry.package_name` works
only because dicts have no attribute by that name. **Naming the key `values` is
the entire trap**, and it was invisible until a saved row was rendered.

Fixed with explicit item access (`entry['values']`), bound once at the top of the
row so the three uses cannot drift apart.

⚠️ **Why the tests missed it:** every existing test exercised *parsing* and
*validation* — `parse_form`, `registry.validate_spec`, the discovery fixtures.
**Nothing rendered a saved `app_configs` row.** The regression test now creates a
policy through the API and fetches the editor page, which is the only shape that
would have caught this. Same lesson as the `/policies/{policy_id}` route collision
earlier in W49: tests that call functions do not exercise what a browser does.

##### ⏳ Not yet proven on hardware

`SM-X520` has none of these apps installed, and the server has only the agent
uploaded. A full proof needs Butterfly (or Chrome) uploaded to
`209.182.235.108`, assigned with a configuration, and the app present on the
tablet — at which point `getInt` returning 300 rather than 0 is the whole test.

---

#### 🔻 W50 — A newer app on the device is a warning, not a failure

**Ask:** when a policy names an app at a lower versionCode than the device already
has, don't attempt the install and don't fail — treat the newer build as
satisfying the requirement, raise a **compliance warning** about the mismatch, and
**still apply that app's managed configuration**, because the package is present
even though the DPC did not put it there.

##### What already works, and the one thing that does not

`AppUpdatePlan.decide` already returns `REFUSED_DOWNGRADE` for exactly this case
and the reconciler skips the install — Android refuses a downgrade anyway, and the
only route down destroys the app's data. That half is done.

⚠️ **The reporting is the problem.** The reconciler files it in `apply_errors`,
which sets `compliance_status = DEGRADED`. Two consequences the operator did not
ask for:

1. A device is marked broken for a condition this project has just decided is
   **acceptable** — the newer build satisfies the requirement.
2. **DEGRADED blocks the agent self-update.** `agent_update.decide()` refuses to
   offer a build to a device that "is not applying its policy cleanly". So a
   device carrying a newer Chrome than its policy names would be permanently
   unable to receive agent updates — the same deadlock W41 hit, arrived at from a
   different direction.

So the model needs a tier it does not have: **converged, with something worth
saying**. Errors and warnings are different facts and cannot share a field.

##### Why not a `WARNING` compliance status

Considered and rejected. `compliance_status` answers *"has this device
converged?"*, and the answer here is genuinely **yes** — the operator has decided
v12 satisfies a request for v10. A third status would blur that question and force
every consumer (the update gate, the fleet table, reports) to re-decide what
"converged" means. The warning is a separate fact **about** a compliant device, so
it gets its own field.

##### Plan (6 steps)

1. **Agent:** `Reconciler` collects warnings separately from errors;
   `REFUSED_DOWNGRADE` becomes a warning naming both versions.
2. **Agent:** report them as `apply_warnings` on check-in, alongside
   `apply_errors`.
3. **Server:** `apply_warnings` on `CheckinRequest`, a `compliance_warnings`
   column, and — critically — **warnings alone never move `compliance_status`**.
4. **Console:** surface them on the device page and the fleet table as a warn
   pill, so "compliant, but read this" is visible without hunting.
5. **Managed configuration must key off presence, not provenance** — an app the
   DPC declined to install still gets its config, because it is installed. This
   lands with W49 chunk 2, whose applier does not exist yet; recorded here so it
   is built that way rather than retrofitted.
6. Build, ship, and prove on `SM-X520` with a real downgrade case.

⚠️ **Step 5 cannot be demonstrated until W49 chunk 2 exists** — no managed
configuration reaches any device today. Steps 1–4 stand on their own and are worth
having regardless.

##### Status: ✅ steps 1–4 shipped, 2026-09-05 (agent **v55**, `0.18.0`)

**726 server tests** (6 new) and the agent suite pass. Migration `p6r8t0v2x4z6`
applied; `compliance_warnings` confirmed on the live column.

* `ApplyReport(errors, warnings)` carries the two facts separately through the
  reconciler; `REFUSED_DOWNGRADE` now produces a **warning** naming both
  versions.
* Check-in gained `apply_warnings`, and warnings are rewritten on every report —
  so raising the policy to match the device clears the notice rather than leaving
  it to haunt the console.
* **Warnings never move `compliance_status`.** The device page shows them as
  "Worth knowing", distinct from "Last reported problem".

The test worth keeping is `test_a_warned_device_is_still_offered_agent_updates`.
It asserts the update gate directly rather than trusting the reasoning: a
DEGRADED device is refused new builds, so had this stayed an error, **every
device carrying a newer app than its policy names would have quietly stopped
receiving agent updates** — W41's deadlock reached from another direction, and
the whole reason warnings needed their own tier rather than a friendlier message.

##### Not yet proven on hardware

The downgrade path has never run on `SM-X520`. Proving it needs a policy naming a
**lower** versionCode than an app the device already carries — Chrome would do it,
but no Chrome build is uploaded to `209.182.235.108` yet. Worth doing before this
is called done, since the whole change is about what the device reports.

---

#### 🔻 W51 — App display names, an upload modal, and the DPC's icon

Three operator-reported items from uploading Chrome.

##### 1. An unlabelled upload should be named what the device would call it

Uploading the Chrome XAPK with no label recorded it as `com.android.chrome`.

⚠️ **`android:label` is usually a resource reference**, so this runs straight
into the same `.arsc` wall as W49's schema discovery. Measured across the
fixtures rather than assumed:

| Source | What is available |
|---|---|
| **XAPK `manifest.json`** | ✅ The display name outright — Chrome → `"Chrome"`, Butterfly → `"Butterfly iQ"` |
| **APK with a literal label** | ✅ Survey123 → `"Survey123"` |
| **APK with a reference** | ❌ Outlook and ATAK give `@0x7f15038b` |

So: read the XAPK manifest first, fall back to a literal `android:label`, and
**fall back to the package name only when neither is readable**. That fixes the
reported case and several others honestly. Inventing a name from the package
(`com.microsoft.office.outlook` → "Outlook") is deliberately not done — a guess
that is usually right is worse than a package name that is always true.

##### 2. An upload of any size needs to say what it is doing

A 100 MB+ upload gave no feedback at all. Wanted: a modal that blocks other
actions, and can cancel.

`XMLHttpRequest` rather than `fetch` — it reports **upload** progress, which
`fetch` still cannot, and `abort()` gives the cancel button something real to do
rather than merely hiding the dialog while the transfer continues.

##### 3. The DPC's launcher icon

A complete adaptive set is supplied: `mipmap-{m,h,x,xx,xxx}dpi` with launcher,
round, foreground, background and monochrome layers, plus the `anydpi-v26`
adaptive XML. The manifest already points at `@mipmap/ic_launcher` /
`ic_launcher_round`, so this is a file merge and a version bump, not a code
change.

##### Plan (6 steps)

1. Read the display name at ingest: XAPK manifest, then a literal label, then the
   package name.
2. Backfill the label for builds already uploaded, so Chrome stops showing as its
   package name without a re-upload.
3. Upload modal on the Apps page: blocking, real progress, working cancel.
4. Merge the icon set into the agent and bump the version.
5. Tests — the name resolution across all three shapes, using the real fixtures.
6. Ship and deploy.

##### Status: ✅ done, 2026-09-05 — agent **v57** (`0.20.0`), 733 server tests

**1. Display names.** Resolved across the fixtures: Chrome → **"Chrome"**,
Butterfly → **"Butterfly iQ"**, Messages → **"Messages"**, Survey123 →
**"Survey123"**. Outlook and Gboard keep their package names, because their
labels are resource references and inventing a name would be a fabrication that
happens to be right.

🐛 **`_container_label` already existed and had never been called.** Someone wrote
the XAPK-manifest reader and never wired it up, which is the entire reason Chrome
was filed under its package id.

🐛 **And wiring it up exposed a second bug in the same breath.** The obvious call
site is the `return`, which sits *after* `with archive:` has closed the zip —
reading a closed `ZipFile` raises `ValueError`, which `_container_label` catches
and turns into a silent `None`. It looked exactly like "this XAPK has no name".
The label is now read inside the block.

`backfill_labels` fixes packages already uploaded, and only where the label is
missing or equals the package name — an operator who typed a name meant it.
⚠️ It re-reads the **base APK only**, so an XAPK whose name lived solely in
`manifest.json` cannot be recovered without a re-upload; that limitation is
stated where the function is.

**2. Upload modal.** Blocking, with real progress and a cancel that genuinely
aborts. **`XMLHttpRequest`, not `fetch`** — `fetch` still cannot report *upload*
progress, and cannot be aborted in a way that stops the bytes, so a cancel button
built on it would hide the dialog while the transfer carried on. It also says
"the server is unpacking and verifying it" once the last byte lands, because a
large XAPK spends real time being split and hashed after the bar hits 100%.

**3. Icon.** 27 files merged into the agent's `res/`; the manifest already pointed
at `@mipmap/ic_launcher`. Verified in the built APK's **resource table** rather
than by filename — resource shrinking renames these, exactly as it did to ATAK's
`res/Kt.xml`:

```
mipmap/ic_launcher   ic_launcher_background   ic_launcher_foreground
mipmap/ic_launcher_monochrome                 ic_launcher_round
```

⚠️ **The icon is not visually confirmed.** The resource table proves all five
layers ship, including the monochrome layer themed icons need; how it looks under
a launcher's mask is something only the tablet can show.

---

#### 🔻 W52 — Version choices scoped to their app; app icons investigated

##### ✅ The version selector now belongs to the app that was picked

Every `<option>` already carried `data-package` and **nothing ever read it**, so
the dropdown listed every version of every app at once — 53 entries, 50 of them
builds of apps that row had nothing to do with, each one a way to pin the wrong
thing.

Verified in a real DOM (`jsdom` against the live `/policies/new`, throwaway, no
dependency added):

| | Before | After |
|---|---|---|
| Options before an app is chosen | all 53 | **"— pick an app first —"**, disabled |
| Options after choosing ADSB Direct | 53 | **3** |
| …belonging to other apps | 50 | **0** |

Options are removed and re-added rather than hidden: browsers honour `hidden` on
an `<option>` inconsistently, and one that is invisible but still keyboard-
selectable would be worse than the bug. Wiring is **lazy and per row**, because
"Add app" clones from a `<template>` long after load — a startup-only pass would
leave every new row unfiltered, which is the state that shipped.

🐛 **The first jsdom run reported the fix not working.** It asserted synchronously,
before the `setTimeout(…, 0)` that wires a newly cloned row had run — a browser
turns that tick long before a human clicks anything. The test was wrong, not the
code. Worth remembering: a DOM test that does not let timers run measures a state
no user ever sees.

##### ❌ App icons: measured, and not worth building — ⛔ **RETRACTED, see W53**

> **This section is wrong.** It is kept because the *way* it was wrong is the
> lesson. The crawler that produced the table below filtered candidate files on
> `.png`/`.webp`/`.jpg` **extensions**, and resource shrinking strips extensions —
> Chrome's icon layers are `res/ima`, `res/EFE`, `res/QtC`, all real WEBP files
> with no extension at all. "Vector drawables all the way down" was an artefact of
> the filter, not a fact about the APKs. The operator pushed back — *"we should be
> able to extract the icon that would be installed for each app on the eud"* — and
> was right. Never conclude "the data isn't there" from a search that filters on a
> naming convention the toolchain is free to destroy; check magic bytes.

An icon column needs the app's launcher icon, and `android:icon` is a **resource
reference** in all five fixtures — the `resources.arsc` wall again.

A minimal `.arsc` resolver was prototyped and **works**: Chrome's icon id
resolved to `res/r2e.xml`, Outlook's to `res/E42.xml`. But those are
**adaptive-icon XML**, not images, and following the chain down finds:

| App | Icon chain ends at |
|---|---|
| Survey123 | ✅ `res/drawable-hdpi-v4/icon.png` |
| ATAK | ✅ `res/3k.png` |
| **Chrome, Butterfly, Outlook** | ❌ **vector drawables all the way down** |

Rasterising a `VectorDrawable` server-side means implementing Android's drawable
pipeline — path data, gradients, clip paths, layer-lists, insets. Outlook's
foreground is already `inset → layer-list → two items` deep. That is a project,
not a column, and it would still only reach ~40% of apps.

**Not built. Options, for the operator to choose:** a monogram from the app's
name (consistent, no parsing, works for every app), an operator-uploaded icon per
app (reliable but manual), or real icons only where extractable (inconsistent —
two apps with pictures and three without looks broken).

⚠️ **The prototype is worth keeping in mind for something else.** A working
`.arsc` resolver would also unlock the *labels* Outlook and Gboard cannot supply
(W51), managed-configuration **titles** (W49 shows keys instead), and **choice
option lists** (currently free text). Those are all string lookups — no rendering
— so they are genuinely reachable. Icons are the one thing on the far side of a
renderer.

#### 🔻 W53 — Real app icons, extracted from the APK

**Measured first, planned second.** A `resources.arsc` reader plus magic-byte
detection resolves `application:icon` to the actual image the launcher would draw,
for four of the six pinned fixtures:

| App | Icon resource | Ends at | Shape |
|---|---|---|---|
| Chrome | `res/r2e.xml` | `res/ima` — **WEBP**, 432² | adaptive foreground |
| Messages | `res/BWP.xml` | `res/vVu.png` — PNG, 432² | adaptive foreground |
| Survey123 | — | `res/…/icon.png` — PNG, 192² | **legacy raster** |
| ATAK | — | `res/3k.png` — PNG, 96² | **legacy raster** |
| Butterfly | `…/ic_launcher.xml` | ❌ `<vector>` foreground | vector only |
| Outlook | `res/E42.xml` | ❌ `inset → layer-list → <vector>` | vector only |

All four extracted icons were **rendered and looked at**, not merely produced: the
Chrome disc, the Messages bubble, the Survey123 notebook, the ATAK crest.

Two rules the measurement settled, both easy to get wrong:

* **Provenance decides the crop.** An adaptive foreground is drawn on a 108dp
  canvas of which only the centre 72dp is guaranteed visible, so it needs a
  ×1.5 crop; a legacy raster is already the finished icon and cropping it eats the
  artwork. Survey123 and ATAK came out visibly clipped until this was separated.
* **Vector-only icons stay unresolved.** Rasterising a `VectorDrawable` is
  Android's drawable pipeline — path data, gradients, clip paths, insets — and
  that part of W52 stands. Those apps fall back to the existing placeholder rather
  than to a fabricated image.

No new Python dependency: the raster is stored **as-is** and the ×1.5 adaptive
crop is done in CSS, so Pillow stays out of `requirements.txt` (it is present only
transitively, and the file says so deliberately).

##### ✅ Chunk 1 — extraction (offline, no schema change) — **done, 744 tests**

Built as planned. All four extractable icons were **rendered through the
production path and looked at**, not just asserted on: Chrome disc, Messages
bubble, Survey123 notebook, ATAK crest, each correctly cropped for its shape.

Two things worth keeping:

* **Splits are skipped.** `inspect_apk` runs on every part of a container, and a
  `config.*` split has no launcher entry — parsing its resource table is real work
  for a guaranteed `None`.
* **Cost is the table parse, not the search.** Outlook ships a **39.6 MB**
  `resources.arsc` (22,886 ids) and costs 1.03 s to read; the icon walk is 0.17 s.
  Chrome's whole extraction is 0.03 s. Acceptable against hashing a 172 MB upload,
  but it is the reason to resolve labels from the *same* parsed table later rather
  than re-reading it per question.

1. `app/artifacts/arsc.py` — minimal resource-table reader: resource id → values
   per configuration, handling the sparse and offset-16 entry encodings. Promote
   `_StringPool` to public in `axml.py` rather than copying it.
2. `app/artifacts/app_icon.py` — resolve `application:icon` through adaptive-icon
   XML to a raster; return bytes + media type + whether the crop applies.
3. Wire `icon` onto `ApkInfo` and `InspectedBundle`.
4. Tests pinned to all six fixtures — including the two **refusals**, so a future
   change that starts inventing icons for vector-only apps fails loudly.

##### ✅ Chunk 2 — labels, persistence, and the column — **done, 751 tests**

Operator asked for *"whichever method will be most reliable"* on whether to fold
label resolution into the same parse. **Folded in**: one parse answers both
questions, so the two can never disagree, and a 39.6 MB table is not read twice.

🐛 **Two bugs in chunk 1's reader, found while adding locale support.**
`ResTable_config` puts density at offset **14**; chunk 1 read it at **12**, which
is `orientation|touchscreen` — zero for practically every resource. So every entry
looked density-less, the best-density-first ordering did nothing, and the only
thing choosing between five candidate rasters was the file-size tiebreak. The
icons came out right anyway, which is precisely why it survived review. Second:
values carried no **locale**, and a string resource exists once per translation —
Outlook's label has **62** of them. "First value wins" meant "whichever
translation the table happened to list first".

Both now fixed and pinned: Chrome's foreground orders 640→480→320→240→160, and
the default locale sorts ahead of all 62.

5. Resolve `android:label` through the same table when the manifest gives a
   reference — completes W51 for Outlook and Gboard.
6. Migration + columns on `AppPackage`; store at upload; backfill existing rows.
7. `GET /api/v1/packages/{id}/icon` and the icon column left of the app name,
   with the ×1.5 adaptive crop in CSS and a placeholder for the vector-only apps.

**Verified on the live Docker stack, not only in tests.** The migration was
round-tripped on Postgres against a table with 10 existing rows (3 columns → 0 →
3; `icon_adaptive` NOT NULL took its `server_default` cleanly). After a rebuild
the catalog reads:

| | |
|---|---|
| Packages with a real icon | **9 of 10** |
| Butterfly iQ | monogram — vector icon, as designed |
| Rendered on `/apps` | 9 `<img>`, 3 adaptive / 6 legacy, 1 monogram |
| Icon over HTTP | `200 image/png 12246 bytes` |

🐛 **`backfill_labels` had no caller. Anywhere.** Not in the app, not in a test.
It was written for W51 to rescue packages named by their package id, and was
never wired to anything — so it never ran, and nothing failed to say so. W53's
icon backfill was about to inherit exactly that. It now runs from `lifespan` on a
worker thread, resolved through `dependency_overrides` rather than importing
`SessionLocal` (the docstring on `get_session_factory` warns in as many words
that a background task importing it directly is one that talks to the real
database during a test run).

The test for it **starts the app** and finds the thread by name, rather than
calling the function — a test that called it would have passed throughout the
period the bug existed. Confirmed by deleting the `lifespan` call and watching
the test fail.

##### ✅ Chunk 3 — hardening, after a pre-commit review found real defects

A 14-agent review of the uncommitted surface (6 dimensions, top findings verified
by two adversarial refuters each) produced **26 candidates; every one of the 4
verified was confirmed**. Committing without it would have shipped all of these.

**`resources.arsc` is attacker-chosen content** — the whole point of the inspector
is to read files it does not trust — and the first draft treated it as merely
untidy:

| Defect | What it actually did |
|---|---|
| `_resolve` bounded **depth, not branching**, and kept no visited set | a **511-byte** APK could ask for years of CPU |
| `entry_count` was an unchecked uint32, and the slot loop `continue`d rather than stopping | a declared 4 billion entries = 4 billion iterations over a few hundred bytes |
| `StringPool` decoded every string eagerly with no cap | 2 MB table → **603 MB** of heap; scaled up, an OOM kill of the single uvicorn worker, dropping every in-flight check-in |
| `read_table` caught `(KeyError, ValueError, ArscError)` | `struct.error` is **not** a `ValueError` — a truncated table escaped as an HTTP 500 and aborted the whole startup backfill |

Fixed with a per-path visited set plus a `_MAX_LOOKUPS` work budget, a clamped
`entry_count`, a decoded-bytes cap, and — the systemic one — `axml` now converts
`struct.error`/`IndexError` into its own declared `AxmlError` at the boundary, so
callers that catch the documented type actually catch everything.

🐛 **Writing those tests found a pre-existing hole the review had not**: a
truncated `AndroidManifest.xml` raised `struct.error` straight out of
`parse_elements`, past `_read_manifest`'s `except AxmlError`, as a 500 on upload.
That predates W53 entirely — the manifest path always had it.

🐛 **The startup backfill never converged.** It selects rows with no icon, but an
app whose icon is a vector drawable can never *get* one — so Outlook's 172 MB base
APK was re-read and its 39.6 MB table re-parsed at **every server start, forever**,
at 1.4 s and 356 MB of heap per attempt, to produce nothing. Now
`icon_source_version_id` records the version last inspected, checked *before* the
read; comparing against the version means a new build is still re-examined.
Verified on the live stack: all 10 packages marked inspected, and a restart logs
nothing.

🐛 **Multi-select managed configuration was written as a scalar.** Android carries
`multi-select` as `String[]`; an app reads it with `getStringArray`, which returns
**null** for a String or an Int — so the app kept its default while the device
reported the policy applied. Exactly the silent failure `AppConfigPlan` exists to
prevent, and it had been sharing the `TYPE_CHOICE` branch. Now `AsStringList` →
`putStringArray`, with 5 tests.

Also: the version-expansion row still spanned 5 columns after a 6th was added.

##### ✅ Deployed to `209.182.235.108`, 2026-09-06

Committed as `51dc262` and pushed to `main`. Database backed up to
`/root/takmdm-20260906-024856.sql.gz` **before** migrating.

| Check | Result |
|---|---|
| Alembic | `r8t0v2x4z6b8` → **`t0v2x4z6b8d0`** |
| Containers | api / db / proxy running |
| Errors in log since restart | **0** |
| Backfill on the live catalog | Chrome → WEBP adaptive 9 540 b; ATLAS MDM → PNG adaptive 68 425 b; both marked inspected |
| `/apps` | 200, 2 icon images, both adaptive |
| Icon endpoint | `200 image/webp 9540 bytes` |
| `https://…:8443/healthz` | 200 |
| `https://…:8443/` | **403** — console still not exposed on the device port |
| `http://…:8080/api/v1/provisioning/agent.apk` | 200, 7 057 180 b |
| `http://…:8080/apps` | **403** |

⚠️ **The agent APK on the server was not replaced.** Local `assembleDebug` is
version **57** and carries the multi-select fix and the new icon; the server still
serves the older published build. Publishing a new agent updates the fleet, so it
is a deliberate act, not a side effect of a server deploy — and the two fixes that
matter on-device (multi-select `String[]`, and `REFUSED_DOWNGRADE` demoted to a
warning) do not reach any device until it happens.

⚠️ **Our own icon is the heaviest in the library**: 213 KB, a 432² RGBA PNG,
because the agent's `ic_launcher_foreground` is unoptimised. The resolver is
right to take the highest density; the asset is what is oversized. Mitigated for
now by `loading="lazy"` and a 24-hour private cache. Worth optimising the PNG.

##### Later, unlocked by the same reader

Outlook's and Gboard's **display names** (W51's remaining gap), managed-config
**titles** and **choice lists** (W49 shows raw keys). All string lookups, no
rendering — genuinely reachable now.

#### 🔻 W54 — W49 completed: real names and real choices for managed config

W49 shipped managed configuration with **raw keys and free-text choices**, because
nothing could resolve a resource reference. W53 built the reader; this spends it.

**Measured before building** — every title reference in every fixture resolves:

| App | Keys | Title refs | Resolved | Choice-array refs |
|---|---|---|---|---|
| Chrome | 231 | 231 | **231** | 270 |
| Gboard | 82 | 78 | **78** | 8 |
| Outlook | 44 | 1 | **1** | 0 |
| Field Maps | 11 | 11 | **11** | 0 |
| ATAK | 6 | 6 | **6** | 0 |
| Messages | 2 | 2 | **2** | 0 |
| Butterfly / Survey123 | 3 / 10 | 0 | — | 0 |

329 titles, none lost. Choice options need **bag entries**, which the W53 reader
skips outright (`if entry_flags & _ENTRY_COMPLEX: continue`) — a `<string-array>`
is a `ResTable_map_entry` holding N `ResTable_map` children. Prototyped: Chrome's
`AdsSettingForIntrusiveAdsSites` resolves to
`["Allow ads on all sites", "Do not allow ads on sites with intrusive ads"]` with
`entryValues` `["0", "1"]` — label and value, which is exactly a `<select>`.

##### ✅ Chunk 1 — resolution — **done**

**383 of 383 keys across all eight fixtures now carry the app's own title**,
including ATAK, Field Maps, Butterfly and Survey123, which previously showed none.
No fixture lost a title.

Options resolve for **41 of the 42 eligible choice keys** (one app's arrays are
themselves unresolvable). The other 93 Chrome keys carrying `entries` are
**booleans** — they already render as a true/false control, and giving them a
dropdown of the app's prose would replace a precise control with a vaguer one, so
they are deliberately left alone.

🔍 **The pairing is index-based, so an off-by-one would be silent and would send
the device a value the operator never chose.** Verified independently: across 45
choice keys, 19 declare a `defaultValue`, and **every one of those 19 falls inside
its own resolved option list**. Zero contradictions. That is evidence the labels
and values line up which does not depend on the pairing code being right.

##### ✅ Chunk 2 — the console — **done, verified in a real DOM**

`jsdom` against the live `atlas.js`, not an assertion about intent:

| | Result |
|---|---|
| Resolved choice | `<select>` with values `["", "1", "2"]` and the app's labels |
| Multi-select | checklist of 3 checkboxes, not a text box |
| Choice whose arrays did **not** resolve | falls back to text **plus** the honest hint |
| Save | `{"AdsSetting…":"2","URLBlocklist":"example.com\nthird.test",…}` |
| Untouched key | absent from the payload |

⚠️ **Separator collision, found by looking rather than by test failure.** The
console first joined checked values with a comma, and the agent split on commas —
so an option value *containing* a comma would be torn into two values the app
never offered. None of the 133 real option values contains one, but that is luck,
not a guarantee. The console now joins with **newlines** and the agent prefers
newlines when present, falling back to commas only for a hand-typed list.

##### ✅ Chunk 3 — a second review, and the worst bug of the lot

16 candidates, 4 verified, **all 4 confirmed**. Two were in W54 code, one was in
the W53 parser, and the most damaging **predated both**.

🐛 **The one that wipes fleet configuration.** `_policy_form.html` rendered saved
values as `value="{{ config_values | tojson }}"`. Jinja's `tojson` escapes `<`,
`>`, `&` and `'` — but **not** `"`, and JSON is made of double quotes. A browser
parses that attribute as the single character `{`. Re-open a policy, press Save,
and the row submits `{`, `json.loads` raises, `form_parse` swallows it, the row
vanishes — and the next check-in calls `setApplicationRestrictions` with an empty
Bundle, erasing that app's entire configuration from every device. No error
anywhere. Shipped in W49; the existing test only *rendered* the page and asserted
substrings, which the broken markup satisfies. Single-quoting the attribute fixes
it, and a real round-trip test now pins it.

🐛 **Slot count is not work count.** Nothing requires index slots to name distinct
entries, so a chunk whose every slot holds offset 0 aims all of them at one bag
declaring the maximum member count: cost is slots × members, gigabytes from a few
KB. Each entry offset is now read once per chunk, with a chunk-wide member budget.

🐛 **Compaction shifts pairing.** `array()` dropped unresolvable members instead of
holding their position, so if both sides dropped the *same number* at different
indexes, the length guard passed and every label sat against the wrong value —
sending the device a value the operator never chose. Members are now positional
(`None` where unresolved) and pairs are dropped, never single sides.

🐛 **"Not declared" ≠ "declared but unreadable."** Both returned `[]`, so an
unresolvable `entryValues` fell back to "the labels are also the values" and sent
the app prose — *"Allow ads on all sites"* — where it expected `1`.

🐛 **My own separator guard was wrong for exactly one item.** Keying on "contains a
newline" works for two or more selections; a single checked value joins to itself
with no newline, falls through to comma-splitting, and `Smith, John` becomes two
values. The console now **terminates** its lists with a newline, so one is as
unambiguous as ten. The test I had written covered the case that worked.

**Performance, measured not guessed.** Ingest parsed the table twice (1.53 s → was
2.79 s on Outlook); `declared_config` is now computed during the pass that already
holds the table. The app-config schema endpoint went from 0.13 s to 1.40 s and
~186 MB per request — it fires once per arrow-key press in the picker — so scans
are memoised by artifact hash (the **result**, never the bytes: an earlier
`lru_cache` over bytes was removed for pinning a gigabyte).

##### ✅ Deployed, 2026-09-06 — server **and** agent 58

Commit `65a6222`. Database backed up to `/root/takmdm-20260906-033821.sql.gz`
first. Agent published under the operator's standing authorisation.

| Check | Result |
|---|---|
| Containers / alembic | api·db·proxy running, `t0v2x4z6b8d0` |
| Errors in log since restart | **0** |
| Agent APK | **58 (0.21.0)** uploaded and published; signature checksum matches the pinned `IJS8…yxkQ`, so provisioning and updates are unaffected |
| Chrome schema on the live host | 170 keys, **170 with a resolved title**, 24 with an option list |
| e.g. `BrowserSignin` | `0` = "Disable browser sign-in", `1` = "Enable browser sign-in" |
| Second schema request (memoised) | **0.023 s** |
| `https://…:8443/healthz` | 200 |
| `https://…:8443/` | **403** |
| `http://…:8080/…/agent.apk` | 200 — serves **58 (0.21.0)**, 20 719 350 b, checksum `IJS8…yxkQ` |
| `http://…:8080/policies/…` | **403** |

⚠️ **The signing key was verified before publishing, not after.** A release built
with a different key would have been un-installable over the existing agent on
every device and would have broken QR provisioning — the kind of thing worth
checking while it is still cheap.

🐛 **"Published" means two different things, and I conflated them.** Uploading the
APK sets `AppPackageVersion.published`, which puts the build in the **library**.
Aiming the **fleet** at it is a separate pointer — `agent.current_version_code` in
`app_setting`, written by `agent_update.publish()` from the Admin page. After the
upload above, the library held 58 and the channel still read **57**, so the one
enrolled device (`R5GL40MMHRN`) would have stayed on 0.20.0 indefinitely while
everything looked deployed. Reporting it as shipped to devices was wrong.

`agent_update`'s own docstring is explicit that there is "exactly one pointer,
`agent.current_version_code`, and publishing aims it at the whole fleet" — the
information was there to be read. Channel now set to 58, and
`offer_for()` confirms the device is offered
`0.21.0 / 20 719 350 b` at its next check-in.

##### ✅ Hardware: the agent replaced itself, 2026-09-06

`R5GL40MMHRN` went **0.20.0 / 57 → 0.21.0 / 58** at 03:56:50, roughly two
check-ins after the channel was aimed at 58 — no operator action on the tablet.

| After the update | |
|---|---|
| Compliance | **COMPLIANT** |
| `acked_state_version` | 13, equal to `state_version` |
| Rollout | `on_published=1, behind=0, unhealthy=0` |

That is the Device-Owner self-replacement path proven on hardware, and it is the
one with no rollback — Android refuses a downgrade, so a bad build could only be
cured by another build.

##### ✅ Hardware: multi-select managed config, and the downgrade warning

Both gaps closed on `R5GL40MMHRN` by assigning a profile carrying Chrome's
`PolicyDictionaryMultipleSourceMergeList` (a real `multi-select`, 7 declared
options) alongside a plain string key as a control.

Desired state carried exactly what it should — the wire value keeping its
terminator, and the declared type the agent needs:

```json
"values": {"PolicyDictionaryMultipleSourceMergeList": "ExtensionSettings\nKeyPermissions\n",
           "HomepageLocation": "https://atlas.test/start"},
"types":  {"PolicyDictionaryMultipleSourceMergeList": 4, "HomepageLocation": 6}
```

**Read from the device's own log**, not inferred from a status:

```
21:09:57 I/PolicyApplier: applied 2 config keys to com.android.chrome
21:09:57 I/SyncService:   sync: state=14 applied=14 errors=0
```

Two keys, both of mine, across four consecutive check-ins with `errors=0` and no
coercion rejection. The three `has no declared type` warnings in the bundle are
from **18:17**, hours earlier, from the previous policy — worth checking rather
than assuming, since a grep for "rejections" matched them.

✅ **W50's downgrade deconfliction, also proven here** and previously unverified.
The tablet carries Chrome `733920733` against the policy's `725815833`:

```
W/Reconciler: com.android.chrome is at versionCode 733920733 but the policy
              wants 725815833; keeping the newer build
```

Surfaced as a **compliance warning** while the device stays COMPLIANT, and the
managed configuration still applied to the package the DPC did not install —
exactly the behaviour W50 specified.

✅ **Self-replacement logged from the inside** as well:
`I/Reconciler: agent update: replacing 57 with 58 (0.21.0); this process is about
to be killed` → `I/Application: agent starting (v0.21.0)`.

⚠️ **What is still not proven:** that *Chrome itself* reads the `String[]`. The
agent put it in the Bundle and `setApplicationRestrictions` accepted it, which is
the whole of the contract this project controls; what a third-party app does with
a correctly-typed value is its own business.

⚠️ **Left on the device:** the proof profile is assigned at **rank 10**, so it
outranks the pre-existing "test app configs" and its three password keys are no
longer being applied. Remove it to restore the previous state.

⚠️ **A curl size is not a file size.** The W53 record said the provisioning APK
was "7 057 180 b" and W54's first draft said "7 196 444 b" — both were
`curl -m 30` giving up mid-transfer over the public link, and both were reported
as if they were the artifact's size. Measured on the host, the endpoint serves
the full **20 719 350 b** with the right checksum. A number that arrives without
an error is not therefore a measurement of the thing intended.

##### Chunk 1 — resolution (original plan)

1. `arsc.py`: read complex entries; `ResourceTable.array(rid)`.
2. `app_restrictions.py`: take a `ResourceTable`; resolve title/description, and
   `entries`/`entryValues` into paired options.
3. `discover()` parses the table once and passes it (one parse, three questions —
   Outlook's is 39.6 MB).
4. Tests across all eight fixtures, including the two that declare no titles.

##### Chunk 2 — the console, and the device

5. Carry options through `AppConfig` / `form_schema`; render a real `<select>`
   for `choice`, and a checked list for `multi_select`.
6. The agent already coerces `multi_select` to `String[]` (W53 hardening); the
   console can now send values the app actually declares rather than typed guesses.
7. Deploy server **and publish the agent APK** — standing authorisation from the
   operator, 2026-09-06: *"its always ok to push the agent apk and server updates
   - we are in development."*

#### 🔻 W55 — ATLAS branding in the DPC: splash and banner

Operator: *"the dpc app to show a splash screen upon load … the logo in the test
files called atlas.png … persist for 3 seconds. i also want that same logo to be
the top banner."*

`Test Files/ATLAS.png` is 1983×793 (2.5∶1) — a finished banner artwork, not a
transparent mark: the ATLAS glyph, wordmark, an MDM badge, the tagline "ATAK
TACTICAL LIFECYCLE & ADMINISTRATION SYSTEM", and "A TAK-Solutions product", all
on a near-black `#000203` field with a topographic/world texture.

Two things that came out of *looking* at it rather than assuming:

* **Its background is near-black; the app's is navy `#071528`.** Dropping it into
  the existing header would show a black rectangle pasted on navy. So the banner
  is **full-bleed** — the logo *is* the header, and there is no mismatch to see.
* **At header size the whole logo is illegible.** Full width on a tablet, 2.5∶1
  is ~320dp tall — absurd for a header. Simulated `centerCrop` bands at 72/88/104
  dp and looked at them: **88dp** keeps the mark, wordmark and MDM badge crisp
  and drops only the tagline, which the splash still shows in full.

⚠️ **Platform contract, not previously recorded.** minSdk is 33, and from Android
12 the **system splash screen always shows and cannot be suppressed** — an app
gets one whether it asks or not. A custom 3-second splash therefore runs *after*
it, and two unrelated splashes in a row look like a bug. The system splash is
themed to the same near-black so the sequence reads as one thing.

##### ✅ Shipped as agent 59 (0.22.0) — and 🐛 a real self-update defect found

The tablet reached **0.22.0 / 59** at 04:48:17, COMPLIANT and fully acked. But the
operator reported *"agent is not updating"* and they were right at the time: it
took **five download attempts over ten minutes**.

The agent's own log named it — `agent update 59: download failed verification` ×4
— and the chain was then checked end to end rather than guessed at:

| Link | Evidence |
|---|---|
| The APK built here | `71a70df5…`, 20 779 763 b |
| Stored on the server | re-hashed from the artifact store: **identical** |
| Sent by nginx | `200 20779763` — the **complete** file, three separate times |
| Verified on device | ❌ failed three times, then passed on the fourth |

So the server is blameless and the fault is in the agent's download or hashing.
Two further clues:

* The one `206` resume asked for `bytes=14171755-` and got exactly the remaining
  6 608 008 — a correct total length that **still** failed the hash, so the bytes
  already on disk were wrong, not merely incomplete.
* Failures come in **pairs seconds apart** (21:38:04 / 21:38:22, 21:41:12 /
  21:41:26), which looks like two reconcile passes racing on the same cache path
  `cacheDir/<sha>` — one deleting or truncating while the other writes.

⚠️ **This is not new to W55.** The same signature appears against build 51 (once)
and build **57 (four times, then success)**. It has been intermittently wasting a
full 20 MB download per attempt and making every rollout look broken.

##### ✅ Root cause found and fixed in agent 61 (0.24.0)

Reported twice by the operator as *"synced but not updated"*. The cause is a
**race between two reconcile passes**, and the evidence names it precisely:

* A `206` resume brought the file to **exactly** the right total length
  (16 003 909 + 4 857 451 = 20 861 360) and **still** failed the hash — so the
  bytes already on disk were wrong, not missing.
* Every cycle left a fresh **~4–5 MB partial** behind.
* The sync log shows two passes **0.6 s apart** (22:00:21.924 / 22:00:22.534).

Both passes downloaded the same artifact to the same path — one writing from
offset 0 while the other appended a resumed range. The result is a file of the
right *length* holding interleaved bytes, whose only symptom is a hash mismatch.
That reads as a corrupt transfer, so the agent deletes and retries, forever.

The server was blameless throughout: the APK built here, the artifact store's
copy and the bytes nginx sent all hash identically, and nginx logged the complete
file three times over.

**Fixed** by serialising downloads on the artifact hash, and landing bytes in a
`.part` file renamed into place **only after it verifies** — so the destination
never holds anything unverified and two passes cannot interleave. A short body is
now also caught against `Content-Length`: `copyTo` returns silently when a stream
ends early, which is why the only previous evidence was a hash mismatch pointing
at the wrong cause.

⚠️ **Not unit-tested.** `ApiClient` takes an Android `Context`, so this cannot be
exercised off-device without adding Robolectric, which the agent deliberately does
not carry. Reasoned from the evidence above, not proven by a test.

⚠️ **And not yet proven on hardware either.** Download requests per build:

| Build | Requests | Fetched by |
|---|---|---|
| 57 | 5 | old code |
| 59 | 5 | old code |
| 60 | **5** | old code |
| 61 | **1** | **old code** — 60's downloader |

61 arriving in one attempt is *not* evidence the fix works: it was fetched by the
unfixed code in 60 and simply did not collide that time. The first update fetched
**by 61** is the real test.

##### 🟡 First evidence from the fixed downloader — encouraging, not conclusive

| Build | Requests | Fetched by |
|---|---|---|
| 57 / 59 / 60 | 5, 5, 5 | old code |
| 61 | 1 | old code |
| **62** | **1** | **fixed code** |

Also **zero** `failed verification` lines in the agent log since `0.24.0` started.

⚠️ **One clean run does not settle an intermittent bug**, and 61 shows why: it also
came down in a single request through the *unfixed* code. The honest reading is
that nothing contradicts the fix yet. Confidence comes from several consecutive
clean updates, not this one.

##### Plan (5 steps)

1. Asset: `drawable-nodpi/atlas_wordmark.webp`, downscaled from the 1.8 MB
   source — matching the existing `ic_atlas_fg.png` nodpi convention.
2. Header becomes a full-bleed 88dp banner; the Sync button moves to its own row
   beneath, since a full-bleed image leaves nowhere to sit.
3. Splash overlay inside `activity_main.xml`, shown on load and dismissed after
   **3 s**, with the whole logo `fitCenter` on its own background colour.
4. Theme `windowSplashScreenBackground` to match, so the unavoidable system
   splash hands over invisibly.
5. Build, deploy to the fleet, and **have the operator confirm what appeared** —
   a build that compiles proves nothing about what is on screen.

#### 🔻 W56 — The ATLAS store reaches the device

Operator: *"any application that is moved into the Atlas store should show up in
the available apps on the EUD for the user to download and install. also, the web
portal page for atlas store should share the same table properties as the local
apps tab, within reason."*

⚠️ **This changes what "Available" means, and the DPC says so in its own words.**
`AppsTabPlan`'s docstring reads: *"Every managed app is **required** by policy …
`AVAILABLE` means 'policy wants this and it is not installed yet' — a queue, not a
shop."* The store makes it a shop. The tab has to carry both senses without
blurring them: a required app not yet installed is a **pending obligation**, a
store app is an **offer**, and showing them identically would make a broken policy
look like a shopping list.

✅ **The precedent already exists.** `files` is split into `required` and
`available` — *"what the agent must install and what it should offer the user in
the marketplace (F4)"* — and the DPC already renders optional files the user picks.
Apps mirror that rather than inventing a second idiom.

**Design decisions:**

* Store membership is **server-wide curation, not policy**. Every enrolled device
  is offered the whole store; there is no per-device store yet. That matches the
  operator's "any application moved into the store" exactly, and a narrower rule
  can be added later without changing the wire format.
* The desired state gains a **new `store` key** rather than reshaping `apps` into
  `{required, available}`. Additive means an agent in the field ignores it; the
  reshape would need a `schema_version` bump, whose whole purpose is to make an old
  agent *refuse* the document.
* A store app the agent must **never auto-install** — that is the difference
  between an offer and an order.

##### ✅ Chunk 1 — server — **done, 784 tests**

Built as planned, and the trap in step 3 was real: nothing recomputed anything.

🐛 **The test that nearly proved nothing.** My first "listing wakes devices" test
called `eff.refresh()` directly — which recomputes unconditionally — so it passed
with the invalidation deleted. Rewritten to go through the cache-aware
`get_effective()`, and then verified by removing the invalidation and watching it
fail. Two tests now cover it.

1. `resolve_store_apps()`: every `store_listed` package with a publishable build,
   resolved to the same artifact shape as required apps.
2. Carried on the effective payload and into the desired state as `store`.
3. ⚠️ Toggling store membership is **not** a policy edit, so nothing currently
   recomputes any device. Without wiring that, a store change reaches nobody.
4. Tests: a store app reaches a device with no policy at all; removing it withdraws
   it; an app both required *and* listed stays required and is not offered twice.

##### ✅ Chunk 2 — agent — **done, 11 AppsTabPlan tests**

Required apps and offers share the Apps screen and its bucketing — a user looks in
one place for "things I could have" — but read differently once there. An offer is
`NEUTRAL`, never `WARN`: nothing is wrong with a store app nobody has taken, and
colouring it like an unmet requirement would cry wolf on every device that ignores
the shop. Only offers get an install button; a required app has none, because the
device installs it regardless and a button would imply a choice that does not exist.

`installFromStore` is deliberately **not** folded into `reconcileApps`. That
function carries the downgrade, pinning and OBB rules that make a *required* app
converge, none of which apply to a user tapping install — sharing it would mean
one caller is always obeying rules meant for the other.

5. Parse `store`; render as offers in Available with an explicit install action.
6. `AppsTabPlan` learns the required/offered distinction, with tests.
7. Install on demand through the existing installer; never from the reconciler.

##### ✅ Chunk 3 — the store table — **done**

Icon, name over package id, published version, parts, sortable — and the header
now matches the rows: verified by rendering the real page and counting, **5
headers, 5 cells**. The intro copy was rewritten too; it claimed the store "does
not install anything on its own", which is still true but no longer the whole
story now that the shelf reaches every device.

8. Match the Local apps table within reason: icon, name over package id, latest
   version, parts, sortable. 🐛 Its header declares **four** columns
   (`Package`, `Label`, `Latest version`, ``) while every row emits **three** —
   so the columns are already misaligned today.

#### 🔻 W57 — The device needs the name and the picture sent to it

The store worked on the first try — screenshot shows UASReady offered with an
Install button and a neutral *Available* pill — but the card was titled
`com.taksolutions.uasready` and had no icon.

⚠️ **The device cannot look either of them up.** `appLabel()` asked
`PackageManager`, which only knows apps that are **installed** — and the Apps
screen most needs a name for one that is *not*, which is the entire point of an
offer. Same for the icon.

So both travel with the entry now, on required apps as well as offers:

* `label` — read out of the APK at upload (W51/W53). Preferred over
  `PackageManager`, which stays as the fallback for an installed app whose entry
  predates this, with the package id as the last resort because it is at least true.
* `icon_url` → a new device-facing `GET /api/v1/device/apps/{package}/icon`,
  behind the mTLS device guard. Already reachable through nginx: the device port
  opts in `/api/v1/device/` as a **prefix**, so no proxy change was needed.

Two things kept cheap on purpose:

* The entry is built from `icon_media_type` — a small column — never by touching
  `icon_data`. Reading the blob to decide whether a URL exists would drag it into
  every check-in for every configured app, which is the exact regression the
  column was deferred to avoid (W53).
* The device caches the icon at `cacheDir/icon_<pkg>_<versionCode>`. There is no
  hash of the icon to key on, and computing one server-side would mean loading the
  blob; the version code changes when a new build brings new artwork, which is the
  same thing for this purpose.

An app with no extractable icon sends `icon_url: null` rather than a URL that
would 404 on every device that tried it, and the card simply starts at the name.

##### ✅ Confirmed on hardware

The device fetched the icon itself — nginx logged
`GET /api/v1/device/apps/com.taksolutions.uasready/icon → 200, 55 949 bytes`,
matching the stored blob exactly. Chrome's was *not* fetched, which is the lazy
behaviour working: it sits on the Installed tab, and an icon is only pulled for a
card actually being drawn.

##### 🟢 Download race: second consecutive clean update

| Build | Requests | Fetched by |
|---|---|---|
| 57 / 59 / 60 | 5, 5, 5 | old code |
| 61 | 1 | old code |
| 62 | 1 | fixed code |
| **63** | **1** | **fixed code** |

Two in a row through the fixed downloader, against a bug that previously cost five
attempts three times running. Still short of proof — 61 managed one attempt on the
old code — but the pattern is now going the right way and each build adds a sample.

#### 🔻 W58 — Progress and cancel for a store install

Operator: a **progress bar beside the Install button**, the button becoming
**Cancel** while it runs, and the bar turning into **Installing** for the second
phase.

The install is two phases that fail and feel differently, and the UI has to say
which one it is in. **Downloading** is 15–20 MB over the device link: slow,
measurable, and safely abandonable. **Installing** is `PackageInstaller`
committing: quick, unmeasurable, and *not* safely abandonable — Android is
mutating the package at that point. So Cancel is offered for the first phase only.

##### Plan (5 steps)

1. `ApiClient.downloadArtifact` gains an optional progress callback and a
   cancellation check. ⚠️ Must not disturb the W-fix discipline it now carries:
   the per-hash lock, the `.part` file, verify-then-rename, and the
   `Content-Length` short-read check.
2. `copyTo` cannot report progress, so the copy becomes an explicit loop that
   counts bytes and polls for cancellation between buffers.
3. `installFromStore` reports `DOWNLOADING` (with bytes) then `INSTALLING`, and
   returns a three-way result — done, cancelled, failed — rather than a
   string, so "the user changed their mind" cannot be shown as an error.
4. Progress spans **all parts** of a split app, summed from the entry's
   `size_bytes`, so the bar measures the install rather than one file of several.
5. ⚠️ The UI updates the bar **in place**, not by re-rendering the list. The
   callback fires per 8 KB buffer — thousands of times for a 16 MB app — and
   rebuilding every card at that rate would make the screen unusable. Posted only
   when the whole percent changes.

##### ✅ Built as agent 0.27.0 (64)

🐛 **A near miss worth recording.** The first attempt patched `MainActivity` by
slicing between two text markers, and the region between them contained
`appsTabBar` and `renderFiles` — both silently deleted. The Kotlin compiler caught
it (`Unresolved reference`), but only because they were referenced elsewhere; a
private helper used once would have vanished without complaint. Reverted and
redone as two exact-match edits instead. **Do not delete code by line range when
an exact-match replacement will do.**

`copyTo` had to become an explicit read/write loop — it can neither report
progress nor be interrupted. Cancellation unwinds through a dedicated
`TransferCancelled`, and the `.part` file is deliberately **left behind**: a user
who changes their mind and retries then pays only for what is missing, and the
verify-then-rename discipline means an abandoned partial can never be mistaken for
a finished download.

A resumed transfer adds what is already on disk to the running total, so the bar
measures the **whole file**. Reporting only the remainder would make a resumed
download start at 70% and crawl, which is worse than showing nothing.

#### 🔻 W59 — Kiosk becomes its own category

Operator: remove the kiosk sub-type from App Management; Kiosk becomes a category
with eight sub-topics — single app, multi app, background apps, launcher,
peripheral settings, kiosk exit settings, website kiosk settings, kiosk
screensaver.

Three things were established **before** building, and two changed the shape:

⚠️ **Hexnode's documentation could not be read.** Their help pages are
JS-rendered; `WebFetch` returned navigation menus and no setting names. Operator's
call: **build from Android capability**, using Hexnode's section names as the
structure but not inventing their exact fields.

⚠️ **Four of the eight need the agent to become a launcher.** The manifest
deliberately declares no `category.HOME`, and the platform reference is blunt:
*"adding kiosk to a background agent is two API calls; removing launcher behaviour
from a launcher is a rewrite."* Multi app, launcher, website kiosk and screensaver
all need that. Operator's call: **build the enforceable half now, write the
launcher rewrite up as a decision record.**

✅ **Peripheral settings — the operator's answer beat all three options offered.**
The overlap with the existing `RESTRICTIONS` policy is resolved *temporally*, not
spatially: **kiosk peripheral settings apply while the device is locked; the
standard restrictions resume when it leaves kiosk.** Nothing is set in two places
at once, so there is no conflict for the resolver to arbitrate — and it matches
what a kiosk is for, since a device on a wall wants different rules from the same
device in someone's hand.

##### Chunk 1 — structure

1. New `KIOSK` policy type and spec; `kiosk_package` moves out of `APP_CATALOG`.
2. Category in the creator catalog carrying all eight sub-topics.
3. ⚠️ The agent reads kiosk from `APP_CATALOG` today. It must read `KIOSK` **and
   fall back**, or a device that has not taken the new build loses its kiosk the
   moment the server deploys.

##### Chunk 2 — the enforceable sections

4. **Single app** — `kiosk_package`, already working and hardware-verified.
5. **Background apps** — extra packages added to the lock-task allowlist.
6. **Kiosk exit settings** — the `setLockTaskFeatures` flags, which map onto this
   section exactly. ⚠️ Two rules from the reference are load-bearing:
   `NOTIFICATIONS` cannot be set without `HOME`, and omitting `GLOBAL_ACTIONS`
   removes the power menu, leaving a field device recoverable only by hard reset.
7. **Peripheral settings** — kiosk-scoped overrides, applied on entering kiosk and
   released on leaving it.

##### Chunk 3 — declared and refused

8. Multi app, launcher, website kiosk, screensaver: declared so the operator can
   see they exist, refused at validation with the launcher reason — the same
   pattern the Knox-gated network fields use.
##### ✅ Deployed, 2026-09-06

Database backed up to `/root/takmdm-20260906-152232.sql.gz` first. **No migration
needed** — the move is spec and registry only, and alembic stayed at
`t0v2x4z6b8d0`.

⚠️ **Checked before deploying, not after:** whether any stored `APP_CATALOG` spec
still carried `kiosk_package`, which would now fail validation and break an
existing policy on load. None did — three APP_CATALOG policies, none using kiosk —
so there was nothing to migrate. Had one existed, this deploy would have needed a
data fix first.

Smoke-tested against the live server rather than trusting the test suite:

| Attempt | Result |
|---|---|
| Single-app kiosk with peripherals | **201** |
| `website_kiosk_url` | **422** — "needs an ATLAS launcher" |
| Notifications with the home button blocked | **422** |
| `kiosk_package` on `APP_CATALOG` | **422** |

All eight sub-pages render; `app_management:kiosk` is gone. The smoke policy was
archived and deleted afterwards — deletion is deliberately two steps, so it took
both. Device unaffected: `0.28.0`, COMPLIANT, state 18/18.

9. ✅ **Decision record written**: [docs/DECISION-atlas-launcher.md](docs/DECISION-atlas-launcher.md)
   — three options, the risk each carries to the kiosk **escape hatch**, and the
   three questions worth answering before spending anything. Recommends a
   separate launcher APK, and only once multi-app kiosk is a confirmed field
   requirement rather than a feature-parity checkbox.

#### 🔻 W60 — A tiled texture behind the banner logo

`Test Files/pattern.png` — a dark navy contour texture, dominant `#000818`, the
same family as the logo's own field — tiled behind the banner.

Two decisions came from rendering it rather than reasoning about it:

* **Tile size is set by the density bucket, not by the layout.** `tileMode` repeats
  a bitmap at its *intrinsic* size, so the asset ships at **xhdpi** (640×256 px =
  320×128 dp). Simulated 64 dp and 128 dp tiles side by side: the smaller one
  repeated five times across a tablet and read as an obviously repeating motif;
  the larger repeats 2.5× and reads as texture. 20 KB, from a 1.6 MB source.
* **The logo stays opaque over it.** Its own background is a topographic/world
  texture of the same family, so it reads as a plate rather than a hole. Cutting
  it out to let the pattern through would have destroyed the artwork.

🐛 **And writing it up caught a bug that had nothing to do with the texture.**

W59's `releaseKioskPeripherals()` blanket-cleared every kiosk peripheral. But
three of them — camera, Bluetooth, screen capture — are *also* `RESTRICTIONS`
fields, and `applyRestrictions` runs **before** the kiosk path in `apply()`. So on
every sync of every device, kiosk or not, the release undid the Restrictions
policy: block Bluetooth in Restrictions, and the next check-in switched it back on.

It would have shipped invisibly — no error, no failed apply, just a policy that
quietly stopped holding. The release now **restores what Restrictions asked for**
rather than clearing, and only the genuinely kiosk-only peripherals (Wi-Fi config,
volume, brightness, airplane mode) are cleared on exit.

#### 🔻 W61 — Single-app kiosk: pick an app, not type a package name

Operator: *"the policy creator for single app kiosk just as a blank type field.
instructions on this are poor."* — two options wanted: **Select App** and
**Select app with activity**, the first like the required-app picker, the second
adding a class field and a *"restrict to this activity only"* checkbox.

The field was a bare text box, which told an operator neither what to type nor
which apps existed. It is now a dropdown of uploaded apps, the same source the
required-app picker uses, plus two radios that reveal the activity fields.

⚠️ **The mode is not stored.** It is derived on load from whether an activity
class is set, so there is no third piece of state to fall out of step with the two
that are saved. And switching back to "Select app" **clears** the activity fields
rather than hiding them — a hidden input still submits, so an activity left behind
would keep being sent while the operator could no longer see it. Verified in a
real DOM, including that clear.

⚠️ **"Restrict to this activity only" cannot mean what it sounds like.** Checked
against the platform before building rather than after: *"an app in lock task mode
can start new activities as long as the activity doesn't start a new task"* — so
an app locked in kiosk moves between its own screens freely and no Device Owner
API prevents it. The nearest thing,
`LOCK_TASK_FEATURE_BLOCK_ACTIVITY_START_IN_TASK` (confirmed to exist by compiling
against it, not by assuming), restricts by **package**, not by activity.

So the control is implemented and does something real — nothing outside the
allowlist can open in the locked task — and both the field description and the
applier say plainly what it does *not* do. Refusing it outright would have thrown
away a genuine tightening; naming it without the caveat would have promised a lock
Android does not offer.

A named activity launches as an explicit `ComponentName`, not through
`getLaunchIntentForPackage`: a kiosk screen is often not the app's launcher entry
and may not be exported as one. A leading dot expands against the package, the
same shorthand `component_class()` already handles server-side.

#### 🔻 W62 — The kiosk activity is picked, not typed

The class name is a fact about the build, so it comes out of the APK. Activities
and `activity-alias` entries are read from the manifest — the same walk that
already collects receivers — and the ones carrying a `LAUNCHER` category are
marked and sorted first, since a kiosk almost always wants the screen a user would
normally arrive at.

ATAK is the case that shows why it matters: **`ATAKActivityCiv` and
`ATAKActivityMil`**, two launchers in one build, and no operator should have to
know which string to type to lock a device to one of them.

⚠️ **It scans every part, not just the base.** Chrome's base APK declares three
activities and **none of them is its launcher** — the rest live in its splits. A
base-only scan would have produced a dropdown that silently omitted the very
screen an operator was looking for, which is worse than the text box it replaces.
Found by checking the extraction against all three fixtures rather than the one
that worked.

✅ **Measured on production, and the margin is not close:**

| Chrome | Activities | Launchers |
|---|---|---|
| Base APK only | 3 | **0** |
| Every part | **60** | 1 — `com.google.android.apps.chrome.Main` |

A base-only dropdown would have offered three Play Core dialogs and no way to
launch Chrome at all.

Fetched on demand and memoised by package, like the managed-config scan; the list
is refilled whenever the app changes, because an activity from the previously
selected app is not a valid choice for this one.

🐛 **The first DOM run reported an empty dropdown, and the code was fine.** The
panel had been dumped from an empty test database, so the app `<select>` held only
its placeholder — and assigning `.value` to an option that does not exist leaves
it empty, so no app was ever selected and nothing was fetched. The harness was
wrong, not the page. Same shape as the W52 jsdom failure: when a DOM test says a
feature is dead, suspect the fixture first.

#### 🔻 W63 — A kiosk app installs itself

Hardware report: *"tested single app kiosk, got error that the app designated for
kiosk mode not installed, not engaging"*. The policy was correct; the device
simply had nothing to lock to.

**Naming a kiosk app *is* an instruction to install it.** Asking an operator to
also add it under required apps is a second step that exists only to be forgotten
— and forgetting it produces exactly this error, which reads like a bug in the
kiosk rather than a missing line elsewhere in the policy.

Two fixes, and the second is the one that would have been easy to miss:

1. **The kiosk package is resolved as a required app.** Done in
   `resolve_required_apps` rather than in the applier, so it inherits the whole
   install pipeline — version resolution, artifact hashes, the downgrade rules —
   instead of growing a second, thinner one beside it. An explicit `required_apps`
   entry for the same package keeps its own pin or floor: an operator who pinned a
   build meant it.

2. ⚠️ **Kiosk now runs *after* the installs.** `policyApplier.apply()` runs before
   `reconcileApps`, so applying kiosk inside it would have failed on the very sync
   that installed the app — marking the device DEGRADED and engaging only on the
   next check-in. Making the app required without moving the call would have
   turned a hard failure into a slower, more confusing one. The kiosk step is now
   called from the reconciler after `reconcileApps`, for the same reason
   `suppressUnwantedApps` already was.

The refusal message was rewritten too: it now says the app is required and should
install on this or the next check-in, rather than stating a fact and leaving the
operator to guess whether the policy is wrong.

#### 🔻 W65 — Kiosk exit settings, as the operator actually meant them

Screenshot supplied from Hexnode. It shows **Kiosk Exit Settings** meaning a
deliberate way *out* of kiosk on the device — a passcode, a tap count to summon
the prompt, reboot behaviour — and not what I built under that name.

⚠️ **I mis-filed the existing section.** `keep_home_button`, `keep_recents_button`,
`keep_notifications`, `keep_system_info`, `keep_keyguard`, `keep_power_menu` are
*what the user can still reach while locked in*, not how to get out. They move to
their own group, **Permitted features**, and "Kiosk exit settings" becomes what
the screenshot shows. That is the "one more subtopic" — nine now, not a rename.

**Both mechanisms already exist in the agent**, which is why this is buildable:
`SYSTEM_ALERT_WINDOW` with a working `TYPE_APPLICATION_OVERLAY` (W44's data-usage
alert), and `RECEIVE_BOOT_COMPLETED` wired into `SyncScheduler`.

⚠️ **The exit passcode is not a security boundary, and the field must say so.**
It travels in the desired state, which is signed but readable on the device by
anyone with adb. It stops a user idly tapping their way out of a wall-mounted
tablet; it does not stop someone determined. Presenting it as security would be
the more dangerous error, because an operator would then trust it.

⚠️ **A local exit has to survive the next sync**, or the reconciler re-locks the
device seconds later and the exit reads as broken. That needs device-local state
the server does not own — the first thing in this project where the device
legitimately overrides policy until told otherwise.

⚠️ **Hexnode's "exit manually while an app is open" does not map.** It
distinguishes their kiosk launcher's home screen from a running app; ATLAS has no
launcher, so the gesture is always over the kiosk app and the option would be a
control with one possible value. Left out rather than shipped inert.

##### Plan

1. Regroup the lock-task features under **Permitted features**; add the subtopic.
2. New exit fields: allow manual exit, passcode, tap count, reboot-tap-to-exit,
   relaunch delay after reboot, auto re-enter.
3. Validators: a passcode is required to allow manual exit — an exit gesture with
   no gate is a kiosk anyone can leave by tapping.
4. Agent: tap-target overlay, passcode prompt, suspension state, reboot delay.
5. Tests, and the platform contracts recorded.

##### ✅ Done — 820 tests

Nine sub-pages now: **Permitted features** holds the six lock-task controls,
**Kiosk exit settings** holds the six new ones.

Two window-level details that had to be right:

* The tap target is `FLAG_NOT_FOCUSABLE` and 56dp in a corner. Focusable, it would
  take the keyboard away from the app the device exists to run; larger, it would
  eat taps that app needed — turning an escape hatch into a fault in the kiosk.
* The passcode prompt is a **separate, focusable** window, added only once the
  taps land. A passcode box that cannot take a keyboard is not a passcode box.

The exit is remembered against `SystemClock.elapsedRealtime()` rather than the
wall clock: it resets on reboot, which is exactly the intended lifetime, and it
cannot be extended by changing the device's date. It is recorded **before** the
release, so a crash between the two leaves the device out of kiosk with the reason
known rather than locked again with no trace.

#### W67 — the kiosk app was being restarted every two minutes

Reported as "applied a kiosk policy for ATAK and it crashes". It was not
crashing: `applyKiosk` runs on every sync and launched the kiosk app with
`FLAG_ACTIVITY_CLEAR_TASK` every time, which destroys the task and cold-starts
the app. ATAK was being killed and restarted every two minutes.

⚠️ **It failed green.** Every relaunch succeeded, so no exception, no policy
failure, no compliance change — the console showed the device healthy the whole
time. The only trace was `kiosk: launched … into lock task` repeating in the
agent's own log, which reads as normal operation. Found by pulling that log with
`COLLECT_LOGS`; adb was not needed and would not have been quicker.

The decision moved into `KioskLaunchPlan` (the `*Plan` pattern) because the bug
was in *when* the launch happened, not how — and a pure decision can be tested
without a device. Verified the test fails against the old always-relaunch
behaviour before keeping it.

The marker is cleared in `releaseKiosk`, which is the one place the device
actually leaves lock task, so the on-device passcode exit is covered too.

⚠️ Still unconfirmed: whether ATAK **also** has a genuine crash under lock task.
Only `logcat` shows that, and adb does not connect to this tablet.

#### W66 — the console's build number, on the device

The operator could not check that the tablet had taken the build the console
published: the DPC showed `0.33.0` and the console publishes a **versionCode**.
Two builds can share a version name, and it is the code that decides an update,
so the agent version row now reads `0.33.1  (build 71)`.

Banner logo replaced with `Test Files/atlasplain.png`, texture unchanged.

⚠️ The new artwork has a **real alpha channel**; the one it replaced was opaque
and carried its own dark field. The old one had to run edge to edge or its
lighter top and bottom read as two seams — this one has no edges to hide, so it
fills the bar's full 64dp, trimmed to its own opaque bounds.

⚠️ **`getbbox()` is the wrong way to trim this artwork.** It keeps any pixel
that is not exactly zero, and the logo has a halo at alpha 1–8 — at most 3%
opacity, invisible — below it. Trimmed that way the asset carried **11dp of dead
space at the bottom and none at the top**, so the logo sat high in a bar that was
nominally full height, and the gap read as an oversized margin. Trim on
`alpha > 8`. Measured, not eyeballed: 0.25dp above / 11.25dp below before,
1.5dp / 1.5dp after.

⚠️ It fills the height only while width is not binding. `fitCenter` keeps the
aspect ratio, so between the 132dp margins the logo goes width-limited below
roughly a 600dp screen and draws shorter — 45dp on a 411dp phone. On the tablet
this project targets it fills; on a phone the margins are the constraint, and
they are what keep the logo centred rather than under the Sync button.

Kept **lossless** (228 KiB): composited over the pattern, lossy left a max
visible error of 74/255 even at q95, on the chrome outlines where the logo meets
transparency. Against a 20 MB APK the size is not worth the artefacts.

##### Older

⚠️ **Left out on purpose:** Hexnode's *"exit manually while an app is open"*. It
distinguishes their kiosk launcher's home screen from a running app, and ATLAS has
no launcher — the gesture is always over the kiosk app, so the control would have
exactly one possible value.

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
| R17 | **A data package imports from `atak/tools/datapackage/incoming/` and nobody can say why.** Proven on `SM-X520` 2026-09-07, and it contradicts the source: `MissionPackageFileIO` marks that directory `// no watch`, the parent's `DirectoryWatcher` is provably non-recursive (it ignores directory events and carries TODOs about sub-directory listeners), and nothing else in `com/atakmap` references it beyond the HTTP transfer path. Behaviour with no identifiable mechanism can change between ATAK releases silently. | **Open, accepted deliberately.** ATLAS delivers there because `DirectoryCleanup` sweeps it after two hours, so packages do not accumulate forever the way they do in the watched parent — which has explicit `no auto-cleanup`. ⚠️ **Two things to confirm:** that the sweep actually happens (expected, never observed — if it does not, the reason for choosing this directory evaporates), and whether the import is immediate or waits for an ATAK restart. The watched parent remains a one-constant fallback (`files.DATA_PACKAGE_DEST`) if either answer disappoints. |
| R16 | ~~**ATAK Config has never run on hardware.**~~ | ✅ **CLOSED 2026-09-07, hardware-verified on `SM-X520`.** Deployed to `209.182.235.108`, policy assigned, device took it (`state 54 → acked 54`, `errors=0`), agent logged `applied 1 config keys to com.atakmap.app.civ`, and **ATAK itself shows the change** — Bluetooth Support on, which is not its default, with **no ATAK restart**. ⚠️ **No agent release was required**: the fleet already ran 0.44.0 and ATAK Config resolves into `app_configs` (D92), so a server-only deploy reached live devices. Had it been given its own applier every tablet would have needed updating first. Original text: the whole server chain was proven against two shipping APKs and the live console, but no tablet had ingested a generated `.pref`. |
| R15 | **The agent signing key is a fleet-wide single point of failure.** Android refuses an update signed with a different key, so losing it means no device can ever be updated again without re-provisioning. | Open. Same class as `pki/ca.key` (R8) and belongs in the same KMS/HSM answer. Called out now that OTA self-update is proven and will become the update path. |
| R5 | Mixed SoC vendors (Qualcomm XCover6 Pro / MediaTek Tab S10+) on One UI 8 | Test every firmware-level behavior on **both** models. ✅ **W90's ATAK Config cleared on two of the three, 2026-09-07** — Exynos 1580 (`SM-X520`) and Dimensity 9300+ (`SM-X828U`), each verified independently rather than extrapolated. `SM-G736U1` (Snapdragon) carries no ATAK, so there is nothing for this feature to configure on it. |
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
