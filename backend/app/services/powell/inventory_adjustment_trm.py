"""
Inventory Adjustment TRM

Narrow TRM for in-cycle corrections to the Inventory Planning GNN output.
Handles persistent stockout patterns, supplier reliability degradation, and
OEE changes affecting production fill rate.

TRM Scope (narrow):
- Given: GNN SS quantity recommendation, recent stockout rate, supplier trends
- Decide: Adjust SS delta? By how much? With what confidence?

Urgency formula:
  urgency = min(1.0, stockout_rate_4w × 3.0 + |supplier_reliability_trend| × 2.0)

HiveSignals emitted:
  - BUFFER_INCREASED if ss_adjustment_delta > 0.10
  - BUFFER_DECREASED if ss_adjustment_delta < -0.10
"""

from dataclasses import dataclass
from typing import Optional, Dict
import logging

from .hive_signal import HiveSignal, HiveSignalBus, HiveSignalType

try:
    from ..conformal_prediction.conformal_decision import get_cdt_registry
    _CDT_AVAILABLE = True
except ImportError:
    _CDT_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class InventoryAdjustmentState:
    """10-dimensional state for Inventory Adjustment TRM."""
    product_id: str
    site_id: str

    # GNN output
    gnn_ss_quantity: float               # GNN safety stock recommendation
    gnn_confidence: float                # [0, 1]

    # Performance signals
    actual_stockout_rate_4w: float       # recent stockout frequency
    supplier_reliability_trend: float    # current - 8w_avg (negative = deteriorating)
    oee_trend: float                     # current OEE - 4w_avg OEE

    # Current state
    on_hand_weeks_cover: float           # current on-hand / avg weekly demand
    lead_time_trend: float               # current LT - 8w_avg LT (normalised weeks)
    demand_cv_trend: float               # demand variability change vs. prior period

    # Cost pressure
    holding_cost_pressure: float         # 1.0 if on_hand > 2×SS, else 0.0

    # Policy context
    ss_multiplier: float                 # current θ*.safety_stock_multiplier


@dataclass
class InventoryAdjustmentRecommendation:
    """Result of Inventory Adjustment TRM evaluation."""
    product_id: str
    site_id: str

    ss_adjustment_delta: float           # bounded [-0.30, +0.50] fractional delta
    adjusted_ss_quantity: float          # gnn_ss_quantity * (1 + ss_adjustment_delta)
    confidence: float                    # [0, 1]
    urgency: float                       # [0, 1]
    requires_human_review: bool          # True if |delta| > 0.30
    reasoning: str

    risk_bound: Optional[float] = None
    risk_assessment: Optional[Dict] = None


