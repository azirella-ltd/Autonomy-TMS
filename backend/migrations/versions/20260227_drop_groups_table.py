"""Drop legacy groups table and consolidate on tenants.

The 'groups' table was the original organizational boundary table
(created in 20240912120000). It was superseded by the Tenant model
which maps to 'tenants' (created in 20260116_tenancy).

Previous sessions already:
- Renamed group_id → tenant_id across 60+ tables via ALTER
- Updated all SQLAlchemy models to use ForeignKey("tenants.id")
- Updated all code to reference Tenant / tenant_id

This migration cleans up what remains in the DB:
1. Drop tenants.customer_id (bridging FK to groups.id)
2. Drop stale FK constraints that still reference groups
3. Drop the groups table itself
4. Rename group_mode_enum → tenant_mode_enum (PostgreSQL only)

Fully idempotent — safe to run even if parts were already applied.

Revision ID: 20260227_drop_groups
Revises: 20260227_merge_heads
Create Date: 2026-02-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '20260227_drop_groups'
down_revision = '20260227_merge_heads'
branch_labels = None
depends_on = None


# --------------------------------------------------------------------------- #
# FK constraints created by 20240912120000 that reference groups.id
# Format: (constraint_name, table_name)
# --------------------------------------------------------------------------- #
LEGACY_FK_CONSTRAINTS = [
    ('fk_users_group', 'users'),
    ('fk_scc_group', 'supply_chain_configs'),
    ('fk_games_group', 'games'),
    ('fk_games_group', 'scenarios'),       # table may have been renamed
]


def _is_postgresql():
    """Detect PostgreSQL dialect."""
    return op.get_bind().dialect.name == 'postgresql'


def _table_exists(table_name):
    """Check whether a table exists in the current database."""
    conn = op.get_bind()
    if _is_postgresql():
        result = conn.execute(
            sa.text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.tables "
                "  WHERE table_schema = 'public' AND table_name = :tbl"
                ")"
            ),
            {"tbl": table_name},
        )
        return result.scalar()
    else:
        # SQLite
        result = conn.execute(
            sa.text(
                "SELECT COUNT(*) FROM sqlite_master "
                "WHERE type='table' AND name = :tbl"
            ),
            {"tbl": table_name},
        )
        return result.scalar() > 0


def _column_exists(table_name, column_name):
    """Check whether a column exists on a table."""
    conn = op.get_bind()
    if _is_postgresql():
        result = conn.execute(
            sa.text(
                "SELECT EXISTS ("
                "  SELECT 1 FROM information_schema.columns "
                "  WHERE table_schema = 'public' "
                "    AND table_name = :tbl AND column_name = :col"
                ")"
            ),
            {"tbl": table_name, "col": column_name},
        )
        return result.scalar()
    else:
        result = conn.execute(sa.text(f"PRAGMA table_info({table_name})"))
        return any(row[1] == column_name for row in result)


def _constraint_exists(constraint_name):
    """Check whether a named constraint exists (PostgreSQL only)."""
    if not _is_postgresql():
        return False
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM information_schema.table_constraints "
            "  WHERE constraint_schema = 'public' "
            "    AND constraint_name = :name"
            ")"
        ),
        {"name": constraint_name},
    )
    return result.scalar()


def _enum_exists(enum_name):
    """Check whether a PostgreSQL enum type exists."""
    if not _is_postgresql():
        return False
    conn = op.get_bind()
    result = conn.execute(
        sa.text(
            "SELECT EXISTS ("
            "  SELECT 1 FROM pg_type WHERE typname = :name"
            ")"
        ),
        {"name": enum_name},
    )
    return result.scalar()


def upgrade():
    # ------------------------------------------------------------------ #
    # 1. Drop tenants.customer_id (bridging FK back to groups)
    # ------------------------------------------------------------------ #
    if _table_exists('tenants') and _column_exists('tenants', 'customer_id'):
        # Drop the FK constraint first (name may vary)
        if _is_postgresql():
            # Find and drop any FK on tenants.customer_id
            conn = op.get_bind()
            fk_rows = conn.execute(sa.text(
                "SELECT tc.constraint_name "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "  ON tc.constraint_name = kcu.constraint_name "
                "WHERE tc.table_name = 'tenants' "
                "  AND tc.constraint_type = 'FOREIGN KEY' "
                "  AND kcu.column_name = 'customer_id'"
            )).fetchall()
            for row in fk_rows:
                try:
                    op.drop_constraint(row[0], 'tenants', type_='foreignkey')
                except Exception:
                    pass

        try:
            op.drop_column('tenants', 'customer_id')
        except Exception:
            pass  # Column may already be gone

    # ------------------------------------------------------------------ #
    # 2. Drop legacy FK constraints that reference groups.id
    # ------------------------------------------------------------------ #
    for constraint_name, table_name in LEGACY_FK_CONSTRAINTS:
        if _table_exists(table_name) and _constraint_exists(constraint_name):
            try:
                op.drop_constraint(constraint_name, table_name, type_='foreignkey')
            except Exception:
                pass

    # Also drop any remaining customer_id columns that reference groups
    # (users, supply_chain_configs, scenarios/games may still have these)
    for table_name in ['users', 'supply_chain_configs', 'scenarios', 'games']:
        if _table_exists(table_name) and _column_exists(table_name, 'customer_id'):
            # Drop FK first if it exists
            if _is_postgresql():
                conn = op.get_bind()
                fk_rows = conn.execute(sa.text(
                    "SELECT tc.constraint_name "
                    "FROM information_schema.table_constraints tc "
                    "JOIN information_schema.key_column_usage kcu "
                    "  ON tc.constraint_name = kcu.constraint_name "
                    "WHERE tc.table_name = :tbl "
                    "  AND tc.constraint_type = 'FOREIGN KEY' "
                    "  AND kcu.column_name = 'customer_id'"
                ), {"tbl": table_name}).fetchall()
                for row in fk_rows:
                    try:
                        op.drop_constraint(row[0], table_name, type_='foreignkey')
                    except Exception:
                        pass

            try:
                op.drop_column(table_name, 'customer_id')
            except Exception:
                pass  # Column may already be gone

    # ------------------------------------------------------------------ #
    # 3. Drop the groups table
    # ------------------------------------------------------------------ #
    if _table_exists('groups'):
        # Drop any remaining FK constraints that reference groups first
        if _is_postgresql():
            conn = op.get_bind()
            referencing_fks = conn.execute(sa.text(
                "SELECT tc.constraint_name, tc.table_name "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.constraint_column_usage ccu "
                "  ON tc.constraint_name = ccu.constraint_name "
                "WHERE ccu.table_name = 'groups' "
                "  AND tc.constraint_type = 'FOREIGN KEY'"
            )).fetchall()
            for fk_name, fk_table in referencing_fks:
                try:
                    op.drop_constraint(fk_name, fk_table, type_='foreignkey')
                except Exception:
                    pass

        op.drop_table('groups')

    # ------------------------------------------------------------------ #
    # 4. Rename group_mode_enum → tenant_mode_enum (PostgreSQL only)
    # ------------------------------------------------------------------ #
    if _is_postgresql():
        if _enum_exists('group_mode_enum') and not _enum_exists('tenant_mode_enum'):
            op.execute("ALTER TYPE group_mode_enum RENAME TO tenant_mode_enum")
        elif _enum_exists('group_mode_enum') and _enum_exists('tenant_mode_enum'):
            # Both exist — tenant_mode_enum wins, drop the stale one
            # First check if any column still uses group_mode_enum
            conn = op.get_bind()
            usage = conn.execute(sa.text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE udt_name = 'group_mode_enum'"
            )).scalar()
            if usage == 0:
                op.execute("DROP TYPE group_mode_enum")


def downgrade():
    # ------------------------------------------------------------------ #
    # 4. Rename tenant_mode_enum back to group_mode_enum
    # ------------------------------------------------------------------ #
    if _is_postgresql():
        if _enum_exists('tenant_mode_enum') and not _enum_exists('group_mode_enum'):
            op.execute("ALTER TYPE tenant_mode_enum RENAME TO group_mode_enum")

    # ------------------------------------------------------------------ #
    # 3. Recreate groups table
    # ------------------------------------------------------------------ #
    if not _table_exists('groups'):
        op.create_table(
            'groups',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('name', sa.String(length=100), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('logo', sa.String(length=255), nullable=True),
            sa.Column('admin_id', sa.Integer(), nullable=False),
            sa.ForeignKeyConstraint(['admin_id'], ['users.id'], ondelete='CASCADE'),
            sa.UniqueConstraint('admin_id'),
        )

        # Re-add mode columns
        if _is_postgresql():
            mode_enum = sa.Enum('training', 'production', name='group_mode_enum')
            mode_enum.create(op.get_bind(), checkfirst=True)
            clock_enum = sa.Enum('turn_based', 'timed', 'realtime', name='clock_mode_enum')
            clock_enum.create(op.get_bind(), checkfirst=True)
        op.add_column('groups', sa.Column('mode', sa.Enum('training', 'production', name='group_mode_enum'),
                                          nullable=False, server_default='production'))
        op.add_column('groups', sa.Column('clock_mode', sa.Enum('turn_based', 'timed', 'realtime', name='clock_mode_enum'),
                                          nullable=True))
        op.add_column('groups', sa.Column('round_duration_seconds', sa.Integer(), nullable=True))
        op.add_column('groups', sa.Column('data_refresh_schedule', sa.String(100), nullable=True))
        op.add_column('groups', sa.Column('last_data_import', sa.DateTime(), nullable=True))

    # ------------------------------------------------------------------ #
    # 2. Re-add customer_id FK columns to users, supply_chain_configs, games/scenarios
    # ------------------------------------------------------------------ #
    target_table = 'scenarios' if _table_exists('scenarios') else 'games'
    for table_name in ['users', 'supply_chain_configs', target_table]:
        if _table_exists(table_name) and not _column_exists(table_name, 'customer_id'):
            op.add_column(table_name, sa.Column('customer_id', sa.Integer(), nullable=True))
            try:
                fk_name = {
                    'users': 'fk_users_group',
                    'supply_chain_configs': 'fk_scc_group',
                }.get(table_name, f'fk_{table_name}_group')
                op.create_foreign_key(fk_name, table_name, 'groups', ['customer_id'], ['id'], ondelete='CASCADE')
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # 1. Re-add tenants.customer_id bridging FK
    # ------------------------------------------------------------------ #
    if _table_exists('tenants') and not _column_exists('tenants', 'customer_id'):
        op.add_column('tenants', sa.Column('customer_id', sa.Integer(), nullable=True))
        try:
            op.create_foreign_key(None, 'tenants', 'groups', ['customer_id'], ['id'])
        except Exception:
            pass
