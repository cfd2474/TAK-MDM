# Remote server — connecting and administering

How to reach the ATLAS dev host from a Claude Code session on this workstation.

Everything here was **verified against the live host on 2026-09-07**. Where I
could not verify something, it says so rather than guessing.

---

## 1. The host

| | |
|---|---|
| Address | `209.182.235.108` (hostname `taksolutions`) |
| User | `root` |
| Password | `fkktpe5bQd` |
| SSH host key | `SHA256:BaB64OAdIoT8g1dARdzHOIfKcVhBg0Bev4GcR779VQ8` |
| Repo on the host | `/opt/atlas` |
| Compose services | `api`, `db`, `proxy` (containers `takmdm-api-1`, `takmdm-db-1`, `takmdm-proxy-1`) |

⚠️ **This is a development host and the operator has said so explicitly.** The
password is in this file because the next session cannot do the job without it and
the repo is private. It is *not* a pattern to repeat for anything that carries
real fleet data — a production host gets a key, not a password in a doc.

### Standing authorization

The operator has given a standing OK to **push server updates and agent APKs to
this host without asking each time** ("its always ok to push the agent apk and
server updates - we are in development"). That covers deploys, restarts and
publishing builds.

It does **not** cover: destroying data (`docker compose down -v`, dropping the
database, `rm -rf /opt/atlas`), or anything on a host that is not this one. Ask
first for those.

⚠️ **Superseded for releases, 2026-09-13.** ATLAS now ships as an InfraTAK
module and the operator deploys each release himself, through InfraTAK's update
function — *"do not push updates to the server, I will manually use the update
function of infraTAK to ensure they update properly"*. A release pushed from
here is a release whose update path was never exercised: it would work on this
box and break on everyone else's, and nobody would find out until a real
deployment. See `CLAUDE.md` section 9. The standing OK above survives only for
things the operator asks for in the moment.

---

## 1b. The InfraTAK dev host (W143)

A **second** host, added 2026-09-12 for the InfraTAK module work. Everything in
section 1 is about `209.182.235.108` and does not describe this box.

| | |
|---|---|
| Address | `199.241.139.160` |
| SSH port | **2222** — ⚠️ port 22 is refused, not filtered |
| User | `root` |
| Password | `4qKDPhmbWb` |
| SSH host key | `SHA256:p7DMadNOaIoZH1J3j+Yfe18dZPhSiTe3QsZsqQtYscs` |
| OS / arch | Ubuntu 22.04.5, x86_64 |
| InfraTAK | `/root/infra-TAK`, console as **root**, gunicorn on `0.0.0.0:5001` |

```bash
"/c/Program Files/PuTTY/plink" -batch -ssh -P 2222   -pw '4qKDPhmbWb'   -hostkey "SHA256:p7DMadNOaIoZH1J3j+Yfe18dZPhSiTe3QsZsqQtYscs"   root@199.241.139.160 "uptime"
```

⚠️ **`-P 2222` is as load-bearing as `-batch` and `-hostkey`.** Port 22 answers
with a connection refused, which reads like an unreachable host rather than a
moved service.

### What is authorised here

The operator described this box as *"my dev server (safe for testing, no
security risks)"* and supplied the credentials to do the InfraTAK module work on
it. That is authorisation for **this** host, for that work.

It does not extend to `209.182.235.108`, and the reverse is equally true: the
standing OK in section 1 was never about this machine. ⚠️ This box runs a live
InfraTAK stack — TAK Server, Authentik, CloudTAK, EUD Remote Assist, TAK Portal
and Caddy are all up. "Safe for testing" means the box is expendable, not that
the services on it are; breaking Caddy takes every one of them down at once.

---

## 2. Connecting

Use **PuTTY's `plink`/`pscp`**, not `ssh`/`scp`. OpenSSH is not reliably present
on this workstation, and `plink -pw` is what has actually worked all along.

Run these from the **Bash** tool (Git Bash), where the `/c/...` paths below
resolve. From the PowerShell tool the same binaries need Windows-style paths.

```bash
# Run a command on the host
"/c/Program Files/PuTTY/plink" -batch -ssh \
  -pw 'fkktpe5bQd' \
  -hostkey "SHA256:BaB64OAdIoT8g1dARdzHOIfKcVhBg0Bev4GcR779VQ8" \
  root@209.182.235.108 "cd /opt/atlas && docker compose ps"

# Copy a file up
"/c/Program Files/PuTTY/pscp" -batch \
  -pw 'fkktpe5bQd' \
  -hostkey "SHA256:BaB64OAdIoT8g1dARdzHOIfKcVhBg0Bev4GcR779VQ8" \
  ./local-file "root@209.182.235.108:/tmp/local-file"
```

