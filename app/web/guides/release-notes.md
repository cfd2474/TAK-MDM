# Release notes

Newest first, one section per release. ATLAS — ATAK Tactical Lifecycle & Administration System, by TAK-Solutions LLC.

## v1.72.1 — 2026-10-06

**ATAK data packages in a policy:** once a package is on the install list, it no longer appears in the **add a data package** dropdown. Removing it puts it back in the list. When every package is already on the policy, the dropdown says so.

A policy that lists the same data package twice is now refused when saved, from the API as well as the page.

## v1.72.0 — 2026-10-06

**Every upload now shows its progress.** Uploading a file, a data package, an app or a web shortcut icon opens a dialog that shows:

- **Progress:** the percentage, the amount sent, the speed, and the time left.
- **Server work:** what the server is doing once the last byte arrives, such as checking a data package.

**Behaviour:**
- **Cancel** stops an upload.
- The dialog won't close on a stray click, and leaving the page asks first, because leaving would abandon the upload.
- If an upload fails, the dialog says why in plain words: too large, dropped by the server or its proxy, or signed out.

Before this, only app uploads showed progress. A large data package on a slow connection showed nothing but the browser's spinner for minutes.

## v1.71.0 — 2026-10-06

**Web shortcut icons can now come from the website itself.** **From the website** is the default: ATLAS fetches the icon the site serves for itself and shows a preview as soon as you enter the address.

- **A site with no icon**, or only a tiny one, gets the **first letter of the shortcut's name** on a coloured background.
- **Custom picture** is still there to use your own image.
- **When you edit a shortcut** with a website icon, it fetches the icon again. One with a custom picture offers to keep it.

## v1.70.0 — 2026-10-06

**New: web shortcuts.** Put a web link on any device as an app icon. Open **Apps → Web shortcuts**, then:

1. Enter a name and a web address.
2. Choose any picture for the icon, and drag and zoom to crop it.
3. Press **Build shortcut**.

ATLAS builds and signs a small app that opens the address in the device's default browser, and adds it to the Library. Add it to a policy or a General apps group to put it on devices. It installs silently, and people can drag it to their home screen. It works on every brand of device, not only Samsung.

Editing a shortcut builds a new version of the same app. Policies keep the version they name: the shortcut's page lists them and marks any on an older version. See **Guides → Put a web link on devices**.

## v1.69.1 — 2026-10-05

**Fixed: the Device Package List Report page now fits the screen.** Package names wrap at their dots, and the version code sits under the version.

Preinstalled apps that were never updated now say **factory image** instead of a misleading date (31 Dec 2008, or 1 Jan 2009 in UTC). That is the fixed date Android gives everything built into the device.

## v1.69.0 — 2026-10-05

**New: Device Package List Report.** A device's page has a new **Device Package List Report** section. Press the button and the device sends a list of every installed package, system apps included. Each row shows:

- the app's name and package;
- its version;
- whether it's a system app, whether it's enabled, and whether ATLAS has hidden it;
- what installed it;
- when it was first installed and last updated.

