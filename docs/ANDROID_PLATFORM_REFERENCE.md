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

### Background location: what periodic reporting actually requires (W106)

📖 Three separate gates, and missing any one of them fails differently:

| Gate | Requirement | Our state |
|---|---|---|
| The runtime permission | `ACCESS_FINE_LOCATION` or `_COARSE` | ✅ declared, self-granted |
| Location services switched on | *"The user must have enabled location services"* | ✅ fixable — see `setLocationEnabled` below |
| Reading location while not visible | A `location` foreground service, **or** `ACCESS_BACKGROUND_LOCATION` | ❌ neither yet |

📖 **A foreground service is the documented way to read location without the
background permission** — an app running a `location`-typed FGS counts as
while-in-use. That type needs `android:foregroundServiceType="location"` *and* the
`FOREGROUND_SERVICE_LOCATION` manifest permission (the type is a bitmask, so it
combines with the `specialUse` the sync service already declares).

⚠️ **But the FGS route does not stand on its own here, and the reason is easy to
miss.** Quoting the foreground-service-types page:

> The location runtime permissions are subject to while-in-use restrictions. For
> this reason, you cannot create a `location` foreground service while your app is
> in the background, unless you've been granted the `ACCESS_BACKGROUND_LOCATION`
> runtime permission.

The agent's sync service **starts at boot** — that is a background start. So the
service type alone is not enough for us: it needs `ACCESS_BACKGROUND_LOCATION`
anyway, and then both are required rather than either.

📖 **`ACCESS_BACKGROUND_LOCATION` is protection level `dangerous`**, so it is
within `setPermissionGrantState`'s reach, and `ensureSelfPermissions()` already
self-grants every dangerous permission the manifest declares — adding it to the
manifest *is* the grant, with no new code. Android 11's enterprise notes confirm
the admin path survives and describe only a **user notification**, not a block:

> If the admin sets a global policy to auto-accept all permissions, the user is
> notified when an app requests, and is granted, location permission because of
> this policy.

✅ **Verified on `SM-X520` (agent 0.47.0, API 36), 2026-09-08.** No Google page
states in so many words that a Device Owner may grant *background* location; the
conclusion was assembled from the permission's protection level plus the
enterprise notes, and the device settled it. From its own log:

```
20:16:21 I/PolicyApplier: self-granting 1 permission(s): android.permission.ACCESS_BACKGROUND_LOCATION
20:17:56 I/LocationTracker: location reporting interval: 0 -> 1 minute(s)
20:19:56 I/LocationTracker: location sampled (gps, 1s old); 1 buffered
20:19:56 I/SyncService: foreground service now claims the location type
```

⚠️ **The fixes are 1–2 seconds old, which is the part that matters.** A device
denied background location does not fail loudly — `getLastKnownLocation` keeps
returning something, just increasingly stale. So "points arrived" is not the test;
"points arrived carrying a fresh fix age" is. Ages of 1–2 s over a run of samples
are a live GPS session, which is what proves the grant and the service type both
took effect.

⚠️ **A foreground service type must never be claimed unconditionally.** Quoting
the Android 14 foreground-service-types page:

> If your app doesn't fulfill all of the runtime requirements for starting a
> foreground service, the system throws a `SecurityException` after you call
> `startForeground()` for that service. This prevents the foreground service from
> starting, might cause a running foreground service to be removed from the
> foreground process state, and might cause your app to crash.

For us that service is `SyncService` — the one that manages the device at all. A
`location` type claimed before the Device Owner has self-granted the permission
would take the agent down at boot on every device in the fleet, to add a feature
most of them will not enable. So the manifest declares `specialUse|location` (the
attribute is a bitmask; declaring is free) while `startForeground` is passed a type
computed from what is *actually* granted, and the claim is upgraded later once
tracking is on. A failure to upgrade is logged and swallowed: losing the type costs
tracking, throwing would cost the device its management.

✅ **`DevicePolicyManager.setLocationEnabled(admin, boolean)` (API 30+)** lets a
Device Owner switch the device's master location setting on, which removes the
second gate as a source of mystery — otherwise a correctly permissioned agent
reports nothing at all because location is off in Settings, and nothing in our own
logs would say so. Android 11 notes that the user is notified when an admin does
this. `Settings.Secure.LOCATION_MODE` is deprecated for this purpose and must not
be used via `setSecureSetting`.

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

⚠️ **The agent extracts entries at the paths the zip gives them**, so the archive's
own layout decides where files land. For DTED this is decisive: ATAK reads terrain
from `atak/DTED/<cell>/` and nowhere else — `FileSystemUtils.unzip(zip, dtedDir,
true)` in `ElevationDownloader` — so cells nested one level down extract perfectly
into `DTED/<folder>/<cell>/` and show no terrain, with nothing written to any log.

ATLAS therefore normalises the archive **on the server at upload** rather than
teaching the agent to flatten (W94). The trade was deliberate: an agent-side fix
needs an APK, and until every device took it, one still on the old build would
place terrain wrong and say nothing. Repacking at upload keeps the invariant that
**what the server stores is what lands on disk**, which is also why no agent
release was needed. Measured on a real 726 MB archive: 46.4s to repack, 68 of 68
CRCs unchanged, 158 archiver-junk entries dropped.

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

### Undoing a HOME takeover names the **target** package (W69) ⚠️

