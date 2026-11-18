# Put a device in kiosk mode

Kiosk (lock-task) is **optional and never the default**. The agent stays out of
the way unless a policy asks for lockdown.

This guide has two parts:

- **Part 1: Lock a device to its kiosk.** Engaging and releasing a kiosk, what
  the user can still reach, the way out at the device, and the kiosk's own
  wallpaper. This applies to every kiosk.
- **Part 2: Design a multi-app home screen.** The ATLAS launcher, its apps, the
  layout, the dock and the settings a kiosk user can change.

# Part 1: Lock a device to its kiosk

## Engage

Set **Kiosk app** in a policy's **Kiosk** category, under **Single app**, to the
app the device should be locked to. Pick its **Kiosk app build** too, and assign
the policy. (Kiosk is its own category. It is not part of App Management.) On
the next check-in the agent:

- allows that app into lock task,
- makes the kiosk app the device's home screen, so HOME goes back to it,
- relaunches the app into lock task.

**Activity class** opens one screen of the app instead of its normal start
screen. **Restrict to this activity only** stops other apps opening inside the
locked task.

⚠️ It cannot stop the kiosk app moving between its own screens. Android has no
lock for one screen of an app.

## What the user can still reach

**Permitted features** sets what a locked-in user keeps. Each one is
**Available** or **Blocked**:

- **Home button**: available by default. It goes back to the kiosk, not to the
  normal home screen.
- **Recents button**: blocked by default.
- **Notifications**: available by default. Android allows it only while the
  home button is available too.
- **Status bar information**: the clock, battery and signal. Available by
  default.
- **Lock screen**: available by default, so the device still locks. Block it
  for a wall-mounted kiosk with no keyguard.
- **Power menu**: available by default.

⚠️ **Blocking the power menu removes the only way to turn the device off or
restart it at the device.** A fielded device that then misbehaves is
recoverable by factory reset and little else.

**Peripheral Settings** has three more switches that apply only while the
device is locked in its kiosk: **Camera**, **Screen capture** and **Airplane
mode**. The standard Restrictions come back when the device leaves the kiosk.

**Background apps** lets other apps run beside the kiosk app, such as a
keyboard, a VPN app or an app the kiosk app hands off to. They are allowed into
lock task. They are not opened for you.

**Night mode** tints the whole screen red, amber or green to keep dark
adaptation, over every app. **Tint strength** never reaches fully dark.

## The way out at the device

**Kiosk exit settings** lets someone at the device leave the kiosk without a
policy change:

- **Allow manually exiting kiosk mode** turns it on. Off, the only way out is to
  change the policy.
- **Kiosk exit passcode** is 4 to 32 characters.
- **Taps to show the passcode prompt** is how many taps in the corner of the
  screen bring up the prompt (3 to 20).
- **Relaunch the kiosk app after a reboot** waits that many seconds after
  start-up before the device is locked again (0 to 300).
- **Re-enter kiosk automatically** decides whether the device locks again at
  its next check-in after someone exits.

⚠️ **The exit passcode is a gate, not a secret.** It travels in the policy the
device holds, so anyone with USB debugging can read it. Do not reuse a passcode
that protects anything else.

## Kiosk wallpaper

The **Kiosk wallpaper** section gives the kiosk its own background: a **Tablet
wallpaper**, a **Phone wallpaper** and **Also set the lock screen**. It works
with single-app and multi-app kiosks.

- While the device is in its kiosk, the kiosk image replaces the Wallpaper
  policy's image. When the kiosk is removed, the Wallpaper policy's image comes
  back.
- Set one image only and it is used on phones and tablets alike.
- Leave the section empty and the kiosk keeps the Wallpaper policy's image.
- **Stop the user changing it** and the device ID label still come from the
  Wallpaper policy. See [Identify a device on sight](/guides/howto/identification).
- In a single-app kiosk the app usually covers the background. It shows between
  apps, and on the lock screen if you set that.

A device enrolled straight into a kiosk gets its wallpaper at once. It does not
wait for the setup screen to close.

## Release

