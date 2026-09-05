# Deploy files to devices

Use **Content** for anything that is not an app: map sources, `.pref` files,
certificates, DTED archives.

## Upload

On the **Content** page, choose a file and press Upload. Zips are detected at
upload so a policy can mark them for extraction.

## Where a file goes

A file has no destination of its own — that lives on the **FILES** policy entry
that places it. On the Content page each file lists every policy that deploys it
and where. You can set **deployment defaults** (destination, persist, extract)
that the policy editor pre-fills.

## Key settings on the policy entry

- **dest_path** — an absolute device path. Must be under `/sdcard/` or
  `/storage/emulated/0/`; `/atak/imagery` resolves to the unwritable filesystem
  root and is rejected at publish.
- **availability** — `required` (installed) or `optional` (offered in the agent's
  in-app marketplace, user chooses).
- **persist** — `on` re-pushes the file whenever it is missing or the wrong size;
  `off` places it once. Defaults from the tier.
- **extract** / **extract_to** — unzip an archive into a directory instead of
  landing it as a `.zip`.

The MDM never deletes a managed file from a device — deployment is write-only.
