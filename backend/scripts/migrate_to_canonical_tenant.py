#!/usr/bin/env python3
"""
One-time schema migration: bring TMS DB up to canonical tenant spec.

Creates the 12 missing tenant-related tables and adds missing columns to
the 2 existing tables (tenants, users) so the TMS DB matches the canonical
azirella-data-model tenant subpackage schema.

This is a prerequisite for Stage 3 Phase 3a (TMS adopts azirella-data-model
tenant imports). Run ONCE inside the backend container:

    docker exec autonomy-backend python scripts/migrate_to_canonical_tenant.py

After running, re-run the preflight to verify:

    docker exec autonomy-backend python scripts/preflight_tenant_adoption.py

This script is idempotent — running it twice is safe (CREATE TABLE IF NOT EXISTS,
ADD COLUMN IF NOT EXISTS).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine, inspect, text

# ── DB connection ────────────────────────────────────────────────────────────
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://autonomy_user:autonomy_password@db:5432/autonomy",
)
if "+asyncpg" in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("+asyncpg", "+psycopg2")

engine = create_engine(DATABASE_URL)

# ── Import canonical tenant entities to register their tables with Base ──────
from azirella_data_model.base import Base
from azirella_data_model.tenant import (  # noqa: F401 — imported for side effects
    Tenant, User, RefreshToken, Permission, Role,
    RolePermissionGrant, UserRoleAssignment,
    PasswordHistory, PasswordResetToken,
    TokenBlacklist, UserSession, SSOProvider,
    UserSSOMapping, SSOLoginAttempt,
)

# The 14 canonical tenant tables
CANONICAL_TABLES = [
    Tenant, User, RefreshToken, Permission, Role,
    RolePermissionGrant, UserRoleAssignment,
    PasswordHistory, PasswordResetToken,
    TokenBlacklist, UserSession, SSOProvider,
    UserSSOMapping, SSOLoginAttempt,
]

# ── Step 1: Create missing tables ────────────────────────────────────────────
# create_all with checkfirst=True only creates tables that don't exist.
# It does NOT alter existing tables (that's step 2).
print("\n[1/3] Creating missing tables (checkfirst=True)...")

table_objects = [cls.__table__ for cls in CANONICAL_TABLES]
Base.metadata.create_all(engine, tables=table_objects, checkfirst=True)

inspector = inspect(engine)
for cls in CANONICAL_TABLES:
    exists = inspector.has_table(cls.__tablename__)
    print(f"  {'✅' if exists else '❌'} {cls.__tablename__}")

# ── Step 2: Add missing columns to existing tables ──────────────────────────
print("\n[2/3] Adding missing columns to existing tables...")

# Re-create inspector after table creation
inspector = inspect(engine)

columns_added = 0
with engine.begin() as conn:
    for cls in CANONICAL_TABLES:
        table_name = cls.__tablename__
        if not inspector.has_table(table_name):
            continue  # Table was just created with all columns — skip

        actual_cols = {c["name"] for c in inspector.get_columns(table_name)}
        canonical_cols = {c.name: c for c in cls.__table__.columns}

        for col_name, col_obj in canonical_cols.items():
            if col_name in actual_cols:
                continue

            # Build the ALTER TABLE ADD COLUMN statement
            col_type = col_obj.type.compile(dialect=engine.dialect)

            # Handle nullable + defaults
            nullable = "NULL" if col_obj.nullable else "NOT NULL"
            default_clause = ""
            if col_obj.server_default is not None:
                default_clause = f" DEFAULT {col_obj.server_default.arg}"
            elif col_obj.default is not None and col_obj.default.is_scalar:
                val = col_obj.default.arg
                if isinstance(val, bool):
                    default_clause = f" DEFAULT {'true' if val else 'false'}"
                elif isinstance(val, (int, float)):
                    default_clause = f" DEFAULT {val}"
                elif isinstance(val, str):
                    default_clause = f" DEFAULT '{val}'"

            # For NOT NULL columns without a default, use a safe default
            # to avoid "column contains null values" errors on existing rows
            if nullable == "NOT NULL" and not default_clause:
                type_str = str(col_type).upper()
                if "INT" in type_str:
                    default_clause = " DEFAULT 0"
                elif "BOOL" in type_str:
                    default_clause = " DEFAULT false"
                elif "VARCHAR" in type_str or "TEXT" in type_str:
                    default_clause = " DEFAULT ''"
                elif "DATETIME" in type_str or "TIMESTAMP" in type_str:
                    default_clause = " DEFAULT now()"
                elif "DATE" in type_str:
                    default_clause = " DEFAULT CURRENT_DATE"
                elif "JSON" in type_str:
                    default_clause = " DEFAULT '[]'::json"

            # Use IF NOT EXISTS for idempotency (PostgreSQL 9.6+)
            sql = f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS "{col_name}" {col_type}{default_clause}'

            try:
                conn.execute(text(sql))
                print(f"  ✅ {table_name}.{col_name} ({col_type})")
                columns_added += 1
            except Exception as e:
                print(f"  ❌ {table_name}.{col_name}: {e}")

# ── Step 3: Add foreign key constraints for new columns ─────────────────────
print(f"\n[3/3] Adding foreign key constraints for new columns...")

fks_added = 0
with engine.begin() as conn:
    # Get existing FK constraints
    for cls in CANONICAL_TABLES:
        table_name = cls.__tablename__
        for col in cls.__table__.columns:
            if not col.foreign_keys:
                continue
            for fk in col.foreign_keys:
                # Check if this FK already exists
                existing_fks = inspector.get_foreign_keys(table_name)
                fk_exists = any(
                    col.name in existing_fk.get("constrained_columns", [])
                    for existing_fk in existing_fks
                )
                if fk_exists:
                    continue

                constraint_name = f"fk_{table_name}_{col.name}"
                target_table, target_col = str(fk.target_fullname).split(".")
                sql = (
                    f'ALTER TABLE "{table_name}" '
                    f'ADD CONSTRAINT "{constraint_name}" '
                    f'FOREIGN KEY ("{col.name}") REFERENCES "{target_table}"("{target_col}") '
                    f'ON DELETE CASCADE'
                )
                try:
                    conn.execute(text(sql))
                    print(f"  ✅ {constraint_name}: {table_name}.{col.name} -> {fk.target_fullname}")
                    fks_added += 1
                except Exception as e:
                    if "already exists" in str(e).lower():
                        pass  # Idempotent — constraint exists
                    else:
                        print(f"  ⚠️  {constraint_name}: {e}")

# ── Summary ──────────────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"Migration complete.")
print(f"  Tables checked: {len(CANONICAL_TABLES)}")
print(f"  Columns added: {columns_added}")
print(f"  FK constraints added: {fks_added}")
print(f"{'='*60}")
print(f"\nNow run the preflight to verify:")
print(f"  python scripts/preflight_tenant_adoption.py")