⚠️ **`-batch` and `-hostkey` are both load-bearing.** Without `-batch` plink
prompts and the tool call hangs until it times out with no output. Without
`-hostkey` it prompts to cache the key — same hang. There is no interactive
terminal here, so any prompt is a dead call, not a question you get to answer.

---

## 3. The workflows

### 3.1 Look at something

```bash
plink … root@209.182.235.108 "cd /opt/atlas && docker compose logs --tail 100 api"
plink … root@209.182.235.108 "cd /opt/atlas && docker compose exec -T api alembic current"
```

`docker compose exec` needs **`-T`**: without it Compose asks for a TTY that does
not exist and the call fails.

### 3.2 Deploy server code

The repo is shipped as a tarball and extracted over `/opt/atlas`. The exclude
list is anchored (`./artifacts`, not `artifacts`) so it drops the *uploaded APK
store* at the repo root without also dropping the `app/artifacts` **source
package** — an unanchored pattern silently ships a broken server.

⚠️ **Stamp the build first.** The tarball excludes `.git`, so the running
server has no other way to say which revision it is — and the console footer
reads "build unknown" without it (W102). It records a dirty tree as dirty, which
is honest: deploying uncommitted work is ordinary, and labelling it with the last
commit alone would make the footer claim something false.

```bash
SP="<scratchpad>"   # the session scratchpad from your environment block
python scripts/write_build.py          # writes ./BUILD, which the footer reads
tar -czf "$SP/atlas.tgz" \
  --exclude='./.git' --exclude='./.venv' --exclude='./artifacts' --exclude='./pki' \
  --exclude='./cache' \
  --exclude='./Test Files' --exclude='./agent/build' --exclude='./agent/app/build' \
  --exclude='./agent/launcher/build' --exclude='./agent/testapp/build' \
  --exclude='./agent/.gradle' --exclude='./.pytest_cache' --exclude='./.env' \
  --exclude='__pycache__' --exclude='*.pyc' .

pscp … "$SP/atlas.tgz" "root@209.182.235.108:/tmp/atlas.tgz"

plink … root@209.182.235.108 \
  "set -e; cd /opt/atlas; tar -xzf /tmp/atlas.tgz; docker compose up -d --build api"
```

⚠️ **`./cache` is excluded for a reason you will not see fail.** It holds the
downloaded F-Droid and IzzyOnDroid indexes — ~180 MB, regenerable, and
gitignored, so it was easy to leave off this list. Shipping it overwrote the
host's copy with this workstation's, **carrying Windows uid 197609 onto files a
container running as uid 1000 then could not write**. The only symptom was one
startup warning saying search would load the index on demand; the console
worked, so nobody looked. Found 2026-09-11 and fixed on the host with
`chown -R 1000:1000 /opt/atlas/cache`.

⚠️ **`--build`, always.** Plain `docker compose up -d` keeps the old image and the
Python change appears to have had no effect. This is the single most expensive
trap on this host: the code is correct, the deploy reported success, and the
behaviour is unchanged. See "Operational notes" in `PROJECT_STATE.md`.

⚠️ **`.env` and `pki/` are excluded deliberately.** They are the host's identity —
the server URL, the agent signature checksum, the device CA. Shipping the local
copies once overwrote them with another deployment's values and broke provisioning
in a way that surfaced only as *"something went wrong"* on the tablet. If you must
change `.env`, edit it **on the host** and back it up first
(`cp .env /root/env-backup-$(date +%s)`).

Changes under `docker/nginx/` or `pki/` need `docker compose restart proxy`
instead — the proxy does not pick them up on its own.

### 3.3 Publish an agent APK

Build locally, copy the APK **into the container**, and run a short ingest script.