`addPersistentPreferredActivity(admin, homeFilter, component)` makes an app the
home screen. The undo is
`clearPackagePersistentPreferredActivities(admin, packageName)` — and the
`packageName` it wants is the package the preference **points at**, not the admin
that set it. AOSP compares `pa.mComponent.getPackageName()`.

⚠️ **Passing your own package removes nothing and reports success.** The agent did
this from the first kiosk build: it set HOME to the kiosk app and cleared for
itself, so every device that ever entered kiosk kept that app as its home screen
after the policy was removed — a HOME button still going to the kiosk on a device
with no kiosk policy, which reads as the removal not having worked at all.

⚠️ **Clearing the preference is still not the whole job.** A launcher installed
alongside the stock one leaves *two* home apps and no default, so HOME raises the
"Complete action using…" chooser. To hand the device back as it was, the extra
launcher has to go — and **uninstall, not hide**: a hidden package still exists
but reads as missing to `getPackageInfo`, so the DPC's own installer decides it
needs installing again on the next kiosk.

### ❌ An `animation-list` is not a notification small icon (W84) ✅ observed

`setSmallIcon` pointing at an `<animation-list>` does not animate and does not
show the first frame. On `SM-X520` (One UI) the platform **substituted the app's
launcher icon** — a full-colour logo *with its wordmark*, which at 24dp is a
smudge that says nothing about a download.

⚠️ The failure is silent and looks like a design choice, not a fault: there is no
log line, and the status bar simply shows a different picture. The only clue is
that the icon is the app's own.

AOSP's `StatusBarIconView` does start an `AnimationDrawable` it is handed, which
is how the platform's *own* `stat_sys_download` moves — but that path is not
reachable for a third-party notification here. Ship a **static** silhouette.

### ❌ Two notifications from one app ⇒ the status bar shows the app icon (W87) ✅ observed

Static artwork did not fix the symptom above. With the download notice as a
**second** notification beside the agent's ongoing service notice, `SM-X828U`
showed the download arrow for about a second and then reverted to the app's
launcher icon — the same wordmark smudge, from a different cause.

Two notifications from one package are auto-grouped, and the group's status-bar
entry is drawn from the **app icon**, not from either notification's
`setSmallIcon`. A single notification never groups, so the icon in the bar is
always the one the app chose.

⚠️ The consequence for a foreground service: its notification id is the only one
to post to, and finishing background work must **re-post** a resting notification
over that id rather than cancel it. Cancelling takes the service out of the
foreground, and Android then kills it. Conversely, when no foreground service
holds the id, an `ongoing` notification left behind cannot be dismissed by hand —
so that case has to cancel. See `AgentNotification.rest`.

Both failures are silent, and both produce the *same* wrong picture, which is
what made the second one look like the first one not being fixed.

### ✅ A Device Owner installs and removes trust anchors (W112) — verified on `SM-X828U`

> ⚠️ **The feature this section describes was removed in W113** (2026-09-09), so
> `CertificateApplier`, `CertificatePlan` and the `certificates` key no longer
> exist — do not go looking for them. **Everything below is still true of the
> platform** and is kept deliberately: it was verified on hardware, and it is
> exactly what a future attempt would otherwise have to rediscover. See the W113
> entry in `PROJECT_STATE.md` for why it came out — briefly, a client certificate
> reaches no consumer here without EAP Wi-Fi support that does not exist.

Both directions, on hardware, from the device's own log:

```
13:45:09 I/CertificateApplier: trusted CA installed: ATLAS W112 Verification CA
13:48:58 I/CertificateApplier: trusted CA removed: 479243d5ce1218b6…
```

The device stayed `compliant` with **no apply errors** through install, removal
and re-install, so `installCaCert` and `uninstallCaCert` both returned true for a
Device Owner on Android 16 with no user interaction and no OEM extension.

⚠️ **A user can delete a policy-installed anchor, and Android announces it.**
Observed on `SM-X828U`: a *"CA cert installed"* notification appears, and the
certificate is removable by hand from **Settings › Encryption & credentials ›
Trusted credentials › User**. A Device Owner does **not** get an anchor the user
cannot touch.

So device trust is **maintained, not enforced** by the certificate APIs alone.
Two answers, and they compose:

1. **Re-assert it** — check `hasCaCertInstalled` against the device on every
   reconcile and put back what has gone, rather than trusting the agent's own
   record of what it installed. ✅ Verified: the operator deleted the anchor in
   Settings and it returned on the next check-in.
2. ✅ **Close the window entirely with `DISALLOW_CONFIG_CREDENTIALS`** — a plain
   Device Owner user restriction, **no Knox required**: *"Specifies if a user is
   disallowed from configuring user credentials."* ⚠️ It blocks the whole
   credentials screen, so the user also cannot add or remove certificates of
   their own — it is not a per-certificate lock, and a console that implies
   otherwise will produce a support call.
An applier that skips anything it believes it already installed leaves a deleted
anchor gone for ever — and the console would show a policy that says "trust this"
while the device does not. A device can therefore be without a policy anchor for
up to one check-in cycle, which is worth saying in the console rather than
implying enforcement.

⚠️ **`uninstallCaCert` identifies a certificate by its *content*.** There is no
alias and no handle — the caller passes the same DER/PEM bytes back. An agent that
does not keep them can remove nothing specific; the only call that works without
them is `uninstallAllUserCaCerts`, which removes **every** user-installed anchor
including ones a person added themselves. So the bytes are stored per anchor, and
the sha256 recorded, precisely so removal can be exact.

