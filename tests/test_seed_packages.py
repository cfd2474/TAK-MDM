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

"""The applications a deployment ships with (W143).

⚠️ A fresh install cannot enrol anything until the agent is in the library: the
provisioning QR carries the signing checksum of the agent APK *this server
serves*, so an empty library means no checksum and the token page refuses. That
is several screens away from anything mentioning an upload, so the install
loads them itself.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

DIST = Path("dist")


# --------------------------------------------------------------------------- #
# What ships, and that it is what it claims
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "filename,package",
    [
        ("atlas-agent.apk", "com.taksolutions.atlasmdm"),
        ("atlas-launcher.apk", "com.taksolutions.atlaslauncher"),
    ],
)
def test_the_bundled_build_is_the_app_it_claims_to_be(filename, package):
    """⚠️ Checked by reading the APK, not by trusting the filename. A mismatch
    would install the wrong application on every device in a fleet."""
    from app.artifacts.apk import inspect_apk

    info = inspect_apk((DIST / filename).read_bytes())

    assert info.package_name == package
    assert info.signature_sha256, "an unsigned build cannot be installed"


def test_the_agent_carries_the_receiver_provisioning_names():
    """The QR names this component; an APK without it fails on-device with
    nothing but "something went wrong", after a download and a factory reset."""
    from app.artifacts.apk import inspect_apk
    from app.config import Settings
    from app.services.provisioning import component_class

    info = inspect_apk((DIST / "atlas-agent.apk").read_bytes())

    assert component_class(Settings().agent_admin_receiver) in info.receivers


def test_both_are_signed_with_the_same_key():
    """packages.ingest refuses a build whose certificate differs from the stored
    one, so two ATLAS apps signed differently would be a deployment that works
    until the second upload."""
    from app.artifacts.apk import inspect_apk

    agent = inspect_apk((DIST / "atlas-agent.apk").read_bytes())
    launcher = inspect_apk((DIST / "atlas-launcher.apk").read_bytes())

    assert agent.signature_sha256 == launcher.signature_sha256


# --------------------------------------------------------------------------- #
# The seeder
# --------------------------------------------------------------------------- #


def test_seeding_loads_every_bundled_application(client, db, artifact_storage, settings):
    """The install path, end to end: an empty library becomes a usable one."""
    from app.services import packages as package_service

    for name in ("atlas-agent.apk", "atlas-launcher.apk"):
        with io.open(DIST / name, "rb") as handle:
            package_service.ingest(db, artifact_storage, handle.read())
    db.commit()

    facts = package_service.agent_build_facts(
        db, artifact_storage, settings.agent_package_name
    )

    assert facts is not None and facts.signature_checksum
    # And that is exactly what makes a QR possible.
    from app.services.provisioning import resolve_signature_checksum

    assert resolve_signature_checksum(settings, facts.signature_checksum)


def test_seeding_twice_changes_nothing(db, artifact_storage):
    """⚠️ The restart case, and the whole basis of running this on boot. The
    second pass must be refused rather than duplicating a build."""
    from app.services import packages as package_service

    data = (DIST / "atlas-launcher.apk").read_bytes()
    package_service.ingest(db, artifact_storage, data)
    db.commit()

    with pytest.raises(package_service.PackageError) as raised:
        package_service.ingest(db, artifact_storage, data)

    assert "already" in str(raised.value)


def test_a_missing_seed_directory_is_not_an_error(tmp_path, capsys):
    """It runs on the startup path. A deployment must never fail to boot because
    the directory is absent."""
    import argparse

    from app.cli import seed_packages

    code = seed_packages(argparse.Namespace(directory=str(tmp_path / "nope")))

    assert code == 0
    assert "nothing to load" in capsys.readouterr().out


def test_an_unreadable_build_does_not_stop_the_others(tmp_path, capsys):
    """⚠️ One corrupt file must not cost a deployment its agent.

    The property is that the loop reaches every file and returns success. It is
    asserted on the *report* rather than on rows, because this function opens
    the real `SessionLocal` — in the container that is the right database, and
    in a test there is none. The rows themselves are covered through the service
    in `test_seeding_loads_every_bundled_application`.
    """
    import argparse

    from app.cli import seed_packages

    (tmp_path / "aaa-broken.apk").write_bytes(b"not an apk")
    (tmp_path / "zzz-second.apk").write_bytes((DIST / "atlas-launcher.apk").read_bytes())

    code = seed_packages(argparse.Namespace(directory=str(tmp_path)))

    out = capsys.readouterr().out
    assert code == 0
    assert "aaa-broken.apk" in out and "not a valid ZIP" in out
    # Reached despite the failure above it, which is the whole point.
    assert "zzz-second.apk" in out


# --------------------------------------------------------------------------- #
# Wiring — a seeder nothing calls seeds nothing
# --------------------------------------------------------------------------- #


def test_the_seed_directory_is_mounted():
    compose = io.open("docker-compose.yml", encoding="utf-8").read()

    assert "./dist:/seed:ro" in compose


def test_startup_runs_the_seeder_after_migrations():
    """⚠️ Order matters: it writes rows, so the schema has to exist first."""
    entrypoint = io.open("docker/entrypoint.sh", encoding="utf-8").read()

    assert "seed-packages" in entrypoint
    assert entrypoint.index("alembic upgrade head") < entrypoint.index("seed-packages")
