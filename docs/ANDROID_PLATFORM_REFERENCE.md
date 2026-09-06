# Android platform reference for ATLAS

**Consult this before writing or changing anything that touches provisioning, the
Device Policy Controller, app installation, permissions, or file placement.**

## Scope, honestly stated

This is **not** a copy of Android's documentation — that cannot be reproduced here
and would go stale. It is a curated record of the platform contracts that govern
*this* project, each traceable to an official source, plus what we have actually
observed on our own hardware.

Two kinds of statement appear, and they are labelled:

* 📖 **Documented** — from an official Android or Google source, linked at the end.
* ✅ **Verified here** — observed directly on `SM-X520` (Galaxy Tab S10 FE,
  Android 16 / One UI 8) or by inspecting real artifacts.

Where the two disagree, the observation wins and the disagreement is called out.
One already exists: see [Signature checksum](#signature-checksum).

⚠️ **The old package name `org.takmdm.agent` still appears below, on purpose.** The
DPC was renamed to `com.taksolutions.atlasmdm` (W34). Instructions and current
values were updated; **captured log output and `dumpsys` excerpts were not**, because
they record what a device actually printed at the time. Rewriting them would make
the evidence say something that never happened. Any `org.takmdm.*` remaining here is
history, not a stale value.

**Why this file exists.** Three factory resets were spent on a failure whose cause
is stated plainly in Android's documentation. Reasoning from symptoms lost to
reading the spec, twice in one session. Platform contracts fail vaguely on purpose
— "something went wrong" is a security decision, not an oversight — so there is
usually nothing to infer, and guessing is the expensive path.

---

## 1. Device Owner preconditions

📖 A device owner **can only be set on an unprovisioned device**. If
`Settings.Secure.USER_SETUP_COMPLETE` has ever been set, the device counts as
provisioned and device owner can no longer be established. The device must be
factory reset.

📖 No accounts may exist on the device.

**Consequences that cost real time:**

* Every failed provisioning attempt costs a full factory reset before the next.
* This is why bench work should use `adb shell dpm set-device-owner` on a
  set-up-but-accountless device: it is repeatable and yields `logcat`.

---

## 2. Provisioning methods

| Method | When to use | Notes |
|---|---|---|
| **QR code** | Field enrollment, any OEM | Six taps on the setup wizard welcome screen opens the scanner |
| **Knox Mobile Enrollment** | Samsung fleets | Survives factory reset; needs a Knox partner account (R3) |
| **Zero-touch** | Reseller-loaded devices | Requires reseller participation |
| **`adb shell dpm set-device-owner`** | **Bench and debugging** | Needs USB debugging and no accounts; the only path that gives logs |

The ADB form, which is what to reach for when provisioning misbehaves:

```
adb install -r app-debug.apk
adb shell dpm set-device-owner com.taksolutions.atlasmdm/.admin.MdmDeviceAdminReceiver
```

---

## 3. Required DPC components

**This is what broke three enrollments.** From Android 12, a DPC must declare
activities handling two actions, each carrying `BIND_DEVICE_ADMIN` so arbitrary
apps cannot launch them. 📖

Without them the system downloads the DPC, installs it, launches
`GET_PROVISIONING_MODE`, finds no handler, and aborts with a bare
"something went wrong" — no logs, after a factory reset. ✅ Observed exactly this.

### `android.app.action.GET_PROVISIONING_MODE`

```xml
<activity android:name=".admin.GetProvisioningModeActivity"
          android:exported="true"
          android:permission="android.permission.BIND_DEVICE_ADMIN">
    <intent-filter>
        <action android:name="android.app.action.GET_PROVISIONING_MODE" />
        <category android:name="android.intent.category.DEFAULT" />
    </intent-filter>
</activity>
```

📖 The system passes in `EXTRA_PROVISIONING_IMEI`,
`EXTRA_PROVISIONING_SERIAL_NUMBER`, `EXTRA_PROVISIONING_ADMIN_EXTRAS_BUNDLE`, and
`PROVISIONING_ALLOWED_PROVISIONING_MODES`.

📖 The activity **must** return `EXTRA_PROVISIONING_MODE`, one of
`PROVISIONING_MODE_FULLY_MANAGED_DEVICE` or `PROVISIONING_MODE_MANAGED_PROFILE`,
then `setResult(RESULT_OK, intent); finish()`. It may pass
`EXTRA_PROVISIONING_ADMIN_EXTRAS_BUNDLE` back through.

📖 **It must not start activities or background services** before returning to
setup.

### `android.app.action.ADMIN_POLICY_COMPLIANCE`

📖 Same declaration shape and permission. Runs after provisioning completes, in the
fully managed user.

📖 **It replaces listening for `ACTION_PROFILE_PROVISIONING_COMPLETE`.** A DPC that
does its startup work in `DeviceAdminReceiver.onProfileProvisioningComplete()` will
never run on a modern device. We had exactly this bug hiding behind the first one.

📖 Finish with `setResult(RESULT_OK, new Intent()); finish()`.

**Our decision:** a failed enrollment inside this activity still returns
`RESULT_OK`. Provisioning cannot be repeated without another factory reset, so a
network blip must not undo it; the agent retries on its own schedule.

### `DeviceAdminReceiver`

Still required, with `BIND_DEVICE_ADMIN` and a `device_admin` metadata resource.
It is the component named in `PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME`.

---

## 4. QR payload keys

📖 All keys are prefixed `android.app.extra.`.

| Key | Type | Required |
|---|---|---|
| `PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME` | String | **Always** |
| `PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_LOCATION` | String | If not pre-installed |
| `PROVISIONING_DEVICE_ADMIN_SIGNATURE_CHECKSUM` | String | If not pre-installed |
| `PROVISIONING_ADMIN_EXTRAS_BUNDLE` | Object | Optional — how config reaches the agent |
| `PROVISIONING_WIFI_SSID` / `_PASSWORD` / `_SECURITY_TYPE` | String | Recommended when the device has no network |
| `PROVISIONING_WIFI_HIDDEN` | Boolean | Optional |
| `PROVISIONING_WIFI_PROXY_HOST` / `_BYPASS` / `_PAC_URL` | String | Optional |
| `PROVISIONING_WIFI_PROXY_PORT` | Integer | Optional |
| `PROVISIONING_SKIP_ENCRYPTION` | Boolean | Optional |
| `PROVISIONING_LEAVE_ALL_SYSTEM_APPS_ENABLED` | Boolean | Optional |
| `PROVISIONING_LOCALE` / `PROVISIONING_TIME_ZONE` | String | Optional |
| `PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_COOKIE_HEADER` | String | Optional |

### Component name expansion

✅ **A leading dot expands against the package root, not the declaring class's
package.** `com.taksolutions.atlasmdm/.MdmDeviceAdminReceiver` means
`com.taksolutions.atlasmdm.MdmDeviceAdminReceiver`. Our receiver is in the `.admin`
sub-package, so the correct value is:

```
com.taksolutions.atlasmdm/.admin.MdmDeviceAdminReceiver
```

Getting this wrong installs the APK and then fails, indistinguishably from every
other provisioning failure. The server now validates the configured component
against the receivers the uploaded APK actually declares, and refuses to generate a
QR on a mismatch.

### Signature checksum

✅ **base64url, unpadded, of the SHA-256 of the signing certificate's DER
encoding.** Verified two ways: our own parser and Google's `apksigner` produce the
same hash, and Android accepted the resulting payload and installed the APK.

⚠️ A fetched summary claimed hexadecimal. That is **wrong** — our observation
supersedes it. Do not "correct" the encoding back to hex.

```
signing cert SHA-256 : 8794055894dbeb2e4c5f4931b9388478fefec331da4a2cc4e738004fe3f3580e
checksum in QR       : h5QFWJTb6y5MX0kxuTiEeP7-wzHaSizE5zgAT-PzWA4
```

Note `PROVISIONING_DEVICE_ADMIN_PACKAGE_CHECKSUM` is a *different, older* key
hashing the APK file rather than the certificate. We use the signature form, which
survives rebuilds of the same signed app.

### Download location must not need a private trust anchor

✅ **The setup wizard downloads the APK using the system trust store, before the
DPC exists.** A self-signed certificate therefore fails and provisioning dies with
no request ever reaching the server. Any CA shipped in the admin extras cannot
help: that is read by the agent, which is not installed yet.

Serving the APK over **plain HTTP** is the correct answer, not a shortcut — the
signature checksum is precisely what makes the transport untrusted-by-design.
Android verifies the download against it and rejects anything else.

---

## 5. App installation

📖✅ **Minimum installable `targetSdk` is API 24** on Android 15 *and* Android 16;
Android 16 did not increment it. Anything lower fails with
`INSTALL_FAILED_DEPRECATED_SDK_VERSION`, from any install source. The only bypass is
`adb install --bypass-low-target-sdk-block`, which does not scale.

📖 A Device Owner installs silently through `PackageInstaller` — it holds system
install privilege and does **not** pass through the user-facing "install unknown
apps" gate.

✅ Confirmed in production by the operator across commercial MDMs and Headwind on
this hardware.

**Split APKs:** write the base first, then each split, into one `PackageInstaller`
session, then commit.

**Signature pinning:** Android refuses an update whose signing certificate differs
from the installed app. Catch this at upload, where the message can say so.

### ✅ Verified on `SM-X520`: a Device Owner installs silently

`org.takmdm.testapp` was installed and then upgraded by the agent with no user
interaction at all. Android's own record is the proof:

```
installerPackageName  = org.takmdm.agent
initiatingPackageName = org.takmdm.agent
```

Both name the agent, so this was `PackageInstaller` under Device Owner privilege
rather than an `adb install`. No "install unknown apps" prompt appeared, as
documented.

✅ **Split installs verified too.** A real 7-part app (Butterfly IQ 2.49.0, an XAPK
unpacked server-side into base + 6 splits, 323 MB) installed into a single session.
Android lists every part:

```
splits=[base, config.arm64_v8a, config.en, config.xhdpi, dltools, firmware, quicktips]
```

Base is written first and the splits after, as documented above. Real ATAK 5.8.0.4
(`com.atakmap.app.civ`, 107 MB, single APK) likewise installed unattended.

✅ **v3 signing blocks parse correctly.** Both production apps are v3-signed; the
hand-written parser had only ever been exercised against v2 before.

### ⚠️ Replacing the agent kills it, and nothing restarts it

Installing over an app terminates its processes. A foreground service does **not**
come back on its own, and neither does a WorkManager periodic job soon enough to
matter: observed **25 minutes of silence** on `SM-X520` after an `adb install -r`.

📖 The fix is `ACTION_MY_PACKAGE_REPLACED`, declared in the manifest alongside
`BOOT_COMPLETED`.

✅ **Verified: a manifest-declared receiver does receive it on Android 16.**

```
BootReceiver: restarting after android.intent.action.MY_PACKAGE_REPLACED
```

⚠️ A fetched summary asserted the opposite — that `MY_PACKAGE_REPLACED` is not
exempt from the Android 8 implicit-broadcast restrictions and so would not reach a
manifest receiver. That reasoning was by analogy with `ACTION_PACKAGE_REPLACED`,
and it is wrong for this action: `MY_PACKAGE_REPLACED` is delivered **only to the
app that was replaced**, which makes it explicit rather than implicit. The
observation stands; do not "correct" it back on the strength of a general article
about background execution limits.

**Any DPC must handle this.** Without it, the first agent update silently ends
management on every device in the fleet, and the symptom at the server is
indistinguishable from a device that lost coverage.

### ✅ A Device Owner can update **itself** through `PackageInstaller`

Verified on `SM-X520` (2026-09-02): the agent was added to a policy's
`required_apps` and pushed its own newer build. The whole sequence:

```
13:01:34.490  Reconciler: upgrading org.takmdm.agent from versionCode 37 to 38
13:02:10.620  base part verified (23 303 571 bytes)          ← 36 s download
13:02:10.623  AppInstaller: session opened for org.takmdm.agent
              ← process killed at commit; no further logs from that PID
13:02:15.047  BootReceiver: restarting after MY_PACKAGE_REPLACED   ← new PID, +4.4 s
13:02:15.403  org.takmdm.agent already at versionCode 38 (want 38); skipping
13:02:15.474  sync: state=53 applied=53 errors=1               ← the 1 was unrelated
```

Four facts worth keeping:

* **The commit survives the caller's death.** Android kills the installing process
  at commit, and the install still completes.
* **The install-result callback never arrives** — the process that registered it is
  gone. So the agent records **no error** for its own upgrade; silence is success.
  Confirm by comparing `versionCode` after restart, never by waiting on the result.
* **`MY_PACKAGE_REPLACED` brings it back in ~4.4 s.** That is the whole management
  outage.
* **No update loop.** After restart the reconciler sees itself already at the
  wanted version and skips.

⚠️ **There is no rollback.** Android refuses a downgrade, so a bad agent build
cannot be reverted by re-pushing the old version — only by shipping a *new* build
with a higher `versionCode` containing the old code. And a build that crashes on
start takes remote management with it. Nothing in the platform will stop this;
the gate has to be operational.

### ✅ The same sequence through the dedicated agent-update channel

Re-verified on `SM-X520` (2026-09-02) with W27's `agent_update` offer rather than
a policy's `required_apps`. v40 → v41, no ADB:

```
14:31:19.564  Reconciler: agent update: replacing 40 with 41 (0.10.1);
                          this process is about to be killed        ← pid 18431
14:31:19.570  AppInstaller: session 124265146 opened (1 part)
14:31:20.057  VerificationCheck: Verification finished for org.takmdm.agent.
                          Result: Fail(reason=DEVELOPER_FAULT)      ← see below
14:31:22.783  Finsky VerifyApps: chooseScanResult returning verdict 0
14:31:23.149  ActivityManager: Start proc 19100 … BootReceiver      ← new PID, +3.6 s
14:31:23.556  ActivityManager: Background started FGS … code:DEVICE_OWNER
```

Server side: the device reported `agent_version_code=41`, `COMPLIANT`, with no
`compliance_detail`. Exactly **one** `agent update: replacing` line exists in the
buffer — the offer stopped on its own once the device reported the new code, with
no acknowledgement protocol.

⚠️ **`VerificationCheck … Result: Fail(reason=DEVELOPER_FAULT)` is a red herring.**
It appears mid-install and the install proceeds anyway; Play Protect's own verdict
two seconds later is `0` (allow). It reflects the debug signing key on a sideloaded
build, not a rejection. Do not treat this line as a failure — the only evidence
that matters is the `versionCode` on the next check-in.

⚠️ **A device on a pre-`agent_update` build can never be updated over the air.**
It reports no `agent_version_code`, so the gate refuses it by design. Reaching the
channel costs exactly one manual install per device, which is a one-time
migration cost and not a recurring one.

### ⚠️ The signing certificate is a one-way commitment for the life of a device

📖 Android refuses to install an update whose signing certificate differs from the
installed app's. There is no override, and Device Owner privilege does not help —
this is the check that stops an attacker replacing a privileged app.

Verified on this project (2026-09-02) at both ends:

* **The APK.** `apksigner verify --print-certs -v` on the debug and release builds
  gives different certificate digests, `8794055894dbeb2e…` (debug keystore) and
  `2094bccc054c681f…` (`CN=Michael Leckliter`, RSA-2048, v2 scheme).
* **The server refuses the upload**, before any device is involved:

  > signing certificate for org.takmdm.agent does not match the stored one
  > (have 8794055894dbeb2e…, got 2094bccc054c681f…). Android would reject this
  > update on device; upload it under a different package or remove the existing
  > package first.

Two consequences worth internalising before choosing a key:

* **Switching keys strands every device already running the old one.** The agent
  is Device Owner, so it cannot simply be uninstalled and replaced — clearing
  Device Owner requires a **factory reset**. Migration cost is a reset and
  re-enrol per device, not a re-install.
* **`EXTRA_PROVISIONING_DEVICE_ADMIN_SIGNATURE_CHECKSUM` changes with the key.**
  It is `base64url(SHA-256(signing certificate DER))`, unpadded — the same bytes
  `apksigner` prints as "certificate SHA-256 digest". Confirmed by deriving the
  deployed debug value from the debug APK and getting a byte-exact match:

  ```
  debug    8794055894dbeb2e…  →  h5QFWJTb6y5MX0kxuTiEeP7-wzHaSizE5zgAT-PzWA4
  release  2094bccc054c681f…  →  IJS8zAVMaB9G2MgSN4wHZXzzOd19ToC1RgJrd6_yxkQ
  ```

  A provisioning QR carrying the wrong checksum fails during setup with a generic
  message, so this must be changed in the same breath as the signing key.

---

### ❌ A Device Owner cannot configure the mobile hotspot

Checked against the Android 36 SDK stub and probed on `SM-X520` (2026-09-03),
because "set a default hotspot SSID and password" is an entirely reasonable thing
to expect an MDM to do.

**It is not available.** Three independent confirmations:

* **`WifiManager.setSoftApConfiguration` is not in the public SDK.** `javap` on
  `android.jar` shows only `startLocalOnlyHotspotWithConfiguration` — a temporary,
  app-scoped hotspot that shares no internet connection and dies with the caller —
  and `validateSoftApConfiguration`, which validates without setting. The real
  setter needs `NETWORK_SETTINGS` (signature|privileged).
* **`DevicePolicyManager` has nothing for it.** Its only Wi-Fi surface is the
  provisioning extras (`EXTRA_PROVISIONING_WIFI_*`, for joining a network during
  setup) and `getMinimumRequiredWifiSecurityLevel`. No tethering or SoftAP API at
  any level.
* **It is not a writable setting either.** `settings list global` on the device
  shows only `tethered_config_state`; the SSID, passphrase and band are held in
  the Wi-Fi stack's own store, not in `Settings.Global`, so the Device Owner's
  three-key `setGlobalSetting` allowance cannot reach them.

**What a Device Owner *can* do is allow or forbid it**, via user restrictions:

| Restriction | Effect |
|---|---|
| `DISALLOW_WIFI_TETHERING` | No Wi-Fi hotspot at all (API 33+) |
| `DISALLOW_CONFIG_TETHERING` | The user cannot change tethering settings |
| `DISALLOW_SHARING_ADMIN_CONFIGURED_WIFI` | The user cannot share an admin-provisioned network |
| `DISALLOW_CHANGE_WIFI_STATE`, `DISALLOW_CONFIG_WIFI`, `DISALLOW_WIFI_DIRECT`, `DISALLOW_ADD_WIFI_CONFIG`, `DISALLOW_NETWORK_RESET` | Adjacent Wi-Fi controls |

⚠️ So "set the hotspot SSID/password/band/timeout" is **not a policy this project
can implement on AOSP**. It belongs with VPN profiles and the all-files app-op in
the set of things that need a vendor layer. Samsung's `WifiPolicy` is the plausible
home — ⚠️ **unverified**, and not to be promised until the Knox SDK is in hand
(three Knox capability claims in this project have already turned out to be wrong
when checked).

---

## 5a. Removing and suppressing apps

### ⚠️ A system app cannot be uninstalled, and the platform says SUCCESS anyway

✅ Verified on `SM-X520` with Gmail (`com.google.android.gm`). Calling
`PackageInstaller.uninstall` on a preinstalled app removes **the update** and
reverts to the factory build. It does not remove the app, and the callback reports
`STATUS_SUCCESS`:

```
codePath     /data/app/~~i7dRm4g60Rnw…   →  /product/app/Gmail2
versionName  2026.08.10.963697514        →  2025.09.22.811856720
flags        [SYSTEM … UPDATED_SYSTEM_APP] → [SYSTEM …]
```

An agent trusting that status reports the app as removed while the user can still
open it. **Detect `FLAG_SYSTEM` / `FLAG_UPDATED_SYSTEM_APP` first and hide instead**,
and verify every uninstall by re-querying afterwards rather than believing the
status code.

### ✅ `setApplicationHidden` does work on system apps

⚠️ A fetched summary claimed system apps "generally cannot be hidden". **Wrong on
this hardware.** Hiding Gmail as Device Owner gave:

```
pm list packages       → absent
pm list packages -u    → present
resolve-activity       → No activity found
dumpsys                → installed=true hidden=true
```

Invisible, unlaunchable, still installed, and fully reversible. That makes hiding
the correct suppression for anything that ships with the device.

⚠️ **`setApplicationHidden` reports failure by returning `false`, not by throwing.**
Wrapping it in a `runCatching` and ignoring the result treats "refused" as "done".

### ⚠️ A hidden package is invisible to the code managing it

✅ `getPackageInfo` throws `NameNotFoundException` for a hidden package: hiding
deliberately makes an app look uninstalled. Anything reasoning about suppression
must pass **`MATCH_UNINSTALLED_PACKAGES`**, or the agent cannot see the app it hid.

Observed: Gmail stayed hidden after being taken off the blocklist, with nothing
logged, because the loop that would have unhidden it could not find it.

### ✅ `setPackagesSuspended` enforces the allowlist (`allowed_packages`)

📖 `DevicePolicyManager.setPackagesSuspended(admin, String[], boolean)` (API 24)
suspends packages for the user — a suspended app shows a "paused" dialog on tap,
its notifications are hidden, and it cannot run. Reversible. It returns the
package names it **refused**: the DPC itself, the active launcher, the package
installer / uninstaller / verifier, the default dialer and the permission
controller are all protected regardless of what is asked.

**What the agent does (W16):** `allowed_packages` ("only these may run") suspends
every **non-system user app** not on the list. System apps (launcher, dialer,
settings) are out of scope — the blocklist is for those. Required apps and the
agent are implicitly allowed. Suspensions are tracked in
`AgentConfig.suspendedByPolicy` (mirrors `hiddenByPolicy`) and released when the
allowlist changes or goes away. An **empty** resolved allowlist (an INTERSECT of
two policies that do not overlap, R4) is reported and **ignored** — not read as
"suspend everything".

✅ **Verified on `SM-X520`, full cycle:**
```
allowlist excludes org.takmdm.testapp
  → Reconciler: allowlist: suspending / dumpsys → testapp suspended=true
  → agent, ATAK, GoodNotes, the launcher and clouddpc all suspended=false
allowlist removed
  → Reconciler: allowlist: un-suspending org.takmdm.testapp / testapp suspended=false
```
Also confirmed incidentally: a **required** app is not suspended even when absent
from `allowed_packages` — `testapp` stayed usable until it was dropped from
`required_apps`, then the allowlist caught it.

---

## 6. Permissions

### Runtime permissions

📖 `DevicePolicyManager.setPermissionGrantState()` grants **runtime permissions**
(protection level `dangerous`). `setPermissionPolicy(PERMISSION_POLICY_AUTO_GRANT)`
sets the default.

### App-ops are not runtime permissions

`MANAGE_EXTERNAL_STORAGE` is an **app-op**, not a runtime permission.
`setPermissionGrantState` cannot grant it. Available routes:

| Route | Viable here? |
|---|---|
| `adb shell appops set ... allow` | Bench only; does not scale |
| Reflection into `AppOpsManager.setMode` | Needs `MANAGE_APP_OPS_MODES` (`signature|privileged`) — system or platform-signed apps only |
| Knox app-op control | Likely on Samsung; gated on the Knox licence |
| One-time user grant via `Settings.ACTION_MANAGE_APP_ALL_FILES_ACCESS_PERMISSION` | ✅ Works on stock Android; what the agent does |

✅ Headwind's source confirms the reflection path exists but sits alongside direct
`/data/system/*.xml` writes — a rooted or platform-signed deployment, not a normally
installed Device Owner.

### ⚠️ The storage permission trap

**On Android 11+, granting `WRITE_EXTERNAL_STORAGE` to an app permanently prevents
it from requesting `MANAGE_EXTERNAL_STORAGE`.**

Auto-granting every requested runtime permission is the obvious thing to do as
Device Owner, and it silently breaks exactly the apps that need all-files access —
**ATAK included**. When pre-granting, detect apps declaring
`MANAGE_EXTERNAL_STORAGE` and *skip* the legacy storage permissions for them.

(Found in Headwind's source, which works around it explicitly. Implemented in
`PolicyApplier.grantRuntimePermissions`.)

### Writing to `/sdcard`

| Destination | Reachable how |
|---|---|
| App-private (`getExternalFilesDir`) | Always |
| Media collections (Downloads, Documents) | `MediaStore`, no special permission |
| Arbitrary paths, e.g. `/sdcard/atak` | Needs all-files access |
| Another app's `/data/data/<pkg>` | Not possible without root or Knox |

ATAK config lives in `/sdcard/atak`, which is **not** a MediaStore collection.

### ✅ Verified: the agent can write into ATAK's own directories

A custom map source was pushed by policy to `/sdcard/atak/imagery` on `SM-X520` and
landed byte-identical:

```
-rw-rw---- 1 u0_a283 media_rw 388 Google_Terrain_NOPOI.xml
sha256 on device == sha256 on server
```

The directory tree was ATAK's own, created by ATAK. **This settles R1**: with
all-files access granted once at provisioning, a Device Owner agent can place files
into another app's external-storage directories. No Knox, no root.

### ⚠️ An absolute path is resolved from the filesystem root

`/atak/imagery` — the way ATAK paths are conventionally written — is **not**
`/sdcard/atak/imagery`. It resolves from `/`, where nothing is writable, and the
failure surfaces as a permission error that says nothing about the real mistake.

Only `/sdcard/...` and `/storage/emulated/0/...` reach external storage; a relative
path is resolved against it. The server now rejects anything else when the policy is
published, and names the path that would have worked.

### ✅ Zip extraction works into the same directories

A DTED archive extracted by policy into `/sdcard/atak/DTED`, ~104 MB unpacked, with
entry hashes matching the archive. Zip-slip is guarded by canonicalising each entry
against the destination root.

⚠️ Archives built on macOS carry `__MACOSX` resource forks and `.DS_Store`, which
extract alongside the data unless filtered. Most ATAK data packages are zipped on a
Mac, so this is the normal case rather than the exception.

### ❌ Verified: the agent cannot write another app's `Android/obb/` (R2)

The [Manage all files](https://developer.android.com/training/data-storage/manage-all-files)
doc says `MANAGE_EXTERNAL_STORAGE` does **not** grant access to "`/Android/data/`,
`/sdcard/Android`, and most subdirectories of `/sdcard/Android`" — without naming
`Android/obb` either way, and it has flip-flopped across releases. A `probe_obb`
debug action (`DebugConfigReceiver`) settled it on `SM-X520`:

```
I DebugConfigReceiver: obb probe /sdcard/Android/obb/org.takmdm.testapp ->
  FAILED: FileNotFoundException: .../atlas_obb_probe.txt: open failed: EACCES (Permission denied)
```

The agent had all-files access — the same grant that makes `/sdcard/atak` writable
(✅ above). Writing **another app's** `Android/obb/<pkg>/` is still blocked. There
is no all-files route around it; the remaining routes are Knox or root, neither of
which a normally-installed Device Owner has.

**Consequence for XAPKs:** an XAPK unpacks server-side into base + splits + OBB,
but the agent can only place the APK parts. It installs, then the app fails at
runtime with its expansion assets missing. `Reconciler.reconcileApps` raises an
apply_error naming the package rather than skipping the OBB silently, and the Apps
page flags a package that carries one.

✅ **The apply_error path is verified on `SM-X520`** (2026-09-02): an XAPK carrying
an OBB was assigned, the agent logged `errors=2` and raised *"…needs an OBB
expansion file, which a Device Owner cannot place on this device…"*, and the
device went **DEGRADED** with that text in `compliance_detail`. ⚠️ That test used a
**synthetic** XAPK from `tests/apk_fixtures.py::build_xapk(with_obb=True)`. It
proves the error path, not that any real package needs it — see below.

⚠️ **No package this project deploys actually carries an OBB** (checked
2026-09-02, by reading the files rather than assuming):

* **ATAK** (`ATAK-5.8.0.4-174b425-civSmall-release.apk`) is one self-contained
  APK — 112 MB, 4 637 entries, **no** OBB and no trace of Google's expansion-file
  downloader library. Its bulk is native geospatial code: `lib/` 128 MB
  (`libgdal.so` 35 MB, `libtakengine.so` 25 MB, `libspatialite.so` 18 MB),
  `assets/` 38 MB, `res/` 17 MB, three dex files 22 MB. Native libraries *must*
  live inside the APK, so an OBB was never available to them. The map and imagery
  data that would be expansion content in a consumer app is pushed at runtime into
  `/sdcard/atak/…` instead — the path a Device Owner **can** write (✅ R1 above).
* **`butterfly-iq-2.49.0.xapk`** has no OBB either. It is base + splits, three of
  them large *feature* splits (`dltools` 112 MB, `quicktips` 76 MB, `firmware`
  45 MB). Splits install normally.

So R2 is a real platform limitation with, so far, **no known package that
triggers it**. Failing loudly stays correct — an app installing "successfully"
and then failing at runtime on missing assets looks like an app bug, not an MDM
one — but this is not blocking any current deployment, and it is a weak argument
for Knox on its own.

Re-run `probe_obb` on the Qualcomm (`SM-G736U1`) and MediaTek (`SM-X828U`) devices
before assuming the underlying EACCES holds there (R5).

---

## 6a. AndroidKeyStore and signing

✅ **`AndroidKeyStore` does not provide `Signature` implementations.** It supplies
`KeyStore`, `KeyPairGenerator` and `KeyFactory`; the signing algorithms for
keystore-held keys live in a *separate* provider named
**`AndroidKeyStoreBCWorkaround`**.

Naming the provider explicitly therefore fails:

```
OperatorCreationException: cannot create signer:
no such algorithm: SHA256WITHECDSA for provider AndroidKeyStore
```

**Do not set a provider** when signing with a keystore key. Leave it unset and let
JCA's *delayed provider selection* choose at `initSign()` time from the key itself:

```kotlin
// Right: provider resolved from the key
JcaContentSignerBuilder("SHA256withECDSA").build(keyPair.private)

// Wrong: AndroidKeyStore has no Signature implementations
JcaContentSignerBuilder("SHA256withECDSA")
    .setProvider("AndroidKeyStore")
    .build(keyPair.private)
```

The instinct to pin the provider is reasonable — the key is non-exportable, so the
operation *must* happen inside the keystore — but it is the pinning itself that
breaks it.

This cost several enrollments and was invisible without on-device diagnostics: the
agent failed before any network call, so the server saw nothing at all. If an agent
never contacts the server, suspect the identity and CSR path before the transport.

## 6a-ii. Device serial: `Build.getSerial()`

✅ **A Device Owner holding `READ_PHONE_STATE` gets the real serial on Android 16.**
Verified on `SM-X520` by testing both states on the device:

```
READ_PHONE_STATE granted=false → SecurityException:
    "getSerial: The uid 10311 does not meet the requirements
     to access device identifiers."
READ_PHONE_STATE granted=true  → 'R5GL40MMHRN'   (matches ro.serialno)
```

⚠️ **This contradicts the widely repeated claim** — including from a summary fetched
during this work — that Android 10+ requires the `signature|privileged`
`READ_PRIVILEGED_PHONE_STATE` and that ordinary `READ_PHONE_STATE` is insufficient.
That is true for a *normal* app. A **device owner** is separately privileged, and
the ordinary runtime permission is enough. The observation stands; do not "correct"
this back on the strength of a general article about Android 10.

**It throws rather than returning `UNKNOWN`,** so any caller must catch. Code that
only checks for `Build.UNKNOWN` will take its fallback path via an exception it
never expected.

### The fallback is not equivalent, and the difference is silent

📖 `Settings.Secure.ANDROID_ID` **"may change if a factory reset is performed on the
device or if an APK signing key changes."** It is scoped per app-signing-key, per
user, per device.

That makes it unusable as a device identity for re-enrolment matching (D24), because
**a factory reset is exactly when re-enrolment happens**. A device that enrols on the
fallback gets a new identity after every wipe, so the server sees a new device and
the old record is orphaned along with its group membership and policy stack.

✅ Observed: one `SM-X520` holds two records, `SM-X520-421929662296025e` and
`SM-X520-6e5d7b239e5d39c3` — two ANDROID_IDs from two provisioning rounds.

**Grant `READ_PHONE_STATE` before enrolling, and treat the fallback as a degraded
state worth reporting**, not as an equivalent alternative.

## 6a-iii. StrongBox: where the device key actually lives

✅ **`SM-X520` (Galaxy Tab S10 FE, Exynos 1580) has no StrongBox.** Asked of the key
itself rather than inferred:

```
device key -> TRUSTED_ENVIRONMENT (TEE), insideSecureHardware=true
StrongBox present on this device = false
```

The feature list agrees — `android.hardware.hardware_keystore=300` is advertised,
`android.hardware.strongbox_keystore` is not.

**The security property that matters holds.** The key is inside secure hardware, so
it is non-exportable and the private key never reaches userspace. D56's fallback
behaved exactly as designed: StrongBox attempted, TEE used, and never a silent drop
to a software key.

### How to ask

`KeyInfo.getSecurityLevel()` (API 31+) is the **only** call that distinguishes
StrongBox from the TEE. `isInsideSecureHardware()` answers a different and weaker
question — "not software" — and cannot tell the two apart, so it is useless for this.

```kotlin
val info = KeyFactory.getInstance(key.algorithm, "AndroidKeyStore")
    .getKeySpec(key, KeyInfo::class.java)
info.securityLevel   // SECURITY_LEVEL_STRONGBOX / _TRUSTED_ENVIRONMENT / _SOFTWARE
```

⚠️ **Do not extrapolate to the rest of the fleet (R5).** This is one model on one
SoC. `SM-G736U1` (Snapdragon 778G) and `SM-X828U` (Dimensity 9300+) are different
silicon from different vendors and must each be asked. A device that *does* have
StrongBox will use it automatically — nothing in the agent needs changing.

## 6b. Reading logs, and why we do not use `logcat`

📖 **`READ_LOGS` has been restricted since Android 4.1 (API 16).** Only privileged
system apps — firmware-signed or in the privileged system image — can hold it. A
normally-installed Device Owner cannot, and no `DevicePolicyManager` call grants it.

⚠️ **Whether an unprivileged app can still read back its *own* lines is unresolved.**
It is widely believed that `logd` filters by UID and therefore returns your own
entries. Official documentation does **not** say so; the page below implies the
opposite, that `READ_LOGS` gates logcat access outright. This was checked
specifically because the belief was about to become load-bearing. **Do not build on
it without testing on hardware first.**

📖 Android's own recommendation settles the design question regardless:

> "Avoid logging to `logcat`. If you need more detailed logs, **use internal storage
> and manage your own logs directly**, instead of using the system log."

**What we do (D87):** the agent keeps its own size-capped ring log in internal
storage and tees to `logcat` as well, so `adb logcat` still works when a cable is
available but nothing depends on reading it back. Redaction is ours to control,
which matters because these logs leave the device when an operator collects them.

### The Device Owner audit channel, which is a different thing

📖 `setSecurityLoggingEnabled()` / `retrieveSecurityLogs()` /
`DeviceAdminReceiver.onSecurityLogsAvailable()`, plus
`retrievePreRebootSecurityLogs()` for the previous boot cycle (check for duplicates
across the two). Device-owner only, and **only on fully managed devices with a
single user or affiliated users** — which describes this fleet.

This is a structured audit stream of system events, **not** the agent's own
diagnostics, and it will not carry an agent stack trace. Useful for compliance
later; it does not replace §6b. Not yet implemented.

## 6c. `DevicePolicyManager` API levels that bite

Verified against the official reference rather than recalled — a version branch
written from memory named the wrong API level for `wipeDevice` and **would not have
compiled**.

| Member | API | Notes |
|---|---|---|
| `wipeData(int)` | 14 | **Deprecated at 26.** Do not use. |
| `wipeData(int, CharSequence)` | 26 | Current. The reason is shown to whoever holds the device. **This is the one to call.** |
| `wipeDevice(int)` | **37** | ⚠️ Does **not** exist against `compileSdk 36`. Calling it is a compile error, not a runtime fallback. |
| `reboot(ComponentName)` | 24 | Throws if a call is active. |
| `lockNow()` | 8 | Device *or* profile owner. |
| `clearApplicationUserData(ComponentName, String, Executor, listener)` | **31** | Asynchronous — await the callback. Returns `false` for a package that is not installed, which is exactly the case an operator is checking. |
| `WIPE_EXTERNAL_STORAGE` | 14 | Separate act on Samsung devices with a card. |
| `WIPE_RESET_PROTECTION_DATA` | 26 | Also clears factory reset protection. |
| `setPasswordHistoryLength(admin, n)` | 8 | ⚠️ **Not deprecated** with the `setPasswordMinimum*` family at API 31 — history length has no complexity-bucket equivalent, so it still applies directly. ✅ Verified on `SM-X520`: policy `history_length: 6` → `dumpsys device_policy` shows `passwordHistoryLength=6`. |
| `setSystemSetting(admin, key, value)` | 28 | Device Owner only. **Exactly three keys** allowed: `Settings.System.SCREEN_BRIGHTNESS`, `SCREEN_BRIGHTNESS_MODE`, `SCREEN_OFF_TIMEOUT` — anything else throws. Value is a string; `SCREEN_OFF_TIMEOUT` is milliseconds. Applies even under `DISALLOW_CONFIG_SCREEN_TIMEOUT`. ✅ Verified on `SM-X520`: policy `screen_timeout_seconds: 45` → `settings get system screen_off_timeout` returns `45000`. |
| `setGlobalSetting(admin, key, value)` | 21 | Device Owner only, **mostly deprecated**. Fixed whitelist: `ADB_ENABLED`, `USB_MASS_STORAGE_ENABLED`, `STAY_ON_WHILE_PLUGGED_IN`, `WIFI_DEVICE_OWNER_CONFIGS_LOCKDOWN` — anything else throws `SecurityException`. |

All of the above except `lockNow` require **device owner**, and the failure without
it is a `SecurityException` whose message does not mention device ownership.

### ❌ A Device Owner cannot set the OS "Device name" (W24)

`Settings > About phone > Device name` is `Settings.Global.DEVICE_NAME`.

* `dpm.setGlobalSetting(admin, "device_name", …)` — **`DEVICE_NAME` is not on the
  whitelist**, so it throws.
* A direct `contentResolver` write needs `WRITE_SECURE_SETTINGS`
  (`signature|privileged|development`) — a Device Owner **cannot self-grant** it
  (`setPermissionGrantState` reaches only `dangerous` runtime permissions). Only
  `adb shell settings put global device_name …` works, because adb shell holds it.
* Commercial MDMs (ManageEngine, Hexnode) hit the same wall — their "device name"
  shows only in their own console, not in Android Settings.

The nearest achievable thing is `BluetoothAdapter.setName()` (needs
`BLUETOOTH_CONNECT`, which a DO *can* grant) — it changes the Bluetooth broadcast
name, not the About-phone name.

⚠️ **Correction (2026-09-02): Knox does not fix this either.** W24 recorded this as
"deferred to Knox"; a read of the Knox SDK reference says otherwise. There is no
`setDeviceName` anywhere in the SDK, `RestrictionPolicy` has no device-name setter,
and `custom.SettingsManager` is an allow-list of ~40 predefined toggles that
**cannot write arbitrary secure/global settings**. Device naming and branding are a
**Knox Configure** feature — a separate Samsung provisioning product, not KPE or the
SDK. See [KNOX.md](KNOX.md). The ATLAS friendly name therefore lives in the console
and on the ATLAS MDM app's Device tab, and that is the end state unless Knox
Configure is ever brought in.

### Network data usage: read freely, enforce not at all (W43)

Assessed against the SDK source before building the category, because an MDM
screen full of "block mobile data" controls is worth nothing if the platform has
no such call. The answer splits cleanly, and the two halves are worth keeping
apart in your head.

#### ✅ Reading usage is free for a Device Owner — no grant, no prompt

📖 `NetworkStatsManager`'s class javadoc, verbatim:

> Calling `querySummaryForDevice` or accessing stats for apps other than the
> calling app requires the permission `PACKAGE_USAGE_STATS`, which is a
> system-level permission and will not be granted to third-party apps. […]
> Profile owner apps are automatically granted permission to query data on the
> profile they manage […] **Device owner apps and carrier-privileged apps
> likewise get access to usage data for all users on the device.**

This is the rare case that goes *our* way. A normal app has to send the user into
Settings → Special access for `PACKAGE_USAGE_STATS`; our agent is a Device Owner
and simply gets it, for every app on the device. Total and per-UID usage, split by
transport (mobile vs Wi-Fi) and by time bucket, is all available.

✅ **Verified on `SM-X520` (One UI 8 / Android 16, agent v51), 2026-09-05.** The
agent read **552.5 MB** of device total data with `PACKAGE_USAGE_STATS`
**never granted** — no prompt, no Settings visit, no Usage-access toggle:

```
I/DataUsage: data usage warning raised: device total_data monthly 1MB at 552.5 MB
I/SyncService: sync: state=3 applied=3 errors=0
```

So the Device Owner exemption is real on Samsung's firmware, not just in AOSP's
javadoc. `querySummaryForDevice` returned a live bucket rather than the null that
would have meant "you may not have this". The `PACKAGE_USAGE_STATS` declaration in
the manifest is therefore belt-and-braces, not load-bearing.

#### ❌ Enforcing a data restriction is not available at all

There is **no** Device Owner API to block Wi-Fi data, block mobile data, block all
connections, or cut one app off the network.

| Candidate | Why it is not the answer |
|---|---|
| `UserManager.DISALLOW_CONFIG_WIFI`, `DISALLOW_CHANGE_WIFI_STATE`, `DISALLOW_CONFIG_MOBILE_NETWORKS` | These govern **configuration** — whether the *user* may change the setting. Data keeps flowing. |
| `DISALLOW_DATA_ROAMING` | Genuinely blocks data, but **only while roaming**. Not a general lever. |
| `NetworkPolicyManager.setUidPolicy(uid, POLICY_REJECT_METERED_BACKGROUND)` | **The exact API Settings uses** for per-app "restrict background data" — and it is `@hide` plus `@SystemApi(client = MODULE_LIBRARIES)`. Unreachable by a normally-installed DO, Device Owner privilege included. |
| `setPackagesSuspended` | Suspends the whole app, not its network. A blunt instrument for a different job. |
| `setAlwaysOnVpnPackage(..., lockdownEnabled = true)` | Can black-hole *all* traffic, but needs a VPN client app and cannot tell Wi-Fi from mobile. |

**The answer is Knox `net.firewall.Firewall`** — per-app and device-wide
allow/deny, already assessed in [KNOX.md](KNOX.md) §4.1 as "the single biggest
win" and already scheduled as Chunk 7 step 4. Commercial MDMs showing per-app data
blocking on Samsung are doing it there, not in AOSP.

**Consequence for the console:** the NETWORK_DATA_USE spec carries the blocking
fields, renders them disabled with a "needs Knox" badge, and **refuses to store a
value for them**. A control that saves and does nothing is worse than one that is
visibly unavailable.

#### How to actually call the stats API (W44)

⚠️ **The non-deprecated overloads are not available to us.** `querySummaryForDevice`
and `queryDetailsForUid` each have a `NetworkTemplate` form and an `int networkType`
form. The `NetworkTemplate` ones are `@SystemApi(client = MODULE_LIBRARIES)`, so an
ordinary app — Device Owner included — **must** use the `int` form, whose
`ConnectivityManager.TYPE_MOBILE` / `TYPE_WIFI` constants are themselves marked
deprecated. Deprecated *and* mandatory at the same time. Do not "modernise" these
calls to the template overloads; they will not compile against the public SDK.

| Rule | Source |
|---|---|
| `subscriberId` is *"guarded by additional restrictions"* from API 29. Callers without privileged access *"can provide a `null` value when querying for the mobile network type to receive usage for all mobile networks"*. | `querySummaryForDevice` javadoc |
| Both queries are `@WorkerThread` — *"This may take a long time, and apps should avoid calling this on their main thread."* | same |
| Returns *"Bucket object or **null** if permissions are insufficient or error happened during statistics collection."* | same |
| Iteration is `hasNextBucket()` / `getNextBucket(bucket)` and the `NetworkStats` must be `close()`d. | `NetworkStats` |

⚠️ **A `null` return is not zero bytes.** It is the API saying "you may not have
this", which is exactly what would happen if the Device-Owner-gets-it-free claim
above turned out to be wrong on Samsung's firmware. The agent reports a null as an
apply error rather than recording 0 MB used — a data cap that silently reads zero
forever would never fire, and would look identical to a device using no data.

### ⚠️ A notification channel's importance cannot be raised (W44)

📖 `createNotificationChannel`, verbatim:

> This can also be used to restore a deleted channel and to update an existing
> channel's name, description, group, and/or importance.
> […]
> **The importance of an existing channel will only be changed if the new
> importance is lower than the current value** and the user has not altered any
> settings on this channel.

So importance ratchets **downwards only**. Shipping a channel too quiet and fixing
it later is not a code change — the fix is a no-op on precisely the devices that
already ran the old build.

📖 Deleting it first does not help either:

> If you create a new channel with this same id, the deleted channel will be
> **un-deleted with all of the same settings** it had before it was deleted.

✅ **The only route is a new channel id**, then deleting the old one so the app's
notification settings do not show a dead duplicate.

**Cost us a real diagnosis.** v51 posted data-usage warnings to an
`IMPORTANCE_DEFAULT` channel. That does not raise a heads-up over a fullscreen
app, so the warning went straight to the shade and was reported as "no
notification" — with the agent log proving it had posted correctly all along.
v52 moved to `takmdm_data_usage_v2` at `IMPORTANCE_HIGH`.

⚠️ **Pick the importance when the channel is born**, and assume you get one
chance. A warning nobody sees is the same as no warning.

### Operator-facing text: support messages and lock-screen info (W42)

📖 Read from `sources/android-36.1/android/app/admin/DevicePolicyManager.java`
(the SDK source shipped with the platform), not from a summary. All three are
API 24+, so far below this project's `minSdk 33`.

| API | What it does, verbatim from the javadoc | Limits |
|---|---|---|
| `setShortSupportMessage(admin, message)` | *"This will be displayed to the user in settings screens where functionality has been disabled by the admin."* The doc's own example is *"This setting is disabled by your administrator. Contact someone@example.com for support."* | *"If the message is longer than 200 characters it may be truncated."* `null` clears. `SecurityException` if `admin` is not an active administrator. |
| `setLongSupportMessage(admin, message)` | *"This will be displayed to the user in the device administrators settings screen."* | *"If the message is longer than 20000 characters it may be truncated."* `null` clears. |
| `setDeviceOwnerLockScreenInfo(admin, info)` | *"Sets the device owner information to be shown on the lock screen."* | Device owner only (or PO of an org-owned device); `SecurityException` otherwise. |

⚠️ **`setDeviceOwnerLockScreenInfo` takes the field away from the user**, which
the other two do not: *"Device owner information set using this method overrides
any owner information manually set by the user and **prevents the user from
further changing it**."* Its clearing behaviour is correspondingly particular:

* `null` **or empty** → *"the device owner info is cleared and the user owner info
  is shown on the lock screen if it is set"* — i.e. the user gets the field back.
* **whitespace only** → *"the message on the lock screen will be blank and the
  user will not be allowed to change it."*

So "" and " " are **not** the same instruction: one hands the field back, the
other holds it blank. The agent normalises a blank spec value to `null` for
exactly this reason — an operator clearing a text box means "stop managing it",
never "hold it blank forever".

⚠️ **All three latch** and belong to the family below: whatever was last written
stays until something writes over it, and survives the policy that set it being
unassigned. So `applyCustomizations` runs even when the section is absent, pushing
`null`. Unlike the `setPasswordMinimumLength` trap (W41), all three accept `null`
in any state, so there is no quality-style gate to satisfy first.

📖 Localization is the DPC's job for all three: *"it is the responsibility of the
DeviceAdminReceiver to listen to the ACTION_LOCALE_CHANGED broadcast and set a new
version of this string accordingly."* ATLAS does not do this — the operator's
message is stored and pushed as written, in whatever language they typed it.
Recorded so it is a known omission rather than a surprise.

### Passcode: the granular `setPasswordMinimum*` family (W18)

📖 `setPasswordQuality`, `setPasswordMinimumLength`, `setPasswordMinimumLetters`,
`setPasswordMinimumNumeric`, `setPasswordMinimumSymbols` are all marked
`@Deprecated` (Android 12) in favour of `setRequiredPasswordComplexity`, which
offers only four buckets (NONE / LOW / MEDIUM / HIGH) with **no per-character-class
control**. But the deprecation note is explicit:

> Company-owned devices (fully-managed and organization-owned managed profile
> devices) are able to continue using this method.

So a Device Owner may still use the granular family, and the agent does (W18) —
it maps 1:1 onto the `PASSWORD` spec, which the complexity buckets do not.

| Rule | Source |
|---|---|
| `setPasswordMinimum{Letters,Numeric,Symbols}` **throw `IllegalStateException`** for an app targeting API 30+ unless `setPasswordQuality(PASSWORD_QUALITY_COMPLEX)` was called first. Default value of each is 1. | `setPasswordMinimumLetters` reference |
| ✅ **`setPasswordMinimumLength` throws too — the reference docs above don't say so, but the platform does.** It requires quality **at least `NUMERIC`** (`131072`), **even when the value being set is 0.** Hit on a freshly imaged `SM-X520` with *no policy ever applied*: `IllegalStateException("password quality should be at least NUMERIC for setPasswordMinimumLenght")` (AOSP's own typo, not ours) — thrown by the agent's own R14 release-to-permissive call, on the very first sync, because quality was still `UNSPECIFIED`. Fixed by gating the call the same way the char-class family is gated, just at `NUMERIC` instead of `COMPLEX` (`PasswordPlan.minLengthApplies`). Not yet re-verified on hardware — next enrolment of a fresh device should confirm the error is gone. | Observed on-device, 2026-09-05; not in the setter's own reference page |
| `setPasswordQuality` **clears** any complexity set via `setRequiredPasswordComplexity` (on the primary instance, for a DO, it just clears — no throw). Don't mix the two APIs. | `setPasswordQuality` reference |
| `setPasswordQuality` on the **parent** `DevicePolicyManager` instance throws `IllegalArgumentException` for an app targeting API 31+ (except a PO on an org-owned device). The agent only ever calls the primary instance. | `setPasswordQuality` reference |
| The calling admin needs `USES_POLICY_LIMIT_PASSWORD` in its `device_admin.xml` (`<limit-password />`). Already declared. | `setPasswordMinimumLetters` reference |

**What the agent does** (`PasswordPlan.effectiveQuality` + `PolicyApplier.applyPassword`):
derives the quality to enforce as the strictest of the `quality` field, `NUMERIC`
if a `min_length` is set, and `COMPLEX` if any `min_letters`/`min_digits`/
`min_symbols` is set; calls `setPasswordQuality` first, then the length and
per-character-class setters. `history_length` / expiry / lockout are unchanged.

### Forcing an exact passcode: `resetPasswordWithToken` (W20)

📖 A Device Owner sets a specific screen-lock passcode with
`resetPasswordWithToken(admin, password, token, flags)` (API 26+). The token
comes from `setResetPasswordToken(admin, token)` — **≥32 bytes, from a CSRNG**.

| Rule | Source |
|---|---|
| The token **activates immediately only if the device has no passcode.** If one is already set, the user must complete a confirm-credential operation (`KeyguardManager.createConfirmDeviceCredentialIntent`) before it works — this **cannot be forced**. | `setResetPasswordToken` reference |
| An un-activated token is **held in memory only and lost on reboot**; a fresh one must be provisioned. An activated token survives reboots and password changes. | `setResetPasswordToken` reference |
| The new passcode must satisfy the active `getPasswordQuality` / `getPasswordMinimumLength` or `resetPasswordWithToken` **returns `false`**. So set the quality/length constraints first. | `resetPasswordWithToken` reference |
| **There is no AOSP API to stop the user changing the passcode.** "Once provisioned and activated, the token will remain effective even if the user changes or clears the lockscreen password" — the DPC's only remedy is to set it back. | `setResetPasswordToken` reference |
| `flags`: `RESET_PASSWORD_REQUIRE_ENTRY` locks the device so the user must enter the new passcode; `0` sets it silently. | `resetPasswordWithToken` reference |
| The token is credential-grade — "NEVER store this token on device in plaintext". | `setResetPasswordToken` reference |

**What the agent does** (`PolicyApplier.ensurePasswordSet`, W20): generates a
32-byte token, keeps its base64 in the agent's private prefs (same store as the
enrolment secret — the pragmatic choice for a normally-installed DO; noted as an
exposure alongside R8/R12), `setResetPasswordToken` when not already active,
reports the confirm-credential requirement rather than working around it, then
`resetPasswordWithToken(admin, desired, token, 0)`. **Re-asserted on every
reconcile** — since the user can change it, setting it back each sync is the
enforcement. Flags `0`: a kiosk device in use is not kicked to the lock screen
when the agent re-applies an unchanged passcode.

