"""RBAC model — re-exports from canonical azirella-data-model.

Stage 3 Phase 3a — TMS adopts azirella-data-model tenant subpackage.
"""
from azirella_data_model.tenant import (  # noqa: F401
    Permission,
    Role,
    RolePermissionGrant,
    UserRoleAssignment,
    role_permissions,
    user_roles,
)
