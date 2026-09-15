# The agent signing key: custody, rotation, and what happens if it is lost

**Why:** `SEC_AUDIT.md` **H-2**. Android refuses an update signed by a different
key than the installed app. The key in `agent/keystore.properties` is therefore
the fleet's identity: **lose it and no device can ever be updated again** without
a factory reset of every tablet, and the agent's own over-the-air update channel
is the delivery mechanism for everything.

---

## ⚠️ There is exactly one cheap moment, and it is before the first enrolment

Rotating this key costs nothing while **no device has installed a build signed by
it**. After the first enrolment it costs a fleet-wide factory reset, for ever.

That window is open now: the fleet was purged and every device factory reset on
2026-09-15. It closes the moment the first tablet is provisioned.

---

## Rotating

### 1. Generate the new key

```bash
cd agent
keytool -genkeypair -v \
  -keystore atlas-release-NEW.jks \
  -alias atlas \
  -keyalg RSA -keysize 4096 \
  -validity 10950 \
  -dname "CN=TAK-Solutions LLC, O=TAK-Solutions LLC, C=US"
```

⚠️ **30 years (`10950`), not the 25-year default and not less.** The certificate
outliving every device that will ever install a build signed by it is the point;
an expired signing certificate does not stop updates, but it removes the option
of ever proving provenance again.

Choose a passphrase you can retrieve without this machine. It is protecting the
same thing the key is.

### 2. Point the build at it

`agent/keystore.properties` — machine-local, gitignored, never committed:

```properties
storeFile=atlas-release-NEW.jks
storePassword=<the passphrase>
keyAlias=atlas
keyPassword=<the passphrase>
```

### 3. Put a copy somewhere this machine is not

The `.jks` **and** the passphrase, in two places that do not fail together:

- a password manager entry (the passphrase, and the `.jks` as an attachment), and
- an encrypted USB stick or a printed base64 dump kept physically elsewhere.

⚠️ **A backup on the build machine is not a backup.** The failure this guards
against — disk death, theft, ransomware, a reinstall — takes the machine and the
copy together.

⚠️ **Verify you can read both back before step 4.** A key you cannot restore is a
key you have destroyed.

### 4. Rebuild and republish

```bash
cd agent
./gradlew :app:assembleRelease :launcher:assembleRelease
cp app/build/outputs/apk/release/app-release.apk       ../dist/atlas-agent.apk
cp launcher/build/outputs/apk/release/launcher-release.apk ../dist/atlas-launcher.apk
```

⚠️ **Both APKs, not just the agent.** They share this key, and the launcher's
access to the agent's kiosk tiles is a `signature` permission (`SEC_AUDIT.md`
L-4) — two APKs signed by different keys means the tiles stop opening.

Confirm they match each other and not the old key:

```bash
apksigner verify --print-certs ../dist/atlas-agent.apk
apksigner verify --print-certs ../dist/atlas-launcher.apk
```

Both digests must be identical, and different from `2094bccc…` (the retired key).

### 5. Release

Commit the rebuilt `dist/` with a version bump and a raised Android
`versionCode`, per `CLAUDE.md` §9. ⚠️ The seeder treats a repeated `versionCode`
as already present and silently keeps the old build.

### 6. Destroy the old key

Only once a device has enrolled on the new build and taken an update. Until then
the old key is the fallback; after that it is liability.

---

## The recovery position

Written down because the honest answer is short and nobody wants to discover it
during the incident.

| Situation | What you can do |
|---|---|
| Key present, passphrase lost | Nothing. The keystore is useless without it; treat it as lost. |
| Key lost, **no device fielded** | Rotate. Costs one rebuild. |
| Key lost, **devices fielded** | ⚠️ **Every tablet must be factory reset and re-provisioned in person.** There is no remote path: a build signed by a new key is, to Android, a different application, and a Device Owner cannot be replaced over the air. |
| Key stolen, devices fielded | An attacker who also controls a distribution path can sign an agent your devices accept as genuine. ⚠️ ATLAS cannot detect this — the update channel verifies the signature, and the signature is valid. Recovery is the row above, plus rotating everything else. |

**There is no revocation for this.** Android checks that the signature matches
the installed app; it does not consult anything that could say "not any more".

---

## Why this is not solved by the offline-root work

`SEC_AUDIT.md` S-2 takes the *device CA* root off the server, and device
certificates renew themselves, so that key's compromise now ends. This one is
different in kind:

- it lives on a **build machine**, not the server, so the server's hardening does
  nothing for it;
- it is used **rarely and by hand**, so there is no automation to bound its
  exposure;
- and there is **no rotation path at all** once devices are fielded, which is the
  property the CA no longer has.

Custody is the whole control. That is why the recovery position is written down
rather than assumed.
