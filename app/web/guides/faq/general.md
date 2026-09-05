# FAQ — general

## Does ATLAS need managed Google Play?

No. Apps are sideloaded APK/XAPK. The agent installs them with `PackageInstaller`
under Device Owner privilege.

## How quickly does a policy change reach a device?

Immediately when the device is online — a long-poll "doorbell" wakes it in the
same second. Polling on a ~15-minute floor is the correctness guarantee for a
device that is offline.

## What happens when a device is offline for weeks?

Nothing is lost. On its next check-in it receives one declarative desired state
and converges. Transient commands (lock, locate) expire rather than surprising a
device that reappears.

## Can I remove an app with a policy?

Yes — `removed_packages` uninstalls it outright. `blocked_packages` hides it
(reversible, keeps data); it does not uninstall. A blocked app that ships with the
device is hidden rather than downgraded.

## Is the console authenticated?

It is meant to sit behind Authentik forward auth (`TAKMDM_ADMIN_AUTH_MODE=forward_auth`).
The `disabled` mode is for local development and says so loudly.
