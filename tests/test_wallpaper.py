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

"""The WALLPAPER policy: two slots, and the device picking between them.

The server deliberately does **not** choose (D46). It sends whichever slots are
filled and the agent decides from its own `smallestScreenWidthDp` — so most of
what is worth testing here is that both slots travel intact, that a missing file
is reported rather than dropped, and that replacing an image actually moves the
fleet.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from app.policies import form_parse
from app.policies.registry import PolicyTypeError, registry
from tests.conftest import ADMIN_HEADERS

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


# --------------------------------------------------------------------------- #
# The spec
# --------------------------------------------------------------------------- #


def test_a_policy_with_no_image_is_refused():
    """Accepting it would give an operator a policy that assigns cleanly, changes
    nothing, and is indistinguishable from one that failed."""
    try:
        registry.validate_spec("WALLPAPER", {})
    except PolicyTypeError as exc:
        assert "at least one image" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an empty wallpaper policy should not validate")


def test_either_slot_alone_is_enough():
    for slot in ("tablet_file_id", "phone_file_id"):
        spec = registry.validate_spec("WALLPAPER", {slot: str(uuid.uuid4())})
        assert slot in spec


def test_both_slots_survive_together():
    tablet, phone = str(uuid.uuid4()), str(uuid.uuid4())
    spec = registry.validate_spec(
        "WALLPAPER", {"tablet_file_id": tablet, "phone_file_id": phone}
    )
    assert spec["tablet_file_id"] == tablet
    assert spec["phone_file_id"] == phone


def test_an_empty_slot_stays_unset_rather_than_null():
    """`to_stored` uses exclude_unset, so an absent field must not contribute to a
    merge. Writing null would make an empty slot beat a lower-ranked policy's image."""
    from starlette.datastructures import FormData

    parsed = form_parse.parse_form(
        "WALLPAPER",
        FormData([("tablet_file_id", str(uuid.uuid4())), ("phone_file_id", "")]),
    )
    assert "phone_file_id" not in parsed


# --------------------------------------------------------------------------- #
# Resolution — both slots travel, the device chooses
# --------------------------------------------------------------------------- #


def resolve(db, values: dict) -> dict:
    from app.services import files

    return files.resolve_wallpaper(db, values)


def test_nothing_resolves_when_no_policy_sets_a_wallpaper(db):
    assert resolve(db, {}) == {}


def test_a_missing_file_is_reported_not_dropped(db):
    """A slot pointing at a deleted upload has to look broken. Dropping it would
    read as "no wallpaper configured", which is a different and wrong story."""
    resolved = resolve(db, {"WALLPAPER": {"tablet_file_id": str(uuid.uuid4())}})

    assert resolved["tablet"]["available"] is False
    assert "sha256" not in resolved["tablet"]


def test_flags_travel_with_the_slots(db):
    resolved = resolve(
        db,
        {
            "WALLPAPER": {
                "phone_file_id": str(uuid.uuid4()),
                "lock_screen": True,
                "prevent_user_change": False,
            }
        },
    )
    assert resolved["lock_screen"] is True
    assert resolved["prevent_user_change"] is False


def test_flags_left_unset_do_not_appear(db):
    resolved = resolve(db, {"WALLPAPER": {"phone_file_id": str(uuid.uuid4())}})

    assert "lock_screen" not in resolved
    assert "prevent_user_change" not in resolved


def test_a_malformed_id_is_ignored_rather_than_raising(db):
    assert resolve(db, {"WALLPAPER": {"tablet_file_id": "not-a-uuid"}}) == {}


# --------------------------------------------------------------------------- #
# The console
# --------------------------------------------------------------------------- #


def test_the_creator_offers_wallpaper_as_a_real_section(client: TestClient):
    """It used to be a subtopic of a placeholder. Listing it in both places would
    offer the same thing twice, once working and once inert."""
    body = client.get("/policies/new", headers=ADMIN_HEADERS).text

    assert "Wallpaper" in body
    configurations = body[body.find("Configurations"):][:400]
    assert "wallpaper" not in configurations.lower()


def test_the_form_offers_both_slots_and_a_preview(client: TestClient):
    body = client.get("/policies/new/single?type=WALLPAPER", headers=ADMIN_HEADERS).text

    assert "tablet_file_id" in body
    assert "phone_file_id" in body
    assert "data-image-preview" in body
    # Both orientations, which is what was asked for.
    assert "portrait" in body and "landscape" in body


def test_serving_an_unknown_file_is_a_404_not_a_stack_trace(client: TestClient):
    response = client.get(f"/content/{uuid.uuid4()}/raw", headers=ADMIN_HEADERS)
    assert response.status_code == 404


