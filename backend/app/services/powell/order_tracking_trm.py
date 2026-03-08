"""
Order Tracking TRM

Narrow TRM for order exception detection and recommended actions.
Monitors order status and detects anomalies that require attention.

TRM Scope (narrow):
- Given: order status, expected vs actual timing, historical patterns
- Decide: Is this an exception? What action to take?

Characteristics that make this suitable for TRM:
- Narrow scope: single order evaluation
- Short horizon: detect and act quickly
- Fast feedback: order eventually resolves
- Clear objective: minimize exceptions and their impact
- Repeatable: many orders with similar patterns

References:
- Conversation with Claude on TRM scope
- Powell VFA for narrow execution decisions
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
import numpy as np
import logging
from datetime import datetime, timedelta

from .engines.order_tracking_engine import (
    OrderTrackingEngine, OrderTrackingConfig, OrderSnapshot, ExceptionResult,
)
from .hive_signal import HiveSignal, HiveSignalBus, HiveSignalType

try:
    from ..conformal_prediction.conformal_decision import get_cdt_registry
    _CDT_AVAILABLE = True
except ImportError:
    _CDT_AVAILABLE = False

logger = logging.getLogger(__name__)


class OrderType(Enum):
    """Type of order being tracked"""
    PURCHASE_ORDER = "purchase_order"  # Inbound from supplier
    TRANSFER_ORDER = "transfer_order"  # Internal transfer
    CUSTOMER_ORDER = "customer_order"  # Outbound to customer
    PRODUCTION_ORDER = "production_order"  # Manufacturing


class OrderStatus(Enum):
    """Current status of order"""
    CREATED = "created"
    CONFIRMED = "confirmed"
    IN_TRANSIT = "in_transit"
    PARTIALLY_RECEIVED = "partially_received"
    RECEIVED = "received"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ExceptionType(Enum):
    """Type of order exception"""
    LATE_DELIVERY = "late_delivery"  # Behind schedule
    EARLY_DELIVERY = "early_delivery"  # Ahead of schedule (capacity issue)
    QUANTITY_SHORTAGE = "quantity_shortage"  # Less than ordered
    QUANTITY_OVERAGE = "quantity_overage"  # More than ordered
    QUALITY_ISSUE = "quality_issue"  # Quality rejection
    MISSING_CONFIRMATION = "missing_confirmation"  # No acknowledgment
    STUCK_IN_TRANSIT = "stuck_in_transit"  # Not moving
    PRICE_VARIANCE = "price_variance"  # Price different than expected
    NO_EXCEPTION = "no_exception"  # Normal status


class RecommendedAction(Enum):
    """Recommended action for exception"""
    NO_ACTION = "no_action"  # Continue monitoring
    EXPEDITE = "expedite"  # Request faster delivery
    DELAY_ACCEPTANCE = "delay_acceptance"  # Defer receipt
    PARTIAL_RECEIPT = "partial_receipt"  # Accept what's available
    FIND_ALTERNATE = "find_alternate"  # Source from elsewhere
    CANCEL_REORDER = "cancel_reorder"  # Cancel and reorder
    QUALITY_INSPECTION = "quality_inspection"  # Inspect before accepting
    PRICE_NEGOTIATION = "price_negotiation"  # Negotiate pricing
    ESCALATE = "escalate"  # Human review needed


class ExceptionSeverity(Enum):
    """Severity of the exception"""
    INFO = "info"  # FYI only
    WARNING = "warning"  # Monitor closely
    HIGH = "high"  # Action needed soon
    CRITICAL = "critical"  # Immediate action required


@dataclass
class OrderState:
    """Current state of an order"""
    order_id: str
    order_type: OrderType
    status: OrderStatus

    # Key dates
    created_date: str
    expected_date: str
    actual_date: Optional[str] = None

    # Quantities
    ordered_qty: float = 0.0
    received_qty: float = 0.0
    remaining_qty: float = 0.0

    # Pricing
    expected_unit_price: float = 0.0
    actual_unit_price: float = 0.0

    # Product and location
    product_id: str = ""
    from_location: str = ""
    to_location: str = ""

    # Supplier/customer
    partner_id: str = ""
    partner_name: str = ""

    # Historical context
    partner_on_time_rate: float = 0.95
    partner_fill_rate: float = 0.98
    typical_transit_days: float = 5.0

    @property
    def days_until_expected(self) -> float:
        """Days until expected delivery"""
        try:
            expected = datetime.strptime(self.expected_date, "%Y-%m-%d")
            return (expected - datetime.now()).days
        except Exception:
            return 0.0

    @property
    def days_since_created(self) -> float:
        """Days since order creation"""
        try:
            created = datetime.strptime(self.created_date, "%Y-%m-%d")
            return (datetime.now() - created).days
        except Exception:
            return 0.0

    @property
    def fill_rate(self) -> float:
        """Current fill rate"""
        if self.ordered_qty <= 0:
            return 1.0
        return self.received_qty / self.ordered_qty

    @property
    def price_variance_pct(self) -> float:
        """Price variance as percentage"""
        if self.expected_unit_price <= 0:
            return 0.0
        return (self.actual_unit_price - self.expected_unit_price) / self.expected_unit_price

    def to_features(self) -> np.ndarray:
        """Convert to feature vector for TRM"""
        return np.array([
            float(self.order_type.value == "purchase_order"),
            float(self.order_type.value == "transfer_order"),
            float(self.order_type.value == "customer_order"),
            float(self.status.value == "in_transit"),
            float(self.status.value == "partially_received"),
            self.days_until_expected,
            self.days_since_created,
            self.ordered_qty,
            self.received_qty,
            self.remaining_qty,
            self.fill_rate,
            self.price_variance_pct,
            self.partner_on_time_rate,
            self.partner_fill_rate,
            self.typical_transit_days,
        ], dtype=np.float32)


@dataclass
class ExceptionDetection:
    """Result of exception detection"""
    order_id: str
    exception_type: ExceptionType
    severity: ExceptionSeverity
    recommended_action: RecommendedAction

    # Details
    description: str
    impact_assessment: str
    estimated_impact_cost: float = 0.0

    # Confidence
    confidence: float = 1.0

    # Context-aware explanation (populated when explainer is available)
    context_explanation: Optional[Dict] = None
    risk_bound: Optional[float] = None
    risk_assessment: Optional[Dict] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "order_id": self.order_id,
            "exception_type": self.exception_type.value,
            "severity": self.severity.value,
            "recommended_action": self.recommended_action.value,
            "description": self.description,
            "impact_assessment": self.impact_assessment,
            "estimated_impact_cost": self.estimated_impact_cost,
            "confidence": self.confidence,
        }
        if self.context_explanation:
            result["context_explanation"] = self.context_explanation
        if self.risk_bound is not None:
            result["risk_bound"] = self.risk_bound
        return result


class OrderTrackingTRM:
    """
    TRM-based service for order exception detection.

    Makes narrow decisions about whether an order is exceptional
    and what action to take.

    Architecture:
    - tGNN provides: partner reliability scores, network context
    - TRM decides: exception detection and recommended actions
    """

    def __init__(
        self,
        trm_model: Optional[Any] = None,
        use_heuristic_fallback: bool = True,
        late_threshold_days: float = 2.0,
        early_threshold_days: float = 3.0,
        quantity_variance_threshold: float = 0.05,
        price_variance_threshold: float = 0.10,
        db: Optional[Any] = None,
        config_id: Optional[int] = None,
    ):
        """
        Initialize Order Tracking TRM.

        Args:
            trm_model: Trained TRM model (optional)
            use_heuristic_fallback: Use heuristic if TRM unavailable
            late_threshold_days: Days late before flagging
            early_threshold_days: Days early before flagging
            quantity_variance_threshold: Quantity variance threshold (5%)
            price_variance_threshold: Price variance threshold (10%)
            db: Optional SQLAlchemy Session for persisting decisions
            config_id: Optional config_id for DB persistence
        """
        self._engine = OrderTrackingEngine(OrderTrackingConfig(
            late_threshold_days=late_threshold_days,
            early_threshold_days=early_threshold_days,
            quantity_variance_threshold=quantity_variance_threshold,
            price_variance_threshold=price_variance_threshold,
        ))
        self.trm_model = trm_model
        self.use_heuristic_fallback = use_heuristic_fallback
        self.late_threshold_days = late_threshold_days
        self.early_threshold_days = early_threshold_days
        self.quantity_variance_threshold = quantity_variance_threshold
        self.price_variance_threshold = price_variance_threshold
        self.db = db
        self.config_id = config_id
        self.signal_bus: Optional[HiveSignalBus] = None  # Set by SiteAgent

        # Context-aware explainer (set externally by SiteAgent or caller)
        self.ctx_explainer = None

        # Conformal Decision Theory wrapper for risk bounds
        self._cdt_wrapper = None
        if _CDT_AVAILABLE:
            try:
                self._cdt_wrapper = get_cdt_registry().get_or_create("order_tracking")
            except Exception:
                pass

        # Decision history for training
        self._decision_history: List[Dict[str, Any]] = []

    def evaluate_order(
        self,
        order_state: OrderState,
        inventory_context: Optional[Dict[str, float]] = None
    ) -> ExceptionDetection:
        """
        Evaluate an order for exceptions.

        Args:
            order_state: Current state of the order
            inventory_context: Current inventory context at destination

        Returns:
            ExceptionDetection with type, severity, and recommended action
        """
        # Read hive signals before decision
        self._read_signals_before_decision()

        if self.trm_model is not None:
            result = self._trm_evaluate(order_state, inventory_context)
        elif self.use_heuristic_fallback:
            result = self._heuristic_evaluate(order_state, inventory_context)
        else:
            result = ExceptionDetection(
                order_id=order_state.order_id,
                exception_type=ExceptionType.NO_EXCEPTION,
                severity=ExceptionSeverity.INFO,
                recommended_action=RecommendedAction.NO_ACTION,
                description="No evaluation available",
                impact_assessment="Unknown",
            )

        # Enrich with context-aware reasoning
        if self.ctx_explainer is not None:
            try:
                summary = (
                    f"{result.exception_type.value}: {result.recommended_action.value} "
                    f"for order {order_state.order_id}"
                )
                ctx = self.ctx_explainer.generate_inline_explanation(
                    decision_summary=summary,
                    confidence=result.confidence,
                    trm_confidence=result.confidence if self.trm_model else None,
                    decision_category='supply_plan',
                    decision_value=result.estimated_impact_cost,
                )
                result.description = ctx.explanation
                result.context_explanation = ctx.to_dict()
            except Exception as e:
                logger.debug(f"Context enrichment failed: {e}")

        # Compute CDT risk bound
        if self._cdt_wrapper is not None and self._cdt_wrapper.is_calibrated:
            try:
                risk = self._cdt_wrapper.compute_risk_bound(result.estimated_impact_cost)
                result.risk_bound = risk.risk_bound
                result.risk_assessment = risk.to_dict()
            except Exception:
                pass

        # Emit signals after decision
        self._emit_signals_after_decision(order_state, result)

        # Record for training
        self._record_evaluation(order_state, result)

        return result

    def evaluate_orders_batch(
        self,
        orders: List[OrderState],
        inventory_contexts: Optional[Dict[str, Dict[str, float]]] = None
    ) -> List[ExceptionDetection]:
        """
        Evaluate multiple orders for exceptions.

        Args:
            orders: List of order states
            inventory_contexts: Map of location_id -> inventory context

        Returns:
            List of exception detections
        """
        results = []
        for order in orders:
            inv_ctx = None
            if inventory_contexts:
                inv_ctx = inventory_contexts.get(order.to_location)
            results.append(self.evaluate_order(order, inv_ctx))

        return results

    def _trm_evaluate(
        self,
        order_state: OrderState,
        inventory_context: Optional[Dict[str, float]]
    ) -> ExceptionDetection:
        """Evaluate using TRM model"""
        try:
            features = order_state.to_features()

            # TRM outputs dict: exception_logits, severity_logits, action_logits, confidence, value
            output = self.trm_model.predict(features.reshape(1, -1))

            exception_idx = int(np.argmax(output["exception_logits"][0]))
            exception_type = list(ExceptionType)[exception_idx]

            severity_idx = int(np.argmax(output["severity_logits"][0]))
            severity = list(ExceptionSeverity)[severity_idx]

            action_idx = int(np.argmax(output["action_logits"][0]))
            recommended_action = list(RecommendedAction)[action_idx]

            confidence = float(np.clip(output["confidence"][0, 0], 0, 1))

            description, impact = self._build_description(
                order_state, exception_type, severity
            )

            return ExceptionDetection(
                order_id=order_state.order_id,
                exception_type=exception_type,
                severity=severity,
                recommended_action=recommended_action,
                description=description,
                impact_assessment=impact,
                confidence=confidence,
            )

        except Exception as e:
            logger.warning(f"TRM evaluation failed: {e}")
            return self._heuristic_evaluate(order_state, inventory_context)

    def _heuristic_evaluate(
        self,
        order_state: OrderState,
        inventory_context: Optional[Dict[str, float]]
    ) -> ExceptionDetection:
        """Evaluate using deterministic engine rules"""
        # Delegate to the deterministic OrderTrackingEngine
        snapshot = OrderSnapshot(
            order_id=order_state.order_id,
            order_type=order_state.order_type.value,
            status=order_state.status.value,
            days_until_expected=order_state.days_until_expected,
            days_since_created=order_state.days_since_created,
            typical_transit_days=order_state.typical_transit_days,
            ordered_qty=order_state.ordered_qty,
            received_qty=order_state.received_qty,
            expected_unit_price=order_state.expected_unit_price,
            actual_unit_price=order_state.actual_unit_price,
            partner_on_time_rate=order_state.partner_on_time_rate,
            partner_fill_rate=order_state.partner_fill_rate,
        )
        engine_result = self._engine.evaluate_order(snapshot)

        # Map engine string results back to TRM enums
        exception_type_map = {v.value: v for v in ExceptionType}
        severity_map = {v.value: v for v in ExceptionSeverity}
        action_map = {v.value: v for v in RecommendedAction}

        exception_type = exception_type_map.get(engine_result.exception_type, ExceptionType.NO_EXCEPTION)
        severity = severity_map.get(engine_result.severity, ExceptionSeverity.INFO)
        recommended_action = action_map.get(engine_result.recommended_action, RecommendedAction.NO_ACTION)

        return ExceptionDetection(
            order_id=order_state.order_id,
            exception_type=exception_type,
            severity=severity,
            recommended_action=recommended_action,
            description=engine_result.description,
            impact_assessment=engine_result.impact_assessment,
            confidence=0.9,  # Heuristic confidence
        )

    def _build_description(
        self,
        order_state: OrderState,
        exception_type: ExceptionType,
        severity: ExceptionSeverity
    ) -> tuple[str, str]:
        """Build description and impact assessment"""

        if exception_type == ExceptionType.NO_EXCEPTION:
            return "Order progressing normally", "No impact expected"

        descriptions = {
            ExceptionType.LATE_DELIVERY: f"Order is {-order_state.days_until_expected:.0f} days late",
            ExceptionType.EARLY_DELIVERY: f"Order arriving {order_state.days_until_expected:.0f} days early",
            ExceptionType.QUANTITY_SHORTAGE: f"Received {order_state.fill_rate*100:.0f}% of ordered quantity",
            ExceptionType.QUANTITY_OVERAGE: f"Received more than ordered ({order_state.fill_rate*100:.0f}%)",
            ExceptionType.QUALITY_ISSUE: "Quality issues reported with order",
            ExceptionType.MISSING_CONFIRMATION: f"No confirmation after {order_state.days_since_created:.0f} days",
            ExceptionType.STUCK_IN_TRANSIT: f"Order in transit for {order_state.days_since_created:.0f} days (expected {order_state.typical_transit_days:.0f})",
            ExceptionType.PRICE_VARIANCE: f"Price variance of {order_state.price_variance_pct*100:.1f}%",
        }

        impacts = {
            ExceptionSeverity.INFO: "Minimal impact expected",
            ExceptionSeverity.WARNING: "Monitor for potential service impact",
            ExceptionSeverity.HIGH: "Service level at risk without action",
            ExceptionSeverity.CRITICAL: "Immediate stockout risk or significant cost impact",
        }

        description = descriptions.get(exception_type, str(exception_type.value))
        impact = impacts.get(severity, "Unknown impact")

        return description, impact

    def get_critical_exceptions(
        self,
        orders: List[OrderState]
    ) -> List[ExceptionDetection]:
        """Get only critical and high severity exceptions"""
        results = self.evaluate_orders_batch(orders)
        return [r for r in results if r.severity in [ExceptionSeverity.CRITICAL, ExceptionSeverity.HIGH]]

    def _record_evaluation(
        self,
        order_state: OrderState,
        result: ExceptionDetection
    ):
        """Record evaluation for TRM training"""
        record = {
            "order_state": {
                "order_id": order_state.order_id,
                "order_type": order_state.order_type.value,
                "status": order_state.status.value,
                "days_until_expected": order_state.days_until_expected,
                "fill_rate": order_state.fill_rate,
            },
            "state_features": order_state.to_features().tolist(),
            "result": result.to_dict(),
            "timestamp": datetime.now().isoformat(),
        }

        self._decision_history.append(record)

        if len(self._decision_history) > 10000:
            self._decision_history = self._decision_history[-10000:]

        # Persist to DB if session available
        self._persist_evaluation(order_state, result)

    def _persist_evaluation(
        self,
        order_state: OrderState,
        result: ExceptionDetection
    ):
        """Persist evaluation to powell_order_exceptions table."""
        if self.db is None or self.config_id is None:
            return
        try:
            from app.models.powell_decisions import PowellOrderException
            from app.services.powell.decision_reasoning import order_tracking_reasoning
            row = PowellOrderException(
                config_id=self.config_id,
                order_id=order_state.order_id,
                order_type=order_state.order_type.value,
                order_status=order_state.status.value,
                exception_type=result.exception_type.value,
                severity=result.severity.value,
                recommended_action=result.recommended_action.value,
                description=result.description,
                impact_assessment=result.impact_assessment,
                estimated_impact_cost=result.estimated_impact_cost,
                confidence=result.confidence,
                state_features=order_state.to_features().tolist(),
                decision_reasoning=order_tracking_reasoning(
                    order_id=order_state.order_id,
                    exception_type=result.exception_type.value,
                    severity=result.severity.value,
                    recommended_action=result.recommended_action.value,
                    confidence=result.confidence,
                    reason=result.description,
                ),
            )
            self.db.add(row)
        except Exception as e:
            logger.warning(f"Failed to persist order exception: {e}")

    # ---- Hive signal methods ------------------------------------------------

    def _read_signals_before_decision(self) -> None:
        """Read relevant hive signals before order evaluation."""
        if self.signal_bus is None:
            return
        try:
            signals = self.signal_bus.read(
                consumer_trm="order_tracking",
                types={
                    HiveSignalType.PO_EXPEDITE,
                    HiveSignalType.TO_DELAYED,
                    HiveSignalType.TO_RELEASED,
                },
            )
            if signals:
                logger.debug(f"OrderTracking read {len(signals)} hive signals")
        except Exception as e:
            logger.debug(f"OrderTracking signal read failed: {e}")

    def _emit_signals_after_decision(
        self, order_state: OrderState, result: ExceptionDetection
    ) -> None:
        """Emit hive signals after order tracking evaluation."""
        if self.signal_bus is None:
            return
        if result.exception_type == ExceptionType.NO_EXCEPTION:
            return
        try:
            severity_urgency = {
                ExceptionSeverity.CRITICAL: 0.9,
                ExceptionSeverity.HIGH: 0.7,
                ExceptionSeverity.WARNING: 0.4,
                ExceptionSeverity.INFO: 0.1,
            }
            urgency = severity_urgency.get(result.severity, 0.3)
            self.signal_bus.emit(HiveSignal(
                source_trm="order_tracking",
                signal_type=HiveSignalType.ORDER_EXCEPTION,
                urgency=urgency,
                direction="risk",
                magnitude=order_state.remaining_qty,
                product_id=order_state.product_id,
                payload={
                    "order_id": order_state.order_id,
                    "exception_type": result.exception_type.value,
                    "severity": result.severity.value,
                    "recommended_action": result.recommended_action.value,
                },
            ))
            self.signal_bus.urgency.update("order_tracking", urgency, "risk")
        except Exception as e:
            logger.debug(f"OrderTracking signal emit failed: {e}")

    def record_outcome(
        self,
        detection: ExceptionDetection,
        action_taken: RecommendedAction,
        actual_outcome: Optional[Dict[str, Any]] = None
    ):
        """
        Record actual outcome for TRM training feedback.

        Args:
            detection: The exception detection
            action_taken: What action was actually taken
            actual_outcome: What actually happened
        """
        record = {
            "detection": detection.to_dict(),
            "action_taken": action_taken.value,
            "actual_outcome": actual_outcome,
            "timestamp": datetime.now().isoformat(),
        }
        self._decision_history.append(record)

    def get_training_data(self) -> List[Dict[str, Any]]:
        """Get decision history for TRM training"""
        return self._decision_history