✅ **Verified on `SM-X520` (agent v36), full cycle:**
* Fresh device (no passcode) + `set_password: atlas1234` → `PolicyApplier: passcode
  set from policy (9 chars)`, `sync … errors=0`, `locksettings verify --old
  atlas1234` → *"Lock credential verified successfully"*. The token activated
  immediately (no existing passcode), as documented.
* User changed the passcode (`locksettings set-password`) → the next sync
  re-asserted it: `atlas1234` verified again, the user's value rejected.
* `set_password` removed from the policy → the agent stopped re-asserting and
  **did not clear** the passcode (scalars are not reverted — W15). Clearing a
  forced passcode still needs the constraints relaxed first; noted as a gap.

⚠️ The internal `resetPasswordWithToken` call logs a full stack trace under
`ActivityManager E` / `LsLogVerify W` — this is the platform's own audit logging
of the reset, **not** an agent error.

### ⚠️ These setters latch — absent must be pushed as permissive

There is no "unset" call in the granular family. Whatever was last written stays
in force until something writes over it, and it survives the policy that put it
there being removed entirely.

✅ **This caused a real failure on `SM-X520`** (2026-09-02): a `min_length: 13`
from a policy that no longer applied kept `minimumPasswordLength=13` latched, so
a later policy's 4-digit `set_password` was rejected by `resetPasswordWithToken`
— and nothing in the console could clear it.

