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

"""ATAK Core and Plugins as their own section (W141).

ATAK and its plugins were ordinary entries in required apps, which gave the
compatibility check no fixed point: it had to guess which row was ATAK. They now
live in a section that names the core build first, so every plugin is compared
against a version the operator chose rather than one inferred.

⚠️ **Nothing about how they install changes.** The resolver folds `atak_core`,
`atak_plugins` and `required_apps` into one list, so the agent is told exactly
what it was told before.
"""

from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.models import AppPackage, Device
from app.policies.registry import PolicyTypeError, registry
from app.services import atak_compat
from app.services import packages as package_service
from tests.apk_fixtures import build_apk, build_xapk, make_signing_certificate
from tests.conftest import ADMIN_HEADERS, base_sha


def _build(db, artifact_storage, package: str, code: int, *, version_name="1.0",
           plugin_api=None, cert=None):
    result = package_service.ingest(
        db,
        artifact_storage,
        build_apk(package, code, version_name, certificate_der=cert,
                  plugin_api=plugin_api),
    )
    db.flush()
    return result.version


def _sha(version) -> str:
    from app.db.models import PartRole

    return next(f.artifact_sha256 for f in version.files if f.role is PartRole.BASE)


def _apps_of(db, device) -> list[dict]:
    from app.services import desired_state

    return desired_state.build(db, device)["apps"]


# --------------------------------------------------------------------------- #
# ⚠️ The section installs exactly what required apps used to
# --------------------------------------------------------------------------- #


def test_atak_core_and_plugins_reach_the_device(
    db, artifact_storage, make_device, make_policy, assign
):
    """The whole point of folding the three fields back together: a device sees
    one list of apps and cannot tell which section each came from."""
    core = _build(db, artifact_storage, "com.atakmap.app.civ", 52800,
                  version_name="5.8.0.4 (174b425)[playstore]")
    plugin = _build(db, artifact_storage, "com.plugin.one", 1,
                    plugin_api="com.atakmap.app@5.8.0.CIV")
    ordinary = _build(db, artifact_storage, "com.example.notes", 7)
    db.commit()

    device = make_device()
    policy = make_policy(
        "Field",
        "APP_CATALOG",
        {
            "atak_core": {"package_name": "com.atakmap.app.civ",
                          "artifact_sha256": _sha(core)},
            "atak_plugins": [{"package_name": "com.plugin.one",
                              "artifact_sha256": _sha(plugin)}],
            "required_apps": [{"package_name": "com.example.notes",
                               "artifact_sha256": _sha(ordinary)}],
        },
    )
    assign(policy["id"], device["id"])
    db.expire_all()

    apps = _apps_of(db, db.scalar(select(Device)))
    assert {a["package_name"] for a in apps} == {
        "com.atakmap.app.civ", "com.plugin.one", "com.example.notes"
    }
    assert all(a["available"] for a in apps)
    # ATAK first: nothing depends on it, but a desired state read by a human
    # should lead with the thing everything else is built against.
    assert apps[0]["package_name"] == "com.atakmap.app.civ"


def test_a_section_with_nothing_in_it_adds_nothing(
    db, artifact_storage, make_device, make_policy, assign
):
    ordinary = _build(db, artifact_storage, "com.example.notes", 7)
    db.commit()

    device = make_device()
    policy = make_policy(
        "Field",
        "APP_CATALOG",
        {"required_apps": [{"package_name": "com.example.notes",
                            "artifact_sha256": _sha(ordinary)}]},
    )
    assign(policy["id"], device["id"])
    db.expire_all()

    apps = _apps_of(db, db.scalar(select(Device)))
    assert [a["package_name"] for a in apps] == ["com.example.notes"]


# --------------------------------------------------------------------------- #
# ⚠️ The two refusals, and why only one of them is airtight
# --------------------------------------------------------------------------- #


def test_atak_is_refused_in_required_apps_by_the_spec_itself():
    """⚠️ A package-name test, so it holds on every path into a policy — the
    console form, the API, a restored template — without a database."""
    with pytest.raises(PolicyTypeError) as raised:
        registry.validate_spec(
            "APP_CATALOG",
            {"required_apps": [{"package_name": "com.atakmap.app.civ"}]},
        )

    assert "ATAK Core and Plugins" in str(raised.value)