```bash
# 1. Bump agent/app/build.gradle.kts (versionCode AND versionName), then:
cd agent && ./gradlew :app:assembleRelease :app:testReleaseUnitTest :launcher:testReleaseUnitTest -q

# 2. Stage the APK and a publish script
cp agent/app/build/outputs/apk/release/app-release.apk "$SP/atlas-agent-<N>.apk"
sed 's/atlas-agent-<N-1>/atlas-agent-<N>/' "$SP/pub<N-1>.py" > "$SP/pub<N>.py"

# 3. Up to the host, into the container, run it
pscp … "$SP/atlas-agent-<N>.apk" "root@209.182.235.108:/tmp/atlas-agent-<N>.apk"
pscp … "$SP/pub<N>.py"           "root@209.182.235.108:/tmp/pub<N>.py"
plink … root@209.182.235.108 "set -e; cd /opt/atlas;
  docker compose cp /tmp/atlas-agent-<N>.apk api:/tmp/atlas-agent-<N>.apk;
  docker compose cp /tmp/pub<N>.py api:/tmp/pub<N>.py;
  docker compose exec -T -e PYTHONPATH=/app api python /tmp/pub<N>.py"
```

The publish script itself (keep a copy; the scratchpad ones do not survive a new
session):

```python
import pathlib
from app.db.base import SessionLocal
from app.config import get_settings
from app.artifacts.storage import LocalArtifactStorage
from app.services import packages, agent_update

storage = LocalArtifactStorage(pathlib.Path(str(get_settings().artifact_dir)))
with SessionLocal() as session:
    r = packages.ingest(
        session, storage,
        pathlib.Path("/tmp/atlas-agent-<N>.apk").read_bytes(),
    )
    session.commit()
    agent_update.publish(session, r.version.version_code, updated_by="deploy")
    session.commit()
    print("agent:", r.version.package.package_name, r.version.version_code,
          r.version.version_name)
    print("fleet pointer ->", agent_update.current(session))
    print("rollout:", agent_update.rollout(session))
```

⚠️ **`ingest` no longer takes `publish=`** (W139). It was removed with the
published flag, and a script still passing it dies with `TypeError` *after* the
APK has been copied into the container — which looks like a broken build rather
than a stale script. The agent's own update channel never used that flag:
`agent_update.publish` on the next line is a different mechanism with its own
pointer, and it is still what aims the fleet at a build.

⚠️ **`-e PYTHONPATH=/app` is required.** Running `python /tmp/pub<N>.py` puts
`/tmp` on `sys.path`, not the working directory, so the script dies with
`ModuleNotFoundError: No module named 'app'` even though `python -c "import app"`
works fine in the same container. `-w /app` does **not** fix it.

⚠️ **The server refuses a duplicate `versionCode`,** and Android refuses a
downgrade. Bump both `versionCode` and `versionName` before every build you intend
to upload.

⚠️ **Publishing is fleet-wide and immediate.** `agent_update.publish` aims every
enrolled device at that build. It is a deliberate act, not a side effect of a
server deploy — the operator's standing OK covers doing it, but do not do it by
accident while testing an ingest.

### 3.4 Migrations

**Back up first — nothing does it for you.** There is no cron on this host; the
`/root/takmdm-*.sql.gz` files are all manual, taken by previous sessions before
migrating.

```bash
plink … root@209.182.235.108 \
  "cd /opt/atlas && docker compose exec -T db pg_dump -U takmdm takmdm | gzip > /root/takmdm-$(date +%Y%m%d-%H%M%S).sql.gz"
```

Then deploy as in 3.2 and check `alembic current` before and after. Head as of
2026-09-07 is `t0v2x4z6b8d0`.

---

## 3.5 The public hostname and its certificate (W100)

`mdm.tak-solutions.com` is an A record for this host. The console answers on it:

| URL | What |
|---|---|
| `https://mdm.tak-solutions.com/` | 302 to `/enrollment` |
| `https://mdm.tak-solutions.com/enrollment` | the console, HTTP Basic |
| `https://…:9443/…` | unchanged, still works, self-signed |

⚠️ **443 is the console on a discoverable port.** The auth boundary is the same
HTTP Basic as 9443 and nothing about who may enter changed — but 443 is scanned
constantly and 9443 is not, so the strength of that one password now matters more.
There is no rate limiting in front of it.

⚠️ **The landing page mints credentials.** `/enrollment` is an operator page whose
"Generate QR" issues a 15-minute token that lets a device join the fleet. What was
added is convenience, not a public page.

### The certificate

Let's Encrypt, issued by webroot HTTP-01. nginx serves
`/.well-known/acme-challenge/` from `/opt/atlas/acme` on port 80 — which is
already published for the provisioning APK, and which Let's Encrypt requires in
the clear, since it follows no redirect to TLS.

