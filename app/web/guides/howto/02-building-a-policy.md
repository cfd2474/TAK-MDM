# Build a policy

What **New Policy** builds is a **profile**: a composite that bundles several
single-concern settings — password, restrictions, apps, files — as categories.
Each category you fill in becomes an independent stackable **section**
underneath, named `<profile> · <category>`.

⚠️ **A section is assigned through its profile, never on its own.** The
Policies list shows the profile, not its sections, and assigning a section
directly is refused. Assign the profile, and every section it owns applies
together, at one rank.

## Steps

1. On the **Policies** page, press **New Policy**, then **Create from scratch**.
2. Name the policy.
3. Choose its **Deployment** state (see below).
4. Work down the category rail on the left. For each category you want to set,
   fill in its controls. Leave a control at *Not managed* to skip it. Only the
   settings you set are stored, so a narrow policy stacks onto a broad one
   without blanking it.
5. Categories shown as *"Not available yet"* need support that has not shipped.
   They will light up in place when it does.
6. Press **Create policy**, or **Save as template** to keep it as a template
   instead. **Create policy** stays grayed out until the policy has a name.
7. You land on the policy's page. It is the same editor, with one **Save policy**
   button for every category. A category whose settings changed gets a new
   version. Set every control in a category to *Not managed* and save to remove
   that category.

**Duplicate policy**, at the bottom of a saved policy, opens a new policy filled
in with all its saved settings, named "Copy of …". The copy is not assigned to
anything, and uses the deployment choice on the new-policy page.

## Assigning it

On the policy's page, use **Assign to devices**. Set the **Rank**, tick devices
or groups, and press **Save and Apply**. It saves your edits to the policy first,
then applies it. The whole thing applies at one rank; unticking a box unassigns.

Each list has a search box: type part of a device's name, serial or model, or
part of a group's name. Devices the policy is already assigned to are listed
first.

You can also work from the other end: a group's page has an **Assign to this
group** control, one A–Z list of every policy.

To change a rank afterwards for one device or one group without touching the
others, edit it where the assignment lives: on the device's page for a policy
assigned to that device, or on the group's page for a policy assigned to the
group. See *How policy stacking works*.

## Templates

Save a finished policy as a **template** from its page, or press **Save as
template** when you create it. A template is a blueprint: it is never assigned,
only cloned into a new policy. Find templates on the **Templates** tab of the
Policies page, and choose **Create a policy from this template**.

## Holding it back, or scheduling it

A policy can be complete — content, devices, groups — and still not be in force.
Every policy is in one of three states, chosen under **Deployment** when you
create it and changeable afterwards from its page:

- **Live**: in force now, on everything it targets. This is the default and
  what every existing policy is.
- **Hold**: reaches no device until you come back and deploy it. Targets can be
  set up freely in the meantime.
- **Deploy at**: reaches devices at the date and time you give, on its own.

⚠️ **Decide it when you create the policy, not after.** A brand-new policy has no
targets, so creating it live is harmless in itself — but you then have to
remember to hold it *before* ticking the first device, and forgetting sends it
to the fleet on the spot.

A held or scheduled policy is marked in the Policies list. A live one is not:
almost everything is live, and a badge on every row is a badge nobody reads.

### The time you type is your time

Times are in the console timezone, set in **Admin → General**. When you save a
schedule the console confirms it back in **both** that zone and UTC — for
example *"deploys at Wed 16 Dec 2026, 08:00 PST (Wed 16 Dec 2026, 16:00 UTC)"*.

⚠️ **Read that line.** It is the only place a timezone set wrongly ever shows
itself: the form redisplays what you typed and the list shows the local form of
it, so both agree with each other and with a wrong zone. A deployment eight
hours out lands on field devices in the middle of the night.

A time that has already passed is accepted rather than refused — it is how
"deploy now" comes out of a form that only offers a date — and the confirmation
says so.

### If the server is off at the appointed hour

Nothing is lost. The schedule is not a job queued to run at a moment; it is a
fact the system reads every time it works out what a device should have. A
server that was down at 08:00 puts the policy in force on the way back up, and a
device that checks in before anything has swept still gets it.

## Taking an app back when the policy stops asking for it

Each required app has an **Uninstall if withdrawn** tick. So do ATAK Core and
each ATAK plugin, under **App Management › ATAK Core and Plugins**. With it on,
the device
removes that app once no policy requires it any more — when you unassign the
policy, delete it, or simply take the app out of its list.

