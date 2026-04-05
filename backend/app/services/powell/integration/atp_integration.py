"""
ATP Integration

Connects SiteAgent's AATP engine to the existing ATP service.
Provides priority-based ATP calculations with TRM exception handling.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import date, datetime
from dataclasses import dataclass, asdict

from sqlalchemy.orm import Session

from app.services.powell.site_agent import SiteAgent, SiteAgentConfig, ATPResponse
from app.services.powell.engines import (
    AATPEngine,
    ATPAllocation,
    Order,
    ATPResult,
    Priority,
)
from app.services.atp_service import (
    ATPService,
    ATPResult as LegacyATPResult,
    CustomerDemand,
    AllocationResult,
)

logger = logging.getLogger(__name__)


@dataclass
class PriorityATPRequest:
    """Request for priority-based ATP check"""
    order_id: str
    product_id: str
    location_id: str
    requested_qty: float
    requested_date: date
    priority: int  # 1=critical, 5=standard
    customer_id: str
    order_type: str = "standard"


@dataclass
class PriorityATPResponse:
    """Response with priority consumption details"""
    order_id: str
    can_fulfill: bool
    promised_qty: float
    shortage_qty: float
    promise_date: date
    consumption_detail: List[Tuple[int, float]]  # [(priority, qty consumed)]
    source: str  # deterministic, trm_adjusted
    confidence: float
    exception_action: Optional[str]  # partial_fill, substitute, defer, escalate
    explanation: str


class SiteAgentATPAdapter:
    """
    Adapter that connects SiteAgent's AATP engine to existing ATP service.

    Provides:
    - Priority-based ATP with tier consumption rules
    - TRM-based exception handling for shortages
    - Integration with legacy ATP service
    """

    def __init__(
        self,
        db: Session,
        use_trm: bool = True
    ):
        """
        Initialize ATP adapter.

        Args:
            db: Database session
            use_trm: Enable TRM exception handling
        """
        self.db = db
        self.use_trm = use_trm
        self._site_agents: Dict[str, SiteAgent] = {}
        self._legacy_atp_service = ATPService(db)

    def get_site_agent(self, site_key: str) -> SiteAgent:
        """Get or create SiteAgent for a site."""
        if site_key not in self._site_agents:
            agent_config = SiteAgentConfig(
                site_key=site_key,
                use_trm_adjustments=self.use_trm,
                agent_mode="copilot",
            )
            self._site_agents[site_key] = SiteAgent(agent_config)
        return self._site_agents[site_key]

    async def check_priority_atp(
        self,
        request: PriorityATPRequest
    ) -> PriorityATPResponse:
        """
        Check ATP with priority-based consumption.

        Uses SiteAgent's AATP engine for deterministic priority consumption,
        with optional TRM exception handling for shortages.

        Args:
            request: Priority ATP request

        Returns:
            Priority ATP response with consumption details
        """
        site_agent = self.get_site_agent(request.location_id)

        # Convert to engine order
        order = Order(
            order_id=request.order_id,
            product_id=request.product_id,
            location_id=request.location_id,
            requested_qty=request.requested_qty,
            requested_date=request.requested_date,
            priority=Priority.from_value(request.priority),
            customer_id=request.customer_id,
            order_type=request.order_type,
        )

        # Execute ATP through SiteAgent
        atp_response = await site_agent.execute_atp(order)

        # Build consumption detail from result
        consumption_detail = []
        if hasattr(atp_response, 'consumption_detail') and atp_response.consumption_detail:
            consumption_detail = [
                (p.value, qty) for p, qty in atp_response.consumption_detail
            ]

        return PriorityATPResponse(
            order_id=atp_response.order_id,
            can_fulfill=atp_response.promised_qty >= request.requested_qty,
            promised_qty=atp_response.promised_qty,
            shortage_qty=max(0, request.requested_qty - atp_response.promised_qty),
            promise_date=atp_response.promise_date,
            consumption_detail=consumption_detail,
            source=atp_response.source,
            confidence=atp_response.confidence,
            exception_action=atp_response.exception_action,
            explanation=atp_response.explanation,
        )

    async def check_batch_atp(
        self,
        requests: List[PriorityATPRequest]
    ) -> List[PriorityATPResponse]:
        """
        Check ATP for multiple orders.

        Args:
            requests: List of priority ATP requests

        Returns:
            List of priority ATP responses
        """
        results = []
        for request in requests:
            result = await self.check_priority_atp(request)
            results.append(result)
        return results

    def load_allocations_from_tgnn(
        self,
        site_key: str,
        allocations: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Load priority allocations from tGNN into AATP engine.

        This is the integration point where tGNN-generated allocations
        feed into the deterministic AATP consumption logic.

        Args:
            site_key: Site identifier
            allocations: List of allocations from tGNN
                [{product_id, location_id, priority, allocated_qty, period_start, period_end}]

        Returns:
            Summary of loaded allocations
        """
        site_agent = self.get_site_agent(site_key)

        # Convert to ATPAllocation objects
        atp_allocations = []
        for alloc in allocations:
            atp_alloc = ATPAllocation(
                product_id=alloc['product_id'],
                location_id=alloc.get('location_id', site_key),
                priority=Priority.from_value(alloc.get('priority', 3)),
                allocated_qty=alloc['allocated_qty'],
                # TODO(virtual-clock): adapter has no config_id/tenant_id; thread tenant
                # context through load_allocations_from_tgnn to use tenant_today_sync.
                period_start=alloc.get('period_start', date.today()),
                period_end=alloc.get('period_end', date.today()),
            )
            atp_allocations.append(atp_alloc)

        # Load into engine
        site_agent.aatp_engine.load_allocations(atp_allocations)

        # Return summary
        summary = site_agent.aatp_engine.get_allocation_summary()
        summary['allocations_loaded'] = len(atp_allocations)
        summary['site_key'] = site_key

        logger.info(f"Loaded {len(atp_allocations)} allocations for site {site_key}")
        return summary

    def get_available_by_priority(
        self,
        site_key: str,
        product_id: str
    ) -> Dict[int, float]:
        """
        Get available ATP by priority tier.

        Args:
            site_key: Site identifier
            product_id: Product identifier

        Returns:
            {priority: available_qty}
        """
        site_agent = self.get_site_agent(site_key)
        available = site_agent.aatp_engine.get_available_by_priority(
            product_id, site_key
        )
        # Convert Priority enum keys to int
        return {p.value: qty for p, qty in available.items()}

    def commit_atp_consumption(
        self,
        request: PriorityATPRequest,
        response: PriorityATPResponse
    ) -> bool:
        """
        Commit ATP consumption after order confirmation.

        Args:
            request: Original ATP request
            response: ATP response to commit

        Returns:
            True if commit successful
        """
        site_agent = self.get_site_agent(request.location_id)

        order = Order(
            order_id=request.order_id,
            product_id=request.product_id,
            location_id=request.location_id,
            requested_qty=response.promised_qty,
            requested_date=request.requested_date,
            priority=Priority.from_value(request.priority),
            customer_id=request.customer_id,
            order_type=request.order_type,
        )

        # Build ATPResult for commit
        result = ATPResult(
            can_fulfill_full=response.can_fulfill,
            available_qty=response.promised_qty,
            shortage_qty=response.shortage_qty,
            consumption_detail=[
                (Priority.from_value(p), qty)
                for p, qty in response.consumption_detail
            ],
            promise_date=response.promise_date,
        )

        try:
            site_agent.aatp_engine.commit_consumption(order, result)
            logger.info(f"Committed ATP consumption for order {request.order_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to commit ATP: {e}")
            return False

    def convert_to_legacy_atp(
        self,
        response: PriorityATPResponse
    ) -> LegacyATPResult:
        """
        Convert SiteAgent ATP response to legacy ATP service format.

        Enables seamless integration with existing ATP-based workflows.

        Args:
            response: Priority ATP response

        Returns:
            Legacy ATPResult for compatibility
        """
        return LegacyATPResult(
            on_hand=0,  # Not tracked in priority ATP
            scheduled_receipts=0,
            allocated_orders=0,
            safety_stock=0,
            atp=int(response.promised_qty),
            timestamp=datetime.utcnow().isoformat(),
        )

    async def allocate_to_customers_priority(
        self,
        site_key: str,
        product_id: str,
        demands: List[CustomerDemand],
        allocation_method: str = "priority"
    ) -> AllocationResult:
        """
        Allocate ATP to customers using priority-based rules.

        Enhanced version that respects priority tiers from AATP engine.

        Args:
            site_key: Site identifier
            product_id: Product identifier
            demands: Customer demands with priorities
            allocation_method: Allocation strategy (priority recommended)

        Returns:
            Allocation result with customer assignments
        """
        site_agent = self.get_site_agent(site_key)

        # Get total available by priority
        available_by_priority = site_agent.aatp_engine.get_available_by_priority(
            product_id, site_key
        )
        total_atp = sum(available_by_priority.values())

        # Use legacy service for allocation logic (extended for priority)
        if allocation_method == "priority":
            # Sort demands by priority (ascending = high priority first)
            sorted_demands = sorted(demands, key=lambda d: d.priority)
        else:
            sorted_demands = demands

        return self._legacy_atp_service.allocate_to_customers(
            scenario_user=None,  # Not needed for allocation logic
            demands=sorted_demands,
            available_atp=int(total_atp),
            allocation_method=allocation_method,
        )

    def get_atp_status(self, site_key: str) -> Dict[str, Any]:
        """
        Get AATP status for a site.

        Args:
            site_key: Site identifier

        Returns:
            Status summary including allocations, consumption, and TRM state
        """
        site_agent = self.get_site_agent(site_key)

        status = {
            "site_key": site_key,
            "use_trm": self.use_trm,
            "model_loaded": site_agent.model is not None,
            "allocations_summary": site_agent.aatp_engine.get_allocation_summary(),
            "timestamp": datetime.utcnow().isoformat(),
        }

        return status
