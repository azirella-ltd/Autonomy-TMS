import random
import statistics
import logging
from enum import Enum
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .beer_game_xai_explain import (
    Obs,
    Forecast,
    RoleParams,
    SupervisorContext,
    explain_role_decision,
    explain_supervisor_adjustment,
)

# Import the Autonomy LLM agent only when needed to avoid unnecessary dependencies
try:  # pragma: no cover - optional import
    from .llm_agent import AutonomyLLMError, LLMAgent, LLMStrategy
except Exception:  # pragma: no cover - tests may not have openai deps
    class AutonomyLLMError(RuntimeError):  # type: ignore
        """Fallback error class used when the real LLM agent is unavailable."""

        pass

    LLMAgent = None  # type: ignore
    LLMStrategy = None  # type: ignore

# Import TRM agent with fallback
try:
    from .trm_agent import compute_trm_order, get_trm_agent
except Exception:
    compute_trm_order = None  # type: ignore
    get_trm_agent = None  # type: ignore

# Import GNN agent with fallback
try:
    from .gnn_agent import compute_gnn_order, get_gnn_agent
except Exception:
    compute_gnn_order = None  # type: ignore
    get_gnn_agent = None  # type: ignore

# Import RL agent with fallback
try:
    from app.agents.rl_agent import RLAgent, create_rl_agent
except Exception:
    RLAgent = None  # type: ignore
    create_rl_agent = None  # type: ignore


logger = logging.getLogger(__name__)

class AgentType(Enum):
    RETAILER = "retailer"
    WHOLESALER = "wholesaler"
    DISTRIBUTOR = "distributor"
    MANUFACTURER = "manufacturer"
    SUPPLIER = "supplier"

class AgentStrategy(Enum):
    NAIVE = "naive"  # Simple strategy, always orders based on current demand
    BULLWHIP = "bullwhip"  # Tends to over-order when demand increases
    CONSERVATIVE = "conservative"  # Maintains stable orders
    RANDOM = "random"  # Random ordering for baseline
    PID = "pid_heuristic"  # Proportional-integral-derivative controller
    TRM = "trm"  # Tiny Recursive Model (7M params, fast inference)
    GNN = "gnn"  # Graph Neural Network (128M params, network-aware)
    RL = "rl"  # Reinforcement Learning (PPO/SAC/A2C via Stable-Baselines3)
    LLM = "llm"  # Autonomy LLM strategy
    LLM_SUPERVISED = "llm_supervised"  # Autonomy LLM with centralized supervisor overrides
    LLM_GLOBAL = "llm_global"  # Single Autonomy LLM orchestrating all roles
    AUTONOMY_DTCE = "autonomy_dtce"  # Decentralized twin coordinated ensemble
    AUTONOMY_DTCE_CENTRAL = "autonomy_dtce_central"  # DTCE with central override
    AUTONOMY_DTCE_GLOBAL = "autonomy_dtce_global"  # Single agent orchestrating the network
    SITE_AGENT = "site_agent"  # Powell SiteAgent with deterministic engines + TRM


@dataclass
class PIDControllerState:
    history: deque = field(default_factory=lambda: deque(maxlen=4))
    integral: float = 0.0
    previous_error: Optional[float] = None


@dataclass
class AgentDecision:
    """Container for an agent's order decision and its rationale."""

    quantity: int
    reason: str
    fallback_used: bool = False
    original_strategy: Optional[str] = None
    fallback_reason: Optional[str] = None


class AutonomyCoordinator:
    """Coordinates decentralized Autonomy agents with an optional override."""

    def __init__(self, default_override: float = 0.05, history_length: int = 8):
        self.default_override = self._clamp(default_override)
        self.history_length = history_length
        self.override_pct: Dict[AgentType, float] = {}
        self.order_history: Dict[AgentType, deque] = {}

    @staticmethod
    def _clamp(pct: Optional[float]) -> float:
        """Clamp override percentage to the 5%-50% range."""
        try:
            pct_val = float(pct) if pct is not None else 0.05
        except (TypeError, ValueError):
            pct_val = 0.05
        pct_val = abs(pct_val)
        pct_val = max(0.05, min(pct_val, 0.5))
        return pct_val

    def set_override_pct(self, agent_type: AgentType, pct: Optional[float]) -> None:
        """Set an override percentage for a specific agent."""
        if pct is None:
            self.override_pct.pop(agent_type, None)
            return
        self.override_pct[agent_type] = self._clamp(pct)

    def get_override_pct(self, agent_type: AgentType) -> float:
        return self.override_pct.get(agent_type, self.default_override)

    def _record_order(self, agent_type: AgentType, order: int) -> None:
        history = self.order_history.setdefault(agent_type, deque(maxlen=self.history_length))
        history.append(order)

    def register_decision(self, agent_type: AgentType, order: int) -> None:
        """Record the final decision from a decentralized agent."""
        self._record_order(agent_type, order)

    def _network_average(self, exclude: AgentType) -> Optional[float]:
        values = [history[-1] for atype, history in self.order_history.items() if atype != exclude and history]
        if values:
            return sum(values) / len(values)
        return None

    def apply_override(
        self,
        agent_type: AgentType,
        base_order: float,
        context: Optional[Dict[str, Any]] = None,
        week: Optional[int] = None,
    ) -> Tuple[int, Optional[str]]:
        """Apply the centralized override to the base order and return an explanation."""

        base = max(0.0, float(base_order))
        network_avg = self._network_average(agent_type)
        target = base
        reasons: List[str] = []
        global_notes: List[str] = []

        if network_avg is not None:
            target = (base + network_avg) / 2.0
            reasons.append(f"align toward network avg {network_avg:.1f}")

        backlog = float(context.get("backlog", 0)) if context else 0.0
        inventory = float(context.get("inventory", 0)) if context else 0.0

        if backlog > inventory:
            target = max(target, base + (backlog - inventory))
            reasons.append("backlog exceeds on-hand")
        elif inventory > backlog * 2 and inventory > 0:
            target = min(target, base - (inventory - backlog) / 2.0)
            reasons.append("inventory well above backlog")

        pct = self.get_override_pct(agent_type)
        max_adjustment = base * pct
        adjustment = target - base
        if adjustment > 0:
            adjustment = min(adjustment, max_adjustment)
        else:
            adjustment = max(adjustment, -max_adjustment)

        adjusted = max(0.0, base + adjustment)
        final_order = int(round(adjusted))
        self._record_order(agent_type, final_order)

        pre_qty = int(round(base))
        if context:
            global_notes.append(f"inventory {inventory:.1f}, backlog {backlog:.1f}")
            pipeline = context.get("pipeline")
            if pipeline is not None:
                global_notes.append(f"pipeline {float(pipeline):.1f}")

        week_val = week if week is not None else int(context.get("week", 0)) if context else 0
        supervisor_ctx = SupervisorContext(
            max_scale_pct=pct * 100,
            rule="stability_smoothing",
            reasons=reasons,
        )
        explanation = explain_supervisor_adjustment(
            role=agent_type.name.replace("_", " ").title(),
            week=week_val,
            pre_qty=pre_qty,
            post_qty=final_order,
            ctx=supervisor_ctx,
            global_notes=global_notes or None,
        )

        return final_order, explanation


