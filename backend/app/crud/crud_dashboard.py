from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional

from ..models.scenario import Scenario, ScenarioStatus
from ..models.scenario_user import ScenarioUser
from ..models.supply_chain import ScenarioUserPeriod, ScenarioRound


def _active_statuses() -> List[ScenarioStatus]:
    """Return the list of scenario statuses considered active."""

    candidates = []
    for status_name in ("IN_PROGRESS", "STARTED", "ROUND_IN_PROGRESS", "PAUSED"):
        if hasattr(ScenarioStatus, status_name):
            candidates.append(getattr(ScenarioStatus, status_name))
    return candidates or [ScenarioStatus.IN_PROGRESS]


def get_active_scenario_for_user(db: Session, user_id: int) -> Optional[Scenario]:
    """Get the most recent active scenario for the supplied user."""

    return (
        db.query(Scenario)
        .join(ScenarioUser, ScenarioUser.scenario_id == Scenario.id)
        .filter(ScenarioUser.user_id == user_id, Scenario.status.in_(_active_statuses()))
        .order_by(Scenario.created_at.desc())
        .first()
    )


# Backward compatible alias
get_active_game_for_user = get_active_scenario_for_user


def _fallback_numeric(value: Optional[float]) -> float:
    return float(value or 0)


def get_participant_metrics(db: Session, scenario_user_id: int, scenario_id: int) -> Dict[str, Any]:
    """Calculate key metrics for a scenario_user in a specific scenario."""

    scenario_user = (
        db.query(ScenarioUser)
        .filter(ScenarioUser.id == scenario_user_id, ScenarioUser.scenario_id == scenario_id)
        .first()
    )
    if not scenario_user:
        return {}

    scenario_user_periods = (
        db.query(ScenarioUserPeriod)
        .join(ScenarioRound, ScenarioUserPeriod.round_id == ScenarioRound.id)
        .filter(ScenarioUserPeriod.scenario_user_id == scenario_user_id, ScenarioRound.scenario_id == scenario_id)
        .order_by(ScenarioRound.round_number.asc())
        .all()
    )

    if not scenario_user_periods:
        current_inventory = _fallback_numeric(getattr(scenario_user, "current_inventory", getattr(scenario_user, "inventory", 0)))
        backlog = _fallback_numeric(getattr(scenario_user, "current_backlog", getattr(scenario_user, "backlog", 0)))
        total_cost = _fallback_numeric(getattr(scenario_user, "total_cost", getattr(scenario_user, "cost", 0)))
        return {
            "current_inventory": current_inventory,
            "inventory_change": 0,
            "backlog": backlog,
            "total_cost": total_cost,
            "avg_weekly_cost": 0,
            "service_level": 1.0,
            "service_level_change": 0,
        }

    latest_round = scenario_user_periods[-1]
    previous_round = scenario_user_periods[-2] if len(scenario_user_periods) > 1 else None

    current_inventory = _fallback_numeric(
        getattr(latest_round, "inventory_after", None)
        if getattr(latest_round, "inventory_after", None) is not None
        else getattr(latest_round, "inventory_before", None)
    )
    previous_inventory = _fallback_numeric(
        getattr(previous_round, "inventory_after", None)
        if previous_round and getattr(previous_round, "inventory_after", None) is not None
        else getattr(latest_round, "inventory_before", None)
    )
    inventory_change = 0.0
    if previous_inventory:
        inventory_change = ((current_inventory - previous_inventory) / previous_inventory) * 100

    backlog = _fallback_numeric(
        getattr(latest_round, "backorders_after", None)
        if getattr(latest_round, "backorders_after", None) is not None
        else getattr(latest_round, "backorders_before", None)
    )

    total_cost = sum(_fallback_numeric(pr.total_cost) for pr in scenario_user_periods)
    avg_weekly_cost = total_cost / len(scenario_user_periods) if scenario_user_periods else 0

    fulfilled_rounds = [1 if _fallback_numeric(pr.backorders_after) == 0 else 0 for pr in scenario_user_periods]
    service_level = sum(fulfilled_rounds) / len(scenario_user_periods) if scenario_user_periods else 1.0
    if len(scenario_user_periods) > 1:
        previous_service_level = sum(fulfilled_rounds[:-1]) / (len(scenario_user_periods) - 1)
    else:
        previous_service_level = service_level
    service_level_change = service_level - previous_service_level

    return {
        "current_inventory": current_inventory,
        "inventory_change": inventory_change,
        "backlog": backlog,
        "total_cost": total_cost,
        "avg_weekly_cost": avg_weekly_cost,
        "service_level": service_level,
        "service_level_change": service_level_change,
    }


# Backward compatible alias
get_player_metrics = get_participant_metrics


def get_time_series_metrics(db: Session, scenario_user_id: int, scenario_id: int, role: str) -> List[Dict[str, Any]]:
    """Build a period-by-period time series for the requested scenario_user."""

    rounds = (
        db.query(ScenarioRound)
        .filter(ScenarioRound.scenario_id == scenario_id)
        .order_by(ScenarioRound.round_number.asc())
        .all()
    )

    scenario_user_periods = (
        db.query(ScenarioUserPeriod)
        .join(ScenarioRound, ScenarioUserPeriod.round_id == ScenarioRound.id)
        .filter(ScenarioUserPeriod.scenario_user_id == scenario_user_id, ScenarioRound.scenario_id == scenario_id)
        .all()
    )
    rounds_by_id = {pr.round_id: pr for pr in scenario_user_periods}

    series: List[Dict[str, Any]] = []
    for round_ in rounds:
        participant_round = rounds_by_id.get(round_.id)

        order = _fallback_numeric(getattr(participant_round, "order_placed", None)) if participant_round else 0
        inventory = _fallback_numeric(getattr(participant_round, "inventory_after", None)) if participant_round else 0
        backlog = _fallback_numeric(getattr(participant_round, "backorders_after", None)) if participant_round else 0
        cost = _fallback_numeric(getattr(participant_round, "total_cost", None)) if participant_round else 0
        supply = _fallback_numeric(getattr(participant_round, "order_received", None)) if participant_round else 0
        reason = getattr(participant_round, "comment", None) if participant_round else None

        entry = {
            "week": getattr(round_, "round_number", 0),
            "inventory": inventory,
            "order": order,
            "cost": cost,
            "backlog": backlog,
            "demand": getattr(round_, "customer_demand", None),
            "supply": supply if supply else None,
            "reason": reason,
        }

        # Limit demand visibility based on role, mirroring the previous behaviour
        if role not in ["RETAILER", "MANUFACTURER", "DISTRIBUTOR"]:
            entry["demand"] = None
        if role not in ["SUPPLIER", "MANUFACTURER", "DISTRIBUTOR"]:
            entry["supply"] = None

        series.append(entry)

    return series
