# How policy stacking works

Several policies can reach one device. ATLAS **merges** them into one effective
policy rather than picking a single winner.

## The rules

- Every assignment has a **rank**. Higher rank wins. Scope (device vs group vs
  tag) only breaks a tie between equal ranks.
- Merging is **per field**, using a strategy declared by the policy type:
  - password `min_length` merges by **MAX** — the strongest requirement wins.
  - restriction flags merge **most-restrictive** — any policy denying the camera
    denies it.
  - app allowlists merge by **INTERSECT** — only packages every policy allows
    survive.
  - `kiosk_package` merges by **highest rank** — a genuine single value.
- An archived policy stops applying but is never deleted, so you can still answer
  "what did this device have in March".

## Seeing it for a device

Open a device and read **Policies reaching this device** (in rank order) and
**Effective policy** — every resolved value is traced to the policy it came from,
the strategy that chose it, and what it overrode. Conflicts (two policies setting
the same single-value field differently) are called out at the top.
