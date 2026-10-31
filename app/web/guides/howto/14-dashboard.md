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
