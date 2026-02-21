"""
Maintenance Scheduling TRM

Narrow TRM for maintenance scheduling decisions.

TRM Scope (narrow):
- Given: Asset condition, production schedule, parts availability, risk factors
- Decide: Schedule now, defer, expedite, combine with other maintenance, or outsource?

Learns which deferrals lead to breakdowns and which are safe.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime, date, timedelta
import numpy as np
import logging

from .engines.maintenance_engine import (
    MaintenanceEngine, MaintenanceEngineConfig, MaintenanceSnapshot,
    MaintenanceSchedulingResult, MaintenanceDecisionType,
)

logger = logging.getLogger(__name__)


@dataclass
class MaintenanceSchedulingState:
    """State representation for maintenance scheduling TRM"""
    order_id: str
    asset_id: str
    site_id: str
    maintenance_type: str
    status: str

    # Scheduling
    scheduled_date: Optional[date] = None
    days_since_last_maintenance: int = 0
    maintenance_frequency_days: int = 90
    days_overdue: int = 0
    defer_count: int = 0

    # Resource
    estimated_downtime_hours: float = 0.0
    estimated_labor_hours: float = 0.0
    estimated_cost: float = 0.0
    spare_parts_available: bool = True

    # Asset context
    asset_criticality: str = "normal"
    asset_age_years: float = 0.0
    mean_time_between_failures_days: float = 365.0
    recent_failure_count: int = 0

    # Production context
    production_schedule_load_pct: float = 0.0
    production_impact_units: float = 0.0
    next_production_gap_days: int = 0

    # Priority
    priority: str = "NORMAL"

    # External option
    external_cost_estimate: float = 0.0
    external_lead_time_days: int = 0

    # Historical
    historical_breakdown_rate_after_defer: float = 0.0
    avg_actual_vs_estimated_cost_ratio: float = 1.0
    avg_actual_vs_estimated_downtime_ratio: float = 1.0


@dataclass
class MaintenanceRecommendation:
    """TRM recommendation for maintenance scheduling"""
    order_id: str
    decision_type: str
    confidence: float

    recommended_date: Optional[date] = None
    defer_to_date: Optional[date] = None
    defer_risk: float = 0.0
    expedite: bool = False
    outsource: bool = False
    combine_with: List[str] = field(default_factory=list)

    breakdown_probability: float = 0.0
    production_impact_hours: float = 0.0
    cost_estimate: float = 0.0

    reason: str = ""


@dataclass
class MaintenanceSchedulingTRMConfig:
    engine_config: MaintenanceEngineConfig = field(default_factory=MaintenanceEngineConfig)
    use_trm_model: bool = True
    confidence_threshold: float = 0.7


class MaintenanceSchedulingTRM:
    """Maintenance Scheduling TRM with learned deferral risk assessment."""

    def __init__(
        self,
        site_key: str,
        config: Optional[MaintenanceSchedulingTRMConfig] = None,
        model: Optional[Any] = None,
        db_session: Optional[Any] = None,
    ):
        self.site_key = site_key
        self.config = config or MaintenanceSchedulingTRMConfig()
        self.engine = MaintenanceEngine(site_key, self.config.engine_config)
        self.model = model
        self.db = db_session

    def evaluate_scheduling(self, state: MaintenanceSchedulingState) -> MaintenanceRecommendation:
        snapshot = MaintenanceSnapshot(
            order_id=state.order_id,
            asset_id=state.asset_id,
            site_id=state.site_id,
            maintenance_type=state.maintenance_type,
            status=state.status,
            scheduled_date=state.scheduled_date,
            days_since_last_maintenance=state.days_since_last_maintenance,
            maintenance_frequency_days=state.maintenance_frequency_days,
            days_overdue=state.days_overdue,
            defer_count=state.defer_count,
            estimated_downtime_hours=state.estimated_downtime_hours,
            estimated_labor_hours=state.estimated_labor_hours,
            estimated_cost=state.estimated_cost,
            spare_parts_available=state.spare_parts_available,
            asset_criticality=state.asset_criticality,
            asset_age_years=state.asset_age_years,
            mean_time_between_failures_days=state.mean_time_between_failures_days,
            recent_failure_count=state.recent_failure_count,
            production_schedule_load_pct=state.production_schedule_load_pct,
            production_impact_units=state.production_impact_units,
            next_production_gap_days=state.next_production_gap_days,
            priority=state.priority,
            external_cost_estimate=state.external_cost_estimate,
            external_lead_time_days=state.external_lead_time_days,
        )

        engine_result = self.engine.evaluate_scheduling(snapshot)

        if self.model is not None and self.config.use_trm_model:
            try:
                recommendation = self._trm_evaluate(state, engine_result)
            except Exception as e:
                logger.warning(f"TRM failed for maintenance {state.order_id}: {e}")
                recommendation = self._heuristic_evaluate(state, engine_result)
        else:
            recommendation = self._heuristic_evaluate(state, engine_result)

        self._persist_decision(state, recommendation)
        return recommendation

    def _trm_evaluate(self, state, engine_result):
        features = self._encode_state(state)
        import torch
        with torch.no_grad():
            output = self.model(torch.tensor([features], dtype=torch.float32))
        confidence = float(output.get('confidence', 0.5))
        if confidence < self.config.confidence_threshold:
            return self._heuristic_evaluate(state, engine_result)

        return MaintenanceRecommendation(
            order_id=state.order_id,
            decision_type=engine_result.decision_type.value,
            confidence=confidence,
            recommended_date=engine_result.recommended_date,
            defer_to_date=engine_result.defer_to_date,
            defer_risk=engine_result.defer_risk_score,
            expedite=engine_result.expedite_recommended,
            outsource=engine_result.outsource_recommended,
            breakdown_probability=engine_result.breakdown_probability,
            production_impact_hours=engine_result.production_impact_hours,
            cost_estimate=engine_result.cost_estimate,
            reason=f"TRM adjusted: {engine_result.explanation}",
        )

    def _heuristic_evaluate(self, state, engine_result):
        # Heuristic: If historical deferral breakdown rate is high, don't defer
        decision_type = engine_result.decision_type.value
        if decision_type == "defer" and state.historical_breakdown_rate_after_defer > 0.30:
            decision_type = "schedule"

        # Heuristic: If cost estimates historically overrun, inflate
        cost = engine_result.cost_estimate * state.avg_actual_vs_estimated_cost_ratio

        return MaintenanceRecommendation(
            order_id=state.order_id,
            decision_type=decision_type,
            confidence=0.6,
            recommended_date=engine_result.recommended_date,
            defer_to_date=engine_result.defer_to_date,
            defer_risk=engine_result.defer_risk_score,
            expedite=engine_result.expedite_recommended,
            outsource=engine_result.outsource_recommended,
            breakdown_probability=engine_result.breakdown_probability,
            production_impact_hours=engine_result.production_impact_hours,
            cost_estimate=cost,
            reason=f"Heuristic: {engine_result.explanation}",
        )

    def _encode_state(self, state):
        criticality_map = {"critical": 1.0, "high": 0.7, "normal": 0.4, "low": 0.2}
        return [
            state.days_since_last_maintenance / 365.0,
            state.maintenance_frequency_days / 365.0,
            state.days_overdue / 30.0,
            state.defer_count / 3.0,
            state.estimated_downtime_hours / 24.0,
            state.estimated_cost / 10000.0,
            1.0 if state.spare_parts_available else 0.0,
            criticality_map.get(state.asset_criticality, 0.4),
            state.asset_age_years / 20.0,
            state.mean_time_between_failures_days / 365.0,
            state.recent_failure_count / 5.0,
            state.production_schedule_load_pct / 100.0,
            state.production_impact_units / 1000.0,
            state.next_production_gap_days / 30.0,
            state.historical_breakdown_rate_after_defer,
            state.avg_actual_vs_estimated_cost_ratio,
        ]

    def _persist_decision(self, state, rec):
        if not self.db:
            return
        try:
            from app.models.powell_decisions import PowellMaintenanceDecision
            decision = PowellMaintenanceDecision(
                config_id=0,
                maintenance_order_id=state.order_id,
                asset_id=state.asset_id,
                site_id=state.site_id,
                maintenance_type=state.maintenance_type,
                decision_type=rec.decision_type,
                scheduled_date=state.scheduled_date,
                deferred_to_date=rec.defer_to_date,
                estimated_downtime_hours=state.estimated_downtime_hours,
                production_impact_units=state.production_impact_units,
                spare_parts_available=state.spare_parts_available,
                priority=state.priority,
                risk_score_if_deferred=rec.defer_risk,
                confidence=rec.confidence,
                state_features={
                    'asset_age': state.asset_age_years,
                    'mtbf': state.mean_time_between_failures_days,
                    'recent_failures': state.recent_failure_count,
                    'prod_load': state.production_schedule_load_pct,
                },
            )
            self.db.add(decision)
            self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to persist maintenance decision: {e}")

    def record_outcome(self, order_id, actual_start_date=None, actual_completion_date=None,
                       actual_downtime_hours=None, breakdown_occurred=False, was_executed=True):
        if not self.db:
            return
        try:
            from app.models.powell_decisions import PowellMaintenanceDecision
            d = (self.db.query(PowellMaintenanceDecision)
                 .filter(PowellMaintenanceDecision.maintenance_order_id == order_id)
                 .order_by(PowellMaintenanceDecision.created_at.desc()).first())
            if d:
                d.was_executed = was_executed
                d.actual_start_date = actual_start_date
                d.actual_completion_date = actual_completion_date
                d.actual_downtime_hours = actual_downtime_hours
                d.breakdown_occurred = breakdown_occurred
                self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to record maintenance outcome: {e}")

    def get_training_data(self, config_id, limit=1000):
        if not self.db:
            return []
        try:
            from app.models.powell_decisions import PowellMaintenanceDecision
            return [d.to_dict() for d in self.db.query(PowellMaintenanceDecision)
                    .filter(PowellMaintenanceDecision.config_id == config_id,
                            PowellMaintenanceDecision.was_executed.isnot(None))
                    .order_by(PowellMaintenanceDecision.created_at.desc()).limit(limit).all()]
        except Exception as e:
            logger.warning(f"Failed to get maintenance training data: {e}")
            return []

    def evaluate_batch(self, states):
        return [self.evaluate_scheduling(s) for s in states]