⚠️ **Uninstalling destroys the app's data**, which is why this is off by default
and set per app rather than per policy. A network profile can be removed and
re-added for free; an app cannot. Uninstalling ATAK removes its data too, and
its plugins have their own tick: tick theirs as well if they should go with it.

⚠️ **Ticking it does not uninstall anything.** The app is still required, so it
stays. The tick only says what happens the day nothing requires it.

The device does the deciding, because only the device knows what it has. It
claims an app the first time it sees one that is required, ticked and installed
— including apps installed long before you turned this on, so the setting works
on tablets already in the field.

Two apps are never removed this way: the ATLAS agent, which Android refuses to
uninstall anyway, and the ATLAS launcher, which the kiosk policy removes when it
is no longer needed.

⚠️ An app that ships with the device cannot be uninstalled at all. The device
reports that it could not remove it, on every check-in, rather than going quiet
about an app that is still there.

## Airplane mode and device controls

Standard Android, so these work on every device:

- **Restrictions → Radios → Airplane mode** — Blocked stops the user turning
  airplane mode on or off.
- **Restrictions → Device controls:** **Status bar expansion**, **Add users**,
  **Backup** and **Force stop and clear data**. A managed device starts with
  backup off; Allowed turns it on.

These keep their last setting when you remove them, like **Camera**; set
**Allowed** to lift one. While the web filter runs, **Force stop and clear
data** stays blocked whatever this control says.

## Date and time, SMS, default browser and Wi-Fi names

Standard Android, so these work on every device:

- **Restrictions → Date and time:** **Automatic date and time** (On or Off) and
  **Change date and time** (Blocked stops the user changing the date, time or
  time zone). ⚠️ A device with the wrong time can fail to reach ATLAS.
- **Restrictions → Network & communication → SMS and MMS:** Blocked stops text
  messages.
- **App Management → Default apps → Default browser:** the app that opens web
  links. The app must be installed. It is not applied to the app a kiosk is
  locked to.
- **Networks → Allowed Wi-Fi networks (SSID):** the device joins only these
  networks. ⚠️ Include the network it uses to reach ATLAS. Needs Android 13 or
  later.

The 24-hour clock is Samsung Knox only: **Knox Configurations → Date and
time → Time format**.

## Knox Configurations

Everything that needs Samsung Knox is in the **Knox Configurations** policy,
even where it is about radios, apps or data. Each control says **Samsung Knox
only**. A device without an active Knox license applies none of them, and its
device page says so.

**Fonts.** Choose a **Font** that is already on the device, and a **Font
size** in percent. Knox cannot add a new font. The font box offers the fonts
that devices have reported, each with the devices that reported it, and you
can also type a name. A device that does not have the font keeps its own font
and says so. Each device uses the font size nearest to the one you set. A
factory reset removes both settings.

**Power and USB:**

- **Start up when USB power is connected:** the device starts fully when power
  reaches its USB port, instead of only showing the charging screen — for
  tablets in a vehicle mount or a case.
- **Shut down when USB power is removed:** the device turns off when its USB
  power is disconnected.
- **USB connection type:** what the device offers a computer it is plugged into:
  the device default, MTP (file transfer), PTP (photo transfer), MIDI, or
  charging only. To forbid file transfer altogether, use Restrictions.

Removing one of these from the policy puts it back to the device's default,
but only if ATLAS set it.

**Battery optimization exceptions:** apps that Android never puts to sleep to
save battery, for example ATAK, so it keeps reporting in the background. Pick
apps from the library or type a package name.

**Radios:** **Cellular data**, **Bluetooth discoverable**, **Hotspot and
tethering** and **USB tethering**. ⚠️ Blocking cellular data on a tablet with
no Wi-Fi leaves it no way to reach ATLAS to lift the block.

**Roaming:** **Data**, **WAP push**, **Data sync** and **Voice calls** while
roaming.

**Device controls:** **Power off**, **Microphone**, **Settings changes**,
**Clipboard**, **Share menu** and **Smart select**. ⚠️ Blocking the microphone
also stops push-to-talk in ATAK.

For the radio, roaming and device controls, a block wins when stacked policies
disagree. Removing a control allows it again, but only if ATLAS blocked it.
The device page lists what Knox blocks on that device.

**USB and storage:**

- **USB host (OTG)** — Blocked stops everything plugged into the USB port:
  drives, card readers, keyboards and adapters. Charging still works.
