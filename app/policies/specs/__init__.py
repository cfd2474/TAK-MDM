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

"""Policy spec schemas.

Importing this package registers every built-in policy type. Adding a new type
means adding a module here and registering it — the resolver never changes (OCP).
"""

from app.policies.specs.app_catalog import AppCatalogSpec
from app.policies.specs.base import PolicySpec
from app.policies.specs.customizations import CustomizationsSpec
from app.policies.specs.files import FilesSpec
from app.policies.specs.network_data_use import NetworkDataUseSpec
from app.policies.specs.networks import NetworksSpec
from app.policies.specs.password import PasswordSpec
from app.policies.specs.restrictions import RestrictionsSpec
from app.policies.specs.wallpaper import WallpaperSpec

__all__ = [
    "AppCatalogSpec",
    "CustomizationsSpec",
    "FilesSpec",
    "NetworkDataUseSpec",
    "NetworksSpec",
    "PasswordSpec",
    "PolicySpec",
    "RestrictionsSpec",
    "WallpaperSpec",
]
