"""
PO Creation TRM

Narrow TRM for Purchase Order creation decisions.
Decides when to create POs, quantities, and timing based on
inventory state, demand forecasts, and supplier constraints.

TRM Scope (narrow):
- Given: inventory position, demand forecast, supplier info, lead times
- Decide: Create PO now? What quantity? Which supplier?

Characteristics that make this suitable for TRM:
- Narrow scope: single product-location-supplier decision
- Short horizon: PO creation is an immediate decision
- Fast feedback: supplier acknowledgment, eventual receipt
- Clear objective: maintain service while minimizing cost
- Repeatable: happens frequently with similar patterns

References:
- Conversation with Claude on TRM scope
- Powell VFA for narrow execution decisions
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
import numpy as np
import logging
from datetime import datetime, timedelta

from .engines.mrp_engine import MRPEngine, MRPConfig
from .hive_signal import HiveSignal, HiveSignalBus, HiveSignalType

try:
    from ..conformal_prediction.conformal_decision import get_cdt_registry
    _CDT_AVAILABLE = True
except ImportError:
    _CDT_AVAILABLE = False

logger = logging.getLogger(__name__)


class POTriggerReason(Enum):
    """Reason for PO creation"""
    REORDER_POINT = "reorder_point"  # Hit reorder point
    SAFETY_STOCK = "safety_stock"  # Below safety stock
    FORECAST_DRIVEN = "forecast_driven"  # Anticipated demand
    SCHEDULED = "scheduled"  # Regular replenishment cycle
    EXPEDITE = "expedite"  # Emergency order
    OPPORTUNISTIC = "opportunistic"  # Good pricing/availability


class POUrgency(Enum):
    """Urgency level for PO"""
    CRITICAL = "critical"  # Stockout imminent
    HIGH = "high"  # Below safety stock
    NORMAL = "normal"  # Standard replenishment
    LOW = "low"  # Opportunistic


@dataclass
class SupplierInfo:
    """Supplier information for PO decisions"""
    supplier_id: str
    product_id: str

    # Lead time
    lead_time_days: float
    lead_time_variability: float  # Std dev

    # Cost
    unit_cost: float
    order_cost: float  # Fixed cost per order

    # Constraints
    min_order_qty: float = 0.0
    max_order_qty: float = float('inf')
    order_multiple: float = 1.0  # Must order in multiples

    # Reliability
    on_time_rate: float = 0.95
    fill_rate: float = 0.98
    quality_rate: float = 0.99

    # Availability
    is_available: bool = True
    next_available_date: Optional[str] = None

    def get_effective_lead_time(self, service_level: float = 0.95) -> float:
        """Get lead time with safety margin for service level"""
        from scipy import stats
        z = stats.norm.ppf(service_level)
        return self.lead_time_days + z * self.lead_time_variability


@dataclass
class InventoryPosition:
    """Current inventory position for a product-location"""
    product_id: str
    location_id: str

    # Current state
    on_hand: float
    in_transit: float
    on_order: float  # POs not yet shipped
    committed: float  # Reserved for orders
    backlog: float

    # Targets
    safety_stock: float
    reorder_point: float
    target_inventory: float

    # Context
    average_daily_demand: float
    demand_variability: float

    @property
    def available(self) -> float:
        """Available inventory"""
        return max(0, self.on_hand - self.committed - self.backlog)

    @property
    def inventory_position(self) -> float:
        """Full inventory position including pipeline"""
        return self.on_hand + self.in_transit + self.on_order - self.committed - self.backlog

    @property
    def days_of_supply(self) -> float:
        """Days of supply based on average demand"""
        if self.average_daily_demand <= 0:
            return float('inf')
        return self.available / self.average_daily_demand

    @property
    def coverage_ratio(self) -> float:
        """Ratio of inventory position to target"""
        if self.target_inventory <= 0:
            return float('inf')
        return self.inventory_position / self.target_inventory


@dataclass
class PORecommendation:
    """Recommendation for PO creation"""
    product_id: str
    location_id: str
    supplier_id: str

    # Quantity
    recommended_qty: float
    min_qty: float
    max_qty: float

    # Timing
    create_now: bool
    urgency: POUrgency
    trigger_reason: POTriggerReason

    # Expected outcomes
    expected_receipt_date: str
    expected_cost: float
    expected_inventory_position_after: float

    # TRM confidence
    confidence: float
    reasoning: str

    # Context-aware explanation (populated when explainer is available)
    context_explanation: Optional[Dict] = None
    risk_bound: Optional[float] = None
    risk_assessment: Optional[Dict] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "product_id": self.product_id,
            "location_id": self.location_id,
            "supplier_id": self.supplier_id,
            "recommended_qty": self.recommended_qty,
            "min_qty": self.min_qty,
            "max_qty": self.max_qty,
            "create_now": self.create_now,
            "urgency": self.urgency.value,
            "trigger_reason": self.trigger_reason.value,
            "expected_receipt_date": self.expected_receipt_date,
            "expected_cost": self.expected_cost,
            "expected_inventory_position_after": self.expected_inventory_position_after,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
        }
        if self.risk_bound is not None:
            result["risk_bound"] = self.risk_bound
        return result


@dataclass
class POCreationState:
    """
    State representation for TRM PO creation decisions.

    Captures the decision context at evaluation time.
    """
    product_id: str
    location_id: str

    inventory_position: InventoryPosition
    suppliers: List[SupplierInfo]

    # Demand context
    forecast_next_30_days: float
    forecast_uncertainty: float

    # Network context from tGNN
    supply_risk_score: float = 0.0
    demand_volatility_score: float = 0.0

    def get_supplier_features(self, supplier_id: str) -> np.ndarray:
        """Get features for a specific supplier"""
        supplier = None
        for s in self.suppliers:
            if s.supplier_id == supplier_id:
                supplier = s
                break

        if supplier is None:
            return np.zeros(15, dtype=np.float32)

        inv_features = np.array([
            self.inventory_position.on_hand,
            self.inventory_position.in_transit,
            self.inventory_position.on_order,
            self.inventory_position.committed,
            self.inventory_position.backlog,
            self.inventory_position.safety_stock,
            self.inventory_position.reorder_point,
            self.inventory_position.days_of_supply if self.inventory_position.days_of_supply != float('inf') else 999,
        ], dtype=np.float32)

        supplier_features = np.array([
            supplier.lead_time_days,
            supplier.unit_cost,
            supplier.min_order_qty,
            supplier.on_time_rate,
            1.0 if supplier.is_available else 0.0,
        ], dtype=np.float32)

        context_features = np.array([
            self.forecast_next_30_days,
            self.forecast_uncertainty,
            self.supply_risk_score,
            self.demand_volatility_score,
        ], dtype=np.float32)

        return np.concatenate([inv_features, supplier_features, context_features])


class POCreationTRM:
    """
    TRM-based service for PO creation decisions.

    Makes narrow decisions about when and how much to order
    from suppliers based on current inventory state and forecasts.

    Architecture:
    - tGNN provides: demand forecasts, supply risk scores, network context
    - TRM decides: PO creation recommendations
    """

    def __init__(
        self,
        trm_model: Optional[Any] = None,
        use_heuristic_fallback: bool = True,
        default_service_level: float = 0.95,
        min_order_benefit_days: float = 1.0,  # Min DOS benefit to recommend
        mrp_engine: Optional[MRPEngine] = None,
        db: Optional[Any] = None,
        config_id: Optional[int] = None,
    ):
        """
        Initialize PO Creation TRM.

        Args:
            trm_model: Trained TRM model (optional)
            use_heuristic_fallback: Use heuristic if TRM unavailable
            default_service_level: Target service level for calculations
            min_order_benefit_days: Minimum DOS improvement to recommend
            mrp_engine: Deterministic MRP engine (optional, for heuristic baseline)
            db: Optional SQLAlchemy Session for persisting decisions
            config_id: Optional config_id for DB persistence
        """
        self._engine = mrp_engine
        self.trm_model = trm_model
        self.use_heuristic_fallback = use_heuristic_fallback
        self.default_service_level = default_service_level
        self.min_order_benefit_days = min_order_benefit_days
        self.db = db
        self.config_id = config_id
        self.signal_bus: Optional[HiveSignalBus] = None  # Set by SiteAgent

        # Context-aware explainer (set externally by SiteAgent or caller)
        self.ctx_explainer = None

        # Conformal Decision Theory wrapper for risk bounds
        self._cdt_wrapper = None
        if _CDT_AVAILABLE:
            try:
                self._cdt_wrapper = get_cdt_registry().get_or_create("po_creation")
            except Exception:
                pass

        # Decision history for training
        self._decision_history: List[Dict[str, Any]] = []

    def evaluate_po_need(
        self,
        state: POCreationState
    ) -> List[PORecommendation]:
        """
        Evaluate PO needs for a product-location.

        Args:
            state: Current state for the product-location

        Returns:
            List of PO recommendations, one per available supplier
        """
        # Read hive signals before decision
        self._read_signals_before_decision()

        recommendations = []

        # First check if we need to order at all
        need_to_order, trigger_reason, urgency = self._assess_order_need(state)

        if not need_to_order:
            return []

        # Evaluate each supplier
        for supplier in state.suppliers:
            if not supplier.is_available:
                continue

            if self.trm_model is not None:
                rec = self._trm_evaluate_supplier(state, supplier, trigger_reason, urgency)
            elif self.use_heuristic_fallback:
                rec = self._heuristic_evaluate_supplier(state, supplier, trigger_reason, urgency)
            else:
                continue

            if rec is not None and rec.recommended_qty > 0:
                recommendations.append(rec)

        # Sort by cost-effectiveness (lowest cost per unit)
        recommendations.sort(
            key=lambda r: r.expected_cost / max(1, r.recommended_qty)
        )

        # Emit signals after decision
        self._emit_signals_after_decision(recommendations)

        # Persist to DB if session available
        self._persist_recommendations(recommendations)

        return recommendations

    def _assess_order_need(
        self,
        state: POCreationState
    ) -> Tuple[bool, POTriggerReason, POUrgency]:
        """Assess whether we need to order"""
        inv_pos = state.inventory_position

        # Critical: at or below zero
        if inv_pos.available <= 0:
            return True, POTriggerReason.EXPEDITE, POUrgency.CRITICAL

        # High: below safety stock
        if inv_pos.inventory_position < inv_pos.safety_stock:
            return True, POTriggerReason.SAFETY_STOCK, POUrgency.HIGH

        # Normal: at or below reorder point
        if inv_pos.inventory_position <= inv_pos.reorder_point:
            return True, POTriggerReason.REORDER_POINT, POUrgency.NORMAL

        # Forecast-driven: will need before lead time
        if state.suppliers:
            min_lead_time = min(s.lead_time_days for s in state.suppliers if s.is_available)
            forecast_demand = (state.forecast_next_30_days / 30) * min_lead_time

            if inv_pos.inventory_position - forecast_demand < inv_pos.safety_stock:
                return True, POTriggerReason.FORECAST_DRIVEN, POUrgency.NORMAL

        return False, POTriggerReason.SCHEDULED, POUrgency.LOW

    def _trm_evaluate_supplier(
        self,
        state: POCreationState,
        supplier: SupplierInfo,
        trigger_reason: POTriggerReason,
        urgency: POUrgency
    ) -> Optional[PORecommendation]:
        """Evaluate a supplier using TRM"""
        try:
            features = state.get_supplier_features(supplier.supplier_id)

            # TRM outputs dict: action_logits, order_qty, confidence, value
            output = self.trm_model.predict(features.reshape(1, -1))

            action_idx = int(np.argmax(output["action_logits"][0]))
            should_order = action_idx in (0, 2)  # order or expedite
            quantity = max(0, float(output["order_qty"][0, 0]))
            confidence = float(np.clip(output["confidence"][0, 0], 0, 1))

            if not should_order or quantity <= 0:
                return None

            # Apply supplier constraints
            quantity = self._apply_supplier_constraints(quantity, supplier)

            return self._build_recommendation(
                state, supplier, quantity, trigger_reason, urgency, confidence
            )

        except Exception as e:
            logger.warning(f"TRM evaluation failed: {e}")
            return self._heuristic_evaluate_supplier(state, supplier, trigger_reason, urgency)

    def _heuristic_evaluate_supplier(
        self,
        state: POCreationState,
        supplier: SupplierInfo,
        trigger_reason: POTriggerReason,
        urgency: POUrgency
    ) -> Optional[PORecommendation]:
        """Evaluate a supplier using heuristic rules"""
        inv_pos = state.inventory_position

        # Calculate order-up-to quantity
        # Cover lead time + review period with safety margin
        effective_lead_time = supplier.get_effective_lead_time(self.default_service_level)

        # Demand during lead time
        demand_during_lt = (state.forecast_next_30_days / 30) * effective_lead_time

        # Target: enough to cover lead time demand plus safety stock
        target_position = demand_during_lt + inv_pos.safety_stock

        # Order quantity = target - current position
        quantity = max(0, target_position - inv_pos.inventory_position)

        if quantity <= 0:
            return None

        # Apply supplier constraints
        quantity = self._apply_supplier_constraints(quantity, supplier)

        if quantity <= 0:
            return None

        return self._build_recommendation(
            state, supplier, quantity, trigger_reason, urgency, 0.85
        )

    def _apply_supplier_constraints(
        self,
        quantity: float,
        supplier: SupplierInfo
    ) -> float:
        """Apply supplier constraints to quantity"""
        # Apply min/max
        quantity = max(supplier.min_order_qty, min(quantity, supplier.max_order_qty))

        # Round to order multiple
        if supplier.order_multiple > 0:
            quantity = np.ceil(quantity / supplier.order_multiple) * supplier.order_multiple

        return quantity

    def _build_recommendation(
        self,
        state: POCreationState,
        supplier: SupplierInfo,
        quantity: float,
        trigger_reason: POTriggerReason,
        urgency: POUrgency,
        confidence: float
    ) -> PORecommendation:
        """Build a complete recommendation"""
        inv_pos = state.inventory_position

        # Calculate expected receipt date
        receipt_date = datetime.now() + timedelta(days=supplier.lead_time_days)

        # Calculate expected cost
        expected_cost = (quantity * supplier.unit_cost) + supplier.order_cost

        # Calculate expected inventory position after receipt
        expected_position_after = inv_pos.inventory_position + quantity

        # Build reasoning
        reasoning, context_dict = self._build_reasoning(
            state, supplier, quantity, trigger_reason, urgency, confidence
        )

        # Compute CDT risk bound
        cdt_risk_bound = None
        cdt_risk_assessment = None
        if self._cdt_wrapper is not None and self._cdt_wrapper.is_calibrated:
            try:
                risk = self._cdt_wrapper.compute_risk_bound(expected_cost)
                cdt_risk_bound = risk.risk_bound
                cdt_risk_assessment = risk.to_dict()
            except Exception:
                pass

        return PORecommendation(
            product_id=state.product_id,
            location_id=state.location_id,
            supplier_id=supplier.supplier_id,
            recommended_qty=quantity,
            min_qty=supplier.min_order_qty,
            max_qty=min(supplier.max_order_qty, quantity * 2),  # Allow some flexibility
            create_now=urgency in [POUrgency.CRITICAL, POUrgency.HIGH],
            urgency=urgency,
            trigger_reason=trigger_reason,
            expected_receipt_date=receipt_date.strftime("%Y-%m-%d"),
            expected_cost=expected_cost,
            expected_inventory_position_after=expected_position_after,
            confidence=confidence,
            reasoning=reasoning,
            context_explanation=context_dict,
            risk_bound=cdt_risk_bound,
            risk_assessment=cdt_risk_assessment,
        )

    def _build_reasoning(
        self,
        state: POCreationState,
        supplier: SupplierInfo,
        quantity: float,
        trigger_reason: POTriggerReason,
        urgency: POUrgency,
        confidence: float = 1.0,
    ) -> Tuple[str, Optional[Dict]]:
        """Build human-readable reasoning, with context-aware explanation if available.

        Returns:
            Tuple of (reasoning_text, context_explanation_dict_or_None)
        """
        inv_pos = state.inventory_position

        parts = []

        # Trigger reason
        if trigger_reason == POTriggerReason.EXPEDITE:
            parts.append(f"CRITICAL: Available inventory ({inv_pos.available:.0f}) at critical level")
        elif trigger_reason == POTriggerReason.SAFETY_STOCK:
            parts.append(f"Below safety stock ({inv_pos.inventory_position:.0f} < {inv_pos.safety_stock:.0f})")
        elif trigger_reason == POTriggerReason.REORDER_POINT:
            parts.append(f"At reorder point ({inv_pos.inventory_position:.0f} <= {inv_pos.reorder_point:.0f})")
        elif trigger_reason == POTriggerReason.FORECAST_DRIVEN:
            parts.append(f"Forecast-driven: anticipated demand during lead time")

        # Quantity rationale
        parts.append(f"Order {quantity:.0f} units from {supplier.supplier_id}")
        parts.append(f"Lead time: {supplier.lead_time_days:.0f} days")

        # Expected outcome
        expected_dos = (inv_pos.inventory_position + quantity) / max(1, state.forecast_next_30_days / 30)
        parts.append(f"Expected DOS after receipt: {expected_dos:.1f} days")

        base_reasoning = "; ".join(parts)

        # Enrich with context-aware explanation if available
        context_dict = None
        if self.ctx_explainer is not None:
            try:
                expected_cost = quantity * supplier.unit_cost + supplier.order_cost
                summary = f"{trigger_reason.value}: Order {quantity:.0f} units from {supplier.supplier_id}"
                ctx = self.ctx_explainer.generate_inline_explanation(
                    decision_summary=summary,
                    confidence=confidence,
                    trm_confidence=confidence if self.trm_model else None,
                    decision_category='supply_plan',
                    decision_value=expected_cost,
                    policy_params={
                        'safety_stock': inv_pos.safety_stock,
                        'reorder_point': inv_pos.reorder_point,
                        'service_level': self.default_service_level,
                    },
                )
                base_reasoning = ctx.explanation
                context_dict = ctx.to_dict()
            except Exception as e:
                logger.debug(f"Context enrichment failed: {e}")

        return base_reasoning, context_dict

    def get_best_recommendation(
        self,
        state: POCreationState
    ) -> Optional[PORecommendation]:
        """Get the single best PO recommendation"""
        recommendations = self.evaluate_po_need(state)
        return recommendations[0] if recommendations else None

    def _persist_recommendations(self, recommendations: List[PORecommendation]):
        """Persist recommendations to powell_po_decisions table."""
        if self.db is None or self.config_id is None:
            return
        try:
            from app.models.powell_decisions import PowellPODecision
            from datetime import date as date_type
            for rec in recommendations:
                inv_pos_val = rec.expected_inventory_position_after - rec.recommended_qty
                try:
                    receipt_date = datetime.strptime(rec.expected_receipt_date, "%Y-%m-%d").date()
                except Exception:
                    receipt_date = None
                row = PowellPODecision(
                    config_id=self.config_id,
                    product_id=rec.product_id,
                    location_id=rec.location_id,
                    supplier_id=rec.supplier_id,
                    recommended_qty=rec.recommended_qty,
                    trigger_reason=rec.trigger_reason.value,
                    urgency=rec.urgency.value,
                    confidence=rec.confidence,
                    inventory_position=inv_pos_val,
                    expected_receipt_date=receipt_date,
                    expected_cost=rec.expected_cost,
                )
                self.db.add(row)
        except Exception as e:
            logger.warning(f"Failed to persist PO decisions: {e}")

    # ---- Hive signal methods ------------------------------------------------

    def _read_signals_before_decision(self) -> None:
        """Read relevant hive signals before PO evaluation."""
        if self.signal_bus is None:
            return
        try:
            signals = self.signal_bus.read(
                consumer_trm="po_creation",
                types={
                    HiveSignalType.ATP_SHORTAGE,
                    HiveSignalType.DEMAND_SURGE,
                    HiveSignalType.SS_INCREASED,
                    HiveSignalType.FORECAST_ADJUSTED,
                },
            )
            if signals:
                logger.debug(f"PO Creation read {len(signals)} hive signals")
        except Exception as e:
            logger.debug(f"PO signal read failed: {e}")

    def _emit_signals_after_decision(
        self, recommendations: List[PORecommendation]
    ) -> None:
        """Emit hive signals after PO decision."""
        if not self.signal_bus or not recommendations:
            return
        try:
            for rec in recommendations:
                if rec.urgency in (POUrgency.CRITICAL, POUrgency.HIGH):
                    self.signal_bus.emit(HiveSignal(
                        source_trm="po_creation",
                        signal_type=HiveSignalType.PO_EXPEDITE,
                        urgency=0.8 if rec.urgency == POUrgency.CRITICAL else 0.6,
                        direction="relief",
                        magnitude=rec.recommended_qty,
                        product_id=rec.product_id,
                        payload={
                            "supplier_id": rec.supplier_id,
                            "qty": rec.recommended_qty,
                            "expected_receipt": rec.expected_receipt_date,
                        },
                    ))
                else:
                    self.signal_bus.emit(HiveSignal(
                        source_trm="po_creation",
                        signal_type=HiveSignalType.PO_DEFERRED,
                        urgency=0.2,
                        direction="neutral",
                        magnitude=rec.recommended_qty,
                        product_id=rec.product_id,
                        payload={
                            "supplier_id": rec.supplier_id,
                            "qty": rec.recommended_qty,
                        },
                    ))
            max_urg = max(
                0.8 if r.urgency == POUrgency.CRITICAL else
                0.6 if r.urgency == POUrgency.HIGH else 0.2
                for r in recommendations
            )
            direction = "relief" if any(
                r.urgency in (POUrgency.CRITICAL, POUrgency.HIGH)
                for r in recommendations
            ) else "neutral"
            self.signal_bus.urgency.update("po_creation", max_urg, direction)
        except Exception as e:
            logger.debug(f"PO signal emit failed: {e}")

    def record_outcome(
        self,
        recommendation: PORecommendation,
        was_executed: bool,
        actual_outcome: Optional[Dict[str, Any]] = None
    ):
        """
        Record outcome for TRM training.

        Args:
            recommendation: The recommendation that was made
            was_executed: Whether the PO was created
            actual_outcome: Actual results (receipt date, qty received, etc.)
        """
        record = {
            "recommendation": recommendation.to_dict(),
            "was_executed": was_executed,
            "actual_outcome": actual_outcome,
        }
        self._decision_history.append(record)

        if len(self._decision_history) > 10000:
            self._decision_history = self._decision_history[-10000:]

    def get_training_data(self) -> List[Dict[str, Any]]:
        """Get decision history for TRM training"""
        return self._decision_history