class AutonomyGlobalController:
    """Orchestrates a single Autonomy agent across the entire supply chain."""

    def __init__(self, history_length: int = 12):
        self.history_length = max(3, int(history_length))
        self.round_marker: Optional[int] = None
        self.base_orders: Dict[AgentType, float] = {}
        self.context: Dict[AgentType, Dict[str, Any]] = {}
        self.plan: Dict[AgentType, int] = {}
        self.last_orders: Dict[AgentType, deque] = {}
        self.network_targets: deque = deque(maxlen=self.history_length)

    def _reset_round(self, round_number: int) -> None:
        if self.round_marker != round_number:
            self.round_marker = round_number
            self.base_orders.clear()
            self.context.clear()
            self.plan.clear()

    def _determine_target_flow(self) -> float:
        if AgentType.RETAILER in self.base_orders:
            return max(0.0, float(self.base_orders[AgentType.RETAILER]))
        if self.base_orders:
            return max(0.0, sum(self.base_orders.values()) / len(self.base_orders))
        if self.network_targets:
            return max(0.0, float(self.network_targets[-1]))
        return 0.0

    def _peer_anchor(self, requesting: AgentType) -> Optional[float]:
        peers = [qty for role, qty in self.plan.items() if role != requesting]
        if peers:
            return sum(peers) / len(peers)
        return None

    def plan_order(
        self,
        agent_type: AgentType,
        round_number: int,
        base_order: float,
        context: Optional[Dict[str, Any]] = None,
        prev_order: Optional[int] = None,
    ) -> Tuple[int, Optional[str]]:
        self._reset_round(round_number)

        safe_base = max(0.0, float(base_order))
        ctx = context or {}
        self.base_orders[agent_type] = safe_base
        self.context[agent_type] = ctx

        target_flow = self._determine_target_flow()
        peer_anchor = self._peer_anchor(agent_type)
        if peer_anchor is not None:
            target_flow = 0.6 * target_flow + 0.4 * peer_anchor

        def _to_float(value: Any) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return 0.0

        backlog = _to_float(ctx.get("backlog"))
        inventory = _to_float(ctx.get("inventory"))
        pipeline = _to_float(ctx.get("pipeline"))

        adjusted = 0.65 * safe_base + 0.35 * target_flow
        reasons: List[str] = []

        if backlog > inventory:
            adjusted += backlog - inventory
            reasons.append("protect service level (backlog > inventory)")
        elif inventory > backlog and inventory > 0:
            reduction = min(inventory - backlog, adjusted * 0.3)
            if reduction > 0:
                adjusted -= reduction
                reasons.append("trim excess inventory")

        if pipeline > target_flow * 1.5 and pipeline > 0:
            dampen = min(pipeline - target_flow * 1.5, adjusted * 0.25)
            if dampen > 0:
                adjusted -= dampen
                reasons.append("pipeline congestion")

        prev_reference = prev_order
        if prev_reference is None:
            prev_history = self.last_orders.get(agent_type)
            if prev_history:
                prev_reference = prev_history[-1]

        if prev_reference is not None:
            max_step = max(3.0, abs(prev_reference) * 0.5)
            upper = prev_reference + max_step
            lower = max(0.0, prev_reference - max_step)
            if adjusted > upper:
                adjusted = upper
                reasons.append("limit step-up for stability")
            elif adjusted < lower:
                adjusted = lower
                reasons.append("limit step-down for stability")

        final_qty = int(round(max(0.0, adjusted)))
        self.plan[agent_type] = final_qty
        history = self.last_orders.setdefault(agent_type, deque(maxlen=self.history_length))
        history.append(final_qty)
        self.network_targets.append(target_flow)

        global_notes: List[str] = [f"target flow {target_flow:.1f}"]
        if peer_anchor is not None:
            global_notes.append(f"peer avg {peer_anchor:.1f}")
        if pipeline > 0:
            global_notes.append(f"pipeline {pipeline:.1f}")

        supervisor_ctx = SupervisorContext(
            max_scale_pct=100.0,
            rule="global_balancing",
            reasons=reasons,
        )
        explanation = explain_supervisor_adjustment(
            role=f"{agent_type.name.replace('_', ' ').title()} (Global)",
            week=round_number,
            pre_qty=int(round(safe_base)),
            post_qty=final_qty,
            ctx=supervisor_ctx,
            global_notes=global_notes or None,
        )

        return final_qty, explanation

