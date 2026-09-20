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

"""Internal certificate authority for device identity.

Devices generate a keypair inside the Android Keystore (StrongBox on Samsung),
send a CSR, and receive a client certificate. The private key never leaves
hardware, so device identity cannot be copied off a device the way a bearer token
can — and there is no token to expire while a device is dark for a month (D10).

EC P-256 throughout: natively supported by Android Keystore and StrongBox, and far
cheaper than RSA on the handshake every check-in performs.

**The CSR's subject is attacker-controlled and is never trusted.** Only the public
key is taken from it; the server builds the subject itself from the device record it
just created. A device that asks to be called something else is simply ignored.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from app.security import keyfiles
from typing import Sequence

logger = logging.getLogger(__name__)


class CertificateError(ValueError):
    """Raised for a malformed CSR or a certificate that fails verification."""


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _aware(value: dt.datetime) -> dt.datetime:
    """Normalize x509's naive UTC timestamps for comparison."""
    return value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)


@dataclass(frozen=True)
class IssuedCertificate:
    certificate: x509.Certificate

    @property
    def serial_hex(self) -> str:
        return format(self.certificate.serial_number, "x")

    @property
    def not_valid_after(self) -> dt.datetime:
        return _aware(self.certificate.not_valid_after_utc)

    def to_pem(self) -> str:
        return self.certificate.public_bytes(serialization.Encoding.PEM).decode()


def issue_intermediate(
    pki_dir: Path, *, common_name: str, validity_days: int
) -> x509.Certificate:
    """Sign a new issuing CA with the root, and retire whatever signed before.

    Requires the **root key**, which is the point: this is the one operation that
    needs it, so it is the one moment the root has to be present. Everything else
    ATLAS does runs on the intermediate.

    ⚠️ **The previous intermediate is retired, not deleted.** Every certificate it
    signed stays valid until it expires, and those devices authenticate by chaining
    through it. Removing its certificate would lock out the whole fleet the moment
    the new intermediate took over.
    """
    root_cert_path = pki_dir / ROOT_CERT
    root_key_path = pki_dir / ROOT_KEY
    if not root_cert_path.exists():
        raise CertificateError(f"{root_cert_path} does not exist; there is no root to sign with")
    if not root_key_path.exists():
        raise CertificateError(
            f"{root_key_path} is not present. Issuing an intermediate is the one "
            f"operation that needs the root key — bring it back to this machine "
            f"for the length of this command, then remove it again."
        )

    root = x509.load_pem_x509_certificate(root_cert_path.read_bytes())
    root_key = serialization.load_pem_private_key(root_key_path.read_bytes(), password=None)

    issuing_cert_path = pki_dir / ISSUING_CERT
    issuing_key_path = pki_dir / ISSUING_KEY

    if issuing_cert_path.exists():
        previous = x509.load_pem_x509_certificate(issuing_cert_path.read_bytes())
        retired_dir = keyfiles.secure_dir(pki_dir / RETIRED_DIR)
        (retired_dir / f"{previous.serial_number:x}.crt").write_bytes(
            previous.public_bytes(serialization.Encoding.PEM)
        )
        issuing_cert_path.unlink()
        issuing_key_path.unlink(missing_ok=True)

    private_key = ec.generate_private_key(ec.SECP256R1())
    now = _utcnow()
    certificate = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)]))
        .issuer_name(root.subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=validity_days))
        # ⚠️ `path_length=0`: this CA may sign devices and may not sign another
        # CA. Without it, a stolen intermediate could mint its own intermediates
        # and the bound this whole exercise buys would be gone.
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(root_key, hashes.SHA256())
    )

    issuing_cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    keyfiles.write_private(
        issuing_key_path,
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ),
    )
    # ⚠️ **Republished here, not left to the next restart.** This is the one
    # moment the trust set actually changes: the intermediate that was signing
    # is now retired and a new one signs. A bundle that still named only the
    # old one would have the proxy reject every device the new intermediate
    # issues, and a bundle missing the retired one would reject every device
    # issued before today. The window between rotating and restarting is
    # exactly when an operator is watching, so it is the worst time to be
    # stale.
    write_trust_bundle(pki_dir, _trust_set(root, pki_dir, certificate))
    return certificate


