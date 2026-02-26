"""
Condition Monitor Service - Persistent Condition Detection

Monitors for conditions that persist over time and triggers appropriate actions.
This goes beyond simple threshold alerts to detect patterns like:

1. ATP SHORTFALL: No available ATP for N consecutive days
2. INVENTORY BELOW TARGET: Inventory < safety stock for N days
3. CAPACITY OVERLOAD: Utilization > threshold for N periods
4. ORDER PAST DUE: Orders that missed their delivery date
5. FORECAST DEVIATION: Actual vs forecast divergence beyond threshold
6. SUPPLY SHORTFALL: Multiple sites reporting inability to fulfill

Key Design Principles:
- Conditions must PERSIST to trigger action (not single-point alerts)
- Severity escalates with duration
- Agents can request supply from other agents (collaborative resolution)
- Conditions can trigger scenario evaluation for impact assessment

Powell Framework Integration:
- Conditions feed into belief state uncertainty
- Persistent issues increase nonconformity scores
- Multi-site patterns trigger S&OP level review
"""

from typing import Dict, Any, List, Optional, Tuple, Set
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc

from app.models.agent_action import AgentAction, ActionMode, ActionCategory
from app.models.powell import PowellBeliefState, EntityType

logger = logging.getLogger(__name__)


# =============================================================================
# Condition Types
# =============================================================================

class ConditionType(str, Enum):
    """Types of conditions to monitor."""
    # Supply-side conditions
    ATP_SHORTFALL = "atp_shortfall"                  # No ATP available
    ATP_CRITICAL = "atp_critical"                    # ATP below critical threshold
    INVENTORY_BELOW_SAFETY = "inventory_below_safety"
    INVENTORY_BELOW_TARGET = "inventory_below_target"
    INVENTORY_ABOVE_MAX = "inventory_above_max"

    # Demand-side conditions
    DEMAND_SPIKE = "demand_spike"                    # Sudden demand increase
    FORECAST_DEVIATION = "forecast_deviation"        # Actual != forecast

    # Capacity conditions
    CAPACITY_OVERLOAD = "capacity_overload"          # Utilization > max
    CAPACITY_CONSTRAINT = "capacity_constraint"      # Utilization approaching max

    # Order conditions
    ORDER_PAST_DUE = "order_past_due"
    ORDER_AT_RISK = "order_at_risk"                  # Likely to miss date

    # Network conditions
    MULTI_SITE_SHORTFALL = "multi_site_shortfall"    # Pattern across sites
    SUPPLY_CHAIN_BOTTLENECK = "supply_chain_bottleneck"


class ConditionSeverity(str, Enum):
    """Severity levels based on duration and impact."""
    INFO = "info"           # Just started, monitoring
    WARNING = "warning"     # Persisting, attention needed
    CRITICAL = "critical"   # Urgent, action required
    EMERGENCY = "emergency" # Severe, escalate immediately


class ConditionResolution(str, Enum):
    """How a condition was resolved."""
    SELF_RESOLVED = "self_resolved"       # Cleared naturally
    AGENT_RESOLVED = "agent_resolved"     # Agent took action
    HUMAN_RESOLVED = "human_resolved"     # Human override
    ESCALATED = "escalated"               # Moved to higher level
    SUPPRESSED = "suppressed"             # Acknowledged, no action


# =============================================================================
# Condition Configuration
# =============================================================================

@dataclass
class ConditionConfig:
    """Configuration for a condition type."""
    condition_type: ConditionType
    threshold_value: float           # Threshold that triggers condition
    persistence_hours: int           # Hours before severity escalates
    check_interval_minutes: int      # How often to check
    severity_escalation: Dict[int, ConditionSeverity]  # hours -> severity
    agent_types: List[str]           # Which agents can handle
    requires_scenario_eval: bool     # Should evaluate alternatives
    can_request_supply: bool         # Can ask other agents for help
    triggers_soop: bool              # Triggers S&OP review