You can **download it as CSV** (times in UTC) or **open it and print to PDF** (times in the console's time zone). Only the latest report for each device is kept, and pressing the button again refreshes it.

Agent **0.82.0** is included and is needed for the report. A device on an older agent says so on its page.

## v1.68.4 — 2026-10-05

On a Tripltek's device page, **Integrity** now reads **not verifiable**, with the reason and a note that it's exempt from the integrity rule. Before, it showed "problem". Other devices are unchanged, except that a problem no longer has "No details" printed beside it.

## v1.68.3 — 2026-10-05

**Tripltek tablets are exempt from the "Device integrity verified" compliance rule.** Their hardware vouches for itself through Tripltek rather than Google, so ATLAS cannot verify it.

- **What you'll see:** on a Tripltek, the rule shows as *not checked*, with the reason, instead of failing. It never makes the device non-compliant or triggers suspend, lock or wipe.
- **Still enforced:** any other integrity problem on a Tripltek still fails the rule.
- **Other devices:** unchanged, whatever Android version they run.

## v1.68.2 — 2026-10-05

The Tripltek 9 Pro now shows as **Tripltek 9 Pro (TRIPLTEK T93)**, type Tablet, on its device page. Before this, it showed only its model string and type Unknown, because the tablet reports a different model string from the one in Tripltek's product list.

## v1.68.1 — 2026-10-05

Creating an enrollment token, or using **Retire & create new**, no longer shows a QR code straight away. You return to the Enroll page. Set the Wi-Fi, the group and how long the QR should last, then press **Generate enrollment QR**.

## v1.68.0 — 2026-10-05

**New: enrolment QR codes with a use count, a timer, or both.** The Generate form on the Enroll page now has two options:

- **Set expiration timer.** On by default, at 15 minutes. Choose minutes, hours or days, up to 30 days.
- **Set use count.** The number of devices that can enrol with the code. Each enrolment uses one, including re-enrolling the same device.

With both set, the code stops working when the first limit is reached. With neither set, the QR is **permanent**: the page warns you and asks you to confirm before making it. This replaces the old "Make this QR permanent" checkbox.

A use is counted when a device actually enrols. Scanning a code without enrolling does not use it up.

The saved list is now **Live QR codes**. It shows every QR that still works, with the time and uses it has left. **Show QR** draws the same code again. **Revoke** stops a limited code immediately. Permanent codes keep **Forget**, which removes them from the list but leaves the code working until the token is retired. Expired and used-up codes leave the list on their own.

QR codes made before this update keep working until their own 15 minutes run out.

## v1.67.3 — 2026-10-05

**Fixed:** a policy built in the policy editor no longer gains an empty **Kiosk** category when you didn't set up a kiosk. Existing policies that show an empty Kiosk category lose it the next time you save them. A Kiosk category with real settings is unaffected.

## v1.67.2 — 2026-10-04

Agent **0.81.3** replaces 0.81.2. The 0.81.2 build included a Google Play licence check that asked devices to sign in to Google Play and could stop the agent running. **0.81.3 has no such check.**

- **Before updating:** if you unpublished the agent update in Admin, publish 0.81.3 once you've updated.
- **A device that installed 0.81.2 and stopped checking in** may need a factory reset and re-enrolment.

## v1.67.1 — 2026-10-04

Agent **0.81.2**. The agent is now the build produced by Google Play from ATLAS's own signing key, and is being reviewed for a Google Play testing track. It's the same app, with the same signing key as before, so enrolled devices update to it as usual and enrolment QR codes don't change. Its purpose is to give Google Play Protect a recognised, reviewed version of the agent, so it stops blocking QR enrolment.

## v1.67.0 — 2026-10-03

**ATLAS now supports Android 12.** The agent (**0.81.0**) and the ATLAS launcher (**0.13.0**) install and run on Android 12 and 12L, as well as on Android 13 and later. That includes rugged devices such as the Tripltek tablets that stay on Android 12.
- **Verified on Android 12 and 12L test devices:** enrolment, signed policy, required apps, compliance rules and actions.
- **Not yet verified:** first enrolment on a real Android 12 device, using the QR code and the device's own setup screens.
- **Keep in mind:** Android 12 no longer receives security updates from Google, so these devices will fail a "maximum security patch age" compliance rule.

## v1.66.3 — 2026-10-03

The device catalogue now includes **Ulefone** (162 models, including the Armor X10 and Armor X10 Pro, and the Armor Pad tablets) and **Sonim** (13 rugged phones: XP10, XP8, XP Pro and others), from Google's certified-device list. Devices from both brands show their type and name on the device page.

## v1.66.2 — 2026-10-03

The device catalogue now names all four **Tripltek** tablets in the fleet:
- **Tripltek X Pro** (model `TRIPLTEK X PRO`)
- **Tripltek 9 Pro** (`T93`)
- **Tripltek 8 Pro** (`T82 X30`)
- **Tripltek Mini** (`T mini`)

Each shows as a Tablet, with its name on the device page.

## v1.66.1 — 2026-10-03

The device catalogue now includes **Tripltek** rugged tablets. Google's certified-device list currently names one model, the **T mini**, so it shows as a Tablet with its name. Other Tripltek models will be added as their model codes are confirmed.

## v1.66.0 — 2026-10-03

**Compliance: hardware integrity.** A new rule, **Device integrity verified**, under Compliance → Device. Once a day, the agent has the device's secure hardware vouch for how it booted, using Google's key attestation, and ATLAS checks the answer against Google's published roots and revocation list. A device passes when:
- its bootloader is locked;
- it booted verified software, so it isn't rooted or running a modified system;
- the key is in secure hardware.

A failing device is treated like any other rule failure, actions included.

The device page's **Device info** now shows an **Integrity** line: verified, or the problem found, with what the hardware reported and when.

If ATLAS can't reach Google's revocation list, the rule shows "not reported" rather than passing or failing. A device that hasn't attested in 7 days shows "not reported" too.

Agent **0.80.0** does the attestation. It needs no new permissions.

## v1.65.1 — 2026-10-03

In a policy's Compliance **Actions**, apps to suspend are now chosen from a dropdown, one at a time: each app you pick is added to the list below it, and can be removed from there. With none chosen, ATAK is suspended, as before.

## v1.65.0 — 2026-10-03

**Compliance: actions when a device keeps failing its rules.** In a policy's Compliance section, under **Actions**, choose what happens and how long after the device starts failing:
- **Suspend apps:** the apps you tick can't be opened and their notifications are hidden. Tick none to suspend ATAK. Plugins don't need ticking; suspending ATAK stops them.
- **Lock the device:** it's locked again on every check-in, about every 2 minutes, until it passes. That gives the user time to fix the cause, such as turning off USB debugging.
- **Wipe the device:** a factory reset, after a number of days. **Off unless you set it.** If the device passes its rules again before the wipe reaches it, the wipe is cancelled.

Each action has its own delay, in hours (0 = at once) or days for wipe. Everything is lifted automatically on the device's next check-in after it passes again.

On the device page, the Compliance rules panel lists each action with when it starts and whether it's in force.

Agent **0.79.0** carries out suspend and lock.

## v1.64.0 — 2026-10-03

**New policy section: Compliance.** It replaces the "Android Enterprise compliance" placeholder. Set the rules a device must keep meeting:
- minimum Android version;
- maximum security patch age;
- storage encrypted;
- passcode meets the Password policy;
- USB debugging off;
- developer options off;
- installs from unknown sources blocked;
- minimum ATAK version;
- ATLAS plugin running;
- checked in within a number of hours.

Devices are checked on every check-in, and again periodically, which is how "checked in within" catches a device that has gone quiet.
- **On the device page,** a new **Compliance rules** panel shows each rule as pass, fail or not reported. A label at the top shows "rules met" or how many rules are failing, and the same label appears in the fleet list.
- **A device on an older agent** that hasn't reported a fact shows that rule as "not reported". That alone never makes it non-compliant.
- **Separate from "applying its policy":** failing a rule doesn't affect whether a device applied its policy, so it still receives agent updates.
- **Two new alert events** you can attach notifications to: a device starts failing a compliance rule, and a device meets its rules again.

Agent **0.78.0** reports what the rules need: security patch date, USB debugging, developer options, the unknown-sources restriction, whether the passcode meets the policy, and encryption.

Coming next: actions when a device fails (suspend chosen apps, lock, and optionally wipe, each after a grace period), then hardware integrity checks.

## v1.63.2 — 2026-10-02

The policy editor's list of sections is tidier:
- **Removed:** Accounts, App usage management, Configurations and Security. None of them were available yet.
- **Moved to Knox Configurations:** fonts, boot and shutdown animations, and OS update scheduling, which are planned as part of Knox support.

## v1.63.1 — 2026-10-02

The ATLAS plugin **1.2.0** is now also shipped for **ATAK 5.6 and 5.7**. Auto-Load plugins, and the ATLAS plugin itself, update without the "Load plugin" prompt on those ATAK versions too. It's verified on ATAK 5.8; 5.6 and 5.7 use the same mechanism.

## v1.63.0 — 2026-10-02

**No more "Load plugin" prompts for Auto-Load plugins (ATAK 5.8).** The ATLAS plugin **1.2.0** for ATAK 5.8 tells ATAK in advance to load updates of Auto-Load plugins, and of the ATLAS plugin itself. When ATLAS updates one of them while ATAK is open, ATAK loads it without asking the user. Plugins that aren't on the Auto-Load list still prompt, as before.
- **The first update to 1.2.0** on a device may still show the prompt once: the older plugin can't pre-approve it.
- **Unticking Auto-Load** takes full effect after ATAK next restarts. Until then, one more update of that plugin may still load without a prompt.
- **On the device page,** the ATAK plugin section now shows, per Auto-Load plugin, whether its next update will load without a prompt, and the same for the ATLAS plugin's own updates.
- **ATAK 5.6 and 5.7** get this once their 1.2.0 builds are back from TAK.gov.

## v1.62.0 — 2026-10-02

**The device page now shows the cellular carrier.** For a device with a SIM, new rows show:
- **Carrier**, for example "Verizon";
- **Network**: the network it's connected to right now, with a **Roaming** label when that's not its own carrier;
- a line for the second SIM on a dual-SIM device.

A device with no SIM in it says **No active SIM**, and a Wi-Fi-only tablet still says it has no cellular radio.

Agent **0.77.3** also looks for the **phone number** in more places: the carrier's records and the network registration, not only the SIM. Some devices that showed no number before may now show one, though some carriers never make it available.

## v1.61.3 — 2026-10-02

The device page now shows a device's marketing name with its model number, for example **Galaxy XCover6 Pro (SM-G736U1)**, in the line under the device name and in the Model row. A model the device catalogue doesn't know is shown as before.

## v1.61.2 — 2026-10-02

Agent **0.77.2**: two log refinements found while testing 0.77.1 on a tablet. Every "sync failed" line, and the enrollment ones, now names the error. The "network validated" line reports how much earlier the agent reconnected. Tested: with 0.77.1, a tablet back from a 13-minute Wi-Fi outage synced 3.8 seconds after Wi-Fi came on, instead of about 3 minutes later.

## v1.61.1 — 2026-10-02

Agent **0.77.1** (sync improvements):
- **Faster recovery after an outage.** When a device's network comes back, it now checks in within seconds, instead of waiting up to five minutes for its retry timer.
- **Clearer logs.** A failed sync now says why in the agent log, for example `UnknownHostException` when the device is offline, as opposed to a server error. Before, the line just said "sync failed".
- **Less load on a struggling server.** If the server's change notification fails instantly, the agent now backs off instead of checking in again straight away.

## v1.61.0 — 2026-10-02

**App groups now come in two kinds: General apps and ATAK plugins.** Apps → App groups has a section for each, and each group's picker offers only its own kind. ATAK itself can't be part of any group: you choose it under ATAK Core in the policy.

In the policy editor, general apps groups are offered under **Required apps**, as before. ATAK plugins groups are offered under **ATAK Core and Plugins**, where they fill in the plugin rows.

Existing groups were sorted automatically: a group made up only of plugins became an ATAK plugins group, and every other group became a general apps group. Nothing was removed. If an existing group contains something that no longer belongs (ATAK, or a plugin in a general apps group), the group shows a warning naming it, and the policy editor won't add it. Click **Save members** on that group to remove it.

## v1.60.5 — 2026-10-02

On the Apps page, opening the **Local apps** or **App groups** tab now briefly reloads the page. An app you just imported from another tab (TPC, TAKWERX, Google Play or a 3rd-party repo) therefore shows up in the library and in the group lists straight away, without a manual refresh.

## v1.60.4 — 2026-10-02

The **TPC Plugins** tab now offers ATAK versions **5.6.0 and higher** only, matching ATLAS's minimum supported ATAK. Older versions are no longer offered or queried.

## v1.60.3 — 2026-10-02

Wording only: the Google Play "no APK" message now starts with a capital letter and says **Try selecting another device under "Download as"**.

## v1.60.2 — 2026-10-02

When Google Play returns nothing for a download, the message now names the device you downloaded as and says first that the app may not be compatible with that device, suggesting you try another device under **Download as**. It still mentions paid and region-locked apps as other possible causes.

## v1.60.1 — 2026-10-02

Google Play now uses only the device you choose under **Download as** on Apps → Google Play, for searches as well as downloads. Search results name that device, for example "as Galaxy Tab S10 FE (SM-X520)". If nothing is chosen, **Flagship Smartphone** is used. The device setting under **Admin → Google Play** has been removed, both when linking an account and afterwards.

## v1.60.0 — 2026-10-02

**Download Google Play apps as your own devices.** On **Apps → Google Play**, choose **Download as** with three dropdowns, **Type**, **Manufacturer** and **Model**, each narrowing the next. Google Play then serves the exact build that device would get: the right processor type, screen density and Android version.

- **Your devices:** each device reports its Google Play profile once it updates to agent 0.77.0. Its model then appears in the list, named the way you'd recognise it, for example "Galaxy Tab S10 FE (SM-X520)".
- **Flagship Smartphone** (a Samsung Galaxy S25 Ultra) is always available, and is the default. Until a device has reported its profile, a notice explains that this generic model is in place.
- **Region:** downloads carry no location. What's available still depends on the server's location and the Google account's country, as before.

The choice applies to that one download. The account's stored device under Admin → Google Play is now used only as a fallback.

Needs **agent 0.77.0**.

## v1.59.0 — 2026-10-02

ATLAS now includes a reference catalogue of about 6,800 phones and tablets from the ten largest Android brands: Samsung, Google, Motorola, Xiaomi, vivo, OPPO, HONOR, realme, Infinix and TECNO. Device **Type** uses it first, so devices from all ten brands are recognised by their exact model code: for example an OPPO Pad (`OPD2101`), a realme Pad (`RMP2102`) or a moto pad (`XT2575-1`), not only Samsung models. A model the catalogue doesn't list still falls back to the existing rules, and otherwise shows **Unknown**.

The catalogue is built from Google Play's published list of certified devices.

## v1.58.0 — 2026-10-02

Devices now have a **Type**: **Smartphone** or **Tablet**, worked out from the device model.

- **Where it shows:** a Type column in the device list, right after Model, and on each device's page.
- **Searching:** typing "tablet" or "smartphone" in the device list's filter shows just those devices.
- **Unknown models:** Samsung models are recognised by their model number. Other brands are recognised where the model name says so, such as "Pixel Tablet". Anything else shows as **Unknown**, rather than a guess.

## v1.57.5 — 2026-10-02

ATLAS now ships a single agent build. The ATLAS app that devices download is unchanged (0.76.9): it uses Samsung Knox features where available and behaves as a standard Android agent on other devices. The duplicate second build is no longer included.

## v1.57.4 — 2026-10-01

The **Apps** page now shows a warning at the top when the app library has no ATAK: *"No ATAK installation detected. Upload a version of ATAK to the app library. ATLAS requires ATAK 5.6 or higher."* If the library has ATAK builds but all are older than 5.6, it warns that no supported ATAK was found, and names the newest version there.

## v1.57.3 — 2026-10-01

After an update, the console's pages now always use the new version's scripts and styles. Until now a browser could keep using a cached older version after an update, so console changes, such as v1.57.2's new plugin compatibility message, didn't appear until the browser cache expired.

## v1.57.2 — 2026-10-01

The ATAK plugin compatibility message no longer says a working plugin will fail. ATAK loads a plugin built for an older ATAK, such as a 5.7 plugin on ATAK 5.8, so that case is now a quiet note on the policy editor and the device page, suggesting a matching build if the vendor has one. A plugin built for a **newer** ATAK still gets a warning, now saying plainly that ATAK will refuse to load it. As before, you can still assign it.

## v1.57.1 — 2026-10-01

After an update, devices now pick up the apps that ship with ATLAS straight away. Until now, a device could keep an older build, such as the ATLAS plugin 1.0.0 after v1.57.0, until something unrelated changed its policy. After each update or restart, every device now recalculates what it should have at its next check-in.

## v1.57.0 — 2026-10-01

**Auto-Load Plugin.** In a policy, **ATAK Config → Plugin behavior** now lists every ATAK plugin in the app library with an **Auto-Load Plugin** checkbox.

- **Loading:** the ATLAS plugin loads each ticked plugin inside ATAK within about 30 seconds of it being installed and not loaded, with no restart and no prompt. That includes a plugin that was never switched on, and one ATAK switched off after an update. ATAK still checks each plugin's version and signature, so a plugin it won't accept is shown as **refused** on the device page with the reason, and isn't retried until it's reinstalled or ATAK restarts.
- **Unticking:** stops the forcing, but doesn't unload or switch off the plugin.
- **After an update made while ATAK is open:** ATAK may still ask "Load plugin?". Either answer is fine; the plugin stays loaded.
- **Device page:** the **ATLAS plugin** section has a new **Auto-Load** table with each ticked plugin's result.

This release includes the ATLAS plugin **1.1.0** for ATAK 5.6, 5.7 and 5.8, signed by the TAK Product Center, which this feature needs.

## v1.56.1 — 2026-10-01

Fixes the **ATLAS plugin** section saying "not running" for a plugin that was running. The ATLAS app sometimes misjudged how old the plugin's last report was, by up to about 15 minutes. It now reads the time from the report itself.

Needs **agent 0.76.9**.

## v1.56.0 — 2026-09-30

A device's page now has an **ATLAS plugin** section showing what the ATLAS plugin inside ATAK last reported:

- whether it's **running**, **stopped**, or **not running** (no report in the last 15 minutes, which usually means ATAK is closed);
- the plugin and ATAK versions;
- every ATAK plugin on the device and whether it loaded, with the reason when it didn't;
- each TAK server set up in ATAK: connected or not, any connection error, the server's version, and when the device's certificate and truststore expire.

The section appears on devices that ATLAS installs the plugin on, and on any device that has reported. A device with an older ATLAS app shows "Not reported" until it updates.

Needs **agent 0.76.8**.

## v1.55.2 — 2026-09-30

The ATLAS ATAK plugin now comes back on after it's updated. If a plugin update arrives while ATAK is open, ATAK switches the plugin off and asks whether to load it. Until now, tapping **Cancel** or ignoring that question left it off for good. Now the ATLAS app turns it back on at its next sync, and the plugin loads the next time ATAK starts.

Needs **agent 0.76.7**.

## v1.55.1 — 2026-09-30

The ATLAS ATAK plugin now includes the build for **ATAK 5.7**, signed by the TAK Product Center. Devices whose policy installs ATAK 5.7 now get it. Until now they got no plugin, because only 5.6 and 5.8 builds were included. ATLAS supports ATAK 5.6 and newer; a device on an older ATAK gets no plugin.

## v1.55.0 — 2026-09-30

**The ATLAS ATAK plugin now ships with ATLAS.** Any device whose policy installs ATAK also gets the plugin, using the build made for that ATAK version. There's nothing to choose or configure. This release includes the builds for ATAK **5.6** and **5.8**, both signed by the TAK Product Center; the 5.5 and 5.7 builds will follow. If a device's ATAK has no build of its own, it gets the build for the nearest older ATAK. ATAK loads those, but never one built for a newer ATAK, so a device with no fitting build gets no plugin rather than one that won't load.

- ATLAS also sends ATAK the setting that keeps the plugin switched on. ATAK turns a plugin off if it's updated while ATAK is open, and the setting turns it back on the next time ATAK starts.
- Like the ATLAS app and launcher, the plugin is not offered in any policy, app group or store, and the build in use for each ATAK version can't be deleted from the library.
- The plugin's development build is refused if uploaded.
- An ATAK settings policy now finds ATAK when ATAK is set under **ATAK Core**. Previously, with more than one ATAK build in the library, such a policy couldn't tell which build its settings were for.

## v1.54.14 — 2026-09-30

During setup, the ATLAS app now requires **every** permission before it can finish, including usage access and the kiosk power menu, which it used to let you skip with **Continue without the rest**. That option is gone. **Continue anyway** with the bypass code from the admin console is still there, for a device where a permission can't be granted. Its message now says the device will report as degraded only when a truly required permission is missing. After setup, a missing usage-access or power-menu permission still counts as a warning, not an error, so it never blocks agent updates.

Needs **agent 0.76.6**.

## v1.54.13 — 2026-09-30

On **New policy**, the settings search now sits below the policy's name and **Deployment** choices, just above the list of sections it searches. Typing a search no longer counts as an unsaved change. A policy's own page keeps the search under its title.

## v1.54.12 — 2026-09-30

**Save deployment** on a policy no longer reloads the page, so unsaved changes in the policy editor are no longer lost.

- If nothing changed, for example the policy is already live and **Live** is still selected, a message says so and nothing is sent.
- If the policy has unsaved changes, you're asked first: **Save policy first**, **Save deployment only** (your unsaved edits stay on the page), or **Cancel**.
- Otherwise the deployment is saved in place. The confirmation appears in a dialog, and the status label next to the policy's name updates without a reload.

## v1.54.11 — 2026-09-30

After **Disenroll and factory reset** is sent, a notice at the **top** of the device page now confirms it: *"Factory reset sent to …"*. The page then returns to the device list after **5 seconds**, not 3. In v1.54.10 the notice appeared only near the bottom of the page, out of view, so the page seemed to jump straight to the device list.

## v1.54.10 — 2026-09-30

After **Disenroll and factory reset** is sent, the device page shows the confirmation for 3 seconds, then returns to the device list by itself. There's also a link to go now. It happens only right after sending: opening a device later that's still waiting for its reset doesn't redirect.

## v1.54.9 — 2026-09-30

- **App configurations can be edited.** Each saved configuration in a policy now has an **Edit** button, which opens it with every value filled in. **Save** updates that configuration in place. Before, the only way to change one value was to remove the configuration and enter every value again. If the app's current build no longer offers a key that was saved earlier, that value is kept as it is and the dialog says so, rather than being dropped.
- **New guide: Network requirements.** The ports ATLAS needs, and the timeout that any gateway, load balancer or firewall in front of port 8449 must allow: at least 135 seconds, 180 recommended. It also lists the sites ATLAS fetches from, for networks that inspect HTTPS.

## v1.54.8 — 2026-09-30

Tablets now keep their connection to ATLAS alive while they wait for changes. A tablet holds a connection open for up to two minutes so ATLAS can tell it the moment something changes. Some networks close a connection that stays silent, and on one deployment every wait was cut off after about 40 seconds, so its tablets re-synced every 42 seconds instead of only when something changed. The tablet now sends a small keepalive every 25 seconds, which such networks leave alone.

Needs **agent 0.76.5**.

## v1.54.7 — 2026-09-30

Fixes a password policy re-setting the tablet's lock-screen PIN on every sync, about every 40 seconds, which woke the screen each time. The PIN is now set only when the policy's PIN changes, or when the user changes it on the tablet, in which case it is set back. The same fix applies to a trusted-area geofence, which suspends the PIN once on arrival and restores it once on leaving.

Needs **agent 0.76.4**.

## v1.54.6 — 2026-09-29

Fixes the ATLAS app on the tablet starting its own update twice at the same moment. When Google Play Protect paused the update for a check, the second copy caused a second prompt, and a failed install appeared in the record even though the update had succeeded. The app now runs one sync at a time and never starts an update of itself while one is still waiting. This does not remove Play Protect's check on the update itself; that is still being investigated.

Needs **agent 0.76.3**. Tablets take it with the agent update, which may show the Play Protect prompt one more time.

## v1.54.5 — 2026-09-29

A policy can now be renamed from its own page, with the **Name** field and **Rename** button under the title. This works for the policies **New policy** creates and for standalone policies and templates.

- Renaming a policy renames each of its sections with it.
- A blank name, a name another policy already uses, or a name too long once a section's suffix is added is refused with a message.
- Devices the policy reaches show the new name on their pages.
- **Breach mode** cannot be renamed, and no policy can be given that name, because ATLAS finds the breach policy by it.

## v1.54.4 — 2026-09-29

In a policy's **Required apps**, an app already picked in one row is no longer offered in the dropdown of another. Picking, changing or removing a row, or adding an app group, updates every row's list straight away.

## v1.54.3 — 2026-09-29

**ATLAS MDM** and the **ATLAS launcher** can no longer be deleted from the app library. Their rows on **Apps → Local apps** say *Ships with ATLAS* instead of offering **Delete**, and the API refuses too. The newest build of each also cannot be deleted on its own, because it is the one provisioning hands out and the kiosk runs. Older builds, which pile up with each release, can still be removed through the API.

## v1.54.2 — 2026-09-29

The storage bar on **Apps** and **Content** no longer says *"Reserved for ATLAS — nothing else on this box can use it, and ATLAS cannot exceed it."* That was not true on any current deployment. Since InfraTAK stopped using a reserved storage image, ATLAS keeps its files in an ordinary folder on the host disk, in both fixed and dynamic mode. A fixed size is what InfraTAK plans the box around, but nothing holds that space or stops ATLAS going past it. The bar now always says it shares the disk with the rest of the box, and no longer shows an **Other** figure, which on a shared disk was the rest of the box's usage.

## v1.54.1 — 2026-09-29

Release notes are now organised by version, one section per release, instead of by change. Every release since v0.1.0 has an entry.

## v1.54.0 — 2026-09-29

The plugin catalogs on **Apps → TPC Plugins** and **Apps → TAKWERX Plugins** now say what your library already holds for each plugin:

- **update · you have X** when only older builds are in the library.
- **newer in library · Y** when the library holds a higher build.
- **imported** for the exact build, as before.
- A held build made for a different ATAK version is named.

This is information only. Nothing is imported or repointed on your behalf.

## v1.53.1 — 2026-09-29

The **TAKWERX Plugins** table no longer squeezes the Import column into one letter per line. The author is now shown beside the plugin name.

## v1.53.0 — 2026-09-29

New **Apps → TAKWERX Plugins** tab beside TPC: the TAKWERX plugin catalog, chosen per ATAK version. Every plugin is listed, and third-party plugins are labelled with their author.

Imports are checked against the SHA-256 the catalog publishes. Downloads are https only, and a redirect that would land inside your own network is refused.

## v1.52.13 — 2026-09-29

- Samsung Knox is marked **Coming Soon** while Samsung licensing is delayed: the Knox settings tab (with a placeholder banner; a key you enter is still saved), the Integrations Knox panel, the **Knox Configurations** category in the policy creator, every Knox-only field, and the OEM licence row on the device page.
- On the tablet, the build number no longer ends in "-knox", the OEM licence row is hidden, and the app no longer tells anyone to enter a key.

Needs **agent 0.76.2**.

## v1.52.12 — 2026-09-29

- A device's page has a new **Groups** section, directly above **Policies reaching this device**: every group the device is in, linked to the group, with its description — or "Not in any group".
- A group can now be renamed on its own page. The name cannot be blank, and a name another group already uses is refused with a message. Renaming is safe: devices and pages refer to groups by id, not by name.

## v1.52.11 — 2026-09-29

While an APK is uploading, clicking outside the upload dialog or pressing Escape no longer cancels it. Before, clicking the page underneath could move you to another page and end the upload without telling you. **Cancel upload** is now the only way to stop an upload, and leaving the page asks you first.

## v1.52.10 — 2026-09-29

ATLAS's own agent and launcher can no longer be chosen in any policy, app group or storefront. They are hidden from every picker, and a save that names them is refused.

The agent is installed at provisioning, and the launcher is applied automatically with any multi-app kiosk, so neither needs choosing. A policy that blocked or restricted the agent could cut the device off from ATLAS. Both stay in the library. The one exception is the **ATLAS Console** tile in a multi-app kiosk, which places the agent on the grid.

## v1.52.9 — 2026-09-28

The app-group picker is now in two parts. An **Add an app…** dropdown with search lists only the apps not yet in the group. Picking one moves it into a list below, and the dropdown stays open so you can add several in a row. Each app in the list has its own remove button. An app with no label is still shown by its package name.

## v1.52.8 — 2026-09-28

Apps are added to an app group from a searchable dropdown instead of a long list of package-name checkboxes, on both the new-group form and each group's page. Apps are listed by name with the package name underneath, sorted alphabetically, and the search matches either. An app with no label is shown by its package name.

## v1.52.7 — 2026-09-28

**Policies reaching this device** lists each policy profile once. It used to show one near-identical row for every section of the profile, and twice over when the profile reached the device two ways. Each profile is now one row, named as the profile, linked to its editor, and listing every route it arrives by. Standalone policies are unchanged.

## v1.52.6 — 2026-09-28

The admin page no longer says "ATLAS does not send mail yet", which had been untrue since alerts arrived in v1.42.0. It now says what this deployment will actually do: send alerts through the mail server you selected, or, if none is selected, discard them. Where InfraTAK's relay is available, it points you to the checkbox that uses it.

## v1.52.5 — 2026-09-24

ATLAS now starts again by itself after the host reboots. Before, its containers stayed stopped after a reboot while every other add-on came back, and the console showed a 502 error the next time you looked.

## v1.52.4 — 2026-09-23

Fixes QR provisioning failing during the agent download. Stored files were sent in tiny pieces, so the 21 MB agent took about four minutes to download and Android's setup wizard gave up. Files are now sent in 1 MiB blocks. The fix also speeds up every app install to managed devices, and every managed-file download.

## v1.52.3 — 2026-09-20

You can now change the Google Play device profile in **Admin** without relinking the account. **Apps → Google Play** can also use a different profile for a single import, and the build records which profile it was fetched with. The profile decides which build Play serves.

## v1.52.2 — 2026-09-19

The policy count on the fleet page now matches the Policies list. It used to count every section of a profile separately, and it counted the hidden breach profile as soon as **Admin → Breach mode** had been opened.

## v1.52.1 — 2026-09-19

Loading the bundled agent can no longer move the fleet back to an older agent build. On the first v1.52.0 update, a library that already held the Knox build was moved down to the plain build. Now a release only moves the fleet forward.

## v1.52.0 — 2026-09-19

The Knox-capable agent (0.76.1-knox) is now the agent the fleet runs. Installing this release moves devices onto it through the agent update. It is the same app as before, not a second one.

The agent now records Samsung's answer to a licence activation, including the reason for a refusal. It no longer retries activation on every check-in: an unanswered attempt waits 20 minutes before it is tried again.

## v1.51.0 — 2026-09-18

ATLAS now writes out its device-certificate trust bundle (the root plus every intermediate that has ever signed) as a file that InfraTAK can read. This matters after a certificate-authority renewal: without it, InfraTAK could not see retired intermediates, and devices whose certificates they had signed would have been refused at the edge. Existing deployments write the file the first time they restart on this release.

## v1.50.0 — 2026-09-18

Groundwork for Samsung Knox licensing:

- A new **Samsung Knox** group in Admin holds the licence key. The key is stored sealed and shown only as "set".
- The key reaches each device, and the device reports its licence status back. That status is shown on the device page and in the ATLAS app on the tablet. A non-Samsung device reports "not applicable".
- A licence problem never counts as a failed policy, so it cannot stop a device receiving agent updates.

Needs **agent 0.75.0**.

## v1.49.0 — 2026-09-18

`TAKMDM_ADMIN_GROUP` now accepts a comma-separated list of groups, and membership of any one of them is enough to administer ATLAS. This lets one server run an ATLAS per agency, each with its own admin group, while a global administrator in a shared group can reach them all. A single group name works exactly as before. When somebody is turned away, the refusal lists the groups that would have let them in.

## v1.48.1 — 2026-09-17

The agency name set in v1.48.0 now actually reaches ATLAS. Before this release it was saved in the settings file but never passed to the running application, so the footer did not show it.

## v1.48.0 — 2026-09-17

The footer can now show the name of the agency a deployment belongs to, before the version. When one server runs several ATLAS deployments, this tells you which fleet's console you are in before you push a policy or wipe a tablet. It is set with `TAKMDM_AGENCY_NAME`. If it is left empty, the footer is unchanged.

## v1.47.3 — 2026-09-17

Internal: the public release repository gains a readme. No change to what ATLAS does.

## v1.47.2 — 2026-09-16

Internal: release-publishing tooling. No change to what ATLAS does.

## v1.47.1 — 2026-09-16

The ATLAS container image is now built only from what the application needs. It used to include copies of uploaded APKs, repository caches and internal documents. On the reference box the image went from 4.56 GB to 362 MB. Docker stores images on the host's root disk, outside ATLAS's storage reservation, so every upload had been making it grow there.

## v1.47.0 — 2026-09-16

Both **Apps** and **Content** now open with a bar showing how much of ATLAS's storage is in use against what is left, with **Apps** and **Files** broken out.

It measures the storage ATLAS actually has. Where InfraTAK has reserved space for ATLAS, the bar shows that reservation — a 100 GB reservation reads as 97.9 GB usable, because the filesystem takes some for itself — and the panel says *"Reserved for ATLAS"*. Where there is no reservation, the panel says so: the space is shared with everything else on the box, and the used figure counts all of it.

⚠️ **Apps + Files does not add up to the used figure, and is not meant to.** The repository caches and the database share this space. On a reserved store, that remainder is shown as **Other**. A file that an app and a managed file both use is stored once and counted once, and is shown as **Shared** when there is any.

## v1.46.1 — 2026-09-16

Creating or replacing the enrollment token no longer asks *"Place enrolling devices in these groups"*. The group a device joins is chosen when you **generate its QR**, and nowhere else. It had been the same choice in two places, and a token set to one group with a QR set to another behaved in a way the page gave no hint of. Enrolling into a group works exactly as before, from the QR form.

## v1.46.0 — 2026-09-16

The Enroll page now lists the permanent QR codes this console can draw again, with what each one enrols into and when it was last shown. **Show QR** redraws the same code — not a new one. Only permanent codes are listed: a fifteen-minute QR is a new credential each time.

⚠️ **Every row is a working credential, not a record of something that happened.** Anyone who photographs one can enrol devices until the token is retired. **Forget** removes the row and nothing else — the code keeps working; only **Retire & create new** stops it. A code whose token has been retired drops off the list by itself.

If a QR had Wi-Fi settings, the Wi-Fi password is kept (sealed) so the code can be reproduced exactly. Generate without Wi-Fi if you would rather nothing was kept.

## v1.45.2 — 2026-09-16

The **Sync now** button has gone from the top bar of the ATLAS app on the tablet. It was a duplicate: the Sync section has its own full-width **Sync now**, and that is still there. The logo now fills the top bar properly on narrower screens.

Needs **agent build 122**.

## v1.45.1 — 2026-09-16

The settings search from v1.45.0 is now on the **New policy** page, which it had missed. That page has the most to search: 94 settings across 42 sections. The search is now on every page with a section rail.

## v1.45.0 — 2026-09-16

A policy page now opens with a search box. Type two or more characters to list every matching setting with its section. Click one, or press Enter, to open that section with the field highlighted.

It searches the words you can see — the setting's name, its help text and its merge hint — and also the field's own key, so a name from a spec or an error message finds it too. Nothing is sent to the server.

## v1.44.2 — 2026-09-16

Ticking **Also set the lock screen** on a wallpaper that was already applied now works. Before, it changed nothing. The agent skips re-applying a wallpaper it has already applied, but it judged "already applied" by the image alone, so changing a checkbox looked like no change. **Stop the user changing it** had the same fault.

Turning **Also set the lock screen** off now removes the image from the lock screen too — but only if ATLAS put it there. A lock-screen picture the user chose is left alone.

Needs **agent build 121**. Each device re-applies its wallpaper once, on its first check-in after the agent update, and that fixes it.

## v1.44.1 — 2026-09-16

The device name label no longer sits on top of the first row of app icons in the kiosk home screen. A band across the top is now kept clear for the label. ⚠️ The band is kept clear even when no device name is shown, because the launcher cannot tell whether one is showing.

Needs **launcher build 13**.

## v1.44.0 — 2026-09-16

The kiosk clock now sits at the bottom of the home screen, just above the dock. With a device ID label shown and a kiosk clock turned on, the two had been drawn in the same place, one on top of the other. The label could not move instead: it is drawn over every app, not just the launcher.

Needs **launcher build 12**.

## v1.43.0 — 2026-09-16

**Kiosk apps** now starts with **ATLAS Console** already in the list. You cannot remove it and there is no build to choose, but the arrows and **Dock** work on it like any other tile. Nothing changes on the tablet, where the console has always been a tile. The list now shows it, and you can place it where you want.

⚠️ **Adding the console by hand used to break the policy**: it came back as a required app reading *"no version chosen"*. The console is never treated as a required app now. ⚠️ A kiosk list holding only the console is not a multi-app kiosk and will not save. Add at least one app of your own.

## v1.42.2 — 2026-09-16

Internal: release records only. No change to what ATLAS does.

## v1.42.1 — 2026-09-16

- ⚠️ **Fixes kiosk mode and multi-app kiosk, which could not start at all.** A kiosk app is made a required app automatically, but those automatic entries named no build, so the app never installed and the device reported it had nothing to lock to.
- The single-app kiosk and every multi-app tile now have a **build** select beside the app.
- ⚠️ **An existing kiosk policy needs its build picked once.** Its page says which app is missing one. ATLAS does not pick a build for you.
- The ATLAS launcher is the exception and needs no build picked. It ships with ATLAS, so there is no wrong build to choose.

## v1.42.0 — 2026-09-16

- **Admin → General** now has alerts: what to be told about, and who to tell.
- There are three kinds of rule, and you can add as many of each as you like. The four categories are device enrolled, disenrolled, out of compliance, and in breach mode. You can also add any number of "no check-in for N" thresholds, each with its own unit, and your own rules on device fields such as battery level or model.
- A **recipient list**, where pausing somebody is not the same as removing them.
- ⚠️ **One message per sweep**, listing everything raised. A bad policy push can put the whole fleet out of compliance at once.
- ⚠️ **You are told once per condition.** A device that has been quiet for three days is quiet on every sweep, but you hear about it only once.
- ⚠️ A device that has **never** checked in is a provisioning problem, not a quiet device, and is reported on its own page instead.
- ⚠️ An alert that cannot be sent is **retried**, not dropped. An alert with nobody to send it to is discarded and logged.
- This is the first mail ATLAS has ever sent. It goes through the server set in **Admin → Email (SMTP)** — your own, or InfraTAK's relay.

## v1.41.0 — 2026-09-16

- **Admin → Email (SMTP)** has a new tick: *use InfraTAK's email configuration*. With it on, the SMTP fields are greyed out and show what ATLAS would send through instead.
- ⚠️ **Needs InfraTAK's Email Relay to be deployed.** If it has not been, the page says so. **Test the relay** only checks that a mail server answers, not that mail will arrive.
- ⚠️ Using the relay needs **no username or password**, by design. The relay holds the provider password itself, and ATLAS never gets a copy.
- Your own SMTP settings are kept while the tick is on, and come back when you untick it.
- ATLAS did not send mail yet in this release. These settings were groundwork for alerts, which arrived in v1.42.0.

## v1.40.1 — 2026-09-15

Maps show tiles again instead of OpenStreetMap's "blocked" tile. ATLAS now sends map-tile requests the way OpenStreetMap's tile policy requires, using its current tile address. Pages still share only the console's address with a tile provider, never the page path. OpenStreetMap's tiles are for light use: a fleet console should point at its own tile server or a commercial provider.

## v1.40.0 — 2026-09-15

- Each required app now has an **Uninstall if withdrawn** tick. With it on, the device removes that app once no policy requires it any more.
- ⚠️ Off by default and set **per app**, because uninstalling destroys the app's data. Ticking it uninstalls nothing by itself — the app is still required; the tick only says what happens once it is not.
- This works on tablets already in the field, including for apps that were installed before the tick existed.
- The agent and the launcher are never removed this way, and an app that came with the device is reported rather than quietly left behind.

Needs **agent build 120**.

## v1.39.0 — 2026-09-15

- **Breach mode** is a new button on a device's page, for a tablet in the wrong hands. It **replaces every policy on that device** with a breach policy that blocks the apps in your library, empties the directories you name, forces on a passcode you chose, shows a lock-screen note, and reports the device's position every minute.
- ⚠️ This is deliberately **not** a factory reset, because a wiped device stops reporting where it is. **Disenroll** is still there when you want that instead.
- The breach policy is set up in **Admin → Breach mode**, and can only be changed there. It is hidden from every list and picker and cannot be assigned, so it cannot be applied to a group by mistake.
- The device page shows **breach sent** separately from **breach applied**, so a tablet that never came back does not look like one that obeyed.
- Clearing breach mode restores the device's policies exactly, but not its data. A device that has been in someone else's hands should still be wiped and reprovisioned.

Needs **agent build 119**.

## v1.38.0 — 2026-09-15

- A policy or profile can be built complete — content, devices, groups — and **held back**, either indefinitely or until a date and time you name. You choose this when you create it, and can change it from its page later.
- A scheduled policy goes live by itself. ⚠️ It does not depend on the server being up at that minute: a server that was down turns it on when it comes back, and a device that checks in first still gets it.
- Times use the console timezone (**Admin → General**), and every schedule is shown back to you in **both** that zone and UTC.
- Held and scheduled policies are marked in the Policies list.

## v1.37.3 — 2026-09-15

Internal: security-audit records only. No change to what ATLAS does.

## v1.37.2 — 2026-09-15

Fixes the phone menu from v1.37.0, which closed again on the same tap that opened it.

## v1.37.1 — 2026-09-15

Fixes the phone menu from v1.37.0: the full navigation banner was still being shown beside the **Menu** button.

## v1.37.0 — 2026-09-15

On a phone or other narrow or touch-only screen, the console's navigation is now a **Menu** button that opens a grid of tiles. It replaces the full banner, which used to take up most of the screen. Desktops and touch laptops with a mouse keep the banner.

## v1.36.0 — 2026-09-15

ATLAS now checks two things on every console request:

- The request must carry a secret that only InfraTAK's proxy adds after sign-in, so a process on the host cannot fake an administrator.
- The signed-in user must be in the admin group, which the InfraTAK module sets to Authentik's own **authentik Admins** — a group that always includes whoever installed ATLAS. Before, anyone Authentik let through was treated as an administrator.

Both checks are switched on by the InfraTAK module. The emergency way back in (break-glass) is to clear `TAKMDM_PROXY_AUTH_SECRET` from `.env` and run `docker compose up -d api`.

## v1.35.1 — 2026-09-15

Internal: security-audit records only. No change to what ATLAS does.

## v1.35.0 — 2026-09-15

When the agent or launcher shipped in a release cannot be loaded, because it is signed with a different key from the one already in your library, **Admin → Agent updates** now says so and explains how to fix it. Before, the refusal appeared only in the container logs, while the console went on showing the old agent as current.

## v1.34.0 — 2026-09-15

The agent and launcher are now signed with a dedicated ATLAS signing key. Before, they shared a key with an unrelated app published on Google Play. Needs **agent 0.72.0** and **launcher 0.11.0**.

⚠️ Android will not update an app to a build signed with a different key, so a deployment that already holds builds signed with the old key refuses the new ones (see v1.35.0).

## v1.33.1 — 2026-09-15

The InfraTAK module page now handles the offline root in one banner: save the recovery file, download it, upload it back, and the root key is removed from the server. A new deployment also creates its intermediate certificate automatically. After that, the only thing you need to do with the certificate authority is keep the recovery file and upload it about twice a decade.

## v1.33.0 — 2026-09-15

Adds the commands that turn the certificate authority's root key into a recovery file you keep: export it, check that a saved copy still matches, and delete it from the server once something else can sign. Checking a saved copy never writes it to the server's disk. Deleting a second time does no harm.

## v1.32.0 — 2026-09-15

- Device certificates now last 90 days instead of 825. Devices renew them on their own, so a certificate copied off a tablet stops working much sooner.
- Only the ATLAS launcher can open the ATLAS app screens behind its kiosk tiles. Other apps can no longer launch them.

Tablets must be enrolled onto **agent 0.71.0**, with **launcher 0.10.0**.

## v1.31.0 — 2026-09-14

The admin page no longer tells an operator that the root key is off the server when it is not. It now shows a warning for as long as the root key is still on the server, including when you created the intermediate certificate but did not delete the root. The reassuring message appears only once the key has actually gone.

## v1.30.0 — 2026-09-14

Device and enrolment requests are now rate limited. Limits are counted per device (by its certificate) and per enrollment token, not per network address, so hundreds of tablets behind one Wi-Fi connection are not throttled together. The limits are set generously enough for bulk policy edits and a provisioning bench. The agent download used during provisioning is deliberately not limited, because a throttled download fails inside Android's setup wizard.

## v1.29.0 — 2026-09-14

The geocoder and address-suggestion URLs in **Admin → Location** can no longer be used to reach the server's own internal services. A geocoder on your own private network still works. Loopback, link-local and cloud-metadata addresses are refused, and a redirect cannot lead anywhere more internal than where the request started.

## v1.28.0 — 2026-09-14

- Uploads over the size limit are now refused as they arrive, instead of after the whole file has been read into memory. InfraTAK's proxy also gets its own upload limit, set slightly above ATLAS's so that ATLAS gives the readable error.
- The release agent no longer contains a debug receiver that could have pointed it at a different management server.

Needs **agent 0.70.1**.

## v1.27.0 — 2026-09-14

- The console now sends strict security headers and no longer runs inline scripts. This also fixes a device serial number being able to run script in the administrator's browser.
- SMTP, Active Directory and SMS passwords are now stored sealed. Settings saved before this release still work.
- A DTED archive entry that would unpack outside its folder is refused.
- Links in guides are restricted to safe types, and the CSRF cookie cannot be read by page scripts.

## v1.26.0 — 2026-09-14

Updates the server's libraries to clear 24 published security advisories, including in the code that reads every upload and handles every request. Test tools are no longer installed in the running image.

## v1.25.0 — 2026-09-14

The trusted-proxy setting from v1.16.0 now reaches the running application. It was being written to the settings file and never passed on, so it had no effect. It takes effect on the next ATLAS update after this one.

## v1.24.1 — 2026-09-14

Internal: release records only. No change to what ATLAS does.

## v1.24.0 — 2026-09-14

Adds a certificate-authority status report for the InfraTAK module page to display. It shows what is signing certificates, when that expires, and whether the root key is still on the server, and it asks for attention 180 days before expiry.

## v1.23.0 — 2026-09-14

A device certificate can no longer outlast the certificate that signed it: its expiry is capped one day before its issuer's. As an issuer nears expiry, devices renew more often and move onto its replacement by themselves. Certificate signing is refused, with the command that fixes it, if the issuer has already expired.

## v1.22.0 — 2026-09-14

Devices now renew their own certificates before they expire, over the connection they already have. Nobody needs to touch a tablet. A failed renewal leaves the working certificate in place and tries again. The console shows the issuing certificate and its expiry, with a warning 180 days ahead. New intermediate certificates now default to five years.

Needs **agent 0.70.0**.

## v1.21.0 — 2026-09-14

Server side of certificate renewal: a device can ask for a new certificate using the certificate it already has. A revoked device cannot renew. Devices start using this in v1.22.0.

## v1.20.0 — 2026-09-14

The default lifetime of an intermediate certificate is now longer, because at this point devices could not yet renew and a short intermediate would cut their certificates short. The command warns you, and shows the numbers, when a shorter lifetime would shorten device certificates.

## v1.19.0 — 2026-09-14

ATLAS can now keep its certificate-authority root off the server. An offline root signs only a short-lived intermediate, and the intermediate on the server signs devices, so a stolen server key can be revoked instead of forcing every device to re-enroll. When the root key is missing, ATLAS refuses to start and tells you how to recover, instead of quietly creating a new authority that every enrolled device would reject.

## v1.18.1 — 2026-09-14

Internal: test records only. No change to what ATLAS does.

## v1.18.0 — 2026-09-14

Device certificates are now checked along the full chain to a trusted root, as groundwork for an offline root. Nothing changes for existing deployments or devices.

## v1.17.1 — 2026-09-14

Every InfraTAK deploy and update now checks whether ATLAS is restricted to administrators in Authentik, and says so in the deploy log and on the module tile when it is not. If Authentik cannot be reached, the last known answer is kept. ATLAS also logs at startup when it trusts every signed-in user as an administrator.

## v1.17.0 — 2026-09-14

Private keys are now created readable only by ATLAS from the start, and the `pki/` folder is private. At startup ATLAS warns about any key file whose permissions have been widened, and says how to fix it.

## v1.16.1 — 2026-09-14

Internal: security-report records only. No change to what ATLAS does.

## v1.16.0 — 2026-09-14

The console only accepts administrator requests from addresses listed in `TAKMDM_TRUSTED_PROXIES`, which the InfraTAK module supplies. If the setting is empty, nothing changes and ATLAS logs a warning at startup.

## v1.15.2 — 2026-09-14

Internal: security-audit records only. No change to what ATLAS does.

## v1.15.1 — 2026-09-14

Internal: security-audit records only. No change to what ATLAS does.

## v1.15.0 — 2026-09-14

The policy names under **Policies reaching this device** now link to their editors. A section of a profile opens the profile it belongs to.

## v1.14.3 — 2026-09-14

The location-history table heading names the console timezone instead of "UTC". If the rows fall either side of a daylight-saving change, the heading shows the zone's full name.

## v1.14.2 — 2026-09-14

The rest of the console now follows the timezone setting too: map pop-ups, every report, and the From/To date boxes. A date you type now means that day in the console timezone. The location-history CSV export stays in UTC, and its column headers say so.

## v1.14.1 — 2026-09-14

Devices enrolled before v1.12.0 now also get the default location-reporting interval. Before, only newly enrolled devices got it. The location-history retention field now shows its 30-day default instead of an empty box.

## v1.14.0 — 2026-09-14

A new **Admin → General** tab sets the console timezone. Timestamps on console pages are shown in that zone. Stored times are unchanged, and devices never see this setting.

## v1.13.0 — 2026-09-14

**Locate** and scheduled location reports now ask the device for a fresh position. Before, they read whatever position another app had last left behind, which could be hours old and somewhere else. If location is switched off on the device, **Locate** now switches it on. A fix that carries no accuracy is no longer shown as ±0 m. Not yet confirmed on a tablet with no other location app running.

Needs **agent 0.69.0**.

## v1.12.0 — 2026-09-14

Every enrolled device now reports its position, every 15 minutes by default. **Admin → Location** sets that default. A policy that sets the interval to 0 still turns tracking off for its devices. The location-history retention field shows its 30-day default.

## v1.11.0 — 2026-09-14

Devices are renamed on their own page only; the rename box has gone from each row of the fleet table. The device page now shows status under the name, then **Actions**, then **Device info** beside **Location**.

## v1.10.0 — 2026-09-14

The multi-app kiosk dock now holds five apps across instead of six, and wraps to a second row beyond that. Needs **launcher 0.9.0** (build 9).

## v1.9.0 — 2026-09-14

- The kiosk guide now covers the multi-app kiosk: tiles, dock, grid, clock and settings rows.
- ⚠️ **Power off** needs the ATLAS power menu turned on in the device's accessibility settings before the kiosk policy is assigned.
- ⚠️ **Radios off** turns off Wi-Fi and Bluetooth, not airplane mode, and does not affect the cellular radio.
- New guide, **Identify a device on sight**, covering wallpaper and the device ID label. The label cannot appear on the lock screen; the guide explains how to use the lock-screen message for that instead.

## v1.8.0 — 2026-09-14

Guides updated to match the product. Tags are no longer mentioned (assignment is to a device or a group), and the permanent enrollment QR is now documented. Also updated: storefronts, choosing an exact app build, kiosk as its own policy category, and data packages and DTED archives in file management.

## v1.7.2 — 2026-09-13

The assign form on a group's page no longer disappears once everything has been assigned. A profile already on the group is listed as "already assigned".

## v1.7.1 — 2026-09-13

A group's page can now be given a policy profile, which is what **New policy** creates. Profiles and standalone policies are in one picker. Adding a profile to a group adds that group, and leaves the profile's other groups and devices as they were.

## v1.7.0 — 2026-09-13

A group's page now shows the profiles assigned to it, and counts them. Before, a group with a profile said "nothing assigned". A single section of a profile can no longer be assigned to a group on its own.

## v1.6.1 — 2026-09-13

Saving a policy and then leaving the page no longer warns about unsaved changes that nobody made.

## v1.6.0 — 2026-09-13

The strict "must not be installed" package list has been removed; use the blocklist. Where an app cannot be uninstalled, the blocklist hides it instead. ⚠️ Packages that were listed only there are **not** moved to the blocklist, because that would start hiding apps you had asked to have deleted. Add them to the blocklist yourself if you still want them blocked.

## v1.5.0 — 2026-09-13

The app blocklist has three tickboxes that fill in the app stores for you: Google Play, Galaxy Store, and the third-party stores. The package names are written into the visible list, so you can check them, add a store, or remove one. Google Play services is deliberately left out, because ATAK and location depend on it.

## v1.4.0 — 2026-09-13

The Google Play device profile is now picked from a list, grouped by CPU architecture, instead of typed. ⚠️ Pick a 64-bit profile for 64-bit tablets: a 32-bit profile gets a working APK that is the wrong build for the device.

## v1.3.2 — 2026-09-13

After linking a Google Play account, the admin page and the success message now send you to **Apps → Google Play**, the tab that uses it.

## v1.3.1 — 2026-09-13

Internal: InfraTAK module branch housekeeping. No change to what ATLAS does.

## v1.3.0 — 2026-09-13

ATLAS now reports the version it is actually running, at `/version` and `/healthz`. This lets InfraTAK tell a finished update from a checkout that was never rebuilt.

## v1.2.2 — 2026-09-13

Reloading the page after generating an enrolment QR, or coming back to it after your sign-in lapsed, now returns you to the Enroll page. Before, it showed a raw "Method Not Allowed" error. The Wi-Fi details are not carried over.

## v1.2.1 — 2026-09-13

The Google Play panel no longer repeats itself when no account is linked.

## v1.2.0 — 2026-09-13

The logo in the top bar is twice the size, and the menu text is half as large again. On screens narrower than about 1400px the menu wraps onto a second line.

## v1.1.1 — 2026-09-13

Every form label now sits directly above its own field, on the groups, manage, storefront, new policy and profile pages.

## v1.1.0 — 2026-09-13

Required fields now show a red asterisk everywhere. This also fixes an error that stopped part of the Apps page's scripts from running.

## v1.0.2 — 2026-09-13

- **Apps → Google Play** no longer offers a search box until an account is linked, and says what to do instead.
- Links to a particular tab, such as **Admin → Google Play**, now open that tab.

## v1.0.1 — 2026-09-13

Internal: release process records only. No change to what ATLAS does.

## v1.0.0 — 2026-09-13

ATLAS now has numbered releases, so InfraTAK can tell when an update is available. The footer shows the version, with the exact build one hover away. When a release brings a new agent build, it is offered to the fleet automatically. This never overrides an agent update channel you have paused or pinned, and the launcher is never offered this way.

## v0.1.4 — 2026-09-13

The agent and the launcher now ship with ATLAS and are loaded into the library at install, so a fresh deployment can enrol devices straight away. The launcher is made available but not installed; policies assign it.

## v0.1.3 — 2026-09-13

The agent's signature checksum for the provisioning QR is now read from the uploaded agent build, so uploading the agent is the only setup needed. A configured checksum that does not match the build is refused.

## v0.1.2 — 2026-09-12

A blank admin group now stays blank: access is left to the identity provider, as intended. Before, a blank value silently turned into a group that did not exist, and every administrator was refused.

## v0.1.1 — 2026-09-12

A deployment can now set its own database password, and the setting that controls whether the TAK Server CA is included in provisioning now takes effect. Leaving an optional setting empty no longer stops the container starting.

## v0.1.0 — 2026-09-12

ATLAS appears as a module on the InfraTAK Marketplace and can be installed from there.

## Before v0.1.0

- The server, agent and protocol: stacked policies, enrolment and mTLS, desired-state check-in, the APK/XAPK pipeline, the managed-file marketplace, the Device Owner agent, kiosk, remote diagnostics, multi-identifier device identity, and the single persistent enrollment token.
- An eight-section console — Enroll, Manage, Policies, Apps, Content, Reports, Admin, Guides — themed to the ATLAS banner.
- **Manage**: a fleet table with device name, serial, model, the policies reaching each device, version and convergence, with filtering and sorting.
- **Policies**: Device, Templates and Archived tabs, and a guided composite policy creator with a category rail.
- **Apps** with local packages, an ATLAS store flag and app groups. **Content** with managed files and their deployment.
- **Reports** (fleet inventory, convergence and compliance, policy deployment, command history, app inventory, marketplace selections), each downloadable as CSV.
- **Admin**: certificates with per-certificate revoke, EULA, SMTP, AD, SMS and geofencing settings, and custom device attributes.