def test_atak_is_refused_in_the_allowlist_too():
    with pytest.raises(PolicyTypeError) as raised:
        registry.validate_spec(
            "APP_CATALOG", {"allowed_packages": ["com.atakmap.app.civ"]}
        )

    assert "ATAK Core and Plugins" in str(raised.value)


def test_atak_is_accepted_in_its_own_section():
    spec = registry.validate_spec(
        "APP_CATALOG", {"atak_core": {"package_name": "com.atakmap.app.civ"}}
    )

    assert spec["atak_core"]["package_name"] == "com.atakmap.app.civ"


def test_a_plugin_in_required_apps_is_refused_by_the_api(
    client: TestClient, db, artifact_storage
):
    """⚠️ The half that needs the library. "Is a plugin" means this app declares
    a `plugin-api`, which is a column — a spec validator cannot see it, so the
    rule lives at every write path that holds a session."""
    _build(db, artifact_storage, "com.plugin.one", 1,
           plugin_api="com.atakmap.app@5.8.0.CIV")
    db.commit()

    response = client.post(
        "/api/v1/policies",
        json={
            "name": "Misplaced",
            "policy_type": "APP_CATALOG",
            "spec": {"required_apps": [{"package_name": "com.plugin.one"}]},
        },
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 422
    assert "ATAK Core and Plugins" in response.text


def test_a_plugin_in_required_apps_is_refused_by_the_console(
    client: TestClient, db, artifact_storage
):
    _build(db, artifact_storage, "com.plugin.one", 1,
           plugin_api="com.atakmap.app@5.8.0.CIV")
    db.commit()

    response = client.post(
        "/policies",
        data={
            "name": "Misplaced",
            "policy_type": "APP_CATALOG",
            "required_apps__package_name": ["com.plugin.one"],
            "required_apps__version_choice": [""],
        },
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )

    assert "error=" in response.headers["location"]
    assert "ATAK" in response.headers["location"]


def test_an_ordinary_app_is_not_mistaken_for_a_plugin(
    client: TestClient, db, artifact_storage
):
    """⚠️ The rule has to be quiet on everything else, or the section becomes a
    place operators route around."""
    _build(db, artifact_storage, "com.example.notes", 7)
    db.commit()

    response = client.post(
        "/api/v1/policies",
        json={
            "name": "Ordinary",
            "policy_type": "APP_CATALOG",
            "spec": {"required_apps": [{"package_name": "com.example.notes"}]},
        },
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 201, response.text


def test_a_plugin_whose_api_was_never_scanned_is_still_caught(
    db, artifact_storage
):
    """⚠️ Asks *any* build, not the newest. `plugin_api` is NULL on anything
    uploaded before the column existed, so a plugin whose latest upload predates
    the scan would otherwise pass as an ordinary app."""
    cert = make_signing_certificate()
    _build(db, artifact_storage, "com.plugin.one", 1,
           plugin_api="com.atakmap.app@5.8.0.CIV", cert=cert)
    newer = _build(db, artifact_storage, "com.plugin.one", 2, cert=cert)
    newer.plugin_api = None
    db.commit()

    assert "com.plugin.one" in atak_compat.plugin_packages(db)


# --------------------------------------------------------------------------- #
# One slot per package, now across three fields
# --------------------------------------------------------------------------- #


def test_the_same_app_cannot_be_a_plugin_and_a_required_app():
    """A package named twice is the same Android slot filled twice, however it is
    spelled. Checking each field alone would let two sections disagree."""
    with pytest.raises(PolicyTypeError) as raised:
        registry.validate_spec(
            "APP_CATALOG",
            {
                "required_apps": [{"package_name": "com.plugin.one"}],
                "atak_plugins": [{"package_name": "com.plugin.one"}],
            },
        )

    assert "more than once" in str(raised.value)


def test_atak_core_cannot_also_be_a_plugin_row():
    with pytest.raises(PolicyTypeError):
        registry.validate_spec(
            "APP_CATALOG",
            {
                "atak_core": {"package_name": "com.atakmap.app.civ"},
                "atak_plugins": [{"package_name": "com.atakmap.app.civ"}],
            },
        )


# --------------------------------------------------------------------------- #
# Two policies, two ATAKs
# --------------------------------------------------------------------------- #


def test_two_policies_naming_different_atak_cores_is_a_conflict(
    client: TestClient, db, artifact_storage, make_device, make_policy, assign
):
    """One ATAK per device. Two policies naming different builds have no natural
    ordering, so the higher rank wins and the operator is told."""
    cert = make_signing_certificate()
    old = _build(db, artifact_storage, "com.atakmap.app.civ", 52500,
                 version_name="5.5.0.1", cert=cert)
    new = _build(db, artifact_storage, "com.atakmap.app.civ", 52800,
                 version_name="5.8.0.4", cert=cert)
    db.commit()

    device = make_device()
    high = make_policy("Field", "APP_CATALOG", {
        "atak_core": {"package_name": "com.atakmap.app.civ",
                      "artifact_sha256": _sha(new)}})
    low = make_policy("Depot", "APP_CATALOG", {
        "atak_core": {"package_name": "com.atakmap.app.civ",
                      "artifact_sha256": _sha(old)}})
    assign(high["id"], device["id"], rank=50)
    assign(low["id"], device["id"], rank=10)

    body = client.get(
        f"/api/v1/devices/{device['id']}/effective-policy", headers=ADMIN_HEADERS
    ).json()

    conflicts = [c for c in body["conflicts"] if c["field"] == "atak_core"]
    assert len(conflicts) == 1, body["conflicts"]
    assert body["values"]["APP_CATALOG"]["atak_core"]["artifact_sha256"] == _sha(new)


# --------------------------------------------------------------------------- #
# The comparison rules themselves, unchanged
# --------------------------------------------------------------------------- #


def test_the_line_comparison_is_unchanged():
    """⚠️ Pinned because the section changes *what* is compared, not *how*.
    ATAK's own versionName carries a fourth component and build metadata, and
    comparing raw strings would call every pairing a mismatch."""
    assert atak_compat.atak_line("5.8.0.4 (174b425)[playstore]") == "5.8.0"
    assert atak_compat.plugin_target("com.atakmap.app@5.8.0.CIV") == "5.8.0"
    assert atak_compat.atak_line("5.8.0.4") == atak_compat.plugin_target(
        "com.atakmap.app@5.8.0.CIV"
    )


def test_an_unscanned_plugin_is_unknown_not_a_mismatch():
    """Silence when unknown. A section that flagged every unscanned build is one
    nobody reads."""
    assert atak_compat.plugin_target(None) is None


# --------------------------------------------------------------------------- #
# Knowing a plugin when we see one
# --------------------------------------------------------------------------- #


def test_a_tak_gov_import_is_a_plugin_whatever_its_manifest_says(db, artifact_storage):
    """⚠️ *"any plugin that comes from the tpc repo is obviously a plugin"*. The
    catalogue is a plugin catalogue, so provenance settles it even when the
    manifest could not be read."""
    from app.services import tak_gov_link

    version = _build(db, artifact_storage, "com.plugin.quiet", 1)
    version.plugin_api = None
    version.source = tak_gov_link.SOURCE_NAME
    db.commit()

    assert "com.plugin.quiet" in atak_compat.plugin_packages(db)


def test_an_fdroid_import_is_not_a_plugin_by_provenance(db, artifact_storage):
    """Only TAK.gov's catalogue carries that meaning. Treating every repository
    import as a plugin would put ordinary F-Droid apps in the ATAK section."""
    version = _build(db, artifact_storage, "com.example.notes", 1)
    version.plugin_api = None
    version.source = "fdroid"
    db.commit()

    assert "com.example.notes" not in atak_compat.plugin_packages(db)


def test_an_xapk_is_scanned_for_plugin_status_like_an_apk(db, artifact_storage):
    """⚠️ *"we do need to scan uploaded apk/xapk for plugin status"*. A split app
    arrives as a container, and the manifest that declares `plugin-api` is the
    base APK inside it."""
    from app.services import packages as package_service

    package_service.ingest(
        db,
        artifact_storage,
        build_xapk("com.plugin.split", 1, splits=("config.arm64_v8a",),
                   plugin_api="com.atakmap.app@5.8.0.CIV"),
    )
    db.commit()

    assert "com.plugin.split" in atak_compat.plugin_packages(db)


# --------------------------------------------------------------------------- #
# ⚠️ MIL and GOV are not separate builds (operator, W141)
# --------------------------------------------------------------------------- #


def test_the_comparison_is_the_version_and_only_the_version():
    """⚠️ A CIV/MIL/GOV comparison was built here and removed, because the
    premise was wrong.

    A device does not run a MIL build. It runs ATAK-CIV, and a *flavour plugin*
    unlocks the rest — so there is no second ATAK for a plugin to be
    incompatible with, and comparing flavours flagged correct pairings as
    broken. What a GOV or MIL plugin needs is that flavour plugin present, which
    is a fact about the fleet rather than a mismatch between two builds.
    """
    assert atak_compat.check(
        atak_version="5.8.0",
        plugins={"com.plugin.mil": "com.atakmap.app@5.8.0.MIL"},
    ) == []

    assert atak_compat.check(
        atak_version="5.8.0",
        plugins={"com.plugin.civ": "com.atakmap.app@5.8.0.CIV"},
    ) == []


def test_a_version_disagreement_is_still_caught_whatever_the_flavour():
    found = atak_compat.check(
        atak_version="5.8.0",
        plugins={"com.plugin.old": "com.atakmap.app@5.5.0.MIL"},
    )

    assert len(found) == 1
    assert "5.5.0" in found[0].message


def test_nothing_reads_a_flavour_any_more():
    """Dead readers that imply a rule which does not exist are worse than none:
    the next person to see `flavours_agree` would assume flavour matters."""
    for gone in ("plugin_flavour", "atak_flavour", "flavours_agree",
                 "UNIVERSAL_FLAVOUR"):
        assert not hasattr(atak_compat, gone), gone


def test_the_tpc_browser_says_gov_and_mil_need_the_flavour_plugin(client, db):
    """⚠️ Where an operator actually meets the requirement — picking the product
    — rather than in a doc they will not open."""
    import pathlib

    apps = pathlib.Path("app/web/templates/apps.html").read_text(encoding="utf-8")

    banner = apps[apps.index("tpc.product != 'ATAK-CIV'"):]
    banner = banner[: banner.index("{% endif %}")]

    assert "ATAK Flavor plugin" in banner
    assert "ATAK will refuse to load them" in banner
    # The licensing warning it already carried is still there, and still its own
    # paragraph — two different problems should not share one sentence.
    assert "export controls" in banner


# --------------------------------------------------------------------------- #
# The console section (W141 chunk 3)
# --------------------------------------------------------------------------- #


def _form(client: TestClient) -> str:
    return client.get(
        "/policies/new?policy_type=APP_CATALOG", headers=ADMIN_HEADERS
    ).text


def _seed(db, artifact_storage):
    """One ATAK, one plugin, one ordinary app — the three kinds the pickers split."""
    cert = make_signing_certificate()
    core = _build(db, artifact_storage, "com.atakmap.app.civ", 52800,
                  version_name="5.8.0.4 (174b425)[playstore]", cert=cert)
    plugin = _build(db, artifact_storage, "com.plugin.one", 1,
                    plugin_api="com.atakmap.app@5.8.0.CIV")
    ordinary = _build(db, artifact_storage, "com.example.notes", 7)
    db.commit()
    return core, plugin, ordinary


def test_the_section_offers_atak_and_plugins_separately(
    client: TestClient, db, artifact_storage
):
    _seed(db, artifact_storage)

    page = _form(client)

    assert 'name="atak_core__package_name"' in page
    assert 'name="atak_plugins__package_name"' in page
    # ⚠️ The names have to actually reach the options. W140 shipped a select
    # that rendered perfectly and had nothing in it.
    core = page[page.index('name="atak_core__package_name"'):]
    core = core[: core.index("</select>")]
    assert "com.atakmap.app.civ" in core
    assert "com.plugin.one" not in core


def test_required_apps_stops_offering_atak_and_plugins(
    client: TestClient, db, artifact_storage
):
    """The filter the operator asked for, on the picker rather than only in a
    refusal: an operator should not be able to choose the wrong thing and then
    be told off for it."""
    _seed(db, artifact_storage)

    page = _form(client)
    required = page[page.index('name="required_apps__package_name"'):]
    required = required[: required.index("</select>")]

    assert "com.example.notes" in required
    assert "com.atakmap.app.civ" not in required
    assert "com.plugin.one" not in required


def test_the_plugin_picker_offers_only_plugins(client: TestClient, db, artifact_storage):
    _seed(db, artifact_storage)

    page = _form(client)
    plugins = page[page.index('name="atak_plugins__package_name"'):]
    plugins = plugins[: plugins.index("</select>")]

    assert "com.plugin.one" in plugins
    assert "com.example.notes" not in plugins
    assert "com.atakmap.app.civ" not in plugins


def test_the_options_carry_the_lines_the_warning_compares(
    client: TestClient, db, artifact_storage
):
    """⚠️ The comparison happens in the browser against these attributes, so an
    option without them is a warning that silently never fires."""
    _seed(db, artifact_storage)

    page = _form(client)

    assert 'data-atak-line="5.8.0"' in page
    assert 'data-plugin-target="5.8.0"' in page


def test_saving_the_form_writes_the_section(client: TestClient, db, artifact_storage):
    """End to end through the real parser, because everything above could pass
    while the saved policy carried nothing."""
    core, plugin, _ = _seed(db, artifact_storage)

    response = client.post(
        "/policies",
        data={
            "name": "Field ATAK",
            "policy_type": "APP_CATALOG",
            "atak_core__package_name": "com.atakmap.app.civ",
            "atak_core__version_choice": f"pin:{_sha(core)}",
            "atak_plugins__package_name": ["com.plugin.one"],
            "atak_plugins__version_choice": [f"pin:{_sha(plugin)}"],
        },
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )
    assert response.status_code in (302, 303), response.text

    from app.db.models import Policy

    spec = db.scalar(select(Policy).where(Policy.name == "Field ATAK")).latest_version.spec
    assert spec["atak_core"] == {
        "package_name": "com.atakmap.app.civ",
        "artifact_sha256": _sha(core),
    }
    assert spec["atak_plugins"][0]["artifact_sha256"] == _sha(plugin)


def test_no_atak_picked_leaves_the_field_out(client: TestClient, db, artifact_storage):
    """⚠️ Absent, not an empty object. Under HIGHEST_RANK an empty value would
    beat a lower-ranked policy that actually named an ATAK."""
    _seed(db, artifact_storage)

    client.post(
        "/policies",
        data={
            "name": "No ATAK",
            "policy_type": "APP_CATALOG",
            "atak_core__package_name": "",
            "atak_core__version_choice": "",
        },
        headers=ADMIN_HEADERS,
        follow_redirects=False,
    )

    from app.db.models import Policy

    spec = db.scalar(select(Policy).where(Policy.name == "No ATAK")).latest_version.spec
    assert "atak_core" not in (spec or {})


def test_the_warning_is_anchored_on_the_chosen_core():
    """⚠️ Not on "whichever row is ATAK". Required apps cannot contain ATAK any
    more, so the old rule would never fire again — and the point of the section
    is that the fixed point is chosen rather than inferred."""
    import pathlib

    js = pathlib.Path("app/web/static/atlas.js").read_text(encoding="utf-8")
    block = js[js.index("ATAK plugin compatibility"):]
    block = block[: block.index("/* --- ")]

    assert 'select[name="atak_core__version_choice"]' in block
    assert "may not be compatible" in block
    # Warn, never block: no disabling, no refusing to submit.
    assert "disabled" not in block


def test_the_orphaned_compat_blob_is_gone():
    """It fed the old row-guessing check and nothing reads it now. A JSON blob of
    every package rendered into every policy page and consumed by nobody is the
    kind of thing that gets resurrected by accident."""
    import pathlib

    for name in ("_policy_form.html", "policy_new.html", "policy_detail.html",
                 "profile_editor.html"):
        text = pathlib.Path("app/web/templates") / name
        assert "app_compat" not in text.read_text(encoding="utf-8"), name


# --------------------------------------------------------------------------- #
# ⚠️ Plugin detection, against the real files
#
# The synthetic fixtures set `plugin-api` only when a test asked for a plugin,
# so they could never have caught ATAK declaring one itself. These read the APKs
# in the checkout.
# --------------------------------------------------------------------------- #

_REAL = pathlib.Path("Test Files")
_REAL_PLUGIN = _REAL / "ATAK-Plugin-uastool-13.0.6-74628a10-5.8.0-civ-release.apk"
_REAL_ATAK = _REAL / "ATAK-5.8.0.4-174b425-civSmall-release.apk"
_REAL_XAPK = _REAL / "Google+Chrome_152.0.7977.82_APKPure.xapk"

needs_real = pytest.mark.skipif(
    not _REAL_PLUGIN.exists(), reason="the real APKs are not in this checkout"
)


@needs_real
def test_a_real_plugin_apk_is_detected_as_one():
    from app.artifacts.bundles import inspect

    bundle = inspect(_REAL_PLUGIN.read_bytes())

    assert bundle.package_name == "com.atakmap.android.uastool.plugin"
    assert bundle.plugin_api == "com.atakmap.app@5.8.0.CIV"


@needs_real
def test_atak_declares_plugin_api_itself_and_is_still_not_a_plugin(db, artifact_storage):
    """⚠️ The bug this file's synthetic fixtures could not have found.

    The real `ATAK-5.8.0.4-174b425-civSmall-release.apk` carries
    `plugin-api="com.atakmap.app@5.8.0.CIV"` — the same meta-data a plugin uses,
    presumably stating the API it *provides*. Detecting plugins by that tag
    alone put ATAK in the plugin picker beside its own ATAK Core picker, where a
    policy could name it twice.
    """
    from app.artifacts.bundles import inspect
    from app.services import packages as package_service

    data = _REAL_ATAK.read_bytes()
    assert inspect(data).plugin_api, "ATAK no longer declares plugin-api; revisit"

    package_service.ingest(db, artifact_storage, data)
    db.commit()

    assert "com.atakmap.app.civ" not in atak_compat.plugin_packages(db)
    assert atak_compat.is_atak("com.atakmap.app.civ")


@needs_real
def test_a_real_xapk_is_scanned_and_is_not_a_plugin(db, artifact_storage):
    """The container path reads the base APK's manifest, so an ordinary split app
    comes back with nothing — which is the answer that keeps Chrome out of the
    ATAK section."""
    from app.artifacts.bundles import inspect

    assert inspect(_REAL_XAPK.read_bytes()).plugin_api is None


# --------------------------------------------------------------------------- #
# ⚠️ A blank section must not tick the rail (W142)
# --------------------------------------------------------------------------- #


def test_the_core_build_select_starts_empty(client: TestClient, db, artifact_storage):
    """⚠️ W135's bug, in a control that did not exist then.

    The rail ticks a page when any control in it holds a value. A build select
    with no empty option is selected by the *browser* the moment the page
    renders, so a section nobody has touched reports itself as configured. The
    package select beside it always had an empty option; this one did not.
    """
    import re

    _seed(db, artifact_storage)

    page = _form(client)
    block = page[page.index('name="atak_core__version_choice"'):]
    block = block[: block.index("</select>")]
    first = re.search(r"<option[^>]*>", block)

    assert first, "the ATAK build select rendered no options at all"
    assert 'value=""' in first.group(0), (
        "the first option carries a build, so a blank policy ticks the rail"
    )


def test_every_version_select_starts_empty(client: TestClient, db, artifact_storage):
    """The same property for the whole family, so the next control of this shape
    inherits the fix instead of the bug."""
    import re

    _seed(db, artifact_storage)
    page = _form(client)

    for match in re.finditer(r'<select name="([^"]*__version_choice)"', page):
        block = page[match.end():]
        block = block[: block.index("</select>")]
        first = re.search(r"<option[^>]*>", block)
        if first is None:
            continue  # nothing uploaded for that half of the library
        assert 'value=""' in first.group(0), match.group(1)


def test_the_rail_settles_after_the_rest_of_the_page_wires_itself():
    """⚠️ The ordering half of the same bug.

    The rail block sits near the top of `atlas.js`, and modules below it disable
    controls while wiring — a build select is disabled until an app is picked,
    and a disabled control is deliberately not counted. Computing the rail only
    at that point reads the page half a tick before it has finished setting
    itself up.
    """
    import pathlib

    js = pathlib.Path("app/web/static/atlas.js").read_text(encoding="utf-8")
    block = js[js.index('panelsRoot.addEventListener("input", refresh);'):]
    block = block[: block.index("})();")]

    assert block.count("setTimeout(refresh, 0)") >= 2, (
        "the rail is computed once, before later modules disable their controls"
    )