def _trust_set(
    root: x509.Certificate,
    pki_dir: Path,
    issuing: x509.Certificate | None = None,
) -> list[x509.Certificate]:
    """Every certificate a device's chain may terminate at or pass through.

    The root, then each intermediate that has ever signed, then the one signing
    now. ⚠️ Order matters to nothing that verifies a chain, but it is stable
    so that the published bundle does not churn between restarts.
    """
    return [root, *_retired_certificates(pki_dir)] + ([issuing] if issuing else [])


def write_trust_bundle(pki_dir: Path, certificates: Sequence[x509.Certificate]) -> Path:
    """Write the trust bundle and return its path.

    ⚠️ **0644 inside a 0700 directory, and that is not a contradiction.**
    These are certificates — the public halves — and the mode says so. What
    keeps them from the world is the directory, which stays as tight as it is
    for the keys beside them; a reader with the privilege to traverse it is one
    that could read `ca.crt` anyway.
    """
    path = Path(pki_dir) / BUNDLE_CERT
    body = "".join(
        c.public_bytes(serialization.Encoding.PEM).decode() for c in certificates
    )
    path.write_text(body, encoding="utf-8")
    os.chmod(path, 0o644)
    return path


def _retired_certificates(pki_dir: Path) -> list[x509.Certificate]:
    """Intermediates that no longer sign but whose devices are still out there.

    Unreadable files are skipped rather than fatal: one corrupt retired
    certificate must not stop the server, because the devices it can still
    authenticate are the ones that need it most.
    """
    retired = []
    directory = pki_dir / RETIRED_DIR
    if not directory.is_dir():
        return retired
    for path in sorted(directory.glob("*.crt")):
        try:
            retired.append(x509.load_pem_x509_certificate(path.read_bytes()))
        except Exception:
            logger.warning("ignoring unreadable retired certificate %s", path)
    return retired


#: Where the pieces live under ``pki/``.
#:
#: ⚠️ `ca.crt` stays the root and the trust anchor **for ever**, through every
#: intermediate rotation. Devices' certificates chain to it, so replacing it is
#: the one change that costs a fleet-wide re-enrolment.
ROOT_CERT = "ca.crt"
ROOT_KEY = "ca.key"

#: The intermediate that signs day to day, and its key. Absent on a deployment
#: that has not split yet.
ISSUING_CERT = "issuing.crt"
ISSUING_KEY = "issuing.key"

#: Intermediates that no longer sign but whose certificates are still out there.
RETIRED_DIR = "retired"

#: The complete trust bundle: the root, every retired intermediate, and the one
#: signing now — concatenated, which is the form a TLS terminator wants.
#:
#: ⚠️ **ATLAS publishes this so that nothing else has to assemble it.** The
#: set is only knowable by listing `retired/`, and the things that need it
#: cannot: this directory is `drwx------` owned by the application's uid, so
#: InfraTAK's console — which stages the pool Caddy verifies devices against —
#: globbed it as an unprivileged user and got nothing back, silently. It could
#: read a *named* file through its broker but had no way to list a directory,
#: so the pool it staged would have been missing every retired intermediate
#: after the first CA renewal. Devices issued by one chain through it, and they
#: would have stopped being trusted at the edge with no error anywhere.
#:
#: So the name is a contract with anything outside this application. Changing
#: it silently breaks them; adding to what it contains does not.
BUNDLE_CERT = "device-ca-bundle.crt"


def root_key_on_server(pki_dir: Path | str) -> bool:
    """Is the root private key still on this machine? (`SEC_AUDIT.md` S-2)

    ⚠️ **`False` is the goal state, and this is not the same question as "has an
    intermediate been issued".** The ceremony has two halves — issue the
    intermediate, and delete `ca.key` — and an operator who does the first and
    forgets the second has changed nothing whatsoever about their exposure: the
    ten-year root is still sitting on an internet-facing box.

    Inferring it from the chain shape instead is what made the console tell that
    operator the root was gone. One function, so the CLI and the console cannot
    answer it differently.
    """
    return (Path(pki_dir) / ROOT_KEY).exists()


class RootKeyMissing(CertificateError):
    """`ca.crt` exists, but nothing here can sign.

    ⚠️ Its own class because the *only* safe response is to stop. Generating a
    fresh CA at this point — which is what `load_or_create` did before W172 — mints
    a new trust anchor and every enrolled device fails authentication on its next
    check-in, with no way back except re-enrolling the fleet by hand.
    """


#: How long before its issuer's expiry a device certificate must end.
#:
#: ⚠️ Not zero. A certificate expiring at the same instant as its issuer leaves no
#: window in which the device could renew — it would be due for renewal and unable
#: to authenticate at the same moment.
ISSUER_EXPIRY_MARGIN = dt.timedelta(days=1)