⚠️ **`installCaCert` returns `false` rather than throwing** when the bytes cannot
be parsed — the same shape as `setWifiEnabled` (W72) and `setKeyguardDisabled`
(W111). A caller that ignores the return value reports success on a certificate
the device never trusted.

### The Security category: what AOSP gives without Knox (W112 scoping, 2026-09-09)

Checked against the framework source rather than recalled. Four of the five
sub-topics are reachable with no OEM extension at all; the Knox-only parts are
narrower than they look.

| Sub-topic | Without Knox? | The AOSP answer |
|---|---|---|
| **Certificates** | ✅ fully | `installCaCert`, `installKeyPair`, `generateKeyPair` (hardware-backed, with attestation), `setDelegatedScopes(DELEGATION_CERT_INSTALL)` |
| **SCEP** | ✅ but we write the client | No SCEP API exists in AOSP. SCEP is an HTTP protocol, and the agent already generates keys and CSRs for enrolment (`DeviceIdentity.kt`), so this is a protocol client plus `installKeyPair` — work, not a dependency |
| **Global HTTP proxy** | ✅ | `setRecommendedGlobalProxy` |
| **Web content filtering** | ⚠️ partly | **No filtering API of any kind in AOSP** — zero matches for url/content/web filter. See below |
| **OS updates** | ✅ scheduling only | `setSystemUpdatePolicy` + `getPendingSystemUpdate` |

⚠️ **The global proxy is advisory, and the javadoc says so outright:**

> This proxy is only a recommendation and it is possible that some apps will
> ignore it.

So it configures rather than enforces — anything using raw sockets, or ignoring
the system proxy, simply goes around it. It also cannot be set at all when there
are unaffiliated secondary users on the device.

⚠️ **"Web content filtering" has no direct API, and the honest substitute is DNS.**
`setGlobalPrivateDnsModeSpecifiedHost` pins the device to a DoT resolver of the
operator's choosing — enforced, and the user cannot change it — so a filtering
resolver gives real category blocking. `setAlwaysOnVpnPackage` is the other route
and needs a VPN app to exist. **Neither does URL-level rules inside HTTPS**, and
nothing in AOSP does. That is the one place where an OEM extension genuinely buys
something ATLAS cannot otherwise have.

⚠️ **`POSTPONE` is capped at 30 days and then the update installs anyway:**

> Postpones the installation of system updates for 30 days. After the 30-day
> period has ended, the system prompts the user to install the update.

So AOSP offers *when*, never *whether* or *which version*. Pinning a fleet to a
specific firmware build is Samsung **E-FOTA**, and that is a real Knox dependency
rather than a convenience — worth knowing before promising a version-locked fleet.

**Conclusion:** certificates, SCEP, the proxy and update *scheduling* need no
Knox. The genuinely Knox-gated pieces are **URL-level web filtering** and
**version-pinned firmware**, and both have partial AOSP substitutes (a filtering
DNS resolver; postpone-and-window scheduling) that are worth building first
because they work on any device.

### ⚠️ `wipeData` cannot factory reset this fleet, and never could (W114, 2026-09-09)

📖 `DevicePolicyManager.wipeData(int, CharSequence)`, quoted from AOSP:

> Calling this method from the primary user will only work if the calling app is
> targeting SDK level `TIRAMISU` or below, in which case it will cause the device
> to reboot, erasing all device data … **If an app targeting SDK level
> `UPSIDE_DOWN_CAKE` and above is calling this method from the primary user or
> last full user, `IllegalStateException` will be thrown.**
>
> If an app wants to wipe the entire device irrespective of which user they are
> from, they should use `wipeDevice` instead.

The agent is a Device Owner on the primary user at `targetSdk 36`. That is not an
edge case — it is **every wipe on every device**, so W104 disenroll had never once
worked.

⚠️ **The rule keys off two different SDK levels, and conflating them is the trap.**
Whether `wipeData` throws depends on **this app's `targetSdk`**; whether
`wipeDevice` exists depends on **the device's API level**. With `minSdk 33` both
matter, so the call branches on `Build.VERSION.SDK_INT`.

✅ **`wipeDevice(int)` is present in android-34, -35 and -36** — verified with
`javap` against each installed `android.jar`, not recalled. The android-33 stubs
are not installed on this workstation, so its absence there is **inferred, not
verified**; the `SDK_INT >= UPSIDE_DOWN_CAKE` branch is written so that
correctness does not depend on that inference either way.

⚠️ **An earlier comment in `DeviceCommandHandlers.kt` asserted `wipeDevice` was
API 37** — "against `compileSdk 36` it does not exist to call" — and on that basis
kept the call that always throws. It was written from recollection, which is the
thing this document exists to prevent. `wipeDevice(int)` also takes **no reason
string**; the user-facing wipe message is not available on this path.

⚠️ **The failure mode is what made this expensive, not the wrong call.** The throw
landed inside `runCatching` in a *deferred* effect, which by design runs only
**after** the acknowledgement reaches the server — and the server revokes the
device's certificate on that acknowledgement. So the one component that knew the
wipe had failed was, by that moment, unable to tell anyone. Observed on
`SM-X828U`: the console reported the device disenrolled and removed, while the
tablet sat still owned by the agent, unmanaged, showing *"sync failed, certificate
is not known"* — `deps.py` rejecting a serial no longer in `device_certificate`.

