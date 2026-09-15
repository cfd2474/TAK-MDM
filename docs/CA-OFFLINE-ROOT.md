# Taking the device CA root offline

**Why:** `SEC_AUDIT.md` **S-2**. `ca.key` on the server is a ten-year root on an
internet-facing machine. Stealing it is **permanent and unrecoverable** — the only
remedy is re-enrolling every device by hand.

After this, stealing the server gets an **intermediate** that expires and can be
revoked. The root stays somewhere an attacker who owns the box cannot reach.

⚠️ **This does not stop an attacker who is on the box from issuing certificates.**
Nothing on a single host can: the application must be able to sign unattended.
What it changes is that the damage **ends** — you revoke the intermediate, issue a
new one, and the fleet carries on. That is the whole difference, and it is worth
the fifteen minutes.

---

## Before you start

- SSH to the server, and somewhere safe to put a small file (a password manager,
  an encrypted USB stick, a printed paper backup).
- Five minutes, plus a device to test with.
- ⚠️ **Do not do this immediately before you are unreachable.** Step 5 is the one
  that proves it worked.

---

## The ceremony

### 1. Issue the intermediate

```bash
cd /root/atlas
docker compose exec -T api python -m app.cli ca-issue-intermediate
```

This signs an issuing CA with the root and prints where it went. **Nothing on any
device changes** — they chain to the root, which has not moved.

### 2. Copy the root key off the server

```bash
cat /root/atlas/pki/ca.key
```

Put the output somewhere an attacker who owns this server cannot reach. It is a
few lines of text; a password manager entry or a printed page both work.

⚠️ **Verify you can read it back before step 3.** A key you cannot restore is a
key you have destroyed — see *If you lose the root key* below.

### 3. Delete it from the server

```bash
rm /root/atlas/pki/ca.key
```

### 4. Restart and confirm ATLAS starts

```bash
docker compose restart api
docker compose logs --tail 20 api
```

ATLAS now signs with the intermediate. ⚠️ If it refuses to start saying neither
`ca.key` nor `issuing.key` is present, **step 1 did not complete** — restore
`ca.key` from step 2 and run it again. The refusal is deliberate: generating a
fresh CA at that point would invalidate every enrolled device.

### 5. Prove it, on hardware

Make a device check in, and enrol one. Both must work: the first proves existing
certificates still verify, the second proves the intermediate can issue.

---

## Every year: renewing the intermediate

The intermediate expires. ⚠️ **When it does, every device it signed stops
authenticating** — the mechanism working, not a fault, but an outage if it
surprises you. Put the expiry in a calendar the day you run the ceremony.

```bash
# put ca.key back, briefly
cd /root/atlas
docker compose exec -T api python -m app.cli ca-issue-intermediate
rm /root/atlas/pki/ca.key
docker compose restart api
```

The previous intermediate is **retired, not deleted** — moved to `pki/retired/`
and kept in the trust store, so the devices it signed keep working.

⚠️ **They keep working until the *retired intermediate* expires, not until their
own certificates do.** That is why the default is 1190 days and the rotation is
yearly: each retired intermediate outlives the last certificate it issued, so the
overlap covers the whole fleet. Rotate a short intermediate and this sentence
stops being true — see *Deciding the interval*.

---

## If the server is compromised

1. Take it off the network.
2. Rebuild it, restore the database.
3. Put the root key back and issue a **new** intermediate.
4. ⚠️ **Delete the stolen intermediate's certificate from `pki/retired/`.** This is
   the step that makes the compromise end: while its certificate is in the trust
   store, certificates the attacker minted with it still verify.
5. Every device issued by the stolen intermediate must re-enrol. Devices from
   *earlier* intermediates are unaffected.
6. Remove the root key again.

---

## If you lose the root key

You cannot issue another intermediate. ATLAS keeps working until the current one
expires, then **every device must re-enrol against a new CA**.

⚠️ This is the failure mode this design trades for. It is a real cost and it is
chosen deliberately: losing a backup is recoverable with an afternoon of work,
while a stolen root on a server is not recoverable at all. Keep **two** copies of
the root key, in different places.

---

## What the files are

| Path | What it is | On the server? |
|---|---|---|
| `pki/ca.crt` | Root certificate. The trust anchor for ever. | Yes — public |
| `pki/ca.key` | **Root private key.** Signs intermediates. | **No** — that is the point |
| `pki/issuing.crt` | Current intermediate certificate. | Yes — public |
| `pki/issuing.key` | Intermediate private key. Signs devices. | Yes — this is what an attacker gets |
| `pki/retired/*.crt` | Previous intermediates. Certificates only. | Yes — public |

Caddy is given `ca.crt` + `issuing.crt` + everything in `retired/`, concatenated.
The module does this on deploy; no Caddy configuration changes.

---

## Deciding the interval

**Devices renew their own certificates** (W174). Each one asks for a fresh
certificate well before its own expires, over the connection it already has, and
is re-issued by whichever intermediate is current. So rotating an intermediate
costs a ceremony and nothing else — the fleet rolls onto the new one by itself,
and no tablet is ever touched.

⚠️ **An earlier version of this page said the opposite**, because renewal did not
exist when it was written: it warned that a short intermediate meant re-enrolling
the fleet. That was true then and is not now. The constraint that remains is
narrower: **an intermediate must still outlive a device certificate**, or a device
that fails to renew for a while has no valid issuer to renew against.

| `--days` | Ceremonies | Note |
|---|---|---|
| 365 | Yearly | Fine, and tighter. More often than most operators will keep up. |
| **1825** (default) | Every 5 years | The balance for a deployment with one operator. |
| 3650 | Never, in practice | Matches the root; you stop getting the bounded-exposure benefit. |

### What actually bounds a compromise

**Revocation, not expiry.** Deleting a stolen intermediate's certificate from
`pki/retired/` kills every certificate it issued, immediately, at any interval.
Devices then renew against the replacement on their next check-in — which is what
makes revocation a thing you can actually do rather than a thing you plan a
weekend around. Natural expiry is only the backstop for a theft nobody noticed.

### Watch the expiry, and the console does

Admin → Certificates names the issuing certificate and its expiry, and starts
warning **180 days out**. ⚠️ That much warning is deliberate: reissuing needs the
root fetched from wherever it was put, which is not a same-afternoon task.
