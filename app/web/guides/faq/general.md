# FAQ — general

## Does ATLAS need managed Google Play?

No. Apps are sideloaded APK/XAPK. The agent installs them with `PackageInstaller`
under Device Owner privilege.

ATLAS can *fetch* from Google Play — Apps › Google Play, as one nominated
account linked under Admin — but that is a download source, not managed Play.
What arrives is an APK, held like every other upload, and it is still the agent
that installs it.

## How quickly does a policy change reach a device?

Immediately when the device is online — a long-poll "doorbell" wakes it in the
same second. Polling on a ~15-minute floor is the correctness guarantee for a
device that is offline.

## What happens when a device is offline for weeks?

Nothing is lost. On its next check-in it receives one declarative desired state
and converges. Transient commands (lock, locate) expire rather than surprising a
device that reappears.

## Can I remove an app with a policy?

Yes — the **blocklist** (`blocked_packages`). An ordinary app is uninstalled; one
that ships with the device is hidden instead, because a preinstalled app cannot
be removed.

⚠️ So "removed" means different things for the two cases. Uninstalling destroys
the app's data and reclaims its storage. Hiding does neither — the app is
unusable but still there — and it is reversible: take the package off the list
and the agent unhides it, having only ever hidden what it hid itself.

## Is the console authenticated?

It is meant to sit behind Authentik forward auth (`TAKMDM_ADMIN_AUTH_MODE=forward_auth`).
The `disabled` mode is for local development and says so loudly.

## Does ATLAS send email?

Yes: alert emails. You choose what is worth an email and who receives it under
**Admin › General**, and ATLAS sends through the mail server on **Admin › Email
(SMTP)**. ⚠️ With no mail server set, or nobody on the recipient list, alerts
are discarded rather than sent, and the page says so. See
[Alerts](/guides/howto/alerts).

## Can ATLAS send email through InfraTAK?

Yes, and it needs no credentials from you. In **Admin › Email (SMTP)**, tick
*Use InfraTAK's email configuration* and save. The page then shows what ATLAS
would send through.

⚠️ **InfraTAK's Email Relay has to be deployed first.** Configure it in the
InfraTAK console; if it has not been, ATLAS says so on the same page and nothing
will send. If you set the relay up *after* deploying ATLAS, run an ATLAS update
so it picks the settings up.

**Test the relay** opens a connection and reads the greeting. It sends nothing.
⚠️ That proves a mail server answered — not that mail will arrive. The provider
can still refuse the sender or the domain, and only a real alert email would
show that.

Why no username or password: the relay is Postfix on the same host, and it
accepts mail from ATLAS's container without authenticating. Postfix holds the
provider credential itself, so there is never a copy of it inside ATLAS.

Your own SMTP settings are kept while inheriting, not replaced — untick the box
and save, and they come straight back.

## Where do I get a Samsung Knox license?

From Samsung, free. A **KPE Premium** key comes from the Knox Admin Portal
(central.samsungknox.com → **Licenses** → **Manage license keys** → generate a
Knox Platform for Enterprise Premium key). It lasts 2 years from its first
activation. Samsung explains it in
[Knox Platform for Enterprise licenses](https://docs.samsungknox.com/admin/knox-platform-for-enterprise/before-you-begin/knox-platform-for-enterprise-licenses/).

Enter it in **Admin › Samsung Knox**. Every Samsung device on this ATLAS uses
the same key. ⚠️ While **Enable KNOX** is on with no key, the dashboard's
**Knox key** tile is red, and Samsung devices skip every Knox setting until a
key is set and active on them.
