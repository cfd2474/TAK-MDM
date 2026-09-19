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

A kiosk does not have to be one app. Fill in **Kiosk apps** in the Kiosk
category and the device gets the **ATLAS launcher** as its home screen, locked
to it — only the apps you list can be opened, in the order you list them.

### The ATLAS console is already in the list

You will find **ATLAS Console** in Kiosk apps before you add anything. It cannot
be removed and it has no build to pick — it is the agent itself, already on the
device and updated through the agent channel. In a multi-app kiosk the launcher
is the only route to anything, and someone standing at a misbehaving tablet needs
a way to reach sync, permissions and the device's own state.

What you *can* do is decide where it goes: move it with the arrows, or tick
**Dock** to keep it along the bottom.

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

Tick **favourite** on an app and it also appears in the dock along the bottom,
reachable from anywhere on the home screen.

⚠️ `favorite` is a property of the app, not a separate list. Two lists could
disagree — a dock tile naming an app the kiosk does not permit — and that tile
would refuse to open, which reads as a broken device rather than a bad policy.

Docked apps spread evenly across the bar, up to five across; beyond that the
dock wraps to a second row and grows rather than hiding the overflow. A favourite
naming an app the device does not actually have is dropped, so the bar never
appears empty.

### The grid, the clock and the search bar

- **Grid columns** — 2 to 8 tiles across.
- **Show the clock** — a clock across the top. The local row is always 24-hour;
  **Zulu row** adds UTC beneath it. Zulu is the second line, not an alternative,
  so it cannot be shown without the local one.
- **Show the search bar** — hidden automatically when there is little to search:
  a filter box above four tiles is furniture.
- **Screen orientation** — pin the launcher to portrait or landscape.

### The settings rows

**Peripheral Settings** decides which controls the launcher offers a locked-down
user: night mode, brightness, screen timeout, volume, flashlight, Bluetooth,
Wi-Fi, and **Radios off**.

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
kiosk and every tile of a multi-app kiosk.

⚠️ **A kiosk app with no build named cannot be installed**, so the device has
nothing to lock to and reports *"the app designated for kiosk mode not
installed, not engaging"*. Nothing is chosen on your behalf: ATLAS stopped
guessing "the newest build" after an unpinned policy entry nearly installed the
wrong app across a fleet.

A kiosk policy written before this needs the build picking once. Its page says
so — the app reads *"no version chosen — edit the policy and pick the build to
install"*.

The **ATLAS launcher** is the exception and needs nothing from you. It is
shipped with ATLAS rather than uploaded, so there is no wrong build to pick, and
a multi-app kiosk installs it automatically.