Clear **Kiosk app** in the policy's Kiosk category, or switch off **Enable
multi-app kiosk**, and save. At the device's next check-in, lock task, the
allowlist and the home screen choice all clear. No cable is needed.

## If a device is stuck

- `adb shell am task lock stop`
- `adb shell dpm remove-active-admin com.taksolutions.atlasmdm/.admin.MdmDeviceAdminReceiver`
- factory reset (last resort)

## Pick the build, not just the app

Every kiosk app needs **which build** as well as which app: the single-app
kiosk and every tile of a multi-app kiosk. The exceptions are a tile that uses
the device's own copy (see *Built-in apps* in Part 2), and ATAK in a multi-app
kiosk, which uses the build chosen for ATAK.

⚠️ **A kiosk app with no build named cannot be installed**, so the device has
nothing to lock to. It reports that the app is not installed yet and that the
device was not locked to it. Nothing is chosen on your behalf: ATLAS stopped
guessing "the newest build" after an unpinned policy entry nearly installed the
wrong app across a fleet.

A kiosk policy written before this needs the build picking once. Its page says
so: the app reads *"no version chosen — edit the policy and pick the build to
install"*.

If a build needs a newer Android than some of the policy's devices run, the
policy's page says which devices and which build. Those devices report the
install as failed and stop retrying it, so pick a build for their Android version
(on Apps, Google Play's **Download as** picks the device a build is for).

The **ATLAS launcher** needs nothing from you. It is shipped with ATLAS rather
than uploaded, so there is no wrong build to pick, and a multi-app kiosk
installs it automatically.

# Part 2: Design a multi-app home screen

## Many apps: the ATLAS launcher

A kiosk does not have to be one app. In the Kiosk category's **Multi app**
section, switch on **Enable multi-app kiosk**, add the apps to **Kiosk apps**,
and arrange them in the layout. The device gets the **ATLAS launcher** as its
home screen, locked to it. Only the apps you add can be opened.

Switch **Enable multi-app kiosk** off and save, and the policy no longer has a
multi-app kiosk. While it is off, the app list, the layout and the home screen
settings (search bar, clock, orientation) are hidden. The rows of settings a
user can change stay, because their **Blocked** choices apply to a single-app
kiosk too.

## The ATLAS console is already in the list

You will find **ATLAS Console** in Kiosk apps before you add anything. It cannot
be removed and it has no build to pick: it is the agent itself, already on the
device and updated through the agent channel. In a multi-app kiosk the launcher
is the only route to anything, and someone standing at a misbehaving tablet needs
a way to reach sync, permissions and the device's own state.

What you *can* do is decide where it goes: drag it to any cell of the layout, or
into the dock row to keep it along the bottom.

⚠️ **A list holding nothing but the console is not a multi-app kiosk.** Open
the Kiosk category, add nothing, and the section saves nothing. The console on
its own is not a home screen, and a device locked to a grid of one tile is not
what anybody meant.

## ATAK and its plugins

With **Enable multi-app kiosk** on, the ATAK and plugin pickers move from App
Management into **Multi app**, under **ATAK and plugins**, above your other
apps. App Management shows a link to them while they are there. They move back
when the multi-app kiosk is off.

- **ATAK gets a tile** as soon as you choose its build. The tile only sets
  where ATAK sits; its build is always the one chosen for ATAK.
- **Plugins never get a tile.** They run inside ATAK. A plugin cannot be added
  as a kiosk tile; saving one is refused.
- **A plugin's companion app** (TAK Beacon, for example) gets a tile of its own
  as soon as you choose the plugin. Place it or dock it like any app.
- **Enable automatic error logging**, beside the ATAK build, is here too while
  ATAK is in the kiosk.

## Built-in apps

A tile can use the app the device already has, such as Chrome, Gmail, Maps,
YouTube, Drive, Calendar, Photos, Contacts, Phone, Messages, Clock, Calculator,
Files, Keep, Meet or Google. Pick it from **Built-in: the device's own app** in
the tile's app list, or choose **Built-in: the device's own app** as the build
of an app you uploaded. **Other built-in app…** takes any package name, for a
maker's own app (a Galaxy's Phone or Messages, say).

