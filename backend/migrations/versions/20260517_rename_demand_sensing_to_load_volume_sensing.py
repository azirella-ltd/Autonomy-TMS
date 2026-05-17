"""Rename TMS decision_type 'demand_sensing' → 'load_volume_sensing'.

Revision ID: 20260517_rename_load_volume_sensing
Revises: 20260504_tms_materialize_core_substrate
Create Date: 2026-05-17

Background
----------
The TMS-side ``DemandSensingTRM`` was renamed to ``LoadVolumeSensingTRM``
on 2026-05-17 to disambiguate from DP's ``DemandSensing`` adjustment
domain. The two were doing different things behind the same name —
TMS senses *load volume* (loads/lane/period), DP senses *product
demand*. Same string in two planes broke the single-home rule.

The Python class, file, endpoint URL, capability key, trm_type string,
heuristic dispatch key, and Core ``DecisionType`` enum member have all
been renamed in the code. This migration brings the underlying
Postgres enum into line.

What this migration does
------------------------
Renames the ``decision_type_enum`` label ``'demand_sensing'`` to
``'load_volume_sensing'``. Postgres stores enum values by internal
OID; renaming the label is a metadata-only operation and any existing
``agent_decisions`` rows that carry this value are transparently
re-labelled.

Safety: ALTER TYPE ... RENAME VALUE is a single DDL statement under
PG ≥ 10. Guarded with a pg_enum existence check so re-running on a DB
that has already applied the rename (or never had the old label) is a
no-op.

DP does not use ``DecisionType.DEMAND_SENSING`` — DP has its own
``AdjustmentDomain.DEMAND_SENSING`` Python enum, persisted in
``powell_forecast_adjustment_decisions.signal_source`` as a free
string. Renaming the Core enum value affects only TMS-written rows in
``agent_decisions``.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260517_rename_load_volume_sensing"
down_revision = "20260504_tms_materialize_core_substrate"
branch_labels = None
depends_on = None


def _enum_has_value(conn, enum_name: str, value: str) -> bool:
    """Check whether a Postgres enum type currently has the given label."""
    return bool(
        conn.execute(
            sa.text(
                "SELECT 1 FROM pg_type t "
                "JOIN pg_enum e ON e.enumtypid = t.oid "
                "WHERE t.typname = :enum_name AND e.enumlabel = :value"
            ),
            {"enum_name": enum_name, "value": value},
        ).scalar()
    )


def upgrade() -> None:
    conn = op.get_bind()
    if _enum_has_value(conn, "decision_type_enum", "demand_sensing") and not _enum_has_value(
        conn, "decision_type_enum", "load_volume_sensing"
    ):
        op.execute(
            "ALTER TYPE decision_type_enum "
            "RENAME VALUE 'demand_sensing' TO 'load_volume_sensing'"
        )


def downgrade() -> None:
    conn = op.get_bind()
    if _enum_has_value(conn, "decision_type_enum", "load_volume_sensing") and not _enum_has_value(
        conn, "decision_type_enum", "demand_sensing"
    ):
        op.execute(
            "ALTER TYPE decision_type_enum "
            "RENAME VALUE 'load_volume_sensing' TO 'demand_sensing'"
        )
