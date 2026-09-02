# Server-Side TAK.gov EUD Link

> ## ✅ Verified against the live service — 2026-09-02
>
> ATLAS linked a real account (`michael.leckliter@coronaca.gov`), pulled **86
> ATAK-CIV 5.8.0 plugins**, and downloaded one with a matching SHA-256. The
> premise of this document holds: a headless server can complete "Link EUD" and
> hold the credential.
>
> **Four corrections, each of which cost a failure to find:**
>
> 1. **The verification URI below is wrong.** §1 and §Flow say
>    `https://tak.gov/register-device`. The realm actually returns
>    `https://auth.tak.gov/auth/realms/TPC/device`, and a code entered at the
>    documented page does not work. Always use the `verification_uri` the server
>    sends; never hardcode one.
> 2. **`eud_api` requires HTTP/2.** Over HTTP/1.1 it answers **`421 HTTP/2
>    Required`**. `auth.tak.gov` does *not* care, so the link succeeds and only
>    the catalog fails — which reads as a permissions problem and is not one.
>    With `httpx` this means `http2=True` and the `h2` package.
> 3. **The code TTL is ~3 minutes, not the RFC default of 10.** Observed
>    `expires_in` of 180 s. Plan the admin experience around that.
> 4. **§4's field table is missing `identifier`** (e.g. `wave-5-8-0-civ`), which
>    is on every row and is the key both `apk_url` and `icon_url` are built from.
>    `os_requirement` also arrives as an **integer**, not a string.
>
> Everything else in §4 matched field-for-field. 10 of the 86 rows have no
> `tak_prerequisite` — those are standalone apps rather than plugins, not a
> parsing fault.

**Question:** Can a server application use ATAK's "Link EUD" process to get direct access to the TAK.gov plugin repository, and can it be driven from a webservice (an MDM)?

**Answer:** Yes. "Link EUD" is not device-bound magic — it is a stock **OAuth 2.0 Device Authorization Grant (RFC 8628)** against TAK.gov's Keycloak. Nothing in the flow requires Android or a physical device. A headless server can complete it and hold the credential indefinitely.

There is a working reference implementation in the wild: OpenTAKServer does exactly this in `opentakserver/blueprints/ots_api/tak_gov_link_api.py`.

---

## 1. The protocol

Confirmed live against the realm's discovery document at
`https://auth.tak.gov/auth/realms/TPC/.well-known/openid-configuration`.

| | |
|---|---|
| IdP | Keycloak, realm `TPC` at `auth.tak.gov` |
| `client_id` | `tak-gov-eud` — **public client, no secret** |
| Device endpoint | `/auth/realms/TPC/protocol/openid-connect/auth/device` |
| Token endpoint | `/auth/realms/TPC/protocol/openid-connect/token` |
| Scope | `openid offline_access email profile` |
| User verification URI | `https://tak.gov/register-device` |
| Resource API | `https://tak.gov/eud_api/software/v1/plugins` |

`offline_access` is the load-bearing scope. It yields an *offline* refresh token, which is what lets your server keep pulling plugins long after the admin closed the browser tab.

### Flow

1. **POST** to the device endpoint → receive `device_code` + `user_code` (~3 min TTL), plus `verification_uri`, `verification_uri_complete`, and `interval`.
2. **Admin** enters the `user_code` at `https://tak.gov/register-device` while signed in to TAK.gov. (`verification_uri_complete` embeds the code — render it as a QR for a better admin experience.)
3. **Poll** the token endpoint with `grant_type=urn:ietf:params:oauth:grant-type:device_code` → `access_token` (short, ~3 min) plus a long-lived `refresh_token`.

---

## 2. Three things that will bite you

### 2.1 Keycloak rotates the refresh token on every refresh

Each refresh response contains a **new** `refresh_token` and invalidates the old one. If two workers refresh concurrently, or you crash between "received new token" and "persisted new token," the link is dead and a human has to re-enter a code at TAK.gov.

In a multi-tenant MDM this is your number one outage source.

- Serialize refreshes per tenant behind a lock.
- Persist the new token **before** using it.
- Keep the previous token as a one-step fallback.

### 2.2 Do not fetch a new access token per request

OpenTAKServer calls `get_new_access_token()` at the top of every handler, which burns a rotation each time. Cache the access token until roughly 30 seconds before expiry.

### 2.3 OpenTAKServer does not actually poll

It makes the admin click "Link Account" after entering the code, and it ignores the `authorization_pending` and `slow_down` responses. For an MDM you want real RFC 8628 polling.

---

## 3. Implementation

```python
import time, hashlib, httpx

REALM = "https://auth.tak.gov/auth/realms/TPC/protocol/openid-connect"
CLIENT_ID = "tak-gov-eud"
UA = {"User-Agent": "YourMDM/1.0"}   # tak.gov is picky about a missing UA


def start_link(tenant_id):
    """Step 1. Show user_code (or a QR of verification_uri_complete) to the admin."""
    r = httpx.post(f"{REALM}/auth/device", headers=UA, data={
        "client_id": CLIENT_ID,
        "scope": "openid offline_access email profile",
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
    })
    r.raise_for_status()
    d = r.json()
    # persist device_code against tenant_id; surface user_code + verification_uri_complete
    return d


def poll_for_token(device_code, interval, expires_in):
    """Step 2. RFC 8628 polling — handles the two soft-error states."""
    deadline = time.monotonic() + expires_in
    while time.monotonic() < deadline:
        time.sleep(interval)
        r = httpx.post(f"{REALM}/token", headers=UA, data={
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": device_code,
            "client_id": CLIENT_ID,
        })
        if r.status_code == 200:
            return r.json()          # access_token + offline refresh_token
        err = r.json().get("error")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            interval += 5
            continue
        raise RuntimeError(f"link failed: {err}")   # access_denied / expired_token
    raise TimeoutError("user never entered the code")


def access_token(tenant):
    """Rotation-safe refresh. MUST hold a per-tenant lock across this whole call."""
    if tenant.access_token and tenant.access_expires_at > time.time() + 30:
        return tenant.access_token
    r = httpx.post(f"{REALM}/token", headers=UA, data={
        "client_id": CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": tenant.refresh_token,
    })
    r.raise_for_status()
    d = r.json()
    tenant.save(refresh_token=d["refresh_token"],          # rotated — persist first
                access_token=d["access_token"],
                access_expires_at=time.time() + d["expires_in"])
    return d["access_token"]
```

