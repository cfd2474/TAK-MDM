# Build a policy

What **New Policy** builds is a **profile**: a composite that bundles several
single-concern settings — password, restrictions, apps, files — as categories.
Each category you fill in becomes an independent stackable **section**
underneath, named `<profile> · <category>`.

⚠️ **A section is assigned through its profile, never on its own.** Sections
appear in the Policies list because they are real policies, but assigning one
directly is refused — assign the profile and every section it owns applies
together, at one rank.

## Steps

1. On the **Policies** page, press **New Policy**, then **Create from scratch**.
2. Name the policy.
3. Work down the category rail on the left. For each category you want to set,
   edit its JSON spec. Only the fields you set are stored, so a narrow policy
   stacks onto a broad one without blanking it.
4. Categories shown as *"not available yet"* need backend support that has not
   shipped — they will light up in place when it does.
5. Press **Create policy**. You land on the editor, where each category is its own
   save form (editing one publishes a new version of just that section).

## Assigning it

On the policy editor, use **Assign to devices** — pick devices or groups and
press Apply. The whole thing applies at one rank; unticking a box unassigns.

You can also work from the other end: a group's page has an **Assign to this
group** control listing both profiles and standalone policies.

## Templates

Save a finished policy as a **template** from its detail page. A template is a
blueprint — it is never assigned, only cloned into a new policy.

## Holding it back, or scheduling it

A policy can be complete — content, devices, groups — and still not be in force.
Every policy is in one of three states, chosen under **Deployment** when you
create it and changeable afterwards from its page:

| State | What happens |
|---|---|
| **Live** | In force now, on everything it targets. This is the default and what every existing policy is. |
| **Hold** | Reaches no device until you come back and deploy it. Targets can be set up freely in the meantime. |
| **Deploy at** | Reaches devices at the date and time you give, on its own. |

⚠️ **Decide it when you create the policy, not after.** A brand-new policy has no
targets, so creating it live is harmless in itself — but you then have to
remember to hold it *before* ticking the first device, and forgetting sends it
to the fleet on the spot.

A held or scheduled policy is marked in the Policies list. A live one is not:
almost everything is live, and a badge on every row is a badge nobody reads.

### The time you type is your time

Times are in the console timezone, set in **Admin → General**. When you save a
schedule the console confirms it back in **both** that zone and UTC — for
example *"deploys at Wed 16 Dec 2026, 08:00 PST (Wed 16 Dec 2026, 16:00 UTC)"*.

⚠️ **Read that line.** It is the only place a timezone set wrongly ever shows
itself: the form redisplays what you typed and the list shows the local form of
it, so both agree with each other and with a wrong zone. A deployment eight
hours out lands on field devices in the middle of the night.

A time that has already passed is accepted rather than refused — it is how
"deploy now" comes out of a form that only offers a date — and the confirmation
says so.

### If the server is off at the appointed hour

Nothing is lost. The schedule is not a job queued to run at a moment; it is a
fact the system reads every time it works out what a device should have. A
server that was down at 08:00 puts the policy in force on the way back up, and a
device that checks in before anything has swept still gets it.

## Taking an app back when the policy stops asking for it

Each required app has an **Uninstall if withdrawn** tick. With it on, the device
removes that app once no policy requires it any more — when you unassign the
policy, delete it, or simply take the app out of its list.

⚠️ **Uninstalling destroys the app's data**, which is why this is off by default
and set per app rather than per policy. A network profile can be removed and
re-added for free; an app cannot.

⚠️ **Ticking it does not uninstall anything.** The app is still required, so it
stays. The tick only says what happens the day nothing requires it.

The device does the deciding, because only the device knows what it has. It
claims an app the first time it sees one that is required, ticked and installed
— including apps installed long before you turned this on, so the setting works
on tablets already in the field.

Two apps are never removed this way: the ATLAS agent, which Android refuses to
uninstall anyway, and the ATLAS launcher, which the kiosk policy removes when it
is no longer needed.

⚠️ An app that ships with the device cannot be uninstalled at all. The device
reports that it could not remove it, on every check-in, rather than going quiet
about an app that is still there.
