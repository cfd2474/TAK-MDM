# Release notes

Newest first. ATLAS — ATAK Tactical Lifecycle & Administration System, by
TAK-Solutions LLC.

## A storage meter on Apps and Content (W208)

Both pages now open with a bar showing how much of ATLAS's storage is in use
against what is left, with **Apps** and **Files** broken out.

It measures the storage ATLAS actually has. Where InfraTAK has reserved a store
for ATLAS, that is the reservation — a 100 GB provision reads as 97.9 GB usable,
the difference being the filesystem's own structures — and the panel says
*"Reserved for ATLAS"*. Where there is no reservation it says so instead, because
then the space is shared with everything else on the box and the used figure
counts all of it.

⚠️ **Apps + Files does not equal what is used, and is not meant to.** The
repository caches and the database share this space; on a reserved store that
remainder is shown as **Other**. A blob that an app and a file both use is stored
once, so it is counted once — and shown as **Shared** when there is any.

## Enrollment tokens no longer ask for a group (W207)

Creating or replacing the enrollment token used to offer *"Place enrolling
devices in these groups"*. It has gone: which group a device lands in is chosen
when you **generate its QR**, and nowhere else.

It was the same decision in two places. Picking a group on the QR form already
resolves to that group's own standing token, so a token scoped to one group with
a QR scoped to another resolved in a way the page gave no clue about.

Nothing is lost — group enrolment works exactly as before, from the QR form.

## Recall a permanent enrollment QR (W204)

The Enroll page now lists the permanent QR codes this console can draw again,
with what each one enrols into and when it was last shown. **Show QR** redraws
the same code — not a new one.

Only permanent codes are listed. A fifteen-minute QR is a different credential
every time, so a list of them would be pictures that had already stopped working.

⚠️ **Every row is a live credential, not a record of something that
happened.** Anyone who photographs one can enrol devices until the token is
retired. **Forget** removes the row and nothing else — the code keeps working;
only *Retire &amp; create new* stops that.

A code whose token has been retired disappears from the list by itself, so what
you see is what still works.

If a QR had Wi-Fi baked in, the password is kept (sealed) so the code can be
reproduced exactly. Generate without Wi-Fi if you would rather nothing was kept.

## The device console's top bar is just the logo (W203)

The **Sync now** button has gone from the header of the ATLAS app on the device.
It was a duplicate: the Sync section carries a full-width **Sync now** of its
own, and that is still there.

The logo fills the bar properly now. It had been held to the middle third to
reserve room for the button on both sides, which kept it small on narrower
screens for a reason that no longer exists.

Needs **agent build 122**.

## The settings search reaches the New policy page (W202)

⚠️ **The search shipped on the wrong page.** It went onto a policy's own
detail page, which is where an existing standalone policy is edited. **New
policy** is a different page — and the one with the most to search: 94 settings
across 42 sections, against 41 across 10.

It is on both now, and on anything else with a section rail.

## Search a policy's settings (W201)

A policy page now opens with a search box. Type two characters or more and it
lists every matching setting with the section it lives in; click one, or press
Enter, and the page opens that section and flashes the field.

It searches the **words you can see** — the setting's name, its help text and its
merge hint — and also the field's own key, so a name you saw in a spec or an
error message finds it too.

Nothing is sent to the server: every section is already on the page, so the
search reads what is in front of you.

## "Also set the lock screen" now does something (W200)

Operator-reported: ticking **Also set the lock screen** on a wallpaper that was
already applied changed nothing — the home screen kept the image, the lock screen
never got it.

⚠️ **Any change to a wallpaper flag on an unchanged image was inert**, not
just this one. The agent skips re-applying a wallpaper it has already applied,
because re-applying flickers visibly — but it recognised "already applied" by the
**image alone**. Ticking a box changes no pixel, so the agent saw nothing to do.
**Stop the user changing it** had the same fault and nobody had hit it yet.

Turning the toggle back **off** now takes the image off the lock screen too — but
only if ATLAS put it there. A lock screen picture the user chose is left alone.

Needs **agent build 121**. Devices pick it up over the agent update channel, and
the wallpaper re-applies once on the first check-in after that, which is the
repair.

