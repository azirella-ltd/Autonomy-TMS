"""Auto-play Autonomy showcase scenarios and capture agent explanations."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

try:  # Prefer loading credentials from .env when available.
    from dotenv import load_dotenv  # type: ignore[import]
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    load_dotenv = None  # type: ignore[assignment]

from main import (
    SessionLocal,
    _coerce_scenario_config,
    _ensure_round,
    _ensure_simulation_state,
    _pending_orders,
    _finalize_round_if_ready,
    _touch_scenario,
    _save_scenario_config,
    _compute_customer_demand,
)
try:
    from scripts.export_round_history import export_scenario as export_round_history
except ImportError:  # pragma: no cover - fallback when executed from package root
    from export_round_history import export_scenario as export_round_history
from app.models.scenario import Scenario, ScenarioStatus as DbScenarioStatus, ScenarioUserAction
from app.models.scenario_user import ScenarioUser
from app.services.agents import (
    AgentDecision,
    AgentManager,
    AgentType,
    AgentStrategy as AgentStrategyEnum,
)
from app.services.llm_payload import build_llm_decision_payload


ROLES = ["retailer", "wholesaler", "distributor", "manufacturer"]


def _role_key(scenario_user: ScenarioUser) -> str:
    return str(scenario_user.role.value if hasattr(scenario_user.role, "value") else scenario_user.role).lower()


def _agent_type_for(role: str) -> AgentType:
    mapping = {
        "factory": AgentType.MANUFACTURER,
        "manufacturer": AgentType.MANUFACTURER,
        "supplier": AgentType.DISTRIBUTOR,
        "distributor": AgentType.DISTRIBUTOR,
        "wholesaler": AgentType.WHOLESALER,
        "retailer": AgentType.RETAILER,
    }
    if role not in mapping:
        raise ValueError(f"Unsupported role {role}")
    return mapping[role]


def _strategy_for(scenario_user: ScenarioUser) -> AgentStrategyEnum:
    raw = (scenario_user.ai_strategy or "autonomy_dtce").lower()
    try:
        return AgentStrategyEnum(raw)
    except ValueError:
        if raw.startswith("llm"):
            return AgentStrategyEnum.LLM
        return AgentStrategyEnum.AUTONOMY_DTCE

def _bootstrap_llm_environment() -> None:
    """Ensure strategist credentials are available when running standalone."""

    if os.getenv("OPENAI_API_KEY") and os.getenv("AUTONOMY_LLM_MODEL"):
        return

    if load_dotenv is None:
        return

    repo_root = Path(__file__).resolve().parents[2]
    env_path = repo_root / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)
    load_dotenv(override=False)  # Fall back to standard search path.

    if "LLM_MODEL_NAME" not in os.environ and not os.getenv("AUTONOMY_LLM_MODEL"):
        os.environ.setdefault("LLM_MODEL_NAME", "qwen3-8b")


def auto_play_autonomy_scenarios() -> None:
    _bootstrap_llm_environment()
    session = SessionLocal()
    try:
        scenarios = session.query(Scenario).order_by(Scenario.id).all()

        for scenario in scenarios:
            # Only auto-play unsupervised scenarios where all scenario_users are AI
            config = _coerce_scenario_config(scenario)
            progression = str(config.get("progression_mode", "")).lower()
            scenario_users = session.query(ScenarioUser).filter(ScenarioUser.scenario_id == scenario.id).all()
            if progression != "unsupervised":
                continue
            if any(not p.is_ai for p in scenario_users):
                continue

            print(f"=== Simulating scenario {scenario.id}: {scenario.name} ===")
            config['progression_mode'] = 'unsupervised'
            _ensure_simulation_state(config)
            _pending_orders(config).clear()
            _save_scenario_config(session, scenario, config)
            session.flush()

            if scenario.status == DbScenarioStatus.CREATED:
                if not scenario.current_round or scenario.current_round <= 0:
                    scenario.current_round = 1
                round_rec = _ensure_round(session, scenario, scenario.current_round)
                round_rec.status = 'in_progress'
                round_rec.started_at = datetime.utcnow()
                scenario.status = DbScenarioStatus.ROUND_IN_PROGRESS
                _touch_scenario(scenario)
                _save_scenario_config(session, scenario, config)
                session.add(round_rec)
                session.add(scenario)
                session.commit()

            agent_manager = AgentManager()
            scenario_users = session.query(ScenarioUser).filter(ScenarioUser.scenario_id == scenario.id).all()
            overrides = config.get('autonomy_overrides') or {}
            info_sharing = config.get('info_sharing') or {}
            full_visibility = str(info_sharing.get('visibility', '')).lower() == 'full'

            for scenario_user in scenario_users:
                if not scenario_user.is_ai:
                    continue
                role_key = _role_key(scenario_user)
                agent_type = _agent_type_for(role_key)
                strategy = _strategy_for(scenario_user)
                agent_manager.set_agent_strategy(
                    agent_type,
                    strategy,
                    llm_model=scenario_user.llm_model,
                    override_pct=overrides.get(role_key),
                )

            while True:
                session.refresh(scenario)
                if scenario.status == DbScenarioStatus.FINISHED:
                    print(f"  Scenario finished at round {scenario.current_round}")
                    break

                config = _coerce_scenario_config(scenario)
                _ensure_simulation_state(config)
                pending = _pending_orders(config)
                pending.clear()
                round_record = _ensure_round(session, scenario, scenario.current_round or 1)
                if round_record.status != 'in_progress':
                    round_record.status = 'in_progress'
                    round_record.started_at = datetime.utcnow()

                demand = _compute_customer_demand(scenario, round_record.round_number)
                history = config.get('history', [])
                last_orders = history[-1]['orders'] if history else {}
                sim_state = config.get('simulation_state', {})
                now_iso = datetime.utcnow().isoformat() + 'Z'

                for scenario_user in scenario_users:
                    if not scenario_user.is_ai:
                        continue
                    role_key = _role_key(scenario_user)
                    agent = agent_manager.get_agent(_agent_type_for(role_key))

                    inventory_record = scenario_user.inventory
                    inventory_value = inventory_record.current_stock if inventory_record else 0
                    backlog_value = inventory_record.backorders if inventory_record else 0
                    incoming_shipments = (
                        inventory_record.incoming_shipments if inventory_record else []
                    )

                    local_state = {
                        'inventory': sim_state.get('inventory', {}).get(role_key, inventory_value),
                        'backlog': sim_state.get('backlog', {}).get(role_key, backlog_value),
                        'incoming_shipments': sim_state.get('incoming', {}).get(role_key, incoming_shipments),
                    }
                    previous_orders_by_role: Dict[str, int] = {}
                    if isinstance(last_orders, dict):
                        for prev_role, payload in last_orders.items():
                            try:
                                quantity = int(
                                    payload.get('quantity', payload.get('order_qty', 0))
                                    if isinstance(payload, dict)
                                    else int(payload)  # type: ignore[arg-type]
                                )
                            except (TypeError, ValueError):
                                quantity = 0
                            previous_orders_by_role[str(prev_role)] = quantity
                    previous_qty = previous_orders_by_role.get(role_key, 0)
                    upstream_data: Dict[str, Any] = {
                        'previous_orders': list(previous_orders_by_role.values()),
                        'previous_orders_by_role': previous_orders_by_role,
                    }
                    strategy_enum = _strategy_for(scenario_user)
                    llm_payload = None
                    if strategy_enum in (
                        AgentStrategyEnum.LLM,
                        AgentStrategyEnum.LLM_SUPERVISED,
                        AgentStrategyEnum.LLM_GLOBAL,
                    ):
                        try:
                            llm_payload = build_llm_decision_payload(
                                session,
                                scenario,
                                round_number=round_record.round_number,
                                action_role=role_key,
                            )
                        except Exception as exc:  # noqa: BLE001 - surfaced in explanation
                            upstream_data['llm_payload_error'] = str(exc)
                        else:
                            upstream_data['llm_payload'] = llm_payload
                    visible_demand = demand if (scenario_user.can_see_demand or role_key == 'retailer' or full_visibility) else None

                    decision = agent.make_decision(
                        current_round=round_record.round_number,
                        current_demand=visible_demand,
                        upstream_data=upstream_data,
                        local_state=local_state,
                    )
                    decision_comment = None
                    if isinstance(decision, AgentDecision):
                        quantity_value = decision.quantity
                        decision_comment = decision.reason
                    else:
                        quantity_value = decision
                    try:
                        quantity = int(max(0, round(quantity_value)))
                    except (TypeError, ValueError):
                        quantity = 0

                    action = session.query(ScenarioUserAction).filter(
                        ScenarioUserAction.scenario_id == scenario.id,
                        ScenarioUserAction.round_id == round_record.id,
                        ScenarioUserAction.scenario_user_id == scenario_user.id,
                        ScenarioUserAction.action_type == 'order',
                    ).first()
                    if action:
                        action.quantity = quantity
                        action.created_at = datetime.utcnow()
                    else:
                        action = ScenarioUserAction(
                            scenario_id=scenario.id,
                            round_id=round_record.id,
                            scenario_user_id=scenario_user.id,
                            action_type='order',
                            quantity=quantity,
                            created_at=datetime.utcnow(),
                        )
                        session.add(action)

                    explanation = decision_comment or agent.get_last_explanation_comment()
                    pending[role_key] = {
                        'scenario_user_id': scenario_user.id,
                        'quantity': quantity,
                        'comment': explanation or f'Autonomy decision: order {quantity} units.',
                        'submitted_at': now_iso,
                    }

                session.flush()
                _save_scenario_config(session, scenario, config)
                progressed = _finalize_round_if_ready(session, scenario, config, round_record, force=True)
                session.add(scenario)
                session.flush()
                session.commit()

                if not progressed:
                    print(f"  Warning: round {round_record.round_number} did not finalize; forcing advance")
                    scenario.current_round = (scenario.current_round or 0) + 1
                    session.commit()

            export_round_history(scenario.id, os.environ.get("ROUND_EXPORT_DIR", "/app/exports"))

        session.commit()
    finally:
        session.close()


if __name__ == "__main__":
    auto_play_autonomy_scenarios()