class InventoryAdjustmentTRM:
    """
    Inventory Adjustment TRM.

    Applies in-cycle corrections to Inventory Planning GNN SS targets.
    Uses heuristic logic when model is absent; supports CDT risk bounds.
    """

    _DELTA_MIN = -0.30
    _DELTA_MAX = +0.50
    _REVIEW_THRESHOLD = 0.30

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
                self._cdt_wrapper = get_cdt_registry().get_or_create("inventory_adjustment")
            except Exception:
                pass

    def evaluate(self, state: InventoryAdjustmentState) -> InventoryAdjustmentRecommendation:
        """Evaluate state and return inventory adjustment recommendation."""
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
                risk = self._cdt_wrapper.compute_risk_bound(abs(rec.ss_adjustment_delta))
                rec.risk_bound = risk.risk_bound
                rec.risk_assessment = risk.to_dict()
            except Exception:
                pass

        self._emit_signals(state, rec)
        self._persist_decision(state, rec)
        return rec

    def _heuristic_evaluate(self, state: InventoryAdjustmentState) -> InventoryAdjustmentRecommendation:
        """Heuristic SS adjustment logic."""
        delta = 0.0

        # Stockout pressure — increase SS
        if state.actual_stockout_rate_4w > 0.05:
            delta += 0.20 * (state.actual_stockout_rate_4w / 0.05)

        # Supplier reliability deterioration
        if state.supplier_reliability_trend < -0.10:
            delta += 0.15

        # OEE decline — production capacity at risk
        if state.oee_trend < -0.10:
            delta += 0.10

        # Lead time increase
        if state.lead_time_trend > 0.5:
            delta += 0.10 * min(1.0, state.lead_time_trend)

        # Holding cost pressure — reduce excess buffer
        if state.holding_cost_pressure:
            delta -= 0.15

        # Bound
        delta = max(self._DELTA_MIN, min(self._DELTA_MAX, delta))

        adjusted_ss = max(0.0, state.gnn_ss_quantity * (1.0 + delta))

        # Urgency
        urgency = min(
            1.0,
            state.actual_stockout_rate_4w * 3.0 + abs(state.supplier_reliability_trend) * 2.0
        )

        # Confidence
        confidence = max(0.40, 0.72 - abs(delta) * 0.5)

        requires_review = abs(delta) > self._REVIEW_THRESHOLD

        reasoning = (
            f"SS delta {delta:+.3f} for {state.product_id}@{state.site_id}: "
            f"stockout_rate={state.actual_stockout_rate_4w:.3f}, "
            f"reliability_trend={state.supplier_reliability_trend:+.3f}, "
            f"oee_trend={state.oee_trend:+.3f}, "
            f"holding_pressure={bool(state.holding_cost_pressure)}"
        )

        return InventoryAdjustmentRecommendation(
            product_id=state.product_id,
            site_id=state.site_id,
            ss_adjustment_delta=delta,
            adjusted_ss_quantity=adjusted_ss,
            confidence=confidence,
            urgency=urgency,
            requires_human_review=requires_review,
            reasoning=reasoning,
        )

    def _trm_evaluate(self, state: InventoryAdjustmentState) -> InventoryAdjustmentRecommendation:
        """Neural TRM evaluation (when model is available)."""
        import torch
        features = self._encode_state(state)
        with torch.no_grad():
            output = self.model(torch.tensor([features], dtype=torch.float32))

        confidence = float(output.get("confidence", 0.5))
        if confidence < 0.40:
            return self._heuristic_evaluate(state)

        raw_delta = float(output.get("ss_adjustment_delta", 0.0))
        delta = max(self._DELTA_MIN, min(self._DELTA_MAX, raw_delta))
        adjusted_ss = max(0.0, state.gnn_ss_quantity * (1.0 + delta))
        urgency = min(
            1.0,
            state.actual_stockout_rate_4w * 3.0 + abs(state.supplier_reliability_trend) * 2.0
        )
        requires_review = abs(delta) > self._REVIEW_THRESHOLD

        return InventoryAdjustmentRecommendation(
            product_id=state.product_id,
            site_id=state.site_id,
            ss_adjustment_delta=delta,
            adjusted_ss_quantity=adjusted_ss,
            confidence=confidence,
            urgency=urgency,
            requires_human_review=requires_review,
            reasoning=f"TRM: delta={delta:+.3f} conf={confidence:.2f}",
        )

    def _encode_state(self, state: InventoryAdjustmentState):
        """Encode state to feature vector for neural model."""
        return [
            state.gnn_ss_quantity / 10000.0,
            state.gnn_confidence,
            state.actual_stockout_rate_4w,
            state.supplier_reliability_trend,
            state.oee_trend,
            state.on_hand_weeks_cover / 52.0,
            state.lead_time_trend / 4.0,
            state.demand_cv_trend,
            state.holding_cost_pressure,
            state.ss_multiplier / 3.0,
        ]

    def _emit_signals(self, state: InventoryAdjustmentState, rec: InventoryAdjustmentRecommendation) -> None:
        """Emit HiveSignals after inventory adjustment decision."""
        if self.signal_bus is None:
            return
        try:
            if rec.ss_adjustment_delta > 0.10:
                self.signal_bus.emit(HiveSignal(
                    source_trm="inventory_adjustment",
                    signal_type=HiveSignalType.BUFFER_INCREASED,
                    urgency=rec.urgency,
                    direction="surplus",
                    magnitude=rec.ss_adjustment_delta,
                    product_id=state.product_id,
                    payload={"delta": rec.ss_adjustment_delta, "site_id": state.site_id},
                ))
                self.signal_bus.urgency.update("inventory_adjustment", rec.urgency, "surplus")
            elif rec.ss_adjustment_delta < -0.10:
                self.signal_bus.emit(HiveSignal(
                    source_trm="inventory_adjustment",
                    signal_type=HiveSignalType.BUFFER_DECREASED,
                    urgency=rec.urgency,
                    direction="shortage",
                    magnitude=abs(rec.ss_adjustment_delta),
                    product_id=state.product_id,
                    payload={"delta": rec.ss_adjustment_delta, "site_id": state.site_id},
                ))
                self.signal_bus.urgency.update("inventory_adjustment", rec.urgency, "shortage")
            else:
                self.signal_bus.urgency.update("inventory_adjustment", 0.0, "neutral")
        except Exception as e:
            logger.debug(f"Signal emit failed: {e}")

    def _persist_decision(self, state: InventoryAdjustmentState, rec: InventoryAdjustmentRecommendation) -> None:
        """Persist decision to DB (no-op if no DB session)."""
        if not self.db:
            return
        try:
            from app.models.planning_trm_decisions import PowellInventoryAdjustmentDecision
            d = PowellInventoryAdjustmentDecision(
                config_id=0,
                product_id=state.product_id,
                site_id=state.site_id,
                gnn_ss_quantity=state.gnn_ss_quantity,
                ss_adjustment_delta=rec.ss_adjustment_delta,
                adjusted_ss_quantity=rec.adjusted_ss_quantity,
                confidence=rec.confidence,
                urgency=rec.urgency,
                reasoning=rec.reasoning[:500] if rec.reasoning else None,
            )
            self.db.add(d)
            self.db.flush()
        except Exception as e:
            logger.warning(f"Failed to persist inventory adjustment decision: {e}")

    def evaluate_batch(self, states):
        return [self.evaluate(s) for s in states]
