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

"""What each kind of administrator may do (W495).

A **super** administrator may do everything, exactly as every administrator
could before W495. A **standard** administrator may use an admin route only
when this module allows it:

* **BASE** permissions — any administrator. Nothing here reads or changes a
  device.
* **CATEGORY** permissions — the groups of actions a super admin turns on or
  off for each standard admin (operator decision 1). What a standard admin has
  comes from a `GrantSource`;
  `app.security.authorization` applies the decision to each request.
* **SUPER** — never for a standard admin: server settings, certificates, the
  primary enrollment token, templates and archived policies, and (for now,
  W495 B7) the app and content library.

⚠️ **Deny by default.** Every admin endpoint must be in `ROUTE_PERMISSIONS`. An
endpoint that is not is refused to every standard admin, and
`tests/test_admin_permissions.py` fails until it is added. A new route is
therefore closed until someone decides, the same principle as mounting
authentication on the router (D70).

This module decides *which kind of action* a route is. *Which devices* a
standard admin may act on is a separate check (W495 B3), because a permission
to lock devices is not a permission to lock every device.
"""

from __future__ import annotations

import enum
from typing import Callable, Mapping, Protocol

from app.security.admin_auth import AdminIdentity


class Tier(str, enum.Enum):
    BASE = "base"
    CATEGORY = "category"
    SUPER = "super"


class Permission(str, enum.Enum):
    """One kind of action. The value is stable: B2 stores it per admin."""

    GUIDES = "guides"
    #: The landing page. A standard admin is sent on to the fleet from it,
    #: because the dashboard itself is about the server (W495 B3).
    HOME = "home"
    DEVICES_VIEW = "devices.view"
    DEVICES_ACTIONS = "devices.actions"  # lock, restart, check in, collect logs
    DEVICES_WIPE = "devices.wipe"  # wipe, retire, disenroll, delete, breach
    DEVICES_EDIT = "devices.edit"  # rename, attributes, group membership
    ENROLL = "enroll"
    POLICIES_VIEW = "policies.view"
    POLICIES_EDIT = "policies.edit"
    #: W501: the sites a device looked up. Not implied by DEVICES_VIEW: it is
    #: the most personal record ATLAS keeps, granted on its own (operator).
    WEB_ACTIVITY_VIEW = "web_activity.view"
    SUPER = "super"

    @property
    def tier(self) -> Tier:
        if self in (Permission.GUIDES, Permission.HOME):
            return Tier.BASE
        if self is Permission.SUPER:
            return Tier.SUPER
        return Tier.CATEGORY


#: The permissions a super admin can grant to a standard admin.
CATEGORIES: frozenset[Permission] = frozenset(
    p for p in Permission if p.tier is Tier.CATEGORY
)

#: What the super admin reads on Admin › Administrators, in the order shown.
CATEGORY_LABELS: dict[Permission, tuple[str, str]] = {
    Permission.DEVICES_VIEW: ("View devices", "The fleet, device pages, logs, reports for their devices."),
    Permission.DEVICES_ACTIONS: ("Device actions", "Ping, lock, locate, restart an app, collect logs, check in."),
    Permission.DEVICES_WIPE: ("Wipe and remove", "Wipe, retire, disenroll, delete, breach mode."),
    Permission.DEVICES_EDIT: ("Edit devices", "Rename, attributes, and putting their devices in their groups."),
    Permission.ENROLL: ("Enroll", "Tokens and QR codes that place devices in their groups."),
    Permission.POLICIES_VIEW: ("View policies", "Policies whose every target is theirs."),
    Permission.POLICIES_EDIT: ("Edit policies", "Create and change those policies, and assign them to their devices."),
    Permission.WEB_ACTIVITY_VIEW: ("View web activity", "The sites their devices looked up (Web Filtering, Log web activity). Every view is audited."),
}

P = Permission