✅ **`wipeDevice` verified on `SM-X520` (agent 0.55.0), 2026-09-09.** A plain
wipe — identical params to disenroll, but without the `disenroll` marker, so the
record and certificate survived to report a failure if there was one — was
acknowledged (`SUCCEEDED`, one attempt) and the tablet factory reset. Confirmed
by the operator at the device, and corroborated server-side by check-ins simply
stopping: 113 s, 137 s, 160 s, 185 s, 209 s, 233 s since last contact from a
device that had been checking in every ~60 s.

So the two halves are each proven, on hardware, separately: the server's
ack → revoke → remove path on 2026-09-09 (which worked correctly even while the
wipe was failing), and the wipe itself now. **They have not yet been run
together**, which is what a real disenroll would test.

**A deferred effect that cannot report its own failure needs its precondition
checked before the acknowledgement, not after.** Recorded as an open risk rather
than silently redesigned.

#### ⚠️ `WIPE_RESET_PROTECTION_DATA`, and why it is not the default (W116)

📖 AOSP, on the flag:

> Flag for `wipeData(int)`: also erase the factory reset protection data.
>
> **This flag may only be set by device owner admins**; if it is set by other
> admins a `SecurityException` will be thrown.

`wipeDevice(int)`'s javadoc lists it among its supported flags, so it applies on
the API 34+ path too.

⚠️ **It is correct on exactly one of the two wipes we send.** Factory Reset
Protection gates the next setup on the Google account signed in before the wipe:

| Wipe | FRP | Why |
|---|---|---|
| **Disenroll** — handing the device back | **cleared** | Otherwise the recipient meets a login screen demanding credentials belonging to whoever held it last, and the only people who can pass it no longer own the device |
| **Ordinary wipe** — a lost device | **left armed** | Clearing it would hand a thief a clean, resellable tablet |

The flag therefore travels in the command params rather than being inferred by
the agent from the disenroll marker: the server owns the decision, and an agent
that does not know the key leaves FRP armed — failing in the safe direction.

⚠️ **Not verified on hardware.** FRP behaviour is partly OEM territory, so
whether Samsung honours the flag as AOSP describes is unproven here. The next
disenroll run is the test.

### ⚠️ A client certificate without a *grant* is silently useless (W112 C2, 2026-09-09)

📖 `installKeyPair` and `generateKeyPair` put a key in KeyChain. **Nothing can
use it yet.** The javadoc for `grantKeyPairToApp` says what the grant replaces:

> This is useful (in combination with `installKeyPair` or `generateKeyPair`) to
> let an application call `KeyChain.getPrivateKey` **without having to call
> `KeyChain.choosePrivateKeyAlias` first**.

`choosePrivateKeyAlias` is a **user-facing chooser dialog**. On an unattended or
kiosk tablet nobody taps it, so an ungranted certificate fails with no error
anywhere: the console shows the policy applied and the certificate installed, and
authentication simply never happens. This is the failure mode that ships
undetected when there is no testbed — everything reports success.

| Call | For |
|---|---|
| `grantKeyPairToWifiAuth(alias)` | Wi-Fi EAP authentication. Note: **no `admin` parameter** |
| `grantKeyPairToApp(admin, alias, packageName)` | A named app — a VPN client, for example |
| `isKeyPairGrantedToWifiAuth(alias)`, `getKeyPairGrants(alias)` | Read back, so a grant can be re-asserted like any other declarative state |

⚠️ All of them **return `boolean` rather than throwing** on refusal — the same
shape as `installCaCert` (above), `setWifiEnabled` (W72) and `setKeyguardDisabled`
(W111). A caller ignoring the return value reports success on a grant that was
never made.

⚠️ `grantKeyPairToApp` throws `IllegalArgumentException` on API 34+ if the alias
does not exist, and if `packageName` is not an installed package. **Order matters:**
install the key before granting it, and install the VPN app before granting to it.

⚠️ **There is nothing for the certificate to attach to yet.** `NetworksSpec`
offers `none` / `wep` / `wpa_psk` / `wpa3_sae` only, and `applyNetworks` sets
`allowedKeyManagement` from that enum — **no EAP of any kind**. EAP-TLS needs
`WifiConfiguration.enterpriseConfig` (`WifiEnterpriseConfig`) carrying the EAP
method, identity, CA certificate and the client alias. So "install a `.p12`" on
its own reaches **no consumer**: the Wi-Fi enterprise config is the larger half of
this work, not the certificate handling.

**VPN stays out of reach beyond the grant.** §6d records that the only
DO-supported VPN is `setAlwaysOnVpnPackage` pointing at an installed client, whose
certificate configuration is that app's own business. ATLAS can grant the key; it
cannot tell the app to use it.

### ⚠️ `setKeyguardDisabled` cannot bypass a PIN that is already set (W111)

📖 AOSP's own javadoc on `DevicePolicyManager.setKeyguardDisabled`, quoted in
full because the sentence in the middle is the one that matters:

> Called by a device owner or profile owner of secondary users that is affiliated
> with the device to disable the keyguard altogether.
>
> Setting the keyguard to disabled has the same effect as choosing "None" as the
> screen lock type. **However, this call has no effect if a password, pin or
> pattern is currently set. If a password, pin or pattern is set after the
> keyguard was disabled, the keyguard stops being disabled.**
>
> `@return` `false` if attempting to disable the keyguard while a lock password
> was in place. `true` otherwise.