- **SD card write** — Blocked makes the SD card read-only.
- **Allowed USB devices** — tick the kinds of USB device that may work; every
  other kind is blocked. USB hubs always work. A device that is several kinds
  at once, such as a headset with buttons, needs each kind ticked. Leave all
  boxes empty to not manage it. It has no effect while **USB host** is
  Blocked. When stacked policies set it, the highest-ranked policy wins; the
  lists are not combined.

**Data blocking** and **App data blocking.** Android itself gives an MDM no
way to block data, so this is Knox only.

- **Block Wi-Fi data** and **Block mobile data** block every app on that network.
- **Data usage restrictions** block the device when its use passes a limit.
  The block lifts when the day, week or month resets.
- **Always allowed apps** keep their data when the device is blocked, for
  example ATAK on mobile data. Pick an app with **Add from library**, or type
  any package name.
- **Per-app data usage restrictions** block one app when its own use passes a
  limit.
- **Always blocked apps** block one app on Wi-Fi, mobile data or both, all the
  time.

⚠️ The usage limits count use the way the **Network data use management**
policy tracks it: its reset time and day, and only while **Enable data usage
tracking** is on. With tracking off, a usage limit never blocks.

The ATLAS agent is never blocked, so a block cannot cut a device off from
ATLAS. An app cannot be both always allowed and blocked. When stacked policies
disagree, a block wins. A limit is checked at each check-in, not at the exact
moment it is passed. A device without Knox shows **Data blocking: Not
enforced** on its device page, with the reason.

**OS updates.** **When to install OS updates** works on every device, because
it is standard Android:

- **Automatic** installs an update as soon as it is ready.
- **Daily Window** installs it only between the two times you set. The window
  can go past midnight.
- **Postpone 30 Days** holds an update for up to 30 days.

Two more switches are Samsung's own, and work only with Knox:
**Block OS updates** stops every OS upgrade, and **Download OS updates
automatically** sets Samsung's own Settings option. You cannot block updates
and set an install schedule in the same policy. When stacked policies
disagree, a block wins. Remove the policy to lift the block.

The device page shows whether an OS update is waiting to install.

**Boot and shutdown animation** (Samsung Knox only). First make the
animation in **Content → Boot/shutdown animations**: give it a name, choose
**Bootup sequence** or **Shutdown sequence**, and choose the screen size.
Then add the frames one way:

- **PNG frames, one by one:** add PNG files to each part (for a bootup
  sequence, the boot animation and the boot loop). Several files chosen at
  once are added in name order. Move a frame up or down with the arrows, or
  remove it. ATLAS names the frames for you. For a bootup sequence, **one
  lane is enough**: with frames only in the boot animation, the loop holds its
  last frame until the device is ready; with frames only in the boot loop,
  they also play once first.
- **A zip of PNG frames**, named as in Samsung's guide (`bootup01.png`… and
  `bootloop01.png`… for a bootup sequence, `shutdown01.png`… for a shutdown
  sequence).
- **Ready-made `.qmg` files.**

For a **shutdown sequence**, two more choices:

- **Landscape tablet: turn the shutdown animation.** On a tablet held in
  landscape, Samsung shows the shutdown animation turned on its side (measured
  on the SM-X520). With this on, ATLAS turns your frames so landscape art shows
  the right way up. It is on by default when you choose a tablet's screen size.
- **Shutdown length**, 1 to 5 seconds (3 by default). The frames are spread
  over this time; Samsung allows up to 30 shutdown frames.

When you click **Make animation**, a window shows each step: **Check** (the
name and the frames, before anything is sent), **Upload** (with progress),
**Make** (ATLAS makes the `.qmg` files), and the **Outcome**: the files made, or
the reason nothing was made. After a refusal, **Back to the form** keeps what
you entered, so you can fix it and try again. ATLAS adds `_boot`, `_bootloop` or
`_shutdown` to your name. Animations play at 12 frames per second; Samsung
allows up to 99 frames for boot and boot loop, and 30 for shutdown.

Then, in the policy, choose **Boot animation** and **Boot loop** (choosing
the *name*\_boot animation also picks *name*\_bootloop), and **Shutdown
animation**, by name. The
device saves them as `bootup.qmg`, `bootloop.qmg` and `shutdown.qmg`. Each
can have an OGG sound, and the boot sound can start after a delay. Without a
sound, the device uses a silent one, because Samsung requires a sound. Remove
the animations from the policy to bring back the device's own. The device
page shows the result for each animation.

⚠️ Samsung warns that a device with encryption on may show its default
animation, and that US carrier models do not support custom animations.
