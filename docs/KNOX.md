# Samsung Knox in ATLAS

**Read this before planning or writing any Knox code, and before answering a
question about what Knox will or will not let ATLAS do.**

## Scope, honestly stated

Knox is **additive and never load-bearing**. The AOSP path is the product; every
Knox capability sits behind `OemPolicyApplier` with a working non-Knox answer on
the other side. A device with no licence, a non-Samsung device, and a device whose
activation failed all keep working — degraded, and saying so.

Statements here are labelled:

* 📖 **Documented** — from Samsung's own developer or admin documentation.
* 🧠 **Inferred** — a reading, not a quote. Flagged because it has not been
  confirmed by Samsung and in one case is a legal question, not a technical one.
* ❌ **Ruled out** — checked and does not exist.

Nothing here is ✅ verified on hardware yet. **No Knox code has been written.**

---

## 1. Two paths, and why the SDK wins here

| | Knox SDK | Knox Service Plugin (KSP / OEMConfig) |
|---|---|---|
| How policy arrives | Direct Java calls into Samsung's framework from our DPC | Managed app configuration delivered to Samsung's KSP app |
| Google Play | 📖 **None** — activation talks to Samsung's licence server over ordinary network | 📖 **Managed Google Play documented as a requirement** |
| Build-time dependency | A stub jar (see §3) | None |
| Who maintains the policy surface | Us | Samsung |

ATLAS deliberately has **no managed Google Play** (D11 — sideloaded APK/XAPK
only). That single constraint decides it: **the SDK is the path.** KSP would drag
in the exact dependency the project exists to avoid.

---

## 2. Licensing — the part that is better than expected

📖 **Knox Platform for Enterprise (KPE) Premium is free.** Samsung retired the
Standard/Premium split; Premium is now no-cost. Only Knox DualDAR and Knox UCM
remain paid.

📖 **The end customer generates their own key**, self-service, in the Knox Admin
Portal → *Licenses → Manage license keys → Generate Knox Platform for Enterprise
Premium license key*. **No EMM-vendor partnership is required** for their key to
work.

📖 Activation is `KnoxEnterpriseLicenseManager.activateLicense(key)`. The result
arrives on the broadcast `com.samsung.android.knox.intent.action.KNOX_LICENSE_STATUS`
with `EXTRA_LICENSE_ERROR_CODE` and `EXTRA_LICENSE_GRANTED_PERMISSIONS` — the
Knox `signature`-level permissions are granted **to the calling package** at
activation. That is the mechanism by which a non-Samsung-signed app may call Knox
APIs at all.

📖 Activation requires network access to Samsung's licence server (error codes
include `ERROR_NETWORK_DISCONNECTED`). It does **not** involve Google.

> ⚠️ This makes **R3 largely stale.** A Knox *developer* account is needed to
> download the SDK — a build-time concern for whoever compiles the agent. A Knox
> *partner* agreement is **not** needed for customers to license their devices.
> R3 as written ("gates KME and KPE") overstates the block for KPE. KME is a
> separate question and still needs looking at.

---

## 3. Distribution — who needs what

📖 Samsung's own setup instructions are:

```gradle
runtimeOnly  files('libs/supportlib.jar')      // Knox <= 2.7.1 backwards compat only
compileOnly  files('libs/knoxsdk.jar')         // the SDK itself
```

`knoxsdk.jar` is **`compileOnly`** — a stub. The real implementation lives in
Samsung's device firmware. It is **not packaged into the APK**.

**Skip `supportlib.jar`.** It is `runtimeOnly` (i.e. it *would* ship inside the
APK) and exists only for the legacy ELM key path on Knox ≤ 2.7.1. This fleet is
Knox 3.x on Android 15/16, so it is not needed — and leaving it out keeps the APK
free of Samsung binaries entirely, which is what makes §3.1 clean.

### 3.1 What that means for a self-hosted product

| Who | Knox SDK? | Knox developer account? | KPE key? |
|---|---|---|---|
| Whoever builds the APK (us) | Yes | Yes | No |
| **Operator running a published APK** | **No** | **No** | Yes — free, self-service |
| Operator building from source *with* Knox | Yes | Yes | Yes |

🧠 **Inferred:** because no Samsung code lands in the binary, publishing a
Knox-enabled APK is not "redistributing the Licensed Software", and the SDK
agreement's redistribution clause does not bite on the release artifact. This
matches how every commercial MDM ships. **It is a legal reading, not a verified
fact — see §7.**

