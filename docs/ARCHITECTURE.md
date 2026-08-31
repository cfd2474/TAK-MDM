# TAK-MDM Architecture

Self-hosted Android MDM. Device Owner mode, sideloaded APK/XAPK deployment,
Samsung Knox integration, stackable composable policies.

## Operating envelope

Decided 2026-08-30:

| Dimension | Choice | Consequence |
|---|---|---|
| Connectivity | Intermittent / offline-tolerant | Desired-state reconciliation, not a command stream. No hard FCM dependency. |
| Fleet size | 50-500 devices | Single host is fine. Postgres job table over Celery. MinIO over CDN. |
| Scope | Generic core + TAK pack | ATAK is a first-class policy *type*, not baked into the core model. |
| Primary OEM | Samsung (Knox) | All OEM code behind an interface with an AOSP no-op implementation. |

---

## 1. Policy composition (the core feature)

The requirement, in Hexnode's terms: policies are *stacked*, not monolithic. A
device gets the union of the policies you pick for it. Nobody rebuilds a password
policy because one tablet also needs a kiosk lock.

### Entities

- **Policy** — named, single-*typed* document (`PASSWORD`, `RESTRICTIONS`,
  `APP_CATALOG`, `APP_BLOCKLIST`, `KIOSK`, `WIFI`, `CERTIFICATES`, `FILES`,
  `KNOX`, `UPDATE`, `TAK`). Its `spec` is JSONB validated by a per-type
  Pydantic schema.
- **PolicyVersion** — policies are **immutable once published**; an edit creates
  a new version. Without this you cannot answer "what was actually on that device
  in March", which is the question that matters during an incident.
- **Assignment** — binds a policy version to a target (`device` | `group` | `tag`)
  with an integer `rank`. Assignments carry either a pinned version or `latest`.
- **EffectivePolicy** — computed per device: merged result + provenance + conflicts.

### The resolver

Gather every assignment reaching a device (direct, via group, via tag), then order
deterministically:

```
rank DESC, then scope specificity (device > group > tag), then assignment_id
```

Merge **per policy type, per field**, using a strategy declared as Pydantic field
metadata — so the schema *is* the merge contract and the two cannot drift:

| Strategy | Applies to | Semantics |
|---|---|---|
| `MOST_RESTRICTIVE` | boolean allow-flags (`allow_camera`, `allow_usb`) | `false` wins — logical AND of the allows |
| `MAX` | `min_password_length`, `min_complex_chars` | numeric maximum wins |
| `MIN` | `screen_timeout_s`, `max_failed_attempts` | numeric minimum wins |
| `UNION` | blocklists, required-app sets, file sets, CA certs | set union |
| `INTERSECT` | allowlists | only what *every* allowlist permits (configurable — this one surprises people) |
| `MERGE_BY_KEY` | object lists keyed by id (apps by package, wifi by SSID) | union by key; same-key collisions resolved by rank |
| `HIGHEST_RANK` | unordered scalars (wallpaper, kiosk app, TAK server URL) | top-ranked wins, **and a conflict is recorded** |

### Provenance is a hard requirement

Every field in the effective policy carries where it came from:

```json
{
  "min_password_length": {
    "value": 8,
    "source_policy": {"id": "...", "name": "Baseline Password", "version": 3},
    "source_assignment": "...",
    "strategy": "MAX",
    "overridden": [{"value": 6, "source_policy_name": "Field Tablets"}]
  }
}
```

This is what makes stacking debuggable instead of mysterious. Build it into the
resolver from the first commit — it cannot be bolted on afterwards.

A `HIGHEST_RANK` merge that discards a *different* value is a **conflict**: surfaced
as a warning, never silently dropped.

### Dry-run

`POST /devices/{id}/effective-policy:preview` takes a hypothetical assignment set
and returns the merged result plus a diff against current. Non-negotiable for a
fleet operator about to change 300 devices.

---

## 2. Device protocol (offline-tolerant)

### Desired state, not a command queue

A device dark for three weeks must not wake to a 500-command backlog whose ordering
matters. Instead the server publishes a **declarative desired state** with a
monotonic `state_version`; the agent diffs desired vs. actual and computes its own
actions. Convergence is idempotent and order-free.

An imperative queue survives only for genuinely transient one-shots — reboot, lock,
wipe, locate, screenshot, clear-app-data — each with a TTL, dropped when stale.

### Check-in

