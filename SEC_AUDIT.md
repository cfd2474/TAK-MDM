# ATLAS — Security Audit

**Date:** 2026-09-14 · **Version audited:** v1.15.0 (`54e22fa`) · **Method:** source review

A static review of the ATLAS server, the Android agent, the deployment
configuration, and the InfraTAK module. Every finding below is traced to a file
and line and was read rather than inferred.

---

## Scope and method

**Reviewed:** `app/` (114 Python modules), `agent/` (Kotlin agent and launcher),
`alembic/`, `docker/`, `docker-compose.yml`, `requirements.txt`, and the public
`modules/atlas.py` in the infra-TAK fork.

**Not done, and it matters when reading this:**

- **No dynamic testing.** Nothing was exploited, fuzzed, or run against a live
  host. Severity ratings are reasoned from code, not demonstrated.
- **No dependency CVE scan was executed.** Finding **H-3** records the version
  ages as fact; it does not assert specific CVEs from memory. Run `pip-audit`
  to turn that finding into a list.
- **The Android agent was reviewed selectively** — manifest, exported
  components, file deployment, location, and the command handlers. The
  provisioning and kiosk paths were not read line by line.
- **No review of Authentik, Caddy, or the InfraTAK host** beyond how ATLAS
  depends on them.

### Severity

| | Meaning |
|---|---|
| **Severe** | Total compromise of the fleet or the server if the condition is met. |
| **High** | Significant compromise, or a systemic weakness with wide reach. |
| **Medium** | Real exposure, bounded by privilege required or by blast radius. |
| **Low** | Hardening gaps and latent issues with no current exploit path. |

⚠️ **Privilege matters throughout.** An ATLAS administrator can already install
arbitrary applications on every device in the fleet. Findings that require
administrator access are therefore rated on *what they add* to that — reach
beyond the fleet, persistence, or evasion of the audit trail — not on the
device-level access an admin has by design.

---

## Summary

| ID | Severity | Finding |
|---|---|---|
| S-1 | ⚠️ High, part-fixed | Admin authentication trusts request headers with no proxy verification — peer check in force; host-local forgery needs the upstream change |
| S-2 | **Severe**, tooling ready | Five private keys sit unencrypted in one directory — offline-root capability and ceremony shipped; **the ceremony has not been run** |
| H-1 | ⚠️ High, detected | Fleet authorization is delegated entirely to Authentik — loss of the binding is now noticed; the delegation stands |
| H-2 | High | The agent signing key is an unrecoverable single point of failure |
| H-3 | ✅ Fixed | Dependencies pinned two years back, with no scanning and no CI — 24 advisories found and cleared |
| H-4 | ✅ Fixed | A device's own serial number reached a JavaScript string in the console — found while fixing M-6 |
| M-1 | ✅ Fixed | Uploads are read whole into memory with no size limit — the cap now bites during the read, plus a body limit at Caddy |
| M-2 | ✅ Fixed | Server-side fetch of operator-supplied URLs, following redirects (SSRF) — validated per hop; private LAN still allowed on purpose |
| M-3 | ✅ Fixed | Private key files are created before they are made private (TOCTOU) — closed by the S-2 key-custody work |
| M-4 | ✅ Fixed | A fleet-takeover receiver is exported in release builds — removed from the release manifest |
| M-5 | ✅ Fixed | Outbound credentials stored in plaintext in the database — sealed in the token vault |
| M-6 | ✅ Fixed | No security response headers anywhere — CSP with no inline script, plus four headers |
| M-7 | Medium | The permanent enrollment QR is a non-expiring credential in a printable image |
| M-8 | Medium | No rate limiting on any endpoint |
| L-1 | ✅ Fixed | DTED archive paths pass through the server unsanitised — escapes refused at plan time |
| L-2 | ✅ Fixed | CSRF cookie is readable by JavaScript for no reason — now HttpOnly |
| L-3 | ✅ Fixed | Markdown link URLs are injected into an attribute without quote escaping — quotes escaped, schemes allowlisted |
| L-4 | Low | Exported agent activities have no caller check |
| L-5 | Low | Enrollment token hashes are unsalted |

**18 findings: 1 severe, 4 high, 8 medium, 5 low.**

**Progress, 2026-09-14:** H-3 and M-3 fixed. S-1 part-fixed and S-2's tooling
shipped — both stay open, for reasons stated in each. H-1 now detects the failure
it could not see. ⚠️ **Nothing below M-3 has been touched.**

⚠️ **S-1 was downgraded from Severe to High on 2026-09-14** after the deployment
was measured rather than assumed. The correction is kept in place rather than
edited away.

---

## Severe

### S-1 — Admin authentication trusts request headers with no proxy verification

> ⚠️ **Rated High, not Severe.** Kept under this heading, and keeping its `S-1`
> identifier, so the downgrade is visible rather than tidied away — the original
> rating rested on an assumption about container networking that measurement
> disproved. The correction is inside the finding.

