"""
Demand Adjustment TRM

Narrow TRM for in-cycle corrections to the Demand Planning GNN output.
Handles learnable deviation patterns: persistent forecast bias, known seasonal
effects the GNN underweights, real-time demand sensing corrections.

TRM Scope (narrow):
- Given: GNN p50 forecast, recent forecast accuracy, contextual signals
- Decide: Adjust forecast? By what factor? With what confidence?

Urgency formula: urgency = min(1.0, recent_mape × 3.0 + |recent_bias| × 2.0)

HiveSignals emitted:
  - DEMAND_SURGE if adjustment_factor > 1.15
  - DEMAND_DROP  if adjustment_factor < 0.85
"""

from dataclasses import dataclass
from typing import Optional, Any, Dict
import logging

from .hive_signal import HiveSignal, HiveSignalBus, HiveSignalType

try:
    from ..conformal_prediction.conformal_decision import get_cdt_registry
    _CDT_AVAILABLE = True
except ImportError:
    _CDT_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class DemandAdjustmentState:
    """12-dimensional state for Demand Adjustment TRM."""
    product_id: str
    site_id: str

    # GNN output
    gnn_p50_forecast: float        # GNN point estimate for this period
    gnn_confidence: float          # GNN model confidence [0, 1]

    # Forecast accuracy signals
    recent_bias: float             # actual - forecast over last 8 periods, normalised
    recent_mape: float             # rolling MAPE last 8 periods

    # Inventory context
    inventory_weeks_cover: float   # current cover (high → demand correction less urgent)
    backlog_flag: float            # 1 if active backlog (demand > supply)

    # Email signal context
    email_signal_adj_factor: float  # most recent demand signal adjustment (1.0 = none)
    email_signal_age_days: float    # days since signal (decay)

    # Product context
    lifecycle_stage: float          # 0=new, 0.33=growth, 0.67=mature, 1=end-of-life
    promotion_active: float         # 1 if active promotion

    # Temporal context
    week_of_year_normalised: float  # seasonality position [0, 1]
    demand_trend_4w: float          # (avg weeks 1-2)/(avg weeks 3-4) - 1


@dataclass
class DemandAdjustmentRecommendation:
    """Result of Demand Adjustment TRM evaluation."""
    product_id: str
    site_id: str

    adjustment_factor: float        # bounded [0.70, 1.50]
    adjusted_forecast: float        # gnn_p50_forecast * adjustment_factor
    confidence: float               # [0, 1]
    urgency: float                  # [0, 1]
    requires_human_review: bool     # True if factor outside [0.85, 1.20]
    reasoning: str

    risk_bound: Optional[float] = None
    risk_assessment: Optional[Dict] = None