#: Every admin endpoint, keyed by `module:qualname`, and the permission it needs.
#:
#: ⚠️ Keyed by endpoint, not by path, so a route moved to a new path keeps its
#: decision and a renamed function fails the completeness test instead of
#: silently losing it.
#:
#: ⚠️ `app.api.routers.commands:enqueue_command` queues any command type, wipe
#: included, through one path. It is listed as DEVICES_ACTIONS and asks for
#: DEVICES_WIPE itself when the command destroys data (`commands.DESTRUCTIVE`).
#: The console's `device_action_form` offers no destructive action.
#:
#: ⚠️ The three `app.api.routers.effective` routes are SUPER (W495 security
#: review): they return resolved values unredacted, and preview loads any policy
#: by id. A standard admin sees the device page's masked view instead.
ROUTE_PERMISSIONS: Mapping[str, Permission] = {
    # --- GUIDES ---
    "app.web.routes:guides_page": P.GUIDES,  # GET /guides
    "app.web.routes:guide_view": P.GUIDES,  # GET /guides/{category}/{slug}
    # --- DEVICES_VIEW ---
    "app.api.routers.inventory:list_devices": P.DEVICES_VIEW,  # GET /api/v1/devices
    "app.api.routers.inventory:get_device": P.DEVICES_VIEW,  # GET /api/v1/devices/{device_id}
    "app.api.routers.atak_logs:list_atak_logs": P.DEVICES_VIEW,  # GET /api/v1/devices/{device_id}/atak-logs
    "app.api.routers.admin_settings:device_attributes": P.DEVICES_VIEW,  # GET /api/v1/devices/{device_id}/attributes
    "app.api.routers.commands:list_commands": P.DEVICES_VIEW,  # GET /api/v1/devices/{device_id}/commands
    "app.api.routers.commands:get_desired_state": P.DEVICES_VIEW,  # GET /api/v1/devices/{device_id}/desired-state
    "app.api.routers.effective:get_effective_policy": P.SUPER,  # GET /api/v1/devices/{device_id}/effective-policy
    "app.api.routers.effective:explain_field": P.SUPER,  # GET /api/v1/devices/{device_id}/effective-policy/explain/{policy_type}/{field_name}
    "app.api.routers.effective:preview_effective_policy": P.SUPER,  # POST /api/v1/devices/{device_id}/effective-policy/preview
    "app.api.routers.files:list_device_selections": P.DEVICES_VIEW,  # GET /api/v1/devices/{device_id}/file-selections
    "app.api.routers.inventory:list_device_identifiers": P.DEVICES_VIEW,  # GET /api/v1/devices/{device_id}/identifiers
    "app.api.routers.device_logs:list_logs": P.DEVICES_VIEW,  # GET /api/v1/devices/{device_id}/logs
    "app.api.routers.device_logs:read_log": P.DEVICES_VIEW,  # GET /api/v1/devices/{device_id}/logs/{bundle_id}
    "app.api.routers.inventory:list_groups": P.DEVICES_VIEW,  # GET /api/v1/groups
    "app.web.routes:home_dashboard": P.HOME,  # GET /dashboard
    "app.web.routes:home_dashboard_data": P.SUPER,  # GET /dashboard/data
    "app.web.routes:home_dashboard_map": P.SUPER,  # GET /dashboard/map
    "app.web.routes:home_dashboard_trends": P.SUPER,  # GET /dashboard/trends
    "app.web.routes:device_detail": P.DEVICES_VIEW,  # GET /devices/{device_id}
    "app.web.routes:download_atak_log": P.DEVICES_VIEW,  # GET /devices/{device_id}/atak-logs/{log_id}/download
    "app.web.routes:download_atak_prefs": P.DEVICES_VIEW,  # GET /devices/{device_id}/atak-prefs/{extract_id}/download
    "app.web.routes:location_history": P.DEVICES_VIEW,  # GET /devices/{device_id}/location-history
    "app.web.routes:location_history_csv": P.DEVICES_VIEW,  # GET /devices/{device_id}/location-history.csv
    # --- WEB_ACTIVITY_VIEW (W501) ---
    "app.web.routes:web_activity": P.WEB_ACTIVITY_VIEW,  # GET /devices/{device_id}/web-activity
    "app.web.routes:web_activity_csv": P.WEB_ACTIVITY_VIEW,  # GET /devices/{device_id}/web-activity.csv
    "app.web.routes:web_activity_search": P.WEB_ACTIVITY_VIEW,  # GET /web-activity
    "app.web.routes:view_log": P.DEVICES_VIEW,  # GET /devices/{device_id}/logs/{bundle_id}
    "app.web.routes:download_log": P.DEVICES_VIEW,  # GET /devices/{device_id}/logs/{bundle_id}/download
    "app.web.routes:view_package_report": P.DEVICES_VIEW,  # GET /devices/{device_id}/package-report
    "app.web.routes:download_package_report": P.DEVICES_VIEW,  # GET /devices/{device_id}/package-report.csv
    "app.web.routes:device_policy_config_csv": P.DEVICES_VIEW,  # GET /devices/{device_id}/policy-config.csv
    "app.web.routes:device_report_zip": P.DEVICES_VIEW,  # GET /devices/{device_id}/report.zip
    "app.web.routes:device_section_csv": P.DEVICES_VIEW,  # GET /devices/{device_id}/sections/{section_key}/{table_key}.csv
    "app.web.routes:dashboard": P.DEVICES_VIEW,  # GET /fleet
    "app.web.routes:groups_page": P.DEVICES_VIEW,  # GET /groups
    "app.web.routes:group_detail_page": P.DEVICES_VIEW,  # GET /groups/{group_id}
    "app.web.routes:reports_page": P.HOME,  # GET /reports
    "app.web.routes:report_view": P.HOME,  # GET /reports/{key}
    # --- DEVICES_ACTIONS ---
    "app.api.routers.commands:cancel_command": P.DEVICES_ACTIONS,  # POST /api/v1/commands/{command_id}/cancel
    "app.api.routers.inventory:force_checkin": P.DEVICES_ACTIONS,  # POST /api/v1/devices/{device_id}/checkin
    "app.api.routers.commands:enqueue_command": P.DEVICES_ACTIONS,  # POST /api/v1/devices/{device_id}/commands
    "app.web.routes:device_action_form": P.DEVICES_ACTIONS,  # POST /devices/{device_id}/action/{action}
    "app.web.routes:request_atak_prefs": P.DEVICES_ACTIONS,  # POST /devices/{device_id}/atak-prefs/extract
    "app.web.routes:delete_atak_prefs": P.DEVICES_ACTIONS,  # POST /devices/{device_id}/atak-prefs/{extract_id}/delete
    "app.web.routes:force_checkin_form": P.DEVICES_ACTIONS,  # POST /devices/{device_id}/checkin
    "app.web.routes:request_logs": P.DEVICES_ACTIONS,  # POST /devices/{device_id}/collect-logs
    "app.web.routes:request_package_report": P.DEVICES_ACTIONS,  # POST /devices/{device_id}/package-report
    "app.web.routes:reset_code_attempts_form": P.DEVICES_ACTIONS,  # POST /devices/{device_id}/reset-code-attempts
    "app.web.routes:restart_app_form": P.DEVICES_ACTIONS,  # POST /devices/{device_id}/restart-app
    # --- DEVICES_WIPE ---
    "app.api.routers.inventory:delete_device": P.DEVICES_WIPE,  # DELETE /api/v1/devices/{device_id}
    "app.api.routers.inventory:retire_device": P.DEVICES_WIPE,  # POST /api/v1/devices/{device_id}/retire
    "app.web.routes:engage_breach_form": P.DEVICES_WIPE,  # POST /devices/{device_id}/breach
    "app.web.routes:clear_breach_form": P.DEVICES_WIPE,  # POST /devices/{device_id}/breach/clear
    "app.web.routes:delete_device_form": P.DEVICES_WIPE,  # POST /devices/{device_id}/delete
    "app.web.routes:disenroll_device_form": P.DEVICES_WIPE,  # POST /devices/{device_id}/disenroll
    "app.web.routes:retire_device_form": P.DEVICES_WIPE,  # POST /devices/{device_id}/retire
    # --- DEVICES_EDIT ---
    "app.api.routers.inventory:update_device": P.DEVICES_EDIT,  # PATCH /api/v1/devices/{device_id}
    "app.api.routers.admin_settings:set_device_attribute": P.DEVICES_EDIT,  # PUT /api/v1/devices/{device_id}/attributes
    "app.api.routers.inventory:set_group_devices": P.DEVICES_EDIT,  # PUT /api/v1/groups/{group_id}/devices
    "app.web.routes:remove_device_assignment": P.DEVICES_EDIT,  # POST /devices/{device_id}/assignments/{assignment_id}/remove
    "app.web.routes:rerank_device_assignment": P.DEVICES_EDIT,  # POST /devices/{device_id}/assignments/{assignment_ref}/rank
    "app.web.routes:set_device_attribute_form": P.DEVICES_EDIT,  # POST /devices/{device_id}/attributes
    "app.web.routes:rename_device_form": P.DEVICES_EDIT,  # POST /devices/{device_id}/rename
    "app.web.routes:set_group_devices_form": P.DEVICES_EDIT,  # POST /groups/{group_id}/devices
    # --- ENROLL ---
    "app.api.routers.enrollment:create_enrollment_token": P.ENROLL,  # POST /api/v1/enrollment-tokens
    "app.api.routers.enrollment:list_enrollment_tokens": P.ENROLL,  # GET /api/v1/enrollment-tokens
    "app.api.routers.enrollment:revoke_enrollment_token": P.ENROLL,  # POST /api/v1/enrollment-tokens/{token_id}/revoke
    "app.api.routers.enrollment:render_provisioning_payloads": P.ENROLL,  # POST /api/v1/provisioning/payloads
    "app.web.routes:enrollment_page": P.ENROLL,  # GET /enrollment
    "app.web.routes:generate_qr": P.ENROLL,  # POST /enrollment/qr
    "app.web.routes:generate_qr_get": P.ENROLL,  # GET /enrollment/qr
    "app.web.routes:forget_saved_qr": P.ENROLL,  # POST /enrollment/qr/{recipe_id}/forget
    "app.web.routes:show_saved_qr": P.ENROLL,  # POST /enrollment/qr/{recipe_id}/show
    "app.web.routes:show_saved_qr_get": P.ENROLL,  # GET /enrollment/qr/{recipe_id}/show
    # --- POLICIES_VIEW ---
    "app.api.routers.assignments:list_assignments": P.POLICIES_VIEW,  # GET /api/v1/assignments
    "app.api.routers.policies:list_policies": P.POLICIES_VIEW,  # GET /api/v1/policies
    "app.api.routers.policies:get_policy": P.POLICIES_VIEW,  # GET /api/v1/policies/{policy_id}
    "app.api.routers.policy_types:list_policy_types": P.POLICIES_VIEW,  # GET /api/v1/policy-types
    "app.api.routers.policy_types:get_policy_type": P.POLICIES_VIEW,  # GET /api/v1/policy-types/{name}
    "app.api.routers.profiles:list_profiles": P.POLICIES_VIEW,  # GET /api/v1/profiles
    "app.api.routers.profiles:get_profile": P.POLICIES_VIEW,  # GET /api/v1/profiles/{profile_id}
    "app.web.routes:list_policies": P.POLICIES_VIEW,  # GET /policies
    "app.web.routes:policy_detail": P.POLICIES_VIEW,  # GET /policies/{policy_id}
    "app.web.routes:profile_detail": P.POLICIES_VIEW,  # GET /profiles/{profile_id}
    "app.web.routes:export_policy_config": P.POLICIES_VIEW,  # GET /profiles/{profile_id}/export
    # --- POLICIES_EDIT ---
    "app.api.routers.assignments:create_assignment": P.POLICIES_EDIT,  # POST /api/v1/assignments
    "app.api.routers.assignments:delete_assignment": P.POLICIES_EDIT,  # DELETE /api/v1/assignments/{assignment_id}
    "app.api.routers.assignments:update_assignment": P.POLICIES_EDIT,  # PATCH /api/v1/assignments/{assignment_id}
    "app.api.routers.policies:create_policy": P.POLICIES_EDIT,  # POST /api/v1/policies
    "app.api.routers.policies:delete_policy": P.SUPER,  # DELETE /api/v1/policies/{policy_id}
    "app.api.routers.policies:archive_policy": P.SUPER,  # POST /api/v1/policies/{policy_id}/archive
    "app.api.routers.policies:clone_policy": P.POLICIES_EDIT,  # POST /api/v1/policies/{policy_id}/clone
    "app.api.routers.policies:restore_policy": P.SUPER,  # POST /api/v1/policies/{policy_id}/restore
    "app.api.routers.assignments:set_policy_targets": P.POLICIES_EDIT,  # PUT /api/v1/policies/{policy_id}/targets
    "app.api.routers.policies:publish_version": P.POLICIES_EDIT,  # POST /api/v1/policies/{policy_id}/versions
    "app.api.routers.profiles:create_profile": P.POLICIES_EDIT,  # POST /api/v1/profiles
    "app.api.routers.profiles:delete_profile": P.SUPER,  # DELETE /api/v1/profiles/{profile_id}
    "app.api.routers.profiles:archive_profile": P.SUPER,  # POST /api/v1/profiles/{profile_id}/archive
    "app.api.routers.profiles:restore_profile": P.SUPER,  # POST /api/v1/profiles/{profile_id}/restore
    "app.api.routers.profiles:remove_section": P.POLICIES_EDIT,  # DELETE /api/v1/profiles/{profile_id}/sections/{category_key}
    "app.api.routers.profiles:upsert_section": P.POLICIES_EDIT,  # PUT /api/v1/profiles/{profile_id}/sections/{category_key}
    "app.api.routers.profiles:set_profile_targets": P.POLICIES_EDIT,  # PUT /api/v1/profiles/{profile_id}/targets
    "app.web.routes:assign_policy_to_group_form": P.POLICIES_EDIT,  # POST /groups/{group_id}/assignments
    "app.web.routes:remove_group_assignment_form": P.POLICIES_EDIT,  # POST /groups/{group_id}/assignments/{assignment_id}/remove
    "app.web.routes:rerank_group_assignment": P.POLICIES_EDIT,  # POST /groups/{group_id}/assignments/{assignment_ref}/rank
    "app.web.routes:create_policy": P.POLICIES_EDIT,  # POST /policies
    "app.web.routes:upload_policy_animation_file": P.POLICIES_EDIT,  # POST /policies/animation-file
    "app.web.routes:app_activities": P.POLICIES_EDIT,  # GET /policies/app-activities
    "app.web.routes:upload_app_config_file": P.POLICIES_EDIT,  # POST /policies/app-config-file/upload
    "app.web.routes:app_config_schema": P.POLICIES_EDIT,  # GET /policies/app-config-schema
    "app.web.routes:import_atak_pref": P.POLICIES_EDIT,  # POST /policies/atak-pref/import
    "app.web.routes:import_atak_toolbars": P.POLICIES_EDIT,  # POST /policies/atak-pref/toolbars
    "app.web.routes:clone_policy_form": P.POLICIES_EDIT,  # POST /policies/clone
    "app.web.routes:create_policy_data_package": P.POLICIES_EDIT,  # POST /policies/data-package/create
    "app.web.routes:upload_policy_data_package": P.POLICIES_EDIT,  # POST /policies/data-package/upload
    "app.web.routes:device_variables_catalogue": P.POLICIES_EDIT,  # GET /policies/device-variables
    "app.web.routes:upload_policy_dted": P.POLICIES_EDIT,  # POST /policies/dted/upload
    "app.web.routes:upload_policy_file": P.POLICIES_EDIT,  # POST /policies/file/upload
    "app.web.routes:geocode_lookup": P.POLICIES_EDIT,  # GET /policies/geocode
    "app.web.routes:geocode_suggest": P.POLICIES_EDIT,  # GET /policies/geocode/suggest
    "app.web.routes:upload_policy_image_form": P.POLICIES_EDIT,  # POST /policies/image
    "app.web.routes:new_policy_page": P.POLICIES_EDIT,  # GET /policies/new
    "app.web.routes:new_single_policy_page": P.POLICIES_EDIT,  # GET /policies/new/single
    "app.web.routes:pref_schema": P.POLICIES_EDIT,  # GET /policies/pref-schema
    "app.web.routes:reported_fonts": P.POLICIES_EDIT,  # GET /policies/reported-fonts
    "app.web.routes:upload_tak_cert": P.POLICIES_EDIT,  # POST /policies/tak-cert/upload
    "app.web.routes:test_web_filter": P.POLICIES_EDIT,  # POST /policies/web-filter/test
    "app.web.routes:archive_policy_form": P.SUPER,  # POST /policies/{policy_id}/archive
    "app.web.routes:delete_policy_form": P.SUPER,  # POST /policies/{policy_id}/delete
    "app.web.routes:set_policy_deployment": P.POLICIES_EDIT,  # POST /policies/{policy_id}/deployment
    "app.web.routes:rename_policy_form": P.POLICIES_EDIT,  # POST /policies/{policy_id}/rename
    "app.web.routes:restore_policy_form": P.SUPER,  # POST /policies/{policy_id}/restore
    "app.web.routes:set_targets": P.POLICIES_EDIT,  # POST /policies/{policy_id}/targets
    "app.web.routes:publish_version": P.POLICIES_EDIT,  # POST /policies/{policy_id}/versions
    "app.web.routes:create_profile_form": P.POLICIES_EDIT,  # POST /profiles
    "app.web.routes:save_profile_form": P.POLICIES_EDIT,  # POST /profiles/{profile_id}
    "app.web.routes:archive_profile_form": P.SUPER,  # POST /profiles/{profile_id}/archive
    "app.web.routes:clone_profile_form": P.POLICIES_EDIT,  # POST /profiles/{profile_id}/clone
    "app.web.routes:delete_profile_form": P.SUPER,  # POST /profiles/{profile_id}/delete
    "app.web.routes:set_profile_deployment": P.POLICIES_EDIT,  # POST /profiles/{profile_id}/deployment
    "app.web.routes:rename_profile_form": P.POLICIES_EDIT,  # POST /profiles/{profile_id}/rename
    "app.web.routes:restore_profile_form": P.SUPER,  # POST /profiles/{profile_id}/restore
    "app.web.routes:upsert_section_form": P.POLICIES_EDIT,  # POST /profiles/{profile_id}/sections/{category_key}
    "app.web.routes:remove_section_form": P.POLICIES_EDIT,  # POST /profiles/{profile_id}/sections/{category_key}/remove
    "app.web.routes:set_profile_targets_form": P.POLICIES_EDIT,  # POST /profiles/{profile_id}/targets
    # --- library: SUPER for now (W495 B7); was LIBRARY_VIEW ---
    "app.api.routers.app_groups:list_groups": P.SUPER,  # GET /api/v1/app-groups
    "app.api.routers.app_groups:get_group": P.SUPER,  # GET /api/v1/app-groups/{group_id}
    "app.api.routers.files:list_files": P.SUPER,  # GET /api/v1/files
    "app.api.routers.files:get_file": P.SUPER,  # GET /api/v1/files/{file_id}
    "app.api.routers.packages:list_packages": P.SUPER,  # GET /api/v1/packages
    "app.api.routers.packages:get_package": P.SUPER,  # GET /api/v1/packages/{package_id}
    "app.api.routers.packages:get_package_icon": P.SUPER,  # GET /api/v1/packages/{package_id}/icon
    "app.web.routes:apps_page": P.SUPER,  # GET /apps
    "app.web.routes:play_search": P.SUPER,  # GET /apps/play/search
    "app.web.routes:play_versions": P.SUPER,  # GET /apps/play/versions
    "app.web.routes:repo_import_status": P.SUPER,  # GET /apps/repo/import/{job_id}
    "app.web.routes:repo_search": P.SUPER,  # GET /apps/repo/search
    "app.web.routes:repo_versions": P.SUPER,  # GET /apps/repo/versions
    "app.web.routes:web_shortcut_page": P.SUPER,  # GET /apps/shortcuts/{shortcut_id}
    "app.web.routes:web_shortcut_icon": P.SUPER,  # GET /apps/shortcuts/{shortcut_id}/icon.png
    "app.web.routes:import_tpc_plugin_status": P.SUPER,  # GET /apps/tpc/import/{job_id}
    "app.web.routes:download_app_version": P.SUPER,  # GET /apps/versions/{version_id}/download
    "app.web.routes:content_page": P.SUPER,  # GET /content
    "app.web.routes:content_download": P.SUPER,  # GET /content/{file_id}/download
    "app.web.routes:content_raw": P.SUPER,  # GET /content/{file_id}/raw
    "app.web.routes:storefront_detail_page": P.SUPER,  # GET /storefronts/{storefront_id}
    # --- library: SUPER for now (W495 B7); was LIBRARY_EDIT ---
    "app.api.routers.app_groups:create_group": P.SUPER,  # POST /api/v1/app-groups
    "app.api.routers.app_groups:update_group": P.SUPER,  # PATCH /api/v1/app-groups/{group_id}
    "app.api.routers.app_groups:set_members": P.SUPER,  # PUT /api/v1/app-groups/{group_id}/members
    "app.api.routers.files:upload_file": P.SUPER,  # POST /api/v1/files
    "app.api.routers.files:update_file": P.SUPER,  # PATCH /api/v1/files/{file_id}
    "app.api.routers.packages:upload_package": P.SUPER,  # POST /api/v1/packages
    "app.api.routers.packages:update_package": P.SUPER,  # PATCH /api/v1/packages/{package_id}
    "app.web.routes:create_app_group_form": P.SUPER,  # POST /app-groups
    "app.web.routes:set_app_group_members_form": P.SUPER,  # POST /app-groups/{group_id}/members
    "app.web.routes:preview_app_upload": P.SUPER,  # POST /apps/preview-upload
    "app.web.routes:repo_import_form": P.SUPER,  # POST /apps/repo/import
    "app.web.routes:create_web_shortcut": P.SUPER,  # POST /apps/shortcuts
    "app.web.routes:web_shortcut_site_icon": P.SUPER,  # POST /apps/shortcuts/site-icon
    "app.web.routes:update_web_shortcut": P.SUPER,  # POST /apps/shortcuts/{shortcut_id}
    "app.web.routes:takwerx_import_form": P.SUPER,  # POST /apps/takwerx/import
    "app.web.routes:import_tpc_plugin_form": P.SUPER,  # POST /apps/tpc/import
    "app.web.routes:upload_app_form": P.SUPER,  # POST /apps/upload
    "app.web.routes:make_animation_form": P.SUPER,  # POST /content/animations
    "app.web.routes:create_data_package_form": P.SUPER,  # POST /content/data-package/create
    "app.web.routes:resolve_data_package_conflict": P.SUPER,  # POST /content/data-package/resolve
    "app.web.routes:upload_data_package_form": P.SUPER,  # POST /content/data-package/upload
    "app.web.routes:upload_content_form": P.SUPER,  # POST /content/upload
    "app.web.routes:edit_content_form": P.SUPER,  # POST /content/{file_id}/edit
    "app.web.routes:set_package_visibility": P.SUPER,  # POST /content/{file_id}/visibility
    "app.web.routes:create_storefront_form": P.SUPER,  # POST /storefronts
    "app.web.routes:rename_storefront_form": P.SUPER,  # POST /storefronts/{storefront_id}
    "app.web.routes:set_storefront_items_form": P.SUPER,  # POST /storefronts/{storefront_id}/items
    # --- SUPER ---
    "app.web.routes:admin_page": P.SUPER,  # GET /admin
    # W495: who the administrators are and what each standard admin reaches.
    "app.web.routes:administrators_page": P.SUPER,  # GET /admin/administrators
    "app.web.routes:administrator_page": P.SUPER,  # GET /admin/administrators/{username}
    "app.web.routes:save_administrator": P.SUPER,  # POST /admin/administrators/{username}
    "app.web.routes:forget_administrator": P.SUPER,  # POST /admin/administrators/{username}/forget
    "app.web.routes:publish_agent_build_form": P.SUPER,  # POST /admin/agent/publish
    "app.web.routes:add_alert_recipient_form": P.SUPER,  # POST /admin/alerts/recipients
    "app.web.routes:delete_alert_recipient_form": P.SUPER,  # POST /admin/alerts/recipients/{recipient_id}/delete
    "app.web.routes:set_alert_recipient_enabled_form": P.SUPER,  # POST /admin/alerts/recipients/{recipient_id}/enabled
    "app.web.routes:add_alert_rule_form": P.SUPER,  # POST /admin/alerts/rules
    "app.web.routes:check_alert_rule_now_form": P.SUPER,  # POST /admin/alerts/rules/{rule_id}/check
    "app.web.routes:delete_alert_rule_form": P.SUPER,  # POST /admin/alerts/rules/{rule_id}/delete
    "app.web.routes:set_alert_rule_enabled_form": P.SUPER,  # POST /admin/alerts/rules/{rule_id}/enabled
    "app.web.routes:set_alert_rule_schedule_form": P.SUPER,  # POST /admin/alerts/rules/{rule_id}/schedule
    "app.web.routes:create_attribute_form": P.SUPER,  # POST /admin/attributes
    "app.web.routes:delete_attribute_form": P.SUPER,  # POST /admin/attributes/{attribute_id}/delete
    "app.web.routes:audit_log_page": P.HOME,  # GET /admin/audit
    "app.web.routes:audit_log_csv": P.HOME,  # GET /admin/audit.csv
    "app.web.routes:set_audit_retention": P.SUPER,  # POST /admin/audit/retention
    "app.web.routes:save_breach_section_form": P.SUPER,  # POST /admin/breach/{category_key}
    "app.web.routes:set_certificate_lifetime": P.SUPER,  # POST /admin/certificates/lifetime
    "app.web.routes:revoke_cert_form": P.SUPER,  # POST /admin/certs/{cert_id}/revoke
    "app.web.routes:add_distrusted_ca_form": P.SUPER,  # POST /admin/distrusted-cas
    "app.web.routes:remove_distrusted_ca_form": P.SUPER,  # POST /admin/distrusted-cas/{entry_id}/delete
    "app.web.routes:google_play_link_form": P.SUPER,  # POST /admin/google-play/link
    "app.web.routes:google_play_unlink_form": P.SUPER,  # POST /admin/google-play/unlink
    "app.web.routes:deactivate_knox": P.SUPER,  # POST /admin/knox/deactivate
    "app.web.routes:probe_mail_relay_form": P.SUPER,  # POST /admin/mail/probe
    "app.web.routes:regenerate_security_code": P.SUPER,  # POST /admin/security-code/regenerate
    "app.web.routes:set_reinstatement": P.SUPER,  # POST /admin/security-code/reinstate
    "app.web.routes:save_admin_settings_form": P.SUPER,  # POST /admin/settings/{group_key}
    "app.web.routes:start_tak_ca_retirement_form": P.SUPER,  # POST /admin/tak-ca-retirement
    "app.web.routes:stop_tak_ca_retirement_form": P.SUPER,  # POST /admin/tak-ca-retirement/stop
    "app.web.routes:takgov_poll_form": P.SUPER,  # POST /admin/takgov/poll
    "app.web.routes:takgov_start_form": P.SUPER,  # POST /admin/takgov/start
    "app.web.routes:takgov_unlink_form": P.SUPER,  # POST /admin/takgov/unlink
    "app.api.routers.app_groups:delete_group": P.SUPER,  # DELETE /api/v1/app-groups/{group_id}
    "app.api.routers.commands:get_bundle_signing_key": P.SUPER,  # GET /api/v1/bundle-signing-key
    "app.api.routers.admin_settings:create_attribute": P.SUPER,  # POST /api/v1/custom-attributes
    "app.api.routers.admin_settings:list_attributes": P.SUPER,  # GET /api/v1/custom-attributes
    "app.api.routers.admin_settings:delete_attribute": P.SUPER,  # DELETE /api/v1/custom-attributes/{attribute_id}
    "app.api.routers.inventory:create_device": P.SUPER,  # POST /api/v1/devices
    "app.api.routers.enrollment:create_primary_enrollment_token": P.SUPER,  # POST /api/v1/enrollment-tokens/primary
    "app.api.routers.enrollment:get_primary_enrollment_token": P.SUPER,  # GET /api/v1/enrollment-tokens/primary
    "app.api.routers.enrollment:issue_primary_enrollment_qr": P.SUPER,  # POST /api/v1/enrollment-tokens/primary/qr
    "app.api.routers.files:delete_file": P.SUPER,  # DELETE /api/v1/files/{file_id}
    "app.api.routers.inventory:create_group": P.SUPER,  # POST /api/v1/groups
    "app.api.routers.packages:delete_package": P.SUPER,  # DELETE /api/v1/packages/{package_id}
    "app.api.routers.packages:delete_package_version": P.SUPER,  # DELETE /api/v1/packages/{package_id}/versions/{version_id}
    "app.web.routes:delete_app_group_form": P.SUPER,  # POST /app-groups/{group_id}/delete
    "app.web.routes:delete_web_shortcut": P.SUPER,  # POST /apps/shortcuts/{shortcut_id}/delete
    "app.web.routes:delete_app_version_form": P.SUPER,  # POST /apps/versions/{version_id}/delete
    "app.web.routes:delete_app_form": P.SUPER,  # POST /apps/{package_id}/delete
    "app.web.routes:delete_content_form": P.SUPER,  # POST /content/{file_id}/delete
    "app.web.routes:create_primary": P.SUPER,  # POST /enrollment/primary
    "app.web.routes:retire_primary": P.SUPER,  # POST /enrollment/retire
    "app.web.routes:inventory_export": P.SUPER,  # GET /fleet/inventory.csv
    "app.web.routes:inventory_apply": P.SUPER,  # POST /fleet/inventory/apply
    "app.web.routes:inventory_preview": P.SUPER,  # POST /fleet/inventory/preview
    "app.web.routes:create_group_form": P.SUPER,  # POST /groups
    "app.web.routes:delete_group_form": P.SUPER,  # POST /groups/{group_id}/delete
    "app.web.routes:rename_group_form": P.SUPER,  # POST /groups/{group_id}/rename
    "app.web.routes:export_policy_configs": P.SUPER,  # GET /policies/export
    "app.web.routes:import_policy_configs": P.SUPER,  # POST /policies/import
    "app.web.routes:preview_policy_import": P.SUPER,  # POST /policies/import/preview
    "app.web.routes:delete_storefront_form": P.SUPER,  # POST /storefronts/{storefront_id}/delete
}


def endpoint_key(endpoint: Callable) -> str:
    return f"{endpoint.__module__}:{endpoint.__qualname__}"


def permission_for(endpoint: Callable | None) -> Permission | None:
    """The permission an endpoint needs, or None when nobody has decided."""
    if endpoint is None:
        return None
    return ROUTE_PERMISSIONS.get(endpoint_key(endpoint))


class GrantSource(Protocol):
    """Where a standard admin's granted categories come from."""

    def categories_for(self, identity: AdminIdentity) -> frozenset[Permission]: ...


def allows(
    identity: AdminIdentity,
    permission: Permission | None,
    granted: frozenset[Permission],
) -> bool:
    """Whether this administrator may use a route that needs `permission`."""
    if not identity.is_standard:
        return True
    if permission is None:
        return False
    if permission.tier is Tier.BASE:
        return True
    if permission.tier is Tier.SUPER:
        return False
    return permission in granted
