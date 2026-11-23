# Move devices from another MDM

This guide is for a fleet that another MDM manages as **Device Owner**, for
example Headwind MDM. It tells you what to expect, what to prepare, and the order
of work.

## The short version

- **Every device must be factory reset.** There is no way to move Device Owner
  from another MDM to ATLAS in place.
- **The QR code is the supported way to enroll.** Use one QR per device group.
  Each device lands in its group and gets its policies on its first check-in.
- **Bring your inventory with you.** Export names and serials from the old MDM,
  and import them into ATLAS before the reset. Each device takes its name and
  attributes when it enrolls.
- **Start with a pilot.** Move a few devices of every model first, then one
  agency at a time.

## Why every device must be reset

Android lets an app become Device Owner only during the setup wizard of a
factory-reset device. After setup, nothing can make ATLAS the Device Owner.

Android 9 and later can hand Device Owner from one app to another, but only the
**current** owner can start that hand-over. ATLAS cannot take a device; the old
MDM would have to give it. Headwind MDM's open-source agent can receive a
hand-over but does not start one, and ATLAS does not accept one today. So plan
for a factory reset of every device.

Devices must have **Android 11 or later** to enroll in ATLAS.

## Which enrollment methods ATLAS supports

- **QR code** (tap the first setup screen six times, then scan): supported.
  Works on every make.
- **Samsung Knox Mobile Enrollment:** not supported yet. Samsung allows it for
  an MDM like ATLAS, but ATLAS has not been tested with it.
- **Android zero-touch:** not available. Google lists only approved MDM apps for
  zero-touch and no longer approves new apps of the ATLAS type. Devices must also
  come from a zero-touch reseller.

## What the factory reset removes

The reset erases everything on the device's internal storage: apps, app data,
accounts, Wi-Fi networks, photos and files. Copy anything you must keep before
the reset. A memory card can survive a reset, but do not rely on it.

⚠️ **Factory Reset Protection.** If a Google account is signed in on the device,
the device can ask for that account after the reset. Remove Google accounts
before the reset, or keep their passwords ready. A reset sent from the old MDM
does not always clear this protection. Headwind's reset command does not.

## Before you start

1. **Set up ATLAS for each agency.** Each agency has its own ATLAS deployment, at
   its own address. Make the device groups and policies there first. See
   [Build a policy](/guides/howto/building-a-policy) and
   [Policy stacking](/guides/howto/policy-stacking).
2. **Check the network.** The devices must reach ATLAS from the Wi-Fi they will
   use for setup. See [Network requirements](/guides/howto/network-requirements).
3. **Upload the apps** the devices need, and put them in the policies. See
   [Upload an app](/guides/howto/uploading-an-app).
4. **Decide on names.** A device name or a custom attribute (for example `Unit`)
   can feed settings such as an ATAK callsign. See
   [Per-device callsigns](/guides/howto/per-device-callsigns).

## Export the inventory from the old MDM

Before the reset, make one spreadsheet with a row for each device:

- **Agency:** which ATLAS deployment the device goes to.
- **Group:** which QR you will scan.
- **Name:** what ATLAS will call the device.
- **Serial:** how ATLAS matches the row to the device when it enrolls.
- **IMEI:** helps you find a device whose serial you cannot read.
- **Custom attributes:** any value a policy uses, for example `Unit`.

**From Headwind MDM:** each device has a device number, a description, its IMEI,
three custom fields and its groups. The serial is not a column. It is in the
device information that the device reported. The open-source Headwind panel has
no device-list export, so read the list from Headwind's REST API or its
PostgreSQL database.

⚠️ Keep the spreadsheet safe. Serials and IMEIs identify real devices.

## Make the QR codes

On the agency's **Enroll** page, make one QR for each group. See
the guide **Enroll a device**.

- **Enroll into group:** the group from your spreadsheet.
- **Wi-Fi:** the network the bench uses.
- **Set use count:** the number of devices you will move in that group in this
  batch.
- **Set expiration timer:** the length of the work day.

Label each printed QR with its agency and group. A code stops working when it
reaches its use count or its time, so a lost printout stops working too.

## Move each device

For each device in the batch:

1. Find its row in the spreadsheet.
2. Copy off any data that must be kept.
3. Factory reset the device. Use the old MDM's reset command, or the device's
   own settings.
4. Remove the device from the old MDM.
5. On the first setup screen, tap six times in the same place. Scan the QR for
   the device's group.
6. The device joins Wi-Fi, installs the ATLAS agent and checks in. It appears on
   **Manage** in a few seconds. Apps and files then download in the background.

## Load the devices before the reset

Import the spreadsheet into the agency's ATLAS before you reset the devices:

1. Make a CSV file with the columns **serial**, **name**, and one column for each
   custom attribute, headed with the attribute's exact name. Make the attributes
   in **Admin** first.
2. On **Manage**, the **Devices** tab, under **Names and attributes in bulk**,
   choose the file and tick **Also add serials that are not enrolled yet**.
3. Choose **Preview import**. The serials that match no device are listed under
   **Will be added, waiting to enroll**. Check them, then choose **Apply**.

Each serial becomes a record that is **waiting to enroll**. **Manage** shows these
with a label, and a filter lists only them. When a device with that serial scans a
QR, it takes the record, with its name and attributes.

- **The group comes from the QR**, not from the file. Scan the QR for the
  device's group.
- **A waiting record gets no commands.** There is no device behind it yet. Its
  page lets you change its name and attributes, or delete it.
- **The serial must match exactly** what the device reports. If a device enrolls
  as a new record instead, its serial was different. Name it on its page, and
  delete the waiting record.

⚠️ A waiting record is taken by any device that scans a working QR and reports
that serial. So keep the spreadsheet and the QR codes safe, and give a waiting
record only a name and attributes, nothing secret.

You can also do it after enrollment: download the CSV from the same panel, fill
in the names by serial, and import it without the tick.

## Order of work for many agencies

1. **Pilot.** In one agency, move a few devices of every model you own. Check
   that each one enrolls, gets its policies, and that its apps work.
2. **One agency at a time.** Move the rest of the pilot agency, then the next
   agency. Keep the old MDM running until each agency is done.
3. **Batches a bench can finish in one day.** Make that day's QR codes in the
   morning, with that day's use count.
4. **Close the day.** Revoke any QR that still works on the **Enroll** page,
   under **Live QR codes**. On **Manage**, filter on **Waiting to enroll**: every
   device in the batch should have left that list.
5. **Close the agency.** Compare **Manage** with the spreadsheet. When every
   device is in ATLAS, remove the agency from the old MDM.

## After the move

A device that ATLAS manages keeps its record when it is wiped and enrolled
again. Its hardware proves it is the same device, or someone types the security
code. Its record and history stay. See
the guide **Enroll a device**, "Re-enrolling a device ATLAS already
manages".

This applies only to devices that ATLAS already knows. On the first move from
another MDM, every device is new to ATLAS.
