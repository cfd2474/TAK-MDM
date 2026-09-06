# Decision record: should the ATLAS agent become a launcher?

**Status:** open. Raised by W59, deferred by the operator so the enforceable half
of Kiosk could ship first.

**Read `ANDROID_PLATFORM_REFERENCE.md` §7 alongside this.** Everything below rests
on what is recorded there, most of it verified on `SM-X520`.

---

## What is blocked without it

Four of the eight Kiosk sub-topics. They are declared in `KioskSpec` and **refused
at validation**, so an operator can see them and cannot be fooled by them:

| Sub-topic | Why it needs a launcher |
|---|---|
| **Multi app** | Several apps needs a home screen to choose between them. Lock task permits many packages, but something has to draw the grid. |
| **Launcher** | The wallpaper, branding and grid *are* the launcher. |
| **Website kiosk** | Needs a browser shell the agent controls. Pointing a third-party browser at a URL leaves the user its chrome, history and address bar. |
| **Kiosk screensaver** | Needs a foreground surface to draw over after idle. |

Working today without one: single app, background apps, kiosk exit settings,
peripheral settings.

## What the change actually is

Declare `category.HOME` on an activity and the agent becomes a candidate home
app; make it the persistent preferred home and it *is* the launcher.

## Why it is not a small change

> "Adding kiosk to a background agent is two API calls; removing launcher
> behaviour from a launcher is a rewrite."
> — `ANDROID_PLATFORM_REFERENCE.md` §7

The asymmetry is the point:

1. **It changes what the agent is on every device**, not only kiosk ones. A HOME
   activity is offered as a home app to every device that installs the build,
   including the ones that must stay general-purpose.
2. **It collides with the existing HOME takeover.** Kiosk already calls
   `addPersistentPreferredActivity` to point HOME at the *kiosk app*, and that is
   what makes enabling `LOCK_TASK_FEATURE_HOME` safe. If the agent is itself the
   home app, that mechanism has to be redesigned rather than reused.
3. **It puts the escape hatches at risk.** The first and best recovery is
   "remove `kiosk_package` from policy" — released in ~15 s, no physical access.
   That works because the agent is not the launcher; a device whose launcher is a
   crashing ATLAS build has fewer ways home.
4. **A launcher is a product, not a screen.** Grid, ordering, icons, labels,
   wallpaper, idle handling, accessibility, rotation, multi-user. Each is small;
   together they are the bulk of the work, and all of it is UI that only a person
   can verify.

## Options

**A. Stay a background agent.** Kiosk keeps single app, background apps, exit
settings and peripherals. The four sections stay refused. No risk to the recovery
path. Multi-app kiosk stays impossible.

**B. Separate launcher APK.** A second package, installed only where a policy asks
for it, made the preferred home while that policy applies. The agent stays what it
is, and the recovery path is intact because removing the policy removes the
launcher's claim on HOME. Costs a second artifact, its own signing, update channel
and version skew against the agent.

**C. Launcher inside the agent, gated by policy.** One artifact, and the HOME
activity is enabled or disabled at runtime with `setComponentEnabledSetting`, so a
device with no kiosk policy never offers it. Cheaper than B and keeps one update
channel, but a bad build now threatens the launcher on every device rather than
only kiosk ones.

**Not recommended: make the agent unconditionally the launcher.** It maximises the
blast radius of the thing the reference warns is hardest to undo.

## What would need answering first

* Is multi-app kiosk actually wanted in the field, or is single-app enough? This
  decision costs nothing if the answer is single-app.
* If a launcher build crashes on a wall-mounted device, what is the recovery — and
  is it acceptable that it may need physical access?
* Does website kiosk need to be a real browser (cookies, TLS errors, downloads),
  or is a fixed page enough? The first is much more than a WebView.

## Recommendation

**Option B or C, and only once multi-app kiosk is a confirmed field requirement.**
Between them, C is cheaper and B is safer; B's separate artifact is what keeps a
launcher fault away from devices that never asked for one, which is the same
instinct that kept `category.HOME` off the agent in the first place.
