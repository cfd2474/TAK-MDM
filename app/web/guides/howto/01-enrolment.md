# Enrol a device

ATLAS enrols an Android device as a **Device Owner** during the out-of-box setup
wizard. Device Owner cannot be established after setup, so the device must be at
factory-reset state.

## Steps

1. Open the **Enroll** page. If there is no active enrollment token, give one a
   name and press **Create enrollment token**. The token has no group setting.
2. Fill in the Wi-Fi network the device should use during provisioning. Choose a
   group under **Enrol into group** if the device should join one: it then picks
   up that group's policies on its first check-in, with no second step. Press
   **Generate enrollment QR**.

   Two options limit how long the code works:

   - **Set expiration timer.** On by default, at 15 minutes. Choose minutes,
     hours or days, up to 30 days.
   - **Set use count.** The number of devices that can enrol with the code. Each
     enrolment uses one, including re-enrolling the same device. Scanning without
     enrolling does not.

   With both set, the code stops working when the first limit is reached, so a
   photograph of it stops working too.

   With **neither** set, the QR is permanent, and the page asks you to confirm
   that. Re-generating it gives the identical image, so it can be printed and left
   on a provisioning bench for bulk onboarding; use **Save QR** to download it.
   ⚠️ A permanent QR stays a live credential, so anyone who photographs it can
   enrol devices until the token is retired. **Retire & create new** on the Enroll
   page undoes that. That risk is why the default is a 15-minute timer.
3. On the factory-reset device, tap the first setup-wizard screen six times in the
   same spot to open the QR scanner. Scan the code.
4. The device joins Wi-Fi, downloads the agent, installs it as Device Owner, and
   checks in. It appears on the **Manage** page within a few seconds.

Setup finishes as soon as the device is enrolled. Apps and files download in the
background afterwards, with a notification on the device. If a EULA is set under
**Admin → End-user licence agreement**, the device shows it after setup, and the
user must accept it.

Android 11 and later can enrol with the QR code.

⚠️ The QR carries the key that signs every policy, and the device checks the
server's answers against it. If a network between the device and ATLAS
intercepts the connection, enrolment stops with a clear message.

## Groups are chosen on the QR, not the token

The enrollment token has no group setting. When you generate a QR you pick the
group the device should land in, and that choice belongs to the QR.

⚠️ This used to be offered in both places, which meant one decision could be
made twice and differently. The QR is the one that decides.

## Getting a QR back

Every code that still works is listed under **Live QR codes** on the Enroll page.
That includes permanent codes, and limited codes until they expire or are used up.
The list shows the time and uses each one has left. **Show QR**
draws the same code again — you do not have to remember which group or which
Wi-Fi it was made with, and re-typing those from memory would have produced a
*different* code with nothing on screen to say so.

⚠️ **That list is a shelf of live credentials, not a history.** Every row
still enrols devices.
- **Revoke**, on a limited code, stops it immediately.
- **Forget**, on a permanent code, takes the row off the list and nothing more.
  The code carries on working, because it carries the token's own secret. To stop
  every code a token can produce, use **Retire & create new**.

A code that has expired, been used up, or lost its token drops off the list on its
own, so anything you can see there still works.

If a code had Wi-Fi baked into it, the password is kept sealed so the code can be
reproduced byte for byte. If you would rather nothing was kept, generate
permanent codes without Wi-Fi — the list still reproduces them.

## After enrolment

- Give the device a friendly name on its detail page.
- Assign it a policy (or add it to a group that already has one).
- Re-enrolment after a wipe re-adopts the same record — identity is matched on a
  set of identifiers, not a single serial.

## Re-enrolling a device ATLAS already manages

A leaked QR and a serial number are not enough to take over a managed device.
When a device ATLAS already manages enrols again, one of two things happens:

- **Its hardware proves it is the same device.** Many devices can do this. They
  re-enrol with nothing to type.
- **Someone holding it types the security code.** Every other device shows a
  **Confirm this device** screen. Type the security code from
  **Admin → Environment**, and setup carries on with the same record and history.
  Emulators and some rugged tablets are in this group.

While a re-enrolment waits for the code, the device's page says so near the top.
Its record, certificate and policies do not change. A wrong code uses one of 10
attempts. **Reset code attempts** on the device's page lets the device try again;
it approves nothing by itself. If you are not re-provisioning that device, leave
it: the request lapses after a day.

The device page's **Identity** row says whether a device's hardware can prove
which device it is. An alert rule can tell you each time an enrolled device
enrols again, or waits for the code; see [Alerts](/guides/howto/alerts).

⚠️ **A retired device cannot enrol again.** Its setup says why. To put it back
into service, delete its record on its device page, then enrol it as a new
device.
