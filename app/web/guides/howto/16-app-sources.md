# Get apps from Google Play, TAK.gov and the plugin catalogs

Besides uploading a file, the **Apps** page can fetch apps from four places, each
on its own tab:

- **TPC Plugins**: the TAK.gov plugin catalog. Needs a linked TAK.gov account.
- **TAKWERX Plugins**: the TAKWERX catalog of ATAK plugins. Needs no account.
- **Google Play**: needs a linked Google account.
- **3rd Party Repos**: F-Droid, the F-Droid archive, IzzyOnDroid and APKPure.
  Needs no account.

⚠️ **Importing is not deploying.** An imported build joins the library, on the
**Local apps** tab, and nothing installs it until a policy names it. Importing a
newer build does not move devices either: change the build in the policy, or set
the app to **Always the newest build**. See
[Upload and deploy an app](/guides/howto/uploading-an-app).

Every import is checked by reading the downloaded file, the same way an upload
is. What a catalog says about an app is never taken on trust.

## Link a TAK.gov account

Go to **Admin → TAK.gov** and press **Link a TAK.gov account**. ATLAS shows a
short code. Enter it at tak.gov while signed in, then press **I have entered the
code**. This is the same "Link EUD" flow ATAK itself uses.

- **linked**: the catalog shows what that account is entitled to see. The link
  is a person's account, so treat it like that person's password.
- **waiting for you at tak.gov**: a code was issued and not yet entered. The page
  shows when it expires.
- **link broken**: the link worked once and has stopped. Link it again.
- **not linked**: there is no TAK.gov catalog to show.

The dashboard's **TAK.gov** tile shows the same state: **Linked**, **Waiting for
code**, **Broken** or **Not linked**.

## Link a Google account

Go to **Admin → Google Play**. The page lists the steps: sign in at Google's
setup page with the account ATLAS should download as, copy the one-time
**oauth_token** cookie value, and paste it with the account's email. Press
**Link account**.

⚠️ **Using this violates Google Play's Terms of Service**, and Google may lock
the account. Use an account kept for this purpose only, never one with mail you
need.

⚠️ The one-time value works **once**. If linking fails, get a fresh one before
you try again.

The dashboard's **Google Play** tile says **Linked**, **Not linked**, or
**Broken**. Broken means the linked account stopped working: link it again on
**Admin → Google Play**, where the last error is shown.

**Unlink** destroys the token ATLAS holds. It does not revoke it at Google:
remove the server's access in the account's security settings as well.

If your network restricts outbound traffic, allow `android.clients.google.com`
for the ATLAS server.

## Google Play

Search by app name, or paste an exact package name to reach an app that search
does not show.

**Download as** chooses the device Google Play serves the build for. Play gives
each device model the build that suits it (CPU type, screen density), so this
decides what you get. Choose the device type, then the manufacturer, then the
model. The choice applies to the next import from this tab only.

⚠️ **Choose one of your own models.** Your enrolled devices' exact models appear
in the list once each has checked in. Until then the only choice is **Flagship
Smartphone**, a stand-in (a Samsung Galaxy S25 Ultra), not one of your devices.
While it is chosen, a yellow banner says so. A build fetched as the stand-in can
be the wrong one for a tablet or a rugged phone.

The **Play offers** column shows the version Play offers the chosen model. It
needs one of your own models: with the stand-in chosen, it says **pick a fleet
device**. If Play cannot be reached it says **version unknown**, and search and
import still work. Play can roll a release out gradually, so a download can still
bring a different build from the one shown. A badge compares it with your
library:

- **in library**: you already have this build.
- **update · you have** *version*: Play has a newer build than your library.
- **newer in library ·** *version*: your library already has a newer build.

## TPC Plugins and TAKWERX Plugins

Both catalogs list plugins per ATAK version. Choose the **ATAK version** (on TPC
Plugins, the **Product** too) and press **Show**. The catalog is not fetched until
you do.

⚠️ **A plugin must suit the ATAK it runs in.** ATAK loads a plugin built for its
own version or an older one, and refuses one built for a newer ATAK. Look at the
catalog for the ATAK version your devices run, which is the version your policy
chooses under **ATAK Core and Plugins**.

On TPC Plugins, a product other than ATAK-CIV needs the **ATAK Flavor plugin** on
the device. Without it, the plugins install and ATAK refuses to load them. GOV
and MIL plugins also carry access and export controls; clear that in writing
before you rely on it.

On TAKWERX Plugins, each row says whose plugin it is: **TAKWERX**, or **third
party** with its author. Every download is checked against the checksum the
catalog publishes, so a row without one shows **no checksum** and cannot be
imported.

Each row says what your library already holds of that plugin:

- **imported**: you have this exact build. It replaces the **Import** button.
- **update · you have** *version*: the catalog has a newer build than your
  library.
- **newer in library ·** *version*: your library already has a newer build.

If the build in your library was made for a different ATAK version, the row says
**built for ATAK** *version* beside the pill.

## 3rd Party Repos

One search covers every repository on the tab, and each result says where it came
from. **What each source is** explains each one and whether it publishes a
checksum to check downloads against. **APKPure only answers to an exact package
name**, never an app name. It publishes no checksum, so its downloads are checked
only by reading the file.

## Hear about updates: update-check alerts

An update-check alert checks a catalog for newer builds of apps already in your
library, and emails you. Add one under **Admin → General**, in **Alerts**, at
**When an app or plugin in the library has a newer release**. Each alert watches
one catalog:

- **TAKWERX marketplace**, for one ATAK version.
- **TAK.gov (TPC) plugins**, for one ATAK edition and version. Needs the TAK.gov
  link.
- **Google Play apps**, asked as one of your own devices. Needs the Google link,
  and checks only the apps you imported from Google Play. It can be added once an
  enrolled device has checked in.

Add one of each to watch several. Each runs every so many days at the time you
choose (every day at 06:00 unless you change it); **Change schedule** on its row
changes that. **Check now** runs it straight away. Each newer build is emailed
once. If a check cannot run, you get one email saying why.

ATLAS also keeps the updates on screen until you act on them:

- On **Apps › Local apps**, an app with an update waiting shows an **update
  available** badge under its version. Click it to open the catalog where you
  import the update.
- On the dashboard, the **Updates available** card counts the apps with an update
  waiting, and lists each one in the same words as the email. Below the list it
  shows each update-check alert, its schedule, whether it is on, and its last
  result. See [The dashboard](/guides/howto/dashboard).

Each check refreshes the list. An update leaves the badge and the card as soon as
the newer build (or a later one) is in the library. Only update-check alerts fill
the list: browsing a catalog tab does not. If no update-check alert is set up, or
all are off, the card says so and links to **Admin → General**.

⚠️ After ATLAS itself is updated, the list starts empty until each alert runs its
next check. To fill it now, press **Check now** on each alert.