## The device name label no longer sits on the app icons (W199)

Operator-reported, immediately after the last release: moving the clock down to
the dock handed the top of the screen to the first row of app icons, and the
device name label landed on top of them.

A band across the top is now held empty for the label. The first row of icons
starts below it.

⚠️ The band is held whether or not a device name is switched on. The label is
drawn by the agent over whatever is on screen, so the launcher cannot ask whether
one is showing — and an empty band is a far cheaper mistake than icons nobody can
read.

Needs **launcher build 13**.

## The kiosk clock moved off the device ID label (W198)

Operator-reported: with a device ID label shown **and** a kiosk clock enabled,
the two drew in the same place and stacked.

The clock now sits along the bottom of the home screen, just above the dock.

⚠️ **The label was not the side that could move.** It is drawn over whatever
is on screen — the launcher, ATAK, anything else — and it is anchored by gravity
rather than by coordinates so that the window manager re-places it on every
rotation. Moving it would have undone that and fixed nothing outside the kiosk.

Needs **launcher build 12**, so the update has to reach the device before the
change shows.

## The ATLAS console is a tile you can see and move (W197)

**Kiosk apps** now opens with **ATLAS Console** already in the list. It cannot be
removed and offers no build to choose; the arrows and **Dock** work on it like
any other tile.

Nothing changes on the device — the console has always been a tile there. What
changes is that the list you read now says so, and that placing it is a drag
rather than something you had to know.

⚠️ **Adding it by hand used to break the policy.** The old advice was to type
it into the list yourself if you wanted to choose its position. Since the last
release every tile is installed with the build it names, and the console names
none — so it came back as a required app reading *"no version chosen"*, pointing
at the app doing the asking. The console is never a required app now: it is the
device's own management agent, and the app catalog was never the thing that
installs it.

⚠️ **A kiosk list holding nothing but the console is not a multi-app kiosk**
and saves nothing. Add at least one app of your own.

## Kiosk apps need a build named (W196)

- ⚠️ **Fixes kiosk mode and multi-app kiosk, which could not engage at all.**
  A kiosk app is required automatically, and since the release that stopped
  ATLAS guessing which build to install, those automatic entries named no build
  — so the app never installed and the device reported having nothing to lock
  to. Multi-app kiosk was worse: the ATLAS launcher failed the same way.
- The single-app kiosk and every multi-app tile now have a **build** select
  beside the app select.
- ⚠️ **An existing kiosk policy needs its build picked once.** Its page says
  which app is missing one. Nothing is chosen for you — that guessing is what
  was removed after an unpinned entry nearly installed the wrong app fleet-wide.
- The ATLAS launcher is the exception and needs nothing: it ships with ATLAS, so
  there is no wrong build to choose.

## Alerts (W195)

- **Admin → General** now has alerts: what to be told about, and who to tell.
- Three kinds of rule, as many as you like of each — the four categories (device
  enrolled, disenrolled, out of compliance, in breach mode), **any number of
  "no check-in for N" thresholds** each with its own unit, and your own rules
  over device fields such as battery level or model.
- A **recipient list**, where pausing somebody is not the same as removing them.
- ⚠️ **One message per sweep**, listing everything raised. A bad policy push
  can put the whole fleet out of compliance at once, and two hundred emails is
  the same outcome as none.
- ⚠️ **You are told once per condition.** A device quiet for three days is
  quiet on every sweep; you hear about it once.
- ⚠️ A device that has **never** checked in is a provisioning problem, not a
  quiet device, and is reported on its own page instead.
- ⚠️ An alert that cannot be sent is **retried**, not dropped. One with nobody
  to send to is discarded and logged, so the first address you add does not
  arrive to a backlog.
- This is the first mail ATLAS has ever sent. It goes through whatever
  **Admin → Email (SMTP)** says — your own server, or InfraTAK's relay.

## Inherit InfraTAK's email relay (W194)

- **Admin → Email (SMTP)** has a new tick: *use InfraTAK's email
  configuration*. With it on, the SMTP fields grey out and show what ATLAS
  would send through instead.
