"""
MCP Tool: ATP/CTP Availability Check.

Real-time Available-to-Promise and Capable-to-Promise checks across
the supply chain network. Multi-stage CTP traverses the BOM and
considers component availability, production capacity, and lead times.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def register(mcp):
    """Register ATP/CTP tools on the MCP server."""

    @mcp.tool()
    async def check_availability(
        tenant_id: int,
        config_id: int,
        product_id: str,
        site_id: str,
        quantity: float,
        target_date: Optional[str] = None,
        priority: int = 3,
    ) -> dict:
        """Check Available-to-Promise (ATP) and Capable-to-Promise (CTP) for a product.

        Performs a multi-stage CTP check that traverses the BOM, checks component
        availability, production capacity, and cumulative lead times to determine
        if and when an order can be fulfilled.

        Priority levels (AATP consumption):
          1 = Highest (consumes from all tiers, bottom-up)
          5 = Lowest (only own tier)

        Args:
            tenant_id: Organization ID
            config_id: Supply chain config ID
            product_id: Material/product identifier
            site_id: Plant/warehouse identifier
            quantity: Requested quantity
            target_date: Requested delivery date (YYYY-MM-DD). If omitted, checks earliest possible.
            priority: Order priority 1-5 (default 3)

        Returns:
            CTP result with feasibility, promise date, binding constraint,
            stage-by-stage breakdown, and pegging preview.
        """
        from datetime import date as date_type
        from .db import get_db
        from app.services.multi_stage_ctp_service import MultiStageCTPService

        parsed_date = None
        if target_date:
            parsed_date = date_type.fromisoformat(target_date)

        async with get_db() as db:
            service = MultiStageCTPService(db, config_id)
            result = service.calculate_multi_stage_ctp(
                product_id=product_id,
                site_id=site_id,
                quantity=quantity,
                target_date=parsed_date,
            )

            return {
                "product_id": result.product_id,
                "site_id": result.site_id,
                "requested_qty": result.requested_qty,
                "ctp_qty": result.ctp_qty,
                "is_feasible": result.is_feasible,
                "promise_date": str(result.promise_date) if result.promise_date else None,
                "cumulative_lead_time_days": result.cumulative_lead_time_days,
                "binding_stage": str(result.binding_stage) if result.binding_stage else None,
                "constraint_summary": result.constraint_summary,
                "stages": [
                    {
                        "stage": str(s.stage),
                        "available_qty": s.available_qty,
                        "lead_time_days": s.lead_time_days,
                    }
                    for s in (result.stages or [])
                ],
            }

    @mcp.tool()
    async def promise_order(
        tenant_id: int,
        config_id: int,
        order_id: str,
        product_id: str,
        site_id: str,
        quantity: float,
        target_date: str,
        priority: int = 3,
    ) -> dict:
        """Promise a customer order with ATP/CTP confirmation.

        Performs the CTP check AND creates the pegging chain (demand-to-supply
        linkage). This is a write operation — it consumes ATP buckets.

        Args:
            tenant_id: Organization ID
            config_id: Supply chain config ID
            order_id: Customer order reference
            product_id: Material/product identifier
            site_id: Plant/warehouse identifier
            quantity: Order quantity
            target_date: Requested delivery date (YYYY-MM-DD)
            priority: Order priority 1-5 (default 3)

        Returns:
            Promise result with confirmed quantity, date, and pegging chain ID.
        """
        from datetime import date as date_type
        from .db import get_db
        from app.services.multi_stage_ctp_service import MultiStageCTPService

        parsed_date = date_type.fromisoformat(target_date)

        async with get_db() as db:
            service = MultiStageCTPService(db, config_id)
            result = service.promise_order(
                order_id=order_id,
                product_id=product_id,
                site_id=site_id,
                quantity=quantity,
                target_date=parsed_date,
                priority=priority,
            )

            return {
                "order_id": result.order_id,
                "promised": result.promised,
                "promised_qty": result.promised_qty,
                "promised_date": str(result.promised_date) if result.promised_date else None,
                "pegging_chain_id": result.pegging_chain_id,
                "constraint_summary": result.ctp_result.constraint_summary if result.ctp_result else None,
            }
