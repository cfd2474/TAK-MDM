# Enrol a device

ATLAS enrols an Android device as a **Device Owner** during the out-of-box setup
wizard. Device Owner cannot be established after setup, so the device must be at
factory-reset state.

## Steps

1. Open the **Enroll** page. If there is no active enrollment token, create one —
   optionally scoping it to a group the enrolling device should join. A device
   that joins a group picks up that group's policies on its first check-in, with
   no second step.
2. Fill in the Wi-Fi network the device should use during provisioning, then press
   **Generate enrollment QR**.

   By default the QR is a **15-minute derivative** of the enrollment token, so a
   photograph of the code stops working after 15 minutes however long the token
   itself lives.

   Tick **Make this QR permanent** for a code that never expires. Re-generating
   gives the identical image, so it can be printed and left on a provisioning
   bench for bulk onboarding — use **Save QR** to download it. ⚠️ The trade is
   the point of the 15-minute default: a permanent QR is a picture that stays a
   live credential, so anyone who photographs it can enrol devices until the
   token is retired. **Retire & create new** on the Enroll page is how that is
   undone.
3. On the factory-reset device, tap the first setup-wizard screen six times in the
   same spot to open the QR scanner. Scan the code.
4. The device joins Wi-Fi, downloads the agent, installs it as Device Owner, and
   checks in. It appears on the **Manage** page within a few seconds.

## Groups are chosen on the QR, not the token

The enrollment token has no group setting. When you generate a QR you pick the
group the device should land in, and that choice belongs to the QR.

⚠️ This used to be offered in both places, which meant one decision could be
made twice and differently. The QR is the one that decides.

## Getting a permanent QR back

Permanent codes you have generated are listed on the Enroll page. **Show QR**
draws the same code again — you do not have to remember which group or which
Wi-Fi it was made with, and re-typing those from memory would have produced a
*different* code with nothing on screen to say so.

⚠️ **That list is a shelf of live credentials, not a history.** Every row
still enrols devices. **Forget** takes the row off the list and nothing more —
the code carries on working, because it carries the token's own secret. To stop
every code a token can produce, use **Retire &amp; create new**.

A code whose token has been retired drops off the list on its own, so anything
you can see there still works.

If a code had Wi-Fi baked into it, the password is kept sealed so the code can be
reproduced byte for byte. If you would rather nothing was kept, generate
permanent codes without Wi-Fi — the list still reproduces them.

## After enrolment

- Give the device a friendly name on its detail page.
- Assign it a policy (or add it to a group that already has one).
- Re-enrolment after a wipe re-adopts the same record — identity is matched on a
  set of identifiers, not a single serial.
