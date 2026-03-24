"""
User Directive — Natural Language Strategic/Tactical/Operational Context Capture

Captures directives from authenticated users at the appropriate Powell layer
based on their role. VP directives route to S&OP GraphSAGE (Layer 4),
regional planners to Execution tGNN (Layer 2), site managers to Site tGNN
(Layer 1.5), and line operators directly to TRMs (Layer 1).

Tracked for effectiveness using the same Bayesian posterior mechanism as
overrides, measured against the appropriate scope (network-wide for strategic,
site-level for operational).
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Text, JSON,
    ForeignKey, Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base


class UserDirective(Base):
    """A natural language directive parsed and routed through the Powell cascade."""
    __tablename__ = "user_directives"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    # Raw input
    raw_text = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    # LLM parsing output
    directive_type = Column(String(50), nullable=False)
    # STRATEGIC_REVENUE_TARGET, MARKET_INTELLIGENCE, CUSTOMER_FEEDBACK,
    # RISK_MITIGATION, CAPACITY_DIRECTION, PROMOTION_PLANNING,
    # COST_REDUCTION, REGULATORY, OPERATIONAL_ADJUSTMENT
    reason_code = Column(String(100), nullable=False)
    parsed_intent = Column(String(30), nullable=False)  # directive | observation | question
    parsed_scope = Column(JSON, nullable=False)
    # {"region": "SW", "product_family": "Frozen", "time_horizon_weeks": 13,
    #  "site_keys": ["RDC_SW"], "product_ids": ["PROD-001"]}
    parsed_direction = Column(String(20), nullable=True)  # increase | decrease | maintain | reallocate
    parsed_metric = Column(String(50), nullable=True)  # revenue | cost | service_level | inventory | capacity
    parsed_magnitude_pct = Column(Float, nullable=True)
    parser_confidence = Column(Float, nullable=False)

    # Routing — determined by user's PowellRole
    target_layer = Column(String(20), nullable=False)
    # strategic (Layer 4 → GraphSAGE), tactical (Layer 2 → Exec tGNN),
    # operational (Layer 1.5 → Site tGNN), execution (Layer 1 → TRM)
    target_trm_types = Column(JSON, nullable=True)  # ["forecast_adjustment", "inventory_buffer"]
    target_site_keys = Column(JSON, nullable=True)  # ["1710", "RDC_SW"] or null for network-wide

    # Actions taken
    routed_actions = Column(JSON, nullable=True)
    # [{"trm": "forecast_adjustment", "action": "increase 5%", "decision_id": 123}, ...]

    # Status
    status = Column(String(20), nullable=False, default="PARSED")
    # PARSED → APPLIED → MEASURED | REJECTED | EXPIRED
    applied_at = Column(DateTime, nullable=True)
    measured_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)  # Based on time_horizon

    # Effectiveness (filled by outcome collector)
    effectiveness_delta = Column(Float, nullable=True)  # BSC delta attributable to this directive
    effectiveness_scope = Column(String(20), nullable=True)  # network | region | site

    # Relationships
    user = relationship("User", lazy="joined")

    __table_args__ = (
        Index("idx_directive_user", "user_id"),
        Index("idx_directive_config", "config_id"),
        Index("idx_directive_tenant_status", "tenant_id", "status"),
        Index("idx_directive_created", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "user_name": self.user.name if self.user else None,
            "config_id": self.config_id,
            "raw_text": self.raw_text,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "directive_type": self.directive_type,
            "reason_code": self.reason_code,
            "parsed_intent": self.parsed_intent,
            "parsed_scope": self.parsed_scope,
            "parsed_direction": self.parsed_direction,
            "parsed_metric": self.parsed_metric,
            "parsed_magnitude_pct": self.parsed_magnitude_pct,
            "parser_confidence": self.parser_confidence,
            "target_layer": self.target_layer,
            "target_trm_types": self.target_trm_types,
            "target_site_keys": self.target_site_keys,
            "routed_actions": self.routed_actions,
            "status": self.status,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "measured_at": self.measured_at.isoformat() if self.measured_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "effectiveness_delta": self.effectiveness_delta,
            "effectiveness_scope": self.effectiveness_scope,
        }


class ConfigProvisioningStatus(Base):
    """Tracks provisioning progress for a supply chain config."""
    __tablename__ = "config_provisioning_status"

    id = Column(Integer, primary_key=True, autoincrement=True)
    config_id = Column(Integer, ForeignKey("supply_chain_configs.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Step 1: Historical demand + belief states
    warm_start_status = Column(String(20), default="pending")
    warm_start_at = Column(DateTime, nullable=True)
    warm_start_error = Column(Text, nullable=True)

    # Step 2: S&OP GraphSAGE training
    sop_graphsage_status = Column(String(20), default="pending")
    sop_graphsage_at = Column(DateTime, nullable=True)
    sop_graphsage_error = Column(Text, nullable=True)

    # Step 3: CFA policy optimization
    cfa_optimization_status = Column(String(20), default="pending")
    cfa_optimization_at = Column(DateTime, nullable=True)
    cfa_optimization_error = Column(Text, nullable=True)

    # Step 4: LightGBM baseline demand forecasting
    lgbm_forecast_status = Column(String(20), default="pending")
    lgbm_forecast_at = Column(DateTime, nullable=True)
    lgbm_forecast_error = Column(Text, nullable=True)

    # Step 5: Demand Planning tGNN
    demand_tgnn_status = Column(String(20), default="pending")
    demand_tgnn_at = Column(DateTime, nullable=True)
    demand_tgnn_error = Column(Text, nullable=True)

    # Step 6: Supply Planning tGNN
    supply_tgnn_status = Column(String(20), default="pending")
    supply_tgnn_at = Column(DateTime, nullable=True)
    supply_tgnn_error = Column(Text, nullable=True)

    # Step 7: Inventory Optimization tGNN
    inventory_tgnn_status = Column(String(20), default="pending")
    inventory_tgnn_at = Column(DateTime, nullable=True)
    inventory_tgnn_error = Column(Text, nullable=True)

    # Step 8: TRM Phase 1 (Behavioral Cloning)
    trm_training_status = Column(String(20), default="pending")
    trm_training_at = Column(DateTime, nullable=True)
    trm_training_error = Column(Text, nullable=True)

    # Step 8b: TRM Phase 2 (Simulation-based RL / PPO fine-tuning)
    rl_training_status = Column(String(20), default="pending")
    rl_training_at = Column(DateTime, nullable=True)
    rl_training_error = Column(Text, nullable=True)

    # Step 9: Supply plan generation
    supply_plan_status = Column(String(20), default="pending")
    supply_plan_at = Column(DateTime, nullable=True)
    supply_plan_error = Column(Text, nullable=True)

    # Step 9b: RCCP validation (rough-cut capacity check against supply plan)
    rccp_validation_status = Column(String(20), default="pending")
    rccp_validation_at = Column(DateTime, nullable=True)
    rccp_validation_error = Column(Text, nullable=True)

    # Step 10: Decision stream seeding
    decision_seed_status = Column(String(20), default="pending")
    decision_seed_at = Column(DateTime, nullable=True)
    decision_seed_error = Column(Text, nullable=True)

    # Step 11: Site tGNN training
    site_tgnn_status = Column(String(20), default="pending")
    site_tgnn_at = Column(DateTime, nullable=True)
    site_tgnn_error = Column(Text, nullable=True)

    # Step 12: Conformal calibration
    conformal_status = Column(String(20), default="pending")
    conformal_at = Column(DateTime, nullable=True)
    conformal_error = Column(Text, nullable=True)

    # Step 13: Scenario bootstrap (warm-start template priors)
    scenario_bootstrap_status = Column(String(20), default="pending")
    scenario_bootstrap_at = Column(DateTime, nullable=True)
    scenario_bootstrap_error = Column(Text, nullable=True)

    # Step 14: Executive briefing
    briefing_status = Column(String(20), default="pending")
    briefing_at = Column(DateTime, nullable=True)
    briefing_error = Column(Text, nullable=True)

    # Overall
    overall_status = Column(String(20), default="not_started")
    # not_started | in_progress | completed | partial | failed
    last_updated = Column(DateTime, server_default=func.now(), onupdate=func.now())

    # Provisioning scope (Mar 2026): controls which steps run on reprovisioning.
    # FULL: All 14 steps (required for structural changes — new sites, lanes, products).
    # PARAMETER_ONLY: Subset of steps that only affect policy/parameters, reusing
    #   existing TRM training, GNN models, and simulation data.
    #   Parameter-only steps: cfa_optimization, decision_seed, conformal, briefing.
    # NULL/empty = FULL (backward compatible).
    provisioning_scope = Column(String(20), nullable=True, default=None)

    STEPS = [
        "warm_start", "sop_graphsage", "cfa_optimization",
        "lgbm_forecast", "demand_tgnn", "supply_tgnn", "inventory_tgnn",
        "trm_training", "rl_training", "supply_plan", "rccp_validation",
        "decision_seed", "site_tgnn", "conformal", "scenario_bootstrap", "briefing",
    ]

    # Steps that run for PARAMETER_ONLY reprovisioning (policy/parameter changes).
    # These reuse existing TRM weights, GNN models, and simulation data.
    # Structural changes (new sites, lanes, products, BOMs) require FULL provisioning.
    PARAMETER_ONLY_STEPS = [
        "cfa_optimization",   # Re-optimize policy parameters θ over existing scenarios
        "decision_seed",      # Re-seed decisions under new policy regime
        "conformal",          # Re-calibrate CDT from new decision-outcome pairs
        "briefing",           # Regenerate executive briefing
    ]

    STEP_LABELS = {
        "warm_start": "Historical Demand Simulation",
        "sop_graphsage": "Strategic Network Planning Agent",
        "cfa_optimization": "Policy Parameter Optimization",
        "lgbm_forecast": "Demand Forecasting",
        "demand_tgnn": "Demand Planning Agent",
        "supply_tgnn": "Supply Planning Agent",
        "rccp_validation": "Rough-Cut Capacity Validation",
        "inventory_tgnn": "Inventory Optimization Agent",
        "trm_training": "Execution Role Agent Training",
        "rl_training": "Simulation RL Fine-Tuning",
        "supply_plan": "Supply Plan Generation",
        "decision_seed": "Decision Stream Seeding",
        "site_tgnn": "Operational Site Agent Training",
        "conformal": "Uncertainty Calibration",
        "scenario_bootstrap": "Scenario Skill Warm-Start",
        "briefing": "Executive Briefing",
    }

    STEP_DEPENDS = {
        "warm_start": [],
        "sop_graphsage": ["warm_start"],
        "cfa_optimization": ["sop_graphsage"],
        "lgbm_forecast": ["cfa_optimization"],
        "demand_tgnn": ["lgbm_forecast", "sop_graphsage"],
        "supply_tgnn": ["lgbm_forecast", "sop_graphsage"],
        "inventory_tgnn": ["supply_tgnn"],
        "trm_training": ["demand_tgnn", "supply_tgnn", "inventory_tgnn"],
        "rl_training": ["trm_training"],
        "supply_plan": ["cfa_optimization", "rl_training"],
        "rccp_validation": ["supply_plan"],
        "decision_seed": ["rl_training"],
        "site_tgnn": ["decision_seed"],
        "conformal": ["warm_start"],
        "scenario_bootstrap": ["conformal", "decision_seed"],
        "briefing": ["supply_plan", "decision_seed", "scenario_bootstrap"],
    }

    def to_dict(self):
        steps = []
        for step in self.STEPS:
            status = getattr(self, f"{step}_status", "pending")
            completed_at = getattr(self, f"{step}_at", None)
            error = getattr(self, f"{step}_error", None)
            deps = self.STEP_DEPENDS.get(step, [])
            deps_met = all(
                getattr(self, f"{d}_status", "pending") == "completed"
                for d in deps
            )
            steps.append({
                "key": step,
                "label": self.STEP_LABELS.get(step, step),
                "status": status,
                "completed_at": completed_at.isoformat() if completed_at else None,
                "error": error,
                "depends_on": deps,
                "dependencies_met": deps_met,
            })
        return {
            "config_id": self.config_id,
            "overall_status": self.overall_status,
            "provisioning_scope": self.provisioning_scope or "FULL",
            "parameter_only_steps": self.PARAMETER_ONLY_STEPS,
            "last_updated": self.last_updated.isoformat() if self.last_updated else None,
            "steps": steps,
        }
