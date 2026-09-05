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

Toggle **Add to store** on a package to list it in the **ATLAS store** tab. The
store is a curated "ready to assign" set — it does not install anything by itself.

## App groups

Create an **app group** to name a set of packages. In a policy's App Management
section, the *"Insert an app group"* control drops the group's packages into
`required_apps` for you.

## Deploying

Add the package to a policy's **App Management** section (`required_apps`) and
assign the policy. The agent installs it silently under Device Owner privilege on
the next check-in.
