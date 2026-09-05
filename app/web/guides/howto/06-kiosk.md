# Put a device in kiosk mode

Kiosk (lock-task) is **optional and never the default**. The agent stays out of
the way unless a policy asks for lockdown.

## Engage

Set `kiosk_package` in a policy's App Management section to the package name of
the app the device should be locked to, and assign the policy. On the next
check-in the agent:

- allows that package into lock task,
- makes itself the temporary home screen,
- relaunches the app into lock task with HOME, RECENTS and the launcher blocked.

The power menu, notifications and the keyguard stay available so a fielded device
is still recoverable and still locks.

## Release

Remove `kiosk_package` from the policy. Lock task, the allowlist and the home
preference all clear within about 15 seconds — no cable needed.

## If a device is stuck

- `adb shell am task lock stop`
- `adb shell dpm remove-active-admin com.taksolutions.atlasmdm/.admin.MdmDeviceAdminReceiver`
- factory reset (last resort)
