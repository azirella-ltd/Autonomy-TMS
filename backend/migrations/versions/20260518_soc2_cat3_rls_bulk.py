"""§3.80 Category 3 bulk: enable RLS + tenant_isolation on all tenant-scoped public tables.

Revision ID: 20260518_soc2_cat3_rls_bulk
Revises: 20260518_soc2_cat3_rls_batch1
Create Date: 2026-05-18

§3.80 Category 3 — dynamic bulk lift
=====================================

Following the targeted 4-table batch in
``20260518_soc2_cat3_rls_batch1`` (which proved the policy patterns
work end-to-end), this migration covers the long tail dynamically:

For every table in the ``public`` schema:

1. If it has a ``tenant_id INTEGER NOT NULL`` column, attach the
   tenant_id-direct policy.
2. Else if it has a ``config_id`` column, attach the via-config-id
   policy.
3. Else skip (the table isn't tenant-scoped — global / lookup data).

Pattern mirrors the pre-squash ``20260330_soc2_schema_isolation``
migration's DO $$ loop, retargeted at ``public`` (legacy only
covered the four isolated schemas: agents / conformal / checkpoints
/ audit).

Exclusions (handled separately or out-of-scope here)
----------------------------------------------------

- ``public.risk_alerts`` — multi-plane Alert substrate (Core §3.62).
  Canonical home is autonomy-db / Core's data-model migrations, not
  TMS's alembic chain. SCP / DP / TMS all write to it; coordinated
  RLS belongs in Core. Tracked separately.

- Tables that *already* have RLS + a ``tenant_isolation`` policy
  (from the legacy ``20260330`` migration on the agents / conformal
  / checkpoints / audit schemas, or from the targeted batch 1 above).
  The DO $$ guards skip them.

- Tables whose ``tenant_id`` column is *not* NOT NULL — e.g. tables
  where tenant scoping is optional. The audit categorises these
  separately as ``hazard_nullable_fk``; they need attention but the
  fix is different (NOT NULL + FK first, then RLS). Not in this
  bulk pass.

Runtime contract
----------------
RLS enforcement requires the application's connection pool to set
``app.tenant_id`` on each tenant-scoped session. TMS runtime in
``autonomy-app`` honours this. Connections without ``app.tenant_id``
set see zero rows — the correct failure mode under the single-home
rule.

Idempotent: skips tables that already have RLS enabled with a
``tenant_isolation`` policy.
"""
from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260518_soc2_cat3_rls_bulk"
down_revision = "20260518_soc2_cat3_rls_batch1"
branch_labels = None
depends_on = None


# Tables to skip in this bulk pass — handled separately or out-of-scope.
_EXCLUDE = (
    "risk_alerts",            # multi-plane (Core §3.62) — see docstring
    "supply_chain_configs",   # parent of the via-config policy
    "tenants",                # tenant identity itself; superuser-only domain
    "users",                  # cross-tenant identity
    "plane_registration",     # registry; tenant-scoped but separate workstream
)


def upgrade() -> None:
    excludes_sql = ", ".join(f"'{t}'" for t in _EXCLUDE)
    op.execute(
        f"""
        DO $$
        DECLARE
            tbl_rec   record;
            has_tenant_not_null boolean;
            has_config_id boolean;
            already_has_policy boolean;
        BEGIN
            FOR tbl_rec IN
                SELECT t.table_name
                FROM information_schema.tables t
                WHERE t.table_schema = 'public'
                  AND t.table_type = 'BASE TABLE'
                  AND t.table_name NOT IN ({excludes_sql})
            LOOP
                -- Skip if a tenant_isolation policy is already attached.
                SELECT EXISTS (
                    SELECT 1 FROM pg_policies
                    WHERE schemaname = 'public'
                      AND tablename = tbl_rec.table_name
                      AND policyname = 'tenant_isolation'
                ) INTO already_has_policy;
                IF already_has_policy THEN
                    CONTINUE;
                END IF;

                -- Detect column shape.
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = tbl_rec.table_name
                      AND column_name = 'tenant_id'
                      AND is_nullable = 'NO'
                ) INTO has_tenant_not_null;

                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = tbl_rec.table_name
                      AND column_name = 'config_id'
                ) INTO has_config_id;

                IF has_tenant_not_null THEN
                    -- Direct tenant_id policy.
                    EXECUTE format(
                        'ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',
                        tbl_rec.table_name
                    );
                    EXECUTE format(
                        'CREATE POLICY tenant_isolation ON public.%I '
                        'USING (tenant_id = current_setting(''app.tenant_id'', true)::int)',
                        tbl_rec.table_name
                    );
                ELSIF has_config_id THEN
                    -- Via supply_chain_configs join.
                    EXECUTE format(
                        'ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY',
                        tbl_rec.table_name
                    );
                    EXECUTE format(
                        'CREATE POLICY tenant_isolation ON public.%I '
                        'USING (config_id IN ('
                        '  SELECT id FROM public.supply_chain_configs '
                        '  WHERE tenant_id = current_setting(''app.tenant_id'', true)::int'
                        '))',
                        tbl_rec.table_name
                    );
                END IF;
            END LOOP;
        END $$;
        """
    )


def downgrade() -> None:
    excludes_sql = ", ".join(f"'{t}'" for t in _EXCLUDE)
    op.execute(
        f"""
        DO $$
        DECLARE
            tbl_rec record;
        BEGIN
            FOR tbl_rec IN
                SELECT t.table_name
                FROM information_schema.tables t
                WHERE t.table_schema = 'public'
                  AND t.table_type = 'BASE TABLE'
                  AND t.table_name NOT IN ({excludes_sql})
            LOOP
                EXECUTE format(
                    'DROP POLICY IF EXISTS tenant_isolation ON public.%I',
                    tbl_rec.table_name
                );
                EXECUTE format(
                    'ALTER TABLE public.%I DISABLE ROW LEVEL SECURITY',
                    tbl_rec.table_name
                );
            END LOOP;
        END $$;
        """
    )
