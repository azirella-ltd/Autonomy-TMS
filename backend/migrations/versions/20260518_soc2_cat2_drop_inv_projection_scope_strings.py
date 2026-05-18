"""§3.80 Category 2: drop inv_projection.scenario_id + scenario_name (redundant).

Revision ID: 20260518_soc2_cat2_drop_inv_projection_scope_strings
Revises: 20260518_soc2_cat1_config_id_fks
Create Date: 2026-05-18

§3.80 Category 2 — `hazard_nullable_fk_plus_redundant_name`
============================================================

The first TMS SOC II audit (2026-05-18) flagged ``public.inv_projection``
with the ``hazard_nullable_fk_plus_redundant_name`` finding: the table
carries the canonical ``config_id`` (nullable FK to
``supply_chain_configs``) plus two redundant scope-string columns
(``scenario_id VARCHAR(100)`` and ``scenario_name VARCHAR(255)``) that
predate the config-id-as-scenario convention.

A grep over the TMS backend confirms these columns are **dead**:

  * No reads — no ``InvProjection.scenario_id``, no ``WHERE
    scenario_id`` on the ``inv_projection`` table.
  * No writes — the sole ``InvProjection(...)`` constructor in
    ``backend/app/api/endpoints/atp_ctp_view.py:262`` doesn't pass
    either column.
  * Two indexes (``idx_inv_projection_scenario``,
    ``idx_inv_projection_scenario_round``) get dropped with the
    columns.

Dropping them closes the Cat 2 audit finding. ``config_id`` stays
nullable for now — that remains a Cat 3 finding addressed under a
separate workstream (the bulk RLS lift).

Idempotent via ``information_schema.columns`` lookup.
"""
from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260518_soc2_cat2_drop_inv_projection_scope_strings"
down_revision = "20260518_soc2_cat1_config_id_fks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop indexes first (column drops fail if indexes still reference them).
    op.execute("DROP INDEX IF EXISTS public.idx_inv_projection_scenario;")
    op.execute("DROP INDEX IF EXISTS public.idx_inv_projection_scenario_round;")

    # Drop the columns. Idempotent guard so re-running on a DB that's
    # already been migrated is a no-op.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'inv_projection'
                  AND column_name = 'scenario_id'
            ) THEN
                ALTER TABLE public.inv_projection DROP COLUMN scenario_id;
            END IF;
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'inv_projection'
                  AND column_name = 'scenario_name'
            ) THEN
                ALTER TABLE public.inv_projection DROP COLUMN scenario_name;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # Re-add the columns + indexes for symmetry with upgrade(). No data
    # restoration — the dropped values are not recoverable.
    op.execute(
        """
        ALTER TABLE public.inv_projection ADD COLUMN IF NOT EXISTS scenario_id VARCHAR(100);
        """
    )
    op.execute(
        """
        ALTER TABLE public.inv_projection ADD COLUMN IF NOT EXISTS scenario_name VARCHAR(255);
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_inv_projection_scenario "
        "ON public.inv_projection (scenario_id, projection_date);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_inv_projection_scenario_round "
        "ON public.inv_projection (scenario_id, period_number);"
    )
