"""
SiteAgent - Unified Execution Orchestrator (Hybrid TRM + Claude Skills)

The SiteAgent is the execution-level orchestrator that combines:
- Deterministic engines (MRP, AATP, Inventory Buffer)
- Learned TRM heads (fast policy execution, ~95% of decisions)
- Claude Skills (exception handler for novel situations, ~5% of decisions)
- CDC monitoring (event-driven replanning)

Each site in the supply chain network has a SiteAgent responsible
for all execution decisions at that location.

Architecture (LeCun JEPA mapping):
- GraphSAGE/tGNN = World Model (network-wide state representation)
- TRMs = Actor (fast, learned policy execution)
- Claude Skills = Configurator (orchestration, exception handling, meta-learning)
- Bayesian/Causal AI = Critic (override effectiveness)
- Conformal Prediction = Uncertainty Module (routing trigger)

Execution Flow:
1. Engine computes deterministic result (always runs)
2. TRM adjusts if enabled (fast, <10ms, learned exceptions)
3. Conformal prediction checks TRM confidence:
   - Tight intervals (high confidence) → TRM result accepted
   - Wide intervals (low confidence) → Escalate to Claude Skills
4. Claude Skills handles exception (novel situation reasoning)
5. Skill proposal validated against engine constraints
6. Skill decisions feed back into TRM training (meta-learning)

Key Principles:
1. Engines are deterministic - auditable, testable, no surprises
2. TRM heads learn exceptions only - bounded adjustments
3. TRMs are the PRIMARY decision path (~95% of decisions)
4. Claude Skills handle only exceptions/novel situations (~5%)
5. Conformal prediction governs routing between TRM and Skills
6. Engines can run without TRM or Skills - graceful degradation
7. CDC monitor triggers out-of-cadence replanning
"""

import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any
import torch
import logging

