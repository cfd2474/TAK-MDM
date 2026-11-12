# Compliance

Rules a device must keep meeting, and what happens when it stops. Add a
**Compliance** section to a policy, the same way as any other section. See
[Build a policy](/guides/howto/building-a-policy).

ATLAS checks every rule when the device checks in. It checks again every few
minutes from the server, even when the device is silent. That is how
**Checked in within** catches a device that has gone quiet.

## The rules

Each rule is off until you set it. A yes/no rule has two choices:
**Required** or **Not checked**.

Under **Device**:

- **Minimum Android version**: the device's Android major version, for
  example 14.
- **Maximum security patch age**: the age of the device's Android security
  patch, in days. The date is the device's own, from Settings › About.
- **Storage encrypted**: every device on Android 10 or later is encrypted, so
  this mainly catches an unusual build.
- **Device integrity verified**: the device's secure hardware must vouch,
  through Google's key attestation, that its bootloader is locked and that it
  booted verified software. That means not rooted and not running a modified
  system. Each device is asked to attest once a day.
- **No distrusted CAs trusted**: the device must not trust any certificate on
  **Admin › Distrusted CAs**. See "Distrusted CAs" below.
- **Act on distrusted CAs**: choose **Act on it** or **Alert only**. See below.

Under **Security settings**:

- **Passcode meets the Password policy**: as Android itself judges it.
- **USB debugging off**.
- **Developer options off**.
- **Installs from unknown sources blocked**: you set this under
  **Restrictions**. This rule checks that it holds.

Under **ATAK**:

- **Minimum ATAK version**: for example 5.8.0.
- **ATLAS plugin running**: the ATLAS plugin must be reporting from inside
  ATAK.

Under **Contact**:

- **Checked in within**: a number of hours.

### "Not reported" is not failing

A rule shows **not reported** when the device has not sent the fact it needs.
An older agent, or a fact the device could not read, gives this result. Not
reported never makes a device non-compliant by itself.

**Device integrity verified** also shows not reported:

- when the device has not attested in the last 7 days;
- when ATLAS could not reach Google's revocation list.

**Tripltek tablets are exempt from the integrity rule.** Their hardware vouches
for itself through Tripltek, not through Google. If that is the only problem
found, the rule shows not reported and the device page says **not
verifiable**. Any other problem still fails the rule.

### When policies stack

The strictest value wins. The highest **Minimum Android version** applies, the
shortest **Checked in within** applies, and **Required** beats **Not checked**.
**Minimum ATAK version** is the exception: the value from the highest-ranked
policy applies. See [How policy stacking works](/guides/howto/policy-stacking).

## Actions

Under **Actions**, choose what happens to a device that keeps failing. Each
action has its own delay. The delay counts from the moment the device started
failing.

- **Apps to suspend** and **Suspend apps after** (hours): the apps you choose
  cannot be opened, and their notifications are hidden. Choose no apps to
  suspend ATAK. You must set **Suspend apps after** when you choose apps.
- **Lock the device after** (hours): the device is locked again on every
  check-in, about every 2 minutes, until it passes. This gives the user time to
  fix the cause, for example to turn off USB debugging.
- **Wipe the device after** (days): a factory reset. It is off unless you set
  it.

For the hours fields, 0 means at once. Empty means never.

When the device passes its rules again, suspend and lock are lifted at its
next check-in. A wipe that is queued but not yet delivered is canceled.

⚠️ **A wipe destroys all data on the device.** The SD card is erased too.
The device must then be enrolled again. When policies stack, the shortest
**Wipe the device after** wins, so one policy with a short wipe applies to
every device it reaches.

### Stage it safely

1. Set the rules with no actions. Assign the policy to a small group first.
2. Open a few devices' pages. Look for rules that fail for a reason you did not
   expect.
3. Add an alert for "A device started failing a compliance rule". See
   [Alerts](/guides/howto/alerts).
4. Add **Suspend apps after** or **Lock the device after**. These are lifted
   by themselves when the device passes.
5. Add **Wipe the device after** last, if at all. Give it enough days for
   someone to see the alert and act.

## What a failing device shows

**On the Manage list**, the **Compliance** column holds two labels:

- whether the device applied its policy (**compliant**, **degraded**,
  **failed** or **unknown**);
- the rules result: **rules met**, **rules not reported**, or how many rules
  are failing, for example **2 rules failing**.

⚠️ The **Compliance** filter above the list filters on the first label,
whether the device applied its policy. It does not filter on the rules.

**On the device page**, the same rules label is at the top. The **Compliance
rules** card counts the rules that are **Passing**, **Failing** and **Not
reported**. Open **Details** to see:

- each rule with **pass**, **fail** or **not reported**, and what the device
  reported;
- when the device started failing, and when it was last checked;
- each action with the time it starts, marked **due**, **in force**, **wipe
  queued** or **wipe sent**;
- the **Trusted certificates** the device reported, with its **Google Play
  system update** date and **Conscrypt module** version.

The device page also has an **Integrity** line with the last attestation result.

Failing a rule does not count as "not applying its policy". A failing device
still gets agent updates, which may be the fix it needs.

## Alerts

Two events in **Admin › General › Alerts**, under **When something happens**:

- "A device started failing a compliance rule". The alert names the rules that
  fail.
- "A device meets its compliance rules again".

Each fires on the change, not while the state continues.

## Distrusted CAs

**Admin › Distrusted CAs** lists certificate authorities that no device should
trust. Every device checks its trusted certificates against the list and
reports any it finds. Certificates are matched by SHA-256 fingerprint, never by
name.

ATLAS ships a built-in list: the eMudhra root and its affected intermediates,
whose keys were compromised in October 2026. You cannot remove built-in
entries. To add your own, type its **SHA-256 fingerprint** (colons are fine), a
**Name** to show in device reports, and an optional **Why**.

**No distrusted CAs trusted** makes this a rule. By default a failing device is
flagged and you are alerted, but nothing is suspended, locked or wiped: the
failure shows **alert only**. The reason is that the user usually cannot fix
it. A system certificate goes away only with an OS or Google Play system
update. Set **Act on distrusted CAs** to **Act on it** to count it toward the
actions like any other rule.

The device page shows the fix for each certificate found. For a system
certificate, it is an OS and Google Play system update. For one the user
installed, it is to remove it under Settings › Security › Trusted credentials ›
User.

## Other settings that wipe or cut off a device

These are not compliance rules, but they act on the device by themselves.

⚠️ **Password › Failed attempts before wipe.** After that many wrong passcodes,
Android factory resets the device. ATLAS is not asked first. When no policy
sets it any more, ATLAS clears the limit on the device.

- **Password › Auto-lock timeout**: seconds of inactivity before the device
  locks.
- **Password › Set the passcode**: forces an exact passcode. The user can
  change it, but the agent sets it back on every sync.
- **Restrictions › Screen timeout**: seconds of inactivity before the screen
  locks.

⚠️ **Restrictions › Wi-Fi set to Block** cuts off a device that has no other
connection, such as a Wi-Fi-only tablet or a phone with no SIM. It cannot reach
ATLAS, so it never receives the policy that lifts the block. It must be factory
reset.

**Restrictions › Developer options** set to **Blocked** also blocks USB
debugging. Set it, and **Install from unknown sources**, when you want the
matching compliance rules to pass.