⚠️ **So a "trusted area that turns the password off" is not buildable this way**,
and the shortfall is invisible from the console: the policy applies, the device
reports success, and the PIN is still there. What this API actually does is remove
the *swipe* keyguard from a device that has **no** credential — useful on a kiosk
tablet that should wake straight into its app, and nothing like Smart Lock's
trusted places.

⚠️ **It also un-disables itself.** Setting any PIN later silently re-enables the
keyguard, so a device that was configured once cannot be assumed to have stayed
that way.

**It returns `false` rather than throwing** when refused — the same shape as
`setWifiEnabled` (W72). Read the return value; a silent success is not one.

The nearest thing that *would* clear a credential is `resetPasswordWithToken` with
an empty password, and §6c already records why that is not a route: the token
"activates immediately only if the device has no passcode. If one is already set,
the user must complete a confirm-credential operation … this **cannot be forced**."

### ✅ A Device Owner *can* turn Wi-Fi on and off (W72) — verified on `SM-X520`

`WifiManager.setWifiEnabled()` has returned false for ordinary apps since
Android 10. A **Device Owner is exempt**, and this is confirmed on hardware: the
kiosk's Device Settings screen toggled the radio on and off on Android 16.

⚠️ It returns **false** rather than throwing when refused, so read the state back
rather than trusting the call — and log both outcomes. Logging only failures made
this unanswerable from a device's own log: a successful toggle said nothing, so
silence meant either "it worked" or "nobody tried it".

### ❌ Airplane mode cannot be toggled by any app (W72)

`Settings.Global.AIRPLANE_MODE_ON` needs `WRITE_SECURE_SETTINGS`
(`signature|privileged|development`), which a Device Owner **cannot self-grant** —
`setPermissionGrantState` reaches only `dangerous` runtime permissions. And
`setGlobalSetting`'s allowlist is `ADB_ENABLED`, `USB_MASS_STORAGE_ENABLED`,
`STAY_ON_WHILE_PLUGGED_IN`, `WIFI_DEVICE_OWNER_CONFIGS_LOCKDOWN` — airplane mode
is not on it and throws.

The same wall as the OS device name (W24). What a Device Owner *can* do is turn
the radios it controls off individually, and forbid the user changing airplane
mode with `DISALLOW_AIRPLANE_MODE`.

### ❌ A DPC cannot remap a hardware key (W72)

There is no API to make the side key long-press do anything. In lock task,
`LOCK_TASK_FEATURE_GLOBAL_ACTIONS` decides whether the power menu may appear at
all — but if the OEM has mapped the key elsewhere (Bixby on Samsung), enabling
the feature changes nothing, because the key never raises the menu.

⚠️ The only route to a power menu from an app is an **AccessibilityService**
performing `GLOBAL_ACTION_POWER_DIALOG`, and that service needs a **manual grant
per device** — the same class of grant as the overlay permission. `dpm.reboot()`
is the one power action available with no grant at all.

### A launcher cannot see other apps (W68)

⚠️ From Android 11 an ordinary app cannot enumerate installed packages, and a
launcher without `<queries>` gets an **empty grid with nothing logged** —
filtering is indistinguishable from "not installed". The agent never hit this: a
**Device Owner is exempt** from package visibility filtering. A separate launcher
APK is not the Device Owner and is not exempt.

```xml
<queries><intent>
  <action android:name="android.intent.action.MAIN" />
  <category android:name="android.intent.category.LAUNCHER" />
</intent></queries>
```

`QUERY_ALL_PACKAGES` also works and is what most launchers reach for; the intent
query is enough when everything shown is launchable by definition.

### Two mechanisms pin orientation, and only one always works (W68)

`setRequestedOrientation` pins the **calling activity** and needs no permission —
so a launcher can pin itself but not the kiosk app the user actually looks at.

`Settings.System.ACCELEROMETER_ROTATION` / `USER_ROTATION` pin every app and need
`WRITE_SETTINGS`. ⚠️ That is a **special permission a person grants through
Settings**; no Device Owner can grant it, because `setPermissionGrantState` does
not reach app-ops. Attempt it and log its absence — do not treat it as a failure,
because the visible half still works.

### A full-screen overlay must never take a touch (W68)

`TYPE_APPLICATION_OVERLAY` across the whole screen is how a DPC tints every app
(night mode). ⚠️ Without `FLAG_NOT_TOUCHABLE` **and** `FLAG_NOT_FOCUSABLE` it
swallows all input, which on a wall-mounted device is a brick recoverable only by
removing the policy — and under a red wash the user cannot even see what is
wrong. Add `FLAG_LAYOUT_IN_SCREEN | FLAG_LAYOUT_NO_LIMITS` or the status and
navigation bars stay untinted as two bright strips.

Recolour the existing view rather than remove-and-re-add: the gap between the two
flashes the untinted screen, which at night is the one thing the feature exists
to prevent.

### Entering lock task is not idempotent (W67) ✅ observed, ✅ fix verified on `SM-X520`

`startActivity(intent, ActivityOptions.makeBasic().setLockTaskEnabled(true))` is
how a Device Owner puts an app into lock task, and `FLAG_ACTIVITY_CLEAR_TASK` is
what makes it work on an app that is **already running** — without it the app
stays up exactly as it is, outside lock task, and the kiosk silently is not one.

