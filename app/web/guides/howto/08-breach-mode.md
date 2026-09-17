# Breach mode

For a device in the wrong hands. One button on the device's page replaces
**every policy that device has** with the breach policy: its apps are removed,
the directories you name are emptied, it is locked with a passcode you chose,
and it reports its position every minute.

⚠️ **It is deliberately not a factory reset.** A wiped device stops reporting
where it is, and that is the one thing still worth having from a tablet somebody
else is holding. Making a device useless and making it silent are different
goals; this does the first. When you want the second, use **Disenroll and
factory reset**.

## Set it up before you need it

**Admin → Breach mode.** Opening the tab creates the configuration, so you can
read and change what the button will do before anyone presses it. The device
page refuses to engage breach mode until this has been done — a device breached
against nothing would lose every policy it had and receive nothing back.

| Setting | What it does |
|---|---|
| Directories to empty | Deleted, contents and all. Defaults to Downloads, Documents, ATAK, DCIM and Pictures. |
| The passcode | Forced onto the device, so whoever holds it is locked out and you are not. |
| Lock screen message | Shown before anyone unlocks it — return-if-found text. |
| Reporting interval | One minute by default. |
| Wallpaper | Shown on the device. |

The **apps removed** list is generated, not edited: it is every app and plugin in
your library, taken as it stands at the moment a device is breached. The ATLAS
agent and launcher are never on it — removing them would leave nothing on the
device able to report where it is.

## Engaging it

On the device's page, under **Lifecycle**. You type the serial number to
confirm, the same gate as a factory reset and for the same reason.

The page then shows one of two things, and the difference matters:

* **breach sent — not yet confirmed.** The instruction is waiting. A device that
  is switched off, or already out of contact, stays here.
* **breach applied.** The device checked in and acted on it.

⚠️ *Applied* means the device acted on the instruction, not that every part
succeeded. An app that ships with the device cannot be uninstalled, only hidden,
and anything that failed is reported under **Last reported problem** on the same
page. Read it.

## Afterwards

⚠️ **Nothing here can be undone on the device.** Clearing breach mode restores
the device's policies exactly as they were — none of them were ever unassigned —
but the apps it lost and the files in those directories do not come back.

Clearing is for a breach engaged by mistake. **A device that has genuinely been
in someone else's hands should be factory wiped and reprovisioned before it is
trusted again**, whatever the console says about it.

## What it does not do

* It does not breach a group or a fleet. One device, one button, one serial
  typed.
* It does not engage itself. A device that stops checking in is not
  automatically breached — that decision is yours.
