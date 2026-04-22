"""
Powell Integration Service

Orchestrates Powell TRM services with existing order management, fulfillment, and ATP services.
Provides hooks for narrow TRM execution decisions at key integration points:

1. ATP Check Flow: ATPExecutorTRM for allocation-based available-to-promise
2. Order Fulfillment: Priority-based allocation consumption during fulfillment
3. Procurement: POCreationTRM for replenishment decisions
4. Order Monitoring: OrderTrackingTRM for exception detection
5. Inventory Balancing: InventoryRebalancingTRM for inter-site transfers

Integration Philosophy:
- Powell services provide RECOMMENDATIONS (not direct actions)
- Existing services execute the actual operations
- All TRM decisions are logged for training data collection
- Confidence thresholds determine when to auto-execute vs. require human approval
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, date, timedelta
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func

from app.models.sc_entities import InvLevel, OutboundOrderLine
from app.models.purchase_order import PurchaseOrder
from app.models.transfer_order import TransferOrder
from app.models.supply_chain_config import Site, TransportationLane

# Powell services
from app.services.powell.allocation_service import (
    AllocationService,
    AllocationConfig,
    PriorityAllocation,
    AllocationCadence,
    UnfulfillableOrderAction,
)
from app.services.powell.atp_executor import (
    ATPExecutorTRM,
    ATPRequest,
    ATPResponse,
)
# po_creation_trm retired — TMS uses FreightProcurementTRM for the ACQUIRE
# phase (commit 3dc1d72e). The _get_po_trm / evaluate_po_recommendations
# paths below now raise NotImplementedError at call time; a future
# FreightProcurement equivalent will replace them.
from typing import Any as _PORecommendation  # placeholder return type
PORecommendation = _PORecommendation
InventoryPosition = Any  # type: ignore
SupplierInfo = Any  # type: ignore
from app.services.powell.order_tracking_trm import (
    OrderTrackingTRM,
    OrderState,
    ExceptionDetection,
    OrderType,
    OrderStatus,
)
from app.services.powell.inventory_rebalancing_trm import (
    InventoryRebalancingTRM,
    SiteInventoryState,
    TransferLane,
    RebalanceRecommendation,
)

logger = logging.getLogger(__name__)


@dataclass
class IntegrationConfig:
    """Configuration for Powell integration behavior."""

    # Auto-execution thresholds (0.0-1.0)
    # Recommendations with confidence >= threshold are auto-executed
    atp_auto_execute_threshold: float = 0.8
    po_auto_execute_threshold: float = 0.7
    rebalance_auto_execute_threshold: float = 0.6

    # Enable/disable individual TRMs
    enable_atp_executor: bool = True
    enable_po_trm: bool = False  # retired — see _get_po_trm
    enable_exception_trm: bool = True
    enable_rebalancing_trm: bool = True

    # Logging for training data
    log_all_decisions: bool = True
    log_outcomes: bool = True


@dataclass
class IntegrationResult:
    """Result of a Powell integration action."""

    success: bool
    action_type: str  # 'atp_check', 'po_recommendation', 'exception_detection', 'rebalance'
    recommendation: Optional[Any] = None
    auto_executed: bool = False
    execution_result: Optional[Dict[str, Any]] = None
    confidence: float = 0.0
    requires_human_approval: bool = False
    reason: str = ""


class PowellIntegrationService:
    """
    Orchestrates Powell TRM services with existing order/fulfillment flows.

    This service acts as a facade that:
    1. Receives events from existing services (order creation, fulfillment, etc.)
    2. Invokes appropriate Powell TRM for decision support
    3. Optionally auto-executes high-confidence recommendations
    4. Logs all decisions for TRM training
    """

    def __init__(
        self,
        db: AsyncSession,
        config: Optional[IntegrationConfig] = None,
    ):
        self.db = db
        self.config = config or IntegrationConfig()

        # Initialize Powell services (lazy - created on first use)
        self._allocation_service: Optional[AllocationService] = None
        self._atp_executor: Optional[ATPExecutorTRM] = None
        self._po_trm: Optional[Any] = None  # retired; see _get_po_trm
        self._exception_trm: Optional[OrderTrackingTRM] = None
        self._rebalancing_trm: Optional[InventoryRebalancingTRM] = None

    # =========================================================================
    # Service Initialization (Lazy)
    # =========================================================================

    def _get_allocation_service(self, supply_chain_config_id: int) -> AllocationService:
        """Get or create allocation service."""
        if self._allocation_service is None:
            # Default config - can be customized per supply chain config
            alloc_config = AllocationConfig(
                cadence=AllocationCadence.WEEKLY,
                unfulfillable_action=UnfulfillableOrderAction.DEFER,
                allow_cross_priority_consumption=False,
            )
            self._allocation_service = AllocationService(alloc_config)
        return self._allocation_service

    def _get_atp_executor(self) -> ATPExecutorTRM:
        """Get or create ATP executor."""
        if self._atp_executor is None:
            self._atp_executor = ATPExecutorTRM()
        return self._atp_executor

    def _get_po_trm(self):
        """PO-creation TRM retired. TMS's ACQUIRE path is FreightProcurementTRM,
        which does not share this interface. This stub keeps callers that
        pass `enable_po_trm=True` from silent-succeeding against missing
        substrate — they will fail fast with a clear message instead."""
        raise NotImplementedError(
            "POCreationTRM has been retired (commit 3dc1d72e). "
            "Use FreightProcurementTRM via /api/v1/freight-procurement/* for "
            "the TMS ACQUIRE phase."
        )

    def _get_exception_trm(self) -> OrderTrackingTRM:
        """Get or create order tracking TRM."""
        if self._exception_trm is None:
            self._exception_trm = OrderTrackingTRM()
        return self._exception_trm

    def _get_rebalancing_trm(self) -> InventoryRebalancingTRM:
        """Get or create inventory rebalancing TRM."""
        if self._rebalancing_trm is None:
            self._rebalancing_trm = InventoryRebalancingTRM()
        return self._rebalancing_trm

    # =========================================================================
    # ATP Integration
    # =========================================================================

    async def check_atp_with_allocations(
        self,
        config_id: int,
        product_id: str,
        location_id: str,
        requested_qty: float,
        order_priority: int,
        order_id: Optional[str] = None,
    ) -> IntegrationResult:
        """
        Check ATP using Powell's allocation-based approach.

        This is the primary integration point for ATP checks. Instead of simple
        inventory availability, it uses priority-based allocations (AATP).

        Args:
            config_id: Supply chain configuration ID
            product_id: Product to check
            location_id: Location (site) to check
            requested_qty: Quantity requested
            order_priority: Order priority (1=highest, 5=lowest)
            order_id: Optional order ID for logging

        Returns:
            IntegrationResult with ATPResponse
        """
        if not self.config.enable_atp_executor:
            return IntegrationResult(
                success=False,
                action_type="atp_check",
                reason="ATP executor disabled",
            )

        try:
            # Load current allocations from database
            allocations = await self._load_allocations(
                config_id, product_id, location_id
            )

            # Get available inventory (convert string location_id to int for DB query)
            inventory = await self._get_inventory_position(
                config_id, product_id, int(location_id) if isinstance(location_id, str) else location_id
            )

            # Build allocation service state
            allocation_service = self._get_allocation_service(config_id)
            for alloc in allocations:
                allocation_service.update_allocation(
                    product_id=alloc.product_id,
                    location_id=alloc.location_id,
                    priority=alloc.priority,
                    allocated_qty=alloc.allocated_qty,
                    consumed_qty=alloc.consumed_qty,
                )

            # Execute ATP check
            atp_executor = self._get_atp_executor()
            request = ATPRequest(
                order_id=order_id or f"ATP-{datetime.utcnow().timestamp()}",
                product_id=product_id,
                location_id=location_id,
                requested_qty=requested_qty,
                priority=order_priority,
            )

            response = atp_executor.check_availability(
                request=request,
                allocation_service=allocation_service,
                current_inventory=inventory,
            )

            # Log for training
            if self.config.log_all_decisions:
                await self._log_atp_decision(
                    config_id=config_id,
                    request=request,
                    response=response,
                )

            # Determine if auto-execution should happen
            auto_execute = (
                response.can_fulfill and
                response.confidence >= self.config.atp_auto_execute_threshold
            )

            return IntegrationResult(
                success=True,
                action_type="atp_check",
                recommendation=response,
                auto_executed=auto_execute,
                confidence=response.confidence,
                requires_human_approval=not auto_execute,
                reason="ATP check completed" if response.can_fulfill else "Insufficient allocation",
            )

        except Exception as e:
            logger.error(f"ATP check failed: {e}", exc_info=True)
            return IntegrationResult(
                success=False,
                action_type="atp_check",
                reason=f"ATP check error: {str(e)}",
            )

    async def commit_atp(
        self,
        config_id: int,
        product_id: str,
        location_id: str,
        order_priority: int,
        consume_qty: float,
        order_id: str,
    ) -> IntegrationResult:
        """
        Commit ATP allocation (consume from allocation bucket).

        Call this after order is confirmed to decrement the allocation.

        Args:
            config_id: Supply chain configuration ID
            product_id: Product ID
            location_id: Location ID
            order_priority: Priority tier to consume from
            consume_qty: Quantity to consume
            order_id: Order ID for tracking

        Returns:
            IntegrationResult with consumption details
        """
        try:
            allocation_service = self._get_allocation_service(config_id)

            result = allocation_service.consume_allocation(
                product_id=product_id,
                location_id=location_id,
                order_priority=order_priority,
                requested_qty=consume_qty,
            )

            # Persist updated allocations
            await self._save_allocation_consumption(
                config_id=config_id,
                product_id=product_id,
                location_id=location_id,
                consumption_result=result,
            )

            return IntegrationResult(
                success=result.success,
                action_type="atp_commit",
                recommendation=result,
                auto_executed=True,
                execution_result={
                    "consumed_qty": result.consumed_qty,
                    "consumption_breakdown": result.consumption_breakdown,
                },
                reason="Allocation consumed" if result.success else result.message,
            )

        except Exception as e:
            logger.error(f"ATP commit failed: {e}", exc_info=True)
            return IntegrationResult(
                success=False,
                action_type="atp_commit",
                reason=f"ATP commit error: {str(e)}",
            )

    # =========================================================================
    # PO Creation Integration
    # =========================================================================

    async def get_po_recommendations(
        self,
        config_id: int,
        site_id: int,
        product_ids: Optional[List[str]] = None,
    ) -> IntegrationResult:
        """
        Get PO creation recommendations from TRM.

        Called periodically (e.g., daily MRP run) to check if POs should be created.

        Args:
            config_id: Supply chain configuration ID
            site_id: Site to check
            product_ids: Optional list of products to check (default: all)

        Returns:
            IntegrationResult with list of PORecommendation
        """
        if not self.config.enable_po_trm:
            return IntegrationResult(
                success=False,
                action_type="po_recommendation",
                reason="PO TRM disabled",
            )

        try:
            po_trm = self._get_po_trm()
            recommendations = []

            # Get all products at this site
            products = await self._get_products_at_site(config_id, site_id, product_ids)

            for product_id in products:
                # Build inventory position
                inv_position = await self._build_inventory_position(
                    config_id, site_id, product_id
                )

                # Get supplier info
                suppliers = await self._get_suppliers_for_product(
                    config_id, site_id, product_id
                )

                if not suppliers:
                    continue

                # Check if PO should be created
                state = po_trm.build_state(
                    inventory_position=inv_position,
                    suppliers=suppliers,
                    current_date=date.today(),
                )

                recommendation = po_trm.evaluate(state)

                if recommendation.should_create_po:
                    recommendations.append(recommendation)

                    # Log for training
                    if self.config.log_all_decisions:
                        await self._log_po_decision(
                            config_id=config_id,
                            state=state,
                            recommendation=recommendation,
                        )

            # Determine if any should be auto-executed
            auto_execute_recs = [
                r for r in recommendations
                if r.confidence >= self.config.po_auto_execute_threshold
            ]

            return IntegrationResult(
                success=True,
                action_type="po_recommendation",
                recommendation=recommendations,
                auto_executed=len(auto_execute_recs) > 0,
                execution_result={
                    "total_recommendations": len(recommendations),
                    "auto_execute_count": len(auto_execute_recs),
                },
                confidence=max((r.confidence for r in recommendations), default=0.0),
                requires_human_approval=len(recommendations) > len(auto_execute_recs),
                reason=f"{len(recommendations)} PO recommendations generated",
            )

        except Exception as e:
            logger.error(f"PO recommendation failed: {e}", exc_info=True)
            return IntegrationResult(
                success=False,
                action_type="po_recommendation",
                reason=f"PO recommendation error: {str(e)}",
            )

    async def execute_po_recommendation(
        self,
        config_id: int,
        recommendation: PORecommendation,
        scenario_id: Optional[int] = None,
    ) -> IntegrationResult:
        """
        Execute a PO recommendation by creating the actual PO.

        Args:
            config_id: Supply chain configuration ID
            recommendation: PO recommendation from TRM
            scenario_id: Optional scenario ID for simulation context

        Returns:
            IntegrationResult with created PO details
        """
        try:
            from app.services.order_management_service import OrderManagementService

            order_mgmt = OrderManagementService(self.db)

            # Generate PO number
            po_number = f"PO-{recommendation.supplier.supplier_id}-{recommendation.product_id}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

            # Calculate delivery date
            delivery_date = date.today() + timedelta(days=int(recommendation.supplier.lead_time))

            # Get destination site ID
            dest_site_id = await self._get_site_id_by_name(
                config_id, recommendation.location_id
            )

            # Get supplier site ID (for inter-company transfers in simulation)
            supplier_site_id = await self._get_site_id_by_name(
                config_id, recommendation.supplier.supplier_id
            )

            # Create PO
            po = await order_mgmt.create_purchase_order(
                po_number=po_number,
                supplier_site_id=supplier_site_id or dest_site_id,
                destination_site_id=dest_site_id,
                product_id=recommendation.product_id,
                quantity=recommendation.recommended_qty,
                requested_delivery_date=delivery_date,
                vendor_id=recommendation.supplier.supplier_id,
                config_id=config_id,
                scenario_id=scenario_id,
            )

            await order_mgmt.commit()

            # Log outcome for training
            if self.config.log_outcomes:
                await self._log_po_execution(
                    config_id=config_id,
                    recommendation=recommendation,
                    po_id=po.id,
                    po_number=po_number,
                )

            return IntegrationResult(
                success=True,
                action_type="po_execution",
                recommendation=recommendation,
                auto_executed=True,
                execution_result={
                    "po_id": po.id,
                    "po_number": po_number,
                    "quantity": recommendation.recommended_qty,
                    "expected_delivery": delivery_date.isoformat(),
                },
                confidence=recommendation.confidence,
                reason=f"PO {po_number} created",
            )

        except Exception as e:
            logger.error(f"PO execution failed: {e}", exc_info=True)
            return IntegrationResult(
                success=False,
                action_type="po_execution",
                reason=f"PO execution error: {str(e)}",
            )

    # =========================================================================
    # Exception Detection Integration
    # =========================================================================

    async def detect_order_exceptions(
        self,
        config_id: int,
        scenario_id: Optional[int] = None,
    ) -> IntegrationResult:
        """
        Scan orders for exceptions using OrderTrackingTRM.

        Should be called periodically (e.g., hourly) to detect:
        - Late deliveries
        - Quantity shortages
        - Stuck orders
        - Missing confirmations

        Args:
            config_id: Supply chain configuration ID
            scenario_id: Optional scenario ID for simulation context

        Returns:
            IntegrationResult with list of ExceptionDetection
        """
        if not self.config.enable_exception_trm:
            return IntegrationResult(
                success=False,
                action_type="exception_detection",
                reason="Exception TRM disabled",
            )

        try:
            exception_trm = self._get_exception_trm()
            exceptions = []

            # Get active orders (POs and TOs)
            active_pos = await self._get_active_purchase_orders(config_id, scenario_id)
            active_tos = await self._get_active_transfer_orders(config_id, scenario_id)

            # Check POs
            for po in active_pos:
                order_state = self._build_po_order_state(po)
                detection = exception_trm.check_for_exceptions(order_state)

                if detection.has_exception:
                    exceptions.append(detection)

                    if self.config.log_all_decisions:
                        await self._log_exception_detection(
                            config_id=config_id,
                            order_state=order_state,
                            detection=detection,
                        )

            # Check TOs
            for to in active_tos:
                order_state = self._build_to_order_state(to)
                detection = exception_trm.check_for_exceptions(order_state)

                if detection.has_exception:
                    exceptions.append(detection)

                    if self.config.log_all_decisions:
                        await self._log_exception_detection(
                            config_id=config_id,
                            order_state=order_state,
                            detection=detection,
                        )

            # Count critical exceptions
            critical_count = sum(
                1 for e in exceptions if e.severity.value == "critical"
            )

            return IntegrationResult(
                success=True,
                action_type="exception_detection",
                recommendation=exceptions,
                auto_executed=False,  # Exceptions always require review
                execution_result={
                    "total_exceptions": len(exceptions),
                    "critical_count": critical_count,
                },
                confidence=max((e.confidence for e in exceptions), default=0.0),
                requires_human_approval=critical_count > 0,
                reason=f"{len(exceptions)} exceptions detected ({critical_count} critical)",
            )

        except Exception as e:
            logger.error(f"Exception detection failed: {e}", exc_info=True)
            return IntegrationResult(
                success=False,
                action_type="exception_detection",
                reason=f"Exception detection error: {str(e)}",
            )

    # =========================================================================
    # Inventory Rebalancing Integration
    # =========================================================================

    async def get_rebalancing_recommendations(
        self,
        config_id: int,
        product_id: Optional[str] = None,
    ) -> IntegrationResult:
        """
        Get inventory rebalancing recommendations from TRM.

        Analyzes inventory positions across sites and recommends transfers
        to balance stock and prevent stockouts.

        Args:
            config_id: Supply chain configuration ID
            product_id: Optional specific product to check

        Returns:
            IntegrationResult with list of RebalanceRecommendation
        """
        if not self.config.enable_rebalancing_trm:
            return IntegrationResult(
                success=False,
                action_type="rebalance_recommendation",
                reason="Rebalancing TRM disabled",
            )

        try:
            rebalancing_trm = self._get_rebalancing_trm()
            recommendations = []

            # Get products to evaluate
            products = await self._get_all_products(config_id)
            if product_id:
                products = [p for p in products if p == product_id]

            for prod_id in products:
                # Build site inventory states
                site_states = await self._build_site_inventory_states(
                    config_id, prod_id
                )

                if len(site_states) < 2:
                    continue  # Need at least 2 sites for rebalancing

                # Get transfer lanes
                transfer_lanes = await self._get_transfer_lanes(config_id)

                # Build rebalancing state and evaluate
                state = rebalancing_trm.build_state(
                    site_states=site_states,
                    transfer_lanes=transfer_lanes,
                )

                site_recommendations = rebalancing_trm.evaluate(state)

                for rec in site_recommendations:
                    recommendations.append(rec)

                    if self.config.log_all_decisions:
                        await self._log_rebalance_decision(
                            config_id=config_id,
                            recommendation=rec,
                        )

            # Auto-execute high-confidence recommendations
            auto_execute_recs = [
                r for r in recommendations
                if r.confidence >= self.config.rebalance_auto_execute_threshold
            ]

            return IntegrationResult(
                success=True,
                action_type="rebalance_recommendation",
                recommendation=recommendations,
                auto_executed=len(auto_execute_recs) > 0,
                execution_result={
                    "total_recommendations": len(recommendations),
                    "auto_execute_count": len(auto_execute_recs),
                },
                confidence=max((r.confidence for r in recommendations), default=0.0),
                requires_human_approval=len(recommendations) > len(auto_execute_recs),
                reason=f"{len(recommendations)} rebalancing recommendations",
            )

        except Exception as e:
            logger.error(f"Rebalancing recommendation failed: {e}", exc_info=True)
            return IntegrationResult(
                success=False,
                action_type="rebalance_recommendation",
                reason=f"Rebalancing error: {str(e)}",
            )

    # =========================================================================
    # Helper Methods - Data Loading
    # =========================================================================

    async def _load_allocations(
        self,
        config_id: int,
        product_id: str,
        location_id: str,
    ) -> List[PriorityAllocation]:
        """Load current allocations from database."""
        try:
            from app.models.powell_allocation import PowellAllocation

            now = datetime.utcnow()
            result = await self.db.execute(
                select(PowellAllocation).where(
                    and_(
                        PowellAllocation.config_id == config_id,
                        PowellAllocation.product_id == product_id,
                        PowellAllocation.location_id == location_id,
                        PowellAllocation.is_active == True,
                        PowellAllocation.valid_from <= now,
                        PowellAllocation.valid_to >= now,
                    )
                ).order_by(PowellAllocation.priority)
            )
            db_allocs = result.scalars().all()

            return [
                PriorityAllocation(
                    product_id=a.product_id,
                    location_id=a.location_id,
                    priority=a.priority,
                    allocated_qty=a.allocated_qty,
                    consumed_qty=a.consumed_qty,
                )
                for a in db_allocs
            ]
        except Exception as e:
            logger.warning(f"Failed to load allocations: {e}")
            return []

    async def _get_inventory_position(
        self,
        config_id: int,
        product_id: str,
        location_id: int,
    ) -> float:
        """Get current inventory level."""
        try:
            result = await self.db.execute(
                select(InvLevel.quantity).where(
                    and_(
                        InvLevel.config_id == config_id,
                        InvLevel.product_id == product_id,
                        InvLevel.site_id == location_id,
                    )
                )
            )
            qty = result.scalar_one_or_none()
            return float(qty) if qty else 0.0
        except Exception:
            return 0.0

    async def _get_products_at_site(
        self,
        config_id: int,
        site_id: int,
        product_ids: Optional[List[str]] = None,
    ) -> List[str]:
        """Get list of products at a site."""
        query = select(InvLevel.product_id.distinct()).where(
            InvLevel.config_id == config_id,
            InvLevel.site_id == site_id,
        )
        if product_ids:
            query = query.where(InvLevel.product_id.in_(product_ids))

        result = await self.db.execute(query)
        return [row[0] for row in result.fetchall()]

    async def _build_inventory_position(
        self,
        config_id: int,
        site_id: int,
        product_id: str,
    ) -> InventoryPosition:
        """Build InventoryPosition for PO TRM."""
        # Get on-hand
        on_hand = await self._get_inventory_position(
            config_id, product_id, site_id
        )

        # Get on-order (pending POs)
        po_query = select(func.sum(PurchaseOrder.total_amount)).where(
            and_(
                PurchaseOrder.config_id == config_id,
                PurchaseOrder.destination_site_id == site_id,
                PurchaseOrder.status.in_(["APPROVED", "ACKNOWLEDGED", "SHIPPED"]),
            )
        )
        po_result = await self.db.execute(po_query)
        on_order = po_result.scalar() or 0.0

        # Get in-transit (TOs)
        to_query = select(func.sum(TransferOrderLineItem.quantity)).join(
            TransferOrder, TransferOrderLineItem.to_id == TransferOrder.id
        ).where(
            and_(
                TransferOrder.config_id == config_id,
                TransferOrder.destination_site_id == site_id,
                TransferOrder.status == "IN_TRANSIT",
                TransferOrderLineItem.product_id == product_id,
            )
        )
        to_result = await self.db.execute(to_query)
        in_transit = to_result.scalar() or 0.0

        # Get backlog
        backlog_query = select(func.sum(OutboundOrderLine.backlog_quantity)).where(
            and_(
                OutboundOrderLine.site_id == site_id,
                OutboundOrderLine.product_id == product_id,
                OutboundOrderLine.status.in_(["CONFIRMED", "PARTIALLY_FULFILLED"]),
            )
        )
        backlog_result = await self.db.execute(backlog_query)
        backlog = backlog_result.scalar() or 0.0

        # Get demand forecast from Forecast table (avg of recent entries)
        from app.models.sc_entities import Forecast as ForecastModel, InvPolicy
        fcst_query = select(func.avg(ForecastModel.p50_quantity)).where(
            and_(
                ForecastModel.product_id == product_id,
                ForecastModel.site_id == site_id,
            )
        )
        fcst_result = await self.db.execute(fcst_query)
        forecast_demand = float(fcst_result.scalar() or 100.0)

        # Get safety stock and reorder point from InvPolicy
        policy_query = select(InvPolicy).where(
            and_(
                InvPolicy.product_id == product_id,
                InvPolicy.site_id == site_id,
            )
        ).limit(1)
        policy_result = await self.db.execute(policy_query)
        policy = policy_result.scalar_one_or_none()
        if policy:
            safety_stock = float(policy.ss_quantity or policy.reorder_point or 50.0)
            reorder_point = float(policy.reorder_point or safety_stock * 2)
        else:
            safety_stock = 50.0
            reorder_point = 100.0

        return InventoryPosition(
            product_id=product_id,
            location_id=str(site_id),
            on_hand=float(on_hand),
            on_order=float(on_order),
            in_transit=float(in_transit),
            backlog=float(backlog),
            safety_stock=safety_stock,
            reorder_point=reorder_point,
            forecast_demand=forecast_demand,
        )

    async def _get_suppliers_for_product(
        self,
        config_id: int,
        site_id: int,
        product_id: str,
    ) -> List[SupplierInfo]:
        """Get supplier information for a product."""
        # Get upstream transportation lanes for this site
        result = await self.db.execute(
            select(TransportationLane).where(
                and_(
                    TransportationLane.config_id == config_id,
                    TransportationLane.to_site_id == site_id,
                )
            )
        )
        lanes = result.scalars().all()

        suppliers = []
        for lane in lanes:
            # Get source node
            source_node = await self.db.get(Site, lane.from_site_id)
            if source_node:
                lead_time = 1.0  # Default
                if lane.supply_lead_time and isinstance(lane.supply_lead_time, dict):
                    lead_time = lane.supply_lead_time.get("min", 1.0)

                suppliers.append(SupplierInfo(
                    supplier_id=str(source_node.id),
                    supplier_name=source_node.name or source_node.dag_type,
                    lead_time=lead_time,
                    min_order_qty=0.0,
                    unit_cost=10.0,  # Default
                    reliability_score=0.95,
                    is_preferred=True,
                ))

        return suppliers

    async def _get_active_purchase_orders(
        self,
        config_id: int,
        scenario_id: Optional[int] = None,
    ) -> List[PurchaseOrder]:
        """Get active purchase orders."""
        query = select(PurchaseOrder).where(
            and_(
                PurchaseOrder.config_id == config_id,
                PurchaseOrder.status.in_(["APPROVED", "ACKNOWLEDGED", "SHIPPED", "PARTIALLY_SHIPPED"]),
            )
        )
        if scenario_id:
            query = query.where(PurchaseOrder.scenario_id == scenario_id)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def _get_active_transfer_orders(
        self,
        config_id: int,
        scenario_id: Optional[int] = None,
    ) -> List[TransferOrder]:
        """Get active transfer orders."""
        query = select(TransferOrder).where(
            and_(
                TransferOrder.config_id == config_id,
                TransferOrder.status == "IN_TRANSIT",
            )
        )
        if scenario_id:
            query = query.where(TransferOrder.scenario_id == scenario_id)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    def _build_po_order_state(self, po: PurchaseOrder) -> OrderState:
        """Build OrderState from PurchaseOrder."""
        return OrderState(
            order_id=po.po_number,
            order_type=OrderType.PURCHASE_ORDER,
            status=OrderStatus(po.status.lower()) if po.status else OrderStatus.CONFIRMED,
            created_date=po.order_date or date.today(),
            expected_delivery_date=po.requested_delivery_date or date.today(),
            actual_delivery_date=po.actual_delivery_date,
            source_site=str(po.supplier_site_id),
            destination_site=str(po.destination_site_id),
            quantity=po.total_amount or 0.0,
            shipped_quantity=0.0,
            received_quantity=0.0,
            last_update=po.updated_at.date() if po.updated_at else date.today(),
            days_since_last_update=(datetime.utcnow() - (po.updated_at or datetime.utcnow())).days,
        )

    def _build_to_order_state(self, to: TransferOrder) -> OrderState:
        """Build OrderState from TransferOrder."""
        return OrderState(
            order_id=to.to_number,
            order_type=OrderType.TRANSFER_ORDER,
            status=OrderStatus(to.status.lower()) if to.status else OrderStatus.IN_TRANSIT,
            created_date=to.order_date or date.today(),
            expected_delivery_date=to.estimated_delivery_date or date.today(),
            actual_delivery_date=to.actual_delivery_date,
            source_site=str(to.source_site_id),
            destination_site=str(to.destination_site_id),
            quantity=0.0,  # Would need to sum line items
            shipped_quantity=0.0,
            received_quantity=0.0,
            last_update=to.updated_at.date() if to.updated_at else date.today(),
            days_since_last_update=(datetime.utcnow() - (to.updated_at or datetime.utcnow())).days,
        )

    async def _get_all_products(self, config_id: int) -> List[str]:
        """Get all products in a config."""
        result = await self.db.execute(
            select(InvLevel.product_id.distinct()).where(
                InvLevel.config_id == config_id
            )
        )
        return [row[0] for row in result.fetchall()]

    async def _build_site_inventory_states(
        self,
        config_id: int,
        product_id: str,
    ) -> List[SiteInventoryState]:
        """Build site inventory states for rebalancing."""
        # Get all inventory levels for this product
        result = await self.db.execute(
            select(InvLevel).where(
                and_(
                    InvLevel.config_id == config_id,
                    InvLevel.product_id == product_id,
                )
            )
        )
        inv_levels = result.scalars().all()

        states = []
        for inv in inv_levels:
            # Get node info
            node = await self.db.get(Site, inv.site_id)

            # Calculate days of supply (simplified)
            avg_demand = 100.0  # Placeholder - should come from forecast
            dos = inv.quantity / avg_demand if avg_demand > 0 else float('inf')

            states.append(SiteInventoryState(
                site_id=str(inv.site_id),
                site_name=node.name if node else str(inv.site_id),
                product_id=product_id,
                on_hand=float(inv.quantity),
                safety_stock=50.0,  # Placeholder
                days_of_supply=dos,
                forecast_demand=avg_demand,
                is_dc=node.master_type == "INVENTORY" if node else False,
            ))

        return states

    async def _get_transfer_lanes(self, config_id: int) -> List[TransferLane]:
        """Get transfer lanes for rebalancing."""
        result = await self.db.execute(
            select(TransportationLane).where(TransportationLane.config_id == config_id)
        )
        lanes = result.scalars().all()

        transfer_lanes = []
        for lane in lanes:
            lead_time = 1.0
            if lane.supply_lead_time and isinstance(lane.supply_lead_time, dict):
                lead_time = lane.supply_lead_time.get("min", 1.0)

            transfer_lanes.append(TransferLane(
                from_site=str(lane.from_site_id),
                to_site=str(lane.to_site_id),
                lead_time=lead_time,
                cost_per_unit=5.0,  # Placeholder
                min_transfer_qty=0.0,
                max_transfer_qty=float('inf'),
            ))

        return transfer_lanes

    async def _get_site_id_by_name(
        self,
        config_id: int,
        site_name: str,
    ) -> Optional[int]:
        """Get site ID by name or ID string."""
        # Try as integer first
        try:
            return int(site_name)
        except ValueError:
            pass

        # Query by name
        result = await self.db.execute(
            select(Site.id).where(
                and_(
                    Site.config_id == config_id,
                    Site.name == site_name,
                )
            )
        )
        return result.scalar_one_or_none()

    # =========================================================================
    # Helper Methods - Logging for Training
    # =========================================================================

    async def _log_atp_decision(
        self,
        config_id: int,
        request: ATPRequest,
        response: ATPResponse,
    ) -> None:
        """Log ATP decision for TRM training."""
        logger.info(
            f"ATP Decision: config={config_id}, order={request.order_id}, "
            f"product={request.product_id}, qty={request.requested_qty}, "
            f"can_fulfill={response.can_fulfill}, confidence={response.confidence}"
        )
        try:
            from app.models.powell_decisions import PowellATPDecision

            from app.services.powell.decision_reasoning import atp_reasoning
            method = response.source if hasattr(response, 'source') else "heuristic"
            breakdown = response.consumption_breakdown if hasattr(response, 'consumption_breakdown') else None
            record = PowellATPDecision(
                config_id=config_id,
                order_id=request.order_id,
                product_id=request.product_id,
                location_id=request.location_id,
                requested_qty=request.requested_qty,
                order_priority=request.priority,
                can_fulfill=response.can_fulfill,
                promised_qty=response.promised_qty,
                consumption_breakdown=breakdown,
                decision_method=method,
                confidence=response.confidence,
                decision_reasoning=atp_reasoning(
                    product_id=request.product_id,
                    location_id=request.location_id,
                    requested_qty=request.requested_qty,
                    promised_qty=response.promised_qty,
                    can_fulfill=response.can_fulfill,
                    order_priority=request.priority,
                    confidence=response.confidence,
                    decision_method=method,
                    consumption_breakdown=breakdown,
                ),
            )
            self.db.add(record)
            await self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to log ATP decision: {e}")

    async def _log_po_decision(
        self,
        config_id: int,
        state: Any,
        recommendation: PORecommendation,
    ) -> None:
        """Log PO decision for TRM training."""
        logger.info(
            f"PO Decision: config={config_id}, product={recommendation.product_id}, "
            f"supplier={recommendation.supplier.supplier_id}, qty={recommendation.recommended_qty}, "
            f"confidence={recommendation.confidence}"
        )
        try:
            from app.models.powell_decisions import PowellPODecision

            inv_pos = getattr(state, 'inventory_position', None)
            on_hand = getattr(inv_pos, 'on_hand', 0.0) if inv_pos else 0.0
            forecast = getattr(inv_pos, 'forecast_demand', 0.0) if inv_pos else 0.0
            dos = on_hand / (forecast / 30.0) if forecast and forecast > 0 else 0.0

            from app.services.powell.decision_reasoning import po_reasoning
            trigger = getattr(recommendation, 'trigger_reason', 'low_inventory')
            urg = getattr(recommendation, 'urgency', 'normal')
            exp_cost = recommendation.recommended_qty * recommendation.supplier.unit_cost
            record = PowellPODecision(
                config_id=config_id,
                product_id=recommendation.product_id,
                location_id=recommendation.location_id,
                supplier_id=recommendation.supplier.supplier_id,
                recommended_qty=recommendation.recommended_qty,
                trigger_reason=trigger,
                urgency=urg,
                confidence=recommendation.confidence,
                inventory_position=on_hand,
                days_of_supply=dos,
                forecast_30_day=forecast,
                expected_receipt_date=date.today() + timedelta(days=int(recommendation.supplier.lead_time)),
                expected_cost=exp_cost,
                decision_reasoning=po_reasoning(
                    product_id=recommendation.product_id,
                    location_id=recommendation.location_id,
                    supplier_id=recommendation.supplier.supplier_id,
                    recommended_qty=recommendation.recommended_qty,
                    trigger_reason=str(trigger),
                    urgency=str(urg),
                    confidence=recommendation.confidence,
                    inventory_position=on_hand,
                    expected_cost=exp_cost,
                ),
            )
            self.db.add(record)
            await self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to log PO decision: {e}")

    async def _log_po_execution(
        self,
        config_id: int,
        recommendation: PORecommendation,
        po_id: int,
        po_number: str,
    ) -> None:
        """Log PO execution outcome for TRM training."""
        logger.info(
            f"PO Executed: config={config_id}, po_id={po_id}, po_number={po_number}, "
            f"product={recommendation.product_id}, qty={recommendation.recommended_qty}"
        )

    async def _log_exception_detection(
        self,
        config_id: int,
        order_state: OrderState,
        detection: ExceptionDetection,
    ) -> None:
        """Log exception detection for TRM training."""
        logger.info(
            f"Exception Detected: config={config_id}, order={order_state.order_id}, "
            f"type={detection.exception_type.value}, severity={detection.severity.value}, "
            f"action={detection.recommended_action.value}"
        )
        try:
            from app.models.powell_decisions import PowellOrderException

            from app.services.powell.decision_reasoning import order_tracking_reasoning
            desc = detection.description if hasattr(detection, 'description') else str(detection.exception_type.value)
            record = PowellOrderException(
                config_id=config_id,
                order_id=order_state.order_id,
                order_type=order_state.order_type.value,
                order_status=order_state.status.value,
                exception_type=detection.exception_type.value,
                severity=detection.severity.value,
                recommended_action=detection.recommended_action.value,
                description=desc,
                confidence=detection.confidence,
                state_features={
                    "source_site": order_state.source_site,
                    "destination_site": order_state.destination_site,
                    "quantity": order_state.quantity,
                    "shipped_qty": order_state.shipped_quantity,
                    "received_qty": order_state.received_quantity,
                    "days_since_last_update": order_state.days_since_last_update,
                },
                decision_reasoning=order_tracking_reasoning(
                    order_id=order_state.order_id,
                    exception_type=detection.exception_type.value,
                    severity=detection.severity.value,
                    recommended_action=detection.recommended_action.value,
                    confidence=detection.confidence,
                    reason=desc,
                ),
            )
            self.db.add(record)
            await self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to log exception detection: {e}")

    async def _log_rebalance_decision(
        self,
        config_id: int,
        recommendation: RebalanceRecommendation,
    ) -> None:
        """Log rebalancing decision for TRM training."""
        logger.info(
            f"Rebalance Decision: config={config_id}, "
            f"from={recommendation.from_site} to={recommendation.to_site}, "
            f"product={recommendation.product_id}, qty={recommendation.recommended_qty}, "
            f"reason={recommendation.reason.value}, confidence={recommendation.confidence}"
        )
        try:
            from app.models.powell_decisions import PowellRebalanceDecision

            impact = recommendation.expected_impact if hasattr(recommendation, 'expected_impact') else {}

            from app.services.powell.decision_reasoning import rebalancing_reasoning, get_product_costs
            from app.db.session import sync_session_factory
            _sync_db = sync_session_factory()
            record = PowellRebalanceDecision(
                config_id=config_id,
                product_id=recommendation.product_id,
                from_site=recommendation.from_site,
                to_site=recommendation.to_site,
                recommended_qty=recommendation.recommended_qty,
                reason=recommendation.reason.value,
                urgency=recommendation.urgency,
                confidence=recommendation.confidence,
                source_dos_before=impact.get("source_dos_before") if isinstance(impact, dict) else None,
                source_dos_after=impact.get("source_dos_after") if isinstance(impact, dict) else None,
                dest_dos_before=impact.get("dest_dos_before") if isinstance(impact, dict) else None,
                dest_dos_after=impact.get("dest_dos_after") if isinstance(impact, dict) else None,
                expected_cost=impact.get("expected_cost") if isinstance(impact, dict) else None,
                decision_reasoning=rebalancing_reasoning(
                    product_id=recommendation.product_id,
                    from_site=recommendation.from_site,
                    to_site=recommendation.to_site,
                    recommended_qty=recommendation.recommended_qty,
                    confidence=recommendation.confidence,
                    reason=recommendation.reason.value,
                    source_dos_before=impact.get("source_dos_before") if isinstance(impact, dict) else None,
                    dest_dos_before=impact.get("dest_dos_before") if isinstance(impact, dict) else None,
                    dest_dos_after=impact.get("dest_dos_after") if isinstance(impact, dict) else None,
                    expected_cost=impact.get("expected_cost") if isinstance(impact, dict) else None,
                    **dict(zip(("unit_cost", "unit_price"), get_product_costs(_sync_db, recommendation.product_id))),
                ),
            )
            self.db.add(record)
            await self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to log rebalance decision: {e}")

    async def _save_allocation_consumption(
        self,
        config_id: int,
        product_id: str,
        location_id: str,
        consumption_result: Any,
    ) -> None:
        """Save allocation consumption to database.

        Updates powell_allocations rows to reflect consumed quantities
        from each priority tier based on the ConsumptionResult.
        """
        fulfilled = getattr(consumption_result, 'fulfilled_qty', None) or getattr(consumption_result, 'consumed_qty', 0)
        logger.info(
            f"Allocation consumed: config={config_id}, product={product_id}, "
            f"location={location_id}, qty={fulfilled}"
        )
        try:
            from app.models.powell_allocation import PowellAllocation
            from sqlalchemy import and_

            consumption_map = getattr(consumption_result, 'consumption_by_priority', None) or {}
            now = datetime.utcnow()

            for priority, consumed_qty in consumption_map.items():
                if consumed_qty <= 0:
                    continue
                result = await self.db.execute(
                    select(PowellAllocation).where(and_(
                        PowellAllocation.config_id == config_id,
                        PowellAllocation.product_id == product_id,
                        PowellAllocation.location_id == location_id,
                        PowellAllocation.priority == int(priority),
                        PowellAllocation.is_active == True,
                        PowellAllocation.valid_from <= now,
                        PowellAllocation.valid_to >= now,
                    ))
                )
                alloc = result.scalar_one_or_none()
                if alloc is not None:
                    alloc.consumed_qty = (alloc.consumed_qty or 0) + consumed_qty
                else:
                    logger.warning(
                        f"No active allocation found for config={config_id}, "
                        f"product={product_id}, location={location_id}, priority={priority}"
                    )

            await self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to save allocation consumption: {e}")

    # ── New TRM decision logging (MO, TO, Quality, Maintenance, Subcontracting, Forecast) ──

    async def _log_mo_decision(
        self,
        config_id: int,
        recommendation: Any,
    ) -> None:
        """Log Manufacturing Order execution decision for TRM training."""
        logger.info(
            f"MO Decision: config={config_id}, order={getattr(recommendation, 'order_id', '?')}, "
            f"type={getattr(recommendation, 'decision_type', '?')}, "
            f"confidence={getattr(recommendation, 'confidence', 0)}"
        )
        try:
            from app.models.powell_decisions import PowellMODecision

            record = PowellMODecision(
                config_id=config_id,
                production_order_id=getattr(recommendation, 'order_id', ''),
                product_id=getattr(recommendation, 'product_id', ''),
                site_id=getattr(recommendation, 'site_id', ''),
                planned_qty=getattr(recommendation, 'planned_qty', 0.0),
                decision_type=getattr(recommendation, 'decision_type', 'release'),
                sequence_position=getattr(recommendation, 'recommended_sequence_position', None),
                priority_override=getattr(recommendation, 'priority_override', None),
                resource_id=getattr(recommendation, 'resource_id', None),
                setup_time_hours=getattr(recommendation, 'setup_time_hours', None),
                run_time_hours=getattr(recommendation, 'run_time_hours', None),
                confidence=getattr(recommendation, 'confidence', None),
                state_features={
                    "capacity_impact_pct": getattr(recommendation, 'capacity_impact_pct', None),
                    "service_risk": getattr(recommendation, 'service_risk', None),
                    "expedite": getattr(recommendation, 'expedite', False),
                    "defer_days": getattr(recommendation, 'defer_days', None),
                },
            )
            self.db.add(record)
            await self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to log MO decision: {e}")

    async def _log_to_decision(
        self,
        config_id: int,
        recommendation: Any,
    ) -> None:
        """Log Transfer Order execution decision for TRM training."""
        logger.info(
            f"TO Decision: config={config_id}, order={getattr(recommendation, 'order_id', '?')}, "
            f"type={getattr(recommendation, 'decision_type', '?')}, "
            f"confidence={getattr(recommendation, 'confidence', 0)}"
        )
        try:
            from app.models.powell_decisions import PowellTODecision

            record = PowellTODecision(
                config_id=config_id,
                transfer_order_id=getattr(recommendation, 'order_id', ''),
                product_id=getattr(recommendation, 'product_id', ''),
                source_site_id=getattr(recommendation, 'source_site_id', ''),
                dest_site_id=getattr(recommendation, 'dest_site_id', ''),
                planned_qty=getattr(recommendation, 'planned_qty', 0.0),
                decision_type=getattr(recommendation, 'decision_type', 'release'),
                transportation_mode=getattr(recommendation, 'transportation_mode', None),
                estimated_transit_days=getattr(recommendation, 'estimated_transit_days', None),
                priority=getattr(recommendation, 'priority', None),
                trigger_reason=getattr(recommendation, 'trigger_reason', None),
                confidence=getattr(recommendation, 'confidence', None),
                state_features={
                    "dest_stockout_risk": getattr(recommendation, 'dest_stockout_risk', None),
                    "source_depletion_risk": getattr(recommendation, 'source_depletion_risk', None),
                    "cost_impact": getattr(recommendation, 'cost_impact', None),
                    "expedite": getattr(recommendation, 'expedite', False),
                    "consolidate_with": getattr(recommendation, 'consolidate_with', None),
                },
            )
            self.db.add(record)
            await self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to log TO decision: {e}")

    async def _log_quality_decision(
        self,
        config_id: int,
        recommendation: Any,
    ) -> None:
        """Log Quality disposition decision for TRM training."""
        logger.info(
            f"Quality Decision: config={config_id}, "
            f"order={getattr(recommendation, 'quality_order_id', '?')}, "
            f"disposition={getattr(recommendation, 'disposition', '?')}, "
            f"confidence={getattr(recommendation, 'confidence', 0)}"
        )
        try:
            from app.models.powell_decisions import PowellQualityDecision

            record = PowellQualityDecision(
                config_id=config_id,
                quality_order_id=getattr(recommendation, 'quality_order_id', ''),
                product_id=getattr(recommendation, 'product_id', ''),
                site_id=getattr(recommendation, 'site_id', ''),
                lot_number=getattr(recommendation, 'lot_number', None),
                inspection_type=getattr(recommendation, 'inspection_type', None),
                inspection_qty=getattr(recommendation, 'inspection_qty', None),
                defect_rate=getattr(recommendation, 'defect_rate', None),
                defect_category=getattr(recommendation, 'defect_category', None),
                severity_level=getattr(recommendation, 'severity_level', None),
                disposition=getattr(recommendation, 'disposition', 'accept'),
                disposition_reason=getattr(recommendation, 'disposition_reason', None),
                rework_cost_estimate=getattr(recommendation, 'rework_cost', None),
                scrap_cost_estimate=getattr(recommendation, 'scrap_cost', None),
                service_risk_if_accepted=getattr(recommendation, 'service_risk', None),
                confidence=getattr(recommendation, 'confidence', None),
                state_features={
                    "accept_qty": getattr(recommendation, 'accept_qty', None),
                    "reject_qty": getattr(recommendation, 'reject_qty', None),
                    "rework_qty": getattr(recommendation, 'rework_qty', None),
                    "scrap_qty": getattr(recommendation, 'scrap_qty', None),
                },
            )
            self.db.add(record)
            await self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to log quality decision: {e}")

    async def _log_maintenance_decision(
        self,
        config_id: int,
        recommendation: Any,
    ) -> None:
        """Log Maintenance scheduling decision for TRM training."""
        logger.info(
            f"Maintenance Decision: config={config_id}, "
            f"order={getattr(recommendation, 'order_id', '?')}, "
            f"type={getattr(recommendation, 'decision_type', '?')}, "
            f"confidence={getattr(recommendation, 'confidence', 0)}"
        )
        try:
            from app.models.powell_decisions import PowellMaintenanceDecision

            record = PowellMaintenanceDecision(
                config_id=config_id,
                maintenance_order_id=getattr(recommendation, 'order_id', ''),
                asset_id=getattr(recommendation, 'asset_id', ''),
                site_id=getattr(recommendation, 'site_id', ''),
                maintenance_type=getattr(recommendation, 'maintenance_type', 'preventive'),
                decision_type=getattr(recommendation, 'decision_type', 'schedule'),
                scheduled_date=getattr(recommendation, 'recommended_date', None),
                deferred_to_date=getattr(recommendation, 'defer_to_date', None),
                estimated_downtime_hours=getattr(recommendation, 'production_impact_hours', None),
                production_impact_units=getattr(recommendation, 'production_impact_units', None),
                spare_parts_available=getattr(recommendation, 'spare_parts_available', None),
                priority=getattr(recommendation, 'priority', None),
                risk_score_if_deferred=getattr(recommendation, 'defer_risk', None),
                confidence=getattr(recommendation, 'confidence', None),
                state_features={
                    "breakdown_probability": getattr(recommendation, 'breakdown_probability', None),
                    "cost_estimate": getattr(recommendation, 'cost_estimate', None),
                    "outsource": getattr(recommendation, 'outsource', False),
                    "combine_with": getattr(recommendation, 'combine_with', None),
                },
            )
            self.db.add(record)
            await self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to log maintenance decision: {e}")

    async def _log_subcontracting_decision(
        self,
        config_id: int,
        recommendation: Any,
    ) -> None:
        """Log Subcontracting routing decision for TRM training."""
        logger.info(
            f"Subcontracting Decision: config={config_id}, "
            f"product={getattr(recommendation, 'product_id', '?')}, "
            f"type={getattr(recommendation, 'decision_type', '?')}, "
            f"confidence={getattr(recommendation, 'confidence', 0)}"
        )
        try:
            from app.models.powell_decisions import PowellSubcontractingDecision

            record = PowellSubcontractingDecision(
                config_id=config_id,
                product_id=getattr(recommendation, 'product_id', ''),
                site_id=getattr(recommendation, 'site_id', ''),
                subcontractor_id=getattr(recommendation, 'recommended_vendor', ''),
                planned_qty=getattr(recommendation, 'external_quantity', 0.0) + getattr(recommendation, 'internal_quantity', 0.0),
                decision_type=getattr(recommendation, 'decision_type', 'keep_internal'),
                reason=getattr(recommendation, 'reason', None),
                internal_capacity_pct=getattr(recommendation, 'internal_capacity_pct', None),
                subcontractor_lead_time_days=getattr(recommendation, 'subcontractor_lead_time_days', None),
                subcontractor_cost_per_unit=getattr(recommendation, 'external_cost', None),
                internal_cost_per_unit=getattr(recommendation, 'internal_cost', None),
                quality_score=getattr(recommendation, 'quality_risk', None),
                on_time_score=getattr(recommendation, 'delivery_risk', None),
                confidence=getattr(recommendation, 'confidence', None),
                state_features={
                    "internal_quantity": getattr(recommendation, 'internal_quantity', None),
                    "external_quantity": getattr(recommendation, 'external_quantity', None),
                    "total_cost": getattr(recommendation, 'total_cost', None),
                    "cost_savings": getattr(recommendation, 'cost_savings', None),
                },
            )
            self.db.add(record)
            await self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to log subcontracting decision: {e}")

    async def _log_forecast_adjustment_decision(
        self,
        config_id: int,
        recommendation: Any,
    ) -> None:
        """Log Forecast adjustment decision for TRM training."""
        logger.info(
            f"Forecast Adjustment Decision: config={config_id}, "
            f"product={getattr(recommendation, 'product_id', '?')}, "
            f"direction={getattr(recommendation, 'direction', '?')}, "
            f"pct={getattr(recommendation, 'adjustment_pct', '?')}, "
            f"confidence={getattr(recommendation, 'confidence', 0)}"
        )
        try:
            from app.models.powell_decisions import PowellForecastAdjustmentDecision

            record = PowellForecastAdjustmentDecision(
                config_id=config_id,
                product_id=getattr(recommendation, 'product_id', ''),
                site_id=getattr(recommendation, 'site_id', ''),
                signal_source=getattr(recommendation, 'signal_source', 'simulation'),
                signal_type=getattr(recommendation, 'signal_type', 'demand_increase'),
                signal_text=getattr(recommendation, 'signal_text', None),
                signal_confidence=getattr(recommendation, 'signal_confidence', None),
                current_forecast_value=getattr(recommendation, 'current_forecast_value', None),
                adjustment_direction=getattr(recommendation, 'direction', 'no_change'),
                adjustment_magnitude=getattr(recommendation, 'adjustment_magnitude', None),
                adjustment_pct=getattr(recommendation, 'adjustment_pct', None),
                adjusted_forecast_value=getattr(recommendation, 'adjusted_forecast_value', None),
                time_horizon_periods=getattr(recommendation, 'time_horizon_periods', None),
                reason=getattr(recommendation, 'reason', None),
                confidence=getattr(recommendation, 'confidence', None),
                state_features={
                    "auto_applicable": getattr(recommendation, 'auto_applicable', False),
                    "requires_human_review": getattr(recommendation, 'requires_human_review', True),
                },
            )
            self.db.add(record)
            await self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to log forecast adjustment decision: {e}")


# Factory function for dependency injection
async def get_powell_integration_service(
    db: AsyncSession,
    config: Optional[IntegrationConfig] = None,
) -> PowellIntegrationService:
    """Factory function to create PowellIntegrationService."""
    return PowellIntegrationService(db, config)