from .engines import (
    MRPEngine, MRPConfig, GrossRequirement, PlannedOrder,
    AATPEngine, AATPConfig, Order, ATPResult, Priority,
    BufferCalculator, BufferConfig, BufferPolicy, DemandStats
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
from .site_capabilities import get_active_trms, ALL_TRM_NAMES
from app.services.agent_context_explainer import AgentContextExplainer, AgentType
from app.services.authorization_protocol import (
    AgentRole,
    ActionCategory,
    get_action_category,
)
from app.services.authorization_service import AuthorizationService

logger = logging.getLogger(__name__)

# Mapping from TRM name → AgentRole for authority boundary checks
_TRM_TO_AGENT_ROLE: Dict[str, AgentRole] = {
    "atp_executor": AgentRole.SO_ATP,
    "po_creation": AgentRole.PROCUREMENT,
    "inventory_rebalancing": AgentRole.INVENTORY,
    "order_tracking": AgentRole.SO_ATP,
    "mo_execution": AgentRole.PLANT,
    "to_execution": AgentRole.LOGISTICS,
    "quality_disposition": AgentRole.QUALITY,
    "maintenance_scheduling": AgentRole.MAINTENANCE,
    "subcontracting": AgentRole.PROCUREMENT,
    "forecast_adjustment": AgentRole.DEMAND,
    "inventory_buffer": AgentRole.INVENTORY,
}


@dataclass
class SiteAgentConfig:
    """Configuration for SiteAgent"""
    site_key: str

    # Engine configs
    mrp_config: MRPConfig = field(default_factory=MRPConfig)
    aatp_config: AATPConfig = field(default_factory=AATPConfig)
    ss_config: BufferConfig = field(default_factory=BufferConfig)

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

    # Authorization protocol
    enable_authorization: bool = True  # Check authority boundaries before actions

    # Tenant isolation — required for tenant-scoped decision memory (RAG)
    tenant_id: Optional[int] = None

    # Claude Skills — hybrid exception handler
    # When True, TRMs remain the PRIMARY path; Skills handle only exceptions
    # where conformal prediction indicates low confidence (wide intervals).
    # Reads from USE_CLAUDE_SKILLS env var at construction time.
    use_claude_skills: bool = field(
        default_factory=lambda: os.getenv("USE_CLAUDE_SKILLS", "false").lower() in ("true", "1", "yes")
    )

    # Conformal prediction threshold for Skills escalation.
    # When TRM confidence < this threshold (or CDT risk_bound > 1 - this),
    # the decision is escalated to Claude Skills for reasoned judgment.
    skill_escalation_threshold: float = 0.6

    # Maximum allowed deviation for Skill proposals vs engine constraints.
    # Skill proposals that deviate more than this fraction from engine
    # baseline are rejected in favor of the TRM/engine result.
    skill_max_deviation: float = 0.3

    # Vertical Escalation — Escalation Arbiter
    # When True, the Arbiter (every 2h) monitors TRM decision patterns
    # for persistent directional drift and routes to tGNN/S&OP replanning.
    # See docs/ESCALATION_ARCHITECTURE.md
    enable_vertical_escalation: bool = True
    escalation_persistence_window_hours: int = 48
    escalation_consistency_threshold: float = 0.70

    # Site tGNN (Layer 1.5) — Intra-site cross-TRM coordination
    # Runs hourly inference to modulate UrgencyVector before the 6-phase
    # decision cycle, learning causal cross-TRM relationships.
    # Cold-start safe: returns neutral (zero) adjustments when no model exists.

    # Site capability filtering — determines which TRMs are active.
    # Extracted from DAG topology (Site.master_type, Site.type).
    # When set, only TRMs relevant to this site's physical capabilities
    # are instantiated (e.g., a DC has no mo_execution or quality_disposition).
    # When None, all 11 TRMs are active (backward compatible).
    master_type: Optional[str] = None      # "manufacturer", "inventory", etc.
    sc_site_type: Optional[str] = None     # "RETAILER", "DISTRIBUTOR", etc.


@dataclass
class ATPResponse:
    """Response from ATP decision.

    source values:
        "deterministic" — Engine-only result (happy path or fallback)
        "trm_adjusted"  — TRM adjusted the engine result
        "skill:haiku"   — Claude Skills (Haiku) handled exception
        "skill:sonnet"  — Claude Skills (Sonnet) handled exception
    """
    order_id: str
    promised_qty: float
    promise_date: Any  # date
    source: str
    confidence: float = 1.0
    explanation: str = ""
    signal_context: Optional[Dict[str, Any]] = None  # Hive signal snapshot at decision time
    escalation_reason: Optional[str] = None  # Why Skills was invoked (if applicable)


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

        # Determine active TRM set from site capabilities
        if config.master_type:
            self.active_trms = get_active_trms(config.master_type, config.sc_site_type)
        else:
            self.active_trms = ALL_TRM_NAMES  # backward compatible: all 11

        # Initialize deterministic engines (100% code)
        self.mrp_engine = MRPEngine(config.site_key, config.mrp_config)
        self.aatp_engine = AATPEngine(config.site_key, config.aatp_config)
        self.ss_calculator = BufferCalculator(config.site_key, config.ss_config)

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

        # Claude Skills orchestrator (lazy-initialized when use_claude_skills=True)
        self._skill_orchestrator = None
        if config.use_claude_skills:
            self._init_skill_orchestrator()

        # Hive signal bus for stigmergic TRM coordination
        self.signal_bus: Optional[HiveSignalBus] = None
        if config.enable_hive_signals:
            self.signal_bus = HiveSignalBus()

        # Registered TRM instances (for signal_bus wiring)
        self._registered_trms: Dict[str, Any] = {}

        # Authorization service for cross-authority requests
        self.authorization_service: Optional[AuthorizationService] = None
        if config.enable_authorization:
            self.authorization_service = AuthorizationService(db=db_session)

        # Site tGNN (Layer 1.5) — intra-site cross-TRM coordination
        # Always instantiated; cold-start safe (neutral output when no model exists)
        self._site_tgnn_service = None
        try:
            from app.services.powell.site_tgnn_inference_service import SiteTGNNInferenceService
            self._site_tgnn_service = SiteTGNNInferenceService(
                site_key=config.site_key,
                config_id=getattr(config, "config_id", 0),
                active_trms=self.active_trms,
            )
        except Exception as e:
            logger.warning(f"Site tGNN init failed (continuing without): {e}")

        # Per-agent stochastic parameters (loaded from agent_stochastic_params table)
        # Dict of trm_type → param_name → distribution JSON dict
        self.stochastic_params: Dict[str, Dict[str, dict]] = {}
        self._load_stochastic_params()

        # Setup matrix and Glenday Sieve (for manufacturer sites)
        self._setup_matrix = None
        self._glenday_sieve = None
        if "mo_execution" in self.active_trms:
            try:
                from app.services.powell.engines.setup_matrix import (
                    SetupMatrix, GlendaySieve,
                )
                self._setup_matrix = SetupMatrix(
                    site_id=config.site_key, db=db_session,
                )
                self._setup_matrix.load()
                self._glenday_sieve = GlendaySieve(
                    site_id=config.site_key, db=db_session,
                )
                self._glenday_sieve.classify()
            except Exception as e:
                logger.debug(f"Setup matrix / Glenday init: {e}")

        # Recent decisions cache for Site tGNN feature engineering
        self._recent_decisions_cache: Dict[str, list] = {name: [] for name in [
            "atp_executor", "order_tracking", "po_creation", "rebalancing",
            "subcontracting", "inventory_buffer", "forecast_adj", "quality",
            "maintenance", "mo_execution", "to_execution",
        ]}

        # State cache
        self._state_cache: Optional[torch.Tensor] = None
        self._state_cache_time: Optional[datetime] = None

        # DM extension data cache — populated once per decision cycle, shared
        # across all TRM state builders to avoid redundant queries.
        # Keyed by (product_id, site_id) or just relevant key per table.
        self._dm_cache: Dict[str, Any] = {}
        self._dm_cache_time: Optional[datetime] = None

        trm_count = len(self.active_trms)
        logger.info(f"SiteAgent initialized for {config.site_key}"
                     f" [{trm_count}/11 TRMs active]"
                     f"{' [hive signals ON]' if self.signal_bus else ''}"
                     f"{' [authorization ON]' if self.authorization_service else ''}"
                     f"{' [site tGNN ON]' if self._site_tgnn_service else ''}")

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
        if trm_name not in self.active_trms:
            logger.info(
                f"Skipping TRM {trm_name} for {self.site_key} "
                f"(not active for master_type={self.config.master_type})"
            )
            return
        self._registered_trms[trm_name] = trm_instance
        if self.signal_bus is not None and hasattr(trm_instance, "signal_bus"):
            trm_instance.signal_bus = self.signal_bus
            logger.debug(f"Wired signal_bus to TRM {trm_name}")

        # Wire tenant-scoped CDT wrapper (replaces global singleton set in __init__)
        tenant_id = getattr(self.config, "tenant_id", None)
        if tenant_id is not None and hasattr(trm_instance, "_cdt_wrapper"):
            try:
                from app.services.conformal_prediction.conformal_decision import get_cdt_registry
                # Map TRM name to CDT agent type key
                cdt_type = trm_name.replace("_trm", "").replace("_executor", "")
                if cdt_type == "atp":
                    cdt_type = "atp"
                trm_instance._cdt_wrapper = get_cdt_registry(
                    tenant_id=tenant_id,
                ).get_or_create(cdt_type)
            except Exception:
                pass  # CDT is optional

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

    def check_authority_boundary(
        self,
        trm_name: str,
        action_type: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Check whether an action requires authorization before execution.

        Uses the authority map to determine if a TRM's proposed action is
        unilateral, requires authorization, or is forbidden.

        Args:
            trm_name: TRM name (e.g. "atp_executor", "po_creation").
            action_type: Action being proposed (e.g. "request_expedite").
            context: Optional context for logging/audit.

        Returns:
            Dict with ``category`` (UNILATERAL/REQUIRES_AUTHORIZATION/FORBIDDEN),
            ``authorized`` (bool), and optionally ``thread_id`` if a review
            thread was created.
        """
        agent_role = _TRM_TO_AGENT_ROLE.get(trm_name)
        if agent_role is None:
            return {"category": "UNILATERAL", "authorized": True}

        category = get_action_category(agent_role, action_type)

        if category == ActionCategory.UNILATERAL:
            return {"category": "UNILATERAL", "authorized": True}

        if category == ActionCategory.FORBIDDEN:
            logger.warning(
                f"[{self.site_key}] FORBIDDEN action: {trm_name}/{action_type}"
            )
            return {"category": "FORBIDDEN", "authorized": False}

        # REQUIRES_AUTHORIZATION — submit to auth service if available
        if self.authorization_service is not None:
            try:
                thread = self.authorization_service.submit_request(
                    requesting_agent=f"{agent_role.value}@{self.site_key}",
                    target_agent="planning_director",
                    proposed_action={
                        "action_type": action_type,
                        "trm_name": trm_name,
                        "site_key": self.site_key,
                    },
                    net_benefit=0.0,
                    benefit_threshold=0.0,
                    justification=f"{trm_name} requests {action_type}",
                    priority="MEDIUM",
                    site_key=self.site_key,
                )
                # Check if auto-resolved
                if hasattr(thread, 'status'):
                    status_val = thread.status.value if hasattr(thread.status, 'value') else str(thread.status)
                    if status_val == "ACCEPTED":
                        return {"category": "REQUIRES_AUTHORIZATION", "authorized": True, "thread_id": thread.thread_id}
                    elif status_val == "DENIED":
                        return {"category": "REQUIRES_AUTHORIZATION", "authorized": False, "thread_id": thread.thread_id}

                # Needs human review
                return {
                    "category": "REQUIRES_AUTHORIZATION",
                    "authorized": False,
                    "needs_review": True,
                    "thread_id": thread.thread_id,
                }
            except Exception as e:
                logger.warning(f"Authorization check failed: {e}; defaulting to authorized")
                return {"category": "REQUIRES_AUTHORIZATION", "authorized": True}

        # No auth service — default to authorized
        return {"category": "REQUIRES_AUTHORIZATION", "authorized": True}

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

    def _load_stochastic_params(self):
        """Load per-agent stochastic parameters from the agent_stochastic_params table.

        Populates self.stochastic_params as:
            { trm_type: { param_name: distribution_dict, ... }, ... }

        Site-specific overrides take precedence over config-wide defaults.
        Falls back silently to empty dict if DB is unavailable.
        """
        if not self.db:
            return

        config_id = getattr(self.config, "config_id", None)
        if not config_id:
            return

        try:
            from app.models.agent_stochastic_param import AgentStochasticParam

            rows = self.db.query(AgentStochasticParam).filter(
                AgentStochasticParam.config_id == config_id,
            ).order_by(
                AgentStochasticParam.trm_type,
                AgentStochasticParam.site_id.asc(),  # NULL (config-wide) first
            ).all()

            for row in rows:
                if row.trm_type not in self.active_trms:
                    continue
                if row.trm_type not in self.stochastic_params:
                    self.stochastic_params[row.trm_type] = {}
                # Site-specific overrides config-wide (later rows overwrite earlier)
                self.stochastic_params[row.trm_type][row.param_name] = row.distribution

            loaded = sum(len(v) for v in self.stochastic_params.values())
            if loaded > 0:
                logger.info(
                    f"Loaded {loaded} stochastic params for "
                    f"{len(self.stochastic_params)} TRM types"
                )
        except Exception as e:
            logger.debug(f"Could not load stochastic params: {e}")

    def get_stochastic_dist(
        self, trm_type: str, param_name: str
    ) -> Optional[dict]:
        """Get the distribution dict for a specific TRM's stochastic parameter.

        Returns the distribution JSON (e.g. {"type": "lognormal", "mean": 7, ...})
        or None if not available. Use with Distribution.from_dict() to sample.
        """
        return self.stochastic_params.get(trm_type, {}).get(param_name)

    def sample_stochastic(
        self, trm_type: str, param_name: str, fallback: float = 0.0
    ) -> float:
        """Sample a single value from a TRM's stochastic parameter distribution.

        Returns fallback if the parameter is not configured.
        """
        dist_dict = self.get_stochastic_dist(trm_type, param_name)
        if not dist_dict:
            return fallback
        try:
            from app.services.stochastic.distributions import Distribution
            dist = Distribution.from_dict(dist_dict)
            return float(dist.sample(size=1)[0])
        except Exception:
            return fallback

    def _init_skill_orchestrator(self):
        """Initialize Claude Skills orchestrator for LLM-based decisions."""
        try:
            from app.services.skills import SkillOrchestrator, ClaudeClient
            # Import all skill registrations
            import app.services.skills.atp_executor
            import app.services.skills.po_creation
            import app.services.skills.inventory_rebalancing
            import app.services.skills.inventory_buffer
            import app.services.skills.order_tracking
            import app.services.skills.mo_execution
            import app.services.skills.to_execution
            import app.services.skills.quality_disposition
            import app.services.skills.maintenance_scheduling
            import app.services.skills.subcontracting
            import app.services.skills.forecast_adjustment

            self._skill_orchestrator = SkillOrchestrator(
                claude_client=ClaudeClient(),
                tenant_id=self.config.tenant_id,
            )
            logger.info("Claude Skills orchestrator initialized for site %s", self.site_key)
        except Exception as e:
            logger.warning("Failed to initialize Skills orchestrator: %s. Falling back to TRM.", e)
            self._skill_orchestrator = None

    def _should_escalate_to_skills(
        self,
        trm_confidence: float,
        risk_assessment: Optional[Dict[str, Any]] = None,
    ) -> tuple[bool, str]:
        """Decide whether to escalate a TRM decision to Claude Skills.

        Uses conformal prediction (CDT risk bounds) as the routing trigger.
        When TRM confidence is low or conformal intervals are wide, the
        decision is escalated to Claude Skills for reasoned judgment.

        Args:
            trm_confidence: TRM output confidence score (0-1).
            risk_assessment: Optional CDT risk assessment dict with
                'risk_bound' (P(loss > threshold)) and 'interval_width'.

        Returns:
            Tuple of (should_escalate, reason).
        """
        if not self.config.use_claude_skills or self._skill_orchestrator is None:
            return False, ""

        # Check 1: TRM confidence below escalation threshold
        if trm_confidence < self.config.skill_escalation_threshold:
            return True, f"trm_confidence={trm_confidence:.3f} < threshold={self.config.skill_escalation_threshold}"

        # Check 2: CDT risk bound indicates high uncertainty
        if risk_assessment:
            risk_bound = risk_assessment.get("risk_bound", 0.0)
            # Risk bound > (1 - escalation_threshold) means too risky for TRM alone
            risk_threshold = 1.0 - self.config.skill_escalation_threshold
            if risk_bound > risk_threshold:
                return True, f"cdt_risk_bound={risk_bound:.3f} > threshold={risk_threshold:.3f}"

            # Check 3: Conformal interval width (wider = more uncertainty)
            interval_width = risk_assessment.get("interval_width", 0.0)
            if interval_width > 0.5:  # Normalized: > 50% of value range
                return True, f"conformal_interval_width={interval_width:.3f} (too wide)"

        return False, ""

    def _validate_skill_proposal(
        self,
        skill_decision: Dict[str, Any],
        engine_result: Dict[str, Any],
        trm_type: str,
    ) -> tuple[bool, str]:
        """Validate a Claude Skills proposal against engine constraints.

        Every Skills proposal must pass constraint checking before execution.
        This prevents the LLM from producing decisions that violate physical
        or business constraints that the deterministic engine enforces.

        Args:
            skill_decision: The decision dict from Claude Skills.
            engine_result: The baseline engine result for comparison.
            trm_type: TRM type identifier for context-specific validation.

        Returns:
            Tuple of (is_valid, rejection_reason).
        """
        max_dev = self.config.skill_max_deviation

        # Quantity-based validation (ATP, PO, inventory)
        skill_qty = skill_decision.get("quantity", skill_decision.get("order_quantity"))
        engine_qty = engine_result.get("available_qty", engine_result.get("quantity"))

        if skill_qty is not None and engine_qty is not None and engine_qty > 0:
            deviation = abs(skill_qty - engine_qty) / engine_qty
            if deviation > max_dev:
                return False, (
                    f"quantity deviation {deviation:.1%} exceeds max {max_dev:.1%} "
                    f"(skill={skill_qty}, engine={engine_qty})"
                )

        # Multiplier-based validation (inventory buffer)
        multiplier = skill_decision.get("multiplier")
        if multiplier is not None:
            if multiplier < 0.5 or multiplier > 2.0:
                return False, f"multiplier {multiplier} outside safe range [0.5, 2.0]"

        # Confidence gate: reject Skills proposals with very low confidence
        skill_confidence = skill_decision.get("confidence", 1.0)
        if skill_confidence < 0.3:
            return False, f"skill confidence {skill_confidence:.2f} too low"

        return True, ""

    async def _record_skill_decision_for_training(
        self,
        trm_type: str,
        state_features: Dict[str, Any],
        skill_decision: Dict[str, Any],
        escalation_reason: str,
    ) -> None:
        """Record a Skills decision for TRM meta-learning.

        Skills decisions (especially successful ones) feed back into TRM
        training data, gradually shifting the 95/5 boundary by teaching
        TRMs to handle situations they previously couldn't.
        """
        if self.db is None:
            return

        try:
            from app.services.decision_memory_service import DecisionMemoryService
            from app.db.kb_session import get_kb_session

            state_summary = (
                f"{trm_type} escalated: {escalation_reason}. "
                f"State: {str(state_features)[:300]}"
            )

            async with get_kb_session() as kb_db:
                svc = DecisionMemoryService(
                    db=kb_db,
                    tenant_id=self.config.tenant_id or 0,
                )
                await svc.embed_decision(
                    trm_type=trm_type,
                    state_features=state_features,
                    state_summary=state_summary,
                    decision=skill_decision,
                    decision_source="skill_exception",
                    site_key=self.site_key,
                )
        except Exception as e:
            logger.debug("Failed to record skill decision for training: %s", e)

    async def execute_atp(self, order: Order) -> ATPResponse:
        """
        Execute ATP decision for incoming order.

        Hybrid TRM + Claude Skills flow:
        1. Read hive signals (quality holds, rebalance inbound, etc.)
        2. AATPEngine computes deterministic availability
        3. If shortage → TRM exception head adjusts (fast, ~95% of cases)
        4. Conformal prediction checks TRM confidence:
           - High confidence → accept TRM result
           - Low confidence → escalate to Claude Skills
        5. Skills proposal validated against engine constraints
        6. Skills decisions recorded for TRM meta-learning
        """
        # Step 0: Read relevant hive signals before decision
        signal_context = self._read_atp_signals()

        # Capture hive signal snapshot for decision audit
        hive_snapshot = self._build_signal_context()

        # Step 1: Deterministic AATP
        base_result = self.aatp_engine.check_availability(order)

        if base_result.can_fulfill_full:
            # Happy path - no TRM or Skills needed
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

        # Step 3: TRM exception head (PRIMARY path — fast, learned)
        trm_confidence = 0.0
        trm_response = None
        risk_assessment = None

        if self.config.use_trm_adjustments and self.model is not None:
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

                trm_confidence = exception_decision.get('confidence', torch.tensor([[0.0]]))[0, 0].item()

                # Extract CDT risk assessment if available
                if 'risk_bound' in exception_decision:
                    risk_assessment = {
                        "risk_bound": exception_decision['risk_bound'][0, 0].item(),
                        "interval_width": exception_decision.get('interval_width', torch.tensor([[0.0]]))[0, 0].item(),
                    }

                trm_response = self._apply_atp_exception(order, base_result, exception_decision)

            except Exception as e:
                logger.warning(f"TRM exception handling failed: {e}")
                # TRM failed — will fall through to Skills or deterministic

        # Step 4: Conformal prediction routing — should we escalate to Skills?
        should_escalate, escalation_reason = self._should_escalate_to_skills(
            trm_confidence, risk_assessment
        )

        if should_escalate and self._skill_orchestrator is not None:
            # Step 5: Claude Skills exception handler (novel situation)
            try:
                state_features = {
                    "order_id": order.order_id,
                    "requested_qty": order.requested_qty,
                    "available_qty": base_result.available_qty,
                    "shortage_qty": base_result.shortage_qty,
                    "priority": getattr(order, "priority", Priority(3)).value if hasattr(getattr(order, "priority", 3), "value") else getattr(order, "priority", 3),
                    "trm_confidence": trm_confidence,
                    "escalation_reason": escalation_reason,
                }
                skill_result = await self._skill_orchestrator.execute(
                    trm_type="atp_executor",
                    state_features=state_features,
                    engine_result={
                        "available_qty": base_result.available_qty,
                        "available_date": str(base_result.available_date),
                    },
                    site_key=self.site_key,
                )

                # Step 5b: Validate Skills proposal against engine constraints
                is_valid, rejection_reason = self._validate_skill_proposal(
                    skill_result.decision,
                    {"available_qty": base_result.available_qty},
                    "atp_executor",
                )

                if is_valid:
                    promised = skill_result.decision.get("quantity", base_result.available_qty)
                    if promised > 0:
                        self.aatp_engine.commit_consumption(order, base_result)

                    # Step 6: Record for TRM meta-learning
                    await self._record_skill_decision_for_training(
                        trm_type="atp_executor",
                        state_features=state_features,
                        skill_decision=skill_result.decision,
                        escalation_reason=escalation_reason,
                    )

                    return ATPResponse(
                        order_id=order.order_id,
                        promised_qty=min(promised, order.requested_qty),
                        promise_date=base_result.available_date,
                        source=f"skill:{skill_result.model_used}",
                        confidence=skill_result.confidence,
                        explanation=skill_result.reasoning,
                        signal_context=hive_snapshot or None,
                        escalation_reason=escalation_reason,
                    )
                else:
                    logger.info(
                        "Skills proposal rejected for ATP: %s. Using TRM/engine result.",
                        rejection_reason,
                    )
            except Exception as e:
                logger.debug("Skill ATP exception failed, using TRM/engine: %s", e)

        # Step 7: Return TRM result if available, otherwise deterministic
        if trm_response is not None:
            trm_response.signal_context = hive_snapshot or None
            return trm_response

        # Final fallback: deterministic engine-only
        if base_result.available_qty > 0:
            self.aatp_engine.commit_consumption(order, base_result)

        return ATPResponse(
            order_id=order.order_id,
            promised_qty=base_result.available_qty,
            promise_date=base_result.available_date,
            source="deterministic",
            confidence=1.0,
            explanation=f"Shortage: {base_result.shortage_qty:.0f} units unavailable",
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

        Hybrid TRM + Claude Skills flow:
        1. MRPEngine computes net requirements (deterministic)
        2. TRM adjusts timing/expedite (fast, PRIMARY path)
        3. If TRM confidence low → escalate to Claude Skills
        4. Skills proposal validated against engine constraints
        """
        # Step 1: Deterministic MRP
        net_requirements, planned_orders = self.mrp_engine.compute_net_requirements(
            gross_requirements=gross_requirements,
            on_hand_inventory=on_hand_inventory,
            scheduled_receipts=scheduled_receipts,
            bom=bom,
            lead_times=lead_times
        )

        # Step 2: Convert to PO recommendations with TRM-first adjustments
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

            # Step 3: TRM timing adjustment (PRIMARY — fast, learned)
            trm_confidence = 0.0
            risk_assessment = None

            if self.config.use_trm_adjustments and self.model is not None:
                try:
                    state = await self._encode_state()
                    po_context = self._po_to_tensor(po)

                    with torch.no_grad():
                        timing_adj = self.model.forward_po_timing(
                            state_embedding=state,
                            po_context=po_context
                        )

                    trm_confidence = timing_adj.get('confidence', torch.tensor([[0.0]]))[0, 0].item()

                    if 'risk_bound' in timing_adj:
                        risk_assessment = {
                            "risk_bound": timing_adj['risk_bound'][0, 0].item(),
                            "interval_width": timing_adj.get('interval_width', torch.tensor([[0.0]]))[0, 0].item(),
                        }

                    rec = self._apply_timing_adjustment(rec, timing_adj)

                except Exception as e:
                    logger.warning(f"TRM timing adjustment failed: {e}")

            # Step 4: Conformal routing — escalate to Skills if low confidence
            should_escalate, escalation_reason = self._should_escalate_to_skills(
                trm_confidence, risk_assessment
            )

            if should_escalate and self._skill_orchestrator is not None:
                try:
                    state_features = {
                        "item_id": po.item_id,
                        "quantity": po.quantity,
                        "order_date": str(po.order_date),
                        "order_type": po.order_type,
                        "lead_time": lead_times.get(po.item_id, 7),
                        "on_hand": on_hand_inventory.get(po.item_id, 0),
                        "trm_confidence": trm_confidence,
                        "escalation_reason": escalation_reason,
                    }
                    skill_result = await self._skill_orchestrator.execute(
                        trm_type="po_creation",
                        state_features=state_features,
                        engine_result={
                            "quantity": po.quantity,
                            "order_date": str(po.order_date),
                            "order_type": po.order_type,
                        },
                        site_key=self.site_key,
                    )

                    # Validate Skills proposal
                    is_valid, rejection_reason = self._validate_skill_proposal(
                        skill_result.decision,
                        {"quantity": po.quantity},
                        "po_creation",
                    )

                    if is_valid and skill_result.decision.get("action") == "create_po":
                        rec.expedite = skill_result.decision.get("timing") == "immediate"
                        rec.confidence = skill_result.confidence
                        rec.source = f"skill:{skill_result.model_used}"

                        # Record for TRM meta-learning
                        await self._record_skill_decision_for_training(
                            trm_type="po_creation",
                            state_features=state_features,
                            skill_decision=skill_result.decision,
                            escalation_reason=escalation_reason,
                        )
                    elif not is_valid:
                        logger.info("Skills PO proposal rejected: %s", rejection_reason)

                except Exception as e:
                    logger.debug("Skill PO adjustment failed: %s", e)

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
        Get inventory parameter adjustments.

        Hybrid TRM + Claude Skills flow:
        1. TRM computes multipliers (PRIMARY — fast, learned)
        2. If TRM confidence low → escalate to Claude Skills
        3. Skills proposal validated (multiplier within [0.5, 2.0])

        Returns dict with:
        - ss_multiplier: Safety stock adjustment
        - rop_multiplier: Reorder point adjustment
        - confidence: Decision confidence
        - source: Decision source ("trm_adjusted", "skill:*", "deterministic")
        """
        # Step 1: TRM inventory adjustment (PRIMARY path)
        trm_confidence = 0.0
        trm_result = None
        risk_assessment = None

        if self.config.use_trm_adjustments and self.model is not None:
            try:
                state = await self._encode_state()

                with torch.no_grad():
                    inv_output = self.model.forward_inventory_planning(state)

                trm_confidence = inv_output['confidence'][0, 0].item()

                if 'risk_bound' in inv_output:
                    risk_assessment = {
                        "risk_bound": inv_output['risk_bound'][0, 0].item(),
                        "interval_width": inv_output.get('interval_width', torch.tensor([[0.0]]))[0, 0].item(),
                    }

                trm_result = {
                    'ss_multiplier': inv_output['ss_multiplier'][0, 0].item(),
                    'rop_multiplier': inv_output['rop_multiplier'][0, 0].item(),
                    'confidence': trm_confidence,
                    'source': 'trm_adjusted',
                }

            except Exception as e:
                logger.warning(f"TRM inventory adjustment failed: {e}")

        # Step 2: Conformal routing — escalate to Skills if low confidence
        should_escalate, escalation_reason = self._should_escalate_to_skills(
            trm_confidence, risk_assessment
        )

        if should_escalate and self._skill_orchestrator is not None:
            try:
                current_mult = trm_result['ss_multiplier'] if trm_result else 1.0
                state_features = {
                    "site_key": self.site_key,
                    "current_multiplier": current_mult,
                    "trm_confidence": trm_confidence,
                    "escalation_reason": escalation_reason,
                }
                skill_result = await self._skill_orchestrator.execute(
                    trm_type="inventory_buffer",
                    state_features=state_features,
                    engine_result={"ss_multiplier": 1.0, "rop_multiplier": 1.0},
                    site_key=self.site_key,
                )

                # Validate Skills proposal
                is_valid, rejection_reason = self._validate_skill_proposal(
                    skill_result.decision,
                    {"ss_multiplier": 1.0},
                    "inventory_buffer",
                )

                if is_valid:
                    multiplier = skill_result.decision.get("multiplier", 1.0)

                    # Record for TRM meta-learning
                    await self._record_skill_decision_for_training(
                        trm_type="inventory_buffer",
                        state_features=state_features,
                        skill_decision=skill_result.decision,
                        escalation_reason=escalation_reason,
                    )

                    return {
                        "ss_multiplier": multiplier,
                        "rop_multiplier": multiplier,
                        "confidence": skill_result.confidence,
                        "source": f"skill:{skill_result.model_used}",
                        "escalation_reason": escalation_reason,
                    }
                else:
                    logger.info("Skills buffer proposal rejected: %s", rejection_reason)

            except Exception as e:
                logger.debug("Skill inventory buffer failed: %s", e)

        # Step 3: Return TRM result if available, otherwise neutral
        if trm_result is not None:
            return trm_result

        return {'ss_multiplier': 1.0, 'rop_multiplier': 1.0, 'confidence': 0.0, 'source': 'deterministic'}

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
                        tenant_id=getattr(self.config, "tenant_id", 0) or 0,
                        config_id=getattr(self.config, "config_id", 0) or 0,
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

    async def _extract_distribution_features(self) -> Dict[str, float]:
        """Extract distribution-aware features for decision metadata.

        These features capture the shape of demand and lead time distributions
        using native parameters (Weibull shape k, Lognormal sigma, etc.)
        instead of just mean/std. Stored in decision metadata for future model
        retraining — NOT fed to current TRM input tensors.

        Insight: Kravanja (2026) — distribution parameters are more meaningful
        features than mean/std for non-Normal supply chain data.

        Returns:
            Dictionary of distribution features (empty if extraction fails
            or is disabled via config).
        """
        if not getattr(self.config, 'use_distribution_features', False):
            return {}

        features: Dict[str, float] = {}
        try:
            from app.services.stochastic.feature_extractor import DistributionFeatureExtractor
            extractor = DistributionFeatureExtractor()

            # Extract demand features from recent history
            demand_history = self._recent_demand_values()
            if demand_history is not None and len(demand_history) >= 10:
                features.update(extractor.extract_demand_features(demand_history))

            # Extract lead time features if available
            lt_history = self._recent_lead_time_values()
            if lt_history is not None and len(lt_history) >= 5:
                features.update(extractor.extract_lead_time_features(lt_history))
        except Exception as e:
            logger.debug("Distribution feature extraction skipped: %s", e)

        return features

    def _recent_demand_values(self):
        """Get recent demand values from the site's history buffer.

        Returns numpy array or None if not available.
        """
        # Placeholder: in production this queries the demand history
        # from the site's state buffer or the database
        return None

    def _recent_lead_time_values(self):
        """Get recent lead time values from the site's history buffer.

        Returns numpy array or None if not available.
        """
        return None

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
                    HiveSignalType.BUFFER_INCREASED,
                    HiveSignalType.BUFFER_DECREASED,
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

        # Glenday Sieve urgency pre-modulation: boost MO urgency for green runners
        # This runs before Site tGNN so the sieve signal flows into tGNN features
        if self._glenday_sieve and self.signal_bus and hasattr(self.signal_bus, "urgency"):
            try:
                from app.services.powell.engines.setup_matrix import RunnerCategory
                green_count = len(self._glenday_sieve.green_runners())
                if green_count > 0:
                    # Boost MO urgency proportional to green runner pressure
                    self.signal_bus.urgency.adjust("mo_execution", 0.1)
            except Exception as e:
                logger.debug(f"Glenday urgency modulation: {e}")

        # Layer 1.5: Site tGNN modulates UrgencyVector before phases execute
        if self._site_tgnn_service and self.signal_bus:
            try:
                from app.services.powell.hive_feedback import compute_feedback_features
                feedback = compute_feedback_features(
                    urgency_snapshot=self.signal_bus.urgency.snapshot() if hasattr(self.signal_bus, "urgency") else None,
                    signal_bus=self.signal_bus,
                )
                site_tgnn_output = self._site_tgnn_service.infer(
                    hive_signal_bus=self.signal_bus,
                    urgency_vector=self.signal_bus.urgency if hasattr(self.signal_bus, "urgency") else None,
                    recent_decisions=self._recent_decisions_cache,
                    hive_feedback=feedback,
                )
                # Apply urgency adjustments
                urgency_vec = self.signal_bus.urgency if hasattr(self.signal_bus, "urgency") else None
                if urgency_vec:
                    for trm_name, adj in site_tgnn_output.urgency_adjustments.items():
                        if abs(adj) > 0.001:  # Skip negligible adjustments
                            urgency_vec.adjust(trm_name, adj)
            except Exception as e:
                logger.debug(f"Site tGNN pre-cycle inference failed: {e}")

        for phase in DecisionCyclePhase:
            phase_start = time.monotonic()
            phase_result = PhaseResult(phase=phase)
            trm_names = PHASE_TRM_MAP.get(phase, [])
            signals_before = len(self.signal_bus) if self.signal_bus else 0

            for trm_name in trm_names:
                if trm_name not in self.active_trms:
                    continue
                executor = executors.get(trm_name)
                if executor is None:
                    continue
                try:
                    # Thread cycle context to TRM for HiveSignalMixin capture
                    trm_instance = self._registered_trms.get(trm_name)
                    if trm_instance is not None:
                        trm_instance._cycle_id = result.cycle_id
                        trm_instance._cycle_phase = phase.name
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

            # ── Forward sweep: propagate phase decisions into shared state ──
            # After each phase, update the projected inventory position so that
            # later phases see the cumulative effect of earlier decisions.
            # E.g., PO ordered in ACQUIRE → rebalancing in REFLECT sees updated
            # inventory position and may decide the transfer is unnecessary.
            if self.signal_bus and phase_result.trms_executed:
                try:
                    self._propagate_phase_decisions(phase, phase_result.trms_executed)
                except Exception as e:
                    logger.debug(f"Phase state propagation failed: {e}")

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

    def _propagate_phase_decisions(
        self,
        phase: DecisionCyclePhase,
        trms_executed: List[str],
    ) -> None:
        """Update shared state with inventory deltas from decisions made in this phase.

        This ensures later phases see the cumulative effect of earlier decisions.
        For example, after ACQUIRE (PO agent orders 500 units), the projected
        on_order quantity increases — so REFLECT (rebalancing) may decide a
        transfer is no longer needed.
        """
        if not hasattr(self, "_state") or self._state is None:
            return

        state = self._state
        # Collect inventory deltas from recent decisions cache
        cache = getattr(self, "_recent_decisions_cache", None)
        if not cache:
            return

        for trm_name in trms_executed:
            decisions = cache.get(trm_name, [])
            for d in decisions:
                qty = 0.0
                if trm_name in ("po_creation", "subcontracting"):
                    qty = d.get("recommended_qty", 0) or d.get("qty", 0) or 0
                    # PO increases on_order (future supply)
                    if hasattr(state, "on_order"):
                        state.on_order = (state.on_order or 0) + float(qty)
                elif trm_name in ("mo_execution",):
                    qty = d.get("planned_qty", 0) or d.get("qty", 0) or 0
                    # MO increases WIP
                    if hasattr(state, "wip"):
                        state.wip = (state.wip or 0) + float(qty)
                elif trm_name in ("to_execution",):
                    qty = d.get("planned_qty", 0) or d.get("qty", 0) or 0
                    # TO increases in_transit at destination (this site if destination)
                    if hasattr(state, "in_transit"):
                        state.in_transit = (state.in_transit or 0) + float(qty)
                elif trm_name == "atp_executor":
                    qty = d.get("promised_qty", 0) or d.get("allocated_qty", 0) or 0
                    # ATP commits inventory
                    if hasattr(state, "committed_inventory"):
                        state.committed_inventory = (state.committed_inventory or 0) + float(qty)

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

    # ---- Authorization boundary checks ------------------------------------

    def check_authority_boundary(
        self,
        trm_name: str,
        action_type: str,
    ) -> ActionCategory:
        """Check the authority category for a TRM action.

        Maps the TRM name to its corresponding AgentRole and looks up
        the action in the AUTHORITY_MAP.

        Args:
            trm_name: TRM name (e.g. "atp_executor", "inventory_rebalancing").
            action_type: Action being proposed (e.g. "cross_dc_transfer").

        Returns:
            ActionCategory (UNILATERAL, REQUIRES_AUTHORIZATION, or FORBIDDEN).
        """
        agent_role = _TRM_TO_AGENT_ROLE.get(trm_name)
        if agent_role is None:
            return ActionCategory.REQUIRES_AUTHORIZATION
        return get_action_category(agent_role, action_type)

    def request_authorization(
        self,
        trm_name: str,
        action_type: str,
        target_trm: str,
        proposed_action: Dict[str, Any],
        net_benefit: float = 0.0,
        benefit_threshold: float = 0.0,
        justification: str = "",
        priority: str = "MEDIUM",
    ) -> Optional[Any]:
        """Submit an authorization request when an action crosses authority boundaries.

        Called by TRM execution logic when ``check_authority_boundary``
        returns REQUIRES_AUTHORIZATION.

        Args:
            trm_name: Requesting TRM.
            action_type: Action type string.
            target_trm: Target TRM or agent role for authorization.
            proposed_action: Action details.
            net_benefit: Balanced scorecard net benefit.
            benefit_threshold: Threshold for auto-resolution.
            justification: Reason for the request.
            priority: Priority level.

        Returns:
            AuthorizationThread if service is available, None otherwise.
        """
        if self.authorization_service is None:
            logger.debug("Authorization disabled; skipping request.")
            return None

        requesting_role = _TRM_TO_AGENT_ROLE.get(trm_name, AgentRole.SO_ATP).value
        target_role = _TRM_TO_AGENT_ROLE.get(target_trm, AgentRole.LOGISTICS).value

        thread = self.authorization_service.submit_request(
            requesting_agent=requesting_role,
            target_agent=target_role,
            proposed_action={
                "action_type": action_type,
                "trm": trm_name,
                **proposed_action,
            },
            net_benefit=net_benefit,
            benefit_threshold=benefit_threshold,
            justification=justification,
            priority=priority,
            site_key=self.site_key,
        )

        logger.info(
            f"Authorization request submitted: {trm_name}→{target_trm} "
            f"({action_type}) thread={thread.thread_id} status={thread.status.value}"
        )
        return thread

    def get_pending_authorizations(self) -> List[Any]:
        """Get pending authorization threads for this site."""
        if self.authorization_service is None:
            return []
        return self.authorization_service.get_pending(site_key=self.site_key)

    # ---- DM extension data fetching for heuristic state enrichment ----------

    def _refresh_dm_cache(self, config_id: int) -> None:
        """Refresh the DM extension data cache if stale (>5 min) or empty.

        Fetches data from extension tables (material_valuation,
        outbound_order_status, work_center_master, capacity_resource_detail,
        outbound_order_line_schedule) in batch and caches for the decision
        cycle.  Each query is wrapped in try/except so missing tables
        (pre-migration) do not break the agent.
        """
        now = datetime.utcnow()
        if (
            self._dm_cache_time is not None
            and (now - self._dm_cache_time).total_seconds() < 300
            and self._dm_cache
        ):
            return  # cache still fresh

        if self.db is None:
            return

        cache: Dict[str, Any] = {}

        # --- material_valuation keyed by (product_id, site_id) ---
        try:
            from app.models.sc_extensions import MaterialValuation
            from sqlalchemy import select
            rows = self.db.execute(
                select(MaterialValuation).where(
                    MaterialValuation.config_id == config_id
                )
            ).scalars().all()
            mv: Dict[tuple, Any] = {}
            for r in rows:
                mv[(str(r.product_id), r.site_id)] = r
            cache["material_valuation"] = mv
        except Exception as exc:
            logger.debug("DM cache: material_valuation unavailable: %s", exc)
            cache["material_valuation"] = {}

        # --- outbound_order_status keyed by order_id ---
        try:
            from app.models.sc_extensions import OutboundOrderStatus
            from sqlalchemy import select
            rows = self.db.execute(
                select(OutboundOrderStatus).where(
                    OutboundOrderStatus.config_id == config_id
                )
            ).scalars().all()
            oos: Dict[str, Any] = {}
            for r in rows:
                oos[str(r.order_id)] = r
            cache["outbound_order_status"] = oos
        except Exception as exc:
            logger.debug("DM cache: outbound_order_status unavailable: %s", exc)
            cache["outbound_order_status"] = {}

        # --- work_center_master keyed by (site_id, work_center_code) ---
        try:
            from app.models.sc_extensions import WorkCenterMaster
            from sqlalchemy import select
            rows = self.db.execute(
                select(WorkCenterMaster).where(
                    WorkCenterMaster.config_id == config_id
                )
            ).scalars().all()
            wcm: Dict[tuple, Any] = {}
            for r in rows:
                wcm[(r.site_id, r.work_center_code)] = r
            cache["work_center_master"] = wcm
        except Exception as exc:
            logger.debug("DM cache: work_center_master unavailable: %s", exc)
            cache["work_center_master"] = {}

        # --- capacity_resource_detail keyed by work_center_id ---
        try:
            from app.models.sc_extensions import CapacityResourceDetail
            from sqlalchemy import select
            rows = self.db.execute(
                select(CapacityResourceDetail).where(
                    CapacityResourceDetail.config_id == config_id
                )
            ).scalars().all()
            crd: Dict[int, Any] = {}
            for r in rows:
                if r.work_center_id is not None:
                    crd[r.work_center_id] = r
            cache["capacity_resource_detail"] = crd
        except Exception as exc:
            logger.debug("DM cache: capacity_resource_detail unavailable: %s", exc)
            cache["capacity_resource_detail"] = {}

        # --- outbound_order_line_schedule: committed qty by (order_id, date) ---
        try:
            from app.models.sc_extensions import OutboundOrderLineSchedule
            from sqlalchemy import select, func as sa_func
            rows = self.db.execute(
                select(
                    OutboundOrderLineSchedule.order_id,
                    OutboundOrderLineSchedule.requested_date,
                    sa_func.coalesce(sa_func.sum(OutboundOrderLineSchedule.confirmed_qty), 0.0).label("total_confirmed"),
                ).where(
                    OutboundOrderLineSchedule.config_id == config_id
                ).group_by(
                    OutboundOrderLineSchedule.order_id,
                    OutboundOrderLineSchedule.requested_date,
                )
            ).all()
            ols: Dict[str, float] = {}
            for r in rows:
                key = f"{r.order_id}|{r.requested_date}"
                ols[key] = float(r.total_confirmed)
            cache["order_schedule_committed"] = ols
        except Exception as exc:
            logger.debug("DM cache: outbound_order_line_schedule unavailable: %s", exc)
            cache["order_schedule_committed"] = {}

        # --- supply_plan: existing planned qty by (product_id, site_id) ---
        try:
            from app.models.sc_entities import SupplyPlan
            from sqlalchemy import select, func as sa_func
            rows = self.db.execute(
                select(
                    SupplyPlan.product_id,
                    SupplyPlan.site_id,
                    sa_func.coalesce(
                        sa_func.sum(SupplyPlan.planned_order_quantity), 0.0
                    ).label("total_planned"),
                ).where(
                    SupplyPlan.config_id == config_id,
                    SupplyPlan.planned_order_quantity > 0,
                ).group_by(
                    SupplyPlan.product_id,
                    SupplyPlan.site_id,
                )
            ).all()
            sp: Dict[tuple, float] = {}
            for r in rows:
                sp[(str(r.product_id), r.site_id)] = float(r.total_planned)
            cache["supply_plan_planned_qty"] = sp
        except Exception as exc:
            logger.debug("DM cache: supply_plan planned qty unavailable: %s", exc)
            cache["supply_plan_planned_qty"] = {}

        # --- vendor_product: external pricing keyed by product_id ---
        # VendorProduct uses company_id (not config_id); fetch all active
        # and take primary/lowest-priority vendor price per product.
        try:
            from app.models.supplier import VendorProduct
            from sqlalchemy import select
            rows = self.db.execute(
                select(VendorProduct).where(
                    VendorProduct.is_active == "true",
                ).order_by(
                    VendorProduct.priority.asc(),
                )
            ).scalars().all()
            vp: Dict[str, float] = {}
            for r in rows:
                pid = str(r.product_id)
                if pid not in vp:
                    vp[pid] = float(r.vendor_unit_cost or 0.0)
            cache["vendor_product_price"] = vp
        except Exception as exc:
            logger.debug("DM cache: vendor_product unavailable: %s", exc)
            cache["vendor_product_price"] = {}

        self._dm_cache = cache
        self._dm_cache_time = now
        logger.debug(
            "DM extension cache refreshed: %s",
            {k: len(v) if isinstance(v, dict) else "?" for k, v in cache.items()},
        )

    def _get_material_valuation(
        self, product_id: str, site_id: Optional[int] = None,
    ) -> Dict[str, float]:
        """Get material valuation data from DM cache.

        Returns dict with ``unit_cost`` (standard or moving avg) and
        ``cost_trend`` (0.0 placeholder — requires historical snapshots).
        """
        mv_cache = self._dm_cache.get("material_valuation", {})
        row = mv_cache.get((product_id, site_id))
        if row is None:
            return {"unit_cost": 0.0, "cost_trend": 0.0}
        price = row.standard_price or row.moving_avg_price or 0.0
        # cost_trend requires comparing against previous period — not yet
        # available in a single-snapshot cache. Return 0.0 as neutral.
        return {"unit_cost": float(price), "cost_trend": 0.0}

    def _get_order_status(self, order_id: str) -> Dict[str, str]:
        """Get outbound order status fields from DM cache."""
        oos_cache = self._dm_cache.get("outbound_order_status", {})
        row = oos_cache.get(order_id)
        if row is None:
            return {
                "delivery_status": "",
                "billing_status": "",
                "goods_issue_status": "",
            }
        return {
            "delivery_status": row.delivery_status or "",
            "billing_status": row.billing_status or "",
            "goods_issue_status": row.goods_issue_status or "",
        }

    def _derive_customer_urgency(self, order_id: str) -> float:
        """Derive a 0-1 urgency score from outbound order status.

        Simple heuristic: partially delivered or goods-issued orders are
        more urgent (customer is expecting delivery).  Fully billed orders
        are less urgent.  Default 0.5 when no status data exists.
        """
        status = self._get_order_status(order_id)
        delivery = status["delivery_status"].upper()
        gi = status["goods_issue_status"].upper()

        if not delivery and not gi:
            return 0.5

        urgency = 0.5
        # Partially delivered = high urgency (customer waiting for rest)
        if delivery in ("B",):  # SAP B = partially delivered
            urgency = 0.8
        elif delivery in ("C",):  # SAP C = fully delivered
            urgency = 0.3
        # Goods issue started but not complete
        if gi in ("B",):
            urgency = max(urgency, 0.7)
        elif gi in ("C",):
            urgency = min(urgency, 0.3)

        return urgency

    def _get_schedule_committed_qty(
        self, order_id: str, date_str: str = "",
    ) -> float:
        """Get total confirmed qty from outbound_order_line_schedule cache."""
        ols_cache = self._dm_cache.get("order_schedule_committed", {})
        key = f"{order_id}|{date_str}"
        return ols_cache.get(key, 0.0)

    def _get_work_center_details(
        self, site_id: Optional[int], work_center_code: str = "",
    ) -> Dict[str, Any]:
        """Get work center capacity details from DM cache.

        Resolves work_center_master → capacity_resource_detail chain.
        Returns capacity_hours, queue_depth (placeholder), and parallel_ops.
        """
        wcm_cache = self._dm_cache.get("work_center_master", {})
        crd_cache = self._dm_cache.get("capacity_resource_detail", {})

        wc_row = wcm_cache.get((site_id, work_center_code))
        result = {
            "work_center_capacity_hours": 8.0,
            "work_center_queue_depth": 0,
            "work_center_parallel_ops": 1,
            "work_center_queue_hours": 0.0,
        }

        if wc_row is not None:
            # Look up capacity detail via work_center_master.id
            crd_row = crd_cache.get(wc_row.id)
            if crd_row is not None:
                if crd_row.base_net_time is not None:
                    result["work_center_capacity_hours"] = float(crd_row.base_net_time)
                if crd_row.standard_parallel_ops is not None:
                    result["work_center_parallel_ops"] = int(crd_row.standard_parallel_ops)

        return result

    def _get_existing_planned_qty(
        self, product_id: str, site_id: Optional[int] = None,
    ) -> float:
        """Get existing planned supply qty from DM cache."""
        sp_cache = self._dm_cache.get("supply_plan_planned_qty", {})
        return sp_cache.get((product_id, site_id), 0.0)

    def _get_vendor_product_price(self, product_id: str) -> float:
        """Get external vendor unit price from DM cache."""
        vp_cache = self._dm_cache.get("vendor_product_price", {})
        return vp_cache.get(product_id, 0.0)

    def _get_order_velocity_trend(self, config_id: int) -> float:
        """Compute a simple order velocity trend from schedule data.

        Returns a normalized trend value (positive = accelerating orders).
        This is a rough proxy using total committed qty vs schedule count.
        Full implementation would compare rolling windows of order frequency.
        """
        ols_cache = self._dm_cache.get("order_schedule_committed", {})
        if not ols_cache:
            return 0.0
        # Placeholder: return 0.0 (neutral).  A full implementation would
        # compare recent-week committed qty against prior-week.
        return 0.0

    # ---- Heuristic state builders (enriched with DM extension data) --------

    def build_replenishment_state(
        self,
        config_id: int,
        product_id: str,
        site_id: Optional[int],
        *,
        inventory_position: float,
        on_hand: float,
        backlog: float,
        pipeline_qty: float,
        avg_daily_demand: float,
        demand_cv: float,
        lead_time_days: float,
        forecast_daily: float,
        day_of_week: int,
        day_of_month: int,
    ) -> "ReplenishmentState":
        """Build an enriched ReplenishmentState with DM extension data.

        Callers pass the core fields; this method enriches with
        material_valuation and supply_plan data from the DM cache.
        """
        from .heuristic_library.base import ReplenishmentState

        self._refresh_dm_cache(config_id)
        mv = self._get_material_valuation(product_id, site_id)
        planned = self._get_existing_planned_qty(product_id, site_id)

        return ReplenishmentState(
            inventory_position=inventory_position,
            on_hand=on_hand,
            backlog=backlog,
            pipeline_qty=pipeline_qty,
            avg_daily_demand=avg_daily_demand,
            demand_cv=demand_cv,
            lead_time_days=lead_time_days,
            forecast_daily=forecast_daily,
            day_of_week=day_of_week,
            day_of_month=day_of_month,
            cost_trend=mv["cost_trend"],
            existing_planned_qty=planned,
            unit_cost=mv["unit_cost"],
        )

    def build_atp_state(
        self,
        config_id: int,
        *,
        order_qty: float,
        order_priority: int,
        product_id: str,
        site_id: str,
        available_inventory: float,
        allocated_inventory: float,
        pipeline_qty: float,
        forecast_remaining: float,
        confirmed_orders: float,
        delivery_date_requested: Optional[str] = None,
        order_id: str = "",
    ) -> "ATPState":
        """Build an enriched ATPState with DM extension data."""
        from .heuristic_library.base import ATPState

        self._refresh_dm_cache(config_id)
        committed = self._get_schedule_committed_qty(
            order_id, delivery_date_requested or ""
        )
        status = self._get_order_status(order_id)
        urgency = self._derive_customer_urgency(order_id)

        return ATPState(
            order_qty=order_qty,
            order_priority=order_priority,
            product_id=product_id,
            site_id=site_id,
            available_inventory=available_inventory,
            allocated_inventory=allocated_inventory,
            pipeline_qty=pipeline_qty,
            forecast_remaining=forecast_remaining,
            confirmed_orders=confirmed_orders,
            delivery_date_requested=delivery_date_requested,
            schedule_committed_qty=committed,
            order_delivery_status=status["delivery_status"],
            customer_urgency=urgency,
        )

    def build_order_tracking_state(
        self,
        config_id: int,
        *,
        order_id: str,
        order_type: str,
        expected_date: str,
        current_status: str,
        quantity_ordered: float,
        quantity_received: float,
        days_overdue: float,
        supplier_on_time_rate: float,
        is_critical: bool = False,
    ) -> "OrderTrackingState":
        """Build an enriched OrderTrackingState with DM extension data."""
        from .heuristic_library.base import OrderTrackingState

        self._refresh_dm_cache(config_id)
        status = self._get_order_status(order_id)

        return OrderTrackingState(
            order_id=order_id,
            order_type=order_type,
            expected_date=expected_date,
            current_status=current_status,
            quantity_ordered=quantity_ordered,
            quantity_received=quantity_received,
            days_overdue=days_overdue,
            supplier_on_time_rate=supplier_on_time_rate,
            is_critical=is_critical,
            delivery_status=status["delivery_status"],
            billing_status=status["billing_status"],
            goods_issue_status=status["goods_issue_status"],
        )

    def build_mo_execution_state(
        self,
        config_id: int,
        site_id_int: Optional[int],
        *,
        mo_id: str,
        product_id: str,
        site_id: str,
        quantity: float,
        priority: int,
        due_date: str,
        setup_time_hours: float,
        run_time_hours: float,
        available_capacity_hours: float,
        current_wip: float,
        product_family: str = "",
        glenday_category: str = "",
        last_product_run: str = "",
        oee: float = 0.85,
        work_center_code: str = "",
    ) -> "MOExecutionState":
        """Build an enriched MOExecutionState with DM extension data."""
        from .heuristic_library.base import MOExecutionState

        self._refresh_dm_cache(config_id)
        wc = self._get_work_center_details(site_id_int, work_center_code)

        return MOExecutionState(
            mo_id=mo_id,
            product_id=product_id,
            site_id=site_id,
            quantity=quantity,
            priority=priority,
            due_date=due_date,
            setup_time_hours=setup_time_hours,
            run_time_hours=run_time_hours,
            available_capacity_hours=available_capacity_hours,
            current_wip=current_wip,
            product_family=product_family,
            glenday_category=glenday_category,
            last_product_run=last_product_run,
            oee=oee,
            work_center_capacity_hours=wc["work_center_capacity_hours"],
            work_center_queue_depth=wc["work_center_queue_depth"],
            work_center_parallel_ops=wc["work_center_parallel_ops"],
        )

    def build_quality_state(
        self,
        config_id: int,
        *,
        lot_id: str,
        product_id: str,
        defect_type: str,
        defect_severity: str,
        quantity: float,
        unit_cost: float,
        rework_cost_per_unit: float,
        scrap_value_per_unit: float,
        customer_impact: bool = False,
        order_id: str = "",
    ) -> "QualityState":
        """Build an enriched QualityState with DM extension data."""
        from .heuristic_library.base import QualityState

        self._refresh_dm_cache(config_id)
        urgency = self._derive_customer_urgency(order_id) if order_id else 0.5

        return QualityState(
            lot_id=lot_id,
            product_id=product_id,
            defect_type=defect_type,
            defect_severity=defect_severity,
            quantity=quantity,
            unit_cost=unit_cost,
            rework_cost_per_unit=rework_cost_per_unit,
            scrap_value_per_unit=scrap_value_per_unit,
            customer_impact=customer_impact,
            customer_urgency=urgency,
        )

    def build_maintenance_state(
        self,
        config_id: int,
        site_id_int: Optional[int],
        *,
        asset_id: str,
        site_id: str,
        last_maintenance_date: str,
        mtbf_days: float,
        mttr_hours: float,
        current_operating_hours: float,
        hours_since_last_pm: float,
        criticality: str,
        upcoming_production_load: float,
        maintenance_cost: float = 0.0,
        work_center_code: str = "",
        production_gap_hours: float = 0.0,
    ) -> "MaintenanceState":
        """Build an enriched MaintenanceState with DM extension data."""
        from .heuristic_library.base import MaintenanceState

        self._refresh_dm_cache(config_id)
        wc = self._get_work_center_details(site_id_int, work_center_code)

        return MaintenanceState(
            asset_id=asset_id,
            site_id=site_id,
            last_maintenance_date=last_maintenance_date,
            mtbf_days=mtbf_days,
            mttr_hours=mttr_hours,
            current_operating_hours=current_operating_hours,
            hours_since_last_pm=hours_since_last_pm,
            criticality=criticality,
            upcoming_production_load=upcoming_production_load,
            maintenance_cost=maintenance_cost,
            work_center_queue_hours=wc["work_center_queue_hours"],
            production_gap_hours=production_gap_hours,
        )

    def build_subcontracting_state(
        self,
        config_id: int,
        site_id_int: Optional[int],
        *,
        product_id: str,
        site_id: str,
        quantity_needed: float,
        internal_capacity_available: float,
        internal_cost_per_unit: float,
        external_cost_per_unit: float,
        external_lead_time_days: float,
        internal_lead_time_days: float,
        quality_risk_external: float,
        due_date: str = "",
    ) -> "SubcontractingState":
        """Build an enriched SubcontractingState with DM extension data."""
        from .heuristic_library.base import SubcontractingState

        self._refresh_dm_cache(config_id)
        mv = self._get_material_valuation(product_id, site_id_int)
        vp_price = self._get_vendor_product_price(product_id)

        # Use DM data if caller passed zero (unset) values
        internal = internal_cost_per_unit if internal_cost_per_unit > 0 else mv["unit_cost"]
        external = external_cost_per_unit if external_cost_per_unit > 0 else vp_price

        return SubcontractingState(
            product_id=product_id,
            site_id=site_id,
            quantity_needed=quantity_needed,
            internal_capacity_available=internal_capacity_available,
            internal_cost_per_unit=internal_cost_per_unit,
            external_cost_per_unit=external_cost_per_unit,
            external_lead_time_days=external_lead_time_days,
            internal_lead_time_days=internal_lead_time_days,
            quality_risk_external=quality_risk_external,
            due_date=due_date,
            internal_unit_cost=internal,
            external_unit_cost=external,
        )

    def build_forecast_adjustment_state(
        self,
        config_id: int,
        *,
        product_id: str,
        site_id: str,
        current_forecast: float,
        signal_type: str,
        signal_direction: str,
        signal_magnitude_pct: float,
        signal_confidence: float,
        forecast_error_recent: float,
        demand_cv: float = 0.0,
    ) -> "ForecastAdjustmentState":
        """Build an enriched ForecastAdjustmentState with DM extension data."""
        from .heuristic_library.base import ForecastAdjustmentState

        self._refresh_dm_cache(config_id)
        velocity = self._get_order_velocity_trend(config_id)

        return ForecastAdjustmentState(
            product_id=product_id,
            site_id=site_id,
            current_forecast=current_forecast,
            signal_type=signal_type,
            signal_direction=signal_direction,
            signal_magnitude_pct=signal_magnitude_pct,
            signal_confidence=signal_confidence,
            forecast_error_recent=forecast_error_recent,
            demand_cv=demand_cv,
            order_velocity_trend=velocity,
        )

    def build_inventory_buffer_state(
        self,
        config_id: int,
        site_id_int: Optional[int],
        *,
        product_id: str,
        site_id: str,
        current_safety_stock: float,
        avg_daily_demand: float,
        demand_cv: float,
        lead_time_days: float,
        lead_time_cv: float,
        service_level_target: float,
        recent_stockout_count: int,
        recent_excess_days: int,
        holding_cost_per_unit: float = 0.0,
        stockout_cost_per_unit: float = 0.0,
    ) -> "InventoryBufferState":
        """Build an enriched InventoryBufferState with DM extension data."""
        from .heuristic_library.base import InventoryBufferState

        self._refresh_dm_cache(config_id)
        mv = self._get_material_valuation(product_id, site_id_int)

        return InventoryBufferState(
            product_id=product_id,
            site_id=site_id,
            current_safety_stock=current_safety_stock,
            avg_daily_demand=avg_daily_demand,
            demand_cv=demand_cv,
            lead_time_days=lead_time_days,
            lead_time_cv=lead_time_cv,
            service_level_target=service_level_target,
            recent_stockout_count=recent_stockout_count,
            recent_excess_days=recent_excess_days,
            holding_cost_per_unit=holding_cost_per_unit,
            stockout_cost_per_unit=stockout_cost_per_unit,
            cost_trend=mv["cost_trend"],
        )

    def invalidate_dm_cache(self) -> None:
        """Force DM extension cache to refresh on next access."""
        self._dm_cache = {}
        self._dm_cache_time = None

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
        if self.authorization_service is not None:
            pending = self.get_pending_authorizations()
            status['pending_authorizations'] = len(pending)
        return status
