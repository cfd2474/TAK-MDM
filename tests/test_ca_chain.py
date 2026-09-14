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

"""Walking a certificate's chain to a trusted root (W172, SEC_AUDIT S-2).

⚠️ **This is the gate in front of every device request.** `require_certificate`
calls `verify()` before anything else is believed, so a chain check that accepts
too much is remote authentication bypass, and one that accepts too little locks
the whole fleet out. Both directions are tested.

The point of the change is that the signing certificate and the trust anchor stop
being the same object: a deployment with its root offline signs with an
intermediate, and must still accept certificates the root issued directly before
the split.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from app.security.ca import CertificateAuthority, CertificateError


def _name(common_name: str) -> x509.Name:
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _cert(
    subject: str,
    *,
    issuer_name: x509.Name | None = None,
    issuer_key: ec.EllipticCurvePrivateKey | None = None,
    ca: bool = False,
    path_length: int | None = None,
    starts_in_days: float = -1,
    lasts_days: float = 365,
    key: ec.EllipticCurvePrivateKey | None = None,
):
    """Build one certificate, self-signed unless an issuer is given."""
    key = key or ec.generate_private_key(ec.SECP256R1())
    signer = issuer_key or key
    builder = (
        x509.CertificateBuilder()
        .subject_name(_name(subject))
        .issuer_name(issuer_name or _name(subject))
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(_now() + dt.timedelta(days=starts_in_days))
        .not_valid_after(_now() + dt.timedelta(days=starts_in_days + lasts_days))
    )
    if ca:
        builder = builder.add_extension(
            x509.BasicConstraints(ca=True, path_length=path_length), critical=True
        )
    return builder.sign(signer, hashes.SHA256()), key


@pytest.fixture
def root():
    return _cert("ATLAS Root", ca=True, path_length=1, lasts_days=3650)


@pytest.fixture
def intermediate(root):
    root_cert, root_key = root
    return _cert(
        "ATLAS Issuing CA",
        issuer_name=root_cert.subject,
        issuer_key=root_key,
        ca=True,
        path_length=0,
        lasts_days=365,
    )


def _device(issuer_cert, issuer_key, name: str | None = None):
    cert, _ = _cert(
        name or str(uuid.uuid4()),
        issuer_name=issuer_cert.subject,
        issuer_key=issuer_key,
        lasts_days=825,
    )
    return cert


# --------------------------------------------------------------------------- #
# The shapes that must work
# --------------------------------------------------------------------------- #


def test_a_legacy_certificate_signed_by_the_root_still_verifies(root):
    """⚠️ Every device enrolled before the split has one of these. If this breaks,
    the entire fleet fails authentication at once."""
    root_cert, root_key = root
    authority = CertificateAuthority(root_cert, root_key)

    authority.verify(_device(root_cert, root_key))


def test_a_certificate_from_the_intermediate_verifies(root, intermediate):
    root_cert, _ = root
    inter_cert, inter_key = intermediate
    authority = CertificateAuthority(
        inter_cert, inter_key, trusted=[root_cert, inter_cert]
    )

    authority.verify(_device(inter_cert, inter_key))


def test_both_generations_verify_at_once(root, intermediate):
    """The migration state: the box signs with the intermediate and still answers
    devices whose certificates the root issued directly."""
    root_cert, root_key = root
    inter_cert, inter_key = intermediate
    authority = CertificateAuthority(
        inter_cert, inter_key, trusted=[root_cert, inter_cert]
    )

    authority.verify(_device(root_cert, root_key))
    authority.verify(_device(inter_cert, inter_key))


def test_a_retired_intermediate_keeps_its_devices_working(root, intermediate):
    """⚠️ Why retired intermediates stay in the store.

    The certificates an old intermediate signed are valid until they expire.
    Dropping its certificate when it stops signing would lock out every device
    that has not yet renewed — a fleet-wide outage caused by good hygiene.
    """
    root_cert, root_key = root
    old_cert, old_key = intermediate
    new_cert, new_key = _cert(
        "ATLAS Issuing CA 2",
        issuer_name=root_cert.subject,
        issuer_key=root_key,
        ca=True,
        path_length=0,
    )
    authority = CertificateAuthority(
        new_cert, new_key, trusted=[root_cert, old_cert, new_cert]
    )

    authority.verify(_device(old_cert, old_key))
    authority.verify(_device(new_cert, new_key))


# --------------------------------------------------------------------------- #
# ⚠️ The shapes that must not
# --------------------------------------------------------------------------- #


def test_a_matching_issuer_name_is_not_enough(root):
    """⚠️ The attack this whole function exists to refuse.

    An issuer field is a string the presenter chose. A certificate that *says* it
    came from "ATLAS Root" and was signed by a key we have never seen must be
    refused — otherwise anyone who can read `ca.crt`, which is public, can mint an
    identity by typing the right name.
    """
    root_cert, root_key = root
    impostor_key = ec.generate_private_key(ec.SECP256R1())
    forged, _ = _cert(
        "impostor", issuer_name=root_cert.subject, issuer_key=impostor_key
    )
    authority = CertificateAuthority(root_cert, root_key)

    with pytest.raises(CertificateError, match="signature does not verify"):
        authority.verify(forged)


def test_an_unknown_issuer_is_refused(root, intermediate):
    """A real certificate from a CA that is simply not ours."""
    root_cert, root_key = root
    other_cert, other_key = _cert("Someone Else's CA", ca=True, path_length=0)
    authority = CertificateAuthority(root_cert, root_key)

    with pytest.raises(CertificateError, match="not issued by this CA"):
        authority.verify(_device(other_cert, other_key))


def test_an_expired_intermediate_stops_its_devices(root):
    """⚠️ The entire point of a short-lived intermediate.

    If an expired issuer still worked, moving the root offline would buy nothing:
    a stolen intermediate would keep minting usable identities for as long as the
    certificates it signed were dated to last.
    """
    root_cert, root_key = root
    expired_cert, expired_key = _cert(
        "ATLAS Issuing CA",
        issuer_name=root_cert.subject,
        issuer_key=root_key,
        ca=True,
        path_length=0,
        starts_in_days=-400,
        lasts_days=365,
    )
    authority = CertificateAuthority(
        expired_cert, expired_key, trusted=[root_cert, expired_cert]
    )

    # The device certificate itself is perfectly current.
    leaf = _device(expired_cert, expired_key)

    with pytest.raises(CertificateError, match="issuing certificate has expired"):
        authority.verify(leaf)


def test_an_intermediate_not_yet_valid_stops_its_devices(root):
    root_cert, root_key = root
    future_cert, future_key = _cert(
        "ATLAS Issuing CA",
        issuer_name=root_cert.subject,
        issuer_key=root_key,
        ca=True,
        path_length=0,
        starts_in_days=10,
        lasts_days=365,
    )
    authority = CertificateAuthority(
        future_cert, future_key, trusted=[root_cert, future_cert]
    )

    with pytest.raises(CertificateError, match="issuing certificate is not yet valid"):
        authority.verify(_device(future_cert, future_key))


def test_an_expired_leaf_is_still_refused(root):
    """The check the flat version already did, which must survive the rewrite."""
    root_cert, root_key = root
    stale, _ = _cert(
        "old-device",
        issuer_name=root_cert.subject,
        issuer_key=root_key,
        starts_in_days=-800,
        lasts_days=365,
    )
    authority = CertificateAuthority(root_cert, root_key)

    with pytest.raises(CertificateError, match="certificate has expired"):
        authority.verify(stale)


def test_a_chain_deeper_than_we_ever_issue_is_refused(root):
    """⚠️ The walk is bounded, and the bound is reachable.

    Our intermediates carry `path_length=0`, so ATLAS never *issues* a chain this
    deep — the cap is defence against a trust store that has been tampered with,
    not against our own output. The `for range(...)` also guarantees the walk
    terminates whatever the store contains, which matters because this runs before
    any credential is checked and a hang here is a denial of service anyone can
    trigger.
    """
    root_cert, root_key = root
    chain = [(root_cert, root_key)]
    for depth in range(3):
        parent_cert, parent_key = chain[-1]
        chain.append(
            _cert(
                f"ATLAS Sub {depth}",
                issuer_name=parent_cert.subject,
                issuer_key=parent_key,
                ca=True,
            )
        )
    deepest_cert, deepest_key = chain[-1]
    authority = CertificateAuthority(
        deepest_cert, deepest_key, trusted=[c for c, _ in chain]
    )

    with pytest.raises(CertificateError, match="too long"):
        authority.verify(_device(deepest_cert, deepest_key))


def test_a_trusted_self_signed_entry_is_an_anchor(root):
    """Putting a certificate in the trust store *is* the act of trusting it.

    A second self-signed CA in the store terminates a chain of its own — that is
    not a bypass, it is what a trust store means. Recorded so the behaviour is
    deliberate rather than discovered.
    """
    root_cert, root_key = root
    other_cert, other_key = _cert("A Second Root", ca=True, path_length=0)
    authority = CertificateAuthority(
        root_cert, root_key, trusted=[root_cert, other_cert]
    )

    authority.verify(_device(other_cert, other_key))


# --------------------------------------------------------------------------- #
# What the proxy is handed
# --------------------------------------------------------------------------- #


def test_the_trust_bundle_carries_every_anchor(root, intermediate):
    root_cert, _ = root
    inter_cert, inter_key = intermediate
    authority = CertificateAuthority(
        inter_cert, inter_key, trusted=[root_cert, inter_cert]
    )

    bundle = authority.trust_bundle_pem()

    assert bundle.count("BEGIN CERTIFICATE") == 2
    for cert in (root_cert, inter_cert):
        assert cert.public_bytes(serialization.Encoding.PEM).decode() in bundle


def test_a_legacy_deployment_trusts_what_it_signs_with(root):
    """No trust store given means the old shape: one certificate, both roles."""
    root_cert, root_key = root
    authority = CertificateAuthority(root_cert, root_key)

    assert authority.trusted == (root_cert,)
    assert authority.trust_bundle_pem().count("BEGIN CERTIFICATE") == 1
