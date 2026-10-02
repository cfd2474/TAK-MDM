# Bundled applications

The two applications a deployment cannot usefully start without, shipped with
the source so that an install has them without a manual upload.

| File | Package | Why it is here |
|---|---|---|
| `atlas-agent-knox.apk` | `com.taksolutions.atlasmdm` | The Device Policy Controller, the **only** agent build shipped (W309). A tablet downloads it during out-of-box setup, and the provisioning QR carries **this file's** signing checksum, so with nothing uploaded no QR can be generated at all. It's the knox flavour: it uses Samsung Knox where present and falls back to plain AOSP behaviour on other hardware (see `docs/KNOX.md` §3.2). Its versionCode is odd (base + 1). The aosp flavour still exists in Gradle but is no longer built or bundled. |
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

    cd agent && ./gradlew :app:testKnoxReleaseUnitTest :app:assembleKnoxRelease :launcher:assembleRelease
    cp app/build/outputs/apk/knox/release/app-knox-release.apk ../dist/atlas-agent-knox.apk
    cp launcher/build/outputs/apk/release/launcher-release.apk ../dist/atlas-launcher.apk

⚠️ Don't copy an aosp build back in as `atlas-agent.apk`. `tests/test_seed_packages.py`
fails if that file exists (W309).
