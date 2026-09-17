# Copyright 2026 TAK-Solutions LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Application configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings, overridable by environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="TAKMDM_", extra="ignore")

    database_url: str = "postgresql+psycopg://takmdm:takmdm@localhost:5432/takmdm"
    sql_echo: bool = False

    # Base URL devices use to reach this server. Goes into provisioning payloads.
    server_url: str = "https://mdm.example.org"

    # --- Artifact storage ----------------------------------------------------
    artifact_dir: Path = Path("artifacts")
    #: Where the APKs shipped with a release are mounted (`./dist:/seed:ro`).
    #:
    #: Read at start by the seeder, and on every Admin render by
    #: `packages.shipped_but_refused`, which is what turns a refused APK from a
    #: line in `docker logs` into something an operator can see (W188).
    seed_dir: Path = Path("/seed")
    # 2 GiB. XAPKs with OBB payloads get large; nginx has a matching limit.
    max_upload_bytes: int = 2 * 1024 * 1024 * 1024
    # ⚠️ Deliberately not inside `artifact_dir` (W97). That directory is addressed
    # by digest and swept; a 59 MB F-Droid index living there would be an
    # unreferenced blob to anything that tidies it up. Cached data that can be
    # re-fetched belongs somewhere losing it costs nothing.
    cache_dir: Path = Path("cache")
    # ⚠️ Parsing the repository indexes at boot so the first search is not the
    # one that pays for it (W103). Off in tests: a background thread that fetches
    # 184 MB from F-Droid would make the suite depend on a third party being up,
    # and would hammer them on every run.
    warm_indexes: bool = True
    #: Whether the daily location-retention sweep runs (W106 C5). Off in tests,
    #: which is not a nicety: the sweeper issues DELETEs, and a background thread
    #: reading the real settings during a test run would aim them at a real table.
    purge_location_history: bool = True
    # --- InfraTAK's email relay (W194) ---------------------------------------
    #
    # ⚠️ **Pushed in by the InfraTAK module, never edited in ATLAS.** They
    # describe somebody else's Postfix, so an ATLAS-side editor would be a
    # second place to get them wrong. The operator's own SMTP settings are the
    # editable ones; these are what inheriting means.
    #
    # ⚠️ **No username and no password, and there never will be.** The relay
    # accepts mail from the Docker bridge unauthenticated — its generated
    # `main.cf` says `mynetworks = 127.0.0.0/8 [::1]/128 172.16.0.0/12` for
    # exactly that reason — and the provider credential stays in
    # `/etc/postfix/sasl_passwd` where Postfix uses it. Copying it here would
    # undo SEC_AUDIT M-5.
    #:
    #: The host, as reachable from inside this container. `host.docker.internal`
    #: is mapped to the gateway in `docker-compose.yml`; an override exists
    #: because a deployment may put the relay somewhere else entirely.
    infratak_mail_host: str = "host.docker.internal"
    infratak_mail_port: int = 25

    @field_validator("infratak_mail_host", "infratak_mail_port", mode="before")
    @classmethod
    def _blank_keeps_the_default(cls, value, info):
        """An empty environment variable means "nobody has said", not "invalid".

        ⚠️ **This is `_blank_is_unset` above, walked into a second time.** Its
        docstring already says it: compose substitutes `${VAR:-}` to an empty
        string, pydantic rejects `""` for an `int`, and the container refuses to
        start. Naming these in `docker-compose.yml` — which is *required*, or the
        module writes a value nothing reads — is therefore enough on its own to
        stop every deployment booting, before the relay is configured at all.
        Caught by trying it rather than by reading the comment one screen up.

        The default is returned rather than `None` because these have real
        defaults: `host.docker.internal` is where the relay is on any ordinary
        InfraTAK box, and 25 is the port its Postfix listens on.
        """
        if isinstance(value, str) and not value.strip():
            return cls.model_fields[info.field_name].default
        return value
    #: What recipients will see. Display and sender only — Postfix rewrites the
    #: envelope through `smtp_generic_maps` regardless, so a blank value costs
    #: correctness nothing and only leaves the console with less to show.
    infratak_mail_from: str = ""

    #: How often to look for a scheduled deployment that has come due, in
    #: seconds. 0 turns the sweeper off, which is what the suite uses.
    #:
    #: ⚠️ **This is a promptness dial, never a correctness one** (W191). The
    #: resolver reads the clock itself and the cache carries an expiry, so a
    #: deployment lands on a device's next read whatever this says. What the
    #: sweeper buys is the wake: devices parked on a long poll hear about it now
    #: rather than within one poll slice.
    #:
    #: A minute, because the console offers minute precision. Sweeping faster
    #: would be a query a second to shave off time nobody can express.
    deployment_sweep_seconds: int = 60

    #: How often to look for the alert conditions that have become true, in
    #: seconds. 0 turns the sweep off, which is what the suite uses.
    #:
    #: ⚠️ Five minutes rather than the deployment sweep's one. Nothing here
    #: is time-critical — the shortest threshold an operator may set is fifteen
    #: minutes — and this pass reads every device and every rule, where the
    #: deployment sweep reads one indexed column.
    alert_sweep_seconds: int = 300

    # --- Device identity PKI -------------------------------------------------
    pki_dir: Path = Path("pki")
    ca_common_name: str = "TAK-MDM Device CA"
    ca_validity_days: int = 3650
    #: How long a device certificate lasts.
    #:
    #: 90 days, down from 825 (W186). ⚠️ **The short life is the control**: a
    #: device credential copied off a tablet stops working on its own, without
    #: anybody noticing the theft or reaching for revocation. 825 days made that
    #: promise meaningless.
    #:
    #: ⚠️ **This is only safe because devices renew themselves** (W174). Before
    #: renewal existed, shortening this meant re-enrolling the fleet by hand every
    #: time it elapsed. An agent older than 0.70.0 does not renew, so a deployment
    #: that somehow still had one would factory-reset that device in 90 days —
    #: which is why the change waited for a fleet where no such agent exists.
    device_cert_validity_days: int = 90
    #: How close to expiry a device should renew.
    #:
    #: The server states it and the agent obeys, so the policy can change without
    #: an agent release — which matters because the fleet updates on its own
    #: schedule and a hardcoded window could not be corrected on a device that had
    #: stopped checking in often enough to be corrected.
    #:
    #: ⚠️ Must stay comfortably **shorter** than `device_cert_validity_days`. At
    #: or above it every certificate is born already due for renewal, and the
    #: fleet renews on every check-in for ever. `tests/test_certificate_renewal.py`
    #: asserts the gap rather than leaving it to whoever next edits either number.
    device_cert_renew_within_days: int = 30

    # mTLS is terminated at the reverse proxy, which forwards the verified client
    # certificate in this header. The app re-verifies chain, validity, and
    # revocation, but possession of the private key is proven by the TLS handshake
    # at the proxy — so this header MUST be stripped from inbound requests by that
    # proxy, and the app must never be exposed directly to the internet.
    client_cert_header: str = "x-ssl-client-cert"

    # Whether provisioning tells the agent to pin a CA for the *server's* TLS.
    #
    # None means decide by looking: pin when this deployment generated its own
    # self-signed certificate, and say nothing when it did not. That is right for
    # a standalone install and wrong the moment a real proxy with a
    # publicly-issued certificate is in front, because `pki/server.crt` can still
    # be sitting there from the init step and would pin a CA nobody serves.
    #
    # ⚠️ **False is how a fronted deployment says so out loud** (W143). An
    # InfraTAK module puts Caddy in front with a public certificate; a QR that
    # pinned ATLAS's own CA would make every device fail the TLS handshake, at
    # provisioning time, with nothing on the device to explain it. Leaving that
    # to the absence of a file made the failure depend on a build step nobody
    # reads.
    include_server_ca: bool | None = None

    @field_validator("include_server_ca", mode="before")
    @classmethod
    def _blank_is_unset(cls, value):
        """An empty environment variable means "nobody chose", not "invalid".

        ⚠️ Compose substitutes `${TAKMDM_INCLUDE_SERVER_CA:-}` to an empty
        string when the deployment has no opinion, and pydantic rejects `""` for
        `bool | None` — so the container refuses to start, which is a very loud
        failure for a variable whose whole point is to be optional.
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value

    # --- Admin authentication (Authentik forward auth) -----------------------
    # "disabled" for local development, "forward_auth" behind an Authentik proxy
    # provider. There is deliberately no middle setting.
    admin_auth_mode: str = "disabled"
    # Membership required to administer. Blank means any authenticated user, which
    # is only sensible if Authentik already restricts the application.
    admin_group: str = "takmdm-admins"
    #: Shared secret Caddy injects as `X-Infratak-Proxy-Auth` on requests that
    #: passed `forward_auth` (`SEC_AUDIT.md` S-1).
    #:
    #: ⚠️ **Blank means the check is off, and that is deliberate.** The header is
    #: only present where the reverse proxy emits it; a deployment whose proxy
    #: does not would reject every administrator, with the console as the thing
    #: you would use to fix it. Fail-open when unconfigured, fail-closed when
    #: configured — the same shape as `trusted_proxies`.
    #:
    #: What it buys is the half `trusted_proxies` provably cannot: Caddy runs on
    #: the host and reaches the container through the bridge gateway, and so does
    #: every other process on that host. A peer address cannot separate them; a
    #: secret the proxy holds can.
    proxy_auth_secret: str = ""
    #: Header carrying it. Named by infra-TAK, not by us.
    proxy_auth_header: str = "x-infratak-proxy-auth"

    # Headers an Authentik proxy provider sets. The proxy MUST strip inbound copies
    # of these, exactly as it must for the mTLS client-certificate header.
    admin_user_header: str = "x-authentik-username"
    admin_groups_header: str = "x-authentik-groups"
    admin_email_header: str = "x-authentik-email"
    admin_name_header: str = "x-authentik-name"

    # The console's own public origin, e.g. "https://atlas.example.org". Used to
    # reject unsafe requests a browser made from somewhere else.
    #
    # Configured explicitly rather than inferred from the request's Host header:
    # behind a proxy that header is whatever the proxy was told, and building a
    # security check on a value the client can influence is the R7 mistake. Blank
    # disables the origin check; the CSRF token still applies.
    console_origin: str = ""

    #: Addresses the administrative surface may be reached from.
    #:
    #: Comma-separated IPs or CIDRs, matched against the connecting peer. Empty
    #: means **not enforced** and is warned about at startup; the literal `any`
    #: means deliberately not enforced and is warned about more quietly.
    #:
    #: ⚠️ **Empty cannot mean "refuse to start", however much it should.** The
    #: InfraTAK module rewrites `.env` on deploy but *not* on update, so a release
    #: that refused to boot without this would brick every existing box on the
    #: next routine update — a far worse outcome than the gap it closes. It warns
    #: instead, and the module writes the value.
    #:
    #: ⚠️ This is a **network** control and cannot tell Caddy from anything else
    #: on the same host: both arrive from the bridge gateway. It closes the
    #: accidental-exposure case (the port republished on 0.0.0.0 and reached from
    #: elsewhere), not host-local forgery. See SEC_AUDIT.md S-1.
    trusted_proxies: str = ""

    # --- Enrollment ----------------------------------------------------------
    enrollment_token_ttl_hours: int = 168  # 7 days

    # How long a QR minted from the persistent enrollment token stays scannable.
    # Deliberately short: this is the only form of the token ever displayed, so a
    # leaked QR image (a photo, a screenshot left on a shared screen) is bounded by
    # this window rather than by the persistent token's own lifetime.
    enrollment_qr_ttl_seconds: int = 900  # 15 minutes

    # --- Check-in ------------------------------------------------------------
    # WorkManager's periodic floor is 15 minutes, so anything lower is wishful.
    checkin_interval_seconds: int = 900
    # Spread wake-ups so a fleet that lost power together does not return as a
    # thundering herd.
    checkin_jitter_ratio: float = 0.2

    # --- Agent APK, for provisioning payloads --------------------------------
    agent_package_name: str = "com.taksolutions.atlasmdm"
    # Must match the receiver the APK actually declares. The leading dot expands
    # against the package root, so the `.admin` segment is required — omitting it
    # points at a class that does not exist, and Android reports only "something
    # went wrong" after installing. Validated against the uploaded APK at QR
    # generation so it cannot drift again.
    agent_admin_receiver: str = "com.taksolutions.atlasmdm/.admin.MdmDeviceAdminReceiver"
    agent_apk_url: str = "https://mdm.example.org/static/agent.apk"
    # base64url SHA-256 of the agent's signing certificate. Android refuses to
    # provision if this does not match the downloaded APK.
    agent_signature_checksum: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
