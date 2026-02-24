"""
Powell Framework Integration Package

Connects SiteAgent with existing platform services:
- Supply plan service (MRP output -> supply plans)
- ATP service (AATP engine with priority consumption)
- Scenario service (SiteAgent as simulation agent strategy)
- Decision service (TRM decisions with audit trail)
"""

from .supply_plan_integration import SiteAgentSupplyPlanAdapter
from .atp_integration import SiteAgentATPAdapter
from .scenario_integration import (
    SiteAgentStrategy,
    SiteAgentPolicy,
    register_site_agent_strategy,
    create_site_agent_for_scenario,
)
from .decision_integration import (
    TRMDecisionRecord,
    SiteAgentDecisionTracker,
)

__all__ = [
    # Supply Plan Integration
    "SiteAgentSupplyPlanAdapter",
    # ATP Integration
    "SiteAgentATPAdapter",
    # Scenario Integration
    "SiteAgentStrategy",
    "SiteAgentPolicy",
    "register_site_agent_strategy",
    "create_site_agent_for_scenario",
    # Decision Tracking
    "TRMDecisionRecord",
    "SiteAgentDecisionTracker",
]