# --------------------------------------------------------------------------- #
# It has to reach the device
# --------------------------------------------------------------------------- #


def test_the_wallpaper_reaches_the_signed_bundle(client: TestClient, enrolled, mtls_headers):
    """The gap that shipped: resolution worked, the payload carried it, and the
    bundle did not — `desired_state.build` enumerates its keys explicitly, so a new
    section is invisible until it is named there. Every other test passed while the
    device was never told."""
    session = enrolled()
    headers = mtls_headers(session["certificate_pem"])

    # force_full, because a device already at the current state_version is sent
    # no bundle at all and the assertion would pass vacuously on None.
    body = client.post(
        "/api/v1/device/checkin",
        json={"state_version": 0, "force_full": True},
        headers=headers,
    ).json()

    assert "wallpaper" in body["desired_state"]


def test_an_assigned_wallpaper_travels_with_both_slots(
    client: TestClient, db, enrolled, mtls_headers, make_policy, assign
):
    from app.db.models import Artifact, ManagedFile

    db.add(Artifact(sha256="ab" * 32, size_bytes=10, media_type="image/png"))
    images = {}
    for slot in ("tablet", "phone"):
        managed = ManagedFile(
            name=f"{slot}-image",
            original_filename=f"{slot}.png",
            media_type="image/png",
            artifact_sha256="ab" * 32,
        )
        db.add(managed)
        db.flush()
        images[slot] = str(managed.id)
    db.commit()

    session = enrolled()
    policy = make_policy("Wall", "WALLPAPER", {
        "tablet_file_id": images["tablet"],
        "phone_file_id": images["phone"],
    })
    assign(policy["id"], session["device_id"])
    db.commit()

    body = client.post(
        "/api/v1/device/checkin",
        json={"state_version": 0},
        headers=mtls_headers(session["certificate_pem"]),
    ).json()

    wallpaper = body["desired_state"]["wallpaper"]
    # Both slots travel; the device picks. The server never chooses (D46).
    assert wallpaper["tablet"]["available"] is True
    assert wallpaper["phone"]["available"] is True
    assert wallpaper["tablet"]["sha256"] == "ab" * 32
    assert wallpaper["tablet"]["url"].endswith("ab" * 32)


def test_the_enrollment_page_prompts_for_a_network_name(client: TestClient):
    """"TAK-Field" read as a value to keep rather than an example of one.

    The field only renders once a primary token exists, so the token has to be
    minted first — asserting against the tokenless page would pass vacuously.

    ⚠️ **W92 generalised the very fix this test protects.** The prompt was moved
    out of the placeholder and into a field tip: grey text inside a box reads as
    a value the field already holds, which is precisely how "TAK-Field" was
    mistaken for one. The guarantee is unchanged — the page still says what the
    field is for — so the assertion moved with the markup rather than being
    dropped.
    """
    client.post(
        "/enrollment/primary", data={"name": "T"}, headers=ADMIN_HEADERS,
        follow_redirects=False,
    )
    body = client.get("/enrollment", headers=ADMIN_HEADERS).text

    assert 'name="wifi_ssid"' in body, "the SSID field should be on the page"
    assert "The network a device joins during provisioning." in body
    assert 'placeholder="Enter Network Name"' not in body
    assert "TAK-Field" not in body


# --------------------------------------------------------------------------- #
# Device ID label (W129)
# --------------------------------------------------------------------------- #


def test_a_label_only_policy_is_valid():
    """⚠️ The validator demanded an image, on the good reasoning that an empty
    wallpaper policy is inert. A label-only policy is not inert — the agent
    draws a background — so the rule is "an image **or** the label"."""
    spec = registry.validate_spec("WALLPAPER", {"device_id_label": True})

    assert spec["device_id_label"] is True


def test_a_policy_that_sets_nothing_is_still_refused():
    """The original reasoning survives, and the message has to name the new way
    out or an operator reads it as "you must upload an image"."""
    try:
        registry.validate_spec("WALLPAPER", {})
    except PolicyTypeError as exc:
        assert "device ID label" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("an empty wallpaper policy should not validate")


def test_the_label_resolves_with_no_image_at_all(db):
    """⚠️ The case the operator asked for, and the one the resolver would have
    dropped: with no file ids it returned `{}`, which the agent reads as "no
    wallpaper policy" and acts on by *clearing* the wallpaper."""
    assert resolve(db, {"WALLPAPER": {"device_id_label": True}}) == {
        "device_id_label": True
    }


def test_the_label_resolves_alongside_an_image(db):
    resolved = resolve(
        db,
        {"WALLPAPER": {"tablet_file_id": str(uuid.uuid4()), "device_id_label": True}},
    )

    assert resolved["device_id_label"] is True
    assert "tablet" in resolved


