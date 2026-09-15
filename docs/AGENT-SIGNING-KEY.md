# The agent signing key: custody, rotation, and what happens if it is lost

**Why:** `SEC_AUDIT.md` **H-2**. Android refuses an update signed by a different
key than the installed app. The key in `agent/keystore.properties` is therefore
the identity of every fleet at every customer: **lose it and no device can be
updated again** without factory-resetting every tablet, and the agent's own
over-the-air channel is how everything else is delivered.

---

## ⚠️ ATLAS has its own key. Never share it with a Play app.

| | |
|---|---|
| ATLAS signing key | `c037760255391d7ffca1fb6137490db1d56267c0caf4949a66028ff12d1b876b` |
| **Google Play key — never use for ATLAS** | `2094bccc054c681f46d8c812378c07657cf339dd7d4e80b546026b77aff2c644` |

Until v1.34.0 the build used `D:/Code/ANDROID/APK Keys/AppSign.jks` — a
general-purpose workstation keystore that **also signs an app published on
Google Play** (confirmed against the Play Console, 2026-09-15). One secret
therefore stood behind two unrelated trust domains: a Play listing, and the
Device Owner on every customer's fleet. A compromise of either was a compromise
of both.

⚠️ **Play App Signing does not protect the agent, and it is easy to assume it
does.** The agent is sideloaded by a Device Owner during provisioning and is
never installed from Play. Whatever key signs the file in `dist/` is what
devices pin; Google holding an app signing key protects the listing and nothing
about the fleet.

`tests/test_signing_key.py` fails if anything in `dist/` carries the Play
fingerprint. It reads the signature with `app.artifacts.apk.extract_signature`
— the same function the upload path uses — so it needs no Android SDK and runs
in CI. ⚠️ A first version shipped its own parser of the APK Signing Block. It
agreed exactly, and was still wrong to exist: two implementations of one format
drift, and the copy with no production traffic drifts first.

---

## ⚠️ There is exactly one cheap moment, and it is before the first enrolment

Changing this key costs nothing while **no device has installed a build signed
by it**. After the first enrolment it needs `apksigner rotate` and a signing
certificate lineage — which requires the old key, and every device to have
accepted the lineage first.

That window is open now: the fleet was purged on 2026-09-15. It closes the
moment the first tablet is provisioned.

---

## Generating a replacement

```bash
keytool -genkeypair -v \
  -keystore "D:/Code/ANDROID/ATLAS Signing/atlas-release.jks" \
  -alias atlas \
  -keyalg RSA -keysize 4096 \
  -validity 18250 \
  -dname "CN=ATLAS Agent Signing, O=TAK-Solutions LLC, C=US"
```

⚠️ **Its own directory, not the shared `APK Keys` folder.** A key that lives
among general-purpose ones gets used as one — which is exactly how this became a
finding.

Then point `agent/keystore.properties` (gitignored) at it, and **back the
keystore and its passphrase up somewhere this machine is not**: an encrypted USB
stick, or a password manager entry with the `.jks` attached. ⚠️ A backup on the
build machine is not a backup — disk death, theft and ransomware take the
machine and the copy together.

---

## Rebuilding after any key change

```bash
cd agent
./gradlew :app:assembleRelease :launcher:assembleRelease
cp app/build/outputs/apk/release/app-release.apk           ../dist/atlas-agent.apk
cp launcher/build/outputs/apk/release/launcher-release.apk ../dist/atlas-launcher.apk
```

⚠️ **Both APKs, always.** They share this key, and the launcher reaches the
agent's kiosk tiles through a `signature` permission (`SEC_AUDIT.md` L-4). Two
APKs signed by different keys means the tiles silently stop opening.

⚠️ **Raise both `versionCode`s.** The seeder treats a repeated code as already
present and keeps the old build, so a re-signed APK at the same code ships
nothing. A re-signed artifact is a new identity even when no source changed.

Then confirm:

```bash
python -m pytest tests/test_signing_key.py -q
```

---

## ⚠️ A key change is refused by every deployment that already has the old one

Before the lineage question, there is one that bites first and is easy to miss.

The seeder **refuses** an APK whose signing certificate differs from the one
already stored for that package — correctly, because Android would reject it as
an update. So on any deployment that has already seeded the old build:

```
seed: atlas-agent.apk not loaded — signing certificate for com.taksolutions.atlasmdm
does not match the stored one (have 2094bccc…, got c037760…).
```

The release updates, the library keeps the **old** agent, and devices go on
being offered it.

⚠️ **This was observed on a real install, not imagined.** It is also why
v1.35.0 surfaces the refusal in Admin → Agent updates: until then it existed
only in `docker logs`, so the console reported the old agent as current and
nothing anywhere suggested otherwise.

**What to do depends on whether a fleet exists:**

| | |
|---|---|
| **No device enrolled** | Delete the package from the Apps page and let it re-seed, or uninstall and reinstall. Nothing is lost. |
| **Devices in the field** | Deleting does not help — the *devices* hold the old signature, not just the library. You need `apksigner rotate` and a lineage, below. |

---

## Rotating once devices *are* fielded

Possible, and narrower than it sounds — but it needs the old key.

`apksigner rotate` builds a **signing certificate lineage**, and rotated keys
are accepted by default on **Android 13+**. `minSdk` here is 33, so every device
in the fleet qualifies and no `--rotation-min-sdk-version` is needed.

```bash
apksigner rotate --out lineage.bin \
  --old-signer --ks old.jks \
  --new-signer --ks new.jks
```

⚠️ **An earlier version of this page said there was "no rotation path at all
once devices are fielded".** That was wrong, and wrong in a way that mattered:
it made the catastrophe sound broader than it is. Wanting to rotate is
recoverable. **Losing the key is not** — without it there is no lineage, and
nothing else can stand in.

---

## The recovery position

| Situation | What you can do |
|---|---|
| Key present, passphrase lost | Nothing. The keystore is useless without it; treat it as lost. |
| Key lost, **no device fielded** | Generate a new one. Costs one rebuild. |
| Key lost, **devices fielded** | ⚠️ **Every tablet factory reset and re-provisioned in person.** No remote path exists: to Android a differently-signed build is a different application, and a Device Owner cannot be replaced over the air. |
| Key present, want to change it, devices fielded | `apksigner rotate` with a lineage, as above. |
| Key stolen, devices fielded | An attacker with a distribution path can sign an agent the fleet accepts. ⚠️ ATLAS cannot detect this — the update channel verifies the signature, and the signature is valid. Rotate with a lineage, and treat every fielded device as suspect. |

**There is no revocation.** Android checks that the signature matches the
installed app; nothing can say "not any more".

---

## Why the offline-root work does not cover this

`SEC_AUDIT.md` S-2 takes the *device CA* root off each customer's server, and
v1.33.0 made that two clicks. This key is different in kind:

- it lives on a **build machine**, so nothing done to a customer's server
  touches it;
- it is **shared across every customer**, so its blast radius is the product
  rather than one deployment;
- and it is used **by hand, rarely**, so there is no automation to bound its
  exposure.

Custody is the entire control, which is why the recovery position is written
down rather than assumed.