**The rule:** a DPC must drive every one of these to a definite value on every
reconcile, pushing the permissive value when the field is absent —
`setPasswordQuality(UNSPECIFIED)`, `setPasswordMinimumLength(0)`,
`setPasswordHistoryLength(0)`, `setPasswordExpirationTimeout(0)`,
`setMaximumTimeToLock(0)`, `setMaximumFailedPasswordsForWipe(0)`. That last one
matters most: a stale attempt limit means a device can wipe itself to satisfy a
policy nobody has assigned to it for months.

The per-character-class minimums are the exception — they throw below
`PASSWORD_QUALITY_COMPLEX`, so only touch them when the effective quality *is*
COMPLEX. Below it they are inert, so nothing latched there can bite.

✅ Verified both ways on `SM-X520` (agent v39): adding `min_length: 4` set
`minimumPasswordLength=4`; removing it returned the device to `0`.

⚠️ **Correction, 2026-09-05: `setPasswordMinimumLength(0)` is not safe to push
unconditionally either.** It turns out to belong with "the per-character-class
minimums are the exception" above, just at a lower bar — it throws below
`NUMERIC` rather than below `COMPLEX`, for a release-to-0 exactly as much as for
a real value. A freshly imaged device with no policy at all is `UNSPECIFIED`, so
the R14 release call was itself throwing on the very first sync a device ever
did. Same fix shape as the char-class family: only call it when quality is at
least `NUMERIC` (`PasswordPlan.minLengthApplies`); below that a stale length is
inert, so nothing latched there can bite either. Not yet re-verified on
hardware.

