"""
Context Engine — MCP Inbound Router.

Single entry point for all ERP change events arriving via MCP.
Classifies changes, computes deltas against DB state, and routes
to HiveSignalBus for TRM consumption.

Flow:
    MCP poll result → DeltaClassifier → ContextEngine → HiveSignalBus
                                                      → Decision Stream WebSocket
                                                      → CDC Monitor (metric update)
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

# DeltaClassifier comes from the canonical azirella-integrations package
# (was defined inline in this file before 2026-04-13).
from azirella_integrations import DeltaClassifier  # noqa: F401  (re-export)

from app.services.powell.hive_signal import HiveSignal, HiveSignalBus, HiveSignalType
from app.services.powell.tms_hive_signals import TMSHiveSignalType

from .adapters.sap_s4 import SAP_TO_AWS_SC_ENTITY
from .audit import MCPAuditLogger
from .client import MCPClientSession, MCPToolResult

logger = logging.getLogger(__name__)


# Map (entity type, change_type) → TMSHiveSignalType.
# Entity types come from ERP extraction (SAP TM, Oracle OTM, etc.) via MCP,
# normalized to TMS entity names by the adapter layer.
CHANGE_TO_SIGNAL: Dict[Tuple[str, str], Any] = {
    # Shipment signals → ShipmentTrackingTRM, ExceptionMgmtTRM
    ("shipment", "new"): TMSHiveSignalType.SHIPMENT_PICKED_UP,
    ("shipment", "changed"): TMSHiveSignalType.SHIPMENT_DELAYED,
    ("shipment", "deleted"): TMSHiveSignalType.EXCEPTION_DETECTED,

    # Load signals → LoadBuildTRM
    ("load", "new"): TMSHiveSignalType.LOAD_CONSOLIDATED,
    ("load", "changed"): TMSHiveSignalType.LOAD_SPLIT,

    # Carrier / rate signals → FreightProcurementTRM, BrokerRoutingTRM
    ("carrier", "changed"): TMSHiveSignalType.CARRIER_SUSPENDED,
    ("freight_rate", "new"): TMSHiveSignalType.RATE_SPIKE,
    ("freight_rate", "changed"): TMSHiveSignalType.RATE_SPIKE,

    # Tender signals → FreightProcurementTRM, CapacityPromiseTRM
    ("freight_tender", "new"): TMSHiveSignalType.TENDER_SENT,
    ("freight_tender", "changed"): TMSHiveSignalType.TENDER_REJECTED,

    # Appointment / dock signals → DockSchedulingTRM
    ("appointment", "new"): TMSHiveSignalType.DOCK_CONGESTION,
    ("appointment", "changed"): TMSHiveSignalType.DOCK_CONGESTION,

    # Equipment signals → EquipmentRepositionTRM
    ("equipment", "changed"): TMSHiveSignalType.EQUIPMENT_SHORTAGE,

    # Exception signals → ExceptionMgmtTRM
    ("shipment_exception", "new"): TMSHiveSignalType.EXCEPTION_DETECTED,
    ("shipment_exception", "changed"): TMSHiveSignalType.EXCEPTION_ESCALATED,

    # Network / master data signals (shared with SCP pattern)
    ("site", "changed"): HiveSignalType.ALLOCATION_REFRESH,
    ("commodity", "changed"): HiveSignalType.ALLOCATION_REFRESH,
    ("lane", "changed"): TMSHiveSignalType.CARRIER_NETWORK_SHIFT,

    # Demand-side signals (from ERP outbound order extraction)
    ("outbound_order", "new"): HiveSignalType.DEMAND_SURGE,
    ("outbound_order", "changed"): HiveSignalType.ORDER_EXCEPTION,
    ("outbound_order", "deleted"): HiveSignalType.DEMAND_DROP,
}


class ContextEngine:
    """Routes MCP inbound data to HiveSignalBus.

    The Context Engine is the single router that:
    1. Receives raw ERP data from MCP polls
    2. Classifies changes via DeltaClassifier
    3. Maps changes to HiveSignalType
    4. Emits signals to the site's HiveSignalBus
    5. Broadcasts to Decision Stream WebSocket
    6. Logs everything for SOC II audit
    """

    def __init__(
        self,
        db: AsyncSession,
        signal_buses: Optional[Dict[str, HiveSignalBus]] = None,
        ws_broadcast_fn=None,
    ):
        """
        Args:
            db: Async DB session
            signal_buses: Dict of site_key → HiveSignalBus (from SiteAgent pool)
            ws_broadcast_fn: async fn(tenant_id, message) for Decision Stream
        """
        self.db = db
        self.signal_buses = signal_buses or {}
        self.ws_broadcast_fn = ws_broadcast_fn
        self.delta_classifier = DeltaClassifier(db)
        self.audit = MCPAuditLogger(db)

    async def process_inbound(
        self,
        erp_type: str,
        changes: Dict[str, List[Dict[str, Any]]],
        config_id: int,
        tenant_id: int,
        entity_specs: Optional[Dict] = None,
        correlation_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process inbound MCP poll results.

        Args:
            erp_type: ERP type (sap_s4, odoo, d365, etc.)
            changes: Dict mapping entity_type → list of records from MCP poll
            config_id: Supply chain config ID
            tenant_id: Tenant ID
            entity_specs: Entity metadata (key fields, etc.) — adapter-specific
            correlation_id: Tracing ID

        Returns:
            Summary dict: {entity_type: {new: N, changed: N, deleted: N, signals: N}}
        """
        cid = correlation_id or str(uuid.uuid4())
        summary = {}
        total_signals = 0

        # Import entity specs based on ERP type
        if entity_specs is None:
            if erp_type == "sap_s4":
                from .adapters.sap_s4 import SAP_ENTITY_SETS
                entity_specs = SAP_ENTITY_SETS
            else:
                entity_specs = {}

        # Map ERP entity types → AWS SC entity types
        entity_type_map = SAP_TO_AWS_SC_ENTITY if erp_type == "sap_s4" else {}

        for entity_type, records in changes.items():
            spec = entity_specs.get(entity_type, {})
            key_field = spec.get("key_field", "id")

            # Classify into new/changed/deleted
            delta = await self.delta_classifier.classify(
                entity_type, records, config_id, key_field
            )

            new_count = len(delta["new"])
            changed_count = len(delta["changed"])
            deleted_count = len(delta["deleted"])

            if new_count == 0 and changed_count == 0 and deleted_count == 0:
                continue

            # Map to AWS SC entity type
            aws_entity = entity_type_map.get(entity_type, entity_type)

            # Emit signals
            signals_emitted = 0
            for change_type, recs in [
                ("new", delta["new"]),
                ("changed", delta["changed"]),
                ("deleted", delta["deleted"]),
            ]:
                if not recs:
                    continue

                signal_type = CHANGE_TO_SIGNAL.get((aws_entity, change_type))
                if signal_type:
                    # Emit one signal per batch (not per record — avoid signal flood)
                    urgency = self._compute_urgency(aws_entity, change_type, len(recs))
                    signal = HiveSignal(
                        signal_type=signal_type,
                        source_trm="context_engine",
                        urgency=urgency,
                        payload={
                            "entity_type": aws_entity,
                            "change_type": change_type,
                            "count": len(recs),
                            "correlation_id": cid,
                            "erp_type": erp_type,
                        },
                    )
                    # Emit to all signal buses for this config
                    for site_key, bus in self.signal_buses.items():
                        bus.emit(signal)
                        signals_emitted += 1

            total_signals += signals_emitted

            summary[entity_type] = {
                "new": new_count,
                "changed": changed_count,
                "deleted": deleted_count,
                "signals": signals_emitted,
            }

            logger.info(
                "Context Engine: %s — new=%d changed=%d deleted=%d signals=%d",
                entity_type, new_count, changed_count, deleted_count, signals_emitted,
            )

        # Broadcast to Decision Stream WebSocket
        if self.ws_broadcast_fn and total_signals > 0:
            await self.ws_broadcast_fn(tenant_id, {
                "type": "mcp_cdc_event",
                "data": {
                    "erp_type": erp_type,
                    "summary": summary,
                    "correlation_id": cid,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            })

        # Audit log
        await self.audit.log_call(
            tenant_id=tenant_id,
            erp_type=erp_type,
            direction="inbound",
            tool_name="context_engine.process_inbound",
            arguments={"entity_types": list(changes.keys())},
            result=summary,
            status="success",
            duration_ms=0,
            correlation_id=cid,
            config_id=config_id,
        )

        return summary

    def _compute_urgency(
        self, aws_entity: str, change_type: str, count: int
    ) -> float:
        """Compute urgency for a signal based on entity type and change volume.

        Returns 0.0–1.0. Higher for demand-side changes and large batches.
        """
        # Base urgency by entity type
        base = {
            "outbound_order": 0.7,    # Demand changes are high priority
            "inbound_order": 0.5,     # Supply changes medium
            "manufacturing_order": 0.5,
            "inventory_level": 0.4,
            "shipment": 0.4,
            "product": 0.3,           # Master data changes lower
            "site": 0.3,
            "trading_partner": 0.2,
            "product_bom": 0.3,
        }.get(aws_entity, 0.3)

        # Boost for deletions (cancellations are urgent)
        if change_type == "deleted":
            base += 0.2

        # Volume boost (capped)
        volume_boost = min(count / 100, 0.2)

        return min(base + volume_boost, 1.0)
