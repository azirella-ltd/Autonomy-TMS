"""
RCCP Adjustment TRM

Narrow TRM for in-cycle corrections to RCCP GNN output when real-time
conditions change after the last daily RCCP run.

TRM Scope (narrow):
- Given: GNN utilisation estimate, unplanned downtime, rush orders, maintenance flags
- Decide: Authorize overtime? Defer MPS? Escalate to S&OP?

Urgency formula:
  urgency = min(1.0,
               chronic_overload_weeks × 0.3
             + unplanned_downtime_hrs / 8.0 × 0.4
             + rush_order_flag × 0.3)
"""

from dataclasses import dataclass
from typing import Optional, Dict
import logging

from .hive_signal import HiveSignalBus

try:
    from ..conformal_prediction.conformal_decision import get_cdt_registry
    _CDT_AVAILABLE = True
except ImportError:
    _CDT_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class RCCPAdjustmentState:
    """9-dimensional state for RCCP Adjustment TRM."""
    site_id: str
    resource_id: str

    # GNN output
    gnn_utilisation_pct: float          # RCCP GNN resource load estimate [0, 1]
    gnn_confidence: float               # [0, 1]

    # Real-time deviation signals
    oee_deviation: float                # actual OEE - planned OEE this cycle
    unplanned_downtime_hrs: float       # unplanned downtime in last 24h

    # Authorization context
    rush_order_flag: float              # 1.0 if AAP rush order authorization received
    overtime_cost_budget_used: float    # fraction of period budget consumed [0, 1]
    maintenance_emergency_flag: float   # 1.0 if MaintenanceSchedulingTRM flagged critical
    shift_extension_authorized: float   # 1.0 if HR/Finance AAP approved

    # Escalation trigger
    chronic_overload_weeks: int         # consecutive weeks of overload


@dataclass
class RCCPAdjustmentRecommendation:
    """Result of RCCP Adjustment TRM evaluation."""
    site_id: str
    resource_id: str

    overtime_delta_hours: float         # additional hours to authorize (>= 0)
    mps_defer_flag: bool                # defer lowest-priority MO to next week
    escalate_to_sop: bool               # trigger EscalationArbiter strategic escalation
    confidence: float                   # [0, 1]
    urgency: float                      # [0, 1]
    reasoning: str
    requires_human_review: bool         # True if escalate_to_sop or overtime > 16h

    risk_bound: Optional[float] = None
    risk_assessment: Optional[Dict] = None


