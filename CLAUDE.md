# Project Workflow Rules

## 1. Project State File
- Maintain a running state file (`PROJECT_STATE.md`) in the repo root.
- Update it after every completed step with:
  - What's been completed
  - What's in progress
  - Constraints
  - Decisions made (with rationale)
- Read this file before starting any new step. Do not proceed without reading it first.

## 2. Task Decomposition
- Before executing complex work, break it into discrete chunks of 5-7 steps.
- Write the chunk plan into the state file before starting execution.
- Do not execute steps that aren't part of a defined chunk.

## 3. Validation Checkpoints
- After completing each chunk, stop.
- Provide a summary: what was done, what changed, any open questions/risks.
- Wait for explicit approval before starting the next chunk.

## 4. Troubleshooting vs. Assumptions
- When debugging, either troubleshoot (gather evidence, test hypotheses) or state assumptions explicitly and proceed - never mix the two silently.
- If troubleshooting is incomplete, do not make assumptions to fill the gap without flagging it.

## 5. SOLID Programming Principles
- Always make sure code falls under the SOLID programming design principles.

## 6. Android Platform Reference
- `docs/ANDROID_PLATFORM_REFERENCE.md` records the Android contracts this project
  depends on, each traceable to an official source, plus what has been verified on
  our own hardware.
- **Read it before writing or changing any code that touches provisioning, the
  Device Policy Controller, app installation, permissions, or file placement.**
  Check the change against it, and do not rely on recollection of how Android
  behaves.
- Platform contracts fail vaguely on purpose — "something went wrong" is a security
  decision, not an oversight. There is usually nothing to infer from the symptom, so
  consult the spec before reasoning from behaviour.
- Update the file whenever hardware teaches something new, marking it ✅ verified.
  Where an official source contradicts an observation, keep both and note the
  disagreement rather than deleting the observation.

## 7. Environment Traps
- Read "Operational notes" in `PROJECT_STATE.md` before debugging anything that
  looks impossible — a correct change appearing to have no effect is almost always
  a stale container or an unrestarted proxy, not a bug in the code.
- Python source changes require `docker compose up -d --build`. Plain `up -d`
  silently keeps the old image.
- Changes under `docker/nginx/` or `pki/` require `docker compose restart proxy`.

## 8. Remote Server
- `docs/REMOTE_SERVER.md` is how to reach the dev host `209.182.235.108`:
  credentials, the `plink`/`pscp` invocations that work here, and the deploy,
  APK-publish and migration procedures.
- **Read it before running anything against the host.** Every command in it has
  been run successfully; several have a non-obvious flag (`-batch`, `-hostkey`,
  `-T`, `PYTHONPATH=/app`) whose absence hangs the call or fails it misleadingly.
- The operator has given a standing OK to push server updates and agent APKs to
  that host without asking. It does not extend to destroying data, or to any other
  host.
- ⚠️ **Superseded for ATLAS releases by section 9.** That standing OK predates
  ATLAS shipping as an InfraTAK module. Releases now reach a server only when
  the operator runs InfraTAK's update — never from here.

## 9. Releases: bump the version, push to GitHub, never to a server

Every push that changes the product is a release. Two halves, and the second is
the one that is easy to get wrong by being helpful.

### Bump the version on every push

`VERSION` at the repo root is the product version. Move it forward in the same
commit as the change:

- **patch** (`1.0.0` → `1.0.1`) by default — fixes, refactors, docs, tests.
- **minor** (`1.0.0` → `1.1.0`) for a new capability an operator would notice.
- **major** only when the operator says so.

Then tag it, in that same commit:

```
git tag -a v1.0.1 -m "v1.0.1 — <what changed>"
git rev-parse 'v1.0.1^{}'      # the COMMIT, for the module pin
```

⚠️ **`git rev-parse v1.0.1` returns the tag object, not the commit.** An
annotated tag is its own object with its own SHA; recording it as the module pin
made a deploy refuse itself, because the clone's HEAD is the commit the tag
points at. The `^{}` suffix is not optional.

⚠️ **`VERSION` must equal the newest tag.** `tests/test_version.py` enforces it,
and that guard is the only reason a hand-maintained version string is allowed
here at all — `main.py` carried `version="0.1.0"` through a hundred work items
and taught anyone reading it nothing true. If the test fails, the fix is to bump
`VERSION`, never to weaken the test.

Three things follow a release and are easy to forget:

- **`dist/` APKs**, when `agent/` changed. Rebuild, copy in, and ⚠️ **raise the
  Android `versionCode`** — the seeder treats a repeated code as already present
  and silently keeps the old build, so a rebuilt APK at the same code ships
  nothing.
- **The module pin** in the infra-TAK fork (`modules/atlas.py`: `ATLAS_TAG`,
  `ATLAS_SHA`). It governs *fresh installs* only; updates resolve the newest tag
  themselves. Leaving it stale means a new install lands on an old release and
  immediately offers an update.
- **`PROJECT_STATE.md`**, per section 1.

### ⚠️ Two repositories, two owners (2026-09-14)

Operator: *"i cannot trigger infratak updates, just atlas. i want you to execute
update changes to infraTAK, i will do manual updates for atlas."*

| Repository | Who updates the box |
|---|---|
| `TAK-MDM` (ATLAS itself) | **The operator**, through InfraTAK's update button. Unchanged. |
| `infra-TAK` fork (`modules/atlas.py`, `templates/atlas.html`) | **Us**, over SSH: `cd /root/infra-TAK && git pull && systemctl restart takwerx-console`. |

The console has no self-update button, so module changes reached GitHub and stopped
there. ⚠️ **This went unnoticed for twelve releases** because the ATLAS updater
resolves the newest tag itself — a stale `ATLAS_TAG` never blocked an update, so
nothing looked wrong while every module-side change sat inert on the box.

**After changing the module or its template: pull it onto the box and restart the
console.** Confirm the route exists (a registered route answers `401`, an
unregistered one `404`) rather than assuming the import succeeded.

⚠️ Restarting `takwerx-console` restarts the management UI for the whole box, not
just ATLAS. It does not touch the running containers, but check it comes back.

### Never push an ATLAS release to a server

**The operator deploys ATLAS. Not us.** They run InfraTAK's update function by hand,
deliberately, so that the update path itself is exercised and proven on every
release rather than bypassed by a convenient `git pull` and rebuild.

Pushing the change to GitHub is the whole job. Do not, unless the operator asks
for that specific thing in that specific message:

- run a deploy, update, `docker compose up`, or a rebuild on any host;
- `git pull` on a server to pick a release up;
- restart the ATLAS containers to "make it take effect".

⚠️ **A server updated from here is a release whose update path was never
tested.** That is the failure this rule exists to prevent: it would work on the
operator's box and break on everyone else's, and nobody would find out until a
real deployment.

Reading the box is still fine — logs, `docker ps`, a rendered page, an audit of
what an uninstall left behind. The line is at *changing* it.