#: How many certificates a chain may contain before we stop walking.
#:
#: Three: device, intermediate, root. ⚠️ A bound rather than a `while` because the
#: trust store is read from disk and a malformed or hostile entry that names
#: itself as its own issuer would otherwise loop forever inside an authentication
#: request — a denial of service reachable before any credential is checked.
_MAX_CHAIN_DEPTH = 3


def _verify_signed_by(certificate: x509.Certificate, issuer: x509.Certificate) -> None:
    """Prove `issuer` actually signed `certificate`, or raise.

    ⚠️ Name matching is not evidence. An issuer field is a string the presenter
    chose; only the signature says who issued it.
    """
    try:
        issuer.public_key().verify(
            certificate.signature,
            certificate.tbs_certificate_bytes,
            ec.ECDSA(certificate.signature_hash_algorithm),
        )
    except Exception as exc:
        raise CertificateError("certificate signature does not verify") from exc


class CertificateAuthority:
    """Signs device certificates, and verifies them against a trust store.

    ⚠️ **The signing certificate and the trust anchor need not be the same one**
    (W172, SEC_AUDIT S-2). A deployment that has moved its root offline signs with
    an *intermediate* and still has to accept certificates the root issued
    directly, before the split. So there are two things here, not one:

    * ``certificate`` / ``private_key`` — what this process signs new certificates
      with. On a legacy deployment that is the root; on a split one it is the
      intermediate, and the root's private key is not on this machine at all.
    * ``trusted`` — every certificate a device's chain may terminate at or pass
      through. The root, plus each intermediate that has ever signed.

    Keeping retired intermediates in the store is deliberate: the certificates
    they signed stay valid until they expire, and dropping the issuer would lock
    out every device that has not yet renewed.
    """

    def __init__(
        self,
        certificate: x509.Certificate,
        private_key: ec.EllipticCurvePrivateKey,
        trusted: Sequence[x509.Certificate] | None = None,
    ):
        self._certificate = certificate
        self._private_key = private_key
        # A legacy deployment trusts exactly what it signs with.
        self._trusted: tuple[x509.Certificate, ...] = tuple(trusted or (certificate,))

    @property
    def trusted(self) -> tuple[x509.Certificate, ...]:
        return self._trusted

    def trust_bundle_pem(self) -> str:
        """Every trusted certificate, as one PEM file.

        This is what a TLS terminator needs for `client_auth`: Caddy's
        ``trust_pool file`` reads a bundle, so root and intermediates go in
        together and no proxy configuration has to change when one is added.
        """
        return "".join(
            c.public_bytes(serialization.Encoding.PEM).decode() for c in self._trusted
        )

    def _issuer_of(self, certificate: x509.Certificate) -> x509.Certificate | None:
        """The trusted certificate whose subject matches this one's issuer.

        ⚠️ Matched on name *and* then proven by signature. A name match alone
        proves nothing — anyone can put any string in an issuer field — so the
        caller must verify the signature before believing this answer.
        """
        for candidate in self._trusted:
            if candidate.subject == certificate.issuer:
                return candidate
        return None

    # -- lifecycle --------------------------------------------------------- #

    @classmethod
    def load_or_create(
        cls, pki_dir: Path, *, common_name: str, validity_days: int
    ) -> CertificateAuthority:
        """Load this deployment's CA, publish its trust bundle, and return it.

        ⚠️ **The bundle is written on every load, not only when it changes.**
        Rewriting an identical file costs nothing, and it is what makes an
        existing deployment publish one the first time it restarts on a
        release that has this — no migration, no operator step, and no way to
        end up with a deployment that quietly never wrote it.

        The loading itself is [_load_or_create]; this exists so that there is
        exactly one place the bundle is published from, rather than one per
        branch of a function with three returns.
        """
        authority = cls._load_or_create(
            pki_dir, common_name=common_name, validity_days=validity_days
        )
        # ⚠️ **A failure here must not stop the server, and must not be
        # quiet either.** The bundle is consumed by the proxy that verifies
        # device certificates; if it is stale or missing, devices issued by a
        # retired intermediate lose their edge authentication. That is worth
        # shouting about, and it is not worth refusing to serve over.
        try:
            write_trust_bundle(pki_dir, authority.trusted)
        except OSError:
            logger.error(
                "could not publish the device CA trust bundle to %s/%s. Whatever "
                "terminates TLS for device connections builds its trust pool from "
                "this file; until it is written, a device issued by a retired "
                "intermediate may fail client authentication at the edge.",
                pki_dir, BUNDLE_CERT, exc_info=True,
            )
        return authority

    @classmethod
    def _load_or_create(
        cls, pki_dir: Path, *, common_name: str, validity_days: int
    ) -> CertificateAuthority:
        """Load this deployment's CA, or create a root on a brand-new install.

        Three shapes, and the third is the one W172 exists for:

        * **Legacy** — `ca.crt` + `ca.key`, the root signs directly.
        * **Split** — `ca.crt` (anchor only) + `issuing.crt`/`issuing.key`. The
          root's private key is not on this machine.
        * **Neither** — nothing at all: a first install, so a root is generated.

        ⚠️ **`ca.crt` present with no usable key raises rather than creating
        one.** Before W172 this path generated a fresh CA, which on a split
        deployment is precisely the normal state — so the safety change and the
        feature are the same change.
        """
        cert_path = pki_dir / ROOT_CERT
        key_path = pki_dir / ROOT_KEY
        issuing_cert_path = pki_dir / ISSUING_CERT
        issuing_key_path = pki_dir / ISSUING_KEY

        if cert_path.exists():
            root = x509.load_pem_x509_certificate(cert_path.read_bytes())
            trusted = _trust_set(root, pki_dir)

            if issuing_cert_path.exists() and issuing_key_path.exists():
                issuing = x509.load_pem_x509_certificate(issuing_cert_path.read_bytes())
                issuing_key = serialization.load_pem_private_key(
                    issuing_key_path.read_bytes(), password=None
                )
                return cls(issuing, issuing_key,
                           trusted=_trust_set(root, pki_dir, issuing))

            if key_path.exists():
                private_key = serialization.load_pem_private_key(
                    key_path.read_bytes(), password=None
                )
                return cls(root, private_key, trusted=trusted)

            raise RootKeyMissing(
                f"{cert_path} exists but neither {ROOT_KEY} nor {ISSUING_KEY} is "
                f"present, so nothing here can issue a certificate. This is what a "
                f"deployment looks like after its root was taken offline and the "
                f"intermediate was lost: restore {ISSUING_KEY} and {ISSUING_CERT} "
                f"from backup, or bring the root key back long enough to run "
                f"`python -m app.cli ca-issue-intermediate`. Refusing to generate a "
                f"new CA — that would invalidate every enrolled device."
            )

        keyfiles.secure_dir(pki_dir)
        private_key = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
        now = _utcnow()

        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=5))
            .not_valid_after(now + dt.timedelta(days=validity_days))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_cert_sign=True,
                    crl_sign=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .sign(private_key, hashes.SHA256())
        )

        cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
        # ⚠️ The root key sits on disk unencrypted, and still does. It is the crown
        # jewel — anyone holding it can mint a device identity — and encrypting it
        # with a passphrase kept on the same host would be theatre. The answer is
        # custody the application only *asks* of: a KMS or an HSM (R8, SEC_AUDIT
        # S-2). What changed is that it is never briefly readable on the way out.
        keyfiles.write_private(
            key_path,
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            ),
        )

        return cls(certificate, private_key)

    # -- issuance ---------------------------------------------------------- #

    @property
    def certificate(self) -> x509.Certificate:
        """What this process signs with — the intermediate on a split deployment,
        the root on a legacy one. Not necessarily the trust anchor (W172)."""
        return self._certificate

    def certificate_pem(self) -> str:
        return self._certificate.public_bytes(serialization.Encoding.PEM).decode()

    def sign_csr(
        self, csr_pem: str, *, device_id: uuid.UUID, serial_number: str, validity_days: int
    ) -> IssuedCertificate:
        """Issue a client certificate binding this key to this device record."""
        try:
            csr = x509.load_pem_x509_csr(csr_pem.encode())
        except Exception as exc:
            raise CertificateError(f"malformed CSR: {exc}") from exc

        # Proof of possession: without this, anyone could submit someone else's
        # public key and be issued a certificate for it.
        if not csr.is_signature_valid:
            raise CertificateError("CSR signature is invalid")

        public_key = csr.public_key()
        if not isinstance(public_key, ec.EllipticCurvePublicKey):
            raise CertificateError("device keys must be EC P-256")

        # Subject is built here, not taken from the CSR.
        subject = x509.Name(
            [
                x509.NameAttribute(NameOID.COMMON_NAME, str(device_id)),
                x509.NameAttribute(NameOID.SERIAL_NUMBER, serial_number),
                x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, "takmdm-device"),
            ]
        )
        now = _utcnow()
        expires = self._capped_expiry(now, validity_days)

        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(self._certificate.subject)
            .public_key(public_key)
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=5))
            .not_valid_after(expires)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_agreement=True,
                    content_commitment=False,
                    key_encipherment=False,
                    data_encipherment=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            .add_extension(
                x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]),
                critical=False,
            )
            .sign(self._private_key, hashes.SHA256())
        )
        return IssuedCertificate(certificate)

    # -- verification ------------------------------------------------------ #

    def verify(self, certificate: x509.Certificate) -> None:
        """Walk this certificate's chain to a trusted root. Raises on failure.

        Revocation is *not* checked here — that is a database concern, handled by
        the authentication dependency (D25).

        ⚠️ **Every certificate in the chain is checked, not just the leaf.** An
        expired intermediate must stop working, or moving the root offline would
        buy nothing: the whole point of a short-lived intermediate is that it stops
        being usable on its own schedule.

        ⚠️ **Depth is capped.** The intermediate is issued with
        ``path_length=0``, so the only shapes accepted are device→root (legacy)
        and device→intermediate→root. The loop below cannot run away on a
        self-issued certificate claiming to be its own issuer, which is what an
        unbounded walk does when handed a cycle.
        """
        chain: list[x509.Certificate] = []
        current = certificate

        for _ in range(_MAX_CHAIN_DEPTH):
            issuer = self._issuer_of(current)
            if issuer is None:
                raise CertificateError("certificate was not issued by this CA")

            _verify_signed_by(current, issuer)
            chain.append(current)

            if issuer.subject == issuer.issuer:
                # A self-issued trusted certificate is the anchor: stop here and
                # check the anchor's own dates along with the rest.
                chain.append(issuer)
                break
            current = issuer
        else:
            raise CertificateError("certificate chain is too long to be one of ours")

        now = _utcnow()
        for link in chain:
            if now < _aware(link.not_valid_before_utc):
                raise CertificateError(
                    "certificate is not yet valid"
                    if link is certificate
                    else "an issuing certificate is not yet valid"
                )
            if now > _aware(link.not_valid_after_utc):
                raise CertificateError(
                    "certificate has expired"
                    if link is certificate
                    else "an issuing certificate has expired"
                )

    def _capped_expiry(self, now: dt.datetime, validity_days: int) -> dt.datetime:
        """A device certificate must never outlive the certificate that signed it.

        ⚠️ **Without this, automatic renewal does not save the fleet** (W175). A
        device renews thirty days before *its own* expiry, so one issued a long
        certificate shortly before its issuer expires stops authenticating when the
        issuer does — with most of its own validity unused — and does not come back
        to ask for another until long after. Issuing a replacement intermediate
        rescues nobody, because nobody asks.

        Capping inverts that. As an issuer ages the certificates it signs get
        shorter, so devices renew more often and roll onto the replacement quickly
        once one exists. The fleet converges on the new issuer by itself, which is
        the property that makes rotation cost a ceremony and nothing else.

        The margin keeps a device from expiring at the same instant as its issuer,
        which would leave no window in which to renew at all.
        """
        wanted = now + dt.timedelta(days=validity_days)
        issuer_expiry = _aware(self._certificate.not_valid_after_utc)
        latest = issuer_expiry - ISSUER_EXPIRY_MARGIN

        if latest <= now:
            # The issuer is expired, or so close that nothing useful can be signed.
            # Refusing is the honest answer: a certificate valid for minutes would
            # look like success and strand the device anyway.
            raise CertificateError(
                f"the issuing certificate expires {issuer_expiry.date()} and cannot "
                f"sign a usable device certificate. Issue a new intermediate "
                f"(`python -m app.cli ca-issue-intermediate`) before enrolling or "
                f"renewing anything else."
            )

        if wanted <= latest:
            return wanted

        logger.info(
            "capping certificate validity at the issuer's expiry: %s rather than %s",
            latest.date(),
            wanted.date(),
        )
        return latest

    @staticmethod
    def device_id_from(certificate: x509.Certificate) -> uuid.UUID:
        attributes = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if not attributes:
            raise CertificateError("certificate has no common name")
        try:
            return uuid.UUID(str(attributes[0].value))
        except ValueError as exc:
            raise CertificateError("certificate common name is not a device id") from exc
