"""
Supply Adjustment TRM

Narrow TRM for real-time corrections to the Supply Planning GNN output.
Handles: RCCP infeasibility flags, supplier confirmation changes, PO
acknowledgement deviations, demand/inventory plan changes.

TRM Scope (narrow):
- Given: GNN supply plan qty, RCCP feasibility, supplier confirmation rate
- Decide: Adjust plan factor? (Locked if frozen_horizon_flag)

Urgency formula:
  urgency = rccp_feasibility_flag × 0.5
          + (1 - supplier_confirmation_rate) × 0.3
          + |lead_time_deviation| × 0.2
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
class SupplyAdjustmentState:
    """11-dimensional state for Supply Adjustment TRM."""
    product_id: str
    site_id: str

    # GNN output
    gnn_supply_plan_qty: float           # GNN planned quantity for this period
    gnn_confidence: float                # [0, 1]

    # Feasibility signals
    rccp_feasibility_flag: float         # 1.0 if RCCP returned infeasible
    supplier_confirmation_rate: float    # confirmed POs / planned (last 4 weeks)
    open_po_coverage: float              # open PO qty / planned requirement
    lead_time_deviation: float           # actual LT vs. planned LT, normalised

    # ATP context
    available_to_promise: float          # current ATP at source site

    # Network signals
    exception_probability: float         # from tGNNSiteDirective (upstream site risk)
    demand_plan_change: float            # fractional change from Demand GNN this cycle
    inventory_target_change: float       # fractional change from Inventory GNN this cycle

    # Horizon lock
    frozen_horizon_flag: float           # 1.0 if order within 2 weeks


@dataclass
class SupplyAdjustmentRecommendation:
    """Result of Supply Adjustment TRM evaluation."""
    product_id: str
    site_id: str

    adjustment_factor: float             # bounded [0.80, 1.30]; 1.0 if frozen
    adjusted_qty: float                  # gnn_supply_plan_qty * adjustment_factor
    confidence: float                    # [0, 1]
    urgency: float                       # [0, 1]
    action_note: str                     # reason for adjustment
    requires_human_review: bool          # True if factor outside [0.90, 1.15]

    risk_bound: Optional[float] = None
    risk_assessment: Optional[Dict] = None


class SupplyAdjustmentTRM:
    """
    Supply Adjustment TRM.

    Applies in-cycle corrections to Supply Planning GNN quantities.
    Frozen horizon lock: if order is within 2 weeks, no adjustment made.
    """

    _FACTOR_MIN = 0.80
    _FACTOR_MAX = 1.30
    _REVIEW_LOW = 0.90
    _REVIEW_HIGH = 1.15

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
                self._cdt_wrapper = get_cdt_registry().get_or_create("supply_adjustment")
            except Exception:
                pass

    def evaluate(self, state: SupplyAdjustmentState) -> SupplyAdjustmentRecommendation:
        """Evaluate state and return supply adjustment recommendation."""
        if self.model is not None:
            try:
                rec = self._trm_evaluate(state)
            except Exception as e:
                logger.warning(f"TRM model failed for {state.product_id}: {e}")
                rec = self._heuristic_evaluate(state)
        else:
            rec = self._heuristic_evaluate(state)

        # CDT risk bound
        if self._cdt_wrapper is not None and getattr(self._cdt_wrapper, "is_calibrated", False):
            try:
                risk = self._cdt_wrapper.compute_risk_bound(abs(rec.adjustment_factor - 1.0))
                rec.risk_bound = risk.risk_bound
                rec.risk_assessment = risk.to_dict()
            except Exception:
                pass

        self._persist_decision(state, rec)
        return rec

    def _heuristic_evaluate(self, state: SupplyAdjustmentState) -> SupplyAdjustmentRecommendation:
        """Heuristic supply plan adjustment logic."""
        notes = []

        # Frozen horizon: no adjustment allowed
        if state.frozen_horizon_flag:
            return SupplyAdjustmentRecommendation(
                product_id=state.product_id,
                site_id=state.site_id,
                adjustment_factor=1.0,
                adjusted_qty=state.gnn_supply_plan_qty,
                confidence=0.95,
                urgency=0.0,
                action_note="Frozen horizon — order locked, no adjustment",
                requires_human_review=False,
            )

        factor = 1.0

        # RCCP infeasibility: reduce to ease capacity
        if state.rccp_feasibility_flag:
            factor = max(self._FACTOR_MIN, factor - 0.15)
            notes.append("RCCP infeasible")

        # Supplier confirmation shortfall: increase to hedge
        if state.supplier_confirmation_rate < 0.85:
            factor += (0.85 - state.supplier_confirmation_rate) * 0.5
            notes.append(f"supplier_conf={state.supplier_confirmation_rate:.2f}")

        # Demand plan increase propagates upstream
        if state.demand_plan_change > 0.10:
            factor += state.demand_plan_change * 0.5
            notes.append(f"demand_change={state.demand_plan_change:+.2f}")

        # Bound
        factor = max(self._FACTOR_MIN, min(self._FACTOR_MAX, factor))
        adjusted_qty = state.gnn_supply_plan_qty * factor

        # Urgency
        urgency = (
            state.rccp_feasibility_flag * 0.5
            + (1.0 - state.supplier_confirmation_rate) * 0.3
            + abs(state.lead_time_deviation) * 0.2
        )
        urgency = min(1.0, urgency)

        confidence = max(0.40, 0.72 - abs(factor - 1.0) * 0.6)
        requires_review = not (self._REVIEW_LOW <= factor <= self._REVIEW_HIGH)
        action_note = "; ".join(notes) if notes else "Supply plan within normal range"

        return SupplyAdjustmentRecommendation(
            product_id=state.product_id,
            site_id=state.site_id,
            adjustment_factor=factor,
            adjusted_qty=adjusted_qty,
            confidence=confidence,
            urgency=urgency,
            action_note=action_note,
            requires_human_review=requires_review,
        )

    def _trm_evaluate(self, state: SupplyAdjustmentState) -> SupplyAdjustmentRecommendation:
        """Neural TRM evaluation (when model is available)."""
        import torch
        if state.frozen_horizon_flag:
            return self._heuristic_evaluate(state)

        features = self._encode_state(state)
        with torch.no_grad():
            output = self.model(torch.tensor([features], dtype=torch.float32))

        confidence = float(output.get("confidence", 0.5))
        if confidence < 0.40:
            return self._heuristic_evaluate(state)

        raw_factor = float(output.get("adjustment_factor", 1.0))
        factor = max(self._FACTOR_MIN, min(self._FACTOR_MAX, raw_factor))
        adjusted_qty = state.gnn_supply_plan_qty * factor
        urgency = (
            state.rccp_feasibility_flag * 0.5
            + (1.0 - state.supplier_confirmation_rate) * 0.3
            + abs(state.lead_time_deviation) * 0.2
        )
        urgency = min(1.0, urgency)
        requires_review = not (self._REVIEW_LOW <= factor <= self._REVIEW_HIGH)

        return SupplyAdjustmentRecommendation(
            product_id=state.product_id,
            site_id=state.site_id,
            adjustment_factor=factor,
            adjusted_qty=adjusted_qty,
            confidence=confidence,
            urgency=urgency,
            action_note=f"TRM: factor={factor:.3f} conf={confidence:.2f}",
            requires_human_review=requires_review,
        )

    def _encode_state(self, state: SupplyAdjustmentState):
        """Encode state to feature vector for neural model."""
        return [
            state.gnn_supply_plan_qty / 10000.0,
            state.gnn_confidence,
            state.rccp_feasibility_flag,
            state.supplier_confirmation_rate,
            state.open_po_coverage,
            state.lead_time_deviation,
            state.available_to_promise / 10000.0,
            state.exception_probability,
            state.demand_plan_change,
            state.inventory_target_change,
            state.frozen_horizon_flag,
        ]

    def _persist_decision(self, state: SupplyAdjustmentState, rec: SupplyAdjustmentRecommendation) -> None:
        """Persist decision to DB (no-op if no DB session)."""
        if not self.db:
            return
        try:
            from app.models.planning_trm_decisions import PowellSupplyAdjustmentDecision
            from datetime import date
            d = PowellSupplyAdjustmentDecision(
                config_id=0,
                product_id=state.product_id,
                site_id=state.site_id,
                period_week=date.today(),
                gnn_supply_qty=state.gnn_supply_plan_qty,
                adjustment_factor=rec.adjustment_factor,
                adjusted_supply_qty=rec.adjusted_qty,
                confidence=rec.confidence,
                urgency=rec.urgency,
                reasoning=rec.action_note[:500] if rec.action_note else None,
            )
            self.db.add(d)
            self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to persist supply adjustment decision: {e}")

    def evaluate_batch(self, states):
        return [self.evaluate(s) for s in states]