def test_the_label_is_absent_rather_than_false_when_off(db):
    """Absent, not `false`: the agent reads a missing key as off, and an
    explicit false on every wallpaper payload would be noise."""
    resolved = resolve(db, {"WALLPAPER": {"tablet_file_id": str(uuid.uuid4())}})

    assert "device_id_label" not in resolved


def test_no_wallpaper_policy_still_resolves_to_nothing(db):
    """⚠️ The distinction the agent depends on. An empty result means "clear the
    wallpaper"; the label-only case must not look like that."""
    assert resolve(db, {}) == {}


# --------------------------------------------------------------------------- #
# ⚠️ What the agent must do with it (W129)
# --------------------------------------------------------------------------- #


def _agent(name: str) -> str:
    import pathlib

    return pathlib.Path(
        f"agent/app/src/main/java/com/taksolutions/atlasmdm/{name}"
    ).read_text(encoding="utf-8")


def test_the_label_no_longer_touches_the_wallpaper_decision():
    """⚠️ Inverted deliberately (W133). While the name was *drawn into* the
    bitmap, a label-only policy had to be kept out of `shouldClear` or it would
    have wiped the screen instead of labelling it. The drawn half is gone, so
    the two are independent: a policy naming no image restores the default
    wallpaper, and the label still shows as a window."""
    reconciler = _agent("sync/Reconciler.kt")

    assert "policyNamesAnyImage = tablet != null || phone != null," in reconciler
    assert "|| wantsLabel" not in reconciler


def test_the_label_is_settled_before_any_wallpaper_shortcut():
    """⚠️ The wallpaper paths return early all over the place — an unchanged
    image, no image, a broken slot. Every one of them would leave a device
    without its label after a process restart if the overlay were driven
    further down."""
    reconciler = _agent("sync/Reconciler.kt")

    body = reconciler[reconciler.index("private fun reconcileWallpaper") :]
    body = body[: body.index("// Commands")]

    assert body.index("DeviceIdLabelController.set(context, idLabel)") < body.index(
        "WallpaperPlan.shouldClear"
    )


def test_the_identity_actually_interpolates():
    """⚠️ The assertion above passed against a broken version, and that is the
    lesson worth keeping.

    A generator wrote Kotlin's *literal-dollar* escape into the source, so the
    identity string was the constant text `${context...}` rather than the
    screen size, and `label:$it` was the literal `$it` rather than the name.
    The key never varied, so a rename would have redrawn nothing — while a test
    matching source text sat there green.
    """
    reconciler = _agent("sync/Reconciler.kt")

    assert "${'$'}" not in reconciler, (
        "a literal-dollar escape makes a Kotlin template a constant string"
    )



def test_an_unnamed_device_falls_back_to_its_serial():
    """⚠️ Operator, W130. The first version reported an error instead, on the
    reasoning that "unnamed" on every tablet is worse than nothing — but a
    serial is not a placeholder. It is unique, so it does the job the label
    exists for: telling two tablets apart."""
    reconciler = _agent("sync/Reconciler.kt")

    body = reconciler[reconciler.index("private fun reconcileWallpaper") :]
    body = body[: body.index("// Commands")]

    assert "config.deviceName?.takeIf { it.isNotBlank() } ?: serialNumber()" in body
    assert "this device has no name" not in body


def test_the_identity_is_cached_rather_than_recomputed():
    """⚠️ `serialNumber()` logs a warning every time it takes the ANDROID_ID
    fallback, and the label asks for an identity on every reconcile. Without a
    cache the log fills with the same line on any device lacking
    READ_PHONE_STATE."""
    reconciler = _agent("sync/Reconciler.kt")
    config = _agent("core/AgentConfig.kt")

    assert "config.deviceSerial?.takeIf" in reconciler
    assert "deviceSerial" in config


def test_the_console_says_what_an_unnamed_device_shows():
    """An operator turning this on for a fleet needs to know it degrades to a
    serial rather than failing."""
    from app.policies import form_schema

    field = next(
        f for f in form_schema.form_fields("WALLPAPER") if f.name == "device_id_label"
    )

    assert "serial" in field.help
    # The lock-screen limit is the one thing an operator cannot discover by
    # looking at a device that happens to be unlocked.
    assert "lock screen" in field.help


# --------------------------------------------------------------------------- #
# ⚠️ The label as a window rather than as paint (W132)
# --------------------------------------------------------------------------- #


