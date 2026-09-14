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
