"""
MCP Tool: Decision Override.

Allows humans (via any MCP client) to override agent decisions.
Write operation — AIIO governed, requires mandatory reason.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def register(mcp):
    """Register override tools on the MCP server."""

    @mcp.tool()
    async def override_decision(
        tenant_id: int,
        decision_id: int,
        decision_type: str,
        action: str,
        reason: str,
        override_values: Optional[dict] = None,
    ) -> dict:
        """Override an agent decision in the Decision Stream.

        Actions:
        - "accept": Accept the decision as-is (for INSPECT decisions)
        - "override": Replace with human values + mandatory reason
        - "cancel": Cancel a pending write-back during delay window

        Post-execution overrides trigger a compensating ERP write-back
        (e.g., PO cancellation) via the MCP write-back service.

        IMPORTANT: The reason is mandatory and feeds into:
        - Bayesian override effectiveness tracking (Layer 4)
        - TRM retraining pipeline
        - SOC II audit trail

        Args:
            tenant_id: Organization ID
            decision_id: Decision record ID
            decision_type: TRM type (po_creation, mo_release, etc.)
            action: "accept", "override", or "cancel"
            reason: Mandatory business reason for the override
            override_values: New values when action="override" (e.g., {"quantity": 200})

        Returns:
            Result with new status and any compensating actions taken.
        """
        if not reason or len(reason.strip()) < 5:
            return {
                "error": "Reason is mandatory and must be at least 5 characters. "
                         "This feeds the Bayesian learning loop and audit trail.",
            }

        if action not in ("accept", "override", "cancel"):
            return {"error": f"Invalid action '{action}'. Must be: accept, override, cancel"}

        from .db import get_db
        from app.services.decision_stream_service import DecisionStreamService

        async with get_db() as db:
            service = DecisionStreamService(db)
            result = await service.act_on_decision(
                decision_id=decision_id,
                decision_type=decision_type,
                action=action,
                override_reason_text=reason,
                override_values=override_values,
            )

            return result

    @mcp.tool()
    async def reverse_erp_writeback(
        tenant_id: int,
        writeback_id: int,
        reason: str,
        user_id: int,
    ) -> dict:
        """Reverse a previously executed ERP write-back.

        Creates a compensating ERP document (e.g., PO cancellation, reverse
        stock transfer) via MCP. Only works on write-backs with status='executed'.

        Args:
            tenant_id: Organization ID
            writeback_id: ID from mcp_pending_writeback table
            reason: Mandatory business reason
            user_id: User requesting the reversal

        Returns:
            Reversal result with correlation ID for audit tracing.
        """
        if not reason or len(reason.strip()) < 5:
            return {"error": "Reason is mandatory (min 5 chars)"}

        from .db import get_db
        from app.integrations.mcp.writeback_service import reverse_writeback
        from app.integrations.mcp.client import mcp_pool

        async with get_db() as db:
            result = await reverse_writeback(
                db=db,
                writeback_id=writeback_id,
                user_id=user_id,
                reason=reason,
                mcp_pool=mcp_pool,
            )
            return result