⚠️ **That same flag is destructive on every call after the first.** It tears the
task down and cold-starts the app. A DPC that applies policy on a timer therefore
restarts its kiosk app on every reconcile — every two minutes here — which on a
heavy app (ATAK: maps, plugins, a long startup) is indistinguishable from the app
crashing in a loop.

⚠️ **It fails green.** Each relaunch succeeds, so there is no exception, no policy
failure and no compliance change; the console shows a healthy device. The only
trace is the DPC's own log saying it launched the app, over and over, which reads
as normal operation. There is no API to ask "is this package already in lock
task" — `ActivityManager.getLockTaskModeState()` answers only for the caller's own
task — so the DPC has to remember what it launched.

✅ **Verified on hardware (W68's first multi-app kiosk).** The agent log now reads
`launched … into lock task` **once**, then `already in lock task; brought to
front` on every sync after — where before the fix it said `launched` every two
minutes.

Front an already-launched kiosk with `NEW_TASK or SINGLE_TOP` instead: a no-op
when it is in front, and it recovers the kiosk if anything got on top of it.
Force the relaunch again only when the component changes or the device reboots —
and detect the reboot with `elapsedRealtime`, since after a restart nothing is in
lock task and fronting would leave the device unlocked.

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

## 10. ATAK's own enterprise-configuration contract

⚠️ **This is an *app* contract, not a platform one**, and it is here because the
rest of the file's discipline applies to it: it fails vaguely, it is invisible
from the device, and reasoning from the symptom costs a factory reset's worth of
time for nothing. Traceable to ATAK's own shipped APK and to `atak-civ` source,
not to recollection.

Established 2026-09-06 against
`Test Files/ATAK-5.8.0.4-174b425-civSmall-release.apk` and
[`PreferenceControl.java`](https://github.com/TAK-Product-Center/atak-civ/blob/main/atak/ATAK/app/src/main/java/com/atakmap/app/preferences/PreferenceControl.java).

### 10a. The six keys ATAK declares

✅ **Verified here** — read out of the shipping APK with this project's own
`app_restrictions` scanner:

| Key | Type | What it takes |
|---|---|---|
| `enterpriseConfigurationPreferences` | String | A `.pref` XML document, **plain text** |
| `enterpriseConfigurationDataPackage` … `…DataPackage5` | String | A data package, **base64** |

⚠️ **Two adjacent keys, two encodings.** The data-package slots are
`Base64.decode`d; the preferences key is written to a file verbatim. Getting this
backwards produces no error anywhere — just a configuration that never applies.

📖 ATAK's own description of the data-package slots states the **64 KB** ceiling
outright, and gives five slots as the workaround for it. That ceiling is
Android's Binder transaction limit, so it governs the preferences key equally.

### 10b. How ATAK ingests it

`PreferenceControl.processEnterpriseConfigurationPreferences()`:

1. reads the key from `RestrictionsManager.getApplicationRestrictions()` —
   precisely what a Device Owner's `setApplicationRestrictions` writes, so **no
   managed Google Play is involved**;
2. compares an MD5 of the content against
   `enterpriseConfigurationPreferencesMd5` in its own prefs, and **does nothing
   if unchanged** — re-pushing identical bytes is a genuine no-op;
3. writes it to `filesDir/defaults`, calls `loadSettings(f)`, deletes the file;
4. records the new MD5.

It is driven by a receiver on `ACTION_APPLICATION_RESTRICTIONS_CHANGED`, so a
change applies **without restarting ATAK**.

This route needs **no `MANAGE_EXTERNAL_STORAGE`, no file push into
`/sdcard/atak/`, and no Knox** — which is why it sidesteps R1 rather than
depending on it.

### 10c. ⚠️ One bad value discards every setting after it

`loadSettings` switches on the `class` attribute verbatim and calls
`Integer.parseInt` / `Float.parseFloat` **unguarded**. There is no per-entry
`try`, so a `NumberFormatException` unwinds the entire document. Three
consequences, all invisible from outside:

* every entry **before** the bad one has already been `editor.apply()`d;
* step 4 above never runs, so the document is **not** marked ingested and the
  same half-application is retried on every restrictions-changed broadcast;
* the only trace is a line in ATAK's own log.

Every value must therefore be validated against its declared class **on the
server**, where the operator can be told. `app/services/atak_pref.py` does this.

⚠️ **A boolean is worse than a crash.** `Boolean.parseBoolean` reads anything
that is not `"true"` as **false**, so `"yes"` applies as false with no error at
all.

### 10c-ii. ⚠️ Removing the configuration does not undo it

`loadRestrictions` returns **null** when the key is absent *or empty*, and
`processEnterpriseConfigurationPreferences` guards on `if (ecp != null)`. So
clearing `enterpriseConfigurationPreferences` — which is exactly what the agent
does when a policy stops naming the app — is a **no-op inside ATAK**. Every
setting the document already wrote stays written, because they went into ATAK's
own `SharedPreferences` and nothing reads them back out.

⚠️ **This is the opposite of every other policy type here.** A password policy
relaxes when removed (R14), managed configuration is cleared when an app is
dropped, kiosk releases. ATAK Config is **write-only from ATAK's side**: it can
change a setting and it can change it again, but "stop managing" is not "restore".
The same asymmetry the FILES policy has — the MDM never deletes what it placed.

**To genuinely revert, push the old values first and only then remove the
policy.** Removing it on its own leaves the device exactly as the last document
left it, with nothing in the console to suggest otherwise.

### 10d. The class names, verbatim

| `class` attribute | Stored as |
|---|---|
| `class java.lang.String` | `putString` |
| `class java.lang.Boolean` | `putBoolean` |
| `class java.lang.Integer` | `putInt` |
| `class java.lang.Float` | `putFloat` |
| `class java.lang.Long` | `putLong` |
| a `Set` class | `putStringSet`, from nested `<element>` children |

Anything else is skipped in silence.

⚠️ **An `EditTextPreference` is a String even when it holds a port.** ATAK's
`chatPort` defaults to `17012` and is stored as `class java.lang.String` — that
is what a real EUD export contains and what `getString` on the device expects.
Typing it as an Integer because it looks numeric throws inside ATAK. The **widget
class** decides the type; the value never does.

### 10e. Value escaping is ATAK's, not XML's

`PreferenceControl.decode` reverses exactly five sequences — `"` `'`
`<` `>` `&` — in element **text**. Writing `&amp;` instead leaves
the app holding those five literal characters. Attribute values are read by a
real XML parser and do take genuine entities.

### 10f. Preference group names

`<preference name="X">` writes into `getSharedPreferences(X)`. ATAK maps three
legacy names — `com.atakmap.app_preferences`, `com.atakmap.civ_preferences`,
`com.atakmap.fvey_preferences` — onto `<packageName>_preferences`, which for
ATAK-CIV is `com.atakmap.app.civ_preferences`.

⚠️ **`cot_inputs` / `cot_outputs` / `cot_streams` are handled by a different code
path** (`loadConnectionHolder`), not as ordinary preferences. ATLAS omits those
blocks entirely rather than writing them empty: a `<preference>` element ATAK
does not see is one it cannot act on, and what it might act on is the operator's
TAK server connection.

### 10g. ✅ Reading settings out of an ATAK build

Measured on 5.8.0.4 with this project's `axml` + `arsc` readers:

| | |
|---|---|
| `res/**/*.xml` entries | 1006 |
| `PreferenceScreen` documents | 65 (48 with storable settings) |
| Storable settings | 293 |
| Titles resolved through `resources.arsc` | 292 of 293 |
| Dropdowns resolved to real label→value pairs | 46 of 47 |
| Scan time, whole APK (112 MB) | ~0.7 s |

⚠️ **Resource names are shrunk** — `res/-v.xml`, `res/0P.xml`, `res/1z.xml`. No
lookup for `res/xml/*pref*.xml` finds anything at all, which is the same
conclusion the managed-configuration scanner reached for `res/Kt.xml` (W49).
Discovery must be by **content**: parse every `res/` XML and decide on the root
element.

⚠️ **Every widget class is subclassed.** 155 of ATAK's rows are
`com.atakmap.android.gui.PanCheckBoxPreference`. Classification must match the
class-name **suffix**, not the exact name.

⚠️ **Only what is declared in `res/` is visible.** Settings written from code, and
custom stores such as `NWSharedPreferences`, cannot be discovered by any amount
of scanning. Say so rather than presenting the list as complete.

---

## 11. ATAK data packages ("mission packages")

⚠️ **An *app* contract again**, here for the same reason as §10: it fails
quietly, and the failure looks like a broken MDM rather than a rejected file.

Read out of `atak-civ` `com/atakmap/android/missionpackage/`, 2026-09-07.

### 11a. What makes a zip a data package

`MissionPackageBuilder.MANIFEST_PATH = "MANIFEST"`, so the document is
`MANIFEST/manifest.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<MissionPackageManifest version="2">
  <Configuration>
    <Parameter name="uid" value="…"/>
    <Parameter name="name" value="…"/>
  </Configuration>
  <Contents>
    <Content ignore="false" zipEntry="overlay.kml"/>
  </Contents>
</MissionPackageManifest>
```

| Rule | Where it is enforced |
|---|---|
| `version="2"` | `@Attribute(name="version", required=true) private int VERSION = 2` |
| `<Configuration>` and `<Contents>` both present | both `@Element(required = true)` |
| Configuration holds **more than one** `<Parameter>`, **and** `name`, **and** `uid` | `MissionPackageConfiguration.isValid()` |
| Each `<Content>` carries `zipEntry` | `@Attribute(name="zipEntry", required=true)` |
| `<Contents>` **may be empty** | `MissionPackageContents.isValid()` returns `true` unconditionally |

### 11b. ⚠️ The manifest is found by suffix, at any depth

`MissionPackageExtractorFactory.HasManifest` scans entries for
`entry.getName().endsWith("MANIFEST/manifest.xml")` and stops at the **first**
match. So `mydata/MANIFEST/manifest.xml` is a valid package, and **everything the
manifest names is relative to the MANIFEST directory's parent** — `mydata/`, not
the zip root.

That nested shape is what a Windows right-click *"compress folder"* produces, and
`MissionPackageManifest` documents it explicitly. A validator that only looks at
the zip root rejects a large share of the packages that actually exist.

### 11c. ⚠️ ATAK accepts a zip with no manifest

`GetExtractor` returns `PlainZipExtractor` when `HasManifest` is false, so a
plain zip is still unpacked — with none of the manifest's placement or
`onReceiveImport` semantics. **ATLAS refuses those anyway**, by operator
decision, because where their contents land is unpredictable. Any rejection
message must say ATAK *would* have taken it, or the operator goes looking for a
fault in their file.

### 11d. Where to drop a package — settled on hardware, against the source

Both directories were tried on `SM-X520` on 2026-09-07, one package each, with
placemarks in different cities so the result could not be ambiguous.

| Directory | What the source says | What the tablet did |
|---|---|---|
| `atak/tools/datapackage/` | **Watched** — *"auto-import any .zips found there (e.g. received or **manually placed**), no HTTP serving, **no auto-cleanup**"* | ✅ imported (San Diego pin) |
| `atak/tools/datapackage/incoming/` | **`// no watch`**, and registered with `DirectoryCleanup` (deletes >2h) | ✅ **imported anyway** (Los Angeles pin) |

⚠️ **The source is wrong, or at least incomplete, about `incoming/`.** It says
`// no watch`; the parent's watcher is provably **non-recursive** —
`DirectoryWatcher.onEvent` ignores directory events outright and carries TODOs
about adding sub-directory listeners — and **nothing else in `com/atakmap`
references that directory** except `MissionPackageReceiver` and the HTTP
downloader writing network transfers into it. Yet a manually placed zip was
imported from it.

⚠️ **So the mechanism is unidentified**, and that is the risk: behaviour nobody
can point at in source is behaviour that can change between ATAK releases without
anyone noticing. Tracked as **R17**.

✅ **ATLAS writes to `incoming/` regardless**, by operator decision, for a reason
the source does support: `DirectoryCleanup` sweeps it after two hours, so
delivered packages do not pile up in ATAK's directory forever — which is exactly
what the watched parent does, with its explicit `no auto-cleanup`.

⚠️ **The sweep itself is still unconfirmed.** It is expected, not observed. If it
does *not* happen, `incoming/` accumulates exactly like the parent and the reason
for choosing it evaporates. Part of R17.

### 11e. ⚠️ Deliver it once, and never again

The watcher imports whatever appears. A package the MDM keeps re-writing is a
package ATAK keeps re-importing — which, on the operator's own account, can take
the app down.

⚠️ **The zip is NOT deleted after import.** ✅ Verified on `SM-X520` 2026-09-07:
ATAK imported the package and **left the file in `tools/datapackage/`**, which
matches that directory's own `no auto-cleanup` note. An earlier draft here said
"ATAK consumes the zip, so absence is the expected end state" — that is the
behaviour of `incoming/`, not of the watched directory, and it was assumed rather
than observed.

**The rule survives the correction, but for a different reason.** Delivering once
matters not because the file disappears but because **re-writing a file the
watcher is watching is what makes ATAK import it again**. Absence is a *possible*
end state — a user may delete it — and a re-push on those grounds would be an
unwanted import, so the applied-content record is still the right gate.

✅ **ATLAS already has exactly this rule: `persist: false`.** `Reconciler.applyFile`
consults the presence check `FileDeployer.isDeployed` **only when `persist` is
true**; with it false, a matching applied-content hash ends the matter and the
file is never re-pushed, gone or not. Proven on `SM-X520` 2026-09-01 by deleting
two files at once and watching one reconcile pass leave one alone and replace the
other, decided purely by the flag.

⚠️ **An earlier draft of this section claimed a new mechanism was needed.** That
came from reading `isDeployed`'s docstring without opening its caller — the exact
failure this file exists to prevent. Recorded rather than quietly deleted.

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
* [`PreferenceControl.java` — ATAK-CIV](https://github.com/TAK-Product-Center/atak-civ/blob/main/atak/ATAK/app/src/main/java/com/atakmap/app/preferences/PreferenceControl.java) — the `.pref` format, the enterprise-configuration keys, and the unguarded number parsing behind §10
* [`MissionPackageBuilder` / `MissionPackageManifest` / `MissionPackageExtractorFactory` / `MissionPackageFileIO` — ATAK-CIV](https://github.com/TAK-Product-Center/atak-civ/tree/main/atak/ATAK/app/src/main/java/com/atakmap/android/missionpackage) — the data-package format, the manifest lookup, and the watched vs. `incoming` directories behind §11
* [RestrictionsManager.getApplicationRestrictions](https://developer.android.com/reference/android/content/RestrictionsManager#getApplicationRestrictions()) and [ACTION_APPLICATION_RESTRICTIONS_CHANGED](https://developer.android.com/reference/android/content/Intent#ACTION_APPLICATION_RESTRICTIONS_CHANGED) — the channel §10 travels in
* [Knox SDK deprecation policy](https://docs.samsungknox.com/dev/knox-sdk/faq/general/)
* [Log info disclosure](https://developer.android.com/privacy-and-security/risks/log-info-disclosure) — `READ_LOGS` restriction, and the "manage your own logs" recommendation
* [Security — Android Enterprise](https://developer.android.com/work/dpc/security) — security logging for device owners
* [Changes to device identifiers in Android O](https://android-developers.googleblog.com/2017/04/changes-to-device-identifiers-in.html) and [Android 8.0 behaviour changes](https://developer.android.com/about/versions/oreo/android-8.0-changes) — `ANDROID_ID` scoping, and that it changes on factory reset

## Maintaining this file

Add to it whenever hardware teaches something the code did not already encode, and
mark it ✅. Correct it whenever an official source contradicts an entry — but keep
the observation and note the disagreement rather than deleting it. A documented
claim that our hardware disproves is more valuable recorded than silently removed.