class SimulationAgent:
    def __init__(
        self,
        agent_id: int,
        agent_type: AgentType,
        strategy: AgentStrategy = AgentStrategy.NAIVE,
        can_see_demand: bool = False,
        initial_inventory: int = 12,
        initial_orders: int = 4,
        llm_model: Optional[str] = None,
        central_coordinator: Optional[AutonomyCoordinator] = None,
        global_controller: Optional[AutonomyGlobalController] = None,
        model_path: Optional[str] = None,
    ):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.strategy = strategy
        self.can_see_demand = can_see_demand
        self.inventory = initial_inventory
        self.backlog = 0
        self.pipeline = [initial_orders] * 2  # Orders in the pipeline (2 rounds of lead time)
        self.order_history = []
        self.demand_history = []
        self.last_order = 0
        # Autonomy LLM specific configuration
        self.llm_model = llm_model
        self.llm_strategy_name: str = "balanced"
        self._llm_agent: Optional[LLMAgent] = None
        # Optional centralized coordinator for Autonomy variants
        self.central_coordinator = central_coordinator
        # Optional global coordinator when a single agent manages all roles
        self.global_controller = global_controller
        self.last_explanation: Optional[str] = None
        # Path to trained model checkpoint (config-specific)
        self.model_path = model_path
        self._last_node_label: str = agent_type.value.title()
        self._last_node_key: str = agent_type.value
        # PID controller state
        self._pid_state = PIDControllerState()
        self._pid_alpha = 0.4
        self._pid_beta = 0.4
        self._pid_gamma = 0.05
        self._pid_delta = 0.1
        self._pid_target_multiplier = 1.0
        self._pid_base_stock = max(initial_inventory + initial_orders, initial_orders * 4)
        self._pid_integral_clip: Tuple[float, float] = (-500.0, 500.0)
        self._pid_max_order: Optional[int] = 500
        # Fallback tracking for AI strategies
        self._fallback_used: bool = False
        self._fallback_reason: Optional[str] = None
        self.reset_for_strategy()

    def make_decision(
        self,
        current_round: int,
        current_demand: Optional[int] = None,
        upstream_data: Optional[Dict] = None,
        local_state: Optional[Dict[str, Any]] = None,
    ) -> AgentDecision:
        """
        Make an order decision based on the agent's strategy and available information.
        
        Args:
            current_round: Current game round
            current_demand: Current customer demand (only visible to retailer if configured)
            upstream_data: Data from upstream (e.g., orders from downstream)
            
        Returns:
            AgentDecision: The finalized order quantity and explanation
        """
        # Reset fallback tracking for this decision
        self._fallback_used = False
        self._fallback_reason = None

        # Update demand history if visible
        if current_demand is not None and (self.agent_type == AgentType.RETAILER or self.can_see_demand):
            self.demand_history.append(current_demand)

        # Normalize local state inputs for advanced strategies
        local_state = local_state or {}
        inventory_level = int(local_state.get("inventory", self.inventory))
        backlog_level = int(local_state.get("backlog", self.backlog))
        inventory_level = max(0, inventory_level)
        backlog_level = max(0, backlog_level)

        shipments_raw = local_state.get("incoming_shipments", self.pipeline)
        processed_shipments: List[float] = []
        if isinstance(shipments_raw, (list, tuple)):
            for item in shipments_raw:
                if isinstance(item, (int, float)):
                    processed_shipments.append(float(item))
                elif isinstance(item, dict):
                    qty = item.get("quantity") or item.get("qty")
                    if qty is not None:
                        try:
                            processed_shipments.append(float(qty))
                        except (TypeError, ValueError):
                            continue
        if not processed_shipments:
            processed_shipments = [float(x) for x in self.pipeline]

        # Keep internal state aligned with the most recent observation
        self.inventory = inventory_level
        self.backlog = backlog_level
        self._last_node_label = str(
            local_state.get("node_label")
            or local_state.get("node_name")
            or self.agent_type.value.title()
        )
        self._last_node_key = str(local_state.get("node_key") or self.agent_type.value)

        prev_order = self.last_order
        self.last_explanation = None

        effective_demand = current_demand
        if self.strategy == AgentStrategy.NAIVE and effective_demand is None:
            downstream_orders = None
            if upstream_data:
                downstream_orders = upstream_data.get("downstream_orders")
                if isinstance(downstream_orders, list):
                    downstream_orders = {
                        str(idx): value for idx, value in enumerate(downstream_orders)
                    }
            if isinstance(downstream_orders, dict) and downstream_orders:
                try:
                    effective_demand = sum(int(v) for v in downstream_orders.values())
                except (TypeError, ValueError):
                    effective_demand = sum(
                        int(v) for v in downstream_orders.values() if isinstance(v, (int, float))
                    )

        # Make decision based on strategy
        local_total_demand = None
        if isinstance(local_state, dict):
            local_total_demand = local_state.get("total_demand")
            if local_total_demand is None:
                local_total_demand = local_state.get("incoming_orders")

        if self.strategy == AgentStrategy.NAIVE:
            order = self._naive_strategy(
                effective_demand,
                backlog_level,
                inventory_level,
                local_state.get("on_order", 0) if isinstance(local_state, dict) else 0,
                debug_context=(local_state.get("debug_inventory") if isinstance(local_state, dict) else None),
                target_inventory=local_state.get("target_inventory") if isinstance(local_state, dict) else None,
                bleed_factor=local_state.get("bleed_factor") if isinstance(local_state, dict) else None,
            )
        elif self.strategy == AgentStrategy.BULLWHIP:
            order = self._bullwhip_strategy(current_demand, upstream_data)
        elif self.strategy == AgentStrategy.CONSERVATIVE:
            order = self._conservative_strategy(current_demand)
        elif self.strategy == AgentStrategy.PID:
            order = self._pid_strategy(
                current_round,
                current_demand,
                upstream_data or {},
                inventory_level,
                backlog_level,
                processed_shipments,
                local_total_demand,
            )
        elif self.strategy == AgentStrategy.TRM:
            order = self._trm_strategy(
                current_round,
                current_demand,
                upstream_data or {},
                inventory_level,
                backlog_level,
                processed_shipments,
            )
        elif self.strategy == AgentStrategy.GNN:
            order = self._gnn_strategy(
                current_round,
                current_demand,
                upstream_data or {},
                inventory_level,
                backlog_level,
                processed_shipments,
            )
        elif self.strategy == AgentStrategy.RL:
            order = self._rl_strategy(
                current_round,
                current_demand,
                upstream_data or {},
                inventory_level,
                backlog_level,
                processed_shipments,
            )
        elif self.strategy in (
            AgentStrategy.LLM,
            AgentStrategy.LLM_SUPERVISED,
            AgentStrategy.LLM_GLOBAL,
        ):
            try:
                if self.strategy == AgentStrategy.LLM:
                    order = self._llm_strategy(
                        current_round,
                        current_demand,
                        upstream_data,
                        inventory_level,
                        backlog_level,
                        processed_shipments,
                    )
                elif self.strategy == AgentStrategy.LLM_SUPERVISED:
                    order = self._llm_supervised_strategy(
                        current_round,
                        current_demand,
                        upstream_data,
                        inventory_level,
                        backlog_level,
                        processed_shipments,
                    )
                else:
                    order = self._llm_global_strategy(
                        current_round,
                        prev_order,
                        current_demand,
                        upstream_data,
                        inventory_level,
                        backlog_level,
                        processed_shipments,
                    )
            except AutonomyLLMError as exc:
                order = self._handle_llm_failure(
                    error=exc,
                    current_round=current_round,
                    prev_order=prev_order,
                    current_demand=current_demand,
                    upstream_data=upstream_data,
                    inventory_level=inventory_level,
                    backlog_level=backlog_level,
                    incoming_shipments=processed_shipments,
                )
        elif self.strategy == AgentStrategy.AUTONOMY_DTCE:
            order = self._autonomy_dtce_strategy(
                current_round,
                prev_order,
                current_demand,
                upstream_data,
                inventory_level,
                backlog_level,
                processed_shipments,
            )
        elif self.strategy == AgentStrategy.AUTONOMY_DTCE_CENTRAL:
            order = self._autonomy_central_strategy(
                current_round,
                prev_order,
                current_demand,
                upstream_data,
                inventory_level,
                backlog_level,
                processed_shipments,
            )
        elif self.strategy == AgentStrategy.AUTONOMY_DTCE_GLOBAL:
            order = self._autonomy_global_strategy(
                current_round,
                prev_order,
                current_demand,
                upstream_data,
                inventory_level,
                backlog_level,
                processed_shipments,
            )
        elif self.strategy == AgentStrategy.SITE_AGENT:
            order = self._site_agent_strategy(
                current_round,
                prev_order,
                current_demand,
                upstream_data,
                inventory_level,
                backlog_level,
                processed_shipments,
            )
        else:  # RANDOM fallback
            order = self._random_strategy()

        order = max(0, int(round(order)))
        self.last_order = order
        self.order_history.append(order)
        reason = self.get_last_explanation_comment()
        return AgentDecision(
            quantity=order,
            reason=reason,
            fallback_used=self._fallback_used,
            original_strategy=self.strategy.value if self._fallback_used else None,
            fallback_reason=self._fallback_reason,
        )

    def reset_for_strategy(self) -> None:
        self._pid_state = PIDControllerState()

    def configure_pid(
        self,
        *,
        alpha: Optional[float] = None,
        beta: Optional[float] = None,
        gamma: Optional[float] = None,
        delta: Optional[float] = None,
        target_multiplier: Optional[float] = None,
        integral_clip: Optional[Tuple[float, float]] = None,
        max_order: Optional[int] = None,
        base_stock: Optional[int] = None,
    ) -> None:
        """Update PID controller hyperparameters and reset its state."""

        if alpha is not None:
            self._pid_alpha = float(alpha)
        if beta is not None:
            self._pid_beta = float(beta)
        if gamma is not None:
            self._pid_gamma = float(gamma)
        if delta is not None:
            self._pid_delta = float(delta)
        if target_multiplier is not None:
            self._pid_target_multiplier = float(target_multiplier)
        if integral_clip is not None:
            try:
                lo, hi = integral_clip
                self._pid_integral_clip = (float(lo), float(hi))
            except (TypeError, ValueError):
                pass
        if max_order is not None:
            self._pid_max_order = int(max_order)
        if base_stock is not None:
            try:
                self._pid_base_stock = max(0, int(base_stock))
            except (TypeError, ValueError):
                pass
        self.reset_for_strategy()

    def _get_downstream_role_name(self) -> Optional[str]:
        mapping = {
            AgentType.WHOLESALER: AgentType.RETAILER.value,
            AgentType.DISTRIBUTOR: AgentType.WHOLESALER.value,
            AgentType.MANUFACTURER: AgentType.DISTRIBUTOR.value,
            AgentType.SUPPLIER: AgentType.MANUFACTURER.value,
        }
        return mapping.get(self.agent_type)
    
    def _naive_strategy(
        self,
        current_demand: Optional[int],
        backlog: float,
        inventory: float,
        on_order: float = 0.0,
        *,
        debug_context: Optional[Dict[str, Any]] = None,
        target_inventory: Optional[float] = None,
        bleed_factor: Optional[float] = None,
    ) -> int:
        """Dampen toward a target: demand plus a bleed toward target inventory."""
        demand = max(0.0, float(current_demand or 0.0)) + max(0.0, float(backlog or 0.0))
        try:
            bleed = max(0.0, float(bleed_factor)) if bleed_factor is not None else 1.0
        except (TypeError, ValueError):
            bleed = 1.0

        tgt = 0.0
        try:
            tgt = float(target_inventory) if target_inventory is not None else 0.0
        except (TypeError, ValueError):
            tgt = 0.0

        end_inv = inventory
        if isinstance(debug_context, dict):
            ctx_end = debug_context.get("ending_inventory")
            try:
                if ctx_end is not None:
                    end_inv = float(ctx_end)
            except (TypeError, ValueError):
                pass

        try:
            end_inv = float(end_inv)
        except (TypeError, ValueError):
            end_inv = 0.0

        desired = demand + bleed * (tgt - end_inv)
        order_qty = max(0, int(round(desired)))

        self.last_explanation = (
            f"Naive damped | demand={demand:.1f} end_inv={end_inv:.1f} "
            f"tgt={tgt:.1f} bleed={bleed:.2f} order_qty={order_qty}"
        )
        return order_qty

    def _bullwhip_strategy(self, current_demand: Optional[int], upstream_data: Optional[Dict]) -> int:
        """Tend to over-order when demand increases."""
        if not self.demand_history:
            self.last_explanation = (
                "Bullwhip heuristic | insufficient history, repeat last order"
            )
            return self.last_order

        avg_demand = sum(self.demand_history) / len(self.demand_history)
        last_demand = self.demand_history[-1]

        # If demand is increasing, over-order
        if last_demand > avg_demand * 1.2:  # 20% increase
            amplified = int(round(last_demand * 1.5))
            self.last_explanation = (
                "Bullwhip heuristic | demand spike "
                f"{last_demand:.1f} vs avg {avg_demand:.1f}, amplify to {amplified}"
            )
            return amplified

        self.last_explanation = (
            "Bullwhip heuristic | demand stable, follow last observed demand "
            f"{last_demand:.1f}"
        )
        return int(round(last_demand))

    def _conservative_strategy(self, current_demand: Optional[int]) -> int:
        """Maintain stable orders, avoid large fluctuations."""
        if not self.order_history:
            self.last_explanation = "Conservative smoothing | no history, default to 4"
            return 4  # Default order

        # Moving average of last 3 orders
        recent_orders = self.order_history[-3:] if len(self.order_history) >= 3 else self.order_history
        avg_order = sum(recent_orders) / len(recent_orders)
        self.last_explanation = (
            "Conservative smoothing | average recent orders "
            f"{[int(o) for o in recent_orders]} -> {avg_order:.1f}"
        )
        return int(round(avg_order))

    def _pid_strategy(
        self,
        current_round: int,
        current_demand: Optional[int],
        upstream_data: Dict[str, Any],
        inventory_level: int,
        backlog_level: int,
        incoming_shipments: List[float],
        local_demand_signal: Optional[Any] = None,
    ) -> int:
        downstream_role = self._get_downstream_role_name()
        previous_orders_by_role: Dict[str, int] = upstream_data.get("previous_orders_by_role", {})
        downstream_orders_map: Dict[str, Any] = upstream_data.get("downstream_orders", {})

        observed_demand: Optional[float]
        if local_demand_signal is not None:
            try:
                observed_demand = float(local_demand_signal)
            except (TypeError, ValueError):
                observed_demand = None
        else:
            observed_demand = None

        if observed_demand is None and current_demand is not None and (
            self.agent_type == AgentType.RETAILER or self.can_see_demand
        ):
            observed_demand = float(current_demand)
        elif observed_demand is None and downstream_orders_map:
            demand_sum = 0.0
            for value in downstream_orders_map.values():
                try:
                    demand_sum += max(0.0, float(value))
                except (TypeError, ValueError):
                    continue
            observed_demand = demand_sum
        elif observed_demand is None and downstream_role:
            try:
                observed_demand = float(previous_orders_by_role.get(downstream_role))
            except (TypeError, ValueError):
                observed_demand = None

        if observed_demand is None:
            observed_demand = (
                self._pid_state.history[-1] if self._pid_state.history else self.last_order
            )

        observed_demand = max(0, int(round(observed_demand)))
        self._pid_state.history.append(observed_demand)
        forecast = (
            sum(self._pid_state.history) / len(self._pid_state.history)
            if self._pid_state.history
            else float(observed_demand)
        )

        inbound_sum = float(sum(incoming_shipments)) if incoming_shipments else 0.0
        inventory_position = float(inventory_level - backlog_level) + inbound_sum

        demand_anchor = max(
            forecast,
            float(previous_orders_by_role.get(downstream_role, 0)) if downstream_role else 0.0,
            float(previous_orders_by_role.get("market_demand", 0)) if previous_orders_by_role else 0.0,
            1.0,
        )
        target_inventory = float(
            max(
                self._pid_base_stock,
                int(round(self._pid_target_multiplier * demand_anchor)),
            )
        )
        error = target_inventory - inventory_position
        # Prevent runaway negative error when inventory is already far above target.
        max_negative_error = -1.0 * max(self._pid_base_stock, demand_anchor * 2.0)
        if error < max_negative_error:
            error = max_negative_error

        self._pid_state.integral += error
        lo, hi = self._pid_integral_clip
        if hi is None or lo is None:
            hi = max(self._pid_base_stock * 3.0, demand_anchor * 3.0)
            lo = -hi
        self._pid_state.integral = max(lo, min(hi, self._pid_state.integral))

        delta_error = 0.0
        if self._pid_state.previous_error is not None:
            delta_error = error - self._pid_state.previous_error
        self._pid_state.previous_error = error

        control = (
            self._pid_alpha * forecast
            + self._pid_beta * error
            + self._pid_gamma * self._pid_state.integral
            + self._pid_delta * delta_error
        )

        order = demand_anchor + control
        if self._pid_max_order is not None:
            order = min(self._pid_max_order, order)

        order = max(0.0, order)
        self.demand_history.append(observed_demand)
        self.last_explanation = (
            "PID heuristic | "
            f"demand_avg={forecast:.1f} error={error:.1f} integral={self._pid_state.integral:.1f} "
            f"derivative={delta_error:.1f} | "
            f"demand_anchor={demand_anchor:.1f} "
            f"inventory={inventory_level} backlog={backlog_level} inbound={inbound_sum:.1f}"
        )
        return int(round(order))

    def _trm_strategy(
        self,
        current_round: int,
        current_demand: Optional[int],
        upstream_data: Dict[str, Any],
        inventory_level: int,
        backlog_level: int,
        incoming_shipments: List[float],
    ) -> int:
        """
        TRM (Tiny Recursive Model) strategy using 7M parameter neural network.

        Falls back to base stock heuristic if TRM model is not available.
        """
        if compute_trm_order is None:
            # TRM not available, use fallback
            logger.warning("TRM agent not available, using base stock fallback")
            self._fallback_used = True
            self._fallback_reason = "TRM model not available - module not loaded"
            return self._base_stock_fallback(current_demand, inventory_level, backlog_level, incoming_shipments)

        try:
            # Build context for TRM agent
            context = {
                "round_number": current_round,
                "upstream_data": upstream_data,
            }

            # Create a simplified node object for TRM
            class SimpleNode:
                def __init__(self, name, node_type, inventory, backlog, pipeline_shipments):
                    self.name = name
                    self.node_type = node_type
                    self.inventory = inventory
                    self.backlog = backlog
                    self.pipeline_shipments = pipeline_shipments

                    # TRM expects incoming_order for demand history
                    self.incoming_order = 0.0

            # Create node object
            node = SimpleNode(
                name=f"{self.agent_type.value}_{self.id}",
                node_type=self.agent_type.value,
                inventory=inventory_level,
                backlog=backlog_level,
                pipeline_shipments=[type('obj', (object,), {'quantity': q})() for q in incoming_shipments]
            )

            # Set incoming order (current demand)
            if current_demand is not None:
                node.incoming_order = float(current_demand)
            elif upstream_data:
                downstream_orders = upstream_data.get("downstream_orders", {})
                if downstream_orders:
                    node.incoming_order = float(sum(downstream_orders.values()))

            # Get TRM decision using config-specific model if available
            order_qty = compute_trm_order(node, context, model_path=self.model_path)
            order = max(0, int(round(order_qty)))

            # Update demand history
            if current_demand is not None:
                self.demand_history.append(current_demand)

            self.last_explanation = (
                f"TRM (Tiny Recursive Model) | "
                f"inventory={inventory_level} backlog={backlog_level} "
                f"pipeline={sum(incoming_shipments):.1f} order={order}"
            )

            return order

        except Exception as e:
            logger.error(f"TRM strategy failed: {e}")
            self._fallback_used = True
            self._fallback_reason = f"TRM inference failed: {str(e)}"
            return self._base_stock_fallback(current_demand, inventory_level, backlog_level, incoming_shipments)

    def _base_stock_fallback(
        self,
        current_demand: Optional[int],
        inventory_level: int,
        backlog_level: int,
        incoming_shipments: List[float],
    ) -> int:
        """Simple base stock fallback when TRM is unavailable."""
        # Estimate demand
        if current_demand is not None:
            demand = float(current_demand)
        elif self.demand_history:
            demand = sum(self.demand_history[-5:]) / len(self.demand_history[-5:])
        else:
            demand = 50.0  # Default

        # Calculate inventory position
        pipeline = sum(incoming_shipments) if incoming_shipments else 0.0
        inv_position = inventory_level + pipeline - backlog_level

        # Base stock policy: order up to (demand * (lead_time + safety))
        lead_time = 2
        safety_factor = 2
        base_stock = demand * (lead_time + safety_factor)

        order = max(0, base_stock - inv_position)
        return int(round(order))

    def _gnn_strategy(
        self,
        current_round: int,
        current_demand: Optional[int],
        upstream_data: Dict[str, Any],
        inventory_level: int,
        backlog_level: int,
        incoming_shipments: List[float],
    ) -> int:
        """
        GNN (Graph Neural Network) strategy using 128M+ parameter model.

        Falls back to base stock heuristic if GNN model is not available.
        Uses config-specific model via self.model_path.
        """
        if compute_gnn_order is None:
            # GNN not available, use fallback
            logger.warning("GNN agent not available, using base stock fallback")
            self._fallback_used = True
            self._fallback_reason = "GNN model not available - module not loaded"
            return self._base_stock_fallback(current_demand, inventory_level, backlog_level, incoming_shipments)

        try:
            # Build context for GNN agent
            context = {
                "round_number": current_round,
                "upstream_data": upstream_data,
            }

            # Create a simplified node object for GNN
            class SimpleNode:
                def __init__(self, name, node_type, inventory, backlog, pipeline_shipments, incoming_order):
                    self.name = name
                    self.node_type = node_type
                    self.inventory = inventory
                    self.backlog = backlog
                    self.pipeline_shipments = pipeline_shipments
                    self.incoming_order = incoming_order

            # Create node object
            node = SimpleNode(
                name=f"{self.agent_type.value}_{self.agent_id}",
                node_type=self.agent_type.value,
                inventory=inventory_level,
                backlog=backlog_level,
                pipeline_shipments=[type('obj', (object,), {'quantity': q})() for q in incoming_shipments],
                incoming_order=0.0
            )

            # Set incoming order (current demand)
            if current_demand is not None:
                node.incoming_order = float(current_demand)
            elif upstream_data:
                downstream_orders = upstream_data.get("downstream_orders", {})
                if downstream_orders:
                    node.incoming_order = float(sum(downstream_orders.values()))

            # Get GNN decision using config-specific model if available
            order_qty = compute_gnn_order(node, context, model_path=self.model_path)
            order = max(0, int(round(order_qty)))

            # Update demand history
            if current_demand is not None:
                self.demand_history.append(current_demand)

            self.last_explanation = (
                f"GNN (Graph Neural Network) | "
                f"inventory={inventory_level} backlog={backlog_level} "
                f"pipeline={sum(incoming_shipments):.1f} order={order}"
            )

            return order

        except Exception as e:
            logger.error(f"GNN strategy failed: {e}")
            self._fallback_used = True
            self._fallback_reason = f"GNN inference failed: {str(e)}"
            return self._base_stock_fallback(current_demand, inventory_level, backlog_level, incoming_shipments)

    def _rl_strategy(
        self,
        current_round: int,
        current_demand: Optional[int],
        upstream_data: Dict[str, Any],
        inventory_level: int,
        backlog_level: int,
        incoming_shipments: List[float],
    ) -> int:
        """
        RL (Reinforcement Learning) strategy using Stable-Baselines3 (PPO/SAC/A2C).

        Falls back to base stock heuristic if RL model is not available.
        Uses config-specific model via self.model_path.
        """
        if RLAgent is None or create_rl_agent is None:
            # RL not available, use fallback
            logger.warning("RL agent not available, using base stock fallback")
            self._fallback_used = True
            self._fallback_reason = "RL model not available - Stable-Baselines3 not installed"
            return self._base_stock_fallback(current_demand, inventory_level, backlog_level, incoming_shipments)

        try:
            # Get or create RL agent with config-specific model
            if not hasattr(self, '_rl_agent_instance') or self._rl_agent_instance is None:
                self._rl_agent_instance = create_rl_agent(
                    algorithm="PPO",  # Default algorithm
                    model_path=self.model_path
                )

            # Build context for RL agent
            context = {
                "round_number": current_round,
                "max_rounds": upstream_data.get("max_rounds", 52) if upstream_data else 52,
            }

            # Create a simplified node object for RL
            class SimpleNode:
                def __init__(self, name, inventory, backlog, pipeline_shipments, incoming_order, last_order, total_cost):
                    self.name = name
                    self.inventory = inventory
                    self.backlog = backlog
                    self.pipeline_shipments = pipeline_shipments
                    self.incoming_order = incoming_order
                    self.last_order_placed = last_order
                    self.total_cost = total_cost

            # Create node object
            node = SimpleNode(
                name=f"{self.agent_type.value}_{self.agent_id}",
                inventory=inventory_level,
                backlog=backlog_level,
                pipeline_shipments=incoming_shipments,
                incoming_order=current_demand or 0,
                last_order=self.last_order,
                total_cost=0.0  # Would need to track this
            )

            # Get RL decision
            order_qty = self._rl_agent_instance.compute_order(node, context)
            order = max(0, int(round(order_qty)))

            # Update demand history
            if current_demand is not None:
                self.demand_history.append(current_demand)

            self.last_explanation = (
                f"RL (Reinforcement Learning) | "
                f"inventory={inventory_level} backlog={backlog_level} "
                f"pipeline={sum(incoming_shipments):.1f} order={order}"
            )

            return order

        except Exception as e:
            logger.error(f"RL strategy failed: {e}")
            self._fallback_used = True
            self._fallback_reason = f"RL inference failed: {str(e)}"
            return self._base_stock_fallback(current_demand, inventory_level, backlog_level, incoming_shipments)

    def _random_strategy(self) -> int:
        """Make random orders for baseline testing."""
        order_qty = random.randint(1, 8)
        self.last_explanation = f"Random baseline | sampled uniform order {order_qty} (1-8)"
        return order_qty

    def _llm_supervisor_context(
        self,
        current_demand: Optional[int],
        upstream_data: Optional[Dict[str, Any]],
        inventory_level: int,
        backlog_level: int,
        incoming_shipments: List[float],
        base_order: float,
    ) -> Dict[str, Any]:
        pipeline = float(sum(incoming_shipments[:2])) if incoming_shipments else 0.0

        demand_window = self.demand_history[-3:] if self.demand_history else []
        try:
            forecast = (
                sum(float(x) for x in demand_window) / len(demand_window)
                if demand_window
                else None
            )
        except (TypeError, ValueError):
            forecast = None
        if forecast is None and current_demand is not None:
            forecast = float(current_demand)
        if forecast is None:
            forecast = float(base_order)

        local_avg = None
        if self.order_history:
            recent_orders = self.order_history[-3:]
            if recent_orders:
                local_avg = sum(recent_orders) / len(recent_orders)

        upstream_avg = None
        if isinstance(upstream_data, dict):
            upstream_orders = upstream_data.get("previous_orders")
            if isinstance(upstream_orders, list) and upstream_orders:
                recent_upstream = upstream_orders[-3:]
                try:
                    upstream_avg = sum(float(x) for x in recent_upstream) / len(recent_upstream)
                except (TypeError, ValueError):
                    upstream_avg = None

        return {
            "inventory": float(inventory_level),
            "backlog": float(backlog_level),
            "pipeline": pipeline,
            "forecast": forecast,
            "local_avg": local_avg,
            "upstream_avg": upstream_avg,
        }

    def _llm_decision_core(
        self,
        current_round: int,
        current_demand: Optional[int],
        upstream_data: Optional[Dict],
        inventory_level: int,
        backlog_level: int,
        incoming_shipments: List[float],
    ) -> Tuple[int, str, Dict[str, Any]]:
        shipments = incoming_shipments or [float(x) for x in self.pipeline]
        llm_agent = self._ensure_llm_agent()

        try:
            order_qty = llm_agent.make_decision(
                current_round=current_round,
                current_inventory=self.inventory,
                backorders=self.backlog,
                incoming_shipments=self.pipeline,
                demand_history=self.demand_history,
                order_history=self.order_history,
                current_demand=current_demand,
                upstream_data=upstream_data,
            )
            rationale = getattr(llm_agent, "last_explanation", None)
        except AutonomyLLMError:
            raise
        except Exception as exc:  # pragma: no cover - defensive guard
            raise RuntimeError(
                "Unexpected error while requesting Autonomy LLM decision"
            ) from exc

        explanation = (
            f"Autonomy LLM | {rationale}".strip()
            if rationale
            else "Autonomy LLM | no rationale returned"
        )
        context = self._llm_supervisor_context(
            current_demand,
            upstream_data,
            inventory_level,
            backlog_level,
            shipments,
            order_qty,
        )
        return max(0, int(round(order_qty))), explanation, context

    def _ensure_llm_agent(self) -> "LLMAgent":
        if LLMAgent is None:
            raise RuntimeError(
                "Autonomy LLM integration unavailable: LLMAgent import failed"
            )

        if self._llm_agent is None:
            try:
                model = self.llm_model or "gpt-5-mini"
                strategy_name = (self.llm_strategy_name or "balanced").strip().lower()
                if not strategy_name:
                    strategy_name = "balanced"
                if LLMStrategy:
                    try:
                        llm_strategy = LLMStrategy(strategy_name)
                    except ValueError:
                        llm_strategy = LLMStrategy.BALANCED
                else:
                    llm_strategy = None
                supervisor_enabled = self.strategy in (
                    AgentStrategy.LLM,
                    AgentStrategy.LLM_SUPERVISED,
                    AgentStrategy.LLM_GLOBAL,
                )
                global_enabled = self.strategy == AgentStrategy.LLM_GLOBAL
                self._llm_agent = LLMAgent(
                    role=self.agent_type.value,
                    strategy=llm_strategy or LLMStrategy.BALANCED,
                    model=model,
                    supervisor=supervisor_enabled,
                    global_agent=global_enabled,
                )
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(
                    "Failed to initialize Autonomy LLM agent"
                ) from exc
        return self._llm_agent

    def _llm_strategy(
        self,
        current_round: int,
        current_demand: Optional[int],
        upstream_data: Optional[Dict],
        inventory_level: int,
        backlog_level: int,
        incoming_shipments: List[float],
    ) -> int:
        order, explanation, _ = self._llm_decision_core(
            current_round,
            current_demand,
            upstream_data,
            inventory_level,
            backlog_level,
            incoming_shipments,
        )
        self.last_explanation = explanation
        return order

    def _llm_supervised_strategy(
        self,
        current_round: int,
        current_demand: Optional[int],
        upstream_data: Optional[Dict],
        inventory_level: int,
        backlog_level: int,
        incoming_shipments: List[float],
    ) -> int:
        base_order, base_explanation, context = self._llm_decision_core(
            current_round,
            current_demand,
            upstream_data,
            inventory_level,
            backlog_level,
            incoming_shipments,
        )
        final_order = base_order
        supervisor_explanation: Optional[str] = None
        llm_agent = self._ensure_llm_agent()
        if getattr(llm_agent, "last_supervisor_patch", None):
            self.last_explanation = base_explanation
            if self.central_coordinator:
                self.central_coordinator.register_decision(self.agent_type, final_order)
            return final_order
        if self.central_coordinator:
            final_order, supervisor_explanation = self.central_coordinator.apply_override(
                self.agent_type,
                float(base_order),
                context,
                week=current_round,
            )

        if supervisor_explanation:
            if base_explanation:
                explanation = f"{base_explanation}\n\n{supervisor_explanation}"
            else:
                explanation = supervisor_explanation
        else:
            explanation = base_explanation

        self.last_explanation = explanation
        return final_order

    def _llm_global_strategy(
        self,
        current_round: int,
        prev_order: Optional[int],
        current_demand: Optional[int],
        upstream_data: Optional[Dict],
        inventory_level: int,
        backlog_level: int,
        incoming_shipments: List[float],
    ) -> int:
        base_order, base_explanation, context = self._llm_decision_core(
            current_round,
            current_demand,
            upstream_data,
            inventory_level,
            backlog_level,
            incoming_shipments,
        )
        final_order = base_order
        global_explanation: Optional[str] = None

        llm_agent = self._ensure_llm_agent()
        if getattr(llm_agent, "last_global_targets", None):
            if self.central_coordinator:
                self.central_coordinator.register_decision(self.agent_type, final_order)
            self.last_explanation = base_explanation
            return final_order
        if self.global_controller:
            final_order, global_explanation = self.global_controller.plan_order(
                self.agent_type,
                current_round,
                float(base_order),
                context,
                prev_order,
            )

        if self.central_coordinator:
            self.central_coordinator.register_decision(self.agent_type, final_order)

        if global_explanation:
            if base_explanation:
                explanation = f"{base_explanation}\n\n{global_explanation}"
            else:
                explanation = global_explanation
        else:
            explanation = base_explanation

        self.last_explanation = explanation
        return final_order

    def _handle_llm_failure(
        self,
        *,
        error: Exception,
        current_round: int,
        prev_order: Optional[int],
        current_demand: Optional[int],
        upstream_data: Optional[Dict],
        inventory_level: int,
        backlog_level: int,
        incoming_shipments: List[float],
    ) -> int:
        """Fallback path when the Autonomy LLM is unavailable."""

        upstream_context = upstream_data or {}
        logger.warning(
            "Autonomy LLM failure | role=%s round=%s | falling back to PID heuristic | error=%s",
            self.agent_type.value,
            current_round,
            error,
        )

        fallback_order = self._pid_strategy(
            current_round,
            current_demand,
            upstream_context,
            inventory_level,
            backlog_level,
            incoming_shipments,
            current_demand,
        )

        error_text = str(error).strip() or error.__class__.__name__
        if len(error_text) > 200:
            error_text = f"{error_text[:197]}..."

        pid_reason = self.last_explanation or ""
        header = f"Autonomy LLM | Fallback heuristic | {error_text}"
        if pid_reason:
            self.last_explanation = f"{header}\n\n{pid_reason}"
        else:
            self.last_explanation = header

        if self.strategy == AgentStrategy.LLM_SUPERVISED and self.central_coordinator:
            context = self._llm_supervisor_context(
                current_demand,
                upstream_context,
                inventory_level,
                backlog_level,
                incoming_shipments,
                fallback_order,
            )
            adjusted_order, supervisor_explanation = self.central_coordinator.apply_override(
                self.agent_type,
                float(fallback_order),
                context,
                week=current_round,
            )
            if supervisor_explanation:
                combined = self.last_explanation or ""
                if combined:
                    combined = f"{combined}\n\n{supervisor_explanation}"
                else:
                    combined = supervisor_explanation
                self.last_explanation = combined
            fallback_order = adjusted_order

        elif self.strategy == AgentStrategy.LLM_GLOBAL and self.global_controller:
            context = self._llm_supervisor_context(
                current_demand,
                upstream_context,
                inventory_level,
                backlog_level,
                incoming_shipments,
                fallback_order,
            )
            adjusted_order, global_explanation = self.global_controller.plan_order(
                self.agent_type,
                current_round,
                float(fallback_order),
                context,
                prev_order,
            )
            if self.central_coordinator:
                self.central_coordinator.register_decision(self.agent_type, adjusted_order)
            if global_explanation:
                combined = self.last_explanation or ""
                if combined:
                    combined = f"{combined}\n\n{global_explanation}"
                else:
                    combined = global_explanation
                self.last_explanation = combined
            fallback_order = adjusted_order

        return max(0, int(round(fallback_order)))

    def _compute_autonomy_base(
        self,
        current_demand: Optional[int],
        upstream_data: Optional[Dict],
        inventory_level: int,
        backlog_level: int,
        incoming_shipments: List[float],
    ) -> Tuple[float, Dict[str, Any]]:
        """Compute the baseline Autonomy DTCE recommendation."""
        alpha = 0.35
        if self.demand_history:
            forecast = float(self.demand_history[0])
            for demand in self.demand_history[1:]:
                forecast = alpha * float(demand) + (1 - alpha) * forecast
        elif current_demand is not None:
            forecast = float(current_demand)
        else:
            forecast = float(self.last_order or 4)

        pipeline = sum(incoming_shipments[:2]) if incoming_shipments else 0.0
        inventory_position = float(inventory_level) + pipeline - float(backlog_level)
        safety_stock = max(0.0, forecast * 0.5)
        base_target = forecast * 2.0 + safety_stock + float(backlog_level)
        base_order = base_target - inventory_position

        upstream_orders = (upstream_data or {}).get('previous_orders') if upstream_data else None
        upstream_avg = None
        if upstream_orders:
            recent_upstream = upstream_orders[-3:]
            if recent_upstream:
                upstream_avg = sum(recent_upstream) / len(recent_upstream)

        recent_local_orders = self.order_history[-3:] if self.order_history else []
        local_avg = sum(recent_local_orders) / len(recent_local_orders) if recent_local_orders else float(self.last_order)

        smoothing_anchor = upstream_avg if upstream_avg is not None else local_avg
        if smoothing_anchor is not None:
            base_order = 0.7 * base_order + 0.3 * float(smoothing_anchor)

        base_order = max(0.0, base_order)
        context = {
            "forecast": forecast,
            "inventory": float(inventory_level),
            "backlog": float(backlog_level),
            "pipeline": pipeline,
            "upstream_avg": upstream_avg,
            "local_avg": local_avg,
        }
        return base_order, context

    def _autonomy_dtce_strategy(
        self,
        current_round: int,
        prev_order: Optional[int],
        current_demand: Optional[int],
        upstream_data: Optional[Dict],
        inventory_level: int,
        backlog_level: int,
        incoming_shipments: List[float],
    ) -> int:
        base_order, context = self._compute_autonomy_base(
            current_demand,
            upstream_data,
            inventory_level,
            backlog_level,
            incoming_shipments,
        )
        order = max(0, int(round(base_order)))
        explanation = self._build_autonomy_explanation(
            week=current_round,
            inventory_level=inventory_level,
            backlog_level=backlog_level,
            incoming_shipments=incoming_shipments,
            context=context,
            action_qty=order,
            prev_action=prev_order,
            base_order=base_order,
        )
        self.last_explanation = explanation
        if self.central_coordinator:
            self.central_coordinator.register_decision(self.agent_type, order)
        return order

    def _autonomy_central_strategy(
        self,
        current_round: int,
        prev_order: Optional[int],
        current_demand: Optional[int],
        upstream_data: Optional[Dict],
        inventory_level: int,
        backlog_level: int,
        incoming_shipments: List[float],
    ) -> int:
        base_order, context = self._compute_autonomy_base(
            current_demand,
            upstream_data,
            inventory_level,
            backlog_level,
            incoming_shipments,
        )
        final_order = max(0, int(round(base_order)))
        supervisor_explanation: Optional[str] = None
        if self.central_coordinator:
            final_order, supervisor_explanation = self.central_coordinator.apply_override(
                self.agent_type,
                base_order,
                context,
                week=current_round,
            )

        role_explanation = self._build_autonomy_explanation(
            week=current_round,
            inventory_level=inventory_level,
            backlog_level=backlog_level,
            incoming_shipments=incoming_shipments,
            context=context,
            action_qty=final_order,
            prev_action=prev_order,
            base_order=base_order,
        )

        if supervisor_explanation:
            if role_explanation:
                role_explanation = f"{role_explanation}\n\n{supervisor_explanation}"
            else:
                role_explanation = supervisor_explanation

        self.last_explanation = role_explanation
        return final_order

    def _autonomy_global_strategy(
        self,
        current_round: int,
        prev_order: Optional[int],
        current_demand: Optional[int],
        upstream_data: Optional[Dict],
        inventory_level: int,
        backlog_level: int,
        incoming_shipments: List[float],
    ) -> int:
        base_order, context = self._compute_autonomy_base(
            current_demand,
            upstream_data,
            inventory_level,
            backlog_level,
            incoming_shipments,
        )
        final_order = max(0, int(round(base_order)))
        global_explanation: Optional[str] = None

        if self.global_controller:
            final_order, global_explanation = self.global_controller.plan_order(
                self.agent_type,
                current_round,
                base_order,
                context,
                prev_order,
            )

        role_explanation = self._build_autonomy_explanation(
            week=current_round,
            inventory_level=inventory_level,
            backlog_level=backlog_level,
            incoming_shipments=incoming_shipments,
            context=context,
            action_qty=final_order,
            prev_action=prev_order,
            base_order=base_order,
        )

        if global_explanation:
            if role_explanation:
                role_explanation = f"{role_explanation}\n\n{global_explanation}"
            else:
                role_explanation = global_explanation

        self.last_explanation = role_explanation

        if self.central_coordinator:
            self.central_coordinator.register_decision(self.agent_type, final_order)

        return final_order

    def _build_autonomy_explanation(
        self,
        week: int,
        inventory_level: int,
        backlog_level: int,
        incoming_shipments: List[float],
        context: Dict[str, Any],
        action_qty: int,
        prev_action: Optional[int],
        base_order: float,
    ) -> str:
        try:
            lead_time = max(1, len(incoming_shipments) or 2)
            pipeline_orders = [int(round(x)) for x in self.order_history[-lead_time:]]
            if not pipeline_orders and self.pipeline:
                pipeline_orders = [int(round(x)) for x in self.pipeline[:lead_time]]
            if not pipeline_orders:
                pipeline_orders = [0] * lead_time

            pipeline_shipments = [int(round(x)) for x in incoming_shipments[:lead_time]]
            if not pipeline_shipments:
                pipeline_shipments = [0] * lead_time

            last_k_in = [int(round(x)) for x in self.demand_history[-lead_time:]] if self.demand_history else []
            last_k_out = [int(round(x)) for x in self.order_history[-lead_time:]] if self.order_history else []
            notes = self._format_autonomy_notes(context)

            obs = Obs(
                on_hand=int(inventory_level),
                backlog=int(backlog_level),
                pipeline_orders=pipeline_orders,
                pipeline_shipments=pipeline_shipments,
                last_k_orders_in=last_k_in,
                last_k_shipments_in=pipeline_shipments,
                last_k_orders_out=last_k_out,
                notes=notes,
            )

            forecast_mean = float(context.get("forecast", 0.0)) if context else 0.0
            forecast_mean_vec = [forecast_mean] * lead_time
            demand_window = self.demand_history[-max(lead_time, 3):]
            forecast_std_vec: Optional[List[float]] = None
            if demand_window and len(demand_window) >= 2:
                std_val = float(statistics.pstdev([float(x) for x in demand_window]))
                if std_val > 0:
                    forecast_std_vec = [std_val] * lead_time

            forecast = Forecast(mean=forecast_mean_vec, std=forecast_std_vec)
            params = RoleParams(
                lead_time=lead_time,
                service_level=0.95,
                capacity_cap=None,
                smoothing_lambda=0.0,
            )

            attribution = self._autonomy_actor_attribution(context, base_order, backlog_level)
            whatifs = self._autonomy_whatifs(inventory_level, backlog_level)

            explanation = explain_role_decision(
                role=self.agent_type.name.replace("_", " ").title(),
                week=week,
                obs=obs,
                action_qty=action_qty,
                forecast=forecast,
                params=params,
                shadow_policy="base_stock",
                actor_attribution=attribution,
                whatif_cfg=whatifs,
                prev_action_qty=prev_action,
            )
            return explanation
        except Exception:
            return f"Decision (Week {week}, {self.agent_type.name.replace('_', ' ').title()}): order **{action_qty}** units upstream."

    def _format_autonomy_notes(self, context: Optional[Dict[str, Any]]) -> Optional[str]:
        if not context:
            return None
        notes: List[str] = []
        upstream_avg = context.get("upstream_avg")
        if upstream_avg is not None:
            notes.append(f"upstream avg {float(upstream_avg):.1f}")
        local_avg = context.get("local_avg")
        if local_avg is not None:
            notes.append(f"recent order avg {float(local_avg):.1f}")
        return "; ".join(notes) if notes else None

    def _autonomy_actor_attribution(
        self,
        context: Optional[Dict[str, Any]],
        base_order: float,
        backlog_level: int,
    ) -> Optional[Dict[str, float]]:
        if not base_order:
            return None
        denom = max(1.0, abs(float(base_order)))
        attribution: Dict[str, float] = {}

        forecast_val = float(context.get("forecast", 0.0)) if context else 0.0
        if forecast_val:
            attribution["forecast_pull"] = max(-1.0, min(forecast_val / denom, 1.0))

        pipeline_val = float(context.get("pipeline", 0.0)) if context else 0.0
        if pipeline_val:
            attribution["pipeline_cover"] = max(-1.0, min(-pipeline_val / denom, 1.0))

        if backlog_level:
            attribution["backlog_pressure"] = max(-1.0, min(backlog_level / denom, 1.0))

        return attribution or None

    def _autonomy_whatifs(
        self,
        inventory_level: int,
        backlog_level: int,
    ) -> Optional[Dict[str, float]]:
        whatifs: Dict[str, float] = {}
        if backlog_level > inventory_level:
            whatifs["demand_scale"] = 1.2
        elif inventory_level > backlog_level * 2 and inventory_level > 0:
            whatifs["demand_scale"] = 0.8
        return whatifs or None

    def _site_agent_strategy(
        self,
        current_round: int,
        prev_order: int,
        current_demand: int,
        upstream_data: Optional[List[Dict[str, Any]]],
        inventory_level: int,
        backlog_level: int,
        incoming_shipments,
    ) -> float:
        """
        Powell SiteAgent strategy using deterministic engines + TRM.

        Uses SiteAgent's base-stock policy with optional TRM adjustments
        for improved order decisions.
        """
        try:
            from app.services.powell.integration.scenario_integration import SiteAgentPolicy

            # Get or create SiteAgent policy for this role
            if not hasattr(self, '_site_agent_policy'):
                site_key = self.agent_type.value
                self._site_agent_policy = SiteAgentPolicy(
                    site_key=site_key,
                    use_trm=True,
                    trm_confidence_threshold=0.7,
                )

            # Normalize incoming_shipments to a scalar
            if isinstance(incoming_shipments, (list, tuple)):
                pipeline = sum(float(x) for x in incoming_shipments)
            else:
                pipeline = float(incoming_shipments)

            observation = {
                'inventory': inventory_level,
                'backlog': backlog_level,
                'pipeline_on_order': pipeline,
                'last_incoming_order': current_demand,
                'base_stock': 20,  # Default, could be configured
                'inventory_position': inventory_level + pipeline - backlog_level,
            }

            # Compute order through SiteAgent policy
            order = self._site_agent_policy.order(observation)

            self.last_explanation = (
                f"SiteAgent (deterministic + TRM) | "
                f"inv={inventory_level} backlog={backlog_level} pipeline={pipeline} | "
                f"demand={current_demand} -> order={order}"
            )

            return float(order)

        except Exception as e:
            logger.warning(f"SiteAgent strategy failed: {e}, falling back to naive")
            self._fallback_used = True
            self._fallback_reason = f"SiteAgent error: {e}"
            on_order = sum(float(x) for x in incoming_shipments) if isinstance(incoming_shipments, (list, tuple)) else float(incoming_shipments)
            return self._naive_strategy(current_demand, backlog_level, inventory_level, on_order)

    def get_last_explanation_comment(self) -> str:
        label = self._last_node_label or self.agent_type.value.title()
        explanation = self.last_explanation
        if explanation:
            flattened = " | ".join(
                part.strip() for part in explanation.splitlines() if part.strip()
            )
        else:
            flattened = (
                f"{self.strategy.value} strategy | order={self.last_order} "
                f"inventory={self.inventory} backlog={self.backlog}"
            )
        if len(flattened) > 240:
            flattened = f"{flattened[:237]}..."
        comment = f"[{label}] {flattened}"
        if len(comment) > 255:
            comment = comment[:252] + "..."
        return comment

    def update_inventory(self, incoming_shipment: int, outgoing_shipment: int):
        """Update inventory and backlog based on incoming and outgoing shipments."""
        self.inventory = self.inventory + incoming_shipment - outgoing_shipment
        if self.inventory < 0:
            self.backlog += abs(self.inventory)
            self.inventory = 0
        else:
            self.backlog = max(0, self.backlog - outgoing_shipment)


