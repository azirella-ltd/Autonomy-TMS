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


@dataclass
class ATPResponse:
    """Response from ATP decision"""
    order_id: str
    promised_qty: float
    promise_date: Any  # date
    source: str  # "deterministic", "trm_adjusted", "exception"
    confidence: float = 1.0
    explanation: str = ""


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

        # State cache
        self._state_cache: Optional[torch.Tensor] = None
        self._state_cache_time: Optional[datetime] = None

        logger.info(f"SiteAgent initialized for {config.site_key}")

    def get_explainer(self, agent_type: str) -> Optional[AgentContextExplainer]:
        """Get the context-aware explainer for a specific agent type."""
        return self._explainers.get(agent_type)

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
                checkpoint = torch.load(
                    checkpoint_path,
                    map_location=self.config.model_config.device
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
        1. AATPEngine computes deterministic availability
        2. If shortage, ATPExceptionHead suggests resolution
        3. Return combined decision
        """
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
                explanation="Full availability in allocation tier"
            )

        # Step 2: Shortage - check if TRM is available
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

        # Gather state from database/APIs
        state_data = await self._gather_state_data()

        # Encode
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
        """
        # Dimensions must match training configuration
        n_products = 1  # Single aggregated product view
        history_window = 12
        forecast_horizon = 8
        lead_time_buckets = 4

        # TODO: Query actual data sources and aggregate to single product view
        # For now, return placeholder tensors with correct dimensions
        return {
            'inventory': torch.zeros(1, n_products),
            'pipeline': torch.zeros(1, n_products, lead_time_buckets),
            'backlog': torch.zeros(1, n_products),
            'demand_history': torch.zeros(1, n_products, history_window),
            'forecasts': torch.zeros(1, n_products, forecast_horizon)
        }

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

    def get_status(self) -> Dict[str, Any]:
        """Get agent status summary"""
        return {
            'site_key': self.site_key,
            'agent_mode': self.config.agent_mode,
            'use_trm': self.config.use_trm_adjustments,
            'model_loaded': self.model is not None,
            'cdc_status': self.cdc_monitor.get_status(),
            'allocations_summary': self.aatp_engine.get_allocation_summary()
        }
