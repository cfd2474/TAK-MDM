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

"""What ATLAS sends mail with, and how it sends it (W194, W195).

W194 built the answer to "send through what" before anything sent anything, so
that when a notifier arrived there would be exactly one answer rather than each
caller assembling its own. W195 is that notifier, and :func:`deliver` is the
only place in this codebase that opens a connection to a mail server.

Two ways to answer it:

* **ATLAS's own SMTP settings**, edited in Admin → Email. Host, port, username,
  password, from address, STARTTLS.
* **InfraTAK's Email Relay**, inherited. Postfix on this host, relaying to
  Brevo, SMTP2GO or Mailgun.

⚠️ **Inheriting never involves a credential, and that is the point rather than a
convenience.** The relay's generated `main.cf` carries
``mynetworks = 127.0.0.0/8 [::1]/128 172.16.0.0/12`` — the Docker bridge range,
with the comment *"we set it in our block for Docker relay"* — and the module
tells operators *"Host: localhost  Port: 25  No auth required"*. So a container
on this host hands Postfix a message and Postfix authenticates onward with the
provider credential it already holds in ``/etc/postfix/sasl_passwd``. Copying
that credential into ATLAS would undo SEC_AUDIT M-5, which sealed outbound
credentials because plaintext at rest was a finding.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config import Settings

#: The setting that switches between the two answers.
INHERIT_KEY = "smtp.use_infratak_relay"


@dataclass(frozen=True)
class MailConfig:
    """Everything a sender needs, and where it came from."""

    host: str
    port: int
    username: str
    password: str
    from_address: str
    use_starttls: bool
    #: True when these describe InfraTAK's relay rather than ATLAS's own settings.
    inherited: bool

    @property
    def configured(self) -> bool:
        """Is there enough here to attempt a send at all?

        ⚠️ A host and nothing else is enough when inheriting — the relay wants no
        credential — and is *not* enough to promise delivery. "Configured" here
        means "a sender would have somewhere to connect", never "mail will
        arrive". Only a real send can make the second claim, and nothing in this
        codebase makes one yet.
        """
        return bool(self.host and self.port)


def inheriting(session: Session) -> bool:
    """Has the operator asked to use InfraTAK's relay?"""
    from app.services import settings_store

    return _truthy(settings_store.get(session, INHERIT_KEY, ""))


def inherited(settings: Settings) -> MailConfig:
    """InfraTAK's relay, as this container would reach it.

    ⚠️ Username and password are empty by construction, not by omission. There
    is no path by which they could be filled: the relay does not want them, and
    the provider credential is Postfix's to hold.
    """
    return MailConfig(
        host=settings.infratak_mail_host.strip(),
        port=settings.infratak_mail_port,
        username="",
        password="",
        from_address=settings.infratak_mail_from.strip(),
        # ⚠️ No STARTTLS on this hop, and that is correct rather than lax. It is
        # a connection to Postfix on the same host across the Docker bridge, and
        # Postfix does TLS onward to the provider (`smtp_tls_security_level =
        # may`, `smtp_use_tls = yes`). Demanding it here would fail against a
        # relay that offers none, for no gain on a hop that never leaves the box.
        use_starttls=False,
        inherited=True,
    )


def own(session: Session) -> MailConfig:
    """ATLAS's own SMTP settings, as the operator entered them."""
    from app.services import settings_store

    values = settings_store.group_values(session, "smtp")
    return MailConfig(
        host=(values.get("smtp.host") or "").strip(),
        port=_port(values.get("smtp.port")),
        username=(values.get("smtp.username") or "").strip(),
        password=values.get("smtp.password") or "",
        from_address=(values.get("smtp.from_address") or "").strip(),
        use_starttls=_truthy(values.get("smtp.use_tls")),
        inherited=False,
    )


def effective_config(session: Session, settings: Settings) -> MailConfig:
    """The one answer to "what would ATLAS send with".

    ⚠️ **One function, so a future notifier has no decision to make.** The
    alternative is every caller reading the toggle and assembling its own
    config, which is how two senders come to disagree about whether a deployment
    is inheriting — and the visible symptom would be alerts arriving from two
    different addresses, or half of them not arriving at all.
    """
    return inherited(settings) if inheriting(session) else own(session)


#: How long the relay gets to say hello.
#:
#: ⚠️ Short on purpose. This runs while an operator waits on a button, and a
#: relay that is not there usually fails instantly (connection refused) — the
#: case this bounds is a host that swallows the packet, where the honest answer
#: after three seconds is "it did not answer", not a spinner.
PROBE_TIMEOUT_SECONDS = 3.0


@dataclass(frozen=True)
class ProbeResult:
    """What happened when ATLAS opened a socket to the relay."""

    reachable: bool
    detail: str