#### ⚠️ `setSystemSetting(SCREEN_OFF_TIMEOUT)` latches too, and has **no permissive
value** to push

Verified on `SM-X520` (2026-09-03). The device sat at its default `1800000`; a
policy set `45000`; **removing that policy left it at `45000`**, with the device
converged and compliant. Nothing but a re-push or a manual
`adb shell settings put system screen_off_timeout` moves it back.

Same latch as the password minimums, **different fix**. A password minimum has a
permissive value — `0` — so writing it on every reconcile is both correct and
complete. A screen timeout does not: what "no policy" should mean is *the user's
own setting*, which the platform will not hand back and which nothing records
before the first overwrite.

So an MDM that writes this setting has to capture the prior value itself, before
its first write, if it ever intends to release it. Driving it to a fixed default
instead would silently overwrite a user preference the operator never asked to
change.

⚠️ **And the release has to run when no policy is present at all.** The obvious
shape — apply a section only when the desired state carries one — means the code
that undoes a latched setting never executes, because removing the last policy of
that type removes the section too. Verified the hard way on `SM-X520`: an agent
that remembered the displaced value correctly still failed to restore it, for this
reason alone. A section whose setters latch must be applied with an empty document
rather than skipped.

### ✅ Verified on `SM-X520` (agent v34), both directions:

| Policy | `dumpsys device_policy` for `org.takmdm.agent` |
|---|---|
| `{min_length: 13}` | `passwordQuality=0x20000` (NUMERIC), `minimumPasswordLength=13` |
| `{min_length: 13, quality: 6, min_digits: 2}` | `passwordQuality=0x60000` (COMPLEX), `minimumPasswordLength=13`, `minimumPasswordNumeric=2` |
| back to `{min_length: 13}` | `passwordQuality` fell to `0x20000`, `minimumPasswordNumeric` back to the `1` default |

`sync: … applied=N errors=0` on every step. The pre-W18 path set
`mPasswordComplexity` (a bucket) and left `minimumPasswordLength=0`; the granular
path leaves `mPasswordComplexity=0` and sets the real minimums, as expected.

### Screenshot is not available to a Device Owner

There is no `DevicePolicyManager` call that captures the screen. `MediaProjection` is
the only route and it requires interactive user consent, which defeats the point of
a remote command on an unattended device. The agent registers a handler that
**reports this as unsupported** rather than leaving the type unhandled — an
unregistered type is retried until the queue expires and reads as a device fault
(D89).

## 6d. Wi-Fi configuration by a Device Owner

📖 `WifiManager.addNetwork(WifiConfiguration)` and the sibling config methods
(`updateNetwork`, `removeNetwork`, `enableNetwork`, `getConfiguredNetworks`) are
**deprecated at API 29** for ordinary apps — a normal app gets `-1` back from
`addNetwork` and an empty list from `getConfiguredNetworks`. The deprecation note
carves out an exception: **"except for Device Owner (DO), Profile Owner (PO) and
system apps"**, which retain access and may modify or remove only the networks
they themselves created.

