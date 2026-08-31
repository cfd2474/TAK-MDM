"""Policy spec schemas.

Importing this package registers every built-in policy type. Adding a new type
means adding a module here and registering it — the resolver never changes (OCP).
"""

from app.policies.specs.app_catalog import AppCatalogSpec
from app.policies.specs.base import PolicySpec
from app.policies.specs.password import PasswordSpec
from app.policies.specs.restrictions import RestrictionsSpec

__all__ = ["AppCatalogSpec", "PasswordSpec", "PolicySpec", "RestrictionsSpec"]