def test_the_label_is_a_window_laid_out_by_the_platform():
    """⚠️ Two rounds of wallpaper geometry failed for a structural reason: the
    system owns a wallpaper's crop and pan, so the agent has no say in where
    its pixels land. A window is laid out by the window manager and re-laid out
    on every rotation, which is why the clock never drifts."""
    overlay = _agent("ui/DeviceIdOverlay.kt")

    assert "TYPE_APPLICATION_OVERLAY" in overlay
    # Gravity, not coordinates: a pixel offset would drift exactly as before.
    assert "Gravity.TOP or Gravity.CENTER_HORIZONTAL" in overlay


def test_the_overlay_never_takes_a_touch():
    """⚠️ An overlay that swallowed input would be a bricked tablet, undoable
    only by removing the policy. Same warning NightOverlay carries."""
    overlay = _agent("ui/DeviceIdOverlay.kt")

    assert "FLAG_NOT_TOUCHABLE" in overlay
    assert "FLAG_NOT_FOCUSABLE" in overlay


def test_the_overlay_is_idempotent_across_reconciles():
    """It is driven every couple of minutes; an unchanged name must not stack a
    second window each time."""
    overlay = _agent("ui/DeviceIdOverlay.kt")

    assert "if (showing == name && view != null) return@post" in overlay


def test_a_rename_retexts_rather_than_recreating():
    """A remove/add cycle flickers, and renaming is the common case."""
    overlay = _agent("ui/DeviceIdOverlay.kt")

    assert "it.text = name" in overlay



def test_the_label_goes_when_the_policy_stops_asking():
    """One call handles show, rename and remove: `set(context, null)` takes it
    away, so there is no second path that can be forgotten.

    The reconcile talks to the controller, not to the window (W136): what the
    label says and when it is on screen are different questions, and the
    reconcile only answers the first."""
    reconciler = _agent("sync/Reconciler.kt")
    controller = _agent("ui/DeviceIdLabelController.kt")
    overlay = _agent("ui/DeviceIdOverlay.kt")

    assert "DeviceIdLabelController.set(context, idLabel)" in reconciler
    assert "DeviceIdOverlay" not in reconciler
    # Dropping the label stops the watcher too, or a device with no label left
    # would poll usage stats once a second forever.
    assert "HomeScreenWatcher.stop(app)" in controller
    assert "if (name.isNullOrBlank())" in overlay
    assert "removeOnMainThread(app)" in overlay


# --------------------------------------------------------------------------- #
# W136 — the label belongs to the home screen only.
#
# The decision itself is tested where it can actually run, in
# `DeviceIdLabelPlanTest` on the JVM. What is left here is the wiring: the
# things that are invisible until a fleet is already wrong.


def test_usage_access_is_optional_not_required():
    """⚠️ The one that costs a fleet.

    A *required* permission that is missing marks the device DEGRADED, and
    `agent_update.decide()` refuses to offer an update to a degraded device —
    so a permission no device has yet been granted would shut the very channel
    that ships the fix. Agent 79 did exactly that with an accessibility
    service. Usage access will be missing on every device already in the field
    the moment this build lands.
    """
    source = _agent("permissions/PermissionRequirement.kt")

    block = source[source.index("data object UsageAccess") :]
    block = block[: block.index("data object PowerMenu")]

    assert "override val optional = true" in block


def test_usage_access_is_granted_through_settings():
    """An app-op: `setPermissionGrantState` does not reach it, so there has to
    be an intent or the wizard cannot show a row at all."""
    source = _agent("permissions/PermissionRequirement.kt")

    assert "Settings.ACTION_USAGE_ACCESS_SETTINGS" in source
    # ⚠️ MODE_ALLOWED only. MODE_DEFAULT defers to the permission, which is
    # signature-protected, so treating it as granted would make every poll
    # throw.
    assert "AppOpsManager.MODE_ALLOWED" in source


def test_the_watcher_stops_when_the_screen_goes_off():
    """One binder call a second is affordable while someone is looking at the
    device and not while it sits in a bag."""
    watcher = _agent("ui/HomeScreenWatcher.kt")

    assert "Intent.ACTION_SCREEN_OFF" in watcher
    assert "if (!interactive) return" in watcher


def test_home_is_resolved_rather_than_named():
    """The operator asked for "native or the atlas launcher". Any package
    answering CATEGORY_HOME is both, plus whatever OEM shell a future fleet
    runs, with no list to keep up to date."""
    watcher = _agent("ui/HomeScreenWatcher.kt")

    assert "Intent.CATEGORY_HOME" in watcher
    assert "com.taksolutions.atlaslauncher" not in watcher


def test_the_optional_permission_warning_carries_its_own_reason():
    """The generic wording claimed every optional permission made "Device
    Settings controls explain themselves instead of working" — true of the
    power menu, false of usage access. A warning that misdescribes its own fix
    is worse than no warning."""
    reconciler = _agent("sync/Reconciler.kt")

    assert "${it.id} — ${it.rationale}" in reconciler
