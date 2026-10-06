# Alerts

Email when the fleet needs attention. Set up in **Admin → General**, in two
parts: what is worth being told about, and who gets told.

## Who gets told

**Alert recipients.** Add an address, optionally with a name. ⚠️ An empty list
means nothing is sent — alerts with nobody to send to are discarded, not queued,
so that the first address you ever add does not arrive to a backlog of
everything since the server was built.

**Paused is not removed.** If an address starts bouncing or somebody goes on
leave, pause them: they stop receiving today and the record of who was on the
list stays.

## What is worth being told about

Three kinds, and you can have as many as you like of each.

**When something happens.** A device finished enrolling, was disenrolled,
stopped applying its policy, or was put into breach mode.

⚠️ "Stopped applying its policy" fires on the *change*, not the state. A device
that has been failing for a week reports it on every check-in; you are told once
when it breaks and once more if it recovers and breaks again.

**When a device goes quiet.** No check-in for a span you choose, with its own
unit — 90 minutes, 72 hours, 14 days. Add several: a short one to notice a
device dropping off, a long one to catch a tablet nobody has picked up in a
fortnight.

⚠️ **A device that has *never* checked in is a different problem** and is not
covered by these. That is a provisioning failure, and it is already reported on
the device's own page. Alerting on it here would tell you about every device in
the fleet the moment you created a threshold.

⚠️ The shortest threshold allowed is fifteen minutes. Anything shorter is true
of every healthy device all the time.

**When a device looks like this.** Pick a device field, a test and a value —
battery level under 20, model contains SM-X, compliance is failed. Give it a
name you will recognise in a list.

⚠️ **A device with no value for the field never matches**, whatever the test. A
tablet that has never reported its battery is not a tablet whose battery "is not
20" — otherwise every device yet to check in would match.

## What you will receive

⚠️ **One message per sweep, listing everything raised** — not one email per
alert. A single bad policy push can put the whole fleet out of compliance at
once, and two hundred emails is the same outcome as none.

⚠️ **You are told once per condition.** A device quiet for three days is quiet
on every sweep; you hear about it when it crosses your threshold and again only
if it comes back and goes quiet a second time.

Alerts are checked every five minutes. Something raised while you were watching
the console — a device enrolling, a breach engaged — goes out on the next sweep
rather than instantly.

## If nothing arrives

In order:

1. **Is there a recipient?** An empty list sends nothing.
2. **Is mail configured?** **Admin → Email (SMTP)** — either your own server, or
   tick *use InfraTAK's email configuration* and press **Test the relay**.
3. **Is there a rule?** No rules means nothing to send.
4. **Check the server log.** Every discard and every failed send is logged with
   the reason. ⚠️ A send that fails is retried on the next sweep, so an alert is
   not lost by a relay being briefly down.