**What the agent does (W14):** `PolicyApplier.applyNetworks` builds one
`WifiConfiguration` per `wifi_networks` entry, security mapped from the policy
enum (`NONE` / `WEP` / `WPA_PSK` / `SAE`), calls `addNetwork` then
`enableNetwork(id, false)`. SSIDs it added and the policy later dropped are
`removeNetwork`'d — a network the user set up by hand is never touched.

✅ **`addNetwork` works for the Device Owner on `SM-X520` (One UI 8 / Android 16).**
A `NETWORKS` policy pushed a `wpa_psk` network and the agent logged
`wifi: configured ATLAS-Test (wpa_psk, id=1)`; `cmd wifi list-networks` then
listed it. So the deprecation carve-out is real on this Samsung build — no need
for the weaker `addNetworkSuggestions` fallback. A `-1` return is still reported
(`wifi <ssid>: addNetwork returned -1 …`) rather than swallowed, in case another
OEM behaves differently (R5).

⚠️ **`getConfiguredNetworks()` returns nothing for the Device Owner** on this
build, even though `addNetwork` works — so the network id handed back at add time
is the only reliable handle for `removeNetwork` later. The agent stores it
(`AgentConfig.wifiNetworkId`); a first version that looked the id up via
`getConfiguredNetworks` logged a successful removal while the network stayed
configured.

