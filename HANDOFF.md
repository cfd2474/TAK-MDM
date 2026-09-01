# Handoff — ATLAS

> **ATAK Tactical Lifecycle & Administration System.** A self-hosted Android MDM
> for Samsung Device Owner fleets, built around stackable composable policies.

**Status at handoff:** working end to end on real hardware. A Galaxy Tab S10 FE
enrols over mTLS, checks in, applies policy, and is woken by a long-poll in the
same second a policy is published. 254 tests passing, 26 commits, agent v8.

---

## 1. Read these first, in this order

| # | File | Why |
|---|---|---|
| 1 | [`CLAUDE.md`](CLAUDE.md) | The working agreement: chunked delivery, stop for approval, SOLID, and pointers to the two references below |
| 2 | [`PROJECT_STATE.md`](PROJECT_STATE.md) | **The source of truth.** Constraints, device matrix, every decision with its rationale (D1–D86), risk register, chunk history |
| 3 | [`docs/ANDROID_PLATFORM_REFERENCE.md`](docs/ANDROID_PLATFORM_REFERENCE.md) | **Mandatory before touching provisioning, the DPC, install, permissions or file placement.** Contracts traced to official sources, plus what is verified on our hardware |
| 4 | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | Design rationale |

Do not treat this handoff as a substitute for `PROJECT_STATE.md`. It is an
orientation; that file is the record.

---

## 2. What this is, in one paragraph

Policies are **typed, single-concern and stackable**. You assign several to a
device, group or tag with a rank, and a resolver merges them per field using a
strategy each field declares — `MAX` for `min_length`, `MOST_RESTRICTIVE` for
`allow_camera`, `UNION` for blocklists, and so on. Every resolved field records
where it came from and what it beat, so "why is this tablet's password length 12?"
is always answerable. That provenance is the product's differentiator and the
reason a mature MDM (Headwind) was evaluated and rejected as a base: its model is
one configuration per group, which is precisely what this replaces.

---

## 3. Run it

```bash
docker compose up -d --build          # --build is not optional; see §7
```

| Surface | Where | Notes |
|---|---|---|
| Admin console | http://localhost:8000 | Devices, policies, enrollment QR |
| API docs | http://localhost:8000/docs | All 38 endpoints |
| Device port | https://192.168.68.89:8443 | mTLS; admin routes 403 here |
| Provisioning APK | http://192.168.68.89:8080 | Plaintext, that one file only |

```bash
pytest                                 # 254 tests, no database or containers needed
python scripts/setup_for_tablet.py     # re-detect LAN address, reissue dev TLS cert
python scripts/dev_enroll.py           # simulate a device end to end
```