### Catalog pull

```python
def list_plugins(tenant, product="ATAK-CIV", product_version="5.5.0"):
    return httpx.get("https://tak.gov/eud_api/software/v1/plugins",
                     params={"product": product, "product_version": product_version},
                     headers={**UA, "Authorization": f"Bearer {access_token(tenant)}"}).json()


def fetch_apk(tenant, plugin):
    r = httpx.get(plugin["apk_url"], follow_redirects=True,   # redirects to presigned storage
                  headers={**UA, "Authorization": f"Bearer {access_token(tenant)}"})
    r.raise_for_status()
    if hashlib.sha256(r.content).hexdigest().lower() != plugin["apk_hash"].lower():
        raise ValueError("APK hash mismatch — do not install")
    return r.content
```

---

## 4. Catalog surface

`product` is one of `ATAK-CIV`, `ATAK-GOV`, `ATAK-MIL`.
`product_version` currently ranges `5.0.0` through `5.8.0`.

Each plugin object carries enough to populate an MDM app catalog without unpacking the APK:

| Field | Use |
|---|---|
| `package_name` | Android package id — your catalog primary key |
| `display_name` | Human-facing name |
| `version` / `revision_code` | versionName / versionCode; match on `revision_code` |
| `apk_url` | Download; redirects to presigned storage |
| `apk_hash` | SHA-256; verify before install |
| `apk_size_bytes` | Size |
| `apk_type` | Plugin vs. app |
| `os_requirement` | minSdkVersion |
| `tak_prerequisite` | Required ATAK plugin-API version |
| `icon_url` | Bearer-authenticated; some plugins 404 here |
| `platform` | Android / etc. |
| `description` | Catalog copy |

---

## 5. Getting plugins onto devices

Two paths. For an MDM, prefer **A**.

### A. MDM-native (recommended)

Treat `eud_api` purely as an **ingest source** into your existing enterprise app catalog, then force-install via your Android Enterprise DPC. You keep your own approval gate, staged rollout, and rollback. Match on `package_name` + `revision_code`.

### B. ATAK-native update repo

Serve a `product.infz` so ATAK's own App Mgmt UI sees your catalog. It is a ZIP containing `product.inf` (headerless CSV) plus icon PNGs. Column order, per OpenTAKServer:

```
platform, plugin_type, package_name, name, version, revision_code,
file_name, icon_filename, description, apk_hash, os_requirement,
tak_prereq, file_size
```

- ATAK **>= 5.5.0** asks for version-scoped repos at `/<atak_version>/product.infz`, plus a `repositories.inf` that is just a newline-delimited list of versions.
- ATAK **<= 5.4.0** uses a single flat repo — which is why OpenTAKServer nulls `atak_version` below 5.5.
- Push the repo URL to devices as ATAK managed configuration rather than making users type it.

Path B is more work and more version-coupling. Its one real advantage is that plugin install stays inside ATAK's own UX. If you already have silent install, skip it.

---

## 6. Before you ship

Two non-technical constraints worth settling early, because they shape the product.

### The token is a person's identity, not a service account

You inherit exactly the entitlements of whoever linked — `list_plugins` only returns what that account is permitted to see.

- One link per tenant, performed by that customer's own TAK.gov admin.
- **Never** embed a shared credential in your product.
- Store the offline refresh token encrypted at rest under a per-tenant key (envelope / KMS). It is a durable bearer credential to someone's TAK.gov account, and it does not idle out.

### Redistribution rights are narrower than the API surface suggests

ATAK-CIV object code carries a distribution grant. ATAK-MIL explicitly does not, and GOV/MIL plugins carry access and export controls. An MDM that mirrors MIL plugins into its own catalog and pushes them to arbitrary enrolled devices is the shape of thing that needs a written OK.

Send TAK PC a note describing the architecture before building the MIL path. CIV-only is uncontroversial and can ship while that is pending.

### Operational note

`eud_api` is undocumented and effectively unversioned in practice. Put it behind a thin adapter with contract tests so a field rename does not take down enrollment.

---

## Sources

- [OpenTAKServer — TAK.gov link implementation](https://github.com/brian7704/OpenTAKServer/blob/master/opentakserver/blueprints/ots_api/tak_gov_link_api.py)
- [OpenTAKServer — package / product.infz API](https://github.com/brian7704/OpenTAKServer/blob/master/opentakserver/blueprints/ots_api/package_api.py)
- [OpenTAKServer — Link TAK.gov Account docs](https://docs.opentakserver.io/link_account.html)
- [TAK.gov FAQ](https://tak.gov/faq)
- [TAK.gov — Our Process / license terms](https://tak.gov/pages/our-process)
- [ATAK-CIV (TAK Product Center)](https://github.com/TAK-Product-Center/atak-civ)
