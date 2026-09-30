# Identify a device on sight

A tablet in a rack of identical tablets is anonymous. Two controls make one
recognisable without unlocking it: the **wallpaper** it wears, and its **name**,
shown on screen.

## Wallpaper

In a policy's **Wallpaper** category, upload or pick an image from Content.

- **Tablet wallpaper** applies to devices at least 600dp wide, **Phone
  wallpaper** to narrower ones — Android's own dividing line. Set whichever
  your fleet is; set both for a mixed fleet.
- **Also set the lock screen** puts the same image behind the keyguard.
- **Stop the user changing it** sets `DISALLOW_SET_WALLPAPER`.

⚠️ The agent applies the image *before* imposing that restriction, because the
restriction would otherwise block the agent too — the order is deliberate, not
incidental.

## The device ID label

**Device ID label**, in the same Wallpaper category, shows the device's name — as
set on its device page — in a small panel at the top of the home screen. It works
over the stock launcher and the ATLAS one, stays put through rotation, and steps
out of the way when an app is opened. A device with no name shows its serial, so
the label always identifies *something*, and renaming updates it on the next
check-in.

It needs no wallpaper image; the two controls are independent.

⚠️ **It needs Usage access**, which a human grants once on the device, in the
agent. Without it the label still appears — but over everything, instead of only
on the home screen. Grant it while setting the device up.

⚠️ **It is not shown on the lock screen.** The panel sits below the keyguard,
and no app can draw above it. For a name on the lock screen, use the message
below.

## A name on the lock screen

In a policy's **Customizations** category, set the **Lock screen message**. It is
shown before anyone unlocks the device — the right place for ownership or
return-if-found text, and the wrong place for anything sensitive, since it is
readable by whoever is holding the tablet.

Write `{device}` anywhere in the text and each device substitutes its own name,
or its serial if it has not been named. One policy then labels a whole fleet:

```
Property of 3rd Battalion — {device}. If found, call 555-0100.
```

The same token works in the other Customizations messages — the one shown when a
user opens a disabled setting, and the admin app's description.

⚠️ While a lock screen message is set the user cannot change the lock screen
owner info themselves. Clearing it hands that back to them.

## Which to use

| You want | Use |
|---|---|
| Recognise a device across a room | Wallpaper, per model |
| Read a device's name while using it | Device ID label |
| Read a device's name while it is locked | Lock screen message with `{device}` |
| Tell a finder who owns it | Lock screen message |
