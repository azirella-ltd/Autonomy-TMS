"""
Inventory Buffer TRM

Narrow TRM for inventory buffer adjustment decisions.
Learns when to adjust buffer levels beyond deterministic formulas.

NOTE: Renamed from SafetyStockTRM (Feb 2026). The term "safety stock" encourages
MRP systems to treat buffer levels as hard demand targets, generating planned orders
that compete with real customer demand for upstream capacity. "Inventory buffer"
emphasizes the buffer's role as an uncertainty absorber, not a replenishment trigger.

TRM Scope (narrow):
- Given: baseline buffer from BufferCalculator, demand context, recent performance
- Decide: Should we adjust the buffer? By how much? (multiplier in [0.5, 2.0])

Characteristics that make this suitable for TRM:
- Narrow scope: single product-location buffer adjustment
- Clear baseline: BufferCalculator provides deterministic formula
- Measurable feedback: stockout rate, excess inventory cost, DOS accuracy
- Repeatable: evaluated periodically for each product-location

The deterministic BufferCalculator handles the 4 AWS SC policy formulas.
This TRM handles context-dependent adjustments the formulas can't capture:
- Seasonal demand shifts
- Demand regime changes (CV shifts)
- Trend-driven adjustments
- Post-stockout safety margin increases
- Forecast bias compensation

References:
- BufferCalculator (engines/buffer_calculator.py)
- Powell VFA for narrow execution decisions
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from enum import Enum
import numpy as np
import logging

from .hive_signal import HiveSignal, HiveSignalBus, HiveSignalType

try:
    from ..conformal_prediction.conformal_decision import get_cdt_registry
    _CDT_AVAILABLE = True
except ImportError:
    _CDT_AVAILABLE = False

logger = logging.getLogger(__name__)


class BufferAdjustmentReason(Enum):
    """Reason for inventory buffer adjustment"""
    NO_ADJUSTMENT = "no_adjustment"
    SEASONAL_PEAK = "seasonal_peak"
    SEASONAL_TROUGH = "seasonal_trough"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    RECENT_STOCKOUT = "recent_stockout"
    EXCESS_INVENTORY = "excess_inventory"
    FORECAST_BIAS = "forecast_bias"


# Backward-compatible alias
SSAdjustmentReason = BufferAdjustmentReason


@dataclass
class BufferState:
    """State representation for inventory buffer TRM decisions"""
    product_id: str
    location_id: str

    # Baseline from engine
    baseline_ss: float
    baseline_reorder_point: float
    baseline_target_inventory: float
    policy_type: str  # "abs_level", "doc_dem", "doc_fcst", "sl"

    # Current inventory position
    current_on_hand: float
    current_dos: float  # Days of supply

    # Demand statistics
    demand_cv: float  # Coefficient of variation (std/mean)
    avg_daily_demand: float
    demand_trend: float  # Positive = increasing, negative = decreasing

    # Seasonal context
    seasonal_index: float  # 1.0 = normal, >1 = peak, <1 = trough
    month_of_year: int  # 1-12

    # Performance history
    recent_stockout_count: int  # Stockouts in last 90 days
    recent_excess_days: int  # Days with DOS > 2x target in last 90 days
    forecast_bias: float  # Avg (forecast - actual) / actual, positive = over-forecast

    # Lead time context
    lead_time_days: float
    lead_time_cv: float  # Lead time variability

    def to_features(self) -> np.ndarray:
        """Convert to feature vector for TRM"""
        return np.array([
            self.baseline_ss / max(1, self.avg_daily_demand * 30),  # Normalized buffer
            self.current_dos / 30,  # Normalized DOS
            self.demand_cv,
            self.demand_trend,
            self.seasonal_index,
            self.month_of_year / 12,
            self.recent_stockout_count / 10,
            self.recent_excess_days / 90,
            self.forecast_bias,
            self.lead_time_cv,
            self.current_on_hand / max(1, self.baseline_target_inventory),
        ], dtype=np.float32)


# Backward-compatible alias
SSState = BufferState


@dataclass
class BufferAdjustment:
    """Result of inventory buffer adjustment evaluation"""
    product_id: str
    location_id: str

    # Engine baseline
    baseline_ss: float

    # Adjustment
    multiplier: float  # Applied to baseline buffer
    adjusted_ss: float  # = baseline_ss * multiplier
    adjusted_reorder_point: float

    # Context
    reason: BufferAdjustmentReason
    confidence: float  # 0-1

    # Explanation
    description: str

    # Context-aware explanation (populated when explainer is available)
    context_explanation: Optional[Dict] = None
    risk_bound: Optional[float] = None
    risk_assessment: Optional[Dict] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "product_id": self.product_id,
            "location_id": self.location_id,
            "baseline_ss": self.baseline_ss,
            "multiplier": self.multiplier,
            "adjusted_ss": self.adjusted_ss,
            "adjusted_reorder_point": self.adjusted_reorder_point,
            "reason": self.reason.value,
            "confidence": self.confidence,
            "description": self.description,
        }
        if self.risk_bound is not None:
            d["risk_bound"] = self.risk_bound
        if self.risk_assessment is not None:
            d["risk_assessment"] = self.risk_assessment
        return d


# Backward-compatible alias
SSAdjustment = BufferAdjustment


class InventoryBufferTRM:
    """
    TRM-based service for inventory buffer adjustment decisions.

    Makes narrow decisions about when and how to adjust the inventory buffer
    beyond what the deterministic BufferCalculator computes.

    NOTE: The buffer is a soft uncertainty absorber — NOT a hard demand target.
    MRP should prioritize real customer demand over buffer replenishment.

    Architecture:
    - BufferCalculator provides: baseline buffer from 4 policy types
    - tGNN provides: demand signals, criticality scores
    - TRM decides: multiplier adjustment [0.5, 2.0]
    """

    def __init__(
        self,
        ss_calculator=None,
        trm_model: Optional[Any] = None,
        use_heuristic_fallback: bool = True,
        min_multiplier: float = 0.5,
        max_multiplier: float = 2.0,
        db: Optional[Any] = None,
        config_id: Optional[int] = None,
    ):
        """
        Initialize Inventory Buffer TRM.

        Args:
            ss_calculator: BufferCalculator engine instance
            trm_model: Trained TRM model (optional)
            use_heuristic_fallback: Use heuristic if TRM unavailable
            min_multiplier: Minimum allowed buffer multiplier
            max_multiplier: Maximum allowed buffer multiplier
            db: Optional SQLAlchemy Session for persisting decisions
            config_id: Optional config_id for DB persistence
        """
        self._engine = ss_calculator
        self.trm_model = trm_model
        self.use_heuristic_fallback = use_heuristic_fallback
        self.min_multiplier = min_multiplier
        self.max_multiplier = max_multiplier
        self.db = db
        self.config_id = config_id

        # Context-aware explainer (set externally by SiteAgent or caller)
        self.ctx_explainer = None
        self._cdt_wrapper = None
        if _CDT_AVAILABLE:
            try:
                self._cdt_wrapper = get_cdt_registry().get_or_create("inventory_buffer")
            except Exception:
                pass

        self.signal_bus: Optional[HiveSignalBus] = None

        # tGNN-provided buffer multiplier for bound modulation.
        # When set via apply_network_context(), modulates min/max_multiplier
        # so the TRM operates within tGNN-adjusted bounds.
        self._tgnn_ss_multiplier: float = 1.0

        # Decision history for training
        self._decision_history: List[Dict[str, Any]] = []

    @property
    def effective_bounds(self) -> tuple:
        """Return (min_mult, max_mult) modulated by the tGNN buffer multiplier.

        When tGNN says safety_stock_multiplier=1.3 (increase buffer across the board),
        the effective bounds shift upward so the TRM's range becomes [0.65, 2.6]
        instead of [0.5, 2.0].  This lets the tGNN steer the TRM without overriding it.
        """
        return (
            self.min_multiplier * self._tgnn_ss_multiplier,
            self.max_multiplier * self._tgnn_ss_multiplier,
        )

    def apply_network_context(self, params: Dict[str, Any]) -> None:
        """Accept network-level parameters from tGNNSiteDirective.

        Called by SiteAgent.apply_directive() when a new directive arrives.
        The key parameter is ``safety_stock_multiplier`` which modulates the
        TRM's effective min/max bounds (see ``effective_bounds``).
        """
        ssm = params.get("safety_stock_multiplier")
        if ssm is not None:
            self._tgnn_ss_multiplier = float(max(0.1, min(5.0, ssm)))
            logger.info(
                f"InventoryBufferTRM: tGNN buffer multiplier updated to "
                f"{self._tgnn_ss_multiplier:.2f}, effective bounds "
                f"{self.effective_bounds}"
            )

    def _read_signals_before_decision(self) -> Dict[str, Any]:
        """Read relevant hive signals before making buffer decision."""
        if self.signal_bus is None:
            return {}
        try:
            signals = self.signal_bus.read(
                consumer_trm="inventory_buffer",
                types={
                    HiveSignalType.ATP_SHORTAGE,
                    HiveSignalType.ATP_EXCESS,
                    HiveSignalType.FORECAST_ADJUSTED,
                    HiveSignalType.DEMAND_SURGE,
                    HiveSignalType.DEMAND_DROP,
                },
            )
            context: Dict[str, Any] = {}
            for s in signals:
                if s.signal_type == HiveSignalType.ATP_SHORTAGE:
                    context["atp_shortage"] = True
                    context["atp_shortage_urgency"] = s.current_strength
                elif s.signal_type == HiveSignalType.ATP_EXCESS:
                    context["atp_excess"] = True
                elif s.signal_type == HiveSignalType.FORECAST_ADJUSTED:
                    context["forecast_adjusted"] = True
                    context["forecast_direction"] = s.direction
                elif s.signal_type == HiveSignalType.DEMAND_SURGE:
                    context["demand_surge"] = True
                elif s.signal_type == HiveSignalType.DEMAND_DROP:
                    context["demand_drop"] = True
            return context
        except Exception as e:
            logger.debug(f"Signal read failed: {e}")
            return {}

    def _emit_signals_after_decision(
        self, state: BufferState, result: BufferAdjustment
    ) -> None:
        """Emit hive signals after buffer decision."""
        if self.signal_bus is None:
            return
        try:
            if result.multiplier > 1.05:
                urgency = min(1.0, (result.multiplier - 1.0) * 2.0)
                self.signal_bus.emit(HiveSignal(
                    source_trm="inventory_buffer",
                    signal_type=HiveSignalType.BUFFER_INCREASED,
                    urgency=urgency,
                    direction="shortage",
                    magnitude=result.multiplier - 1.0,
                    product_id=state.product_id,
                    payload={
                        "baseline": result.baseline_ss,
                        "adjusted": result.adjusted_ss,
                        "multiplier": result.multiplier,
                        "reason": result.reason.value,
                    },
                ))
                self.signal_bus.urgency.update("inventory_buffer", urgency, "shortage")
            elif result.multiplier < 0.95:
                urgency = min(1.0, (1.0 - result.multiplier) * 2.0)
                self.signal_bus.emit(HiveSignal(
                    source_trm="inventory_buffer",
                    signal_type=HiveSignalType.BUFFER_DECREASED,
                    urgency=urgency,
                    direction="surplus",
                    magnitude=1.0 - result.multiplier,
                    product_id=state.product_id,
                    payload={
                        "baseline": result.baseline_ss,
                        "adjusted": result.adjusted_ss,
                        "multiplier": result.multiplier,
                        "reason": result.reason.value,
                    },
                ))
                self.signal_bus.urgency.update("inventory_buffer", urgency, "surplus")
            else:
                self.signal_bus.urgency.update("inventory_buffer", 0.0, "neutral")
        except Exception as e:
            logger.debug(f"Signal emit failed: {e}")

    def evaluate(self, state: BufferState) -> BufferAdjustment:
        """
        Evaluate whether inventory buffer should be adjusted.

        Args:
            state: Current buffer state with baseline and context

        Returns:
            BufferAdjustment with multiplier and adjusted buffer level
        """
        self._read_signals_before_decision()

        if self.trm_model is not None:
            result = self._trm_evaluate(state)
        elif self.use_heuristic_fallback:
            result = self._heuristic_evaluate(state)
        else:
            result = BufferAdjustment(
                product_id=state.product_id,
                location_id=state.location_id,
                baseline_ss=state.baseline_ss,
                multiplier=1.0,
                adjusted_ss=state.baseline_ss,
                adjusted_reorder_point=state.baseline_reorder_point,
                reason=BufferAdjustmentReason.NO_ADJUSTMENT,
                confidence=1.0,
                description="No adjustment - TRM disabled",
            )

        # Enrich with context-aware reasoning
        if self.ctx_explainer is not None:
            try:
                summary = (
                    f"Buffer {result.reason.value}: {result.multiplier:.2f}x "
                    f"for {state.product_id} at {state.location_id}"
                )
                ctx = self.ctx_explainer.generate_inline_explanation(
                    decision_summary=summary,
                    confidence=result.confidence,
                    trm_confidence=result.confidence if self.trm_model else None,
                    decision_category='inventory_buffer',
                    delta_percent=abs(result.multiplier - 1.0) * 100,
                    policy_params={
                        'baseline_ss': state.baseline_ss,
                        'baseline_rop': state.baseline_reorder_point,
                        'multiplier': result.multiplier,
                    },
                )
                result.description = ctx.explanation
                result.context_explanation = ctx.to_dict()
            except Exception as e:
                logger.debug(f"Context enrichment failed: {e}")

        # CDT risk bound
        if self._cdt_wrapper is not None and self._cdt_wrapper.is_calibrated:
            try:
                risk = self._cdt_wrapper.compute_risk_bound(result.adjusted_ss)
                result.risk_bound = risk.risk_bound
                result.risk_assessment = risk.to_dict()
            except Exception:
                pass

        # Emit signals
        self._emit_signals_after_decision(state, result)

        # Record for training
        self._record_decision(state, result)

        # Persist to DB
        self._persist_decision(state, result)

        return result

    def evaluate_batch(
        self,
        states: List[BufferState]
    ) -> List[BufferAdjustment]:
        """Evaluate multiple product-locations."""
        return [self.evaluate(state) for state in states]

    def _trm_evaluate(self, state: BufferState) -> BufferAdjustment:
        """Evaluate using TRM model"""
        try:
            features = state.to_features()
            output = self.trm_model.predict(features.reshape(1, -1))

            multiplier = float(output["multiplier"][0, 0])
            lo, hi = self.effective_bounds
            multiplier = max(lo, min(hi, multiplier))
            confidence = float(np.clip(output["confidence"][0, 0], 0, 1))

            adjusted_ss = state.baseline_ss * multiplier
            adjusted_rop = state.baseline_reorder_point + (adjusted_ss - state.baseline_ss)

            reason = self._classify_reason(state, multiplier)

            return BufferAdjustment(
                product_id=state.product_id,
                location_id=state.location_id,
                baseline_ss=state.baseline_ss,
                multiplier=multiplier,
                adjusted_ss=adjusted_ss,
                adjusted_reorder_point=adjusted_rop,
                reason=reason,
                confidence=confidence,
                description=f"TRM adjustment: {multiplier:.2f}x ({reason.value})",
            )

        except Exception as e:
            logger.warning(f"TRM evaluation failed: {e}")
            return self._heuristic_evaluate(state)

    def _heuristic_evaluate(self, state: BufferState) -> BufferAdjustment:
        """
        Evaluate using deterministic heuristic rules.

        This delegates to the BufferCalculator engine for the baseline,
        then applies context-based multiplier adjustments.
        """
        multiplier = 1.0
        reason = BufferAdjustmentReason.NO_ADJUSTMENT

        # Rule 1: Recent stockouts → increase buffer
        if state.recent_stockout_count >= 3:
            multiplier = 1.4
            reason = BufferAdjustmentReason.RECENT_STOCKOUT
        elif state.recent_stockout_count >= 1:
            multiplier = 1.2
            reason = BufferAdjustmentReason.RECENT_STOCKOUT

        # Rule 2: High demand volatility → increase buffer
        elif state.demand_cv > 0.5:
            multiplier = 1.3
            reason = BufferAdjustmentReason.HIGH_VOLATILITY
        elif state.demand_cv > 0.3:
            multiplier = 1.15
            reason = BufferAdjustmentReason.HIGH_VOLATILITY

        # Rule 3: Seasonal peak → increase buffer
        elif state.seasonal_index > 1.3:
            multiplier = 1.2
            reason = BufferAdjustmentReason.SEASONAL_PEAK
        elif state.seasonal_index < 0.7:
            multiplier = 0.8
            reason = BufferAdjustmentReason.SEASONAL_TROUGH

        # Rule 4: Demand trend → adjust buffer
        elif state.demand_trend > 0.1:
            multiplier = 1.1
            reason = BufferAdjustmentReason.TREND_UP
        elif state.demand_trend < -0.1:
            multiplier = 0.9
            reason = BufferAdjustmentReason.TREND_DOWN

        # Rule 5: Excess inventory → decrease buffer
        elif state.recent_excess_days > 60:
            multiplier = 0.85
            reason = BufferAdjustmentReason.EXCESS_INVENTORY

        # Rule 6: Forecast bias compensation
        elif abs(state.forecast_bias) > 0.15:
            # Under-forecasting → increase buffer; over-forecasting → decrease
            multiplier = 1.0 + min(0.3, max(-0.3, -state.forecast_bias))
            reason = BufferAdjustmentReason.FORECAST_BIAS

        # Clamp multiplier using tGNN-modulated bounds
        lo, hi = self.effective_bounds
        multiplier = max(lo, min(hi, multiplier))

        adjusted_ss = state.baseline_ss * multiplier
        adjusted_rop = state.baseline_reorder_point + (adjusted_ss - state.baseline_ss)

        return BufferAdjustment(
            product_id=state.product_id,
            location_id=state.location_id,
            baseline_ss=state.baseline_ss,
            multiplier=multiplier,
            adjusted_ss=adjusted_ss,
            adjusted_reorder_point=adjusted_rop,
            reason=reason,
            confidence=0.85,  # Heuristic confidence
            description=f"Heuristic adjustment: {multiplier:.2f}x ({reason.value})",
        )

    def _classify_reason(self, state: BufferState, multiplier: float) -> BufferAdjustmentReason:
        """Classify the reason for a TRM-generated adjustment"""
        if abs(multiplier - 1.0) < 0.05:
            return BufferAdjustmentReason.NO_ADJUSTMENT
        if state.recent_stockout_count >= 1:
            return BufferAdjustmentReason.RECENT_STOCKOUT
        if state.demand_cv > 0.3:
            return BufferAdjustmentReason.HIGH_VOLATILITY if multiplier > 1.0 else BufferAdjustmentReason.LOW_VOLATILITY
        if state.seasonal_index > 1.2:
            return BufferAdjustmentReason.SEASONAL_PEAK
        if state.seasonal_index < 0.8:
            return BufferAdjustmentReason.SEASONAL_TROUGH
        if state.demand_trend > 0.05:
            return BufferAdjustmentReason.TREND_UP
        if state.demand_trend < -0.05:
            return BufferAdjustmentReason.TREND_DOWN
        if abs(state.forecast_bias) > 0.1:
            return BufferAdjustmentReason.FORECAST_BIAS
        return BufferAdjustmentReason.NO_ADJUSTMENT

    def _record_decision(self, state: BufferState, result: BufferAdjustment):
        """Record decision for TRM training"""
        record = {
            "state": {
                "product_id": state.product_id,
                "location_id": state.location_id,
                "baseline_ss": state.baseline_ss,
                "current_dos": state.current_dos,
                "demand_cv": state.demand_cv,
                "seasonal_index": state.seasonal_index,
                "recent_stockout_count": state.recent_stockout_count,
            },
            "state_features": state.to_features().tolist(),
            "result": result.to_dict(),
        }
        self._decision_history.append(record)

        if len(self._decision_history) > 10000:
            self._decision_history = self._decision_history[-10000:]

    def record_outcome(
        self,
        adjustment: BufferAdjustment,
        actual_stockout: bool,
        actual_dos_after: float,
        excess_cost: float = 0.0,
        actual_outcome: Optional[Dict[str, Any]] = None
    ):
        """
        Record actual outcome for TRM training feedback.

        Args:
            adjustment: The buffer adjustment that was made
            actual_stockout: Whether a stockout occurred in the review period
            actual_dos_after: Actual DOS at end of review period
            excess_cost: Cost of excess inventory held
            actual_outcome: Additional outcome data
        """
        record = {
            "adjustment": adjustment.to_dict(),
            "actual_stockout": actual_stockout,
            "actual_dos_after": actual_dos_after,
            "excess_cost": excess_cost,
            "actual_outcome": actual_outcome,
        }
        self._decision_history.append(record)

    def get_training_data(self) -> List[Dict[str, Any]]:
        """Get decision history for TRM training"""
        return self._decision_history

    def _persist_decision(self, state: BufferState, result: BufferAdjustment):
        """Persist decision to powell_buffer_decisions table."""
        if self.db is None or self.config_id is None:
            return
        try:
            from app.models.powell_decisions import PowellBufferDecision
            from app.services.powell.decision_reasoning import inventory_buffer_reasoning
            row = PowellBufferDecision(
                config_id=self.config_id,
                product_id=result.product_id,
                location_id=result.location_id,
                baseline_ss=result.baseline_ss,
                multiplier=result.multiplier,
                adjusted_ss=result.adjusted_ss,
                reason=result.reason.value,
                confidence=result.confidence,
                demand_cv=state.demand_cv,
                current_dos=state.current_dos,
                seasonal_index=state.seasonal_index,
                recent_stockout_count=state.recent_stockout_count,
                state_features=state.to_features().tolist(),
                decision_reasoning=inventory_buffer_reasoning(
                    product_id=result.product_id,
                    location_id=result.location_id,
                    baseline_ss=result.baseline_ss,
                    adjusted_ss=result.adjusted_ss,
                    multiplier=result.multiplier,
                    confidence=result.confidence,
                    reason=result.reason.value,
                ),
            )
            self.db.add(row)
        except Exception as e:
            logger.warning(f"Failed to persist buffer decision: {e}")


# Backward-compatible alias
SafetyStockTRM = InventoryBufferTRM