class AgentManager:
    """Manages multiple agents in the supply chain."""

    def __init__(self, can_see_demand: bool = False, model_path: Optional[str] = None):
        self.agents: Dict[AgentType, SimulationAgent] = {}
        self.can_see_demand = can_see_demand
        self.model_path = model_path  # Config-specific trained model path
        self.autonomy_coordinator = AutonomyCoordinator()
        self.autonomy_global_controller = AutonomyGlobalController()
        self.initialize_agents()

    def set_model_path(self, model_path: Optional[str]) -> None:
        """Set the trained model path for all agents (config-specific)."""
        self.model_path = model_path
        for agent in self.agents.values():
            agent.model_path = model_path

    def initialize_agents(self):
        """Initialize agents for each role in the supply chain."""
        self.agents[AgentType.RETAILER] = SimulationAgent(
            agent_id=1,
            agent_type=AgentType.RETAILER,
            strategy=AgentStrategy.NAIVE,
            can_see_demand=True,  # Retailer can always see demand
            llm_model="gpt-5-mini",
            central_coordinator=self.autonomy_coordinator,
            global_controller=self.autonomy_global_controller,
            model_path=self.model_path,
        )

        self.agents[AgentType.WHOLESALER] = SimulationAgent(
            agent_id=2,
            agent_type=AgentType.WHOLESALER,
            strategy=AgentStrategy.NAIVE,
            can_see_demand=self.can_see_demand,
            llm_model="gpt-5-mini",
            central_coordinator=self.autonomy_coordinator,
            global_controller=self.autonomy_global_controller,
            model_path=self.model_path,
        )

        self.agents[AgentType.DISTRIBUTOR] = SimulationAgent(
            agent_id=3,
            agent_type=AgentType.DISTRIBUTOR,
            strategy=AgentStrategy.NAIVE,
            can_see_demand=self.can_see_demand,
            llm_model="gpt-5-mini",
            central_coordinator=self.autonomy_coordinator,
            global_controller=self.autonomy_global_controller,
            model_path=self.model_path,
        )

        self.agents[AgentType.MANUFACTURER] = SimulationAgent(
            agent_id=4,
            agent_type=AgentType.MANUFACTURER,
            strategy=AgentStrategy.NAIVE,
            can_see_demand=self.can_see_demand,
            llm_model="gpt-5-mini",
            central_coordinator=self.autonomy_coordinator,
            global_controller=self.autonomy_global_controller,
            model_path=self.model_path,
        )

        self.agents[AgentType.SUPPLIER] = SimulationAgent(
            agent_id=5,
            agent_type=AgentType.SUPPLIER,
            strategy=AgentStrategy.NAIVE,
            can_see_demand=self.can_see_demand,
            llm_model="gpt-5-mini",
            central_coordinator=self.autonomy_coordinator,
            global_controller=self.autonomy_global_controller,
            model_path=self.model_path,
        )

    def get_agent(self, agent_type: AgentType) -> SimulationAgent:
        """Get agent by type."""
        return self.agents.get(agent_type)

    def set_agent_strategy(
        self,
        agent_type: AgentType,
        strategy: AgentStrategy,
        llm_model: Optional[str] = None,
        override_pct: Optional[float] = None,
        llm_strategy: Optional[str] = None,
    ):
        """Set strategy and optional Autonomy LLM model for a specific agent."""
        if agent_type in self.agents:
            agent = self.agents[agent_type]
            agent.central_coordinator = self.autonomy_coordinator
            agent.global_controller = self.autonomy_global_controller
            strategy_changed = agent.strategy != strategy
            uses_llm = strategy in (
                AgentStrategy.LLM,
                AgentStrategy.LLM_SUPERVISED,
                AgentStrategy.LLM_GLOBAL,
            )
            if llm_model is not None and agent.llm_model != llm_model:
                agent.llm_model = llm_model
                agent._llm_agent = None
            if llm_strategy is not None:
                normalized = str(llm_strategy).strip().lower() or "balanced"
                if getattr(agent, "llm_strategy_name", None) != normalized:
                    agent.llm_strategy_name = normalized
                    agent._llm_agent = None
            if not uses_llm and agent._llm_agent is not None:
                agent._llm_agent = None

            agent.strategy = strategy
            if strategy in (
                AgentStrategy.AUTONOMY_DTCE_CENTRAL,
                AgentStrategy.LLM_SUPERVISED,
            ):
                if override_pct is not None:
                    self.autonomy_coordinator.set_override_pct(agent_type, override_pct)
                else:
                    self.autonomy_coordinator.set_override_pct(agent_type, None)
            else:
                self.autonomy_coordinator.set_override_pct(agent_type, None)
            if strategy_changed:
                agent.reset_for_strategy()
            if uses_llm and agent._llm_agent is None:
                try:
                    agent._ensure_llm_agent()
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "Failed to pre-initialize LLM agent for %s: %s",
                        agent_type.value,
                        exc,
                    )
    
    def set_demand_visibility(self, visible: bool):
        """Set whether agents can see the actual customer demand."""
        self.can_see_demand = visible
        for agent in self.agents.values():
            # Don't change visibility for retailer (always sees demand)
            if agent.agent_type != AgentType.RETAILER:
                agent.can_see_demand = visible
    
    def get_agent_states(self) -> Dict[str, Dict]:
        """Get current state of all agents."""
        return {
            agent_type.value: {
                'inventory': agent.inventory,
                'backlog': agent.backlog,
                'last_order': agent.last_order,
                'order_history': agent.order_history,
                'strategy': agent.strategy.value
            }
            for agent_type, agent in self.agents.items()
        }