# Default condition configurations
CONDITION_CONFIGS: Dict[ConditionType, ConditionConfig] = {
    ConditionType.ATP_SHORTFALL: ConditionConfig(
        condition_type=ConditionType.ATP_SHORTFALL,
        threshold_value=0,           # No ATP available
        persistence_hours=24,        # Persists for 24 hours
        check_interval_minutes=60,   # Check hourly
        severity_escalation={
            0: ConditionSeverity.INFO,
            24: ConditionSeverity.WARNING,
            48: ConditionSeverity.CRITICAL,
            72: ConditionSeverity.EMERGENCY,
        },
        agent_types=["trm_atp", "trm_rebalance", "trm_po_creation"],
        requires_scenario_eval=True,
        can_request_supply=True,
        triggers_soop=False,
    ),
    ConditionType.INVENTORY_BELOW_SAFETY: ConditionConfig(
        condition_type=ConditionType.INVENTORY_BELOW_SAFETY,
        threshold_value=1.0,         # At or below safety stock
        persistence_hours=48,
        check_interval_minutes=60,
        severity_escalation={
            0: ConditionSeverity.WARNING,
            48: ConditionSeverity.CRITICAL,
            72: ConditionSeverity.EMERGENCY,
        },
        agent_types=["trm_rebalance", "trm_po_creation"],
        requires_scenario_eval=True,
        can_request_supply=True,
        triggers_soop=False,
    ),
    ConditionType.CAPACITY_OVERLOAD: ConditionConfig(
        condition_type=ConditionType.CAPACITY_OVERLOAD,
        threshold_value=0.95,        # 95% utilization
        persistence_hours=24,
        check_interval_minutes=120,
        severity_escalation={
            0: ConditionSeverity.INFO,
            24: ConditionSeverity.WARNING,
            72: ConditionSeverity.CRITICAL,
        },
        agent_types=["gnn_execution"],
        requires_scenario_eval=True,
        can_request_supply=False,
        triggers_soop=True,         # Capacity issues trigger S&OP
    ),
    ConditionType.MULTI_SITE_SHORTFALL: ConditionConfig(
        condition_type=ConditionType.MULTI_SITE_SHORTFALL,
        threshold_value=3,           # 3+ sites with shortfall
        persistence_hours=24,
        check_interval_minutes=60,
        severity_escalation={
            0: ConditionSeverity.WARNING,
            24: ConditionSeverity.CRITICAL,
            48: ConditionSeverity.EMERGENCY,
        },
        agent_types=["gnn_soop", "gnn_execution"],
        requires_scenario_eval=True,
        can_request_supply=False,
        triggers_soop=True,
    ),
    ConditionType.ORDER_PAST_DUE: ConditionConfig(
        condition_type=ConditionType.ORDER_PAST_DUE,
        threshold_value=1,           # 1 day past due
        persistence_hours=0,         # Immediate
        check_interval_minutes=60,
        severity_escalation={
            0: ConditionSeverity.CRITICAL,
        },
        agent_types=["trm_order_tracking"],
        requires_scenario_eval=False,
        can_request_supply=True,
        triggers_soop=False,
    ),
    ConditionType.FORECAST_DEVIATION: ConditionConfig(
        condition_type=ConditionType.FORECAST_DEVIATION,
        threshold_value=0.25,        # 25% deviation
        persistence_hours=168,       # 1 week
        check_interval_minutes=1440, # Daily
        severity_escalation={
            0: ConditionSeverity.INFO,
            168: ConditionSeverity.WARNING,
            336: ConditionSeverity.CRITICAL,
        },
        agent_types=["gnn_soop"],
        requires_scenario_eval=True,
        can_request_supply=False,
        triggers_soop=True,
    ),
}


# =============================================================================
# Condition State
# =============================================================================

@dataclass
class ConditionState:
    """Current state of a monitored condition."""
    condition_type: ConditionType
    entity_type: str          # product, site, order, etc.
    entity_id: str
    tenant_id: int

    # Status
    is_active: bool = True
    severity: ConditionSeverity = ConditionSeverity.INFO
    first_detected: datetime = field(default_factory=datetime.utcnow)
    last_checked: datetime = field(default_factory=datetime.utcnow)
    duration_hours: float = 0.0

    # Values
    current_value: float = 0.0
    threshold_value: float = 0.0
    deviation: float = 0.0

    # Context
    context: Dict[str, Any] = field(default_factory=dict)
    related_conditions: List[str] = field(default_factory=list)

    # Resolution
    resolution: Optional[ConditionResolution] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None  # Agent or user


