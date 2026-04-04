"""
AgentContract — Abstract Base Class for All 12 TRM Agents.

Defines the formal interface that every TRM must implement:
  - Input shape (state dataclass)
  - Actions (recommendation dataclass)
  - Permissions (which signals it reads/emits, which decisions it makes)
  - Output schema (persistence format)

This enables:
  1. Type-safe agent orchestration in SiteAgent
  2. Automated agent discovery and registration
  3. Formal verification of agent capabilities per site type
  4. Decision chain tracing (correlation ID propagation)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Optional, Type

from .hive_signal import HiveSignalBus, HiveSignalType


@dataclass
class AgentCapabilities:
    """Declares what a TRM agent can do."""
    trm_type: str                                    # Canonical name (e.g., "forecast_baseline")
    display_name: str                                # Human-readable (e.g., "Forecast Baseline Agent")
    decision_phase: str                              # SENSE, ASSESS, ACQUIRE, PROTECT, BUILD, REFLECT
    decision_level: str                              # tactical, execution, strategic

    # Signals this agent reads before deciding
    reads_signals: FrozenSet[HiveSignalType]
    # Signals this agent emits after deciding
    emits_signals: FrozenSet[HiveSignalType]

    # Decision table name
    decision_table: str                              # e.g., "powell_forecast_baseline_decisions"

    # Site applicability
    site_types: FrozenSet[str]                       # {"manufacturer", "inventory", "retailer"}

    # LLM escalation capability
    has_skill_escalation: bool = False
    skill_name: Optional[str] = None                 # e.g., "forecast_adjustment"


class AgentContract(ABC):
    """Abstract base class for all 12 TRM agents.

    Every TRM must implement this interface. SiteAgent uses it for
    type-safe orchestration and capability discovery.
    """

    # Class-level capability declaration (override in each TRM)
    CAPABILITIES: AgentCapabilities

    def __init__(self, site_key: str, config=None, model=None, db_session=None):
        self.site_key = site_key
        self.config = config
        self.model = model
        self.db = db_session
        self.signal_bus: Optional[HiveSignalBus] = None
        self.ctx_explainer = None
        self._cycle_id: Optional[str] = None
        self._cycle_phase: Optional[str] = None
        self._correlation_id: Optional[str] = None

    @abstractmethod
    def evaluate(self, state: Any) -> Any:
        """Main decision method. Takes state, returns recommendation.

        Must:
        1. Read hive signals before deciding
        2. Apply heuristic or model-based logic
        3. Emit hive signals after deciding
        4. Persist decision to DB
        5. Propagate correlation_id for tracing
        """
        ...

    def set_cycle_context(
        self,
        cycle_id: str,
        cycle_phase: str,
        correlation_id: Optional[str] = None,
    ) -> None:
        """Set the decision cycle context for tracing."""
        self._cycle_id = cycle_id
        self._cycle_phase = cycle_phase
        self._correlation_id = correlation_id

    @classmethod
    def get_capabilities(cls) -> AgentCapabilities:
        """Return this agent's capability declaration."""
        return cls.CAPABILITIES


# ---------------------------------------------------------------------------
# Capability declarations for all 12 TRMs
# ---------------------------------------------------------------------------

