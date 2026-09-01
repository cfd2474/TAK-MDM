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

## 7. Kiosk and lock task

📖 `setLockTaskPackages(admin, packages)` then `startLockTask()`. Available to a
Device Owner without any launcher role.

**Design note:** adding kiosk to a background agent is two API calls; removing
launcher behaviour from a launcher is a rewrite. This agent declares no
`category.HOME` and engages lock task only when a policy sets `kiosk_package` (F6).

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
* [Android minimum targetSdk matrix — Jason Bayton](https://bayton.org/android/android-minimum-targetsdk-matrix/)
* [Advanced Protection Mode](https://developer.android.com/privacy-and-security/advanced-protection-mode)
* [Knox SDK deprecation policy](https://docs.samsungknox.com/dev/knox-sdk/faq/general/)
* [Log info disclosure](https://developer.android.com/privacy-and-security/risks/log-info-disclosure) — `READ_LOGS` restriction, and the "manage your own logs" recommendation
* [Security — Android Enterprise](https://developer.android.com/work/dpc/security) — security logging for device owners

## Maintaining this file

Add to it whenever hardware teaches something the code did not already encode, and
mark it ✅. Correct it whenever an official source contradicts an entry — but keep
the observation and note the disagreement rather than deleting it. A documented
claim that our hardware disproves is more valuable recorded than silently removed.
