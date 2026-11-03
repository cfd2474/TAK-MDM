# Put a device in kiosk mode

Kiosk (lock-task) is **optional and never the default**. The agent stays out of
the way unless a policy asks for lockdown.

## Engage

Set **Kiosk package** in a policy's **Kiosk** category to the app the device
should be locked to, and assign the policy. (Kiosk is its own category — it is
not part of App Management.) On the next check-in the agent:

- allows that package into lock task,
- makes itself the temporary home screen,
- relaunches the app into lock task with HOME, RECENTS and the launcher blocked.

The power menu, notifications and the keyguard stay available so a fielded device
is still recoverable and still locks.

## Many apps: the ATLAS launcher

A kiosk does not have to be one app. In the Kiosk category's **Multi app**
section, switch on **Enable multi-app kiosk**, add the apps, and arrange them in
the layout. The device gets the **ATLAS launcher** as its home screen, locked to
it — only the apps you add can be opened.

Switch **Enable multi-app kiosk** off and save, and the policy no longer has a
multi-app kiosk. The app list and the layout are hidden while it is off; the
settings rows stay, because their **Blocked** choices apply to a single-app kiosk
too.

### The ATLAS console is already in the list

You will find **ATLAS Console** in Kiosk apps before you add anything. It cannot
be removed and it has no build to pick — it is the agent itself, already on the
device and updated through the agent channel. In a multi-app kiosk the launcher
is the only route to anything, and someone standing at a misbehaving tablet needs
a way to reach sync, permissions and the device's own state.

What you *can* do is decide where it goes: drag it to any cell of the layout, or
into the dock row to keep it along the bottom.

⚠️ **A list holding nothing but the console is not a multi-app kiosk.** Open
the Kiosk category, add nothing, and the section saves nothing — the console on
its own is not a home screen, and a device locked to a grid of one tile is not
what anybody meant.

### The clock sits above the dock

With **Show clock** on, the clock draws along the bottom of the home screen, just
above the dock.

⚠️ **It used to be at the top, and it collided with the device ID label.**
That label is drawn by the agent over whatever is on screen — the launcher, ATAK,
anything — at the top centre. With both switched on, the two stacked. The label is
anchored where it is so it survives rotation, and it is not the launcher's to
move, so the clock moved instead.

### The top of the screen is kept clear

A band across the top of the home screen is held empty for the device name label,
whether or not a label is switched on. The first row of app icons starts below
it.

⚠️ **It is held unconditionally, and that is deliberate.** The label is drawn
by the agent over whatever is on screen; the launcher has no way to ask whether
one is showing. An empty band on a kiosk with no device name is a much cheaper
mistake than a plate of white text sitting on the first row of icons, which is
what happened when the clock moved out of that space.

### The dock

Below the layout is the **Dock** row: four slots along the bottom of every page.
Drag an app into it to dock it, drag it along to reorder, and drag it back onto
the layout to undock it. With the keyboard, select an app and press **D**.

A docked app appears only in the dock, never on the pages as well. The dock holds
four; a fifth is refused. If two policies together dock more than four, a device
docks the first four and puts the rest on the pages.

Docked apps spread evenly across the bar. An app the device does not actually
have is left out, so the bar never shows an empty slot for it.

### The layout, the clock and the search bar

- **Layout** — **Phone** (3 to 5 columns, 4 to 7 rows) or **Tablet** (4 to 8
  columns, 3 to 6 rows), in pages of up to 5. A new kiosk starts as a Phone, 4
  columns by 5 rows. Drag each app to the cell you want; dropping it on another
  app swaps them, and dropping it on a page's tab moves it to that page.
- **Show the clock** — a clock above the dock. The local row is always 24-hour;
  **Zulu row** adds UTC beneath it. Zulu is the second line, not an alternative,
  so it cannot be shown without the local one.
- **Show the search bar** — hidden automatically when there is little to search:
  a filter box above four tiles is furniture.
- **Screen orientation** — pin the launcher to portrait or landscape.

### The settings rows

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
mode and does not touch the cellular radio — no app can set airplane mode,
because it needs a permission no Device Owner is granted.

⚠️ **Power off** raises Android's power menu, and needs the ATLAS power menu
enabled in the device's accessibility settings. That **cannot be done from a
locked device**, so grant it before the kiosk policy is assigned. Without it the
row appears and explains itself rather than working.

## Release

Clear **Kiosk package** in the policy's Kiosk category. Lock task, the allowlist and the home
preference all clear within about 15 seconds — no cable needed.

## If a device is stuck

- `adb shell am task lock stop`
- `adb shell dpm remove-active-admin com.taksolutions.atlasmdm/.admin.MdmDeviceAdminReceiver`
- factory reset (last resort)

## Pick the build, not just the app

Every kiosk app needs **which build** as well as which app — the single-app
kiosk and every tile of a multi-app kiosk — unless the tile uses the device's own
copy (see *Built-in apps* below).

⚠️ **A kiosk app with no build named cannot be installed**, so the device has
nothing to lock to and reports *"the app designated for kiosk mode not
installed, not engaging"*. Nothing is chosen on your behalf: ATLAS stopped
guessing "the newest build" after an unpinned policy entry nearly installed the
wrong app across a fleet.

A kiosk policy written before this needs the build picking once. Its page says
so — the app reads *"no version chosen — edit the policy and pick the build to
install"*.

If a build needs a newer Android than some of the policy's devices run, the
policy's page says which devices and which build. Those devices report the
install as failed and stop retrying it, so pick a build for their Android version
(on Apps, Google Play's **Download as** picks the device a build is for).

The **ATLAS launcher** is the exception and needs nothing from you. It is
shipped with ATLAS rather than uploaded, so there is no wrong build to pick, and
a multi-app kiosk installs it automatically.

## Built-in apps

A multi-app kiosk tile can use the app the device already has, such as Chrome,
Gmail, Maps, YouTube, Drive, Calendar, Photos, Contacts, Phone, Messages, Clock,
Calculator, Files, Keep, Meet or Google. Pick it from **Built-in: the device's own
app** in the tile's app list, or choose **Built-in** as the build of an app you
uploaded. **Other built-in app** takes any package name, for a maker's own app
(a Galaxy's Phone or Messages, say).

- ATLAS never installs a built-in app. If the device has it switched off, the
  agent switches it back on.
- A device without the app leaves its tile out, and the policy's page lists those
  devices. Pick a library build for that tile to have it installed instead.
