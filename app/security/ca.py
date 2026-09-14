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
import uuid
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from app.security import keyfiles
from typing import Sequence


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
        cert_path = pki_dir / "ca.crt"
        key_path = pki_dir / "ca.key"

        if cert_path.exists() and key_path.exists():
            certificate = x509.load_pem_x509_certificate(cert_path.read_bytes())
            private_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
            return cls(certificate, private_key)

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

        certificate = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(self._certificate.subject)
            .public_key(public_key)
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=5))
            .not_valid_after(now + dt.timedelta(days=validity_days))
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

    @staticmethod
    def device_id_from(certificate: x509.Certificate) -> uuid.UUID:
        attributes = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if not attributes:
            raise CertificateError("certificate has no common name")
        try:
            return uuid.UUID(str(attributes[0].value))
        except ValueError as exc:
            raise CertificateError("certificate common name is not a device id") from exc