- ⚠️ **Needs InfraTAK's Email Relay to be deployed.** If it has not been,
  the page says so. **Test the relay** opens a connection and reads the
  greeting — it proves a mail server answered, not that mail will arrive.
- ⚠️ Inheriting asks for **no username or password**, by design. The relay
  is Postfix on the host and holds the provider credential itself; ATLAS never
  gets a copy.
- Your own SMTP settings are kept while inheriting, and come straight back when
  you untick the box.
- ⚠️ **ATLAS still does not send mail.** These settings are groundwork for
  notifications; nothing reads them yet, and the page says so.

## Apps can be taken back (W192)

- Each required app now has an **Uninstall if withdrawn** tick. With it on, the
  device removes that app once no policy requires it any more.
- ⚠️ Off by default and set **per app**, because uninstalling destroys the
  app's data. Ticking it uninstalls nothing by itself — the app is still
  required; the tick only says what happens the day it is not.
- Works on tablets already in the field: the device claims an app the first
  time it sees one that is required, ticked and installed, rather than only
  ones it installed after the setting existed.
- The agent and the launcher are never removed this way, and an app that ships
  with the device is reported rather than quietly left behind.

## Breach mode (W193)

- A button on a device's page for a tablet in the wrong hands. It **replaces
  every policy on that device** with a breach policy: the apps in your library
  blocked, named directories emptied, a passcode you chose forced on, a lock
  screen note, and its position reported every minute.
- ⚠️ Deliberately **not** a factory reset — a wiped device stops reporting
  where it is. Disenroll is still there when you want that instead.
- Configured in **Admin → Breach mode**, which is also the only place it can be
  changed: the breach policy is hidden from every list and picker, and both
  assignment routes refuse it, so it cannot be applied to a group by mistake.
- The device page tells **breach sent** apart from **breach applied**, because a
  tablet that never came back must not look like one that obeyed.
- Clearing breach mode restores the device's policies exactly — none were ever
  unassigned — but not its data. A device that has been in someone else's hands
  should still be wiped and reprovisioned.

## Pending deployment, and a date it goes live on (W191)

- A policy or profile can be built complete — content, devices, groups — and
  **held back**, either indefinitely or until a date and time you name. Chosen
  when you create it, and changeable from its page afterwards.
- A scheduled policy deploys itself. ⚠️ It does not depend on the server being
  up at that minute: the schedule is read every time a device's policy is worked
  out, so a server that was down activates on the way back up and a device that
  checks in first still gets it.
- Times are in the console timezone (**Admin → General**) and every schedule is
  confirmed back in **both** that zone and UTC — the only place a timezone set
  wrongly ever shows itself.
- Held and scheduled policies are marked in the Policies list. Live ones are
  not, because almost everything is live.

## Console overhaul (W1–W9)

- **Eight-section console**: Enroll, Manage, Policies, Apps, Content, Reports,
  Admin, Guides — themed to the ATLAS banner, still server-rendered Jinja with no
  build step.
- **Manage**: fleet table with device name, serial, model, reaching policies,
  version and convergence; client-side filter and sort. Devices can be named.
- **Policies**: Device / Templates / Archived tabs, a New Policy modal, and a
  guided **composite policy creator** — one named policy with a category rail
  (password, restrictions, app management, file management wired; ~12 more as
  placeholders). Templates and archive/restore.
- **Apps**: local packages, an ATLAS store flag, and app groups.
- **Content**: managed files with per-policy deployment shown, and editable
  deployment defaults.
- **Reports**: fleet inventory, convergence & compliance, policy deployment,
  command history, app inventory, marketplace selections — each downloadable as
  CSV.
- **Admin**: certificate list with per-cert revoke, EULA / SMTP / AD / SMS /
  geofencing settings, and operator-defined custom device attributes.
- **Guides**: this section.

## Earlier

The server, agent and protocol work (stacked policies, enrolment and mTLS,
desired-state check-in, the APK/XAPK pipeline, the managed-file marketplace, the
Device Owner agent, kiosk, remote diagnostics, multi-identifier device identity,
the single persistent enrollment token) predates this console overhaul and is
recorded in the project history.
