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

"""Application configuration."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings, overridable by environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="TAKMDM_", extra="ignore")

    database_url: str = "postgresql+psycopg://takmdm:takmdm@localhost:5432/takmdm"
    sql_echo: bool = False

    # Base URL devices use to reach this server. Goes into provisioning payloads.
    server_url: str = "https://mdm.example.org"

    # --- Artifact storage ----------------------------------------------------
    artifact_dir: Path = Path("artifacts")
    # 2 GiB. XAPKs with OBB payloads get large; nginx has a matching limit.
    max_upload_bytes: int = 2 * 1024 * 1024 * 1024

    # --- Device identity PKI -------------------------------------------------
    pki_dir: Path = Path("pki")
    ca_common_name: str = "TAK-MDM Device CA"
    ca_validity_days: int = 3650
    device_cert_validity_days: int = 825

    # mTLS is terminated at the reverse proxy, which forwards the verified client
    # certificate in this header. The app re-verifies chain, validity, and
    # revocation, but possession of the private key is proven by the TLS handshake
    # at the proxy — so this header MUST be stripped from inbound requests by that
    # proxy, and the app must never be exposed directly to the internet.
    client_cert_header: str = "x-ssl-client-cert"

    # --- Enrollment ----------------------------------------------------------
    enrollment_token_ttl_hours: int = 168  # 7 days

    # --- Check-in ------------------------------------------------------------
    # WorkManager's periodic floor is 15 minutes, so anything lower is wishful.
    checkin_interval_seconds: int = 900
    # Spread wake-ups so a fleet that lost power together does not return as a
    # thundering herd.
    checkin_jitter_ratio: float = 0.2

    # --- Agent APK, for provisioning payloads --------------------------------
    agent_package_name: str = "org.takmdm.agent"
    agent_admin_receiver: str = "org.takmdm.agent/.MdmDeviceAdminReceiver"
    agent_apk_url: str = "https://mdm.example.org/static/agent.apk"
    # base64url SHA-256 of the agent's signing certificate. Android refuses to
    # provision if this does not match the downloaded APK.
    agent_signature_checksum: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