### 3.2 Build layout

Gradle product flavours, so the repo builds for someone who has never heard of
Knox:

* **`aosp`** — no Knox source set, no jar. `./gradlew assembleAospRelease` works
  on a fresh clone and produces today's agent.
* **`knox`** — adds `src/knox/kotlin/` and `compileOnly files('libs/knoxsdk.jar')`
  (gitignored). Fails with a clear message if the jar is absent.

Publish **both** APKs in releases. Nobody but us touches a Samsung download.

---

## 4. What Knox actually buys — assessed against the API reference

The SDK spans 49 packages. What matters is which of them do something AOSP
cannot, and which are being retired.

### 4.1 Genuine wins, no AOSP equivalent

| Package / class | Capability |
|---|---|
| `net.firewall.Firewall` | Per-app and device-wide IP allow/deny/**redirect**, domain filtering via DNS blocking, proxy redirection, raw iptables listing, blocked-domain reports. **The single biggest win.** DO/PO-gated from API 39. |
| `net.vpn.GenericVpnPolicy` | **Per-app VPN routing** (`addPackagesToVpn`). AOSP gives one always-on app and nothing granular. |
| `restriction.RestrictionPolicy` | USB **class** exception lists, Settings-app lockdown, mic/camera/headphone/home-key control. Well past `UserManager.DISALLOW_*`. |
| `keystore`, `zt.devicetrust.cert` | Remote certificate provisioning, SCEP/ACME scopes. Directly relevant to the TAK cert-enrolment pack. |
| `integrity` | Hardware-rooted device attestation. |
| `log` | Forensic event logs off the device. |
| `location` | Geofencing — the Admin section already has a placeholder for it. |
| `net.wifi`, `net.apn` | Enterprise Wi-Fi (EAP/certs) properly, rather than the deprecated `WifiConfiguration` we are grandfathered into (§6d of the platform reference). |
| `application.ApplicationPolicy` | Battery-optimisation allow-list (one of our permission-wizard steps), force-stop blacklist, signature-based app allow/deny. |

### 4.2 ❌ Walls Knox does **not** close

These were hoped for and are ruled out. Recorded so nobody re-litigates them.

| Wall | Why Knox does not fix it |
|---|---|
| **All-files access app-op** (R1's one-tap grant) | `ApplicationPolicy.applyRuntimePermissions()` is deprecated at API 30 and **unavailable since Android 12**. Samsung stepped back because AE covers runtime permissions — and that still never reached app-ops. |
| **VPN without a client app** (W14) | `GenericVpnPolicy` still **binds to a third-party VPN vendor app**; it does not implement IPsec/L2TP itself. Per-app routing is the gain, not built-in profiles. |
| **OS device name** (W24) | No `setDeviceName` anywhere. `custom.SettingsManager` is a fixed allow-list of ~40 toggles and **cannot write arbitrary secure/global settings**. Device naming is **Knox Configure**, a separate provisioning product. |
| **XAPK OBB placement** (R2) | Nothing in the SDK addresses another app's `Android/obb`. Not re-checked in depth, but no package looks like a candidate. |

### 4.3 The deprecation trend — read this before choosing a feature

📖 Samsung is aggressively retiring the parts of the SDK that overlap with Android
Enterprise. Dead or dying on modern Android:

* `applyRuntimePermissions` — gone since Android 12
* **ProKiosk** (`custom.ProKioskManager`) — deprecated API 35, **not available
  since Android 14**, so gone on our One UI 8 fleet
* `custom.SystemManager` / `custom.SettingsManager` — heavily deprecated
* `ApplicationPolicy.setApplicationRestrictions`, `changeApplicationName/Icon` —
  deprecated API 35
* `ex.peripheral.PeripheralManager` — removed entirely in Knox 3.11
* Containers/workspaces, legacy Email/Exchange/LDAP accounts, split billing — removed

Roughly a third of the legacy surface. 📖 Knox APIs are also now restricted to
**Device Owner / Profile Owner apps only** (Knox 3.11 on Android 15, all APIs by
3.12 on Android 16) — ATLAS is a Device Owner, so this is fine.

**Selection rule:** build against the things Android Enterprise never attempted
(§4.1). Anything that looks like a nicer version of an AE feature is a bad bet and
will be deprecated under us.

---

## 5. Operator walkthrough (once Chunk 7 lands)

What a downstream operator does, beyond the normal ATLAS setup in the README:

1. Sign in to the **Knox Admin Portal** (free account).
2. *Licenses → Manage license keys → Generate KPE Premium key.* Copy it.
3. In ATLAS: **Admin → Knox** → paste the key → Save.
4. Upload the **`knox`-flavour agent APK** (from ATLAS releases) instead of the
   `aosp` one, and set `TAKMDM_AGENT_SIGNATURE_CHECKSUM` from the upload response
   as usual.
5. Enrol devices normally (QR / Knox Mobile Enrollment).

On its first check-in each device receives the key in its desired state, calls
`activateLicense`, and reports the outcome. The console shows **Knox: active** on
the device page; the ATLAS MDM app shows it on its Device tab. On failure — bad
key, no network, non-Samsung hardware — the agent reports the error and falls back
to the AOSP path.

The **Knox** policy category then stops being a placeholder.

---

## 6. Chunk 7 shape

See `PROJECT_STATE.md` for the tracked plan. In outline:

1. Gradle `aosp` / `knox` product flavours; gitignored `libs/knoxsdk.jar`; the
   `aosp` build must stay the default and stay green.
2. `knox_license_key` admin setting → desired state → agent activation → status
   reported back and surfaced in both consoles.
3. A `KNOX` policy type in the registry + the creator-catalog category wired.
4. **Firewall first** — the highest-value capability with no AOSP equivalent —
   end-to-end through `OemPolicyApplier`, proving the seam.
5. This document's §5 promoted into the README, plus release artifacts for both
   flavours.

---

## 7. Open questions for Samsung

To be settled as part of the express-approval conversation. The first is the only
one that could change the distribution model.

1. **May we distribute a compiled APK built against the Knox SDK to third
   parties**, as a self-hosted open-source product, where those parties supply
   their own KPE keys? (§3.1 is our reading, not Samsung's word.)
2. Do downstream operators need **any** relationship with Samsung beyond
   generating a free KPE Premium key?
3. Is there any **app registration or allow-listing** required for a package to
   activate a KPE licence, or is a valid key sufficient?
4. Is **Knox Mobile Enrollment** available to a self-hosted EMM, and what does it
   require? (This is the part of R3 that is *not* stale.)

**If (1) is a no**, the fallback is bounded: operators who want Knox build the
`knox` flavour themselves with their own free developer account. Everyone else
runs `aosp`, which is the whole product. The flavour split in §3.2 is worth doing
either way.

---

## Sources

* [Knox SDK API reference — packages](https://docs.samsungknox.com/devref/knox-sdk/reference/packages.html)
* [Knox SDK — deprecated API methods](https://docs.samsungknox.com/dev/knox-sdk/api-reference/deprecated-api-methods/)
* [Knox Platform for Enterprise licenses](https://docs.samsungknox.com/admin/knox-platform-for-enterprise/before-you-begin/knox-platform-for-enterprise-licenses/)
* [Knox SDK licensing FAQ](https://docs.samsungknox.com/dev/knox-sdk/faq/licensing/)
* [Install the SDK](https://docs.samsungknox.com/dev/knox-sdk/get-started/install-the-sdk/)
* [`KnoxEnterpriseLicenseManager`](https://docs.samsungknox.com/devref/knox-sdk/reference/com/samsung/android/knox/license/KnoxEnterpriseLicenseManager.html)
* [`Firewall`](https://docs.samsungknox.com/devref/knox-sdk/reference/com/samsung/android/knox/net/firewall/Firewall.html)
* [`GenericVpnPolicy`](https://docs.samsungknox.com/devref/knox-sdk/reference/com/samsung/android/knox/net/vpn/GenericVpnPolicy.html)
* [`ApplicationPolicy`](https://docs.samsungknox.com/devref/knox-sdk/reference/com/samsung/android/knox/application/ApplicationPolicy.html)
* [`RestrictionPolicy`](https://docs.samsungknox.com/devref/knox-sdk/reference/com/samsung/android/knox/restriction/RestrictionPolicy.html)
* [`custom.SettingsManager`](https://docs.samsungknox.com/devref/knox-sdk/reference/com/samsung/android/knox/custom/SettingsManager.html)
* [Knox SDK Agreement](https://seap.samsung.com/content/knox-sdk-agreement)
