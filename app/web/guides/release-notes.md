# Release notes

Newest first, one section per release. ATLAS — ATAK Tactical Lifecycle & Administration System, by TAK-Solutions LLC.

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