@dataclass
class SupplyRequest:
    """Request from one agent/site to another for supply assistance."""
    requesting_entity: str        # Site or agent requesting
    requested_entity: str         # Site or agent being asked
    product_id: str
    quantity_needed: float
    needed_by: datetime
    priority: int                 # 1=highest
    context: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"       # pending, accepted, rejected, fulfilled


# =============================================================================
# Main Service
# =============================================================================

class ConditionMonitorService:
    """
    Monitors persistent conditions and triggers appropriate actions.

    Key capabilities:
    1. Detect conditions that persist over time
    2. Escalate severity based on duration
    3. Coordinate agent responses
    4. Enable inter-agent supply requests
    5. Trigger scenario evaluation for impact assessment
    6. Detect network-wide patterns
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._active_conditions: Dict[str, ConditionState] = {}
        self._supply_requests: List[SupplyRequest] = []

    # =========================================================================
    # Condition Detection
    # =========================================================================

    async def check_conditions(
        self,
        tenant_id: int,
        condition_types: Optional[List[ConditionType]] = None,
    ) -> List[ConditionState]:
        """
        Check for conditions across all entities.

        Args:
            tenant_id: Customer to check
            condition_types: Specific conditions to check (all if None)

        Returns:
            List of active condition states
        """
        types_to_check = condition_types or list(CONDITION_CONFIGS.keys())
        detected = []

        for condition_type in types_to_check:
            config = CONDITION_CONFIGS.get(condition_type)
            if not config:
                continue

            # Check this condition type
            conditions = await self._check_condition_type(
                tenant_id=tenant_id,
                condition_type=condition_type,
                config=config,
            )
            detected.extend(conditions)

        # Check for network-wide patterns
        network_conditions = await self._detect_network_patterns(
            tenant_id=tenant_id,
            conditions=detected,
        )
        detected.extend(network_conditions)

        # Update severity based on duration
        for condition in detected:
            self._update_severity(condition, CONDITION_CONFIGS[condition.condition_type])

        logger.info(
            f"Condition check for tenant {tenant_id}: "
            f"{len(detected)} active conditions"
        )

        return detected

    async def _check_condition_type(
        self,
        tenant_id: int,
        condition_type: ConditionType,
        config: ConditionConfig,
    ) -> List[ConditionState]:
        """Check for a specific condition type."""
        conditions = []

        if condition_type == ConditionType.ATP_SHORTFALL:
            conditions = await self._check_atp_shortfall(tenant_id, config)
        elif condition_type == ConditionType.INVENTORY_BELOW_SAFETY:
            conditions = await self._check_inventory_below_safety(tenant_id, config)
        elif condition_type == ConditionType.CAPACITY_OVERLOAD:
            conditions = await self._check_capacity_overload(tenant_id, config)
        elif condition_type == ConditionType.ORDER_PAST_DUE:
            conditions = await self._check_orders_past_due(tenant_id, config)
        elif condition_type == ConditionType.FORECAST_DEVIATION:
            conditions = await self._check_forecast_deviation(tenant_id, config)

        return conditions

    async def _check_atp_shortfall(
        self,
        tenant_id: int,
        config: ConditionConfig,
    ) -> List[ConditionState]:
        """Check for ATP shortfall — active allocations with no available qty."""
        from app.models.powell_allocation import PowellAllocation
        from app.models.supply_chain_config import SupplyChainConfig

        conditions = []
        try:
            # Get config_ids belonging to this customer
            config_ids_q = select(SupplyChainConfig.id).where(
                SupplyChainConfig.tenant_id == tenant_id
            )

            # Find product/location combos where available ATP <= 0
            stmt = (
                select(
                    PowellAllocation.product_id,
                    PowellAllocation.location_id,
                    func.sum(
                        PowellAllocation.allocated_qty
                        - PowellAllocation.consumed_qty
                        - PowellAllocation.reserved_qty
                    ).label("available"),
                )
                .where(
                    PowellAllocation.is_active == True,
                    PowellAllocation.config_id.in_(config_ids_q),
                )
                .group_by(PowellAllocation.product_id, PowellAllocation.location_id)
                .having(
                    func.sum(
                        PowellAllocation.allocated_qty
                        - PowellAllocation.consumed_qty
                        - PowellAllocation.reserved_qty
                    ) <= config.threshold_value
                )
            )
            result = await self.db.execute(stmt)
            for row in result.all():
                conditions.append(ConditionState(
                    condition_type=ConditionType.ATP_SHORTFALL,
                    entity_type="product_site",
                    entity_id=f"{row.product_id}_{row.location_id}",
                    tenant_id=tenant_id,
                    current_value=float(row.available),
                    threshold_value=config.threshold_value,
                    deviation=float(config.threshold_value - row.available),
                    context={
                        "product_id": row.product_id,
                        "site_id": row.location_id,
                    },
                ))
        except Exception as e:
            logger.warning(f"ATP shortfall check failed for tenant {tenant_id}: {e}")

        return conditions

    async def _check_inventory_below_safety(
        self,
        tenant_id: int,
        config: ConditionConfig,
    ) -> List[ConditionState]:
        """Check for inventory below safety stock (abs_level policies)."""
        from app.models.sc_entities import InvLevel, InvPolicy
        from app.models.supply_chain_config import SupplyChainConfig

        conditions = []
        try:
            config_ids_q = select(SupplyChainConfig.id).where(
                SupplyChainConfig.tenant_id == tenant_id
            )

            # Join inv_level with inv_policy on product+site, filter abs_level policies
            stmt = (
                select(
                    InvLevel.product_id,
                    InvLevel.site_id,
                    InvLevel.on_hand_qty,
                    InvPolicy.ss_quantity,
                )
                .join(InvPolicy, and_(
                    InvLevel.product_id == InvPolicy.product_id,
                    InvLevel.site_id == InvPolicy.site_id,
                ))
                .where(
                    InvLevel.config_id.in_(config_ids_q),
                    InvPolicy.ss_quantity.isnot(None),
                    InvPolicy.ss_quantity > 0,
                    InvLevel.on_hand_qty < InvPolicy.ss_quantity * config.threshold_value,
                )
            )
            result = await self.db.execute(stmt)
            for row in result.all():
                ratio = row.on_hand_qty / row.ss_quantity if row.ss_quantity else 0
                conditions.append(ConditionState(
                    condition_type=ConditionType.INVENTORY_BELOW_SAFETY,
                    entity_type="product_site",
                    entity_id=f"{row.product_id}_{row.site_id}",
                    tenant_id=tenant_id,
                    current_value=float(row.on_hand_qty),
                    threshold_value=float(row.ss_quantity * config.threshold_value),
                    deviation=float(row.ss_quantity * config.threshold_value - row.on_hand_qty),
                    context={
                        "product_id": row.product_id,
                        "site_id": str(row.site_id),
                        "safety_stock": float(row.ss_quantity),
                        "ratio": round(ratio, 3),
                    },
                ))
        except Exception as e:
            logger.warning(f"Inventory below safety check failed for tenant {tenant_id}: {e}")

        return conditions

    async def _check_capacity_overload(
        self,
        tenant_id: int,
        config: ConditionConfig,
    ) -> List[ConditionState]:
        """Check for capacity overload — utilization > threshold."""
        from app.models.sc_entities import ProductionProcess, SupplyPlan
        from app.models.supply_chain_config import SupplyChainConfig
        from datetime import date

        conditions = []
        try:
            config_ids_q = select(SupplyChainConfig.id).where(
                SupplyChainConfig.tenant_id == tenant_id
            )

            # Sum planned MO hours vs capacity per site/process
            stmt = (
                select(
                    ProductionProcess.site_id,
                    ProductionProcess.id.label("process_id"),
                    ProductionProcess.manufacturing_capacity_hours,
                    func.sum(
                        SupplyPlan.planned_order_quantity * ProductionProcess.operation_time
                    ).label("required_hours"),
                )
                .join(SupplyPlan, and_(
                    SupplyPlan.site_id == ProductionProcess.site_id,
                    SupplyPlan.plan_type == "mo_request",
                    SupplyPlan.config_id.in_(config_ids_q),
                ))
                .where(
                    ProductionProcess.config_id.in_(config_ids_q),
                    ProductionProcess.manufacturing_capacity_hours.isnot(None),
                    ProductionProcess.manufacturing_capacity_hours > 0,
                )
                .group_by(
                    ProductionProcess.site_id,
                    ProductionProcess.id,
                    ProductionProcess.manufacturing_capacity_hours,
                )
            )
            result = await self.db.execute(stmt)
            for row in result.all():
                utilization = row.required_hours / row.manufacturing_capacity_hours
                if utilization > config.threshold_value:
                    conditions.append(ConditionState(
                        condition_type=ConditionType.CAPACITY_OVERLOAD,
                        entity_type="site_process",
                        entity_id=f"{row.site_id}_{row.process_id}",
                        tenant_id=tenant_id,
                        current_value=round(utilization, 3),
                        threshold_value=config.threshold_value,
                        deviation=round(utilization - config.threshold_value, 3),
                        context={
                            "site_id": str(row.site_id),
                            "process_id": str(row.process_id),
                            "required_hours": round(float(row.required_hours), 1),
                            "capacity_hours": float(row.manufacturing_capacity_hours),
                        },
                    ))
        except Exception as e:
            logger.warning(f"Capacity overload check failed for tenant {tenant_id}: {e}")

        return conditions

    async def _check_orders_past_due(
        self,
        tenant_id: int,
        config: ConditionConfig,
    ) -> List[ConditionState]:
        """Check for orders past their delivery date."""
        from app.models.sc_entities import OutboundOrderLine
        from app.models.supply_chain_config import SupplyChainConfig
        from datetime import date as date_type

        conditions = []
        try:
            config_ids_q = select(SupplyChainConfig.id).where(
                SupplyChainConfig.tenant_id == tenant_id
            )

            today = date_type.today()
            stmt = (
                select(OutboundOrderLine)
                .where(
                    OutboundOrderLine.config_id.in_(config_ids_q),
                    OutboundOrderLine.requested_delivery_date < today,
                    OutboundOrderLine.status.notin_(["FULFILLED", "CANCELLED", "SHIPPED"]),
                    OutboundOrderLine.backlog_quantity > 0,
                )
                .limit(100)  # Cap to avoid overwhelming results
            )
            result = await self.db.execute(stmt)
            for row in result.scalars().all():
                days_past = (today - row.requested_delivery_date).days
                if days_past >= config.threshold_value:
                    conditions.append(ConditionState(
                        condition_type=ConditionType.ORDER_PAST_DUE,
                        entity_type="order",
                        entity_id=f"{row.order_id}_{row.line_number}",
                        tenant_id=tenant_id,
                        current_value=float(days_past),
                        threshold_value=config.threshold_value,
                        deviation=float(days_past - config.threshold_value),
                        context={
                            "order_id": row.order_id,
                            "line_number": row.line_number,
                            "product_id": row.product_id,
                            "site_id": str(row.site_id),
                            "requested_date": str(row.requested_delivery_date),
                            "backlog_qty": float(row.backlog_quantity),
                        },
                    ))
        except Exception as e:
            logger.warning(f"Orders past due check failed for tenant {tenant_id}: {e}")

        return conditions

    async def _check_forecast_deviation(
        self,
        tenant_id: int,
        config: ConditionConfig,
    ) -> List[ConditionState]:
        """Check for significant forecast vs actual demand deviations."""
        from app.models.sc_entities import Forecast, OutboundOrderLine
        from app.models.supply_chain_config import SupplyChainConfig
        from datetime import date as date_type

        conditions = []
        try:
            config_ids_q = select(SupplyChainConfig.id).where(
                SupplyChainConfig.tenant_id == tenant_id
            )

            today = date_type.today()
            lookback = today - timedelta(days=30)

            # Subquery: actual demand by product in the lookback window
            actual_demand = (
                select(
                    OutboundOrderLine.product_id,
                    func.sum(OutboundOrderLine.ordered_quantity).label("actual_qty"),
                )
                .where(
                    OutboundOrderLine.config_id.in_(config_ids_q),
                    OutboundOrderLine.order_date >= lookback,
                    OutboundOrderLine.order_date <= today,
                )
                .group_by(OutboundOrderLine.product_id)
            ).subquery()

            # Subquery: forecast demand by product in the same window
            forecast_demand = (
                select(
                    Forecast.product_id,
                    func.sum(Forecast.forecast_quantity).label("forecast_qty"),
                )
                .where(
                    Forecast.config_id.in_(config_ids_q),
                    Forecast.forecast_date >= lookback,
                    Forecast.forecast_date <= today,
                )
                .group_by(Forecast.product_id)
            ).subquery()

            # Join actual vs forecast
            stmt = (
                select(
                    forecast_demand.c.product_id,
                    forecast_demand.c.forecast_qty,
                    actual_demand.c.actual_qty,
                )
                .join(
                    actual_demand,
                    forecast_demand.c.product_id == actual_demand.c.product_id,
                )
                .where(forecast_demand.c.forecast_qty > 0)
            )

            result = await self.db.execute(stmt)
            for row in result.all():
                deviation = abs(row.actual_qty - row.forecast_qty) / row.forecast_qty
                if deviation > config.threshold_value:
                    conditions.append(ConditionState(
                        condition_type=ConditionType.FORECAST_DEVIATION,
                        entity_type="product",
                        entity_id=str(row.product_id),
                        tenant_id=tenant_id,
                        current_value=round(deviation, 4),
                        threshold_value=config.threshold_value,
                        deviation=round(deviation - config.threshold_value, 4),
                        context={
                            "product_id": str(row.product_id),
                            "forecast_qty": float(row.forecast_qty),
                            "actual_qty": float(row.actual_qty),
                            "deviation_pct": round(deviation * 100, 1),
                        },
                    ))
        except Exception as e:
            logger.warning(f"Forecast deviation check failed for tenant {tenant_id}: {e}")

        return conditions

    # =========================================================================
    # Network Pattern Detection
    # =========================================================================

    async def _detect_network_patterns(
        self,
        tenant_id: int,
        conditions: List[ConditionState],
    ) -> List[ConditionState]:
        """Detect patterns that span multiple sites/entities."""
        network_conditions = []

        # Group conditions by type and product
        product_conditions: Dict[str, Dict[str, List[ConditionState]]] = {}

        for condition in conditions:
            product_id = condition.context.get("product_id", "unknown")
            ctype = condition.condition_type.value

            if product_id not in product_conditions:
                product_conditions[product_id] = {}
            if ctype not in product_conditions[product_id]:
                product_conditions[product_id][ctype] = []

            product_conditions[product_id][ctype].append(condition)

        # Check for multi-site shortfall
        for product_id, type_conditions in product_conditions.items():
            atp_shortfalls = type_conditions.get(ConditionType.ATP_SHORTFALL.value, [])
            inv_shortfalls = type_conditions.get(ConditionType.INVENTORY_BELOW_SAFETY.value, [])

            # Multiple sites with shortfall for same product
            unique_sites = set()
            for c in atp_shortfalls + inv_shortfalls:
                site_id = c.context.get("site_id")
                if site_id:
                    unique_sites.add(site_id)

            config = CONDITION_CONFIGS[ConditionType.MULTI_SITE_SHORTFALL]
            if len(unique_sites) >= config.threshold_value:
                network_conditions.append(ConditionState(
                    condition_type=ConditionType.MULTI_SITE_SHORTFALL,
                    entity_type="product",
                    entity_id=product_id,
                    tenant_id=tenant_id,
                    current_value=len(unique_sites),
                    threshold_value=config.threshold_value,
                    context={
                        "product_id": product_id,
                        "affected_sites": list(unique_sites),
                        "related_conditions": [c.entity_id for c in atp_shortfalls + inv_shortfalls],
                    },
                    severity=ConditionSeverity.WARNING,
                ))

        return network_conditions

    # =========================================================================
    # Severity Management
    # =========================================================================

    def _update_severity(
        self,
        condition: ConditionState,
        config: ConditionConfig,
    ) -> None:
        """Update condition severity based on duration."""
        duration_hours = (datetime.utcnow() - condition.first_detected).total_seconds() / 3600
        condition.duration_hours = duration_hours

        # Find appropriate severity for duration
        for hours_threshold, severity in sorted(config.severity_escalation.items(), reverse=True):
            if duration_hours >= hours_threshold:
                condition.severity = severity
                break

    # =========================================================================
    # Supply Request Management
    # =========================================================================

    async def create_supply_request(
        self,
        condition: ConditionState,
        target_entities: List[str],
        quantity_needed: float,
        needed_by: datetime,
    ) -> List[SupplyRequest]:
        """
        Create supply requests to other sites/agents.

        This enables the "ATP agents asking for more supply" pattern.

        Args:
            condition: The condition triggering the request
            target_entities: Sites/agents to request from
            quantity_needed: How much is needed
            needed_by: Deadline for supply

        Returns:
            Created supply requests
        """
        requests = []
        config = CONDITION_CONFIGS.get(condition.condition_type)

        if not config or not config.can_request_supply:
            logger.info(
                f"Condition {condition.condition_type.value} cannot request supply"
            )
            return requests

        for target in target_entities:
            request = SupplyRequest(
                requesting_entity=condition.entity_id,
                requested_entity=target,
                product_id=condition.context.get("product_id", ""),
                quantity_needed=quantity_needed,
                needed_by=needed_by,
                priority=1 if condition.severity == ConditionSeverity.EMERGENCY else 2,
                context={
                    "condition_type": condition.condition_type.value,
                    "condition_severity": condition.severity.value,
                    "current_value": condition.current_value,
                },
            )
            requests.append(request)
            self._supply_requests.append(request)

        logger.info(
            f"Created {len(requests)} supply requests for "
            f"{condition.condition_type.value}"
        )

        return requests

    async def get_pending_supply_requests(
        self,
        entity_id: str,
    ) -> List[SupplyRequest]:
        """Get supply requests directed to a specific entity."""
        return [
            r for r in self._supply_requests
            if r.requested_entity == entity_id and r.status == "pending"
        ]

    async def respond_to_supply_request(
        self,
        request: SupplyRequest,
        accepted: bool,
        quantity_available: Optional[float] = None,
    ) -> SupplyRequest:
        """Respond to a supply request."""
        if accepted:
            request.status = "accepted"
            request.context["quantity_available"] = quantity_available or request.quantity_needed
        else:
            request.status = "rejected"

        return request

    # =========================================================================
    # Plan Deviation Detection
    # =========================================================================

    async def check_plan_deviation(
        self,
        tenant_id: int,
        current_state: Dict[str, Any],
        previous_plan: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Alternative approach: Check deviation from previous plan.

        Instead of checking absolute thresholds, compare current state
        to what the plan predicted and trigger based on deviation.

        Args:
            tenant_id: Customer to check
            current_state: Current system state
            previous_plan: The previous plan's predictions

        Returns:
            Deviation analysis with recommended actions
        """
        deviations = {
            "inventory_deviations": [],
            "demand_deviations": [],
            "supply_deviations": [],
            "total_deviation_score": 0.0,
            "recommended_actions": [],
        }

        # Compare inventory levels
        current_inventory = current_state.get("inventory", {})
        planned_inventory = previous_plan.get("projected_inventory", {})

        for key, current_value in current_inventory.items():
            planned_value = planned_inventory.get(key, current_value)
            if planned_value > 0:
                deviation = abs(current_value - planned_value) / planned_value
                if deviation > 0.1:  # 10% deviation
                    deviations["inventory_deviations"].append({
                        "entity": key,
                        "current": current_value,
                        "planned": planned_value,
                        "deviation_pct": deviation * 100,
                    })

        # Compare demand (actual vs forecast)
        current_demand = current_state.get("demand", {})
        forecasted_demand = previous_plan.get("forecast", {})

        for key, current_value in current_demand.items():
            forecast_value = forecasted_demand.get(key, current_value)
            if forecast_value > 0:
                deviation = abs(current_value - forecast_value) / forecast_value
                if deviation > 0.15:  # 15% deviation
                    deviations["demand_deviations"].append({
                        "entity": key,
                        "actual": current_value,
                        "forecast": forecast_value,
                        "deviation_pct": deviation * 100,
                    })

        # Calculate overall deviation score
        total_deviations = (
            len(deviations["inventory_deviations"]) +
            len(deviations["demand_deviations"]) +
            len(deviations["supply_deviations"])
        )

        max_deviation = max(
            [d["deviation_pct"] for d in deviations["inventory_deviations"]] +
            [d["deviation_pct"] for d in deviations["demand_deviations"]] +
            [0]
        )

        deviations["total_deviation_score"] = min(100, max_deviation)

        # Recommend actions based on deviation
        if deviations["total_deviation_score"] > 50:
            deviations["recommended_actions"].append({
                "action": "trigger_soop_review",
                "reason": "High overall deviation from plan",
            })
        elif deviations["total_deviation_score"] > 25:
            deviations["recommended_actions"].append({
                "action": "trigger_execution_replan",
                "reason": "Moderate deviation requiring adjustment",
            })

        if len(deviations["demand_deviations"]) > 5:
            deviations["recommended_actions"].append({
                "action": "forecast_recalibration",
                "reason": "Multiple products with forecast deviation",
            })

        return deviations

    # =========================================================================
    # Trigger Management
    # =========================================================================

    async def get_triggered_actions(
        self,
        conditions: List[ConditionState],
    ) -> List[Dict[str, Any]]:
        """
        Get the actions that should be triggered based on conditions.

        Returns structured action recommendations for the orchestrator.
        """
        actions = []

        for condition in conditions:
            config = CONDITION_CONFIGS.get(condition.condition_type)
            if not config:
                continue

            # Basic action for all conditions
            action = {
                "condition_id": f"{condition.condition_type.value}_{condition.entity_id}",
                "condition_type": condition.condition_type.value,
                "severity": condition.severity.value,
                "entity_type": condition.entity_type,
                "entity_id": condition.entity_id,
                "agent_types": config.agent_types,
                "requires_scenario_eval": config.requires_scenario_eval,
                "triggers_soop": config.triggers_soop,
                "context": condition.context,
            }

            # Add severity-based recommendations
            if condition.severity == ConditionSeverity.EMERGENCY:
                action["priority"] = 1
                action["auto_execute"] = False  # Require human review
            elif condition.severity == ConditionSeverity.CRITICAL:
                action["priority"] = 2
                action["auto_execute"] = True
            else:
                action["priority"] = 3
                action["auto_execute"] = True

            actions.append(action)

        # Sort by priority
        actions.sort(key=lambda x: x["priority"])

        return actions

    async def should_trigger_soop(
        self,
        conditions: List[ConditionState],
    ) -> Tuple[bool, str]:
        """
        Determine if S&OP cycle should be triggered.

        S&OP is triggered when:
        1. Multiple sites report supply shortfall
        2. Capacity constraints affect multiple products
        3. Forecast deviations exceed threshold
        4. Network-wide pattern detected

        Returns:
            (should_trigger, reason)
        """
        # Check for S&OP-triggering conditions
        soop_conditions = [
            c for c in conditions
            if CONDITION_CONFIGS.get(c.condition_type, ConditionConfig(
                condition_type=c.condition_type,
                threshold_value=0, persistence_hours=0, check_interval_minutes=0,
                severity_escalation={}, agent_types=[], requires_scenario_eval=False,
                can_request_supply=False, triggers_soop=False
            )).triggers_soop
        ]

        if soop_conditions:
            reasons = [c.condition_type.value for c in soop_conditions]
            return True, f"Conditions triggering S&OP: {', '.join(reasons)}"

        # Check for multi-site patterns
        multi_site = [
            c for c in conditions
            if c.condition_type == ConditionType.MULTI_SITE_SHORTFALL
        ]
        if multi_site:
            return True, "Multi-site supply shortfall detected"

        # Check for critical conditions at network level
        critical_network = [
            c for c in conditions
            if c.severity in [ConditionSeverity.CRITICAL, ConditionSeverity.EMERGENCY]
            and c.entity_type in ["network", "product"]
        ]
        if len(critical_network) >= 3:
            return True, f"{len(critical_network)} critical network-level conditions"

        return False, ""
