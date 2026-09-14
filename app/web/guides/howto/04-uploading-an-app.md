# Upload and deploy an app

## Upload

On the **Apps** page, **Local apps** tab, choose an `.apk`, `.xapk`, `.apks` or
`.apkm` and press Upload. The server:

- reads the package name, version code and signing certificate from the file
  itself — form fields cannot lie about what an APK is;
- pins the signing certificate on first upload (an update signed by a different
  key will fail on the device, so it is rejected here where the error is legible);
- unpacks an XAPK into base + splits + OBB, each stored content-addressed.

## The ATLAS store

A **storefront** is a named shelf of apps a user may install for themselves.
Build one on the **Apps** page, **ATLAS store** tab, choosing the exact build of
each app it offers.

A policy names **one** storefront — a device has one store, not several.
⚠️ Two policies on the same device naming different storefronts is reported as a
conflict: the higher-ranked one wins and the other's apps are simply not
offered. Where both list the same app at different builds, the losing build is
not a fallback — it is unreachable.

The store installs nothing by itself; it is what the device's user may choose.

## App groups

Create an **app group** to name a set of packages. In a policy's App Management
section, the *"Insert an app group"* control drops the group's packages into
`required_apps` for you.

## Deploying

Add the package to a policy's **App Management** section, under **Required
apps**, and assign the policy. The agent installs it silently under Device Owner
privilege on the next check-in.

⚠️ **Pick the build.** There is no "latest" — a policy names the exact build it
installs, defaulting to the newest at the time you add it. Uploading a newer
version does not move a fleet; editing the policy does. An entry that names no
build resolves to nothing rather than to the newest one.

ATAK and its plugins are not set here: they have their own **ATAK Core and
Plugins** section, where the ATAK version is chosen first and plugins are
version-checked against it.
