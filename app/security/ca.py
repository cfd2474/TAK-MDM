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


class CertificateAuthority:
    """Signs and verifies device certificates."""

    def __init__(self, certificate: x509.Certificate, private_key: ec.EllipticCurvePrivateKey):
        self._certificate = certificate
        self._private_key = private_key

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

        pki_dir.mkdir(parents=True, exist_ok=True)
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
        key_path.write_bytes(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        # The root key sits on disk unencrypted. Acceptable for a single self-hosted
        # server where the DB is equally exposed, but it is the crown jewel: anyone
        # holding it can mint a device identity. Restrict the directory, and move it
        # behind a KMS or HSM before this leaves a trusted host.
        key_path.chmod(0o600)

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
        """Check issuer, signature, and validity window. Raises on failure.

        Revocation is *not* checked here — that is a database concern, handled by
        the authentication dependency (D25).
        """
        if certificate.issuer != self._certificate.subject:
            raise CertificateError("certificate was not issued by this CA")

        now = _utcnow()
        if now < _aware(certificate.not_valid_before_utc):
            raise CertificateError("certificate is not yet valid")
        if now > _aware(certificate.not_valid_after_utc):
            raise CertificateError("certificate has expired")

        try:
            self._certificate.public_key().verify(
                certificate.signature,
                certificate.tbs_certificate_bytes,
                ec.ECDSA(certificate.signature_hash_algorithm),
            )
        except Exception as exc:
            raise CertificateError("certificate signature does not verify") from exc

    @staticmethod
    def device_id_from(certificate: x509.Certificate) -> uuid.UUID:
        attributes = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        if not attributes:
            raise CertificateError("certificate has no common name")
        try:
            return uuid.UUID(str(attributes[0].value))
        except ValueError as exc:
            raise CertificateError("certificate common name is not a device id") from exc
