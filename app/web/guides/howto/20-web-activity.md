# Web activity

See which sites each app on a device looked up, and when. Use it to answer
questions such as "which sites did this tablet reach this morning?" or "which
devices reached this site this week?".

## What is recorded

The ATLAS filter sees every name an app looks up, in every browser and app,
and records:

- the name, for example `www.cnn.com`;
- the app that looked it up, for example Chrome or Samsung Internet;
- when it was first looked up in each few minutes;
- whether **Web Filtering** blocked it.

It does **not** record full addresses, pages, search words, page content or
what was typed. It cannot: the rest of each address is encrypted.

## Turn it on

1. Open a policy, or make one, and add a **Web Filtering** section. See
   [Build a policy](/guides/howto/building-a-policy).
2. Under **Web activity**, set **Log web activity** to **On**.
3. Assign the policy to the devices.

You do not need to block any site. **Log web activity** on its own turns the
ATLAS filter on, with nothing blocked. When any policy on a device turns it
on, it is on for that device.

The device user is told. Android shows "Device is managed", and its **Device
management** screen says that browsing data is visible to the IT admin.

## Read it

On the device page, open **Web filter** and click **Web activity**.

- Choose a **Day**, or step a day back or forward.
- **Browsers only** (the default) shows what web browsers looked up. **All
  apps** adds every other app, such as Play services and messaging.
- Names are grouped by site: `www.cnn.com` and `edition.cnn.com` are
  `cnn.com`. Click the number under **Names** to see each name.
- **First** and **Last** are times in the console's timezone.

⚠️ A page pulls in many other sites: ads, fonts, maps and analytics. So the
busiest sites are not always the sites the user opened. Look for the site
names you know first.

**Visits (estimate)** joins a site's lookups that are less than 10 minutes
apart into one visit, for example `10:02–10:40`. It is an estimate: a page left
open without use makes no lookups, and a short look can show as one time.

**Time in apps** shows how long each app was in front that day, for example
Chrome 2 h 10 min. It comes from Android's usage statistics, so it appears only
when the device user allowed ATLAS **Usage access** (Android does not let ATLAS
switch it on itself). It follows the **Apps** choice above.

**Export all web activity** downloads every stored lookup for the device, all
apps and all days, with times in UTC.

To find which devices reached a site, click **Which devices reached a site?**
on the Web activity page. Type the site, for example `example.com`. It also
finds every name under it, such as `www.example.com`.

## Who can see it

- Super admins.
- Standard admins who have the **View web activity** action, for their own
  devices only. **View devices** alone does not give it. See
  [Administrators](/guides/howto/administrators).

Every view, export and search is written to the audit log, with who did it.

## How long it is kept

30 days by default. A super admin changes this in **Admin › Location** with
**Keep web activity for (days)**. Older lookups are deleted
once a day. 0 means keep everything.

## Limits

- It works only while the ATLAS filter runs. The device page shows **Web
  activity log** with the last upload, and the filter's state above it.
- An app that uses its own encrypted DNS, outside the filter, is not seen.
- Repeat visits to the same site within a few minutes count as one entry.
- A device that is offline keeps up to 20,000 entries and sends them when it is
  back. Past that, the oldest are dropped.
