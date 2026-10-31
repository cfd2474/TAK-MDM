# The dashboard

The page ATLAS opens on. It shows how the server is doing and whether
anything in ATLAS needs you. Open it any time from **Dashboard** in the menu,
or by selecting the ATLAS logo.

It updates itself every minute while it is open. Under the tiles it says
when it last updated; if an update fails it says so and keeps showing the
figures it last had, with their time. It does not update while the tab is
in the background, and catches up as soon as you come back to it.

## Server resources

Three rings for the server ATLAS runs on. They describe the whole server,
not only ATLAS, because that is what runs out.

- **CPU:** how busy the processors have been since the last update, about
  the last minute. Below it, the load average over 1, 5 and 15 minutes and
  the number of processors.
- **Memory:** memory in use, out of the server's total.
- **Disk:** space used on the disk that holds the app and file library, out
  of its total. It is the same figure as the storage meter on the Apps and
  Content pages.

A ring turns amber at 75 % and red at 90 %. A figure ATLAS cannot read shows
a dash, never 0 %.

## Status

One tile each. Green is fine, amber needs attention soon, red needs it now,
grey is either not set up or not readable. The line under each value says
which.

| Tile | What it checks |
|---|---|
| **Database** | That ATLAS's database is answering, and how big it is. |
| **HTTPS certificate** | Days until the certificate on the console's address expires. Amber under 30 days, red once expired. ATLAS reads it by connecting to its own address about once an hour, so a renewal can take up to an hour to show. If the server cannot reach its own address (some firewalls and load balancers prevent it), the tile shows **Unknown**. |
| **Device CA** | Days until the certificate authority that signs device certificates expires. Renew it from **Admin › Certificates** before it does. |
| **Google Play** | Whether a Google account is linked for downloading apps. **Not linked** is grey: you only need it to import from Google Play. **Broken** means the account stopped working and must be linked again. |
| **TAK.gov** | The same for the TAK.gov link. |
| **Open alerts** | Alert conditions that still hold, such as a device out of compliance. Events that are over (a device was wiped) are not counted. See **Alerts**. |
| **Expired device certificates** | Enrolled devices whose certificate has expired. They cannot check in until reinstated. |
| **Stalled enrollments** | Devices that enrolled and then never checked in. The device page says what to check. |

Below the tiles: how long the server has been up, and the total size of the
app and file library.

## The device list

The list of devices that used to be the first page is under **Manage**.

## The summary and the warning banner

The line under the title counts enrolled devices: how many checked in during
the last 24 hours, how many have not been seen in over a year, how many have
never checked in, and how many have a last known location. Devices that
were imported but never enrolled, and retired devices, are not counted
anywhere on this page.

When any status tile is red, a banner under the summary says which and why.
It disappears on the next update once nothing is red.

## Fleet by last check-in

Every enrolled device falls into one bucket, by when it last checked in:

| Bucket | Last check-in |
|---|---|
| **Active <24h** | Within the last 24 hours |
| **Stale 1–7d** | 1 to 7 days ago |
| **Stale 7–30d** | 7 to 30 days ago |
| **Stale 30d–1y** | 30 days to a year ago |
| **Stale >1y** | Over a year ago |
| **Never checked in** | Enrolled, and has not checked in yet |

The bar shows the whole fleet; the table below it gives the counts. Next to
the bar: the total, how many are stale (the four Stale buckets) with their
share of the devices that have ever checked in, and how many are over a
year.

Above the bar: **new enrollments** in the last 24 hours and 7 days (by when
the device record was created, so a device re-enrolled under an existing
record keeps its first date), and **low battery**: devices under 20 % that
checked in within the last 24 hours.

## Groups: active vs stale

One bar per device group, in the same buckets. A device in several groups
counts in each, so the groups can add up to more than the fleet. Devices in
no group have a **No group** row. Bar length is the group's size, against
the largest group.

Sort with the tabs: **Most stale**, **Most >1 year**, **Stale share** or
**Largest**.

## Last known device locations

Each enrolled device at the last position it reported, on the map tiles set
under **Admin › Location**. Devices within about 1 km of each other share a
dot. A bigger dot is more devices; its colour is the oldest bucket among
them. Select a dot for the devices in it, each a link to its page.

Switch buckets on and off with the checkboxes, and choose a group to see
only its devices. The map stays where you put it when it updates.

## Trends

ATLAS takes one reading a day, in the console's timezone, and keeps a year
of them. Four charts, over the last 30, 90 or 365 days:

- **Checked in:** devices that checked in within an hour, and within 24
  hours, of the reading.
- **Stale over 30 days:** devices that have checked in before, but not for
  30 days or more.
- **Disk and memory:** the server's disk and memory use, in percent.
- **Low battery devices:** as above.

The charts start on the day this version is installed. ATLAS does not
record the past, so there is nothing to fill in before then. A day with no
reading (the server was off all day) is a gap in the line. Point at a dot
for its date and value.