**Where:** [app/security/admin_auth.py:95–134](app/security/admin_auth.py#L95-L134)

In `forward_auth` mode the entire administrative identity is read from request
headers:

```python
username = request.headers.get(settings.admin_user_header)   # x-authentik-username
groups   = _split_groups(request.headers.get(settings.admin_groups_header))
```

Nothing establishes that the request came from the Authentik proxy. I searched
for a trusted-proxy source check, a shared secret, a client-IP allowlist, and
`forwarded_allow_ips` — **there is none**:

```
$ grep -rn "trusted_prox|client.host|REMOTE_ADDR|X-Forwarded-For|forwarded_allow" app/
(no matches)
```

Anyone able to make an HTTP request directly to the application port is a full
administrator by sending two headers. There is no audit distinction between that
and a genuine sign-in.

⚠️ **Corrected 2026-09-14, after verifying the deployment.** The first version
of this finding claimed that any other container on the box could reach the
application, and that an SSRF in a co-located service became ATLAS administrator.
**Both were wrong**, and the correction is recorded rather than quietly edited
because a severity inflated by an unchecked assumption is its own kind of defect.

What was actually measured on the dev host:

| Claim | Reality |
|---|---|
| Containers share a network with ATLAS | `takmdm-api-1` is on `takmdm_default` with **only** `takmdm-db-1`. No other stack is attached. |
| Other containers can reach the port | The port is published `127.0.0.1:8760`, not `0.0.0.0`. A container's own loopback is not the host's, and the bind excludes the docker gateway. |
| Caddy is a container | Caddy runs **on the host**, reaching `127.0.0.1:8760` directly. |

**What remains true, and why this is still a finding.** Everything that can open
a socket to the host's loopback is a full administrator by sending two headers:

- Any process on the host, under any user account that can reach loopback.
- Any container started with `--network host`.
- Anyone with SSH access or a port-forward (`ssh -L 8760:127.0.0.1:8760` — an
  invocation the module's own help text prints).
- An SSRF in a **host-level** service, Caddy included.
- A compose override, debug session, or misconfiguration that republishes the
  port on `0.0.0.0`, which converts this into remote unauthenticated admin.

There is no audit distinction between any of those and a genuine sign-in.

**Downgraded from Severe to High.** The blast radius is unchanged — full
administrative control — but reaching it requires code execution on the host or a
configuration error, not merely a foothold in a neighbouring container.

`R7` in `PROJECT_STATE.md` records the same trust assumption for the *device* API
and notes "the app does not refuse to start when no trusted proxy is configured."
The **admin** surface has the identical hole and is not recorded there.

### ✅ InfraTAK has already solved this, for itself

InfraTAK core hit this exact finding — their source labels it **"v10.1.1 S1"** —
and fixed it with a shared secret:

```caddy
forward_auth @needs_sso 127.0.0.1:9090 { ... }
request_header @needs_sso X-Infratak-Proxy-Auth <64-hex secret>
reverse_proxy 127.0.0.1:5001
```

The secret is attached **after** forward_auth passes, on the same matcher, so it
is present exactly when authentication succeeded. The console then requires it
alongside `X-Authentik-Username`. Their comment states the intent precisely: *"a
forged identity header alone is dead even if the client strip above ever
regresses."*

⚠️ **ATLAS's vhost already strips this header inbound** (`request_header
-X-Infratak-Proxy-Auth`, emitted for every vhost) so a client cannot forge it —
but the generator **sets** it only for InfraTAK's own upstream at
`127.0.0.1:5001`. Module vhosts get the strip and not the injection, so the
mechanism is half-present on ATLAS: protected against forgery, and carrying
nothing to verify.

### ⚠️ Status: partially mitigated in v1.16.0 — the finding stays open

**What shipped (option 3 below):** `TAKMDM_TRUSTED_PROXIES` bounds which peer
addresses the administrative surface answers. The check runs **before** the
identity headers are read, so a refused caller is never authenticated. The
InfraTAK module writes the value — the Docker bridge subnet, detected at deploy —
and backfills it on update, because the update path does not rewrite `.env`.
`--no-proxy-headers` is now explicit in the image so uvicorn cannot rewrite the
peer from `X-Forwarded-For`, which would have made the control bypassable by the
very class of header it defends against.

**What it does not do, and this is the point:** Caddy runs on the host and
reaches the container through the bridge gateway — *and so does every other
process on that host*. The peer address cannot separate them. This closes the
accidental-exposure case and leaves host-local forgery exactly where it was.

**Unset still means not enforced**, deliberately. Failing closed on a missing
value would brick every existing deployment on the next routine update, since
`_run_update` never rewrites `.env`. It warns at startup instead, and the module
supplies the value. A control that can lock an operator out of the console it
protects is not a control, it is an outage.

**Option 1 is the fix, and it is upstream.** Until the Caddyfile generator offers
the proxy-auth secret to module vhosts, ATLAS cannot tell Caddy from anything else
on the host, and no amount of ATLAS-side code changes that.

**Recommendation, in order of what actually closes the gap:**

1. **Have the Caddyfile generator offer the proxy-auth secret to module vhosts**,
   and verify it in ATLAS alongside the identity headers. This is the complete
   fix, it is InfraTAK's own mechanism, and it is the only option that defeats a
   host-local forgery. It needs a change upstream, because modules do not control
   the generated vhost.
2. **Refuse to start in `forward_auth` mode without a trusted-proxy
   configuration**, matching the existing `TAKMDM_CONSOLE_ORIGIN` warning.
   ATLAS-side, ships immediately.
3. **Reject requests whose client address is not the expected proxy source.**
   ATLAS-side. Closes the accidental-exposure case (port republished on
   `0.0.0.0`, reached from the LAN) but **not** host-local forgery — Caddy and any
   other host process arrive from the same address, so the check cannot separate
   them. Worth having for the most likely failure, not mistaken for a solution.

---

### S-2 — Five private keys sit unencrypted in one directory

**Where:** [app/security/ca.py:124–136](app/security/ca.py#L124-L136),
[token_vault.py:52–63](app/security/token_vault.py#L52-L63),
[csrf.py:88–90](app/security/csrf.py#L88-L90),
[enrollment_qr.py:74–76](app/security/enrollment_qr.py#L74-L76),
[bundle.py:73–80](app/security/bundle.py#L73-L80)

`pki/` holds, all unencrypted at rest:

| File | What it grants |
|---|---|
| `ca.key` | Mint a client certificate for **any** device — full impersonation |
| `token_vault.key` | Decrypt every stored enrollment token secret |
| `bundle` signing key | Sign desired-state documents the agent trusts |
| `csrf` key | Forge CSRF tokens for any administrator |
| `enrollment_qr` key | Forge signed provisioning QR payloads |

The CA key is written with `encryption_algorithm=serialization.NoEncryption()`
and the code says so plainly. `R8` and `R12` record the first two; the other
three are not tracked as risks anywhere.

Read access to one directory is total compromise: impersonate devices, decrypt
enrolment credentials, forge management payloads, and forge admin actions. The
0600 mode is the only control, and the container runs as `APP_UID` with `pki/`
bind-mounted from the host.

### ⚠️ Status: hardened in v1.17.0 — the finding stays **Severe** and open

Nothing below reduces the severity, and it would be dishonest to present it as
if it did. A key the application reads at runtime, on a host the attacker is
assumed to have reached, is readable by that attacker. **Encrypting it with a
passphrase kept on the same host is the oldest anti-pattern in the subject** — on
this deployment the passphrase would live in `.env`, in the same directory, in
the same backup. It was considered and deliberately not done, because shipping it
would have looked like a fix.

What did change, all of it worth doing and none of it the answer:

* **No key is ever briefly world-readable.** All six writers now create the file
  with `os.open(..., O_CREAT|O_EXCL, 0o600)` instead of writing it and chmodding
  after. This also closes **M-3**.
* **`pki/` is created `0700`.** Measured on the reference box at `drwxr-xr-x`:
  the keys inside were correctly `0600`, but the directory was traversable and
  `ca.crt` world-readable.
* **A startup audit reports any key whose mode has widened**, naming the file and
  the remedy. This is the realistic failure — a restore, a `cp -r`, an archive
  unpacked at the default umask, a bind mount nobody tightened. None of them
  announce themselves, so something has to look on every start. It reports rather
  than refuses: an outage of the management plane leaves the keys no safer and
  removes the console an operator would investigate from.

⚠️ **The audit said five keys. There are six.** A guard written to stop the
old pattern returning found `app/cli.py` writing a development server key the
same way. The finding's own enumeration was wrong, which is a fair indication of
how a seventh would fare — so the audited list is now explicit, and a test creates
every key through its real constructor and asserts the list matches what appeared
on disk.

⚠️ **Verified on Linux, not on the workstation.** The mode assertions cannot
run on Windows, where `st_mode` reports `0o666` whatever is asked for. Running
them in a `python:3.13-slim` container found two of these tests broken by a
constructor signature — they had been silently skipping. Full suite on Linux:
**1786 passed**. Six mutation checks, all caught.

### ✅ v1.19.0 — the root can now leave the server

ATLAS supports an **offline root**: a long-lived root that signs only
intermediates, and a short-lived intermediate on the box that signs devices.

| | Before | After the ceremony |
|---|---|---|
| What a stolen `pki/` yields | A 10-year root | An intermediate valid ~1 year |
| How you recover | Re-enrol every device by hand | Revoke, re-issue, carry on |
| Cost | — | One ~15-minute ceremony a year |

⚠️ **This does not stop an attacker on the box from issuing certificates**, and
nothing on a single host can — the application signs unattended. What it changes is
that the damage **ends**.

⚠️ **The dangerous part was the migration, not the attack.** A deployment whose
root has gone offline looks, to the old code, exactly like a fresh install — and
`load_or_create` generated a new CA in that state, which would have invalidated
every enrolled device at once. It now raises `RootKeyMissing` and names both
recovery routes. Six mutation checks, that one first.

Verification walks the chain: every link's signature proved and every link's dates
checked, so an **expired intermediate stops its devices** — without which the short
life buys nothing. Retired intermediates stay in the trust store, because the
certificates they signed remain valid and dropping the issuer would lock out the
fleet.

The ceremony is [docs/CA-OFFLINE-ROOT.md](docs/CA-OFFLINE-ROOT.md). **It is opt-in
and has not been run on the reference box** — shipping the capability is not the
same as using it, and this finding stays Severe until the root is actually gone
from that server.

### ✅ v1.22.0 — certificates now renew themselves

Devices ask for a new certificate over their existing mTLS connection, before
expiry, reusing their StrongBox key. Nothing is re-enrolled, and rotating an
intermediate no longer touches a tablet. The renewal window is stated by the
server on every check-in, so it can be corrected without shipping an agent.

⚠️ **The key never changes, which is what makes it safe unattended.** There is no
swap to get half-done: a failed renewal leaves the working certificate exactly
where it was and tries again.

This also unlocks **short device certificates** — the validity can drop from 825
days to 90 once the fleet runs an agent that renews, so a stolen device credential
expires on its own. ⚠️ **Not done yet, and the ordering matters**: shortening
before the fleet has updated would strand every device still on an older agent in
90 days.

**What still has to happen:** run the offline-root ceremony; shorten device
certificates once the fleet is on agent 0.70.0 or later; and for the remaining
keys, custody the application only *asks* of — a KMS or an HSM (`R8`).

**Why Severe and not accepted risk.** The existing acceptance ("acceptable on a
single trusted host where the DB is equally exposed") holds for `ca.key` versus
the database. It does not hold for the *aggregate*: this directory is a single
object whose compromise defeats every independent control in the system at once,
including the ones designed to detect compromise.

**Recommendation.** The KMS/HSM answer `R8` already anticipates. Short of that,
two cheap improvements: encrypt the CA key with a passphrase supplied at start
(it is used rarely — at enrolment), and separate the signing keys from the CA so
one directory read is not everything.

---

## High

### H-1 — Fleet authorization is delegated entirely to Authentik

**Where:** [app/security/admin_auth.py:115–127](app/security/admin_auth.py#L115-L127),
and `TAKMDM_ADMIN_GROUP=` in the module's env template

```python
required = settings.admin_group
if required and required not in groups:
    raise HTTPException(403, ...)
```

When `admin_group` is empty the group check is skipped entirely — any identity
Authentik forwards is a full ATLAS administrator. The InfraTAK module ships it
**blank**, documented as "blank here means whoever Authentik let through".

Authorization then rests wholly on the Authentik application binding that
`_restrict_to_admins` creates. That binding was already found missing once
(recorded in `PROJECT_STATE.md`: *"ATLAS app had no policy binding — verified
live: `bindings: NONE`"*), and during that window every Authentik user was an
ATLAS administrator. The binding is created by a module that runs at install; if
it fails, is edited, or is lost in an Authentik restore, **ATLAS has no second
check and no way to notice**.

### ⚠️ Status: detection added in v1.17.1 — the delegation itself is unchanged

The empty group stays. A group ATLAS required would be a second place to manage
access and a bootstrap nobody could complete — until somebody created it and added
themselves, **nobody could sign in at all**. The module's `.env` argues this at
length and the argument holds. What was missing was not a second gate; it was any
way to know the first one had gone.

* **The binding check's answer is no longer discarded.** `_restrict_to_admins`
  already returned True/False and the deploy ignored it. The result is now
  recorded in settings and stated in the deploy log, in the words that matter:
  *"every authenticated Authentik user can reach the console — remote wipe,
  factory reset, policy push."*
* **Every update re-asks.** A check that only runs at install answers a question
  about the past; the binding can disappear to an Authentik restore or somebody
  unbinding the policy long afterwards.
* **The module tile carries the state.** Read from settings, never probed —
  `detect()` runs on every dashboard poll from several threads and must answer in
  under a second, so an Authentik round-trip there would make ATLAS's tile report
  Authentik's latency instead.
* ⚠️ **"Could not ask" is not "not restricted."** No Authentik, no token, no
  network returns `None` and leaves the stored value alone. Reporting a failure
  because the identity provider was briefly unreachable would train an operator
  to ignore the one message that matters.
* **ATLAS says its own posture at startup**: with no group configured, every
  identity the proxy forwards is a full administrator, and the log says so
  alongside the existing warnings for disabled auth and an unset origin.

**What is still true:** if the Authentik binding is removed, ATLAS will keep
accepting whoever Authentik authenticates until a deploy, an update, or a reading
of the tile. That is a detection latency, not a gate, and closing it properly
means ATLAS having authorization of its own — which is the bootstrap problem
above, and a product decision rather than a patch.

---

### H-2 — The agent signing key is an unrecoverable single point of failure

**Where:** `agent/keystore.properties`, recorded as `R15`

Android refuses an update signed by a different key. Losing it means **no device
can ever be updated again** without a factory reset of the entire fleet; stealing
it means an attacker who also controls a distribution path can sign an agent the
devices accept as genuine.

W162 raised the stakes: OTA self-update is now the delivery mechanism, and this
audit's own release process pushed a new signed APK. Signature continuity is
verified at release time, which is good practice, and it also means the key is in
routine use on a workstation.

**Recommendation.** Belongs with `S-2` in the same key-management answer. At
minimum: an offline backup of the keystore held separately from the build
machine, and a documented recovery position for "the key is gone".

---

### H-4 — A device's own serial number reached a JavaScript string in the console

**Found in v1.27.0, while converting the inline handlers for M-6. Fixed by that
same conversion.** It was not in the original audit; the original audit had
recorded the console's XSS posture as good, on the strength of autoescaping being
on and `|safe` appearing in only three audited places. Both of those remain true.

**Where:** `app/web/templates/device_detail.html` — two forms:

```html
onsubmit="return confirm('Retire {{ device.serial_number }}? ...');"
```

⚠️ **Autoescaping did not help here, and looking at it would suggest it did.**
Jinja escaped the apostrophe to `&#39;`. The browser decodes entities in an
attribute value *before* handing it to the JavaScript parser, so the escaped
apostrophe arrives as a live `'`, ends the string, and everything after it runs
with the signed-in administrator's session. Autoescape is an HTML escape; the
context was JavaScript.

The console can wipe and retire devices, so script execution in an
administrator's session is fleet-level.

#### What an attacker needs

A serial number is reported **by the device** at enrolment and validated only for
length (`min_length=1, max_length=64`, [schemas.py:46](app/api/schemas.py#L46)).
So this needs an enrolment credential — and **M-7** records that the permanent
enrolment QR is designed to be printed and left on a provisioning bench.

One thing narrows it, and it is worth stating because it is easy to mistake for a
fix: the serial also becomes the certificate subject's CN, encoded as an ASN.1
`PrintableString`. A payload containing `;`, `<`, `!` or `_` is refused by the
X.509 encoder at enrolment. That leaves `A-Z a-z 0-9 space ' ( ) + , - . / : = ?`

`SER'),alert(1),('` is built entirely from that alphabet, and is what the
regression test uses.

#### ✅ Fixed in v1.27.0

Both handlers became `data-confirm`, read by a delegated listener in `atlas.js`.
The same bytes are now a string handed to `window.confirm` — there is no script
context on the page for a decoded apostrophe to escape from, and `script-src
'self'` means an injected one could not create one.

`test_a_device_serial_cannot_close_a_javascript_string` enrols a device with that
serial and asserts the device page renders it while carrying no inline handler.
Restoring the `onsubmit` fails it.

⚠️ **The general lesson is not about this page.** Autoescaping protects the HTML
context it knows about. Every remaining place a template value lands inside a
JavaScript string, a URL, or a CSS value is unprotected by it — the inline-handler
guard in `tests/test_security_headers.py` now makes the first of those three
impossible to reintroduce, and the other two have not been audited.

---

### H-3 — Dependencies pinned two years back, with no scanning and no CI

**Where:** [requirements.txt](requirements.txt)

The project operates in September 2026 against pins from late 2024:

| Package | Pinned | Released |
|---|---|---|
| `fastapi` | 0.115.0 | Sept 2024 |
| `cryptography` | 43.0.1 | Sept 2024 |
| `jinja2` | 3.1.4 | May 2024 |
| `uvicorn` | 0.30.6 | Aug 2024 |
| `sqlalchemy` | 2.0.35 | Sept 2024 |
| `python-multipart` | 0.0.12 | Oct 2024 |

### ✅ Resolved in v1.26.0 — the list, and then the fix

`pip-audit` was run. The answer was **24 advisories across five packages**:

| Package | Pinned | Advisories | Fixed in |
|---|---|---|---|
| `python-multipart` | 0.0.12 | 7 | 0.0.31 |
| `starlette` | 0.38.6 | 7 | 1.3.1 |
| `cryptography` | 43.0.1 | 6 | 49.0.0 |
| `jinja2` | 3.1.4 | 3 | 3.1.6 |
| `pytest` | 8.3.3 | 1 | 9.0.3 |

⚠️ **The two worst are the two that read untrusted input.** `python-multipart`
parses every file upload this system accepts, and `starlette` is the HTTP layer
under every request. Neither was a judgement call about exploitability once the
list existed.

Upgraded to `fastapi` 0.141.1 (bringing `starlette` 1.6.0), `cryptography` 50.0.1,
`python-multipart` 0.0.32, `jinja2` 3.1.6, `sqlalchemy` 2.0.53, `pydantic` 2.13.5,
`uvicorn` 0.53.0. **1850 tests pass** on the new stack; 22 references to three
Starlette status constants renamed where they had been deprecated.

### ⚠️ The pytest advisory was a *production* finding, and should not have been

`requirements.txt` is what the Dockerfile installs, and it carried `pytest` — so
test tooling shipped into the running image, and its advisory counted against the
deployment. Split into `requirements.txt` (runtime) and `requirements-dev.txt`.
Both now report **no known vulnerabilities**.

### The control

`.github/workflows/ci.yml` — the repository had none. It runs the suite **on
Linux** (six key-permission tests skip on Windows, and running them on Linux is
how two were found broken) and `pip-audit` against the production requirements,
failing the build. Dev requirements are audited too but non-blocking: a test-only
advisory should be visible without stopping a release for something no running
server imports.

⚠️ **It also runs weekly on a schedule.** Dependencies rot without anyone
touching the code, so time has to be a trigger — pinning without scanning means
the versions cannot drift *into* a fix on their own, which is exactly how 24
advisories accumulated unnoticed.

**Remaining:** Dependabot or Renovate for the upgrade cadence, so the weekly
failure arrives with a pull request attached rather than a chore.

---

## Medium

### M-1 — Uploads are read whole into memory with no size limit

**Where:** [app/api/routers/packages.py:55](app/api/routers/packages.py#L55) and
seven sites in [app/web/routes.py](app/web/routes.py) — `data = file.file.read()`

Every upload path buffers the entire file in memory before inspection, and
`inspect_apk` / `dted.plan` wrap that in `io.BytesIO(data)`. The application
enforces **no size cap**. `docker/nginx/nginx.conf` sets `client_max_body_size`
between 4 MB and 2048 MB depending on location — but the InfraTAK deployment
fronts ATLAS with **Caddy**, and the vhost the module writes sets no request body
limit at all.

`app/artifacts/dted.py` documents a real operator sample at **726 MB compressed,
1.75 GB inflated**. A handful of concurrent uploads exhausts the container's
memory and takes the management plane down with it — which also stops every
device check-in.

**Recommendation.** A streaming read with a byte cap enforced in the application
(it cannot be delegated to a proxy that varies by deployment), and a
`request_body max_size` in the Caddy vhost.

### ✅ Fixed in v1.28.0

⚠️ **A correction to the finding above, which understated one thing and
overstated another.** `max_upload_bytes` (2 GiB) did exist, and every one of the
thirteen handlers checked it. What none of them did was check it before
`file.file.read()` had already materialised the body — so the 413 was correct and
useless: a 50 GB POST was refused once 50 GB was resident.

So this was never "no size limit". It was a limit applied at a point where it
could not prevent anything.

**The application.** [app/api/uploads.py](app/api/uploads.py) reads in 1 MiB
chunks and raises `UploadTooLarge` the moment the running total passes the cap.
Peak use is the cap plus one chunk, whatever the sender does. All thirteen sites
converted; each keeps the error shape it had, because a JSON endpoint and a
browser form need different refusals and the operator only ever sees one of them.

⚠️ **The two multi-file handlers pass the *remaining* budget**, not the cap. Ten
files of 300 MB is the same denial of service as one file of 3 GB, and checking
each against the full cap would wave it through.

**The proxy.** The ATLAS vhost now emits:

```
request_body {
    max_size 2304MiB
}
```

Deliberately **above** the application's 2 GiB, so an over-size upload is refused
by ATLAS with a message naming the limit rather than by Caddy with a bare 413.
Verified by adapting the box's real Caddyfile rather than by reading the docs:
`caddy validate` accepts it, and the adapted JSON puts the `request_body` handler
at index 1 of the vhost's handler chain — ahead of the subroute holding
`forward_auth` and `reverse_proxy`, which is what makes it apply at all.

⚠️ **`_run_update` did not regenerate the Caddyfile**, only `deploy` did. Without
noticing that, this directive would have reached the box and sat inert until
somebody happened to redeploy — the same shape of failure as the twelve releases
of stale module pins. The update path re-emits the vhost now.

#### What is still true

A *permitted* upload is materialised as `bytes` and usually copied again into an
`io.BytesIO`, so one 2 GiB upload costs roughly 4 GiB. The dev box has 31 GB, so
the ceiling is survivable there and is not a claim about anyone else's. Bounding
it properly means handing the file object to `inspect_apk` and `dted.plan`
instead of bytes — a refactor of both, not a line in the reader. Recorded rather
than implied, because "M-1 fixed" should not be read as "uploads are cheap now".

---

### M-2 — Server-side fetch of operator-supplied URLs, following redirects

**Where:** [app/services/geocoding.py:83–116](app/services/geocoding.py#L83-L116)

```python
url = endpoint(session)          # operator-set location.geocoder_url, unvalidated
http = httpx.Client(timeout=..., follow_redirects=True)
response = http.get(url, params={...})
```

`endpoint()` returns the stored setting with no scheme, host, or address
validation. The same pattern applies to `location.suggest_url`. The server will
fetch `http://169.254.169.254/...`, `http://localhost:9000/...`, or any container
on the Docker network.

⚠️ **Correction (v1.29.0): "and return part of the response to the console" was
wrong.** `_parse` extracts only `lat`, `lon` and `display_name` from a JSON list,
and `GeocodingError` carries a fixed string rather than the `httpx` error — so
neither the response body nor the failure detail reaches the console. What the
finding actually is, stated properly: a **blind** SSRF with a status-and-timing
oracle, plus a narrow read channel for any endpoint whose JSON happens to parse
as a place. That is still worth fixing; it is not the exfiltration primitive the
sentence described.

⚠️ **`follow_redirects=True` widens this beyond the admin who set it.** Even a
legitimate external geocoder — or an open redirect on one — can send the fetch to
an internal address without the setting ever changing.

Rated Medium rather than High because setting the URL requires administrator
access. It is not Low because it reaches *beyond* the fleet an admin already
controls, into the host's internal network.

**Recommendation.** Validate the scheme, resolve the host and reject private and
link-local ranges, and stop following redirects (or re-validate each hop).

### ✅ Fixed in v1.29.0

[app/security/outbound.py](app/security/outbound.py), used by both `search` and
`_ask_photon`. `follow_redirects=True` is gone from both.

⚠️ **The recommendation above is half wrong, and following it literally would
have shipped an outage.** "Reject private ranges" would refuse
`http://10.0.0.5:8080/search` — a self-hosted Nominatim or Photon on a private
LAN, which is precisely what an air-gapped TAK installation runs. The
deployments that most need this product are the ones that fix would have broken,
and the breakage would look like "address lookup stopped working" with no
obvious cause.

So the policy has two axes, and only the second is about the attacker the
finding names:

| | Allowed | Refused |
|---|---|---|
| **What an admin may configure** | public, and their own LAN | loopback, link-local, multicast, unspecified — no geocoder is at any of those |
| **Where a redirect may go** | anywhere no more internal than where the chain started | public → internal, at any hop |

The second row is the part that reaches past the administrator: an external
geocoder, or an open redirect on one, steering the fetch inward while the
setting stays exactly as they left it. Redirects are followed by hand with a hop
limit rather than by `follow_redirects=True`.

Two details worth recording because the obvious version of each is wrong:

* **`is_global`, not a hand-written list of private ranges.** CPython maintains
  it against the IANA special-purpose registries, which is how `100.64.0.0/10`
  — shared address space, and Alibaba's metadata range — is caught. ⚠️ Python's
  `is_private` does **not** cover it. The one thing `is_global` gets wrong here
  is multicast, which reports global.
* **A host is internal if *any* of its addresses is.** A hostile resolver can
  answer with several in any order, so judging by the first is a coin toss the
  attacker calls.

#### What this does not close

⚠️ **DNS rebinding.** The host is resolved for validation and resolved again by
`httpx` when it connects. A name that answers publicly the first time can answer
`127.0.0.1` the second. Closing it means connecting to the validated address and
carrying the hostname only in SNI and `Host`, which httpx does not expose without
replacing its transport. The attacker must control DNS for a host an
administrator typed into the settings. Recorded rather than left out of the
claim.

#### A side effect worth knowing about

The guard resolves hostnames, so it made the test suite query
`nominatim.openstreetmap.org` and `photon.komoot.io` on every run — the W101
mistake (a test that quietly queried a third party) reappearing through a
security fix, and a suite that would fail outright on a machine with no DNS.
`tests/conftest.py` now replaces the resolver for every test; the whole suite
performs no external lookups.

---

### M-3 — Private key files are created before they are made private

**Where:** all five key writers — e.g.
[token_vault.py:61–62](app/security/token_vault.py#L61-L62)

```python
key_path.write_bytes(key)
key_path.chmod(0o600)
```

Between those two statements the key exists with the process umask's permissions
— commonly `0644`. The window is short but it is a real race on a host with other
users or processes, and it applies to `ca.key`, `token_vault.key`, the CSRF key,
the QR key, and the bundle signing key.

**Recommendation.** `os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)`
and write through that descriptor. One helper, five call sites.

---

### M-4 — A fleet-takeover receiver is exported in release builds

**Where:** [agent/app/src/main/AndroidManifest.xml:304–311](agent/app/src/main/AndroidManifest.xml#L304-L311),
[DebugConfigReceiver.kt](agent/app/src/main/java/com/taksolutions/atlasmdm/admin/DebugConfigReceiver.kt)

`DebugConfigReceiver` accepts a broadcast that sets `server_url`,
`enrollment_token`, and `server_ca_pem` — repointing the agent at an arbitrary
management server. Its own docstring names it correctly: *"a receiver that can
repoint an agent at an arbitrary server is a fleet takeover primitive."*

It **is** guarded — `if (!BuildConfig.DEBUG) return` is the first statement. But
the manifest declares it `exported="true"` `enabled="true"` in **all** build
types, so the entire defence is one boolean at runtime. Any app on the device can
send the broadcast; only that check stops it.

For a primitive of this consequence, one line of runtime logic is thin. A build
misconfiguration, a refactor that drops the guard, or a debug build reaching a
real device are all ordinary events.

**Recommendation.** Remove it from the release manifest — `tools:node="remove"`
in a `release/AndroidManifest.xml`, or `android:enabled="${debugReceiver}"` from
a manifest placeholder. Keep the runtime check as the second layer, not the only
one. A signature-level custom permission would also work.

### ✅ Fixed in v1.28.0 — agent 0.70.1 (versionCode 116)

[`agent/app/src/release/AndroidManifest.xml`](agent/app/src/release/AndroidManifest.xml)
removes the declaration with `tools:node="remove"`. The first of the two
recommended forms, chosen over the placeholder: a component absent from the
merged manifest cannot be enabled by a `pm enable`, a package-manager call, or
anything else, because there is nothing left to enable. `BuildConfig.DEBUG` stays
in the Kotlin as the second layer — it does nothing about a *release* APK, but a
debug build reaching a real device is the case it does cover.

**Verified on the built artifacts, not on the source.** `aapt2 dump xmltree`:

| Variant | `DebugConfigReceiver` |
|---|---|
| `app-debug.apk` | present, `exported=true` — bench provisioning over ADB still works |
| `app-release.apk` | **absent** |

⚠️ The class's own KDoc claimed it was "compiled out of release builds". It was
not: the class shipped, the receiver was declared in every build type, and the
runtime boolean was the whole defence. The comment is true now because the
overlay exists; it was false when it was written, and a reader auditing this file
would have believed it.

`tests/test_debug_receiver_removed.py` guards what a source-only test can: that
the overlay exists, that it *removes* rather than disables, that the name it
removes is still the name the main manifest declares (⚠️ `tools:node="remove"`
for a component nothing declares is a silent no-op — the build succeeds and the
overlay reads exactly as it does today), and that the runtime guard is still the
first statement of `onReceive`. Seven mutations of those; all seven fail.

---

### M-5 — Outbound credentials stored in plaintext in the database

**Where:** [app/services/settings_store.py:22–25](app/services/settings_store.py#L22-L25)

SMTP, Active Directory bind, and SMS API credentials are stored unencrypted in
`app_setting`. The module docstring documents this and rates it "next in danger
to `pki/ca.key` and the token vault", which is a fair assessment.

The console never echoes them back (verified: `test_blank_password_keeps_the_stored_one`),
so the exposure is a database read — a backup, a dump, a read-only SQL injection
elsewhere, or the Postgres container.

Note the asymmetry: the Google Play AAS token **is** sealed in the token vault
([google_play_link.py](app/services/google_play_link.py)), and the enrollment
secrets are too. These three fields are the ones left behind.

**Recommendation.** Seal them with the existing `TokenVault` — the mechanism is
already in the codebase and already used for exactly this purpose.

### ✅ Fixed in v1.27.0

`save_group` seals every field of a secret kind through the existing
`TokenVault`; `group_values` unseals on the way back out.

⚠️ **Credentials written before this release still work.** `_unseal` returns the
stored string unchanged when it is not sealed, so an upgrade does not lock an
operator out of their own SMTP relay and then blame the password. They are
re-sealed the next time the group is saved. The cost is that a plaintext value
cannot be distinguished from a corrupt sealed one — accepted, because the
alternative is a migration that must guess.

Guarded by `test_every_secret_field_is_sealed_in_the_database` (reads the row
back out of the database and asserts the plaintext is not in it) and
`test_a_credential_written_before_sealing_still_works`.

---

### M-6 — No security response headers anywhere

**Where:** [app/main.py](app/main.py) — no `add_middleware` call of any kind

Neither the application nor `docker/nginx/nginx.conf` sets
`Content-Security-Policy`, `X-Frame-Options`, `X-Content-Type-Options`,
`Referrer-Policy`, or `Strict-Transport-Security`.

The console's own XSS posture is good (autoescape on, `|safe` used in exactly
three audited places), so CSP here is defence in depth rather than a fix for a
known hole. `X-Frame-Options`/`frame-ancestors` is the more concrete gap:
clickjacking a console that can wipe devices is worth preventing outright.

**Recommendation.** One middleware setting all five. CSP can start in
report-only; the console loads no third-party scripts, so a strict policy is
achievable.

### ✅ Fixed in v1.27.0

[`app/security/headers.py`](app/security/headers.py), installed as middleware in
`main.py` so the static mount and the error responses — the two that a
per-router dependency always misses — are covered too.

Enforcing, not report-only. Two things were measured first, and either would
have made the policy worthless or actively breaking:

| Assumption that had to be checked | What was actually there |
|---|---|
| The console has no inline script | It had **four** `on*` handlers. They were converted to `data-confirm`, `data-reveals` and `data-add-app-group`, delegated from `atlas.js`. |
| Images are ours | ⚠️ Map tiles are fetched **by the browser** from `location.tile_url`, an operator-set value defaulting to openstreetmap.org. A reflexive `img-src 'self'` would have blanked every map on every deployment, with the reason only in the browser console. |

The policy:

```
default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline';
img-src 'self' data: https:; font-src 'self'; connect-src 'self';
object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'
```

plus `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy: same-origin`
and a `Permissions-Policy` denying geolocation, camera, microphone, payment and
USB.

`script-src 'self'` with no `'unsafe-inline'` is the only directive here that
turns an injection into inert text; everything else shapes one. It is true only
while no template reintroduces an inline handler, so
`tests/test_security_headers.py` asserts per template that none has — and, for
each converted control, that the listener exists, is registered for the right
event, and still reads the attribute the template writes. Seven mutations of that
wiring were checked; all seven fail the suite.

Two deliberate holes, both documented in the module:

* **`img-src ... https:`** — wider than the rest, because the tile origin lives
  in the database and changes without a restart.
* **`/docs` and `/redoc`** get a policy allowing Swagger's CDN and its inline
  bootstrap. Under the strict policy those pages render blank with the reason
  only in the console. Framing, forms and objects stay refused.

⚠️ **HSTS is deliberately absent.** Caddy already sets it — verified on the
box, not assumed: `header Strict-Transport-Security "max-age=31536000;"` on the
`atlas.` vhost, and that is the *only* security header Caddy emits. Two emitters
for one header is how the two come to disagree, and the one an operator reads is
not necessarily the one the browser obeys. The other five have no second source.

---

### M-7 — The permanent enrollment QR is a non-expiring credential

**Where:** enrollment QR flow; documented in `app/web/guides/howto/01-enrolment.md`

The default QR is a 15-minute derivative. The **permanent** option produces a
code that never expires, designed to be printed and left on a provisioning
bench. The guide states the trade-off in as many words.

This is a deliberate, documented product decision and is recorded here for
completeness rather than as an error. The residual risks are worth stating
plainly: a photograph of that sheet enrols devices indefinitely; there is no
per-use audit distinguishing legitimate from stolen use; and revocation is
fleet-wide ("Retire & create new"), not per-credential.

**Recommendation.** Not a code change — an operational one. Consider an optional
expiry or use-count on permanent tokens, and surface "enrolments by token" so
anomalous use is visible.

---

### M-8 — No rate limiting on any endpoint

**Where:** [app/main.py](app/main.py) — no middleware; no limiter dependency

Nothing limits request rate on enrolment, the device API, or the console.

Credential brute force is **not** the practical risk: enrollment secrets are
`secrets.token_urlsafe(32)` (256 bits), HMAC comparisons use
`hmac.compare_digest`, and the bypass PIN has an attempt counter
(`Device.bypass_attempts`). Those are all done correctly.

The real exposure is resource exhaustion — unauthenticated requests to the
device port, and the memory amplification in **M-1**.

**Recommendation.** A limiter on the enrolment and device endpoints, sized well
above a real fleet's check-in rate.

---

## Low

### L-1 — DTED archive paths pass through the server unsanitised

**Where:** [app/artifacts/dted.py:190–191](app/artifacts/dted.py#L190-L191)

Entries not matching the cell pattern keep their raw archive name as the
destination: `moves.append((name, normalised))`, with no rejection of `..`.
`mission_package.py:332` does strip traversal segments; DTED does not.

**This is not currently exploitable**, and the reason is good code elsewhere: the
agent's extractor performs a canonical-path check and throws
`SecurityException("archive entry escapes destination")`
([FileDeployer.kt:163–168](agent/app/src/main/java/com/taksolutions/atlasmdm/files/FileDeployer.kt#L163-L168)).
Zip-slip is stopped at the point of write, which is the right place.

Recorded as Low because the server is planning paths it has not validated, and
the only thing preventing arbitrary file write on every device is a check in a
different codebase that ships on its own release cycle.

**Recommendation.** Reject `..` and absolute paths in `plan_layout`, matching
what `mission_package.py` already does.

### ✅ Fixed in v1.27.0

`_escapes()` refuses `..` **as a path segment**, a leading `/`, and a Windows
drive letter; `plan_layout` raises `DtedError` naming the offending entry.

⚠️ Two details that a shorter version of this would have got wrong:

* The check normalises backslashes **itself** rather than trusting the caller.
  A zip written on Windows carries `..\..\payload`, which every test below reads
  as one harmless filename until the separators are converted.
* It matches `..` as a whole segment, not as a substring. `docs/a..b/notes.txt`
  is a filename, and refusing it would reject real archives with no explanation
  an operator could act on.

The agent-side check stays where it is. Two guards is the point: this one is on
the server's own release cycle.

---

### L-2 — CSRF cookie is readable by JavaScript for no reason

**Where:** [app/web/routes.py:335](app/web/routes.py#L335) — `httponly=False`

The token is also placed in a hidden form field, and `atlas.js` never reads the
cookie (verified). `httponly=False` therefore grants an XSS payload the token for
no functional benefit.

**Recommendation.** Set `httponly=True`. If a form submit breaks, the double
submit is relying on the cookie and the reason should be written down.

### ✅ Fixed in v1.27.0

`httponly=True`. Nothing broke, because the token reaches every form from the
hidden field.

`tests/test_csrf.py` asserts `HttpOnly` and `SameSite=lax` on the raw
`Set-Cookie` header. ⚠️ `Secure` is **not** asserted: `_render` reads it from
`get_settings()` called directly rather than through the dependency, so a test's
`console_origin` never reaches it and any assertion would be describing the
workstation's environment. The gap is recorded in the test file rather than
papered over with a passing assertion.

---

### L-3 — Markdown link URLs are injected into an attribute without quote escaping

**Where:** [app/web/markdown_lite.py:38–42](app/web/markdown_lite.py#L38-L42)

```python
text = html.escape(text, quote=False)          # " is NOT escaped
text = _LINK.sub(r'<a href="\2">\1</a>', text) # \2 lands inside an attribute
```

The module's docstring claims it "escapes all HTML first anyway". That is true
for element context and **not** for the attribute this line creates: a link
target containing `"` breaks out of the `href`. `javascript:` targets are also
unfiltered. Output reaches the page via `{{ guide_body | safe }}`.

Low because the input is repo-controlled markdown, not user input — there is no
path by which an attacker supplies a guide. It is a latent issue that becomes a
real one the day guides become editable.

**Recommendation.** `html.escape(text, quote=True)`, and an allowlist of `http`,
`https`, and relative schemes.

### ✅ Fixed in v1.27.0

`html.escape(text, quote=True)`, and `_safe_link` drops the anchor entirely
unless the target starts with `http://`, `https://`, `mailto:`, `/` or `#` —
compared after `.strip().lower()`, because a leading space defeats a bare
`startswith` and the browser ignores it.

A refused link renders as its own text rather than as a link. Silently dropping
the words too would make a guide read as though a sentence were missing.

Checked in both directions: `javascript:`, `JaVaScRiPt:`, `data:`, `vbscript:`
and a space-prefixed `javascript:` produce no anchor at all, while the https,
http, relative, fragment and mailto links the guides actually contain are
untouched. ⚠️ That second half matters as much as the first — an allowlist that
also drops real links turns every cross-reference in the documentation into
plain text, and nobody reports a link that merely stopped being a link.

---

### L-4 — Exported agent activities have no caller check

**Where:** [AndroidManifest.xml:192–198](agent/app/src/main/AndroidManifest.xml#L192-L198)
(`DeviceSettingsActivity`), and `PowerTileActivity` at 169–175

Both are `exported="true"` with no `android:permission` and no caller
verification, so any app on the device can launch them.

The impact is contained by design: `DeviceSettingsActivity` renders only what the
kiosk policy permits (`DeviceSettingsPlan.offers(kiosk, ...)`), so a malicious app
gains nothing the kiosk user was not already granted. The residual issue is that a
settings surface intended to be reached from the ATLAS launcher can be summoned
from anywhere.

**Recommendation.** `exported="false"` if the launcher is same-signature, or a
signature-level permission if not.

---

### L-5 — Enrollment token hashes are unsalted

**Where:** [app/services/enrollment.py:55](app/services/enrollment.py#L55) —
`hashlib.sha256(secret.encode()).hexdigest()`

A single unsalted SHA-256, which would be a serious finding for user-chosen
secrets. It is **not** here, because the input is `secrets.token_urlsafe(32)` —
256 bits of entropy makes precomputation and brute force equally hopeless.

Recorded only so a future change to shorter or operator-chosen tokens does not
inherit the hashing unexamined.

---

## What is done well

An audit that lists only faults misrepresents a codebase. These were verified,
not assumed:

- **Device authentication is thorough.** `require_certificate` verifies the CA
  signature, that the serial is a known certificate, that it is not revoked, that
  the device exists, and that it is `ENROLLED` — and identity comes from the
  certificate, never from a path parameter, so there is no IDOR in the device API
  ([deps.py:201–238](app/api/deps.py#L201-L238)).
- **Zip-slip is correctly prevented** where extraction happens, with a canonical
  path check and a clear exception.
- **No `extractall` anywhere** in the server; archives are read into memory by
  member name rather than written by path.
- **Artifact storage validates the digest** before building a path
  ([storage.py:86–92](app/artifacts/storage.py#L86-L92)), with a comment naming
  the escape it prevents.
- **Subprocess use is safe** — list-form arguments, no `shell=True` — and the
  durable Google Play token is written to a `0600` ini rather than argv,
  deliberately, because *"an AAS token passed as `-t …` sits in argv"*.
- **Admin routes are guarded at registration**, not per endpoint, so a new route
  is protected by default ([main.py:297–318](app/main.py#L297-L318)). This is the
  right structural choice and it is rare to see.
- **Jinja autoescape is on**, with `|safe` at three audited sites.
- **Constant-time comparison** for every HMAC, and 256-bit secrets throughout.
- **CSRF is identity-bound and origin-checked**, with a loud startup warning when
  the origin is unset.
- **Failure modes are documented in the code**, consistently, including the ones
  that were accepted rather than fixed. Several findings above were faster to
  confirm because the code said what it was doing and why.

---

## Recommended order of work

1. **H-3** — run `pip-audit`. It is the only finding whose real size is unknown,
   and the answer may reorder everything below it.
2. **S-1** — add a proxy-trust check. Highest impact for the least code.
3. **M-4**, **M-3**, **L-2**, **L-1** — small, self-contained hardening.
4. **M-5** — seal the remaining credentials with the vault already in use.
5. **M-1**, **M-2**, **M-6** — upload cap, SSRF validation, response headers.
6. **S-2**, **H-1**, **H-2** — the key-management and authorization answer.
   Architectural, and the only items here that need a decision rather than a
   patch.

---

*Prepared by static review. No finding was exploited; none should be treated as
confirmed-exploitable without testing, and none should be dismissed without it
either.*
