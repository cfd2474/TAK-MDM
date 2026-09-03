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

"""Which build a policy resolves to, and what happens when it cannot.

Pinning ``artifact_sha256`` is how an operator holds a fleet on a specific build —
including an **older** one. That makes the failure modes asymmetric: resolving to a
*newer* build than asked for is not a degraded outcome, it is the opposite of the
instruction. So a pin that cannot be honoured has to fail rather than fall back.

R17 and R18 were both found by probing this, and both had exactly that shape.
"""

from __future__ import annotations

from app.db.models import PartRole
from app.services import effective_policy as eff
from app.services import packages as package_service
from tests.apk_fixtures import build_apk, make_signing_certificate


def base_sha(result) -> str:
    return next(f.artifact_sha256 for f in result.version.files if f.role is PartRole.BASE)


def resolve(db, entry: dict) -> dict:
    return eff.resolve_required_apps(db, {"APP_CATALOG": {"required_apps": [entry]}})[0]


def two_builds(db, storage, package: str = "com.probe"):
    """Codes 100 and 200 of one package. Returns (old, new)."""
    certificate = make_signing_certificate()
    old = package_service.ingest(
        db, storage, build_apk(package, 100, "1.0", certificate_der=certificate)
    )
    new = package_service.ingest(
        db, storage, build_apk(package, 200, "2.0", certificate_der=certificate)
    )
    db.flush()
    return old, new


# --------------------------------------------------------------------------- #
# The three levels of intent
# --------------------------------------------------------------------------- #


def test_no_floor_and_no_pin_takes_the_newest(db, artifact_storage):
    two_builds(db, artifact_storage)
    assert resolve(db, {"package_name": "com.probe"})["version_code"] == 200


def test_a_floor_takes_the_newest_that_clears_it(db, artifact_storage):
    two_builds(db, artifact_storage)
    assert resolve(db, {"package_name": "com.probe", "min_version_code": 100})[
        "version_code"
    ] == 200


def test_a_pin_holds_an_older_build_against_a_newer_one(db, artifact_storage):
    """The whole point: 200 is uploaded and available, and the fleet stays on 100."""
    old, _ = two_builds(db, artifact_storage)

    entry = {"package_name": "com.probe", "artifact_sha256": base_sha(old)}
    assert resolve(db, entry)["version_code"] == 100


def test_a_pin_beats_a_floor_that_would_have_chosen_otherwise(db, artifact_storage):
    old, _ = two_builds(db, artifact_storage)

    entry = {
        "package_name": "com.probe",
        "min_version_code": 100,  # would resolve to 200 on its own
        "artifact_sha256": base_sha(old),
    }
    assert resolve(db, entry)["version_code"] == 100


# --------------------------------------------------------------------------- #
# R17 — a pin that cannot be honoured must not become "latest"
# --------------------------------------------------------------------------- #


def test_a_pin_to_a_missing_artifact_resolves_to_nothing(db, artifact_storage):
    """Was R17: this fell through to the floor and returned the NEWEST build, so
    deleting an artifact silently jumped the fleet forward — precisely when the
    operator had pinned it back."""
    two_builds(db, artifact_storage)

    resolved = resolve(db, {"package_name": "com.probe", "artifact_sha256": "de" * 32})

    assert resolved["available"] is False
    assert "version_code" not in resolved
    assert "pinned" in resolved["reason"]


def test_a_pin_that_fails_does_not_quietly_use_the_floor(db, artifact_storage):
    """The same bug wearing a floor: the fallback path *was* the floor, so a policy
    carrying both would resolve instead of failing."""
    two_builds(db, artifact_storage)

    resolved = resolve(
        db,
        {
            "package_name": "com.probe",
            "min_version_code": 100,
            "artifact_sha256": "de" * 32,
        },
    )
    assert resolved["available"] is False


def test_an_artifact_leaving_the_library_breaks_the_pin_rather_than_moving_it(
    db, artifact_storage
):
    """The realistic route into R17: the pinned build is deleted later."""
    old, _ = two_builds(db, artifact_storage)
    sha = base_sha(old)
    package_service.delete_version(db, artifact_storage, old.version)
    db.flush()

    resolved = resolve(db, {"package_name": "com.probe", "artifact_sha256": sha})
    assert resolved["available"] is False


# --------------------------------------------------------------------------- #
# R18 — a pin belongs to its package
# --------------------------------------------------------------------------- #


def test_a_pin_to_another_packages_artifact_is_refused(db, artifact_storage):
    """Was R18: the lookup matched on sha alone, so this returned the other
    package's version while still declaring it under this package_name. The agent
    would have installed the wrong app and then never converged, because the named
    one was still absent."""
    two_builds(db, artifact_storage)
    other = package_service.ingest(db, artifact_storage, build_apk("com.other", 7, "9.9"))
    db.flush()

    resolved = resolve(
        db, {"package_name": "com.probe", "artifact_sha256": base_sha(other)}
    )

    assert resolved["available"] is False
    assert resolved["package_name"] == "com.probe"
    assert "version_code" not in resolved


def test_the_same_sha_still_resolves_for_the_package_it_belongs_to(db, artifact_storage):
    """The fix must constrain, not break: the pin still works on its own package."""
    other = package_service.ingest(db, artifact_storage, build_apk("com.other", 7, "9.9"))
    db.flush()

    resolved = resolve(
        db, {"package_name": "com.other", "artifact_sha256": base_sha(other)}
    )
    assert resolved["version_code"] == 7


# --------------------------------------------------------------------------- #
# The reason travels with the failure
# --------------------------------------------------------------------------- #


def test_nothing_uploaded_still_says_so(db, artifact_storage):
    resolved = resolve(db, {"package_name": "com.absent"})

    assert resolved["available"] is False
    assert resolved["reason"] == "nothing uploaded for it"


def test_a_floor_nothing_satisfies_names_the_floor(db, artifact_storage):
    """Distinct from "nothing uploaded": builds exist, none is new enough."""
    two_builds(db, artifact_storage)

    resolved = resolve(db, {"package_name": "com.probe", "min_version_code": 9999})

    assert resolved["available"] is False
    assert "9999" in resolved["reason"]


def test_each_failure_gives_a_different_reason(db, artifact_storage):
    """All three used to reach the agent as "nothing uploaded for it" — the least
    alarming of them, and wrong for the other two."""
    two_builds(db, artifact_storage)

    reasons = {
        resolve(db, {"package_name": "com.absent"})["reason"],
        resolve(db, {"package_name": "com.probe", "min_version_code": 9999})["reason"],
        resolve(db, {"package_name": "com.probe", "artifact_sha256": "de" * 32})["reason"],
    }
    assert len(reasons) == 3
