"""
SiteAgent - Unified Execution Orchestrator

The SiteAgent is the execution-level orchestrator that combines:
- Deterministic engines (MRP, AATP, Safety Stock)
- Learned TRM heads (exception handling, adjustments)
- CDC monitoring (event-driven replanning)

Each site in the supply chain network has a SiteAgent responsible
for all execution decisions at that location.

Key Principles:
1. Engines are deterministic - auditable, testable, no surprises
2. TRM heads learn exceptions only - bounded adjustments
3. Engines can run without TRM - graceful degradation
4. CDC monitor triggers out-of-cadence replanning
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
import torch
import logging

from .engines import (
    MRPEngine, MRPConfig, GrossRequirement, PlannedOrder,
    AATPEngine, AATPConfig, Order, ATPResult, Priority,
    SafetyStockCalculator, SafetyStockConfig, SSPolicy, DemandStats
)
from .cdc_monitor import CDCMonitor, CDCConfig, SiteMetrics, TriggerEvent, ReplanAction
from .site_agent_model import SiteAgentModel, SiteAgentModelConfig
from .hive_signal import HiveSignal, HiveSignalBus, HiveSignalType
from .hive_health import HiveHealthMetrics
from .inter_hive_signal import (
    InterHiveSignal, InterHiveSignalType, tGNNSiteDirective,
)
from .decision_cycle import (
    DecisionCyclePhase, CycleResult, PhaseResult, TRM_PHASE_MAP,
    PHASE_TRM_MAP, detect_conflicts,
)
from app.services.agent_context_explainer import AgentContextExplainer, AgentType

logger = logging.getLogger(__name__)


@dataclass
class SiteAgentConfig:
    """Configuration for SiteAgent"""
    site_key: str

    # Engine configs
    mrp_config: MRPConfig = field(default_factory=MRPConfig)
    aatp_config: AATPConfig = field(default_factory=AATPConfig)
    ss_config: SafetyStockConfig = field(default_factory=SafetyStockConfig)

    # Model config
    model_config: SiteAgentModelConfig = field(default_factory=SiteAgentModelConfig)

    # CDC config
    cdc_config: CDCConfig = field(default_factory=CDCConfig)

    # Operational settings
    use_trm_adjustments: bool = True  # If False, use engines only
    trm_confidence_threshold: float = 0.7  # Min confidence to apply TRM suggestions
    agent_mode: str = "copilot"  # "autonomous" or "copilot"

    # Model checkpoint
    model_checkpoint_path: Optional[str] = None

    # Hive signal coordination
    enable_hive_signals: bool = True  # Enable stigmergic coordination


@dataclass
class ATPResponse:
    """Response from ATP decision"""
    order_id: str
    promised_qty: float
    promise_date: Any  # date
    source: str  # "deterministic", "trm_adjusted", "exception"
    confidence: float = 1.0
    explanation: str = ""
    signal_context: Optional[Dict[str, Any]] = None  # Hive signal snapshot at decision time


@dataclass
class PORecommendation:
    """PO recommendation from replenishment planning"""
    item_id: str
    order_date: Any  # date
    receipt_date: Any  # date
    quantity: float
    order_type: str
    expedite: bool = False
    confidence: float = 1.0
    source: str = "deterministic"


class SiteAgent:
    """
    Unified execution agent for a supply chain site.

    Orchestrates deterministic engines with learned TRM adjustments.
    """

    def __init__(
        self,
        config: SiteAgentConfig,
        db_session: Optional[Any] = None
    ):
        self.config = config
        self.site_key = config.site_key
        self.db = db_session

        # Initialize deterministic engines (100% code)
        self.mrp_engine = MRPEngine(config.site_key, config.mrp_config)
        self.aatp_engine = AATPEngine(config.site_key, config.aatp_config)
        self.ss_calculator = SafetyStockCalculator(config.site_key, config.ss_config)

        # Initialize TRM model (learned)
        self.model: Optional[SiteAgentModel] = None
        if config.use_trm_adjustments:
            self._load_model()

        # Initialize CDC monitor
        self.cdc_monitor = CDCMonitor(config.site_key, config.cdc_config)

        # Initialize context-aware explainers for each TRM type
        self._explainers: Dict[str, AgentContextExplainer] = {}
        for agent_type in [
            AgentType.TRM_ATP, AgentType.TRM_PO, AgentType.TRM_REBALANCE,
            AgentType.TRM_ORDER_TRACKING, AgentType.TRM_MO_EXECUTION,
            AgentType.TRM_TO_EXECUTION, AgentType.TRM_QUALITY,
            AgentType.TRM_MAINTENANCE, AgentType.TRM_SUBCONTRACTING,
            AgentType.TRM_FORECAST_ADJUSTMENT, AgentType.TRM_SAFETY_STOCK,
        ]:
            self._explainers[agent_type.value] = AgentContextExplainer(agent_type)

        # Hive signal bus for stigmergic TRM coordination
        self.signal_bus: Optional[HiveSignalBus] = None
        if config.enable_hive_signals:
            self.signal_bus = HiveSignalBus()

        # Registered TRM instances (for signal_bus wiring)
        self._registered_trms: Dict[str, Any] = {}

        # State cache
        self._state_cache: Optional[torch.Tensor] = None
        self._state_cache_time: Optional[datetime] = None

        logger.info(f"SiteAgent initialized for {config.site_key}"
                     f"{' [hive signals ON]' if self.signal_bus else ''}")

    def get_explainer(self, agent_type: str) -> Optional[AgentContextExplainer]:
        """Get the context-aware explainer for a specific agent type."""
        return self._explainers.get(agent_type)

    def connect_trm(self, trm_name: str, trm_instance: Any) -> None:
        """Register a TRM instance and wire the shared signal bus to it.

        Any object with a ``signal_bus`` attribute will receive the SiteAgent's
        bus, enabling stigmergic coordination between TRM workers within this
        hive.

        Args:
            trm_name: Canonical TRM name (e.g. "atp_executor", "po_creation").
            trm_instance: The TRM object. Must have a ``signal_bus`` attribute.
        """
        self._registered_trms[trm_name] = trm_instance
        if self.signal_bus is not None and hasattr(trm_instance, "signal_bus"):
            trm_instance.signal_bus = self.signal_bus
            logger.debug(f"Wired signal_bus to TRM {trm_name}")

    def connect_trms(self, **trms: Any) -> None:
        """Bulk-register TRM instances and wire the signal bus.

        Example::

            site_agent.connect_trms(
                atp_executor=atp_trm,
                po_creation=po_trm,
                safety_stock=ss_trm,
            )
        """
        for name, instance in trms.items():
            self.connect_trm(name, instance)
        if trms:
            logger.info(
                f"Connected {len(trms)} TRMs to SiteAgent {self.site_key}: "
                f"{list(trms.keys())}"
            )

    def _load_model(self):
        """Load TRM model from checkpoint with fallback resolution."""
        checkpoint_path = self.config.model_checkpoint_path

        # If no explicit path, try the fallback chain
        if not checkpoint_path:
            try:
                from .trm_site_trainer import find_best_checkpoint
                # Extract site_id from site_key (format: "site_42" or just an int string)
                site_id_str = self.config.site_key.replace("site_", "")
                site_id = int(site_id_str) if site_id_str.isdigit() else 0
                checkpoint_path = find_best_checkpoint(
                    trm_type="atp_executor",  # Primary TRM for SiteAgent
                    site_id=site_id,
                    master_type="INVENTORY",
                )
            except Exception:
                pass

        if checkpoint_path:
            try:
                # SiteAgentModelConfig is stored in our checkpoints; allowlist it
                # so torch.load(weights_only=True) can deserialize it safely.
                torch.serialization.add_safe_globals([SiteAgentModelConfig])
                checkpoint = torch.load(
                    checkpoint_path,
                    map_location=self.config.model_config.device,
                )
                self.model = SiteAgentModel(checkpoint.get('model_config', self.config.model_config))
                self.model.load_state_dict(checkpoint['model_state_dict'])
                self.model.eval()
                logger.info(f"Loaded TRM model from {checkpoint_path}")
            except Exception as e:
                logger.warning(f"Failed to load TRM model: {e}. Running without TRM.")
                self.model = None
        else:
            # Initialize fresh model
            self.model = SiteAgentModel(self.config.model_config)
            self.model.eval()

    async def execute_atp(self, order: Order) -> ATPResponse:
        """
        Execute ATP decision for incoming order.

        Flow:
        1. Read hive signals (quality holds, rebalance inbound, etc.)
        2. AATPEngine computes deterministic availability
        3. If shortage, ATPExceptionHead suggests resolution
        4. Emit hive signals (shortage, demand surge/drop)
        5. Return combined decision
        """
        # Step 0: Read relevant hive signals before decision
        signal_context = self._read_atp_signals()

        # Capture hive signal snapshot for decision audit
        hive_snapshot = self._build_signal_context()

        # Step 1: Deterministic AATP
        base_result = self.aatp_engine.check_availability(order)

        if base_result.can_fulfill_full:
            # Happy path - no TRM needed
            self.aatp_engine.commit_consumption(order, base_result)

            return ATPResponse(
                order_id=order.order_id,
                promised_qty=order.requested_qty,
                promise_date=base_result.available_date,
                source="deterministic",
                confidence=1.0,
                explanation="Full availability in allocation tier",
                signal_context=hive_snapshot or None,
            )

        # Step 2: Shortage detected — emit signal
        self._emit_atp_shortage_signal(order, base_result)

        # Step 2b: Check if TRM is available
        if not self.config.use_trm_adjustments or self.model is None:
            # No TRM - return deterministic result
            if base_result.available_qty > 0:
                self.aatp_engine.commit_consumption(order, base_result)

            return ATPResponse(
                order_id=order.order_id,
                promised_qty=base_result.available_qty,
                promise_date=base_result.available_date,
                source="deterministic",
                confidence=1.0,
                explanation=f"Shortage: {base_result.shortage_qty:.0f} units unavailable"
            )

        # Step 3: Invoke TRM exception head
        try:
            state = await self._encode_state()
            order_context = self._order_to_tensor(order)
            shortage_tensor = torch.tensor([[base_result.shortage_qty]], dtype=torch.float32)

            with torch.no_grad():
                exception_decision = self.model.forward_atp_exception(
                    state_embedding=state,
                    order_context=order_context,
                    shortage_qty=shortage_tensor
                )

            return self._apply_atp_exception(order, base_result, exception_decision)

        except Exception as e:
            logger.error(f"TRM exception handling failed: {e}")
            # Fallback to deterministic
            if base_result.available_qty > 0:
                self.aatp_engine.commit_consumption(order, base_result)

            return ATPResponse(
                order_id=order.order_id,
                promised_qty=base_result.available_qty,
                promise_date=base_result.available_date,
                source="deterministic",
                confidence=1.0,
                explanation=f"TRM error, fallback to deterministic"
            )

    def _apply_atp_exception(
        self,
        order: Order,
        base_result: ATPResult,
        decision: Dict[str, torch.Tensor]
    ) -> ATPResponse:
        """Apply TRM exception decision with bounds checking"""

        action_probs = decision['action_probs'][0]  # [4]
        fill_rate = decision['fill_rate'][0, 0].item()  # scalar
        confidence = decision['confidence'][0, 0].item()  # scalar

        # Action mapping: 0=partial, 1=substitute, 2=split, 3=reject
        action_idx = action_probs.argmax().item()
        actions = ['partial', 'substitute', 'split', 'reject']
        action = actions[action_idx]

        # Check confidence threshold
        if confidence < self.config.trm_confidence_threshold:
            # Low confidence - fall back to deterministic partial fill
            if base_result.available_qty > 0:
                self.aatp_engine.commit_consumption(order, base_result)

            return ATPResponse(
                order_id=order.order_id,
                promised_qty=base_result.available_qty,
                promise_date=base_result.available_date,
                source="deterministic",
                confidence=confidence,
                explanation=f"TRM confidence {confidence:.2f} below threshold"
            )

        if action == 'partial':
            # Use suggested fill rate, bounded
            promised_qty = min(
                order.requested_qty * fill_rate,
                base_result.available_qty
            )
            if promised_qty > 0:
                # Create modified result for consumption
                modified_result = ATPResult(
                    order_id=order.order_id,
                    can_fulfill_full=False,
                    available_qty=promised_qty,
                    shortage_qty=order.requested_qty - promised_qty,
                    available_date=base_result.available_date,
                    consumption_detail=base_result.consumption_detail  # Will be adjusted
                )
                # Note: actual consumption would need to be recalculated

            return ATPResponse(
                order_id=order.order_id,
                promised_qty=promised_qty,
                promise_date=base_result.available_date,
                source="trm_adjusted",
                confidence=confidence,
                explanation=f"TRM suggested partial fill at {fill_rate:.1%}"
            )

        elif action == 'reject':
            return ATPResponse(
                order_id=order.order_id,
                promised_qty=0,
                promise_date=base_result.available_date,
                source="trm_adjusted",
                confidence=confidence,
                explanation="TRM recommended rejection"
            )

        else:
            # substitute/split - would need additional logic
            # For now, fall back to partial
            if base_result.available_qty > 0:
                self.aatp_engine.commit_consumption(order, base_result)

            return ATPResponse(
                order_id=order.order_id,
                promised_qty=base_result.available_qty,
                promise_date=base_result.available_date,
                source="trm_adjusted",
                confidence=confidence,
                explanation=f"TRM suggested {action}, using available qty"
            )

    async def execute_replenishment(
        self,
        gross_requirements: List[GrossRequirement],
        on_hand_inventory: Dict[str, float],
        scheduled_receipts: Dict[str, List],
        bom: Dict[str, List],
        lead_times: Dict[str, int]
    ) -> List[PORecommendation]:
        """
        Execute replenishment planning for the site.

        Flow:
        1. MRPEngine computes net requirements
        2. SafetyStockCalculator provides targets
        3. POTimingHead adjusts timing/expedite decisions
        """
        # Step 1: Deterministic MRP
        net_requirements, planned_orders = self.mrp_engine.compute_net_requirements(
            gross_requirements=gross_requirements,
            on_hand_inventory=on_hand_inventory,
            scheduled_receipts=scheduled_receipts,
            bom=bom,
            lead_times=lead_times
        )

        # Step 2: Convert to PO recommendations
        recommendations = []

        for po in planned_orders:
            rec = PORecommendation(
                item_id=po.item_id,
                order_date=po.order_date,
                receipt_date=po.receipt_date,
                quantity=po.quantity,
                order_type=po.order_type,
                expedite=False,
                confidence=1.0,
                source="deterministic"
            )

            # Step 3: TRM timing adjustments (if enabled)
            if self.config.use_trm_adjustments and self.model is not None:
                try:
                    state = await self._encode_state()
                    po_context = self._po_to_tensor(po)

                    with torch.no_grad():
                        timing_adj = self.model.forward_po_timing(
                            state_embedding=state,
                            po_context=po_context
                        )

                    rec = self._apply_timing_adjustment(rec, timing_adj)

                except Exception as e:
                    logger.warning(f"TRM timing adjustment failed: {e}")

            recommendations.append(rec)

        return recommendations

    def _apply_timing_adjustment(
        self,
        rec: PORecommendation,
        decision: Dict[str, torch.Tensor]
    ) -> PORecommendation:
        """Apply TRM timing decision with bounds checking"""

        timing_probs = decision['timing_probs'][0]  # [3]
        expedite_prob = decision['expedite_prob'][0, 0].item()
        days_offset = decision['days_offset'][0, 0].item()
        confidence = decision['confidence'][0, 0].item()

        if confidence < self.config.trm_confidence_threshold:
            return rec

        # Action: 0=now, 1=wait, 2=split
        action_idx = timing_probs.argmax().item()

        from datetime import timedelta

        if action_idx == 1:  # wait
            # Apply days offset (bounded to ±7)
            days_offset = max(-7, min(7, int(days_offset)))
            rec.order_date = rec.order_date + timedelta(days=days_offset)
            rec.source = "trm_adjusted"

        rec.expedite = expedite_prob > 0.5
        rec.confidence = confidence

        return rec

    async def get_inventory_adjustments(self) -> Dict[str, float]:
        """
        Get inventory parameter adjustments from TRM.

        Returns dict with:
        - ss_multiplier: Safety stock adjustment
        - rop_multiplier: Reorder point adjustment
        """
        if not self.config.use_trm_adjustments or self.model is None:
            return {'ss_multiplier': 1.0, 'rop_multiplier': 1.0}

        try:
            state = await self._encode_state()

            with torch.no_grad():
                inv_output = self.model.forward_inventory_planning(state)

            return {
                'ss_multiplier': inv_output['ss_multiplier'][0, 0].item(),
                'rop_multiplier': inv_output['rop_multiplier'][0, 0].item(),
                'confidence': inv_output['confidence'][0, 0].item()
            }

        except Exception as e:
            logger.error(f"Inventory adjustment failed: {e}")
            return {'ss_multiplier': 1.0, 'rop_multiplier': 1.0, 'confidence': 0.0}

    async def check_cdc_trigger(self, metrics: SiteMetrics) -> TriggerEvent:
        """
        Check for CDC triggers and execute appropriate action.
        Persists trigger events to powell_cdc_trigger_log when db is available.
        """
        trigger = await self.cdc_monitor.check_and_trigger(metrics, db=self.db)

        if trigger.triggered:
            logger.info(f"CDC trigger at {self.site_key}: {trigger.message}")

            if self.config.agent_mode == "autonomous":
                await self._handle_cdc_trigger(trigger)
            else:
                # Copilot mode - log for human review
                logger.info(f"CDC action recommended: {trigger.recommended_action.value}")

        return trigger

    async def _handle_cdc_trigger(self, trigger: TriggerEvent):
        """Handle CDC trigger in autonomous mode"""

        if trigger.recommended_action == ReplanAction.FULL_CFA:
            logger.warning(f"Full CFA triggered for {self.site_key}")
            # Evaluate and execute retraining if warranted
            if self.db:
                try:
                    from app.services.powell.cdc_retraining_service import CDCRetrainingService
                    retraining_svc = CDCRetrainingService(
                        db=self.db,
                        site_key=self.site_key,
                        group_id=0,  # Will be resolved from config
                    )
                    if retraining_svc.evaluate_retraining_need():
                        result = retraining_svc.execute_retraining(trigger_event=trigger)
                        if result and result.final_loss < float("inf"):
                            logger.info(
                                f"Retrained model for {self.site_key}: "
                                f"loss={result.final_loss:.4f}"
                            )
                except Exception as e:
                    logger.error(f"CDC retraining failed for {self.site_key}: {e}")

        elif trigger.recommended_action == ReplanAction.TGNN_REFRESH:
            logger.info(f"Off-cadence tGNN refresh triggered for {self.site_key}")
            # Signal to tGNN layer that this site needs re-inference.
            # In production this would enqueue a tGNN job for this site.
            if self.signal_bus is not None:
                from .hive_signal import HiveSignal, HiveSignalType
                self.signal_bus.emit(HiveSignal(
                    source_trm="cdc_monitor",
                    signal_type=HiveSignalType.ALLOCATION_REFRESH,
                    urgency=0.8,
                    direction="risk",
                    magnitude=0.0,
                    payload={"reason": "signal_divergence", "site_key": self.site_key},
                ))

        elif trigger.recommended_action == ReplanAction.ALLOCATION_ONLY:
            logger.info(f"Allocation refresh triggered for {self.site_key}")
            # Would call allocation service here

        elif trigger.recommended_action == ReplanAction.PARAM_ADJUSTMENT:
            adjustments = await self.get_inventory_adjustments()
            logger.info(f"Param adjustments: {adjustments}")

    async def _encode_state(self) -> torch.Tensor:
        """
        Encode current site state.

        Uses cache if recent enough (within 5 minutes).
        """
        # Check cache
        now = datetime.utcnow()
        if (self._state_cache is not None and
            self._state_cache_time is not None and
            (now - self._state_cache_time).seconds < 300):
            return self._state_cache

        # Gather state from database/APIs (includes urgency_vector when signals enabled)
        state_data = await self._gather_state_data()

        # Encode (urgency_vector is passed through if present)
        with torch.no_grad():
            state = self.model.encode_state(**state_data)

        # Cache
        self._state_cache = state
        self._state_cache_time = now

        return state

    async def _gather_state_data(self) -> Dict[str, torch.Tensor]:
        """Gather current state data for encoding.

        Note: The dimensions here must match the trained model's state_dim.
        state_dim = inventory(1) + pipeline(4) + backlog(1) + demand_history(12) + forecasts(8) = 26
        Plus optional urgency_vector(11) when hive signals are enabled.
        """
        # Dimensions must match training configuration
        n_products = 1  # Single aggregated product view
        history_window = 12
        forecast_horizon = 8
        lead_time_buckets = 4

        # TODO: Query actual data sources and aggregate to single product view
        # For now, return placeholder tensors with correct dimensions
        data: Dict[str, torch.Tensor] = {
            'inventory': torch.zeros(1, n_products),
            'pipeline': torch.zeros(1, n_products, lead_time_buckets),
            'backlog': torch.zeros(1, n_products),
            'demand_history': torch.zeros(1, n_products, history_window),
            'forecasts': torch.zeros(1, n_products, forecast_horizon),
        }

        # Append urgency vector from hive signal bus (11-dim)
        if self.signal_bus is not None:
            uv = self.signal_bus.urgency.values_array()
            data['urgency_vector'] = torch.tensor([uv], dtype=torch.float32)

        return data

    def _order_to_tensor(self, order: Order) -> torch.Tensor:
        """Convert order to tensor for TRM"""
        # Encode order features
        features = [
            order.requested_qty / 1000,  # Normalized
            order.priority.value / 5,  # Normalized
            1.0 if order.order_type == "rush" else 0.0,
            # ... more features
        ]
        # Pad to expected dimension
        while len(features) < self.config.model_config.order_context_dim:
            features.append(0.0)

        return torch.tensor([features], dtype=torch.float32)

    def _po_to_tensor(self, po: PlannedOrder) -> torch.Tensor:
        """Convert planned order to tensor for TRM"""
        features = [
            po.quantity / 1000,  # Normalized
            1.0 if po.order_type == "manufacture" else 0.0,
            # ... more features
        ]
        # Pad to expected dimension
        while len(features) < self.config.model_config.po_context_dim:
            features.append(0.0)

        return torch.tensor([features], dtype=torch.float32)

    # ---- Hive signal helpers ------------------------------------------------

    def _read_atp_signals(self) -> Dict[str, Any]:
        """Read signals relevant to ATP decisions. Returns empty dict if bus is None."""
        if self.signal_bus is None:
            return {}
        try:
            signals = self.signal_bus.read(
                consumer_trm="atp_executor",
                types={
                    HiveSignalType.QUALITY_REJECT,
                    HiveSignalType.QUALITY_HOLD,
                    HiveSignalType.REBALANCE_INBOUND,
                    HiveSignalType.MO_RELEASED,
                    HiveSignalType.SS_INCREASED,
                    HiveSignalType.SS_DECREASED,
                },
            )
            return {"signals": [s.to_dict() for s in signals], "count": len(signals)}
        except Exception as e:
            logger.debug(f"Signal read failed: {e}")
            return {}

    def _emit_atp_shortage_signal(self, order: Order, result: ATPResult) -> None:
        """Emit ATP_SHORTAGE signal when a shortage is detected."""
        if self.signal_bus is None:
            return
        try:
            urgency = min(1.0, result.shortage_qty / max(1.0, order.requested_qty))
            signal = HiveSignal(
                source_trm="atp_executor",
                signal_type=HiveSignalType.ATP_SHORTAGE,
                urgency=urgency,
                direction="shortage",
                magnitude=result.shortage_qty,
                product_id=order.product_id,
                payload={
                    "order_id": order.order_id,
                    "shortage_qty": result.shortage_qty,
                    "available_qty": result.available_qty,
                },
            )
            self.signal_bus.emit(signal)
            self.signal_bus.urgency.update("atp_executor", urgency, "shortage")
        except Exception as e:
            logger.debug(f"Signal emit failed: {e}")

    def _build_signal_context(self) -> Dict[str, Any]:
        """Build signal context dict for logging/training data."""
        if self.signal_bus is None:
            return {}
        try:
            return self.signal_bus.to_context_dict()
        except Exception as e:
            logger.debug(f"Signal context build failed: {e}")
            return {}

    def get_hive_health(self) -> Optional[Dict[str, Any]]:
        """Get current hive health metrics. Returns None if signals disabled."""
        if self.signal_bus is None:
            return None
        try:
            metrics = HiveHealthMetrics.from_signal_bus(
                self.signal_bus, site_key=self.site_key
            )
            return metrics.to_dict()
        except Exception as e:
            logger.debug(f"Hive health failed: {e}")
            return None

    def execute_decision_cycle(
        self,
        trm_executors: Optional[Dict[str, Any]] = None,
    ) -> CycleResult:
        """Execute a full 6-phase decision cycle with ordered TRM execution.

        Each phase runs its assigned TRMs. Signals emitted in earlier phases
        are visible to later phases within the same cycle.

        Args:
            trm_executors: Optional dict mapping TRM name → callable.
                Each callable takes no args and returns any result.
                Only TRMs present in this dict are executed.
                If None, no TRMs are executed (dry-run for testing).

        Returns:
            CycleResult with per-phase details and conflict detection.
        """
        import time

        executors = trm_executors or {}
        result = CycleResult()
        cycle_start = time.monotonic()

        for phase in DecisionCyclePhase:
            phase_start = time.monotonic()
            phase_result = PhaseResult(phase=phase)
            trm_names = PHASE_TRM_MAP.get(phase, [])
            signals_before = len(self.signal_bus) if self.signal_bus else 0

            for trm_name in trm_names:
                executor = executors.get(trm_name)
                if executor is None:
                    continue
                try:
                    executor()
                    phase_result.trms_executed.append(trm_name)
                except Exception as e:
                    phase_result.errors.append(f"{trm_name}: {e}")
                    logger.warning(f"Decision cycle phase {phase.name} TRM {trm_name} failed: {e}")

            signals_after = len(self.signal_bus) if self.signal_bus else 0
            phase_result.signals_emitted = signals_after - signals_before
            phase_result.duration_ms = (time.monotonic() - phase_start) * 1000.0
            result.phases.append(phase_result)
            result.total_signals_emitted += phase_result.signals_emitted

            # REFLECT phase: detect conflicts and update signal divergence
            if phase == DecisionCyclePhase.REFLECT and self.signal_bus:
                try:
                    snapshot = self.signal_bus.urgency.snapshot()
                    result.conflicts_detected = detect_conflicts(snapshot)
                except Exception as e:
                    logger.debug(f"Conflict detection failed: {e}")
                # Update signal divergence score for next CDC check
                try:
                    self.cdc_monitor.update_signal_divergence(
                        self.signal_bus,
                        self.get_current_directive(),
                    )
                except Exception as e:
                    logger.debug(f"Signal divergence update failed: {e}")

        result.completed_at = datetime.utcnow()
        result.total_duration_ms = (time.monotonic() - cycle_start) * 1000.0
        return result

    # Mapping from InterHiveSignalType → HiveSignalType for local bus injection.
    _INTER_TO_LOCAL: Dict[InterHiveSignalType, HiveSignalType] = {
        InterHiveSignalType.NETWORK_SHORTAGE: HiveSignalType.NETWORK_SHORTAGE,
        InterHiveSignalType.NETWORK_SURPLUS: HiveSignalType.NETWORK_SURPLUS,
        InterHiveSignalType.DEMAND_PROPAGATION: HiveSignalType.PROPAGATION_ALERT,
        InterHiveSignalType.BOTTLENECK_RISK: HiveSignalType.PROPAGATION_ALERT,
        InterHiveSignalType.CONCENTRATION_RISK: HiveSignalType.PROPAGATION_ALERT,
        InterHiveSignalType.RESILIENCE_ALERT: HiveSignalType.PROPAGATION_ALERT,
        InterHiveSignalType.ALLOCATION_REFRESH: HiveSignalType.ALLOCATION_REFRESH,
        InterHiveSignalType.PRIORITY_SHIFT: HiveSignalType.ALLOCATION_REFRESH,
        InterHiveSignalType.FORECAST_REVISION: HiveSignalType.PROPAGATION_ALERT,
        InterHiveSignalType.POLICY_PARAMETER_UPDATE: HiveSignalType.PROPAGATION_ALERT,
    }

    def apply_directive(self, directive: tGNNSiteDirective) -> Dict[str, Any]:
        """Apply a tGNNSiteDirective to this hive.

        Performs three actions:
        1. Injects inter-hive signals into the local signal bus
        2. Stores the directive so individual TRMs can read it
        3. Pushes network params to TRMs that implement ``apply_network_context``

        Args:
            directive: A tGNNSiteDirective from the tGNN layer.

        Returns:
            Summary of actions taken.
        """
        summary: Dict[str, Any] = {
            "site_key": self.site_key,
            "signals_injected": 0,
            "params_applied": {},
        }

        # Store directive for TRM consumption
        self._current_directive = directive

        # 1. Inject inter-hive signals into local bus
        if self.signal_bus is not None:
            for ihs in directive.inter_hive_signals:
                try:
                    local_type = self._INTER_TO_LOCAL.get(
                        ihs.signal_type, HiveSignalType.PROPAGATION_ALERT
                    )
                    local_signal = HiveSignal(
                        source_trm="tgnn_network",
                        signal_type=local_type,
                        urgency=ihs.urgency,
                        direction=ihs.direction,
                        magnitude=ihs.magnitude,
                        half_life_minutes=ihs.half_life_hours * 60.0,
                        payload={
                            "source_site": ihs.source_site,
                            "signal_type": ihs.signal_type.value,
                            "from_tgnn": True,
                        },
                    )
                    self.signal_bus.emit(local_signal)
                    summary["signals_injected"] += 1
                except Exception as e:
                    logger.debug(f"Failed to inject inter-hive signal: {e}")

        # 2. Collect S&OP parameters from directive
        params: Dict[str, Any] = {}
        for attr in (
            "safety_stock_multiplier", "criticality_score", "bottleneck_risk",
            "resilience_score", "demand_forecast", "exception_probability",
        ):
            val = getattr(directive, attr, None)
            if val is not None:
                params[attr] = val
        summary["params_applied"] = params

        # 3. Push directive params to registered TRMs that can consume them
        for trm_name, trm_instance in self._registered_trms.items():
            if hasattr(trm_instance, "apply_network_context"):
                try:
                    trm_instance.apply_network_context(params)
                except Exception as e:
                    logger.debug(f"TRM {trm_name} rejected network context: {e}")

        logger.info(
            f"Applied tGNN directive to {self.site_key}: "
            f"{summary['signals_injected']} signals, "
            f"{len(params)} params"
        )
        return summary

    def get_current_directive(self) -> Optional[tGNNSiteDirective]:
        """Return the most recently applied tGNNSiteDirective, or None."""
        return getattr(self, "_current_directive", None)

    def get_registered_trm(self, trm_name: str) -> Optional[Any]:
        """Get a registered TRM instance by name."""
        return self._registered_trms.get(trm_name)

    def get_status(self) -> Dict[str, Any]:
        """Get agent status summary"""
        status = {
            'site_key': self.site_key,
            'agent_mode': self.config.agent_mode,
            'use_trm': self.config.use_trm_adjustments,
            'model_loaded': self.model is not None,
            'cdc_status': self.cdc_monitor.get_status(),
            'allocations_summary': self.aatp_engine.get_allocation_summary(),
            'registered_trms': list(self._registered_trms.keys()),
        }
        if self.signal_bus:
            status['hive_signals'] = self.signal_bus.stats()
            status['signal_divergence'] = getattr(
                self.cdc_monitor, "_signal_divergence_score", 0.0
            )
        if self.get_current_directive() is not None:
            status['has_tgnn_directive'] = True
        return status
