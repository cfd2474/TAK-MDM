# Give every device its own callsign

One policy, a different value on every device. Write `${device.name}` or
`${attribute.Unit}` in a setting, and each device receives its own name or Unit
in its place. A fleet of trackers then needs one policy, not one per device.

## The variables

- **`${device.name}`**: the name set on the device's page. The usual choice
  for a readable callsign.
- **`${device.id}`**: ATLAS's own identifier for the device. Unique and never
  changes, but long; better for a machine than a map.
- **`${device.serial}`**: the hardware serial. Missing on a device that Android
  would not tell its serial to (ATLAS then knows it only by another ID).
- **`${device.model}`**: the model the device reports, such as SM-X520.
- **`${attribute.Unit}`**: any custom attribute you define, by its exact name,
  spaces and capitals included: `${attribute.Vehicle number}`.

A variable can sit inside other text: `Medic ${attribute.Unit}`. Fallbacks
such as `${device.name:-…}` are not supported.

## Where they work

- **App Management › App configurations**: any text setting of any app with a
  managed configuration, for example AndroidTAKTracker's **callsign**. Inside a
  JSON setting such as its `serversJson`, put the variable inside quotes; ATLAS
  keeps the JSON valid whatever the name contains.
- **ATAK Config**: ATAK's own settings (filter the table for "callsign") and
  plugin settings.

Only text settings take a variable. A number or a true/false cannot hold a
name, and saving one there is refused. TAK Server connections do not take
variables.

## Set it up for a fleet

1. **Create the attribute.** In **Admin › Custom attributes**, add one called
   `Unit`. Skip this if the device name is enough.
2. **Fill it in.** On **Fleet**, the Devices tab, under **Names and attributes
   in bulk**, choose **Download CSV**. It has a row per device with its serial,
   model, name and a column for each attribute. Fill in the names or the Unit
   column in a spreadsheet, save it as CSV, and choose **Preview import**.
   - The preview lists every change before anything is applied. Choose
     **Apply** when it is right.
   - A blank cell clears that value. A column you delete from the file is not
     touched, so a file with just **serial** and **Unit** changes only Units.
   - Rows ATLAS cannot match to a device are listed under **Not used**.
   - One device at a time also works: its page has a name and its attributes.
3. **Write the policy.** In the setting, choose **Insert device variable…**
   beside the text box, or type it: `callsign = ${attribute.Unit}`.
   AndroidTAKTracker adds its own `.att` after the callsign, so do not add it
   yourself.
4. **Check before you rely on it.** Under **Preview device variables** on the
   policy's page:
   - the table shows, across every device the policy is assigned to, how many
     have a value for each setting and which do not, and any value several
     devices would share. Two trackers with one callsign look like one on the
     map;
   - **Preview** shows exactly what one chosen device would receive.

## When a device has no value

That one setting is **left out** for that device, and the app uses its own
default. ATLAS never sends the literal `${…}` or an empty value. The device's
page says **Device variables — N settings left out**; hover over it for which
setting and which variable. Give the device a value and the setting arrives on
its next check-in.

## Good to know

- **Changes follow the device.** Renaming a device, or changing one of its
  attributes, sends the new value on its next check-in. A rename also asks the
  device to check in straight away.
- **An attribute a policy uses cannot be deleted.** ATLAS names the policies
  to change first.
- **Values that look secret are hidden.** A setting whose name contains
  password, token, secret or similar shows as `••••••` in previews, summaries
  and the device page. Devices still receive the real value.
- **A higher-ranked policy wins.** If another policy sets the same setting at
  a higher rank, its value is what the device gets. The device's page shows
  what it actually receives.