class RCCPAdjustmentTRM:
    """
    RCCP Adjustment TRM.

    Handles real-time capacity exceptions between daily RCCP GNN runs.
    Key decisions: overtime authorization, MPS deferral, S&OP escalation.
    """

    def __init__(self, site_key: str, config=None, model=None, db_session=None):
        self.site_key = site_key
        self.config = config
        self.model = model
        self.db = db_session
        self.signal_bus: Optional[HiveSignalBus] = None
        self.ctx_explainer = None
        self._cdt_wrapper = None
        if _CDT_AVAILABLE:
            try:
                self._cdt_wrapper = get_cdt_registry().get_or_create("rccp_adjustment")
            except Exception:
                pass

    def evaluate(self, state: RCCPAdjustmentState) -> RCCPAdjustmentRecommendation:
        """Evaluate state and return RCCP adjustment recommendation."""
        if self.model is not None:
            try:
                rec = self._trm_evaluate(state)
            except Exception as e:
                logger.warning(f"TRM model failed for {state.resource_id}: {e}")
                rec = self._heuristic_evaluate(state)
        else:
            rec = self._heuristic_evaluate(state)

        # CDT risk bound
        if self._cdt_wrapper is not None and getattr(self._cdt_wrapper, "is_calibrated", False):
            try:
                risk = self._cdt_wrapper.compute_risk_bound(rec.overtime_delta_hours / 24.0)
                rec.risk_bound = risk.risk_bound
                rec.risk_assessment = risk.to_dict()
            except Exception:
                pass

        self._persist_decision(state, rec)
        return rec

    def _heuristic_evaluate(self, state: RCCPAdjustmentState) -> RCCPAdjustmentRecommendation:
        """Heuristic RCCP adjustment logic."""
        overtime_delta = 0.0
        mps_defer = False
        escalate = False
        notes = []

        # Unplanned downtime recovery — use shift extension if authorized
        if state.unplanned_downtime_hrs > 4 and state.shift_extension_authorized:
            overtime_delta = state.unplanned_downtime_hrs
            notes.append(f"shift_extension for {state.unplanned_downtime_hrs:.1f}h downtime")

        # Chronic overload — escalate to S&OP for structural resolution
        if state.chronic_overload_weeks >= 3:
            escalate = True
            notes.append(f"chronic_overload_weeks={state.chronic_overload_weeks}")

        # Rush order — add overtime if budget allows
        if state.rush_order_flag and state.overtime_cost_budget_used <= 0.8:
            overtime_delta += 4.0
            notes.append("rush_order_overtime")

        # Maintenance emergency at high utilisation — defer MPS
        if state.maintenance_emergency_flag and state.gnn_utilisation_pct > 0.90:
            mps_defer = True
            notes.append("maintenance_emergency_mps_defer")

        # Urgency
        urgency = min(
            1.0,
            state.chronic_overload_weeks * 0.3
            + (state.unplanned_downtime_hrs / 8.0) * 0.4
            + state.rush_order_flag * 0.3
        )

        confidence = 0.75 if not escalate else 0.65
        requires_review = escalate or overtime_delta > 16.0
        reasoning = "; ".join(notes) if notes else "No RCCP adjustment required"

        return RCCPAdjustmentRecommendation(
            site_id=state.site_id,
            resource_id=state.resource_id,
            overtime_delta_hours=max(0.0, overtime_delta),
            mps_defer_flag=mps_defer,
            escalate_to_sop=escalate,
            confidence=confidence,
            urgency=urgency,
            reasoning=reasoning,
            requires_human_review=requires_review,
        )

    def _trm_evaluate(self, state: RCCPAdjustmentState) -> RCCPAdjustmentRecommendation:
        """Neural TRM evaluation (when model is available)."""
        import torch
        features = self._encode_state(state)
        with torch.no_grad():
            output = self.model(torch.tensor([features], dtype=torch.float32))

        confidence = float(output.get("confidence", 0.5))
        if confidence < 0.40:
            return self._heuristic_evaluate(state)

        overtime_delta = max(0.0, float(output.get("overtime_delta_hours", 0.0)))
        mps_defer = bool(output.get("mps_defer_flag", False))
        escalate = bool(output.get("escalate_to_sop", False))
        urgency = min(
            1.0,
            state.chronic_overload_weeks * 0.3
            + (state.unplanned_downtime_hrs / 8.0) * 0.4
            + state.rush_order_flag * 0.3
        )
        requires_review = escalate or overtime_delta > 16.0

        return RCCPAdjustmentRecommendation(
            site_id=state.site_id,
            resource_id=state.resource_id,
            overtime_delta_hours=overtime_delta,
            mps_defer_flag=mps_defer,
            escalate_to_sop=escalate,
            confidence=confidence,
            urgency=urgency,
            reasoning=f"TRM: overtime={overtime_delta:.1f}h defer={mps_defer} escalate={escalate}",
            requires_human_review=requires_review,
        )

    def _encode_state(self, state: RCCPAdjustmentState):
        """Encode state to feature vector for neural model."""
        return [
            state.gnn_utilisation_pct,
            state.gnn_confidence,
            state.oee_deviation,
            state.unplanned_downtime_hrs / 24.0,
            state.rush_order_flag,
            state.overtime_cost_budget_used,
            state.maintenance_emergency_flag,
            state.shift_extension_authorized,
            min(1.0, state.chronic_overload_weeks / 10.0),
        ]

    def _persist_decision(self, state: RCCPAdjustmentState, rec: RCCPAdjustmentRecommendation) -> None:
        """Persist decision to DB (no-op if no DB session)."""
        if not self.db:
            return
        try:
            from app.models.planning_trm_decisions import PowellRCCPAdjustmentDecision
            from datetime import date
            d = PowellRCCPAdjustmentDecision(
                config_id=0,
                site_id=state.site_id,
                resource_id=state.resource_id,
                # TODO(virtual-clock): TRM has no tenant/config context (config_id=0 placeholder);
                # add config_id to TRM __init__ then use config_today_sync for period_week.
                period_week=date.today(),
                gnn_utilisation_pct=state.gnn_utilisation_pct,
                overtime_delta_hours=rec.overtime_delta_hours,
                mps_defer_flag=rec.mps_defer_flag,
                escalate_to_sop=rec.escalate_to_sop,
                confidence=rec.confidence,
                urgency=rec.urgency,
                reasoning=rec.reasoning[:500] if rec.reasoning else None,
            )
            self.db.add(d)
            self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to persist RCCP adjustment decision: {e}")

    def evaluate_batch(self, states):
        return [self.evaluate(s) for s in states]