✅ **The full cycle is verified on `SM-X520`.** Assigning the policy:
`wifi: configured ATLAS-Test (wpa_psk, id=2)`, network listed. Unassigning it:
`wifi: removing ATLAS-Test (id=2, removed=true)`, network gone. The device's own
Wi-Fi (`LeckliterFIOS`) was untouched throughout. `errors=0` on both syncs.

**MAC randomization** (`WifiConfiguration.macRandomizationSetting`) is `@SystemApi`
— not settable by a DO. **Per-network auto-join** has no public toggle for a DO
either (`WifiManager.allowAutojoin` is `@SystemApi`). W18 removed both fields
(`mac_randomization`, `auto_join`) from `NetworksSpec` rather than keep accepting
values the agent can never honour. A configured network auto-joins by default and
the platform picks the randomization mode.

**VPN** is deliberately absent. Android's built-in VPN profile
(`com.android.internal.net.VpnProfile` + `IVpnManager`) is private and
unavailable to a DO, and PPTP was removed from Android in Android 12. The only
DO-supported VPN is `setAlwaysOnVpnPackage(admin, vpnAppPackage, lockdown)` —
pointing at an installed VPN client app. Deferred until one is in the deployment.

## 7. Kiosk and lock task

📖 `setLockTaskPackages(admin, packages)` then `startLockTask()`. Available to a
Device Owner without any launcher role.

**Design note:** adding kiosk to a background agent is two API calls; removing
launcher behaviour from a launcher is a rewrite. This agent declares no
`category.HOME` and engages lock task only when a policy sets `kiosk_package` (F6).

### Permitting is not locking

📖 `setLockTaskPackages` only builds an allowlist. To actually lock a **third-party**
app — ATAK will never call `startLockTask` itself — launch it with
`ActivityOptions.makeBasic().setLockTaskEnabled(true)`.

📖 That throws `SecurityException` unless `isLockTaskPermitted(pkg)` is already true,
so check first and report rather than crash. 📖 It also "doesn't affect activities
that are already running" — a running app must be **relaunched**
(`FLAG_ACTIVITY_CLEAR_TASK`), or it is permitted and not locked.

### ⚠️ NOTIFICATIONS cannot be enabled without HOME

✅ Observed on `SM-X520`, and stated in neither the `setLockTaskFeatures`
documentation nor the lock task guide:

```
java.lang.IllegalArgumentException:
  Cannot use LOCK_TASK_FEATURE_NOTIFICATIONS without LOCK_TASK_FEATURE_HOME
```

This looks like it forces a hole in the kiosk, and does not, **provided the home
button has somewhere safe to go**. Pair it with
`addPersistentPreferredActivity(admin, <HOME filter>, <kiosk activity>)` so HOME
returns to the kiosk app instead of the launcher, and set that **before** enabling
the feature — otherwise there is a window where HOME is live and still points at the
system launcher.