class DemandAdjustmentTRM:
    """
    Demand Adjustment TRM.

    Applies in-cycle corrections to Demand Planning GNN output.
    Uses heuristic logic when model is absent; supports CDT risk bounds.
    """

    _FACTOR_MIN = 0.70
    _FACTOR_MAX = 1.50
    _REVIEW_LOW = 0.85
    _REVIEW_HIGH = 1.20

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
                self._cdt_wrapper = get_cdt_registry().get_or_create("demand_adjustment")
            except Exception:
                pass

    def evaluate(self, state: DemandAdjustmentState) -> DemandAdjustmentRecommendation:
        """Evaluate state and return demand adjustment recommendation."""
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

        self._emit_signals(state, rec)
        self._persist_decision(state, rec)
        return rec

    def _heuristic_evaluate(self, state: DemandAdjustmentState) -> DemandAdjustmentRecommendation:
        """Heuristic demand adjustment logic."""
        factor = 1.0

        # Primary signal: persistent forecast bias + recent trend
        if state.recent_bias > 0.10 and state.demand_trend_4w > 0.05:
            factor = 1.0 + (state.recent_bias * 0.5 + state.demand_trend_4w * 0.3)

        # Email signal adjustment (decay by age)
        if state.email_signal_adj_factor != 1.0 and state.email_signal_age_days < 14:
            age_decay = max(0.0, 1.0 - state.email_signal_age_days / 14.0)
            email_delta = (state.email_signal_adj_factor - 1.0) * age_decay
            factor += email_delta * 0.5

        # Backlog amplification: demand clearly exceeds supply
        if state.backlog_flag:
            factor = min(self._FACTOR_MAX, factor * 1.1)

        # Lifecycle end-of-life correction
        if state.lifecycle_stage > 0.85:
            factor = min(factor, 1.0)  # Do not amplify end-of-life items

        # Bound
        factor = max(self._FACTOR_MIN, min(self._FACTOR_MAX, factor))

        adjusted = state.gnn_p50_forecast * factor

        # Urgency
        urgency = min(1.0, state.recent_mape * 3.0 + abs(state.recent_bias) * 2.0)

        # Confidence: reduce when signals conflict
        confidence = max(0.40, 0.70 - abs(factor - 1.0) * 0.5)

        requires_review = not (self._REVIEW_LOW <= factor <= self._REVIEW_HIGH)

        reasoning = (
            f"Demand adjustment factor {factor:.3f} for {state.product_id}@{state.site_id}: "
            f"bias={state.recent_bias:.3f}, MAPE={state.recent_mape:.3f}, "
            f"trend={state.demand_trend_4w:.3f}, backlog={bool(state.backlog_flag)}"
        )

        return DemandAdjustmentRecommendation(
            product_id=state.product_id,
            site_id=state.site_id,
            adjustment_factor=factor,
            adjusted_forecast=adjusted,
            confidence=confidence,
            urgency=urgency,
            requires_human_review=requires_review,
            reasoning=reasoning,
        )

    def _trm_evaluate(self, state: DemandAdjustmentState) -> DemandAdjustmentRecommendation:
        """Neural TRM evaluation (when model is available)."""
        import torch
        features = self._encode_state(state)
        with torch.no_grad():
            output = self.model(torch.tensor([features], dtype=torch.float32))

        confidence = float(output.get("confidence", 0.5))
        if confidence < 0.40:
            return self._heuristic_evaluate(state)

        raw_factor = float(output.get("adjustment_factor", 1.0))
        factor = max(self._FACTOR_MIN, min(self._FACTOR_MAX, raw_factor))
        adjusted = state.gnn_p50_forecast * factor
        urgency = min(1.0, state.recent_mape * 3.0 + abs(state.recent_bias) * 2.0)
        requires_review = not (self._REVIEW_LOW <= factor <= self._REVIEW_HIGH)

        return DemandAdjustmentRecommendation(
            product_id=state.product_id,
            site_id=state.site_id,
            adjustment_factor=factor,
            adjusted_forecast=adjusted,
            confidence=confidence,
            urgency=urgency,
            requires_human_review=requires_review,
            reasoning=f"TRM: factor={factor:.3f} conf={confidence:.2f}",
        )

    def _encode_state(self, state: DemandAdjustmentState):
        """Encode state to feature vector for neural model."""
        return [
            state.gnn_p50_forecast / 10000.0,
            state.gnn_confidence,
            state.recent_bias,
            state.recent_mape,
            state.inventory_weeks_cover / 52.0,
            state.backlog_flag,
            state.email_signal_adj_factor - 1.0,
            state.email_signal_age_days / 30.0,
            state.lifecycle_stage,
            state.promotion_active,
            state.week_of_year_normalised,
            state.demand_trend_4w,
        ]

    def _emit_signals(self, state: DemandAdjustmentState, rec: DemandAdjustmentRecommendation) -> None:
        """Emit HiveSignals after demand adjustment decision."""
        if self.signal_bus is None:
            return
        try:
            if rec.adjustment_factor > 1.15:
                self.signal_bus.emit(HiveSignal(
                    source_trm="demand_adjustment",
                    signal_type=HiveSignalType.DEMAND_SURGE,
                    urgency=rec.urgency,
                    direction="surplus",
                    magnitude=rec.adjustment_factor - 1.0,
                    product_id=state.product_id,
                    payload={"factor": rec.adjustment_factor, "site_id": state.site_id},
                ))
                self.signal_bus.urgency.update("demand_adjustment", rec.urgency, "surplus")
            elif rec.adjustment_factor < 0.85:
                self.signal_bus.emit(HiveSignal(
                    source_trm="demand_adjustment",
                    signal_type=HiveSignalType.DEMAND_DROP,
                    urgency=rec.urgency,
                    direction="shortage",
                    magnitude=1.0 - rec.adjustment_factor,
                    product_id=state.product_id,
                    payload={"factor": rec.adjustment_factor, "site_id": state.site_id},
                ))
                self.signal_bus.urgency.update("demand_adjustment", rec.urgency, "shortage")
            else:
                self.signal_bus.urgency.update("demand_adjustment", 0.0, "neutral")
        except Exception as e:
            logger.debug(f"Signal emit failed: {e}")

    def _persist_decision(self, state: DemandAdjustmentState, rec: DemandAdjustmentRecommendation) -> None:
        """Persist decision to DB (no-op if no DB session)."""
        if not self.db:
            return
        try:
            from app.models.planning_trm_decisions import PowellDemandAdjustmentDecision
            d = PowellDemandAdjustmentDecision(
                config_id=0,
                product_id=state.product_id,
                site_id=state.site_id,
                gnn_p50_forecast=state.gnn_p50_forecast,
                adjustment_factor=rec.adjustment_factor,
                adjusted_forecast=rec.adjusted_forecast,
                confidence=rec.confidence,
                urgency=rec.urgency,
                reasoning=rec.reasoning[:500] if rec.reasoning else None,
            )
            self.db.add(d)
            self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to persist demand adjustment decision: {e}")

    def evaluate_batch(self, states):
        return [self.evaluate(s) for s in states]