def probe(config: MailConfig) -> ProbeResult:
    """Open a socket to the relay and read its greeting. Sends nothing.

    ⚠️ **This proves the socket answers and speaks SMTP. It does not prove
    mail will arrive**, and the button must not be worded as though it did. The
    relay can greet ATLAS happily and still be refused by the provider, reject
    the sender domain, or drop the message — none of which is visible from here.

    ⚠️ **Deliberately a raw socket, not `smtplib`.** Two reasons, and the
    second is the important one. A greeting is all that is wanted, so a mail
    library is more machinery than the job needs; and `import smtplib` appearing
    in this codebase is what `test_nothing_in_the_codebase_sends_mail_yet`
    watches for. A probe that tripped that test would have blurred the line this
    whole module is careful about — between reaching a relay and sending
    through it.

    ⚠️ **No SSRF guard here, unlike `app.security.outbound`**, and that is a
    decision rather than an omission. That module refuses loopback and
    link-local *even when an administrator configures them deliberately*,
    because no geocoder lives there. This target is the opposite: the relay is
    meant to be on this host, reached across the Docker bridge, and refusing
    private addresses would refuse the only address that can ever be right. What
    keeps it safe is that the destination comes from settings only an
    administrator or the InfraTAK module can write, and the caller is already an
    authenticated administrator — so it grants nobody anything they did not
    already have.
    """
    import socket

    if not config.configured:
        return ProbeResult(False, "no relay address is configured")

    try:
        with socket.create_connection(
            (config.host, config.port), timeout=PROBE_TIMEOUT_SECONDS
        ) as sock:
            sock.settimeout(PROBE_TIMEOUT_SECONDS)
            greeting = sock.recv(512).decode("utf-8", "replace").strip()
            # Polite rather than necessary: a bare disconnect leaves a logged
            # "lost connection after CONNECT" in the relay's mail log for every
            # press of this button.
            try:
                sock.sendall(b"QUIT\r\n")
            except OSError:
                pass
    except OSError as exc:
        return ProbeResult(False, f"{config.host}:{config.port} — {exc.strerror or exc}")

    if not greeting.startswith("220"):
        # Something is listening and it is not a mail server. Worth telling
        # apart from silence: the fix is a different port, not a deployment.
        return ProbeResult(
            False,
            f"{config.host}:{config.port} answered, but not as a mail server: "
            f"{greeting[:120] or 'it said nothing'}",
        )
    return ProbeResult(True, greeting[:200])


# --------------------------------------------------------------------------- #
# Sending
# --------------------------------------------------------------------------- #


class SendFailed(Exception):
    """The message was not handed over, and the caller must not pretend it was."""


#: How long a send may take before it is a failure.
#:
#: ⚠️ This runs in a background thread, so a hang costs no operator a page —
#: but an unbounded one costs the *sweep*, and every alert behind it waits on a
#: mail server that is never going to answer.
SEND_TIMEOUT_SECONDS = 20.0


def deliver(
    config: MailConfig, recipients: list[str], subject: str, body: str
) -> None:
    """Hand one message to the mail server. Raises :class:`SendFailed` if not.

    ⚠️ **The only `smtplib` in this codebase, deliberately.** Everything else
    asks :func:`effective_config` and hands the result here, so "what does this
    deployment send through" has one answer rather than one per caller — and a
    deployment inheriting InfraTAK's relay cannot end up half-inheriting it.

    ⚠️ **Raising rather than returning False.** A caller that forgets to
    check a boolean marks the alert sent and loses it; a caller that forgets to
    catch an exception fails loudly in a log. Given the failure being guarded
    against is "nobody was told and nobody knows", loud is the right default.
    """
    import smtplib
    from email.message import EmailMessage

    if not config.configured:
        raise SendFailed("no mail server is configured")
    if not recipients:
        raise SendFailed("there is nobody to send to")

    message = EmailMessage()
    # ⚠️ A From of last resort rather than a refusal. An operator inheriting
    # InfraTAK's relay may have no from-address pushed yet, and Postfix rewrites
    # the envelope through `smtp_generic_maps` regardless — so refusing here
    # would withhold an alert over a header the relay was going to replace.
    message["From"] = config.from_address or f"atlas@{config.host}"
    message["To"] = ", ".join(recipients)
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(
            config.host, config.port, timeout=SEND_TIMEOUT_SECONDS
        ) as server:
            if config.use_starttls:
                server.starttls()
            if config.username:
                server.login(config.username, config.password)
            server.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        # ⚠️ The address is named in the failure. "Connection refused" with no
        # host is the least actionable error a mail problem can produce, and the
        # host here may be one the operator never typed — it can come from
        # InfraTAK's relay settings.
        raise SendFailed(f"{config.host}:{config.port} — {exc}") from exc


def _truthy(value: str | None) -> bool:
    """How a stored `bool` field reads as a decision.

    The settings store keeps everything as text. The console writes exactly
    `"true"` when ticked and `""` when not — the checkbox carries
    `value="true"` and `admin.html` renders it back with `val == 'true'`.

    ⚠️ The other spellings are tolerated for a value that did **not** come
    from the console: a row set by hand in the database, or by a future writer
    that reasonably assumes a checkbox submits "on". They are not what the form
    produces, and a test pins the form's own value so that this staying
    generous never becomes the reason the two drift apart.
    """
    return (value or "").strip().lower() in {"1", "true", "on", "yes"}


def _port(value: str | None) -> int:
    """A port number, or 0 when there is not one.

    ⚠️ Zero rather than a guess at 25 or 587. Those are different answers for
    different deployments, and inventing one here would make an unconfigured
    deployment look configured — which `MailConfig.configured` would then
    report, and a sender would act on.
    """
    try:
        port = int((value or "").strip())
    except ValueError:
        return 0
    return port if 0 < port < 65536 else 0
