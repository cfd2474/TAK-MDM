# Bundled applications

The two applications a deployment cannot usefully start without, shipped with
the source so that an install has them without a manual upload.

| File | Package | Why it is here |
|---|---|---|
| `atlas-agent.apk` | `com.taksolutions.atlasmdm` | The Device Policy Controller. A tablet downloads it during out-of-box setup, and the provisioning QR carries **this file's** signing checksum — so with nothing uploaded, no QR can be generated at all. |
| `atlas-agent-knox.apk` | `com.taksolutions.atlasmdm` | The same agent built with Samsung Knox support: same package, same key, versionCode one higher (odd, where the plain build is even) and the same version name. **The seeder publishes this one as the fleet build**, because it is the highest code. On non-Samsung hardware it behaves exactly as the plain build. See `docs/KNOX.md` §3.2. |
| `atlas-launcher.apk` | `com.taksolutions.atlaslauncher` | The ATLAS home screen. Policies assign it; it is not installed on a device unless a policy says so. |
| `atlas-atak-plugin-<atak>.apk` | `com.taksolutions.atlasmdm.atak` | The ATLAS ATAK plugin, one build per ATAK line (W300). Installed automatically wherever a policy installs ATAK, with the build for that ATAK's line. **Signed by the TAK Product Center, not with the ATLAS key**: certificate SHA-256 `f24a3805…bb8c17`. These come back from TPC signing and are copied in, never rebuilt here. |

⚠️ **These are release build outputs, committed on purpose.** `.gitignore`
excludes `agent/*/build/`, which is right for build products — but these two are
release *artifacts* of the tagged version, and an InfraTAK module installs by
cloning this repository at a tag. There is nowhere else for them to come from:
the box has no Android toolchain, and a private repository's release assets
cannot be fetched with the read-only SSH deploy key the module uses.

Both are signed with the release key. `app/services/packages.py` refuses a build
whose signing certificate does not match the one already stored for that
package, so a mismatched rebuild is rejected rather than silently shipped.

## Updating them

Rebuild, then copy in — **the version code must increase**, or the seeder treats
the build as already present and leaves the old one in place:

    cd agent && ./gradlew :app:assembleRelease :launcher:assembleRelease
    cp app/build/outputs/apk/release/app-release.apk ../dist/atlas-agent.apk
    cp launcher/build/outputs/apk/release/launcher-release.apk ../dist/atlas-launcher.apk
