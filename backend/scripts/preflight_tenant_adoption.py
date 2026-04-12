#!/usr/bin/env python3
"""
Preflight check for Stage 3 Phase 3a — TMS adopts azirella-data-model tenant subpackage.

Verifies that TMS's current database schema is a superset of the canonical tenant
entities defined in azirella-data-model. This MUST pass before we delete TMS's
local copies of the tenant/user/rbac model files.

Usage (inside the backend container):
    python scripts/preflight_tenant_adoption.py

Exit codes:
    0 — all canonical tables + columns present in TMS DB (safe to proceed)
    1 — missing tables or columns found (fix schema before proceeding)

Source: msi-stealth's Stage 2 extraction session (2026-04-11), adapted for TMS.
"""
import sys
import os

# Ensure app is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect

# Use sync engine for inspection (the preflight is a one-shot script, not async)
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://autonomy_user:autonomy_password@db:5432/autonomy",
)
# psycopg2 sync URL (not asyncpg)
if "+asyncpg" in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("+asyncpg", "+psycopg2")

engine = create_engine(DATABASE_URL)

# Import canonical tenant entities from the shared package
from azirella_data_model.tenant import (
    Tenant,
    User,
    RefreshToken,
    Permission,
    Role,
    RolePermissionGrant,
    UserRoleAssignment,
    PasswordHistory,
    PasswordResetToken,
    TokenBlacklist,
    UserSession,
    SSOProvider,
    UserSSOMapping,
    SSOLoginAttempt,
)

canonical_classes = [
    Tenant, User, RefreshToken, Permission, Role,
    RolePermissionGrant, UserRoleAssignment,
    PasswordHistory, PasswordResetToken,
    TokenBlacklist, UserSession,
    SSOProvider, UserSSOMapping, SSOLoginAttempt,
]

inspector = inspect(engine)

missing = []
for cls in canonical_classes:
    table_name = cls.__tablename__
    if not inspector.has_table(table_name):
        missing.append((table_name, "table missing entirely"))
        continue
    actual_cols = {c["name"] for c in inspector.get_columns(table_name)}
    canonical_cols = {c.name for c in cls.__table__.columns}
    diff = canonical_cols - actual_cols
    if diff:
        missing.append((table_name, f"missing columns: {sorted(diff)}"))

if missing:
    print(f"\n{'='*60}")
    print("PREFLIGHT FAILED — TMS DB is NOT a superset of canonical tenant schema")
    print(f"{'='*60}\n")
    for t, msg in missing:
        print(f"  BLOCKER: {t}: {msg}")
    print(f"\nFix the schema first (migration to add missing columns) OR")
    print("regenerate the alembic chain now (promoted to Stage 3 scope).")
    raise SystemExit(1)
else:
    print(f"\n{'='*60}")
    print(f"OK — TMS DB is a superset of canonical tenant schema")
    print(f"  Checked {len(canonical_classes)} canonical classes")
    print(f"  All tables present, all columns present")
    print(f"{'='*60}")
    print(f"\nSafe to proceed with Stage 3 Phase 3a (delete TMS local copies).")
