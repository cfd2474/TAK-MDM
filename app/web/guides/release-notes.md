# Release notes

Newest first. ATLAS — ATAK Tactical Lifecycle & Administration System, by
TAK-Solutions LLC.

## Console overhaul (W1–W9)

- **Eight-section console**: Enroll, Manage, Policies, Apps, Content, Reports,
  Admin, Guides — themed to the ATLAS banner, still server-rendered Jinja with no
  build step.
- **Manage**: fleet table with device name, serial, model, reaching policies,
  version and convergence; client-side filter and sort. Devices can be named.
- **Policies**: Device / Templates / Archived tabs, a New Policy modal, and a
  guided **composite policy creator** — one named policy with a category rail
  (password, restrictions, app management, file management wired; ~12 more as
  placeholders). Templates and archive/restore.
- **Apps**: local packages, an ATLAS store flag, and app groups.
- **Content**: managed files with per-policy deployment shown, and editable
  deployment defaults.
- **Reports**: fleet inventory, convergence & compliance, policy deployment,
  command history, app inventory, marketplace selections — each downloadable as
  CSV.
- **Admin**: certificate list with per-cert revoke, EULA / SMTP / AD / SMS /
  geofencing settings, and operator-defined custom device attributes.
- **Guides**: this section.

## Earlier

The server, agent and protocol work (stacked policies, enrolment and mTLS,
desired-state check-in, the APK/XAPK pipeline, the managed-file marketplace, the
Device Owner agent, kiosk, remote diagnostics, multi-identifier device identity,
the single persistent enrollment token) predates this console overhaul and is
recorded in the project history.
