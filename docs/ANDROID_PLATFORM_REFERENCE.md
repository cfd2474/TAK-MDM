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
adb shell dpm set-device-owner org.takmdm.agent/.admin.MdmDeviceAdminReceiver
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
package.** `org.takmdm.agent/.MdmDeviceAdminReceiver` means
`org.takmdm.agent.MdmDeviceAdminReceiver`. Our receiver is in the `.admin`
sub-package, so the correct value is:

```
org.takmdm.agent/.admin.MdmDeviceAdminReceiver
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

All of the above except `lockNow` require **device owner**, and the failure without
it is a `SecurityException` whose message does not mention device ownership.

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
configured. **Removal by stored id is not yet re-verified on hardware** (the
tablet dropped off `adb` before the re-test).

**MAC randomization** (`WifiConfiguration.macRandomizationSetting`) is `@SystemApi`
— not settable by a DO. The policy field is accepted and ignored; not a failure.

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
| Android 14 (34) | Installs blocked below `targetSdk` 23 | — |
| Android 15 (35) | Floor raised to API 24 | — |
| Android 16 (36) | Floor **unchanged** at 24 | Section 5 |
| Android 16 | Advanced Protection Mode blocks user sideloading; enterprise policy control not until Android 17 | Does not affect Device Owner installs — confirmed in production |

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
