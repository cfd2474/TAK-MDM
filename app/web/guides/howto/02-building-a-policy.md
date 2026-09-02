# Build a policy

A **policy** in ATLAS is a composite: it bundles several single-concern settings
— password, restrictions, apps, files — organised as tabs. Each tab you fill in
becomes an independent stackable rule underneath.

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

On the policy editor, use **Assign to devices** — pick devices, groups or tags and
press Apply. The whole policy applies at one rank; unticking a box unassigns.

## Templates

Save a finished policy as a **template** from its detail page. A template is a
blueprint — it is never assigned, only cloned into a new policy.
