# Configure ATAK and connect to TAK Servers

A policy's **ATAK Config** category sets up ATAK itself: the TAK Servers it
connects to, its own settings and its plugins' settings, its custom toolbars,
and which plugins load by themselves. It has five parts:

- **Plugin behavior**: **Auto-Load Plugin**.
- **ATAK Core Pref Config**: ATAK's own settings.
- **Custom Toolbars**: toolbars from a .pref, the **Active toolbar** and the
  **Overflow menu layout**.
- **Plugin Pref Config**: a plugin's own settings.
- **TAK Server connections**.

Many of these need the **ATLAS plugin**, which runs inside ATAK. ATLAS installs
it by itself on every device a policy installs ATAK on, with the build for that
ATAK version. You never pick it, and it is not listed in any app picker.

## TAK Server connections

**Add TAK Server** opens a window. First choose how devices sign in, then fill
in **Name** (shown in ATAK's server list), **Server** (a name such as
tak.example.org or an IPv4 address, with no port and no https://), **Port**
(8089 by default) and **Protocol** (**SSL** or **QUIC**). **Save** adds the
server as a card. Click a card to change it or to **Remove server**. Nothing is
stored until you save the policy.

### Enroll for a certificate

Give a **Username** and **Password** for a TAK Server account. The ATLAS plugin
enrolls each device for its own client certificate, with no prompt on the
device.

- **Every device under the policy enrolls as that one TAK Server user.**
- The TAK Server's enrollment port (8446) must have a publicly trusted
  certificate, such as Let's Encrypt.
- It needs the ATLAS plugin 1.3.0 or later running in ATAK.
- A device receives the password only until it has enrolled. The plugin then
  deletes it from the device.
- **Renewal:** when a device's certificate is within 14 days of expiring, ATLAS
  sends the password again and the plugin enrolls for a new certificate. If a
  renewal fails, the device keeps its current certificate until it really
  expires.

⚠️ **A failed enrollment is not retried until you change the login in the
policy.** ATAK shows its own error on the device (for example, for a wrong
password). Repeated attempts could lock the account, so ATLAS waits for you.

⚠️ A failed renewal takes that one connection down for about two minutes while
it tries, then puts the old certificate back.

### Upload certificate files

Upload the server's **CA truststore** and a **Client certificate**, each a .p12
file with its password. Type the password first, then choose the file. ATLAS
opens each file at once, refuses a wrong password or the wrong kind of file,
and shows the certificate's name and expiry.

- ATAK gets the connection and the certificates directly. No plugin is needed.
- Every device under the policy gets the same client certificate.
- ATLAS does not renew uploaded certificates. Upload new files before they
  expire.

### Passwords

Once saved, a password is never shown again, in the editor or anywhere else in
the console. Leave a password box blank to keep the saved one. If you change a
server's address, enter its passwords again.

### Remove server upon policy removal

Tick **Remove server upon policy removal** on a connection, and when no policy
names that server any more, the ATLAS plugin removes it from ATAK, with its
certificates. This also works when a device loses its last ATAK policy.

- Without the tick, a server that leaves the policy stays in ATAK.
- Only the ATLAS plugin can remove a connection. A device without it keeps the
  server until the plugin next runs.

### Rules

- One connection per server address in a policy. When two policies name the
  same server, the higher-ranked policy's settings win.
- A server name cannot hold an IPv6 address; ATAK cannot use one here.
- TAK Server connections do not take device variables.
- Web Filtering never blocks the TAK Servers a policy configures.

### On the device page

The device's **ATLAS plugin** window has two tables about servers:

- **Managed TAK Server connections** lists each server from the policy, how it
  signs in, and its state on the device: **enrolled**, **existing** (a valid
  certificate was already there), **in progress**, **failed**, **enrollment
  failed** (not retried until the login changes), **waiting for the ATLAS
  plugin**, or **delivered in ATAK's configuration** for uploaded certificates.
  A warning says so when the device's plugin is too old to enroll or remove.
- **TAK servers** lists every server set up in ATAK, managed or not: connected
  or not, any connection error, the server's version, which certificate
  authority the client certificate is from (**Issued by**, with the start of
  its fingerprint), and when the client certificate and the truststore expire.
  **Issued by** needs the ATLAS plugin 1.5.0 or later; an older plugin shows
  **unknown**.

On **Manage**, a device with TAK Server certificates shows **TAK CA** and the
certificate authority's name under its own name. Type the name in the filter
box to find every device on that CA.

## Moving to a new TAK Server intermediate CA

When your TAK Server's intermediate CA is rotated, each device's client
certificate must come from the new intermediate before the old one is removed
from TAK Server. ATLAS moves managed devices without a new QR code.

**Before you start, on TAK Server:**

- TAK Server signs new client certificates with the **new** intermediate.
- TAK Server still **trusts the old** intermediate, so devices that have not
  moved yet stay connected.
- ⚠️ ATAK trusts a TAK Server certificate only if it is signed by a CA the
  device already has. If the 8089 server certificate is signed by the new
  intermediate, devices still on the old one lose the connection at once.
  A server certificate signed by the root CA keeps old and new devices
  connected together. If devices did lose the connection, ATLAS can still
  move devices that enroll with a login, because enrollment uses port 8446.

**In ATLAS:** go to **Admin → TAK Server CAs**. The list shows each
certificate authority that devices report, and how many devices are on it.
Choose the old one, give an optional **Retire by** date, and click **Retire**.

- **Connections that enroll with a login:** at its next check-in, each device
  on the old CA gets the login again, and the ATLAS plugin enrolls it for a new
  certificate. There is no prompt on the device. A device that has moved stops
  getting the login.
- **Connections with uploaded certificate files:** the page lists each policy
  whose client certificate is from the old CA. Upload a client certificate
  from the new CA to that policy. ATAK replaces the certificate of the
  existing connection on every device under the policy. The upload shows
  **issued by** and the CA's name, so you can see the file is from the new CA.
- The progress shows the devices **still on it** (and how each connection is
  moving), the devices **on another CA**, and the devices that **cannot say**
  because their ATLAS plugin is older than 1.5.0.
- The date is your plan for removing the old CA from TAK Server. Nothing
  happens by itself when it passes; the page marks it **overdue** while
  devices are still on the CA.
- **Stop** ends the move. Devices that have not moved stop getting the login.

When no device is still on the old CA, remove it from TAK Server's truststore,
then click **Stop**.

⚠️ **Retire only the old CA.** If you retire the CA that TAK Server still signs
with, each device enrolls once more and gets a certificate from the same CA.
The plugin tries a login only once per ATAK start, so this does not repeat.

⚠️ A failed move is like a failed renewal: that one connection is down for
about two minutes, then the old certificate is put back. It is not retried
until you change the login in the policy.

### Connections enrolled outside ATLAS (TAK Portal QR codes)

A device can have a TAK connection that no ATLAS policy set up. For example,
the user scanned a QR code from TAK Portal. ATLAS has no login for such a
connection, and the QR code's password expired 15 minutes after it was made.
ATLAS can still renew its certificate, so the user does not scan a QR code
again.

**What it needs:**

- ATLAS installed and updated from InfraTAK. Each install and update makes
  the `atlas-renewal` account in Authentik and starts ATLAS's renewal
  container. The account's token is replaced on every update.
- The ATLAS plugin 1.6.0 or later on the device.
- The connection is to the TAK Server on the same InfraTAK box. A connection
  to another TAK Server is not renewed.

**When it happens:** 30 days before the certificate ends, or while you
retire its CA (above). No action is needed from you or the user.

**How it works:**

1. At a check-in, ATLAS sends the plugin a challenge for that connection.
2. The plugin signs it with that connection's own certificate key.
3. ATLAS's renewal container checks the signature and that the certificate
   comes from your TAK Server's CA. It then makes a password for the user
   named in the certificate, which works for 10 minutes.
4. The plugin enrolls that connection with it at once. The user keeps the
   same TAK identity and groups.
5. ATLAS deletes the password.

Each step happens at a check-in, so a renewal takes three or four check-ins.

**Limits:**

- The user must still exist in Authentik and be active. ATLAS never makes a
  password for an Authentik administrator or a service account.
- If a renewal is refused or fails, ATLAS tries again after a day. So a
  failed renewal costs the user at most one failed login a day, which is far
  below the lockout.
- ⚠️ Authentik keeps a successful LDAP login for up to an hour. So a password
  ATLAS deleted can still work for up to an hour. TAK Portal's QR passwords
  have the same window. The password goes only to the device, over its
  mutual TLS connection.

**On the progress page:** a connection enrolled outside ATLAS shows
**renewing**, **renewed**, or **renewal paused** with the reason and when it
tries again. If the plugin is older than 1.6.0, or renewal is not set up on
this server, the page says so.

## ATAK Core Pref Config and Plugin Pref Config

**ATAK Core Pref Config** lists every setting the ATAK build in your library
declares, read from that build. Filter the table by name or key. **Plugin Pref
Config** does the same for one plugin: **Add plugin**, pick it, and choose its
settings.

- Each setting starts as **not managed**. ATLAS leaves a setting that is not
  managed alone, and the device keeps whatever it has.
- Give a setting a value and devices receive it.
- **Clear all values** sets every ATAK setting in the policy back to not
  managed. It asks first. ATLAS stops managing them when you save, and devices
  keep the values they already have.
- A plugin entry needs at least one setting.
- When two policies set the same setting, the higher-ranked policy wins.

**Each setting is applied once.** A device sends ATAK only the settings that are
new or changed since it last received them. If someone changes a setting on the
device, it stays changed until you change that setting in the policy. Editing a
different setting does not put it back. When ATAK is reinstalled, the device
gets the whole configuration again.

⚠️ This needs the ATLAS plugin to confirm that ATAK has read each change. On a
device without it, each policy change sends every ATAK setting again, so a hand
edit there lasts only until the next change.

ATLAS applies these settings whatever a device's **Import Preferences Action**
is set to. That setting only affects .pref files a user imports themselves.

For a different value on each device, such as a callsign, see
[Give every device its own callsign](/guides/howto/per-device-callsigns).

## Import .pref

**Import .pref**, in ATAK Core Pref Config, reads a preference file exported
from ATAK and lists every entry.

- ATAK's own settings are listed with a tick box each, all ticked. **Uncheck
  all** clears them. Untick anything you don't want, then **Import ticked
  settings** fills those fields. Save the policy to keep them.
- Entries that are not ATAK settings (ATAK's internal state, such as the map
  position, and other apps' settings) are listed separately and are not
  imported.
- Entries ATAK writes as raw binary are listed as not importable. The rest of
  the file imports.

⚠️ **Some entries are removed, and the window says which and why:**

- the exporting device's certificate-database identity, which would make ATAK
  enroll its certificate again;
- certificate passwords and locations, and the mesh key;
- sign-in tokens and API keys;
- TAK Server connections (set those in TAK Server connections);
- the exporting device's UID and callsign.

ATLAS also refuses to send the certificate identity, certificate passwords and
tokens if they reach a policy another way.

## Extract current pref

The device page's **ATLAS plugin** window has an **ATAK preferences** section.
**Extract current pref** asks ATAK on that device to write a .pref of its
current configuration, the same as ATAK's own export. ATLAS keeps the file on
the device page until you delete it.

- It needs the ATLAS plugin 1.4.0 or later. Until the device's plugin reports
  it, the button is disabled with the reason.
- ATAK exports only while it is running. A request made with ATAK closed shows
  **waiting for ATAK** until it next runs. A failure shows the plugin's reason.
- The file is named after the device and the time, in UTC.
- It does not include TAK Server connections. ATAK keeps those outside its
  settings.

⚠️ **The file is exactly what ATAK writes, so it can include a certificate
password.** Every download and delete is recorded in the audit log.

**The round trip:** set ATAK up by hand on one device, press **Extract current
pref**, download the file, and **Import .pref** it into a policy. The import
leaves out what belongs to that one device, so the result is safe to send to
the fleet.

## Custom Toolbars

**Import .pref**, in **Custom Toolbars**, lists the custom toolbars in an
exported file, by name.

- Rename a toolbar in its box, or **Remove** the ones you don't want. **Put
  back** undoes a removal. Save the policy to keep them.
- ATAK's built-in **Default** toolbar is listed but removed to start, because
  sending it replaces each device's own Default.
- Each toolbar names the plugins its tools come from. Devices need those
  plugins for the buttons to work.
- **Active toolbar** switches devices to one of the listed toolbars. **None**
  leaves each device on the toolbar it is using.
- Like other ATAK settings, each toolbar is applied once. A user's own changes
  to a delivered toolbar stay until you change that toolbar in the policy.

**Overflow menu layout** is **Tiles** or **List**. **Not managed** leaves each
device as it is. Importing a .pref sets it from the file, and devices pick it up
without restarting ATAK.

## Auto-Load Plugin

**Plugin behavior** lists every ATAK plugin in your app library, each with an
**Auto-Load Plugin** box. For each ticked plugin, the ATLAS plugin loads it
inside ATAK within about 30 seconds of it being installed and not loaded,
including after an update. There is no restart and no prompt.

- A plugin ticked in any policy is auto-loaded.
- ATAK still checks each plugin's version and signature. A plugin it won't
  accept shows as **refused** on the device page, with the reason.
- Unticking stops this, but does not unload the plugin.
- After an update made while ATAK is open, ATAK may still ask "Load plugin?".
  Either answer is fine: the plugin stays loaded.
- It needs the ATLAS plugin 1.1.0 or later.

## The ATLAS plugin window

Each device that ATLAS installs the plugin on has an **ATLAS plugin** card on
its page. Its window shows what the plugin last reported:

- whether it is **running**, **stopped** or **not running**. Not running means
  no report in the last 15 minutes, which usually means ATAK is closed.
- the plugin and ATAK versions, and when it last reported;
- **ATAK plugins**: each plugin on the device and whether it loaded, with the
  reason when it didn't;
- **Auto-Load**: each ticked plugin's result, and whether its next update will
  load without a prompt;
- the TAK Server tables and **ATAK preferences**, described above.

A device with an ATLAS app too old to report shows **not reported**. A
compliance rule, **ATLAS plugin running**, can flag devices where the plugin
is not running.