⚠️ **Registered with no email contact**, deliberately: the operator's address is
for identifying them here, not for handing to a third party. That means **no
expiry warnings from Let's Encrypt** — the renewal timer is the only safety net.
Add one later with:

```bash
docker run --rm -v /etc/letsencrypt:/etc/letsencrypt certbot/certbot   update_account --email you@example.com
```

### Renewal

`atlas-certbot-renew.timer` runs twice daily (units in `docker/systemd/`, copied
to `/etc/systemd/system/`). ⚠️ **A timer, because this host has no cron** —
`crontab` is not on the PATH. Verify it works without waiting for expiry:

```bash
docker run --rm -v /etc/letsencrypt:/etc/letsencrypt   -v /var/lib/letsencrypt:/var/lib/letsencrypt -v /opt/atlas/acme:/var/www/acme   certbot/certbot renew --dry-run
systemctl list-timers atlas-certbot-renew.timer
```

Issuing a *new* name needs the 443 block edited first — and nginx will not start
naming a certificate that does not exist yet, so add the ACME path, issue, then
add the listener.

---

## 4. Endpoints

Verified 2026-09-07. The codes are the *expected* ones — a `403` here is the
design, not a fault.

| URL | Expect | What it is |
|---|---|---|
| `https://209.182.235.108:8443/healthz` | `200` | Device port, health |
| `https://209.182.235.108:8443/` | `403` | Device port default-denies `/`; only `/api/v1/...` is opted back in |
| `https://209.182.235.108:9443/` | `401` | Console, behind nginx Basic auth |
| `http://209.182.235.108:8080/api/v1/provisioning/agent.apk` | `200` | Provisioning download (port 8080 for guest Wi-Fi) |
| `http://209.182.235.108/api/v1/provisioning/agent.apk` | `200` | Same, on port 80 |

Use `curl -k` — the certificates are self-signed.

**Console credentials:** user `atlas`; the password is a bcrypt hash in
`/opt/atlas/pki/console.htpasswd` and **is not recorded anywhere I can read**. Ask
the operator, or reset it on the host with `htpasswd`. Note this is *nginx* Basic
auth and is separate from `TAKMDM_ADMIN_AUTH_MODE`, which is currently `disabled`
at the application layer — the 401 comes from the proxy.

---

## 5. Traps that have actually cost time here

These are real failures from previous sessions, not hypotheticals.

- **A green build is not evidence an edit landed.** A heredoc died silently and
  four sections were never written; everything downstream compiled and passed.
  Verify by grepping for a symbol you just added.
- **`docker compose up -d` without `--build`** keeps the old image. Covered above
  because it is the one that keeps recurring.
- **Curl against the console returns the 401 page, not your data.** Grepping that
  HTML for a value finds nothing and reads like the feature is broken. Check the
  status code before believing the body.
- **The terminal renders UTF-8 as cp1252**, so `·` and `…` come back looking
  corrupted. The bytes are usually fine — check them before "fixing" the source.
  Python writing to stdout may also die on `UnicodeEncodeError`; set
  `PYTHONIOENCODING=utf-8`.
- **A policy change made through `docker compose exec` does not wake anything.**
  The live-push bus is a set of `asyncio` waiters **inside the uvicorn process**
  (`app/services/notifications.py`: "waiters live in this process"). A script run
  with `docker compose exec` is a *different* process, so its post-commit wake
  reaches no parked long-poll, and the device only sees the change on its next
  scheduled poll — up to ~15 minutes later. Nothing reports this: the write
  succeeds, `state_version` bumps, and the device simply looks slow. Either wait
  for the poll, or make the change through the HTTP API so it happens inside the
  serving process.

- **`docker compose up -d --build` wipes the container's `/tmp`** — and it bit
  twice in one session, the second time silently: a watch loop kept polling a
  script that no longer existed and simply never reported, which looks exactly
  like a device that has stopped checking in. Scripts copied
  in with `docker compose cp` disappear with the old container, so a deploy in the
  middle of a session silently removes the tooling you staged before it. Re-copy
  after every rebuild.

- **Do not guess database column names** for an ad-hoc query. Read the model in
  `app/db/models.py`; previous sessions wrote watch scripts against columns that
  do not exist and spent the time debugging the wrong thing.

---

## 6. Related reading

- `PROJECT_STATE.md` — "Operational notes", plus the full chunk history and every
  decision with its rationale. **The source of truth.**
- `CLAUDE.md` — the working agreement, including the restart rules summarised here.
- `HANDOFF.md` — orientation for the project as a whole.