Agent build (note the JDK — Android Studio's bundled JBR 25 is rejected):

```powershell
$env:JAVA_HOME="C:\Program Files\Microsoft\jdk-17.0.20.8-hotspot"
cd agent; .\gradlew.bat assembleDebug
```

Then upload the APK through the console — **bump `versionCode`** first, the server
refuses duplicates.

---

## 4. Layout

```
app/
  policies/     merge strategies, spec schemas, type registry, the pure resolver
  services/     DB ↔ resolver bridge, enrollment, packages, files, notifications
  artifacts/    content-addressed storage, AXML parser, APK/XAPK inspection
  security/     device CA, bundle signing, token vault, admin auth
  api/routers/  device-facing and admin endpoints
  web/          server-rendered admin console (Jinja)
agent/          Kotlin Device Owner agent
alembic/        7 migrations
```

Four policy types: `PASSWORD`, `RESTRICTIONS`, `APP_CATALOG`, `FILES`.

---

## 5. Operator requirements, and where they stand

| | Requirement | State |
|---|---|---|
| F1 | Stacked policies per device | ✅ hardware-verified |
| F2 | One-to-many assignment, policy-first | ✅ |
| F3 | Immediate propagation | ✅ **verified on the tablet — woken in the same second** |
| F4 | User-selectable marketplace installs | ✅ server; agent UI **unproven on hardware** |
| F5 | Admin-controlled zip expansion | ✅ server; **unproven on hardware** |
| F6 | Kiosk optional, never default | ✅ modelled; **unproven on hardware** |

---

## 6. What is NOT yet proven on hardware

Enrolment, check-in, policy application and live wake are verified. These are
written, tested, and have never run on a device:

- **App install** — `PackageInstaller`, split APKs. The whole Chunk 4 pipeline ends here.
- **File placement and zip extraction** — needs all-files access
- **Marketplace** — optional file selection round trip
- **Kiosk / lock task**
- **Transient commands** — lock, wipe, locate have never been dispatched to a real device
- **StrongBox specifically** — key generation worked; whether it used StrongBox or fell back to the TEE is unconfirmed

**Suggested next step:** upload a small real APK, require it by policy, and watch
it install. That exercises the largest untested surface in one move.

---

## 7. Traps that have already cost real time

Full list in `PROJECT_STATE.md` → *Operational notes*. The expensive ones:

**`docker compose up -d` is usually not enough.** Python changes need
`--build` (source is baked into the image). Anything under `docker/nginx/` or
`pki/` needs `docker compose restart proxy` — nginx reads config and certificates
once, at startup. All three failures look identical and deeply misleading: the code
is right, the test is right, the result is wrong.

**A correct change appearing to have no effect is almost always a stale container.**

**Android fails vaguely on purpose.** "Something went wrong" is a security
decision. There is nothing to infer from the symptom — read
`docs/ANDROID_PLATFORM_REFERENCE.md` before reasoning from behaviour. Three factory
resets were spent learning this.

**When a client never contacts the server, no amount of server-side looking will
help.** Two bugs hid there. The fix was making the agent report its own errors on
its own screen (D79); both were then found in one attempt each.

---

## 8. Open risks

| # | Risk | Severity |
|---|---|---|
| R11 | **No CSRF protection** on console form posts, now that authenticated sessions exist | Should close before wider use |
| R8/R12 | `pki/` holds the CA key and the token vault key unencrypted | Accepted on one trusted host; needs a KMS before that changes |
| R7 | The app trusts proxy-set identity headers and does not refuse to start when exposed directly | Mitigated by placement, not by code |
| R3 | Knox partner application pending — gates KME and KPE | Tracking; the AOSP path must stay functional without it |
| R5 | Three SoC vendors (Qualcomm, MediaTek, Exynos) | Verify firmware-level behaviour on each, never extrapolate |

---

## 9. Suggested order of work

1. **Prove app install on hardware** — largest untested surface, and Chunk 4 exists for it
2. **Prove file placement and the marketplace** — settles R1 in practice and completes F4/F5
3. **Chunk 7 as planned: the Knox layer** — `OemPolicyApplier` is already the seam, with an AOSP no-op behind it. Prefer KSP via `setApplicationRestrictions` over the Knox SDK (D11): it needs no managed Google Play, which matches the sideload constraint
4. **TAK pack** — ATAK policy type: data packages, `.pref` files, plugin sets, cert enrolment. The operator configures the ATAK server on the device, so this is config push with no upstream integration
5. **Close R11**, then R7

---

## 10. Things worth knowing about how this went

Three bugs found on hardware shared one shape: **an over-specific constraint that
looked careful and instead guaranteed failure, reported as something unrelated.**
Pinning the `AndroidKeyStore` provider for signing. Restricting the device key to
one digest. Blocking `acked_state_version` on any error. The instinct to be precise
was right; the precision was wrong, and each failure surfaced somewhere else
entirely. Expect the same temptation in the Knox work.

Two claims were corrected by checking sources rather than reasoning: Headwind's
public agent contains **no Knox code** (it is Pro-gated), and Android's setup wizard
**cannot use a self-signed TLS certificate** for the provisioning download. Both had
been asserted confidently beforehand.

The test suite is genuinely good — 254 tests, hermetic, no database — and it caught
real bugs including two caching faults that would have woken the whole fleet over a
no-op edit. But it found **none** of the six hardware bugs. Both kinds of testing
were necessary; neither substituted for the other.
