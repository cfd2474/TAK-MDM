# Audit log

Who changed what, and when. Open it from **Admin → Audit log**.

## What is recorded

**Every change** made through the console or the API: saving or publishing a
policy, retiring or disenrolling a device, uploading an app, changing a setting,
and everything else that changes something. Each entry says who made it, where
they connected from, what they did, and whether it worked:

- **ok**: it was done.
- **refused**: ATLAS said no, for example a serial number typed wrong when
  confirming a factory reset. The reason you were given is in the entry.
- **failed**: something went wrong on the server.

Common actions are described in words, such as *Saved 'Field kit': Passcode
v3 → v4: min_length changed: 4 → 8*. Others show the page they were made on.

**Who used the console today.** Looking around isn't recorded, except for
each person's first visit of the day, so **Today** lists everyone who signed
in, with when they were first and last active and how many changes they made.

⚠️ **Secrets are never recorded.** A changed password, PIN, key or Wi-Fi
network shows as *changed*, never as its value. Settings are named, not shown.

## Finding something

The full log has filters for the person, the kind of action (every device
action, or just one), the outcome, and a date range. **Every entry for this
device** on any entry shows that device's whole history. **CSV** downloads what
the filters show; times in it are UTC.

## Checking nobody edited it

Each entry is sealed to the one before it. **Verify chain** checks them all, and
says so if any entry was changed or removed outside ATLAS, and where. It reads
the whole log, so on a busy server it can take a moment.

## How long it is kept

A year by default. Change it under **Admin → Audit log** (at least 30 days, or 0
to keep everything). Older entries are removed once a day, and each removal is
itself recorded, so Verify chain still checks what remains.

## "From" shows the same address for everyone

That address belongs to the proxy in front of ATLAS. A standalone install shows
it until `TAKMDM_TRUSTED_PROXIES` names the proxy's network; InfraTAK installs
set this for you. It also limits the console to requests that come through that
proxy.
