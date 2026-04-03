"""
MCP Tool: Decision Reasoning — Ask Why.

Explains why an agent made a specific decision: the reasoning chain,
alternatives considered, model attribution, and confidence breakdown.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def register(mcp):
    """Register reasoning/explanation tools on the MCP server."""

    @mcp.tool()
    async def ask_why(
        tenant_id: int,
        decision_id: int,
        decision_type: str,
    ) -> dict:
        """Explain why an agent made a specific decision.

        Returns the full reasoning chain including:
        - What triggered the decision (signal context)
        - What alternatives were considered
        - Why this option was chosen (model attribution)
        - Confidence level and conformal prediction interval
        - Impact scoring breakdown (5 dimensions)

        Decision types: po_creation, mo_release, inventory_rebalancing,
        transfer_order, atp_allocation, order_tracking, quality_disposition,
        maintenance_scheduling, subcontracting, forecast_adjustment, inventory_buffer

        Args:
            tenant_id: Organization ID
            decision_id: Decision record ID from the powell_*_decisions table
            decision_type: TRM type that made the decision

        Returns:
            Structured explanation with reasoning, alternatives, and attribution.
        """
        from sqlalchemy import text as sql_text
        from .db import get_db

        table_map = {
            "po_creation": "powell_po_creation_decisions",
            "mo_release": "powell_mo_release_decisions",
            "inventory_rebalancing": "powell_inventory_rebalancing_decisions",
            "transfer_order": "powell_transfer_order_decisions",
            "atp_allocation": "powell_atp_allocation_decisions",
            "order_tracking": "powell_order_tracking_decisions",
            "quality_disposition": "powell_quality_decisions",
            "maintenance_scheduling": "powell_maintenance_decisions",
            "subcontracting": "powell_subcontracting_decisions",
            "forecast_adjustment": "powell_forecast_adjustment_decisions",
            "inventory_buffer": "powell_inventory_buffer_decisions",
        }

        table = table_map.get(decision_type)
        if not table:
            return {"error": f"Unknown decision type: {decision_type}"}

        async with get_db() as db:
            result = await db.execute(
                sql_text(f"""
                    SELECT id, product_id, site_id, confidence, urgency_at_time,
                           decision_reasoning, signal_context, cycle_phase,
                           status, created_at,
                           suggested_action, alternatives_considered
                    FROM {table}
                    WHERE id = :id
                """),
                {"id": decision_id},
            )
            row = result.fetchone()

            if not row:
                return {"error": f"Decision {decision_id} not found in {table}"}

            return {
                "decision_id": row.id,
                "decision_type": decision_type,
                "product_id": row.product_id,
                "site_id": row.site_id,
                "confidence": row.confidence,
                "urgency": row.urgency_at_time,
                "status": row.status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "reasoning": row.decision_reasoning,
                "signal_context": row.signal_context,
                "cycle_phase": row.cycle_phase,
                "suggested_action": getattr(row, "suggested_action", None),
                "alternatives_considered": getattr(row, "alternatives_considered", None),
            }
