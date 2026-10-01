# FAQ — troubleshooting

## A device shows "behind" on the Manage page

The **Convergence** column is `applied / target` policy version. "Behind" means
the server has a newer version than the device has confirmed applying. Usual
causes: the device is offline, or a policy apply is failing — check its
**Compliance** state and detail, or collect its logs.

## Collect a device's logs

On the device page, press **Collect logs**. The doorbell wakes the device and the
bundle usually arrives within a check-in. The agent keeps its own ring-buffer log
on internal storage — it does not scrape `logcat`.

## A device enrolled with no hardware serial

The device page warns when a device is identified only by an `android_id`
fallback — a wipe would fork a new record. The agent needs `READ_PHONE_STATE` to
report a real serial; it self-grants this on every sync, so installing a current
agent build and waiting one sync fixes it.

## A policy change "had no effect" in the Docker stack

Rebuild: `docker compose up -d --build`. Python source is baked into the image at
build time, so a plain `up -d` runs the old code. Changes under `docker/nginx/`
or `pki/` need `docker compose restart proxy`.

## An app upload is rejected for a signature mismatch

The package's signing certificate differs from the version already uploaded.
Android would refuse the update on the device; ATLAS refuses it at upload so the
error is legible. Upload it under a different package name, or remove the old one.
