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

## Blocking data (Samsung Knox)

The **Network data use management** policy can block data as well as track it. Blocking
works only on Samsung devices with an active Knox license, because Android
itself gives an MDM no way to block data. Each blocking control says
**Samsung Knox only**.

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

The ATLAS agent is never blocked, so a block cannot cut a device off from
ATLAS. An app cannot be both always allowed and blocked. When stacked policies
disagree, a block wins.

A limit is checked at each check-in, not at the exact moment it is passed.

⚠️ A device without Knox does not block anything. Its device page shows
**Data blocking: Not enforced**, with the reason, so you never believe in a
block that is not there.

## Knox Configurations: fonts and OS updates

**Fonts** (Samsung Knox only). Choose a **Font** that is already on the
device, and a **Font size** in percent. Knox cannot add a new font. The font
box offers the fonts that devices have reported, each with the devices that
reported it, and you can also type a name.
A device that does not have the font keeps its own font and says so. Each
device uses the font size nearest to the one you set. A factory reset removes
both settings.

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

**Boot and shutdown animation** (Samsung Knox only). Upload Samsung's
animation files: **Boot animation** (`bootup.qmg`) and **Boot loop**
(`bootloop.qmg`) together, and **Shutdown animation** (`shutdown.qmg`). Each
can have an OGG sound, and the boot sound can start after a delay. Without a
sound, the device uses a silent one, because Samsung requires a sound. You cannot
make `.qmg` files with Samsung's own tools: send your animation frames as PNG
files to Samsung through a support ticket in the Knox Admin Portal, and
Samsung returns the `.qmg` files. Remove the files from the policy to bring
back the device's own animation. The device page shows the result for each
animation.

⚠️ Samsung warns that a device with encryption on may show its default
animation, and that US carrier models do not support custom animations.
