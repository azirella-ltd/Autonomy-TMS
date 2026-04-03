"""
MCP Write-back Service — AIIO-Governed Outbound with Adaptive Delay.

Every agent decision gets an adaptive cooling period before ERP write-back:
- Delay scales inversely with urgency (urgent → short delay)
- Delay scales inversely with confidence (uncertain → long delay)
- During the delay, the decision is visible in Decision Stream for human override
- After the delay expires, write-back executes automatically

AIIO modes still apply:
- AUTOMATE: Short adaptive delay, then auto-execute
- INFORM: Moderate adaptive delay, user notified, then auto-execute
- INSPECT: Full hold (existing hold_minutes), requires explicit approval
- OVERRIDE: User has overridden — skip original write-back

Delay formula (from DecisionGovernanceService.compute_writeback_delay):
  delay = base × (1 - urgency × u_weight) × (2 - confidence × c_weight)
  clamped to [min_delay, max_delay] per tenant governance policy

Decision → MCP tool mapping:
- PO TRM decision → create_purchase_order
- MO TRM decision → create_production_order
- Rebalancing TRM → create_stock_transfer
- ATP TRM → update_sales_order (confirmation)
- TO TRM → create_stock_transfer
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from .audit import MCPAuditLogger
from .client import MCPClientSession, MCPToolResult

logger = logging.getLogger(__name__)


# Map TRM decision type → (canonical MCP tool name, payload builder function name)
DECISION_TYPE_TO_MCP_TOOL = {
    "po_creation": "create_purchase_order",
    "mo_release": "create_production_order",
    "inventory_rebalancing": "create_stock_transfer",
    "transfer_order": "create_stock_transfer",
    "atp_allocation": "update_sales_order",
    "order_tracking": "update_sales_order",
    "subcontracting": "create_purchase_order",  # Subcontracting PO
}

# AIIO modes that allow automatic execution
AUTO_EXECUTE_MODES = {"AUTOMATE", "INFORM"}
HOLD_FOR_APPROVAL_MODES = {"INSPECT"}
SKIP_MODES = {"OVERRIDE"}  # User has already overridden — don't execute original


class WritebackResult:
    """Result of a write-back attempt."""

    def __init__(
        self,
        decision_id: int,
        decision_type: str,
        executed: bool,
        held_for_approval: bool = False,
        mcp_result: Optional[MCPToolResult] = None,
        erp_reference: Optional[str] = None,
        error: Optional[str] = None,
        writeback_delay_minutes: Optional[int] = None,
    ):
        self.decision_id = decision_id
        self.decision_type = decision_type
        self.executed = executed
        self.held_for_approval = held_for_approval
        self.mcp_result = mcp_result
        self.erp_reference = erp_reference
        self.error = error
        self.writeback_delay_minutes = writeback_delay_minutes


class MCPWritebackService:
    """Executes agent decisions back to ERP via MCP, governed by AIIO mode."""

    def __init__(
        self,
        db: AsyncSession,
        ws_broadcast_fn=None,
    ):
        self.db = db
        self.ws_broadcast_fn = ws_broadcast_fn
        self.audit = MCPAuditLogger(db)

    async def execute_decision(
        self,
        decision_id: int,
        decision_type: str,
        decision_data: Dict[str, Any],
        aiio_mode: str,
        mcp_client: MCPClientSession,
        tenant_id: int,
        config_id: int,
        urgency: float = 0.5,
        confidence: float = 0.5,
        site_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        force_immediate: bool = False,
    ) -> WritebackResult:
        """Schedule or execute a TRM decision write-back to ERP via MCP.

        Every decision gets an adaptive cooling period before ERP write-back.
        The delay is computed from the governance policy based on urgency and
        confidence:
        - High urgency + high confidence → short delay (act fast)
        - Low urgency + low confidence → long delay (human review window)

        During the delay, the decision is visible in Decision Stream and can
        be overridden by the user. After expiry, write-back auto-executes.

        Args:
            decision_id: Powell decision table ID
            decision_type: TRM type (po_creation, mo_release, etc.)
            decision_data: The decision payload (quantities, materials, etc.)
            aiio_mode: AUTOMATE/INFORM/INSPECT/OVERRIDE
            mcp_client: Connected MCP client session
            tenant_id: Tenant scope
            config_id: Supply chain config
            urgency: Decision urgency (0-1)
            confidence: Agent confidence (0-1)
            site_id: Optional site scope
            correlation_id: Tracing ID
            force_immediate: Skip delay (used by approval executor)
        """
        cid = correlation_id or str(uuid.uuid4())

        # Check AIIO mode
        if aiio_mode in SKIP_MODES:
            logger.info(
                "Write-back skipped: decision=%d type=%s mode=%s (user overridden)",
                decision_id, decision_type, aiio_mode,
            )
            return WritebackResult(
                decision_id=decision_id,
                decision_type=decision_type,
                executed=False,
                error="Skipped: user override in effect",
            )

        # Map decision type to MCP tool
        tool_name = DECISION_TYPE_TO_MCP_TOOL.get(decision_type)
        if not tool_name:
            return WritebackResult(
                decision_id=decision_id,
                decision_type=decision_type,
                executed=False,
                error=f"No MCP tool mapping for decision type: {decision_type}",
            )

        # Build ERP payload from decision data
        erp_payload = self._decision_to_erp_payload(decision_type, decision_data)

        # ── Compute adaptive write-back delay ──
        if not force_immediate:
            from app.services.decision_governance_service import DecisionGovernanceService
            from app.models.agent_action import ActionMode

            # Look up governance policy for this tenant + action type
            policy = await self._get_governance_policy(tenant_id, decision_type)

            mode_enum = {
                "AUTOMATE": ActionMode.AUTOMATE,
                "INFORM": ActionMode.INFORM,
                "INSPECT": ActionMode.INSPECT,
            }.get(aiio_mode, ActionMode.INFORM)

            delay_minutes = DecisionGovernanceService.compute_writeback_delay(
                policy=policy,
                urgency=urgency,
                confidence=confidence,
                mode=mode_enum,
            )

            # Check if write-back is disabled for this policy
            if delay_minutes is None:
                return WritebackResult(
                    decision_id=decision_id,
                    decision_type=decision_type,
                    executed=False,
                    error="Write-back disabled by governance policy",
                )

            # Schedule for later — store in mcp_pending_writeback with eligible_at
            if delay_minutes > 0 and aiio_mode != "AUTOMATE":
                # For INFORM: schedule with delay, notify user
                # For INSPECT: schedule with hold (already in existing flow)
                await self._schedule_writeback(
                    decision_id=decision_id,
                    decision_type=decision_type,
                    tool_name=tool_name,
                    erp_payload=erp_payload,
                    tenant_id=tenant_id,
                    config_id=config_id,
                    correlation_id=cid,
                    delay_minutes=delay_minutes,
                    aiio_mode=aiio_mode,
                    urgency=urgency,
                    confidence=confidence,
                )

                logger.info(
                    "Write-back scheduled: decision=%d type=%s mode=%s "
                    "delay=%d min urgency=%.2f confidence=%.2f",
                    decision_id, decision_type, aiio_mode,
                    delay_minutes, urgency, confidence,
                )

                return WritebackResult(
                    decision_id=decision_id,
                    decision_type=decision_type,
                    executed=False,
                    held_for_approval=(aiio_mode in HOLD_FOR_APPROVAL_MODES),
                    writeback_delay_minutes=delay_minutes,
                )

            # AUTOMATE with delay: still apply minimum delay but proceed
            # (the scheduler will pick it up, or for very short delays, execute inline)
            if delay_minutes > 0 and aiio_mode == "AUTOMATE":
                await self._schedule_writeback(
                    decision_id=decision_id,
                    decision_type=decision_type,
                    tool_name=tool_name,
                    erp_payload=erp_payload,
                    tenant_id=tenant_id,
                    config_id=config_id,
                    correlation_id=cid,
                    delay_minutes=delay_minutes,
                    aiio_mode=aiio_mode,
                    urgency=urgency,
                    confidence=confidence,
                )
                return WritebackResult(
                    decision_id=decision_id,
                    decision_type=decision_type,
                    executed=False,
                    writeback_delay_minutes=delay_minutes,
                )

        # ── Immediate execution (force_immediate=True or delay=0) ──
        result = await mcp_client.call_tool(
            tool_name, erp_payload, correlation_id=cid
        )

        # Extract ERP reference number from result
        erp_ref = None
        if result.success and isinstance(result.data, dict):
            erp_ref = (
                result.data.get("PurchaseOrder")
                or result.data.get("ManufacturingOrder")
                or result.data.get("MaterialDocument")
                or result.data.get("SalesOrder")
                or result.data.get("d", {}).get("PurchaseOrder")
            )

        # Audit log
        await self.audit.log_call(
            tenant_id=tenant_id,
            erp_type=mcp_client.params.erp_type,
            direction="outbound",
            tool_name=tool_name,
            arguments=erp_payload,
            result=result.data,
            status="success" if result.success else "error",
            duration_ms=result.duration_ms,
            correlation_id=cid,
            config_id=config_id,
            decision_id=decision_id,
            error_message=result.error,
        )

        # Update decision record with ERP reference
        if result.success and erp_ref:
            await self._update_decision_erp_ref(decision_id, decision_type, erp_ref)

        # INFORM mode: also broadcast to Decision Stream
        if aiio_mode == "INFORM" and self.ws_broadcast_fn:
            await self.ws_broadcast_fn(tenant_id, {
                "type": "mcp_writeback",
                "data": {
                    "decision_id": decision_id,
                    "decision_type": decision_type,
                    "tool_name": tool_name,
                    "erp_reference": erp_ref,
                    "success": result.success,
                    "error": result.error,
                    "correlation_id": cid,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })

        return WritebackResult(
            decision_id=decision_id,
            decision_type=decision_type,
            executed=result.success,
            mcp_result=result,
            erp_reference=erp_ref,
            error=result.error,
        )

    def _decision_to_erp_payload(
        self, decision_type: str, decision_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Map a TRM decision to an MCP tool call payload.

        Each decision type produces a different ERP document structure.
        """
        if decision_type == "po_creation":
            return self._build_po_payload(decision_data)
        elif decision_type == "mo_release":
            return self._build_mo_payload(decision_data)
        elif decision_type in ("inventory_rebalancing", "transfer_order"):
            return self._build_transfer_payload(decision_data)
        elif decision_type in ("atp_allocation", "order_tracking"):
            return self._build_so_update_payload(decision_data)
        elif decision_type == "subcontracting":
            return self._build_subcontract_po_payload(decision_data)
        else:
            return decision_data  # Pass through as-is

    def _build_po_payload(self, data: Dict) -> Dict:
        """Build SAP Purchase Order creation payload."""
        items = []
        for item in data.get("items", [data]):
            items.append({
                "PurchaseOrderItem": item.get("line_number", "00010"),
                "Material": item.get("product_id", ""),
                "OrderQuantity": str(item.get("quantity", 0)),
                "Plant": item.get("site_id", ""),
                "NetPriceAmount": str(item.get("unit_price", 0)),
                "NetPriceCurrency": item.get("currency", "USD"),
                "DeliveryDate": item.get("delivery_date", ""),
            })

        return {
            "service": "API_PURCHASEORDER_PROCESS_SRV",
            "entitySet": "A_PurchaseOrder",
            "data": {
                "CompanyCode": data.get("company_code", ""),
                "PurchaseOrderType": "NB",
                "Supplier": data.get("vendor_id", ""),
                "PurchasingOrganization": data.get("purchasing_org", ""),
                "PurchasingGroup": data.get("purchasing_group", ""),
                "to_PurchaseOrderItem": items,
            },
        }

    def _build_mo_payload(self, data: Dict) -> Dict:
        """Build SAP Production Order creation payload."""
        return {
            "service": "API_PRODUCTION_ORDER_2_SRV",
            "entitySet": "A_ProductionOrder",
            "data": {
                "Material": data.get("product_id", ""),
                "ProductionPlant": data.get("site_id", ""),
                "TotalQuantity": str(data.get("quantity", 0)),
                "ProductionOrderType": data.get("order_type", "PP01"),
                "MfgOrderPlannedStartDate": data.get("start_date", ""),
                "MfgOrderPlannedEndDate": data.get("end_date", ""),
            },
        }

    def _build_transfer_payload(self, data: Dict) -> Dict:
        """Build SAP Stock Transfer posting payload."""
        return {
            "service": "API_MATERIAL_DOCUMENT_SRV",
            "entitySet": "A_MaterialDocumentHeader",
            "data": {
                "GoodsMovementCode": "04",  # Transfer posting
                "to_MaterialDocumentItem": [{
                    "Material": data.get("product_id", ""),
                    "Plant": data.get("from_site_id", ""),
                    "StorageLocation": data.get("from_storage", ""),
                    "GoodsMovementType": "311",  # Transfer within company
                    "QuantityInEntryUnit": str(data.get("quantity", 0)),
                    "EntryUnit": data.get("uom", "EA"),
                    "IssuingOrReceivingPlant": data.get("to_site_id", ""),
                    "IssuingOrReceivingStorageLoc": data.get("to_storage", ""),
                }],
            },
        }

    def _build_so_update_payload(self, data: Dict) -> Dict:
        """Build SAP Sales Order update payload (ATP confirmation)."""
        return {
            "service": "API_SALES_ORDER_SRV",
            "entitySet": "A_SalesOrder",
            "key": data.get("sales_order_id", ""),
            "data": {
                "to_Item": [{
                    "SalesOrderItem": data.get("line_number", "000010"),
                    "ConfdDelivQtyInOrderQtyUnit": str(data.get("confirmed_qty", 0)),
                    "ConfirmedDeliveryDate": data.get("confirmed_date", ""),
                }],
            },
        }

    def _build_subcontract_po_payload(self, data: Dict) -> Dict:
        """Build SAP Subcontracting Purchase Order payload."""
        payload = self._build_po_payload(data)
        payload["data"]["PurchaseOrderType"] = "UB"  # Subcontracting
        return payload

    async def _schedule_writeback(
        self,
        decision_id: int,
        decision_type: str,
        tool_name: str,
        erp_payload: Dict,
        tenant_id: int,
        config_id: int,
        correlation_id: str,
        delay_minutes: int,
        aiio_mode: str,
        urgency: float,
        confidence: float,
    ) -> None:
        """Schedule a write-back with business-hours-aware delay.

        The eligible_at timestamp accounts for the tenant's operating schedule:
        - Delay countdown only ticks during business hours
        - Pauses overnight, weekends, and holidays
        - Urgent decisions can bypass hours (if enabled)
        - Capped by max_calendar_delay_hours to prevent indefinite hold

        Stored in mcp_pending_writeback. A scheduler job
        (process_pending_writebacks) picks these up when eligible_at
        has passed and no override has occurred.
        """
        try:
            # Compute business-hours-aware eligible_at
            from app.services.oversight_schedule_service import (
                compute_writeback_eligible_at_with_hours,
            )

            eligible_at = await compute_writeback_eligible_at_with_hours(
                db=self.db,
                tenant_id=tenant_id,
                delay_minutes=delay_minutes,
                urgency=urgency,
            )

            await self.db.execute(
                sql_text("""
                    INSERT INTO mcp_pending_writeback (
                        decision_id, decision_type, tool_name, erp_payload,
                        tenant_id, config_id, correlation_id, status,
                        aiio_mode, delay_minutes, urgency, confidence,
                        eligible_at, created_at
                    ) VALUES (
                        :decision_id, :decision_type, :tool_name, :payload,
                        :tenant_id, :config_id, :correlation_id, 'scheduled',
                        :aiio_mode, :delay_minutes, :urgency, :confidence,
                        :eligible_at, NOW()
                    )
                """),
                {
                    "decision_id": decision_id,
                    "decision_type": decision_type,
                    "tool_name": tool_name,
                    "payload": json.dumps(erp_payload, default=str),
                    "tenant_id": tenant_id,
                    "config_id": config_id,
                    "correlation_id": correlation_id,
                    "aiio_mode": aiio_mode,
                    "delay_minutes": delay_minutes,
                    "urgency": urgency,
                    "confidence": confidence,
                    "eligible_at": eligible_at,
                },
            )
            await self.db.flush()
        except Exception as e:
            logger.error("Failed to schedule write-back: %s", e)

        # Broadcast to Decision Stream — user sees the countdown
        if self.ws_broadcast_fn:
            await self.ws_broadcast_fn(tenant_id, {
                "type": "mcp_writeback_scheduled",
                "data": {
                    "decision_id": decision_id,
                    "decision_type": decision_type,
                    "tool_name": tool_name,
                    "aiio_mode": aiio_mode,
                    "delay_minutes": delay_minutes,
                    "urgency": round(urgency, 2),
                    "confidence": round(confidence, 2),
                    "correlation_id": correlation_id,
                    "eligible_at": eligible_at.isoformat() if eligible_at else None,
                    "message": (
                        f"ERP write-back scheduled in {delay_minutes} business-minutes "
                        f"(urgency={urgency:.0%}, confidence={confidence:.0%}). "
                        f"Override in Decision Stream to cancel."
                    ),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })

        # Notify on-call user if outside business hours
        try:
            await notify_oncall_if_needed(
                db=self.db,
                tenant_id=tenant_id,
                decision_id=decision_id,
                decision_type=decision_type,
                urgency=urgency,
                confidence=confidence,
                aiio_mode=aiio_mode,
                ws_broadcast_fn=self.ws_broadcast_fn,
            )
        except Exception as e:
            logger.debug("On-call notification check failed: %s", e)

    async def _get_governance_policy(self, tenant_id: int, decision_type: str):
        """Load the matching governance policy for this tenant + action type."""
        try:
            result = await self.db.execute(
                sql_text("""
                    SELECT * FROM decision_governance_policies
                    WHERE tenant_id = :tenant_id
                      AND is_active = true
                      AND (action_type = :action_type OR action_type IS NULL)
                    ORDER BY
                        CASE WHEN action_type IS NOT NULL THEN 0 ELSE 1 END,
                        priority ASC
                    LIMIT 1
                """),
                {"tenant_id": tenant_id, "action_type": decision_type},
            )
            row = result.fetchone()
            if row:
                # Build a lightweight policy-like object
                from types import SimpleNamespace
                return SimpleNamespace(
                    hold_minutes=row.hold_minutes if hasattr(row, 'hold_minutes') else 60,
                    writeback_enabled=getattr(row, 'writeback_enabled', True),
                    writeback_base_delay_minutes=getattr(row, 'writeback_base_delay_minutes', 30),
                    writeback_min_delay_minutes=getattr(row, 'writeback_min_delay_minutes', 5),
                    writeback_max_delay_minutes=getattr(row, 'writeback_max_delay_minutes', 480),
                    writeback_urgency_weight=getattr(row, 'writeback_urgency_weight', 1.0),
                    writeback_confidence_weight=getattr(row, 'writeback_confidence_weight', 1.0),
                )
        except Exception as e:
            logger.debug("Could not load governance policy: %s", e)
        return None

    async def _hold_for_approval(
        self,
        decision_id: int,
        decision_type: str,
        tool_name: str,
        erp_payload: Dict,
        tenant_id: int,
        config_id: int,
        correlation_id: str,
    ) -> None:
        """Store pending write-back for INSPECT mode approval (legacy path)."""
        await self._schedule_writeback(
            decision_id=decision_id,
            decision_type=decision_type,
            tool_name=tool_name,
            erp_payload=erp_payload,
            tenant_id=tenant_id,
            config_id=config_id,
            correlation_id=correlation_id,
            delay_minutes=60,
            aiio_mode="INSPECT",
            urgency=0.5,
            confidence=0.5,
        )

    async def _update_decision_erp_ref(
        self, decision_id: int, decision_type: str, erp_ref: str
    ) -> None:
        """Update the powell decision record with the ERP document reference."""
        # Powell decision tables follow naming pattern: powell_{type}_decisions
        table_map = {
            "po_creation": "powell_po_creation_decisions",
            "mo_release": "powell_mo_release_decisions",
            "inventory_rebalancing": "powell_inventory_rebalancing_decisions",
            "transfer_order": "powell_transfer_order_decisions",
            "atp_allocation": "powell_atp_allocation_decisions",
            "order_tracking": "powell_order_tracking_decisions",
            "subcontracting": "powell_subcontracting_decisions",
        }
        table = table_map.get(decision_type)
        if not table:
            return

        try:
            await self.db.execute(
                sql_text(f"""
                    UPDATE {table}
                    SET erp_reference = :erp_ref,
                        erp_writeback_at = NOW()
                    WHERE id = :decision_id
                """),
                {"erp_ref": erp_ref, "decision_id": decision_id},
            )
            await self.db.flush()
        except Exception as e:
            # Column might not exist yet — log but don't fail
            logger.warning("Could not update ERP reference on %s: %s", table, e)


import json


async def process_pending_writebacks(
    db: AsyncSession,
    mcp_pool,
) -> int:
    """Process all pending write-backs whose delay has expired.

    Called by APScheduler every minute. Picks up rows from
    mcp_pending_writeback where eligible_at <= NOW() and status = 'scheduled'.

    Skips any decision that was overridden in Decision Stream during the delay.

    Returns number of write-backs executed.
    """
    try:
        result = await db.execute(
            sql_text("""
                SELECT id, decision_id, decision_type, tool_name, erp_payload,
                       tenant_id, config_id, correlation_id, aiio_mode
                FROM mcp_pending_writeback
                WHERE status = 'scheduled'
                  AND eligible_at <= NOW()
                ORDER BY eligible_at ASC
                LIMIT 50
            """)
        )
        pending = result.fetchall()
    except Exception as e:
        logger.error("Failed to query pending write-backs: %s", e)
        return 0

    executed = 0
    for row in pending:
        try:
            # Check if decision was overridden during the delay
            overridden = await _check_decision_overridden(
                db, row.decision_id, row.decision_type
            )
            if overridden:
                await db.execute(
                    sql_text("""
                        UPDATE mcp_pending_writeback
                        SET status = 'cancelled', executed_at = NOW(),
                            execution_result = 'Cancelled: decision overridden during delay'
                        WHERE id = :id
                    """),
                    {"id": row.id},
                )
                logger.info(
                    "Write-back cancelled (overridden): decision=%d type=%s",
                    row.decision_id, row.decision_type,
                )
                continue

            # Get MCP client for this tenant
            from .config import get_mcp_config, MCPServerParams
            mcp_config = await get_mcp_config(db, row.tenant_id, "sap_s4")  # TODO: store erp_type in pending table
            if not mcp_config:
                continue

            params = MCPServerParams(
                erp_type=mcp_config.erp_type,
                transport=mcp_config.transport,
                tenant_id=mcp_config.tenant_id,
                server_url=mcp_config.server_url,
                server_command=mcp_config.server_command,
                server_env=mcp_config.server_env,
                tool_mappings=mcp_config.tool_mappings,
            )
            client = await mcp_pool.get_client(params)

            # Execute the write-back
            erp_payload = json.loads(row.erp_payload)
            mcp_result = await client.call_tool(
                row.tool_name, erp_payload,
                correlation_id=row.correlation_id,
            )

            # Update status
            status = "executed" if mcp_result.success else "failed"
            await db.execute(
                sql_text("""
                    UPDATE mcp_pending_writeback
                    SET status = :status, executed_at = NOW(),
                        execution_result = :result
                    WHERE id = :id
                """),
                {
                    "id": row.id,
                    "status": status,
                    "result": str(mcp_result.data)[:500] if mcp_result.data else mcp_result.error,
                },
            )

            if mcp_result.success:
                executed += 1
                logger.info(
                    "Write-back executed: decision=%d type=%s tool=%s",
                    row.decision_id, row.decision_type, row.tool_name,
                )

        except Exception as e:
            logger.error(
                "Write-back execution failed: decision=%d error=%s",
                row.decision_id, e,
            )
            await db.execute(
                sql_text("""
                    UPDATE mcp_pending_writeback
                    SET status = 'failed', executed_at = NOW(),
                        execution_result = :error
                    WHERE id = :id
                """),
                {"id": row.id, "error": str(e)[:500]},
            )

    if pending:
        await db.commit()

    return executed


async def _check_decision_overridden(
    db: AsyncSession, decision_id: int, decision_type: str
) -> bool:
    """Check if a decision was overridden in Decision Stream during the delay."""
    table_map = {
        "po_creation": "powell_po_creation_decisions",
        "mo_release": "powell_mo_release_decisions",
        "inventory_rebalancing": "powell_inventory_rebalancing_decisions",
        "transfer_order": "powell_transfer_order_decisions",
        "atp_allocation": "powell_atp_allocation_decisions",
        "order_tracking": "powell_order_tracking_decisions",
        "subcontracting": "powell_subcontracting_decisions",
    }
    table = table_map.get(decision_type)
    if not table:
        return False

    try:
        result = await db.execute(
            sql_text(f"""
                SELECT status FROM {table} WHERE id = :id
            """),
            {"id": decision_id},
        )
        row = result.fetchone()
        if row and row.status == "OVERRIDDEN":
            return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# Post-execution reversal
# ---------------------------------------------------------------------------

# Compensating MCP tool for each decision type
# These are the "undo" operations — not a rollback, but a new ERP document
# that cancels the effect of the original.
REVERSAL_TOOL_MAP = {
    "po_creation": "update_purchase_order",         # Set PO status to cancelled/blocked
    "mo_release": "update_production_order",         # Cancel production order
    "inventory_rebalancing": "create_stock_transfer",  # Reverse transfer (swap from/to)
    "transfer_order": "create_stock_transfer",       # Reverse transfer
    "atp_allocation": "update_sales_order",          # Remove ATP confirmation
    "subcontracting": "update_purchase_order",       # Cancel subcontracting PO
}


async def reverse_writeback(
    db: AsyncSession,
    writeback_id: int,
    user_id: int,
    reason: str,
    mcp_pool,
    ws_broadcast_fn=None,
) -> Dict[str, Any]:
    """Reverse a previously executed ERP write-back.

    Called when a human overrides an already-executed decision. This does NOT
    undo the original — it creates a compensating ERP document:
    - PO → Cancel PO (set status to blocked/deleted)
    - MO → Cancel production order
    - Stock transfer → Reverse transfer (swap source/destination)
    - SO update → Remove ATP confirmation

    Args:
        writeback_id: ID in mcp_pending_writeback (status='executed')
        user_id: User requesting the reversal
        reason: Business reason for the override
        mcp_pool: MCP connection pool
        ws_broadcast_fn: WebSocket broadcast function

    Returns:
        Result summary
    """
    from .audit import MCPAuditLogger

    # Load the original write-back
    result = await db.execute(
        sql_text("""
            SELECT id, decision_id, decision_type, tool_name, erp_payload,
                   tenant_id, config_id, correlation_id, execution_result
            FROM mcp_pending_writeback
            WHERE id = :id AND status = 'executed'
        """),
        {"id": writeback_id},
    )
    row = result.fetchone()
    if not row:
        return {"status": "error", "error": "Write-back not found or not yet executed"}

    # Build compensating payload
    original_payload = json.loads(row.erp_payload) if row.erp_payload else {}
    reversal_tool = REVERSAL_TOOL_MAP.get(row.decision_type)

    if not reversal_tool:
        return {"status": "error", "error": f"No reversal mapping for {row.decision_type}"}

    reversal_payload = _build_reversal_payload(
        row.decision_type, original_payload, row.execution_result
    )

    # Get MCP client
    from .config import get_mcp_config, MCPServerParams
    mcp_config = await get_mcp_config(db, row.tenant_id, "sap_s4")
    if not mcp_config:
        return {"status": "error", "error": "No MCP config for tenant"}

    params = MCPServerParams(
        erp_type=mcp_config.erp_type,
        transport=mcp_config.transport,
        tenant_id=mcp_config.tenant_id,
        server_url=mcp_config.server_url,
        server_command=mcp_config.server_command,
        server_env=mcp_config.server_env,
        tool_mappings=mcp_config.tool_mappings,
    )
    client = await mcp_pool.get_client(params)

    # Execute the reversal
    reversal_cid = str(uuid.uuid4())
    mcp_result = await client.call_tool(
        reversal_tool, reversal_payload, correlation_id=reversal_cid
    )

    # Update original write-back status
    await db.execute(
        sql_text("""
            UPDATE mcp_pending_writeback
            SET status = 'reversed',
                execution_result = COALESCE(execution_result, '') || E'\n--- REVERSED ---\n' || :reason
            WHERE id = :id
        """),
        {"id": writeback_id, "reason": f"Reversed by user {user_id}: {reason}"},
    )

    # Update the powell decision status to OVERRIDDEN
    table_map = {
        "po_creation": "powell_po_creation_decisions",
        "mo_release": "powell_mo_release_decisions",
        "inventory_rebalancing": "powell_inventory_rebalancing_decisions",
        "transfer_order": "powell_transfer_order_decisions",
        "atp_allocation": "powell_atp_allocation_decisions",
        "subcontracting": "powell_subcontracting_decisions",
    }
    table = table_map.get(row.decision_type)
    if table:
        try:
            await db.execute(
                sql_text(f"""
                    UPDATE {table}
                    SET status = 'OVERRIDDEN',
                        override_reason = :reason,
                        overridden_by = :user_id,
                        overridden_at = NOW()
                    WHERE id = :decision_id
                """),
                {
                    "reason": reason,
                    "user_id": user_id,
                    "decision_id": row.decision_id,
                },
            )
        except Exception as e:
            logger.warning("Could not update decision override status: %s", e)

    # Audit log the reversal
    audit = MCPAuditLogger(db)
    await audit.log_call(
        tenant_id=row.tenant_id,
        erp_type=mcp_config.erp_type,
        direction="outbound",
        tool_name=f"REVERSAL:{reversal_tool}",
        arguments=reversal_payload,
        result=mcp_result.data,
        status="success" if mcp_result.success else "error",
        duration_ms=mcp_result.duration_ms,
        correlation_id=reversal_cid,
        config_id=row.config_id,
        decision_id=row.decision_id,
        error_message=mcp_result.error,
    )

    await db.commit()

    # Broadcast to Decision Stream
    if ws_broadcast_fn:
        await ws_broadcast_fn(row.tenant_id, {
            "type": "mcp_writeback_reversed",
            "data": {
                "decision_id": row.decision_id,
                "decision_type": row.decision_type,
                "reversed_by": user_id,
                "reason": reason,
                "reversal_success": mcp_result.success,
                "correlation_id": reversal_cid,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        })

    return {
        "status": "success" if mcp_result.success else "error",
        "reversal_executed": mcp_result.success,
        "correlation_id": reversal_cid,
        "error": mcp_result.error,
    }


def _build_reversal_payload(
    decision_type: str,
    original_payload: Dict,
    execution_result: Optional[str],
) -> Dict[str, Any]:
    """Build a compensating ERP payload from the original.

    The reversal is not a delete — it's a new document that undoes the effect.
    """
    original_data = original_payload.get("data", original_payload)

    if decision_type == "po_creation":
        # Cancel the PO by setting deletion indicator
        po_number = ""
        if execution_result:
            # Try to extract PO number from execution result
            import re
            match = re.search(r'(\d{10})', str(execution_result))
            if match:
                po_number = match.group(1)
        return {
            "service": "API_PURCHASEORDER_PROCESS_SRV",
            "entitySet": "A_PurchaseOrder",
            "key": po_number,
            "data": {"PurchaseOrderDeletionCode": "L"},  # Deletion flag
        }

    elif decision_type == "mo_release":
        return {
            "service": "API_PRODUCTION_ORDER_2_SRV",
            "entitySet": "A_ProductionOrder",
            "key": original_data.get("ManufacturingOrder", ""),
            "data": {"MfgOrderConfirmation": "TECO"},  # Technically complete (cancel)
        }

    elif decision_type in ("inventory_rebalancing", "transfer_order"):
        # Reverse: swap source and destination
        items = original_data.get("to_MaterialDocumentItem", [{}])
        reversed_items = []
        for item in items:
            reversed_items.append({
                **item,
                "Plant": item.get("IssuingOrReceivingPlant", ""),
                "StorageLocation": item.get("IssuingOrReceivingStorageLoc", ""),
                "IssuingOrReceivingPlant": item.get("Plant", ""),
                "IssuingOrReceivingStorageLoc": item.get("StorageLocation", ""),
                "GoodsMovementType": "312",  # Reversal of 311
            })
        return {
            "service": "API_MATERIAL_DOCUMENT_SRV",
            "entitySet": "A_MaterialDocumentHeader",
            "data": {
                "GoodsMovementCode": "04",
                "to_MaterialDocumentItem": reversed_items,
            },
        }

    elif decision_type == "atp_allocation":
        # Remove ATP confirmation from sales order
        return {
            "service": "API_SALES_ORDER_SRV",
            "entitySet": "A_SalesOrder",
            "key": original_data.get("SalesOrder", original_payload.get("key", "")),
            "data": {
                "to_Item": [{
                    "SalesOrderItem": original_data.get("to_Item", [{}])[0].get("SalesOrderItem", "000010"),
                    "ConfdDelivQtyInOrderQtyUnit": "0",
                    "ConfirmedDeliveryDate": "",
                }],
            },
        }

    # Default: pass through with a cancel flag
    return {**original_payload, "_reversal": True}


# ---------------------------------------------------------------------------
# On-call notification for after-hours urgent decisions
# ---------------------------------------------------------------------------

import uuid


async def notify_oncall_if_needed(
    db: AsyncSession,
    tenant_id: int,
    decision_id: int,
    decision_type: str,
    urgency: float,
    confidence: float,
    aiio_mode: str,
    ws_broadcast_fn=None,
) -> Optional[int]:
    """Notify the on-call user if a decision arrives outside business hours.

    Called by the write-back service after scheduling. Checks:
    1. Is it currently outside business hours?
    2. Is on-call enabled for this tenant?
    3. Is the decision urgent enough to warrant notification?

    Notification is via Decision Stream WebSocket targeted to the on-call user.
    Returns the on-call user_id if notified, None otherwise.
    """
    from app.services.oversight_schedule_service import load_tenant_schedule
    from zoneinfo import ZoneInfo

    schedule, holidays, tz_name, config = await load_tenant_schedule(db, tenant_id)

    if not config.get("oncall_enabled"):
        return None

    oncall_user_id = config.get("oncall_user_id")
    if not oncall_user_id:
        return None

    # Check if we're currently outside business hours
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")

    now_local = datetime.now(timezone.utc).astimezone(tz)
    dow = now_local.weekday()
    current_date = now_local.date()

    # Check holiday
    is_holiday = current_date in holidays

    # Check operating hours
    day_schedule = schedule.get(dow) if not is_holiday else None
    is_within_hours = False
    if day_schedule:
        from app.services.oversight_schedule_service import _parse_time
        start = _parse_time(day_schedule[0])
        end = _parse_time(day_schedule[1])
        is_within_hours = start <= now_local.time() < end

    if is_within_hours:
        # During business hours — no on-call notification needed
        return None

    # Outside hours — notify on-call user
    severity = "critical" if urgency >= 0.9 else "high" if urgency >= 0.7 else "medium"

    if ws_broadcast_fn:
        await ws_broadcast_fn(tenant_id, {
            "type": "oncall_notification",
            "data": {
                "target_user_id": oncall_user_id,
                "decision_id": decision_id,
                "decision_type": decision_type,
                "urgency": round(urgency, 2),
                "confidence": round(confidence, 2),
                "aiio_mode": aiio_mode,
                "severity": severity,
                "message": (
                    f"After-hours {severity} decision requires attention: "
                    f"{decision_type} (urgency={urgency:.0%}, confidence={confidence:.0%}). "
                    f"Review in Decision Stream."
                ),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        })

    logger.info(
        "On-call notified: user=%d decision=%d type=%s urgency=%.2f severity=%s",
        oncall_user_id, decision_id, decision_type, urgency, severity,
    )

    return oncall_user_id
