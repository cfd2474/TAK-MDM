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

"""Taking the root offline, without stranding a fleet (W172, SEC_AUDIT S-2).

The whole exercise turns *permanent, unrecoverable* compromise into *bounded and
revocable*: steal the box and you get an intermediate that expires and can be
revoked, not a ten-year root that can only be answered by re-enrolling every
tablet by hand.

⚠️ **The dangerous case is not the attack, it is the migration.** A deployment
whose root key has gone offline looks — to code written before this — exactly like
a fresh install. `load_or_create` used to generate a new CA in that state, which
would invalidate every enrolled device at once. Several tests below exist only to
hold that line.
"""

from __future__ import annotations

import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization

from app.security.ca import (
    CertificateAuthority,
    CertificateError,
    RootKeyMissing,
    issue_intermediate,
)


def _root(pki):
    return CertificateAuthority.load_or_create(
        pki, common_name="ATLAS Test Root", validity_days=3650
    )


def _enrol(authority: CertificateAuthority):
    """A device certificate from whatever this CA currently signs with."""
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    device_id = uuid.uuid4()
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, str(device_id))]))
        .sign(key, hashes.SHA256())
    )
    issued = authority.sign_csr(
        csr.public_bytes(serialization.Encoding.PEM).decode(),
        device_id=device_id,
        serial_number="TEST-DEVICE",
        validity_days=825,
    )
    return x509.load_pem_x509_certificate(issued.to_pem().encode())


# --------------------------------------------------------------------------- #
# The ceremony
# --------------------------------------------------------------------------- #


def test_an_intermediate_is_signed_by_the_root(tmp_path):
    pki = tmp_path / "pki"
    root = _root(pki)

    intermediate = issue_intermediate(
        pki, common_name="ATLAS Issuing CA", validity_days=365
    )

    assert intermediate.issuer == root.certificate.subject
    assert (pki / "issuing.crt").exists()
    assert (pki / "issuing.key").exists()


def test_the_intermediate_may_not_sign_another_ca(tmp_path):
    """⚠️ `path_length=0`, or the bound this buys evaporates.

    Without it a stolen intermediate could mint intermediates of its own, and
    revoking the one you know about would achieve nothing.
    """
    pki = tmp_path / "pki"
    _root(pki)

    intermediate = issue_intermediate(
        pki, common_name="ATLAS Issuing CA", validity_days=365
    )

    constraints = intermediate.extensions.get_extension_for_class(
        x509.BasicConstraints
    ).value
    assert constraints.ca is True
    assert constraints.path_length == 0


def test_the_intermediate_takes_over_signing(tmp_path):
    pki = tmp_path / "pki"
    _root(pki)
    issue_intermediate(pki, common_name="ATLAS Issuing CA", validity_days=365)

    authority = _root(pki)

    assert authority.certificate.subject.rfc4514_string() == "CN=ATLAS Issuing CA"


def test_the_root_key_can_then_be_removed(tmp_path):
    """The state the whole exercise is for."""
    pki = tmp_path / "pki"
    _root(pki)
    issue_intermediate(pki, common_name="ATLAS Issuing CA", validity_days=365)

    (pki / "ca.key").unlink()
    authority = _root(pki)

    assert authority.certificate.subject.rfc4514_string() == "CN=ATLAS Issuing CA"
    assert len(authority.trusted) == 2, "the root is still the anchor"


# --------------------------------------------------------------------------- #
# ⚠️ The line that must never move
# --------------------------------------------------------------------------- #


def test_a_missing_root_key_never_regenerates_the_ca(tmp_path):
    """⚠️ The single most dangerous behaviour in this work.

    Before W172, `load_or_create` generated a new CA whenever the key was absent.
    After the root goes offline that is the *normal* state — so the old code would
    have minted a fresh trust anchor and every enrolled device would have failed
    authentication on its next check-in, with no remedy short of re-enrolling the
    fleet by hand.
    """
    pki = tmp_path / "pki"
    original = _root(pki).certificate.public_bytes(serialization.Encoding.PEM)
    (pki / "ca.key").unlink()

    with pytest.raises(RootKeyMissing):
        _root(pki)

    assert (pki / "ca.crt").read_bytes() == original, "the root certificate was replaced"


def test_the_refusal_says_how_to_recover(tmp_path):
    """A stop with no way forward is an outage. This one names both routes."""
    pki = tmp_path / "pki"
    _root(pki)
    (pki / "ca.key").unlink()

    with pytest.raises(RootKeyMissing) as raised:
        _root(pki)

    message = str(raised.value)
    assert "issuing.key" in message and "restore" in message
    assert "ca-issue-intermediate" in message
    assert "every enrolled device" in message


def test_a_first_install_still_creates_a_root(tmp_path):
    """Nothing above may break the empty-directory case."""
    authority = _root(tmp_path / "pki")

    assert (tmp_path / "pki" / "ca.crt").exists()
    assert authority.trusted == (authority.certificate,)


# --------------------------------------------------------------------------- #
# Rotation, and the fleet that is mid-flight
# --------------------------------------------------------------------------- #


def test_rotating_retires_the_old_intermediate_rather_than_deleting_it(tmp_path):
    pki = tmp_path / "pki"
    _root(pki)
    first = issue_intermediate(pki, common_name="ATLAS Issuing CA", validity_days=365)

    second = issue_intermediate(pki, common_name="ATLAS Issuing CA 2", validity_days=365)

    retired = list((pki / "retired").glob("*.crt"))
    assert len(retired) == 1
    kept = x509.load_pem_x509_certificate(retired[0].read_bytes())
    assert kept.serial_number == first.serial_number
    assert second.serial_number != first.serial_number


def test_devices_from_a_retired_intermediate_still_authenticate(tmp_path):
    """⚠️ The fleet-wide outage this avoids.

    A device holds its certificate for 825 days. Rotating the intermediate every
    year means most of the fleet is chained through one that no longer signs, and
    dropping it from the trust store would lock them all out at once.
    """
    pki = tmp_path / "pki"
    _root(pki)
    issue_intermediate(pki, common_name="ATLAS Issuing CA", validity_days=365)

    device_cert = _enrol(_root(pki))

    issue_intermediate(pki, common_name="ATLAS Issuing CA 2", validity_days=365)
    new_authority = _root(pki)

    new_authority.verify(device_cert)


def test_the_trust_bundle_grows_with_each_rotation(tmp_path):
    pki = tmp_path / "pki"
    _root(pki)
    issue_intermediate(pki, common_name="ATLAS Issuing CA", validity_days=365)
    issue_intermediate(pki, common_name="ATLAS Issuing CA 2", validity_days=365)

    bundle = _root(pki).trust_bundle_pem()

    # Root, the retired intermediate, and the current one.
    assert bundle.count("BEGIN CERTIFICATE") == 3


# --------------------------------------------------------------------------- #
# Issuing an intermediate needs the root, which is the point
# --------------------------------------------------------------------------- #


def test_issuing_without_the_root_key_is_refused(tmp_path):
    pki = tmp_path / "pki"
    _root(pki)
    issue_intermediate(pki, common_name="ATLAS Issuing CA", validity_days=365)
    (pki / "ca.key").unlink()

    with pytest.raises(CertificateError, match="root key"):
        issue_intermediate(pki, common_name="ATLAS Issuing CA 2", validity_days=365)


def test_the_refusal_explains_the_ceremony(tmp_path):
    pki = tmp_path / "pki"
    _root(pki)
    (pki / "ca.key").unlink()

    with pytest.raises(CertificateError) as raised:
        issue_intermediate(pki, common_name="x", validity_days=365)

    assert "bring it back" in str(raised.value)