✅ Verified: with HOME enabled and home pointed at the kiosk app, pressing HOME,
pressing RECENTS, and launching `com.sec.android.app.launcher` directly all stayed
inside the kiosk app.

📖 `setLockTaskFeatures` defaults to **`GLOBAL_ACTIONS` only**, and any flag omitted
is implicitly disabled — so it must be passed again alongside anything else, or the
power menu disappears and a field device becomes recoverable only by a hard reset.

📖 From Android 14, **lock task features and packages are a single policy**: "a
failure to apply one will result in a failure to apply the other." ✅ Confirmed — the
rejected feature set above left `mLockTaskPackages` empty rather than half-applied.

### ⚠️ There is no per-activity lock

📖 *"An app in lock task mode **can start new activities** as long as the activity
doesn't start a new task."* So an app locked in kiosk moves between its own
screens freely, and nothing a Device Owner can call prevents it.

`LOCK_TASK_FEATURE_BLOCK_ACTIVITY_START_IN_TASK` (API 30, verified present against
`compileSdk` 36) blocks activities **not on the lock-task allowlist** from opening
inside the locked task. That is a restriction by *package*, not by activity — it
is the closest thing available and it is not the same thing, so a control named
"restrict to this activity only" has to say which of the two it is doing (W61).

📖 Launching a **named** activity is an explicit `ComponentName` intent, not
`getLaunchIntentForPackage` — a kiosk screen is often deliberately not the app's
launcher entry, and may not be exported as one at all.

### Peripheral control while locked in

📖 These are ordinary Device Owner user restrictions, so a kiosk can hold different
rules from the same device out of kiosk with no OEM extension:
`DISALLOW_BLUETOOTH`, `DISALLOW_CONFIG_WIFI`, `DISALLOW_ADJUST_VOLUME`,
`DISALLOW_CONFIG_BRIGHTNESS` (API 28+), `DISALLOW_AIRPLANE_MODE` (API 28+).

⚠️ **Camera is not one of them.** There is no `DISALLOW_CAMERA`; it is
`setCameraDisabled(admin, boolean)`. Screen capture is likewise
`setScreenCaptureDisabled`. Both were assumed to be user restrictions in W59 and
the compiler caught it — worth stating because the rest of the group behaves
uniformly and invites the assumption.

⚠️ Restrictions applied on entering kiosk **must be cleared on leaving it**. They
latch like every other DPM setter, so one left behind follows the device out of
kiosk and nothing else will ever take it off.

### Getting out **on the device** (W65)

A Device Owner can release its own kiosk: clearing the allowlist ejects the locked
app, and the agent can do that from a `SYSTEM_ALERT_WINDOW` overlay it already has
permission for. Two things make that usable rather than merely possible:

* 📖 An overlay target must be `FLAG_NOT_FOCUSABLE`, or it steals focus and the
  kiosk app loses its keyboard. The passcode prompt is the opposite — it needs
  focus, so it is a **separate** window, added only when the taps land.
* ⚠️ The release has to be **remembered**, or the next reconcile re-locks the
  device seconds later and the exit reads as broken. Stored against
  `SystemClock.elapsedRealtime()`, which resets on reboot — so "I am working on
  this device" ends at a restart, and a restart is also the recovery if an exit
  ever strands one.

⚠️ **An exit passcode carried in policy is not a secret.** It is on the device, in
a document anyone with USB debugging can read. It stops idle tapping; it stops
nothing else, and a console that implies otherwise is worse than one with no
passcode at all.

### Getting out

In order of preference, all verified on `SM-X520`:

1. **Remove `kiosk_package` from policy.** Released in ~15 s, and it also clears the
   allowlist and the home preference. No physical access needed.
2. **`adb shell am task lock stop`** — "End the current task lock."
3. `adb shell dpm remove-active-admin <component>`.
4. Factory reset.

There is no remote `stopLockTask`; clearing the allowlist is what ejects a locked
app.

---

## 8. Version-specific behaviour

| Version | Change | Effect here |
|---|---|---|
| Android 10 (29) | `GET_PROVISIONING_MODE` / `ADMIN_POLICY_COMPLIANCE` introduced | — |
| Android 11 (30) | Scoped storage enforced; `MANAGE_EXTERNAL_STORAGE` introduced | Section 6 |
| Android 11+ | `WRITE_EXTERNAL_STORAGE` grant locks out all-files access | ⚠️ trap above |
| Android 12 (31) | Both provisioning activities **required**; `ACTION_PROVISION_MANAGED_DEVICE` fails | Section 3 |
| Android 12 (31) | **System splash screen is mandatory** on cold start — an app cannot opt out | ⚠️ trap below |
| Android 14 (34) | Installs blocked below `targetSdk` 23 | — |
| Android 15 (35) | Floor raised to API 24 | — |
| Android 16 (36) | Floor **unchanged** at 24 | Section 5 |
| Android 16 | Advanced Protection Mode blocks user sideloading; enterprise policy control not until Android 17 | Does not affect Device Owner installs — confirmed in production |

### ⚠️ A custom splash is always the *second* splash

From Android 12 the system draws its own splash screen on every cold start, built
from the app icon and `windowSplashScreenBackground`, and **there is no way to
disable it**. `minSdk` here is 33, so this always applies.

Anything the app draws itself therefore appears *after* it. Left unstyled the
result is two unrelated splashes in a row — the system's icon on the default
background, then the app's own — which reads as a defect rather than branding.

The fix is to make the handover invisible rather than to fight it: set
`android:windowSplashScreenBackground` to the same colour the custom splash uses,
so one continuous field is on screen throughout and only the artwork changes.

`SplashScreen.setKeepOnScreenCondition()` can hold the *system* splash instead,
but it shows the **app icon**, masked to the launcher's shape — no use for a wide
wordmark, which is why W55 draws its own.

> Sources: [Splash screens](https://developer.android.com/develop/ui/views/launch/splash-screen),
> [Migrate your splash screen](https://developer.android.com/develop/ui/views/launch/splash-screen/migrate).

---

## 9. Verified on `SM-X520` (Android 16 / One UI 8)

| Observation | Status |
|---|---|
| Setup wizard downloads APK over HTTP on :8080 | ✅ works |
| Setup wizard over HTTPS with self-signed cert | ❌ never connects |
| base64url-unpadded signature checksum accepted | ✅ APK installed |
| Missing `GET_PROVISIONING_MODE` handler | ❌ "something went wrong" after install |
| `testOnly` in debug APK | Not set by AGP — not a blocker |
| `debuggable=true` | Does not block provisioning |

**User agent seen from the tablet**, useful for spotting real device traffic in
proxy logs:

```
AndroidDownloadManager/16 (Linux; U; Android 16; SM-X520 Build/BP4A.251205.006)
```

---

## Sources

* [Provision for device management — AOSP](https://source.android.com/docs/devices/admin/provision)
* [What's new for enterprise in Android 10](https://developer.android.com/work/versions/android-10) — the `GET_PROVISIONING_MODE` / `ADMIN_POLICY_COMPLIANCE` contracts
* [Provision devices — Google Play EMM API](https://developers.google.com/android/work/play/emm-api/prov-devices) — QR payload keys
* [Build a DPC](https://developer.android.com/work/dpc/build-dpc)
* [DevicePolicyManager reference](https://developer.android.com/reference/android/app/admin/DevicePolicyManager)
* [Manage all files on a storage device](https://developer.android.com/training/data-storage/manage-all-files)
* [WifiManager.addNetwork — deprecation note](https://developer.android.com/reference/android/net/wifi/WifiManager#addNetwork(android.net.wifi.WifiConfiguration)) — the DO/PO/system-app carve-out
* [DevicePolicyManager.setAlwaysOnVpnPackage](https://developer.android.com/reference/android/app/admin/DevicePolicyManager#setAlwaysOnVpnPackage(android.content.ComponentName,%20java.lang.String,%20boolean))
* [Android minimum targetSdk matrix — Jason Bayton](https://bayton.org/android/android-minimum-targetsdk-matrix/)
* [Advanced Protection Mode](https://developer.android.com/privacy-and-security/advanced-protection-mode)
* [Knox SDK deprecation policy](https://docs.samsungknox.com/dev/knox-sdk/faq/general/)
* [Log info disclosure](https://developer.android.com/privacy-and-security/risks/log-info-disclosure) — `READ_LOGS` restriction, and the "manage your own logs" recommendation
* [Security — Android Enterprise](https://developer.android.com/work/dpc/security) — security logging for device owners
* [Changes to device identifiers in Android O](https://android-developers.googleblog.com/2017/04/changes-to-device-identifiers-in.html) and [Android 8.0 behaviour changes](https://developer.android.com/about/versions/oreo/android-8.0-changes) — `ANDROID_ID` scoping, and that it changes on factory reset

## Maintaining this file

Add to it whenever hardware teaches something the code did not already encode, and
mark it ✅. Correct it whenever an official source contradicts an entry — but keep
the observation and note the disagreement rather than deleting it. A documented
claim that our hardware disproves is more valuable recorded than silently removed.
