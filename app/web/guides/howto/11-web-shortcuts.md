# Put a web link on devices

A **web shortcut** is a small app with your name and icon that opens one web
address in the device's default browser. It works on every device ATLAS manages,
and installs with no prompt.

## Make one

1. Open **Apps** → **Web shortcuts**.
2. Enter a **name** (shown under the icon, so short names fit best) and the **web
   address**, starting with `https://` or `http://`.
3. Choose the **icon**:
   - **From the website** (the default): ATLAS fetches the icon the site serves
     for itself, and shows a preview once you've entered the address. If the site
     has no icon, or only a tiny one (under 48 pixels), the shortcut shows the
     **first letter of its name** on a coloured background instead.
   - **Custom picture**: choose any picture, then drag it and use **Zoom** to crop
     it. The circle shows what round home screens show; square home screens show
     the whole square.
4. Press **Build shortcut**. ATLAS builds and signs the app and adds it to the
   Library.

## Put it on devices

Building a shortcut deploys nothing on its own. Add it to a policy's **Required
apps**, or to a **General apps** group used by a policy, like any other app.

The app then installs silently and appears in the app drawer. People can drag it
to their home screen.

## Change one

Open the shortcut and change its name, address or icon, then press **Save and
build**. ATLAS builds a new version of the same app, so devices update it in place.

A shortcut whose icon came from the website fetches it again when you save, so a
changed address brings the new site's icon. One with a custom picture keeps it
unless you choose another.

⚠️ **A policy keeps the version it names.** The shortcut's page lists the policies
that use it and marks any on an older version; open each and choose the new
version to update the devices it reaches.

## Remove one

Take it out of every policy that uses it, then press **Delete shortcut** on its
page. The page lists those policies, and refuses to delete the shortcut while any
remain.

## Good to know

- Each ATLAS server signs its shortcuts with its own key, made the first time a
  shortcut is built and kept with the server's certificates. If that key is lost,
  existing shortcuts can't be updated, only removed and built again.
- Only web addresses are accepted. Other kinds of link (`file:`, `intent:`,
  `javascript:`) are refused.
- To find a website's icon, the ATLAS server fetches the page itself. A site on
  your own network works. A public site's page can't point the server at an
  address inside your network, and neither can its redirects.