TRM_CAPABILITIES: Dict[str, AgentCapabilities] = {
    "forecast_baseline": AgentCapabilities(
        trm_type="forecast_baseline",
        display_name="Forecast Baseline Agent",
        decision_phase="SENSE",
        decision_level="tactical",
        reads_signals=frozenset({HiveSignalType.DEMAND_SURGE, HiveSignalType.DEMAND_DROP, HiveSignalType.ALLOCATION_REFRESH}),
        emits_signals=frozenset({HiveSignalType.DEMAND_SURGE, HiveSignalType.DEMAND_DROP, HiveSignalType.FORECAST_ADJUSTED}),
        decision_table="powell_forecast_baseline_decisions",
        site_types=frozenset({"manufacturer", "inventory", "retailer"}),
        has_skill_escalation=False,
    ),
    "atp_executor": AgentCapabilities(
        trm_type="atp_executor",
        display_name="Order Promise Agent",
        decision_phase="SENSE",
        decision_level="execution",
        reads_signals=frozenset({HiveSignalType.DEMAND_SURGE, HiveSignalType.FORECAST_ADJUSTED, HiveSignalType.BUFFER_DECREASED}),
        emits_signals=frozenset({HiveSignalType.ATP_SHORTAGE, HiveSignalType.ATP_EXCESS}),
        decision_table="powell_atp_allocation_decisions",
        site_types=frozenset({"manufacturer", "inventory"}),
        has_skill_escalation=True,
        skill_name="atp_executor",
    ),
    "order_tracking": AgentCapabilities(
        trm_type="order_tracking",
        display_name="Order Tracking Agent",
        decision_phase="SENSE",
        decision_level="execution",
        reads_signals=frozenset({HiveSignalType.TO_DELAYED, HiveSignalType.PO_DEFERRED}),
        emits_signals=frozenset({HiveSignalType.ORDER_EXCEPTION}),
        decision_table="powell_order_tracking_decisions",
        site_types=frozenset({"manufacturer", "inventory"}),
        has_skill_escalation=True,
        skill_name="order_tracking",
    ),
    "inventory_buffer": AgentCapabilities(
        trm_type="inventory_buffer",
        display_name="Inventory Agent",
        decision_phase="ASSESS",
        decision_level="tactical",
        reads_signals=frozenset({HiveSignalType.DEMAND_SURGE, HiveSignalType.DEMAND_DROP, HiveSignalType.FORECAST_ADJUSTED, HiveSignalType.ATP_SHORTAGE}),
        emits_signals=frozenset({HiveSignalType.BUFFER_INCREASED, HiveSignalType.BUFFER_DECREASED}),
        decision_table="powell_buffer_decisions",
        site_types=frozenset({"manufacturer", "inventory"}),
        has_skill_escalation=True,
        skill_name="inventory_buffer",
    ),
    "forecast_adjustment": AgentCapabilities(
        trm_type="forecast_adjustment",
        display_name="Demand Planner Agent",
        decision_phase="ASSESS",
        decision_level="tactical",
        reads_signals=frozenset({HiveSignalType.DEMAND_SURGE, HiveSignalType.DEMAND_DROP, HiveSignalType.ORDER_EXCEPTION}),
        emits_signals=frozenset({HiveSignalType.FORECAST_ADJUSTED}),
        decision_table="powell_forecast_adjustment_decisions",
        site_types=frozenset({"manufacturer", "inventory", "retailer"}),
        has_skill_escalation=True,
        skill_name="forecast_adjustment",
    ),
    "quality_disposition": AgentCapabilities(
        trm_type="quality_disposition",
        display_name="Quality Agent",
        decision_phase="ASSESS",
        decision_level="execution",
        reads_signals=frozenset({HiveSignalType.MO_RELEASED}),
        emits_signals=frozenset({HiveSignalType.QUALITY_REJECT, HiveSignalType.QUALITY_HOLD}),
        decision_table="powell_quality_decisions",
        site_types=frozenset({"manufacturer"}),
        has_skill_escalation=True,
        skill_name="quality_disposition",
    ),
    "po_creation": AgentCapabilities(
        trm_type="po_creation",
        display_name="Procurement Agent",
        decision_phase="ACQUIRE",
        decision_level="execution",
        reads_signals=frozenset({HiveSignalType.BUFFER_DECREASED, HiveSignalType.ATP_SHORTAGE, HiveSignalType.FORECAST_ADJUSTED}),
        emits_signals=frozenset({HiveSignalType.PO_EXPEDITE, HiveSignalType.PO_DEFERRED}),
        decision_table="powell_po_decisions",
        site_types=frozenset({"manufacturer", "inventory"}),
        has_skill_escalation=True,
        skill_name="po_creation",
    ),
    "subcontracting": AgentCapabilities(
        trm_type="subcontracting",
        display_name="Subcontracting Agent",
        decision_phase="ACQUIRE",
        decision_level="execution",
        reads_signals=frozenset({HiveSignalType.QUALITY_REJECT, HiveSignalType.MO_DELAYED}),
        emits_signals=frozenset({HiveSignalType.SUBCONTRACT_ROUTED}),
        decision_table="powell_subcontracting_decisions",
        site_types=frozenset({"manufacturer"}),
        has_skill_escalation=True,
        skill_name="subcontracting",
    ),
    "maintenance_scheduling": AgentCapabilities(
        trm_type="maintenance_scheduling",
        display_name="Maintenance Agent",
        decision_phase="PROTECT",
        decision_level="execution",
        reads_signals=frozenset({HiveSignalType.MO_RELEASED, HiveSignalType.QUALITY_REJECT}),
        emits_signals=frozenset({HiveSignalType.MAINTENANCE_DEFERRED, HiveSignalType.MAINTENANCE_URGENT}),
        decision_table="powell_maintenance_decisions",
        site_types=frozenset({"manufacturer"}),
        has_skill_escalation=True,
        skill_name="maintenance_scheduling",
    ),
    "mo_execution": AgentCapabilities(
        trm_type="mo_execution",
        display_name="Production Agent",
        decision_phase="BUILD",
        decision_level="execution",
        reads_signals=frozenset({HiveSignalType.PO_EXPEDITE, HiveSignalType.QUALITY_HOLD, HiveSignalType.MAINTENANCE_URGENT}),
        emits_signals=frozenset({HiveSignalType.MO_RELEASED, HiveSignalType.MO_DELAYED}),
        decision_table="powell_mo_decisions",
        site_types=frozenset({"manufacturer"}),
        has_skill_escalation=True,
        skill_name="mo_execution",
    ),
    "to_execution": AgentCapabilities(
        trm_type="to_execution",
        display_name="Transfer Agent",
        decision_phase="BUILD",
        decision_level="execution",
        reads_signals=frozenset({HiveSignalType.REBALANCE_OUTBOUND, HiveSignalType.BUFFER_DECREASED}),
        emits_signals=frozenset({HiveSignalType.TO_RELEASED, HiveSignalType.TO_DELAYED}),
        decision_table="powell_to_decisions",
        site_types=frozenset({"manufacturer", "inventory"}),
        has_skill_escalation=True,
        skill_name="to_execution",
    ),
    "rebalancing": AgentCapabilities(
        trm_type="rebalancing",
        display_name="Rebalancing Agent",
        decision_phase="REFLECT",
        decision_level="tactical",
        reads_signals=frozenset({HiveSignalType.ATP_SHORTAGE, HiveSignalType.BUFFER_DECREASED, HiveSignalType.NETWORK_SHORTAGE}),
        emits_signals=frozenset({HiveSignalType.REBALANCE_INBOUND, HiveSignalType.REBALANCE_OUTBOUND}),
        decision_table="powell_inventory_rebalancing_decisions",
        site_types=frozenset({"manufacturer", "inventory"}),
        has_skill_escalation=True,
        skill_name="inventory_rebalancing",
    ),
}
