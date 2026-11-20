# Super admins and standard admins

An agency can have two kinds of administrator:

- **Super admins** can do everything, as every administrator could before.
- **Standard admins** reach only the devices, device groups and actions a super
  admin gives them.

Authentik decides **who** has each role. ATLAS stores **what** each standard
admin may reach.

## Before you start

A standard admin can sign in only when all of these are true:

1. ATLAS is version 2.3.0 or later.
2. InfraTAK is a version that admits the standard admin group.
3. After you updated InfraTAK, you pressed **Update** for this deployment on
   InfraTAK's ATLAS page. This step lets the standard admin group in. Updating
   InfraTAK alone does not.

Until then, Authentik refuses a standard admin with "Permission denied", even
when they are in the right group.

## Who is which

Roles come from groups in Authentik. InfraTAK makes the groups:

- **An agency**: super admins are in `atlas-<agency>-admins`, standard admins
  in `atlas-<agency>-standard-admins`.
- **The plain ATLAS (no agency)**: super admins are in `authentik Admins`,
  standard admins in `atlas-standard-admins`.

- Members of `authentik Admins` (global Authentik administrators) are super
  admins on every deployment.
- Someone in both groups is a super admin.
- Add or remove people in Authentik.

ATLAS reads the groups from each sign-in, so a change in Authentik applies at
that person's next sign-in.

On a server with Hardened security, every administrator needs an MFA device.
Without one, Authentik stops them at the second sign-in step.

## Set up a standard admin

1. Open **Admin → Administrators**, then **Open administrators**.
2. Find the person under **Standard admins** and press **Edit**. You can also
   type their Authentik username in **Set up by Authentik username**. This works
   before they sign in for the first time.
3. Choose the **actions** they may use, the **device groups** they look after,
   any **single devices** outside those groups, and the **templates** they may
   use.
4. Press **Save**.

A standard admin with nothing set up reaches nothing but the guides and their
own audit log.

### Actions

- **View devices**: the fleet, device pages, logs and reports for their devices.
- **Device actions**: ping, lock, locate, restart an app, collect logs, check in.
- **Wipe and remove**: wipe, retire, disenroll, delete and breach mode.
- **Edit devices**: rename, attributes, and putting their devices in their groups.
- **Enroll**: tokens and QR codes that place devices in their groups.
- **View policies**: policies whose every target is theirs.
- **Edit policies**: create and change those policies, and assign them to their devices.

The app and content library is for super admins only for now. A change there
applies to every device, not only to one admin's devices.

### Device groups and single devices

- A device group gives every device in it, including devices added later.
- A single device gives that device only. It does not give the device's groups.
- If you delete a group or a device, it leaves every scope by itself.

### Templates

Templates belong to super admins. You can share a template with a standard
admin. Then they can create a policy from it, on the **Templates** tab of
**Policies**. The new policy is theirs: they can change it and assign it to
their own devices, as with any policy they make.

- They cannot open, change, archive or delete the template itself.
- An archived template is not shared, even if it was chosen before.
- A copy keeps the template's stored passwords, such as TAK Server passwords.
- The template's page shows which standard admins may use it.

## What a standard admin sees

- **Manage** lists only their devices and groups. A device outside their scope
  shows as "not found".
- **Policies** lists only policies whose every target, each device and each
  group, is theirs. A policy with no targets yet is listed too.
- **Enroll**: a QR or token must place devices in one of their groups. A QR
  with no group is refused.
- **Reports** show only their devices. The policy report needs View policies.
  The app report is for super admins.
- **Audit log** shows what they did, and what anyone did to their devices.
- The **Dashboard** and **Admin** are for super admins. A standard admin who
  opens the dashboard goes to **Manage**.

These always stay with super admins: server settings, certificates, alerts, the
server's own enrollment token, creating, renaming and deleting device groups,
importing and exporting policies, making and changing templates, archiving,
restoring and deleting policies, and the app and content library.

A standard admin cannot see archived policies, or templates not shared with
them.

## The administrator list

**Admin → Administrators** lists who Authentik says is in each group. It reads
this with a read-only Authentik token that InfraTAK sets up. The list only
helps you set people up: it never gives anyone access.

- **Not in the standard admin group** lists stored scopes for people who left
  the group. They reach nothing. Press **Forget** to remove one.
- If the list cannot be read, the page says why. You can still set someone up
  by username.
- Global Authentik administrators are not listed.

Saving and forgetting a scope are recorded in the [audit log](/guides/howto/audit-log).

## A standard admin cannot sign in

- **"Permission denied" from Authentik**: Authentik does not let the group in
  yet. Check **Before you start** above, and that the person is in the
  standard admin group for this deployment.
- **ATLAS opens but says "your administrator role does not include this
  action"**: sign-in works. Their scope does not include that action. Edit it
  under **Admin → Administrators**.
- **ATLAS opens but shows no devices**: their scope has no device groups or
  devices yet. See **Set up a standard admin** above.

