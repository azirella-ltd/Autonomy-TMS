"""Mirror of Core 0053: RLS + tenant_isolation on standalone supply_chain_configs.

Revision ID: 20260518_soc2_supply_chain_configs_rls
Revises: 20260518_soc2_risk_alerts_rls
Create Date: 2026-05-18

Companion to Autonomy-Core@6926f60 (data-model migration
``0053_supply_chain_configs_rls``). Core's migration covers
``supply_chain_configs`` in autonomy-db (AD-13 production target);
this one covers TMS's standalone DB (AD-12 legacy topology).

Closes 1 of the 2 remaining §3.80 deferrals on the TMS audit. After
this lands, audit reports only ``users`` — which needs its own design
(cross-tenant identity).

Same DDL as Core 0053. Idempotent.
"""
from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260518_soc2_supply_chain_configs_rls"
down_revision = "20260518_soc2_risk_alerts_rls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT (
                SELECT relrowsecurity FROM pg_class
                WHERE oid = 'public.supply_chain_configs'::regclass
            ) THEN
                ALTER TABLE public.supply_chain_configs ENABLE ROW LEVEL SECURITY;
            END IF;

            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE schemaname = 'public'
                  AND tablename = 'supply_chain_configs'
                  AND policyname = 'tenant_isolation'
            ) THEN
                CREATE POLICY tenant_isolation ON public.supply_chain_configs
                  USING (tenant_id = current_setting('app.tenant_id', true)::int);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON public.supply_chain_configs;")
    op.execute("ALTER TABLE public.supply_chain_configs DISABLE ROW LEVEL SECURITY;")
