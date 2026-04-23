import json
import logging
import os
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from llm_agent.autonomy_client import AutonomyStrategistSession, get_session


class AutonomyLLMError(RuntimeError):
    """Domain specific error raised when Autonomy LLM integration fails."""

    def __init__(self, message: str, *, context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.context = context or {}

class LLMStrategy(Enum):
    """Different Autonomy LLM prompting strategies for simulation."""
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"
    ADAPTIVE = "adaptive"

MAX_RATIONALE_CHARS = 255


def _truncate_rationale(text: str, *, max_length: int = MAX_RATIONALE_CHARS) -> str:
    """Return ``text`` trimmed to ``max_length`` characters (ellipsized if needed)."""

    cleaned = text.strip()
    if len(cleaned) <= max_length:
        return cleaned

    # Leave room for a single ellipsis so the total stays within the cap.
    cutoff = max(0, max_length - 1)
    trimmed = cleaned[:cutoff].rstrip()
    if not trimmed:
        # Fallback to hard cut if whitespace consumed everything.
        trimmed = cleaned[:cutoff]
    return f"{trimmed}…"


class LLMAgent:
    """Autonomy LLM-based agent that delegates to the Strategist assistant."""

    def __init__(
        self,
        role: str,
        strategy: LLMStrategy = LLMStrategy.BALANCED,
        model: str = "qwen3-8b",
        *,
        supervisor: bool = True,
        global_agent: bool = False,
        custom_gpt: Optional[str] = None,
    ):
        self.role = role
        self.strategy = strategy
        default_model = os.getenv("LLM_MODEL_NAME") or os.getenv("AUTONOMY_LLM_MODEL")
        self.model = model or default_model or "qwen3-8b"
        self.supervisor_enabled = supervisor
        self.global_enabled = global_agent
        self.custom_gpt = custom_gpt or os.getenv("AUTONOMY_CUSTOM_GPT") or os.getenv("SIMULATION_CUSTOM_GPT")
        if not os.getenv("LLM_API_KEY") and not os.getenv("OPENAI_API_KEY") and not os.getenv("LLM_API_BASE"):
            raise ValueError(
                "No LLM provider configured. Set LLM_API_BASE for local LLM "
                "(vLLM/Ollama) or LLM_API_KEY for a hosted API."
            )

        strategy_name = strategy.value if isinstance(strategy, LLMStrategy) else str(strategy)
        self.session = get_session(
            self.model,
            strategy=strategy_name,
            supervisor=self.supervisor_enabled,
            global_agent=self.global_enabled,
            custom_gpt=self.custom_gpt,
        )
        self.last_explanation: Optional[str] = None
        self._last_ship_plan: Optional[int] = None
        self.last_decision: Optional[Dict[str, Any]] = None
        self.last_supervisor_patch: Optional[Dict[str, Any]] = None
        self.last_global_targets: Optional[Dict[str, Any]] = None
        self.last_proposal: Optional[Dict[str, Any]] = None

    def make_decision(
        self,
        current_period: int,
        current_inventory: int,
        backorders: int,
        incoming_shipments: list,
        demand_history: list,
        order_history: list,
        current_demand: Optional[int] = None,
        upstream_data: Optional[Dict[str, Any]] = None
    ) -> int:
        """Make a decision on how many units to order."""
        self.last_explanation = None
        self._last_ship_plan = None
        self.last_decision = None
        self.last_supervisor_patch = None
        self.last_global_targets = None
        self.last_proposal = None
        payload: Optional[Dict[str, Any]] = None
        if isinstance(upstream_data, dict):
            candidate = upstream_data.get("llm_payload")
            if isinstance(candidate, dict):
                payload = candidate
            elif candidate is not None:
                logger.warning(
                    "Unexpected llm_payload type: %s", type(candidate)
                )

        if payload is not None:
            def _summarize(obj: Any, *, max_length: int = 800) -> str:
                try:
                    text = json.dumps(obj, sort_keys=True, default=str)
                except Exception:
                    text = repr(obj)
                if len(text) > max_length:
                    return f"{text[:max_length]}…"
                return text

            logger.debug(
                "Autonomy LLM request | role=%s round=%s | payload=%s",
                self.role,
                current_period,
                _summarize(payload),
            )
            try:
                decision = self.session.decide(payload)
                self.last_decision = decision
                self.last_supervisor_patch = decision.get("supervisor_patch")
                self.last_global_targets = decision.get("global_targets")
                self.last_proposal = decision.get("proposal")

                logger.debug(
                    "Autonomy LLM response | role=%s round=%s | decision=%s",
                    self.role,
                    current_period,
                    _summarize(decision),
                )

                def _safe_int(value: Any) -> int:
                    try:
                        return max(0, int(value))
                    except (TypeError, ValueError):
                        return 0

                action_block = decision.get("action", {}) if isinstance(decision, dict) else {}
                order_quantity = _safe_int(
                    action_block.get("order_qty", decision.get("order_upstream", 0))
                )
                ship_plan = action_block.get("ship_qty", decision.get("ship_to_downstream", order_quantity))
                self._last_ship_plan = _safe_int(ship_plan)

                rationale_raw = action_block.get("rationale", decision.get("rationale", ""))
                rationale = str(rationale_raw or "").strip()
                notes = action_block.get("notes")
                if notes:
                    rationale = f"{rationale} | Notes: {notes}" if rationale else str(notes)

                patch = self.last_supervisor_patch or {}
                if isinstance(patch, dict):
                    patch_body: Optional[Dict[str, Any]] = None
                    if isinstance(patch.get("patch"), dict):
                        patch_body = patch.get("patch")
                    elif "patch" not in patch:
                        patch_body = patch
                    if isinstance(patch_body, dict):
                        if patch_body.get("order_qty") is not None:
                            order_quantity = _safe_int(patch_body.get("order_qty"))
                        patch_reason = patch_body.get("reason")
                        if patch_reason:
                            rationale = (
                                f"{rationale} | Supervisor: {patch_reason}"
                                if rationale
                                else f"Supervisor: {patch_reason}"
                            )

                ship_fragment = (
                    f" | Proposed ship downstream: {self._last_ship_plan}"
                    if self._last_ship_plan is not None
                    else ""
                )
                combined_explanation = f"{rationale}{ship_fragment}".strip()
                if not combined_explanation:
                    combined_explanation = "No rationale provided"
                self.last_explanation = _truncate_rationale(combined_explanation)
                return order_quantity
            except Exception as exc:
                summary = _summarize(payload)
                logger.exception(
                    "Autonomy LLM error | role=%s round=%s | payload=%s | error=%s",
                    self.role,
                    current_period,
                    summary,
                    exc,
                )
                error_message = (
                    "Autonomy LLM call failed in llm_agent.LLMAgent.make_decision "
                    f"(role={self.role}, round={current_period}): {exc}"
                )
                self.last_explanation = error_message
                raise AutonomyLLMError(
                    error_message,
                    context={
                        "role": self.role,
                        "round": current_period,
                        "payload": summary,
                    },
                ) from exc

        if isinstance(upstream_data, dict):
            upstream_keys = sorted(upstream_data.keys())
        elif upstream_data is None:
            upstream_keys = []
        else:
            upstream_keys = [f"<{type(upstream_data).__name__}>"]

        error_message = (
            "Autonomy LLM payload missing in llm_agent.LLMAgent.make_decision "
            f"(role={self.role}, round={current_period}) | upstream_keys={upstream_keys}"
        )
        logger.error(error_message)
        self.last_explanation = error_message
        raise AutonomyLLMError(
            error_message,
            context={
                "role": self.role,
                "round": current_period,
                "upstream_keys": upstream_keys,
            },
        )


logger = logging.getLogger(__name__)


def check_autonomy_llm_access(
    *,
    model: Optional[str] = None,
    request_timeout: float = 5.0,
) -> Tuple[bool, str]:
    """Probe the configured Autonomy LLM endpoint to confirm availability."""

    if not os.getenv("LLM_API_KEY") and not os.getenv("OPENAI_API_KEY") and not os.getenv("LLM_API_BASE"):
        return False, "No LLM provider configured (set LLM_API_BASE or LLM_API_KEY)"

    target_model = model or os.getenv("LLM_MODEL_NAME") or os.getenv("AUTONOMY_LLM_MODEL") or "qwen3-8b"

    try:
        session = AutonomyStrategistSession(model=target_model)
        session.reset()
        # Minimal ping state — uses AWS SC master_type, no Beer Scenario role names or hardcoded values
        ping_state: Dict[str, Any] = {
            "master_type": "INVENTORY",
            "period": 0,
            "toggles": {
                "demand_history_sharing": False,
                "volatility_signal_sharing": False,
                "downstream_inventory_visibility": False,
            },
            "parameters": {
                "holding_cost_rate": 0.0,
                "backlog_cost_rate": 0.0,
                "lead_time_periods": 1,
            },
            "local_state": {
                "on_hand_qty": 0.0,
                "backlog_qty": 0.0,
                "incoming_orders": 0.0,
                "received_shipment": 0.0,
                "pipeline_orders": [],
                "pipeline_shipments": [],
            },
        }
        session.decide(ping_state)
        return True, target_model
    except Exception as exc:  # pragma: no cover - depends on external service
        logger.warning("Autonomy LLM probe failed for model %s: %s", target_model, exc)
        return False, str(exc)

# Example usage
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    # Example usage
    agent = LLMAgent(role="retailer", strategy=LLMStrategy.BALANCED, model="qwen3-8b")
    
    # Example scenario state
    order = agent.make_decision(
        current_period=1,
        current_inventory=12,
        backorders=0,
        incoming_shipments=[4, 4],
        demand_history=[8, 8, 8, 8, 12],
        order_history=[8, 8, 8, 8, 12],
        current_demand=8,
        upstream_data={
            "wholesaler_inventory": 24,
            "recent_lead_time": 2,
            "market_conditions": "stable"
        }
    )
    
    print(f"Agent decided to order: {order} units")
