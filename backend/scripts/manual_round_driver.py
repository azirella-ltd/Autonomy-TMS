"""Interactive driver for stepping through simulation periods in a debugger.

Run this script under Windsurf's ``Python: Launch current file`` configuration
while the FastAPI backend is attached to the debugger. The script pauses before
each round so you can switch back to the backend debugger, inspect breakpoints,
and then resume execution when you're ready to see the next node advance.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional

import requests


BASE_URL = "http://localhost:8000/api/v1"
AUTH_EMAIL = "admin@example.com"
AUTH_PASSWORD = "Admin123!"


class BackendError(RuntimeError):
    """Raised when the simulation backend responds with an error."""


def _raise_for_status(response: requests.Response) -> None:
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:  # pragma: no cover - convenience wrapper
        detail = exc.response.text if exc.response is not None else "<no body>"
        raise BackendError(f"Backend request failed: {exc}\n{detail}") from exc


def _post_json(
    path: str,
    *,
    token: str,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    response = requests.post(
        f"{BASE_URL}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload or {},
        timeout=30,
    )
    _raise_for_status(response)
    return response.json()


def _put(
    path: str,
    *,
    token: str,
    params: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    response = requests.put(
        f"{BASE_URL}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        params=params,
        json=json_data,
        timeout=30,
    )
    _raise_for_status(response)
    return response.json()


def _get(path: str, *, token: str) -> Dict[str, Any]:
    response = requests.get(
        f"{BASE_URL}{path}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    _raise_for_status(response)
    return response.json()


def _login() -> str:
    response = requests.post(
        f"{BASE_URL}/auth/token",
        data={"username": AUTH_EMAIL, "password": AUTH_PASSWORD},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    _raise_for_status(response)
    payload = response.json()
    return payload["access_token"]


@dataclass
class PlayerSnapshot:
    role: str
    inventory: int
    backlog: int
    incoming_shipments: Iterable[int]
    cost: float


def _format_player_snapshot(snapshot: PlayerSnapshot) -> str:
    shipments = ", ".join(str(val) for val in snapshot.incoming_shipments)
    return (
        f"{snapshot.role:>12}: inv={snapshot.inventory:>3}  backlog={snapshot.backlog:>3}"
        f"  pipeline=[{shipments}]  cost={snapshot.cost:>6.1f}"
    )


class ManualRoundDebugger:
    """Creates an AI-only scenario and advances it on demand."""

    def __init__(self, *, token: str) -> None:
        self.token = token
        self.scenario_id: Optional[int] = None

    # ------------------------------------------------------------------
    # Lifecycle helpers
    # ------------------------------------------------------------------
    def setup_game(
        self,
        *,
        max_periods: int = 12,
        supply_chain_config_id: int,
        demand_pattern: Optional[Dict[str, Any]] = None,
        policies: Optional[Dict[str, tuple[str, Dict[str, Any]]]] = None,
    ) -> None:
        payload: Dict[str, Any] = {
            "name": "Debugger walkthrough",
            "max_periods": max_periods,
            "supply_chain_config_id": supply_chain_config_id,
        }
        if demand_pattern is not None:
            payload["demand_pattern"] = demand_pattern

        created = _post_json("/agent-games/", token=self.token, payload=payload)
        self.scenario_id = int(created["scenario_id"])

        _post_json(f"/agent-games/{self.scenario_id}/start", token=self.token)

        # Default AI policies are acceptable for inspection, but you can tweak
        # them here if desired. The API call resets policy state, which keeps the
        # scenario deterministic while you experiment inside the debugger.
        policies = policies or {
            "retailer": ("naive", {}),
            "wholesaler": ("conservative", {"base_stock": 18}),
            "distributor": ("bullwhip", {"aggressiveness": 1.4}),
            "manufacturer": ("naive", {"base_stock": 24}),
        }
        for role, (strategy, params) in policies.items():
            _put(
                f"/agent-games/{self.scenario_id}/agent-strategy",
                token=self.token,
                params={"role": role, "strategy": strategy},
                json_data=params or {},
            )

    # ------------------------------------------------------------------
    # Round control
    # ------------------------------------------------------------------
    def play_next_round(self) -> Dict[str, Any]:
        if self.scenario_id is None:
            raise RuntimeError("Scenario is not initialised; call setup_game() first")
        return _post_json(f"/agent-games/{self.scenario_id}/play-round", token=self.token)

    def fetch_state(self) -> Dict[str, Any]:
        if self.scenario_id is None:
            raise RuntimeError("Scenario is not initialised; call setup_game() first")
        return _get(f"/agent-games/{self.scenario_id}/state", token=self.token)


def _print_state(state: Dict[str, Any]) -> None:
    print(f"\nRound {state['current_period']}/{state['max_periods']}  status={state['status']}")
    print("ScenarioUsers:")
    for scenario_user in state.get("scenario_users", []):
        snapshot = PlayerSnapshot(
            role=scenario_user["role"],
            inventory=int(scenario_user.get("inventory", 0)),
            backlog=int(scenario_user.get("backlog", 0)),
            incoming_shipments=scenario_user.get("incoming_shipments", []),
            cost=float(scenario_user.get("cost", 0.0)),
        )
        print("  " + _format_player_snapshot(snapshot))

    print("\nDemand pattern:")
    print(json.dumps(state.get("demand_pattern", {}), indent=2))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config-id",
        type=int,
        default=1,
        help="Supply chain configuration ID to seed the scenario (default: 1)",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=12,
        help="Maximum number of rounds to simulate (default: 12)",
    )
    return parser.parse_args()


def main() -> None:
    print("=== Manual Simulation debugger ===")
    args = _parse_args()
    token = _login()
    driver = ManualRoundDebugger(token=token)
    driver.setup_game(
        max_periods=args.max_periods,
        supply_chain_config_id=args.config_id,
    )

    while True:
        user_input = input("\nPress <enter> to play the next round, or 'q' to quit: ")
        if user_input.lower().startswith("q"):
            break

        result = driver.play_next_round()
        state = result.get("scenario_state") or driver.fetch_state()
        _print_state(state)

        if state.get("status") == "FINISHED":
            print("\nThe scenario has finished; restart the script for a new session.")
            break


if __name__ == "__main__":
    main()
