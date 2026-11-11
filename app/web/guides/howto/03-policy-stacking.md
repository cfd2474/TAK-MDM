# How policy stacking works

Several policies can reach one device. ATLAS **merges** them into one effective
policy rather than picking a single winner.

## The rules

- Every assignment has a **rank**. Higher rank wins. Scope (device vs group)
  only breaks a tie between equal ranks.
- Merging is **per field**, using a strategy declared by the policy type:
  - password `min_length` merges by **MAX** — the strongest requirement wins.
  - restriction flags merge **most-restrictive** — any policy denying the camera
    denies it.
  - app allowlists merge by **INTERSECT** — only packages every policy allows
    survive.
  - `kiosk_package` merges by **highest rank** — a genuine single value.
- An archived policy stops applying, but its history is kept, so you can still
  answer "what did this device have in March". The **Archived** tab of the
  Policies page has a **Delete** that destroys a policy and every version of it.
  It works only on an archived policy, and is meant for one that never reached a
  device.

## Changing a rank

A rank is set when you assign, and can be changed afterwards where the
assignment lives:

- **On a device's page**, open **Details** on the **Policies reaching this
  device** card. A policy or profile assigned directly to that device has a rank
  box and **Save**. Only that device changes.
- **On a group's page**, every policy and profile assigned to the group has a
  rank box and **Save**. Every device in the group changes.

A policy that reaches a device through a group shows its rank on the device's
page with "via group …", but is changed on the group's page, because the change
reaches every device in the group. Devices pick up a new rank at their
next check-in.

## Seeing it for a device

Open a device. **Details** on the **Policies reaching this device** card lists
them in rank order. **Effective policy** has one card per category; its
**Details** shows every setting, the policy it came from, how it was chosen, and
what it overrode. Conflicts (two policies setting the same single-value field
differently) are called out near the top of the page.

**Export policy config**, at the top of the device page, downloads the same thing
as one CSV: one row per value, with the policy it came from, that policy's
version, scope and rank, how it was chosen, and anything it overrode. Secrets are
masked, as they are on the page.
