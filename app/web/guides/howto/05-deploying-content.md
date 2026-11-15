# Deploy files to devices

Use **Content** for anything that is not an app: map sources, `.pref` files,
certificates, DTED archives.

## Upload

On the **Content** page, under **Upload a file**, choose a file and press
**Upload**. Zips are detected at upload so a policy can mark them for extraction.

Every upload opens a dialog with its progress, speed and time left, then what the
server is doing with the file. **Cancel** stops it. If an upload fails, the dialog
says why.

Every item on the Content page has a **Download** button. It saves the file
exactly as ATLAS holds it and sends it to devices.

## Where a file goes

A file has no destination of its own — that lives on the **File management**
policy entry that places it. On the Content page, **Deployed by** lists every
policy that deploys a file and where, including policies that deliver data
packages and DTED archives.

Each file can also store suggested deployment defaults, under **Metadata &
suggested deployment defaults**. The policy editor does not fill them in for you:
set the destination on each policy entry.

## Key settings on the policy entry

- **Destination** — an absolute device path. Must be under `/sdcard/` or
  `/storage/emulated/0/`; `/atak/imagery` resolves to the unwritable filesystem
  root and is rejected at publish.
- **required** or **optional (marketplace)** — required is installed; optional
  is offered in the agent's in-app marketplace, and the user chooses.
- **persist** — **persist: yes** re-pushes the file whenever it is missing or the
  wrong size; **persist: no** places it once. Left at **persist: from tier**, a
  required file is kept present and an optional one is placed once.
- **extract** and **Extract to** — unzip an archive into a directory instead of
  landing it as a `.zip`. Extract to defaults to the destination.
- **overwrite** (the last choice on the row) — what happens when a file is
  already there: **if_newer** replaces it only if the new one is newer (the
  default), **always** replaces it every time, and **if_absent** places it only
  if nothing is there yet.

The MDM never deletes a managed file from a device — deployment is write-only.

## Data packages and DTED

The File management category has two entry kinds besides plain files:

- **ATAK data packages** — a TAK data package (`.zip`) is validated on upload and
  delivered to ATAK, which imports it. ⚠️ ATAK does not delete the package after
  importing, and delivery is once per device rather than on every check-in.
- **ATAK DTED** — terrain archives, unpacked into the DTED tree rather than
  landed as a zip.

On the Content page, under **ATAK data packages**:

- **Upload packages you already have** takes one zip or several. Several are
  uploaded and checked one at a time, and each is named from its own manifest.
- **Create data package** builds one from files you choose.
- ⚠️ **Duplicates are caught.** Uploading a package the library already holds
  with different contents (same name, or the same ID in its manifest) asks what
  to do. **Replace** keeps the library entry and every policy that uses it, and
  swaps in the new contents; devices on those policies receive the new version
  once, at their next check-in. The dialog says how many policies that reaches.
- **Show on the map when imported** decides whether a package's overlays show on
  ATAK's map when ATAK imports it.
