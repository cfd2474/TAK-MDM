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