```
POST /api/v1/devices/{id}/checkin
  { state_version, agent_version, inventory_hash, results: [...] }
→ { desired_state_version, bundle_url, transient_commands: [...] }
```

Jittered ~15 min period (WorkManager's floor anyway). FCM high-priority data
messages are a **latency optimization only** — a doorbell. Correctness never
depends on push delivery.

### Signed policy bundles

The effective policy ships as an Ed25519-signed JSON blob. The agent verifies the
signature independently of TLS. This costs little now and is precisely what makes a
future LAN-relay or sneakernet delivery path possible without redesigning anything.

### Content delivery

Every artifact is **content-addressed by sha256**. Downloads go direct from
MinIO/S3 via short-lived signed URLs with `Range` support, so a download interrupted
at 80% resumes. The agent verifies the hash before install. The API server never
proxies binaries.

---

## 3. Device Owner provisioning

In build order:

1. **`adb shell dpm set-device-owner`** — bench and development, day one.
2. **QR provisioning** — server generates the payload; operator taps the setup
   wizard welcome screen 6× to open the scanner. The practical field path.
   ```
   PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME
   PROVISIONING_DEVICE_ADMIN_SIGNATURE_CHECKSUM   (base64url SHA-256 of signing cert)
   PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_LOCATION
   PROVISIONING_ADMIN_EXTRAS_BUNDLE               { server_url, enrollment_token }
   PROVISIONING_WIFI_SSID / _PASSWORD
   PROVISIONING_LEAVE_ALL_SYSTEM_APPS_ENABLED
   ```
3. **Knox Mobile Enrollment (KME)** — Samsung's zero-touch. Upload IMEI/serials (or
   the reseller does), define a KME profile pointing at the agent APK URL plus the
   same extras bundle. Devices self-enroll on first boot or factory reset, and
   survive a wipe. Gated on the pending Knox partner account.

---

## 4. Knox strategy

Two routes to Knox controls, and the choice matters:

**(a) Knox SDK directly** — `EnterpriseDeviceManager`, `RestrictionPolicy`,
`ApplicationPolicy`, `FirewallPolicy`. Requires activating a KPE license via
`KnoxEnterpriseLicenseManager.activateLicense()`. Maximum control; binds the agent
to Samsung's SDK lifecycle.

**(b) Knox Service Plugin (KSP) via managed configuration** — KSP exposes hundreds
of Knox controls through app restrictions. EMMs normally deliver those through
managed Google Play, but **as Device Owner you can call
`DevicePolicyManager.setApplicationRestrictions(admin, "com.samsung.android.knox.kpu", bundle)`
against a sideloaded KSP APK and it works.** No managed Play account required —
which is exactly the constraint here.

**Decision: (b) primary, (a) selectively.** Note the accurate reason: the Knox SDK is
*not* being retired wholesale. Samsung deprecates individual APIs — mostly to cut
duplication with Android Enterprise — on a published clock: full support for one
year after announcement, no bug fixes after that, eligible for removal at two years.
(It is the separate *Knox Cloud* SDK that was deprecated outright.) KSP wins on
**freshness and coverage**: new Knox features reach KSP on release day, while SDK
parity lags.

Model Knox policy as a KSP restriction bundle generated from the policy spec; drop
to the SDK only for gaps, and track the deprecation clock on anything used. Everything
Samsung sits behind an `OemPolicyApplier` interface with an AOSP no-op
implementation, so the agent degrades cleanly on non-Samsung hardware. This is the
highest-risk seam in the system and it is where the dependency-inversion rule from
CLAUDE.md earns its keep.

**Offline caveat:** KPE license activation contacts Samsung's servers. Activate
during enrollment, when connectivity is under your control, and treat re-activation
failure as degraded-not-fatal.

---

## 5. App deployment (no managed Play)

- **APK** — `PackageInstaller` session, silent install under Device Owner. Pair with
  `setPermissionPolicy(AUTO_GRANT)` and `setPermissionGrantState` to pre-grant
  runtime permissions.
- **XAPK / APKS / APKM** — these are ZIP containers. **Unpack server-side**, storing
  base APK + each split as separate content-addressed artifacts plus a manifest.
  The device opens one `PackageInstaller` session, writes base + splits, commits as a
  multi-package split install. Less device CPU and storage, and the server validates
  package name, version, and signature at upload time.
- **Signature pinning** — record the signing certificate hash at upload. An update
  whose signature doesn't match the installed app *will* fail on device; catch that
  at upload and reject it there, where the error is legible.
