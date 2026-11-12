# Device certificates, recovery and troubleshooting

How a device proves who it is, how to bring one back when that breaks, and the
tools for finding out what a device is doing.

## Device certificates

Every enrolled device signs in to ATLAS with its own certificate. Set how long
they last under **Admin › Certificates**:

- **Device certificates last (days):** from 7 to 825. The default is 90.
- **Devices renew when this many days remain:** the renewal window. The
  default is 30. It must be shorter than the lifetime.

Devices renew by themselves, over their usual connection, once they are inside the window.
Nobody touches the tablet. If a renewal fails, the device keeps its working
certificate and tries again.

The note under the numbers says what they mean: a device renews about every
*lifetime − window* days.

⚠️ **The renewal window decides how long a device can be offline, not the
lifetime.** A device that goes offline just before it renews has only the
window left. If your devices spend long stretches offline, raise the window.

A new lifetime applies to certificates issued from then on. A new window
reaches every device at its next check-in.

## A device offline past its certificate's expiry

A device whose certificate expired can't reach ATLAS at all. ATLAS shows it:

- On **Manage**, a **certificate expired** pill beside its last check-in. Point
  at it for the date and what can be done.
- On the device page, a banner at the top says when it expired and what to do.
- On the dashboard, the **Expired device certificates** tile counts them.

## The security code

The security code is on **Admin › Environment**. Typed on a device, it does
two things:

- It skips the permissions step during provisioning, when setup is blocked
  because a required permission hasn't been granted.
- It restores a device whose certificate expired.

The code is checked by ATLAS, so the device must be able to reach the server.
It is never put in an enrollment QR, and it gives no access to the console.
**Regenerate code** replaces it at once, for both uses. Do it if the code has
been shared more widely than you'd like.

## Restoring a device whose certificate expired

When such a device comes back online, it shows a **Restore this device**
screen. Whoever holds it types the security code. The device is back with the
same record, policies, apps and settings, and no factory reset.

- It works for up to 180 days after the certificate expired. After that, the
  device has to be set up again.
- It never works for a device that is retired, has its certificate revoked,
  is in breach mode, or has a disenrollment it hasn't acknowledged yet. The
  device is told only that it can't be restored this way.
- The device itself is needed. The code alone is not enough.
- Each device gets 10 tries.
- **Admin › Environment** has a checkbox, *Allow devices with an expired
  certificate to be restored with the security code*. It is on unless you turn
  it off. When it is off, a device with an expired certificate has to be set
  up again. Setting up new devices is not affected.

An alert event, "A device with an expired certificate was restored with the
security code", can tell you when it happens. See [Alerts](/guides/howto/alerts).

⚠️ **A device in breach mode can't be restored.** It has to be set up again.
See [Breach mode](/guides/howto/breach-mode).

## Enrolling a device again

When a device ATLAS already manages enrolls again (after a wipe, for example),
it has to show that it is the same tablet. It does that in one of two ways:

- **Its hardware proves it.** Many devices can have their secure hardware sign
  their own serial number or IMEI. These enroll again with nothing to type.
- **Someone holding the tablet types the security code.** Every other device
  is held, and the tablet shows a **Confirm this device** screen. Type the
  security code from **Admin › Environment** and setup carries on, with the
  same record and history.

The **Identity** row in the device page's **Device info** says which way a
device will go: **provable** devices need no code, **not provable** ones ask
for it.

While a re-enrollment waits, nothing changes. The device keeps its
certificate and its policies, and its page says so near the top. If you
aren't re-provisioning it, someone may be trying to take over its identity:
leave it, and the request lapses after a day. Each one is in the audit log, and
the alert event "A re-enrollment is waiting for the security code on the
tablet" can tell you about it.

A wrong code uses one of the same 10 tries the restore screen uses. Once one
is used, **Reset code attempts** appears in the **Lifecycle** section at the
bottom of the device page. It lets the tablet try again. It approves nothing
by itself.

## A retired device can't enroll again

A device you retired is refused when it tries to enroll, and the tablet's setup
says why. To put a retired tablet back into service, select **Delete
permanently** in its **Lifecycle** section, then enroll it as a new device.
Its history, logs and assignments are deleted with it.

## Troubleshooting tools on the device page

**What these do**, under the buttons at the top, explains each one.

- **Export device report** downloads everything on the page as a ZIP, with one
  CSV file for each table. Times are in UTC. Secrets are masked. Location
  history isn't included.
- **Export policy config** downloads one CSV of every policy setting that
  reaches the device, one row per value: which policy set it, at what scope,
  and which policy it overrode.

On Samsung devices, while Knox is on, there are also **Restart app**, **Re-enable
after wrong passwords** and **Power off**. See [Build a policy](/guides/howto/building-a-policy),
"Knox buttons on the device page".

**Effective policy** has one card per policy category. **Details** on a card
shows every setting, the policy it came from, how it was chosen and what it
overrode.

**Diagnostics**, under **Records**:

- **Collect logs** asks the agent for its own log and wakes the device at once.
  Each log has **view** and **download .txt**. ATLAS keeps the last 20 for each
  device.
- **ATAK session logs** are ATAK's own logs, one per session, while **Enable
  automatic error logging** is on in the device's policy. ATLAS keeps the last
  20, for up to 14 days. A log marked **still running** is replaced by the
  whole session once it ends.

**ATLAS plugin** shows whether the ATLAS plugin is running inside ATAK, its
version and ATAK's, and any problem it reports. It also lists ATAK's plugins,
what loads automatically and the TAK servers. **Extract current pref**, under
**ATAK preferences**, takes a copy of ATAK's current settings. ⚠️ The file can
include a certificate password, and each download is recorded in the audit log.

**Device package list** lists every package on the device, system apps
included. Select **Device Package List Report** to ask the device for it, then
**View / print** or **Download CSV**.

**Location history**, under **Location**, shows the device's stored positions
for a date range. **Export all history** downloads every stored point.

## Reports

**Reports** in the menu has fleet-wide views. Each opens on screen and
downloads as CSV:

- **Fleet inventory**
- **Convergence & compliance**
- **Policy deployment**
- **Command history**
- **App inventory**
- **Marketplace selections**

## Common problems

**A device shows "behind".** On **Manage**, the **Convergence** column is the
policy version the device has applied, then the version ATLAS wants it to
have. **behind** means ATLAS has a newer version than the device has confirmed
applying. The device page says the same at the top. Usually the device is
offline, or applying the policy is failing: check its **Compliance**, or
collect its logs.

**A device shows "No hardware serial".** The device page's **Identity** card
warns when a device is known only by values that change on a factory reset. A
wipe would then enroll it as a new record, and it would lose its policies. The
agent needs the phone-state permission to read the real serial. It grants
itself its permissions at every sync, so installing a current agent and
waiting for one sync fixes it.

**An app upload is refused because its signing certificate differs.** The
new file is signed with a different certificate from the version already in
the library. Android would refuse that update on the device, so ATLAS refuses
it at upload, where the reason can be shown.
