# Upload and deploy an app

## Upload

On the **Apps** page, **Local apps** tab, choose an `.apk`, `.xapk`, `.apks` or
`.apkm` and press **Upload**. The server:

- reads the package name, version code and signing certificate from the file
  itself — form fields cannot lie about what an APK is;
- pins the signing certificate on first upload (an update signed by a different
  key will fail on the device, so it is rejected here where the error is legible);
- unpacks an XAPK into base + splits + OBB, each stored content-addressed.

To get an app from Google Play, TAK.gov, the TAKWERX catalog or another
repository instead, see
[Get apps from Google Play, TAK.gov and the plugin catalogs](/guides/howto/app-sources).

When an update-check alert finds a newer build of a library app, the app shows an
**update available** badge under its version on **Local apps**. Click it to open
the catalog to import the update. The badge goes away when the newer build is in
the library.

**Plugins that carry an app.** Some ATAK plugins carry an app of their own inside
them. When you upload or import such a plugin, ATLAS adds that app to the library
too, labeled **Companion of** the plugin. A policy that installs the plugin also
installs its companion, just before the plugin, so the device's user is never
asked.

## The ATLAS store

A **storefront** is a named shelf of apps a user may install for themselves.
Build one on the **Apps** page, **ATLAS store** tab, choosing the exact build of
each app it offers.

A policy names **one** storefront — a device has one store, not several. Choose
it under **App Management › ATLAS store**.
⚠️ Two policies on the same device naming different storefronts is reported as a
conflict: the higher-ranked one wins and the other's apps are simply not
offered. Where both list the same app at different builds, the losing build is
not a fallback — it is unreachable.

The store installs nothing by itself; it is what the device's user may choose. A
multi-app kiosk can offer it too: see [Put a device in kiosk mode](/guides/howto/kiosk).

## App groups

Create an **app group** on the **Apps** page, **App groups** tab, to name a set of
packages. In a policy's **App Management › Required apps**, the row *"Add an app
group to Required apps"* has a button for each group; press one to add its
packages. A group of ATAK plugins has the same row under **ATAK Core and
Plugins**.

## Deploying

Add the package to a policy's **App Management** section, under **Required
apps**, and assign the policy. The agent installs it silently under Device Owner
privilege on the next check-in.

⚠️ **Pick the build.** A policy names the exact build it installs, defaulting
to the newest at the time you add it. Uploading a newer version does not move a
fleet; editing the policy does. An entry that names no build resolves to
nothing rather than to the newest one.

**Or keep it current.** Choose **Always the newest build** at the top of the
build list, and each device gets the newest build in the library that it can
run: builds needing a newer Android or another CPU type are skipped. A newer
upload reaches those devices at their next check-in, with no policy edit. This
is set per app, in the policy, never on the library.

To take an app off devices when no policy requires it any more, see **Uninstall
if withdrawn** in [Build a policy](/guides/howto/building-a-policy).

## ATAK and its plugins

ATAK and its plugins are not set under Required apps. They have their own **ATAK
Core and Plugins** section:

1. Choose ATAK Core.
2. Choose its **ATAK version**. Only versions with a build of that ATAK in your
   library are offered, newest first.
3. Choose the build. **Always the newest build of** a version stays within that
   version: a newer ATAK version in the library does not move devices. Change the
   version in the policy when you are ready to move.
4. Add plugins. Each is version-checked against the chosen ATAK, and a plugin
   set to **Always the newest build** follows that ATAK version too.