- **`targetSdk` floor** — Android 16 blocks installing anything targeting below
  **API 24** (unchanged from Android 15). Validate at upload rather than letting it
  surface as `INSTALL_FAILED_DEPRECATED_SDK_VERSION` on a device in the field. The
  only bypass is `adb install --bypass-low-target-sdk-block`, which is useless at fleet scale.

### Hardware-specific policy surface

The XCover6 Pro's programmable **XCover / Top key** is configurable through KSP and
is the natural binding for ATAK push-to-talk. Worth modelling as a real field in the
`KNOX` policy type rather than hand-configuring per device — it is exactly the kind
of setting that motivated stackable policies in the first place.

---

## 6. File push

Spec: `[{artifact_sha256, dest_path, mode, overwrite: always|if-newer|if-absent}]`

Destinations, by how achievable they actually are:

| Destination | Feasibility |
|---|---|
| Agent's own private dir | Always works |
| Shared media (Downloads, Documents) | Works via MediaStore, no special permission |
| Arbitrary `/sdcard/...` | Needs `MANAGE_EXTERNAL_STORAGE` — see risk below |
| Another app's `/data/data/<pkg>/` | **Not possible** without root or Knox privilege |

The TAK pack rides entirely on this: ATAK data packages, `.pref` files, map source
XML, and `.p12` certs are all file pushes into `/sdcard/atak/...` — shared storage,
so no private-dir problem.

---

## 7. Identity and security

Enrollment token (short TTL, scoped to a group and policy set) travels in the QR or
KME extras bundle. On first contact the agent generates a keypair in the **Android
Keystore, hardware-backed / StrongBox** on Samsung, submits a CSR, and receives a
client certificate. Every subsequent check-in is **mTLS**.

The device identity is then non-exportable, and there is no bearer token to expire
while a device is dark for a month — which is the failure mode that matters given
the offline-tolerant requirement.

Optionally gate certificate issuance on Knox Attestation or Play Integrity to
confirm the device is genuine and unrooted.

Admin-side auth is separate and conventional (session/OIDC). Every policy change and
every command is audit-logged.

---

## 8. Stack

| Layer | Choice | Why |
|---|---|---|
| API | FastAPI (already chosen) | Keep it |
| DB | Postgres + SQLAlchemy 2.0 + Alembic | JSONB for policy specs |
| Validation | Pydantic v2 | Field metadata carries merge strategy |
| Artifacts | MinIO (S3-compatible) | Same host at this scale |
| Jobs | Postgres-backed job table, or arq | 50-500 devices does not justify Celery |
| Agent | Kotlin, WorkManager, OkHttp | Knox SDK as an optional Gradle flavor |

---

## Open risks

1. **`MANAGE_EXTERNAL_STORAGE` on Android 11+** — it is an *app-op*, not a runtime
   permission, so `setPermissionGrantState` does not grant it. Arbitrary `/sdcard`
   writes and OBB placement depend on it. The documented workaround is
   `adb shell appops set --uid <pkg> MANAGE_EXTERNAL_STORAGE allow`, which does not
   scale to a fleet. Remaining options: Knox app-op control, a preinstalled/privileged
   agent, or a one-time user tap. **This is the kind of detail that quietly consumes a
   week — validate it on real hardware early.**
2. **OBB placement** for XAPKs inherits risk #1 directly.
3. **Android 16 Advanced Protection Mode** — when a user enables it, "install unknown
   apps" is disabled and sideloading is blocked. Android Enterprise policy control
   over Advanced Protection is not arriving until **Android 17**, so on this One UI 8
   fleet it cannot be suppressed by policy. Device Owner installs go through
   `PackageInstaller` with system install privilege and *should* be unaffected by a
   user-facing "unknown sources" block — but this is **unverified and load-bearing**.
   Test it in the same hardware session as risk #1.
4. **Knox licensing timeline** — the partner application is pending and gates KME and
   KPE. Design so the AOSP path is fully functional without it; Knox is additive.
5. **`INTERSECT` on allowlists** is correct but counter-intuitive. Make it
   configurable per policy and show the resulting set in the UI before publish.
6. **Mixed SoC vendors** — Snapdragon 778G on the XCover6 Pro, MediaTek Dimensity
   9300+ on the Tab S10+. Same ABI (arm64-v8a), so no artifact-model complexity, but
   firmware-level behavior must be verified on **both** models, never just one.
