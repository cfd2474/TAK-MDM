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

The ATLAS console is always added as a tile. In a multi-app kiosk the launcher
is the only route to anything, and someone standing at a misbehaving tablet
needs a way to reach sync, permissions and the device's own state. Add it
yourself if you want to choose where it sits.

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
