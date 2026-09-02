# Enrol a device

ATLAS enrols an Android device as a **Device Owner** during the out-of-box setup
wizard. Device Owner cannot be established after setup, so the device must be at
factory-reset state.

## Steps

1. Open the **Enroll** page. If there is no active enrollment token, create one —
   optionally scoping it to the groups and tags an enrolling device should join.
2. Fill in the Wi-Fi network the device should use during provisioning, then press
   **Generate enrollment QR**. The QR is a 15-minute derivative of the persistent
   token, so a photo of it stops working after 15 minutes regardless of how long
   the token itself lives.
3. On the factory-reset device, tap the first setup-wizard screen six times in the
   same spot to open the QR scanner. Scan the code.
4. The device joins Wi-Fi, downloads the agent, installs it as Device Owner, and
   checks in. It appears on the **Manage** page within a few seconds.

## After enrolment

- Give the device a friendly name on its detail page.
- Assign it a policy (or add it to a group that already has one).
- Re-enrolment after a wipe re-adopts the same record — identity is matched on a
  set of identifiers, not a single serial.