- ATLAS never installs a built-in app. If the device has it switched off, the
  agent switches it back on.
- A device without the app leaves its tile out, and the policy's page lists those
  devices. Pick a library build for that tile to have it installed instead.

## The ATLAS store inside the kiosk

Switch on **Allow the ATLAS store** and the kiosk user can install apps from the
ATLAS store, from the ATLAS console tile.

- The policy must also choose an ATLAS store in **App Management**. ATLAS will
  not save the switch without one.
- The store's apps are the approved apps. Adding an app to the store offers it;
  taking one out uninstalls it from the devices that added it. ATAK plugins are
  never offered.
- An installed app gets a tile in the first empty space, on a new page when the
  screen is full. The user can remove apps they added, never ones the policy
  requires.

## The layout

- **Layout**: **Phone** (3 to 5 columns, 4 to 7 rows) or **Tablet** (4 to 8
  columns, 3 to 6 rows), in pages of up to 5. A new kiosk starts as a Phone, 4
  columns by 5 rows.
- Drag each app to the cell you want. Dropping it on another app swaps them, and
  dropping it on a page's tab moves it to that page.
- With the keyboard: select a tile, then the arrow keys move it, Page Up and
  Page Down move it between pages, and **D** docks or undocks it.

## The dock

Below the layout is the **Dock** row: four slots along the bottom of every page.
Drag an app into it to dock it, drag it along to reorder, and drag it back onto
the layout to undock it.

A docked app appears only in the dock, never on the pages as well. The dock holds
four; a fifth is refused. If two policies together dock more than four, a device
docks the first four and puts the rest on the pages.

Docked apps spread evenly across the bar. An app the device does not actually
have is left out, so the bar never shows an empty slot for it.

## The clock, the search bar and orientation

These settings are in **Multi app**, below the layout:

- **Show the clock**: a clock along the bottom of the home screen, just above
  the dock. The local row is always 24-hour; **Zulu row** adds UTC beneath it.
  Zulu is the second line, not an alternative, so it cannot be shown without the
  local one.
- **Show the search bar**: shown only when there are more than eight apps on the
  pages. With fewer, everything is already on screen.
- **Screen orientation**: pin the launcher to portrait or landscape.

⚠️ **The clock used to be at the top, and it collided with the device ID
label.** That label is drawn by the agent over whatever is on screen (the
launcher, ATAK, anything) at the top center. The label is anchored where it is
so it survives rotation, and it is not the launcher's to move, so the clock
moved instead.

## The top of the screen is kept clear

A band across the top of the home screen is held empty for the device name label,
whether or not a label is switched on. The first row of app icons starts below
it.

⚠️ **It is held unconditionally, and that is deliberate.** The label is drawn
by the agent over whatever is on screen; the launcher has no way to ask whether
one is showing. An empty band on a kiosk with no device name is a much cheaper
mistake than a plate of white text sitting on the first row of icons.

## The settings rows

Below the layout in **Multi app** are the controls the launcher offers a
locked-down user: night mode, brightness, screen timeout, volume, flashlight,
Bluetooth, Wi-Fi, **Radios off** and **Power off**.

- Switch any of them to **User can change** and a **Device Settings** tile appears
  in the layout, where the user finds those controls.
- **Power off** adds a **Power** tile as well.
- Drag either tile where you want it, or into the dock, like any app.
- Switch the controls off and the tiles go.

⚠️ Setting volume, brightness, Wi-Fi or Bluetooth to **Blocked** locks it on the
device. That works on a single-app kiosk too, so look for those switches here
even when the kiosk has one app.

⚠️ **Radios off** turns Wi-Fi and Bluetooth off together. It is *not* airplane
mode and does not touch the cellular radio. No app can set airplane mode,
because it needs a permission no Device Owner is granted.

⚠️ **Power off** raises Android's power menu, and needs the ATLAS power menu
enabled in the device's accessibility settings. That **cannot be done from a
locked device**, so grant it before the kiosk policy is assigned. Without it the
row appears and explains itself rather than working. It also needs **Power
menu** left available under Permitted features.
