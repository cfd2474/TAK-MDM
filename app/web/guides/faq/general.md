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

## Can ATLAS send email through InfraTAK?

Yes, and it needs no credentials from you. In **Admin → Email (SMTP)**, tick
*use InfraTAK's email configuration*. The fields grey out and show what ATLAS
would send through.

⚠️ **InfraTAK's Email Relay has to be deployed first.** Configure it in the
InfraTAK console; if it has not been, ATLAS says so on the same page and nothing
will send. If you set the relay up *after* deploying ATLAS, run an ATLAS update
so it picks the settings up.

**Test the relay** opens a connection and reads the greeting. ⚠️ That proves a
mail server answered — not that mail will arrive. The provider can still refuse
the sender or the domain, and only a real send would show that.

Why no username or password: the relay is Postfix on the same host, and it
accepts mail from ATLAS's container without authenticating. Postfix holds the
provider credential itself, so there is never a copy of it inside ATLAS.

Your own SMTP settings are kept while inheriting, not replaced — untick the box
and they come straight back.

⚠️ **ATLAS does not send mail yet.** These settings are groundwork for the
notification categories that are coming; nothing reads them today.
