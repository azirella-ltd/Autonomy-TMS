#!/usr/bin/env python3
"""Export per-round supply chain metrics for one or more scenarios."""

from __future__ import annotations

import argparse
import csv
import json
import os
from typing import Dict, Any, Iterable

from main import SessionLocal, _coerce_game_config
from app.models.scenario import Scenario, Round

ROLES = ["retailer", "wholesaler", "distributor", "manufacturer"]

CSV_COLUMNS = [
    "Round",
    "Node",
    "Starting Inventory",
    "Demand",
    "Supply",
    "Ending Inventory",
    "Backlog Cost",
    "Holding Cost",
    "Comment",
]


def _net_inventory(state: Dict[str, Any]) -> int:
    inventory = int(state.get("inventory", 0))
    backlog = int(state.get("backlog", 0))
    return inventory - backlog


def export_game(scenario_id: int, output_dir: str) -> str:
    session = SessionLocal()
    try:
        scenario = session.query(Scenario).filter(Scenario.id == scenario_id).first()
        if not scenario:
            raise RuntimeError(f"Scenario {scenario_id} not found")

        config = _coerce_game_config(scenario)
        history = config.get("history", [])
        if not history:
            rounds = session.query(Round).filter(Round.scenario_id == scenario_id).order_by(Round.round_number.asc()).all()
            history = []
            for round_record in rounds:
                payload = round_record.config or {}
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except json.JSONDecodeError:
                        payload = {}
                entry = {
                    "round": round_record.round_number,
                    "demand": payload.get("demand", 0),
                    "orders": payload.get("orders", {}),
                    "node_states": payload.get("node_states", {}),
                }
                history.append(entry)
    finally:
        session.close()

    if not history:
        raise RuntimeError(f"Scenario {scenario_id} has no recorded rounds to export.")

    initial_state = config.get("initial_state", {})
    if not initial_state:
        base_inventory = int(config.get("simulation_parameters", {}).get("initial_inventory", 12))
        initial_state = {
            role: {"inventory": base_inventory, "backlog": 0} for role in ROLES
        }

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"scenario_{scenario_id}_rounds.csv")

    prev_inventory = {role: _net_inventory(initial_state.get(role, {})) for role in ROLES}
    pipelines = {
        role: [0] * max(1, int(config.get("simulation_parameters", {}).get("shipping_lead_time", 1)))
        for role in ROLES
    }

    params = config.get("simulation_parameters", {})
    holding_rate = float(params.get("holding_cost_per_unit", params.get("holding_cost", 0.5)))
    backlog_rate = float(params.get("backorder_cost_per_unit", params.get("backorder_cost", 5.0)))

    with open(output_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_COLUMNS)

        # Round 0 baseline
        for role in ROLES:
            base_state = initial_state.get(role, {})
            starting_inventory = _net_inventory(base_state)
            writer.writerow([
                0,
                role,
                starting_inventory,
                0,
                0,
                starting_inventory,
                0,
                0,
                "",
            ])
            prev_inventory[role] = starting_inventory

        for entry in history:
            orders = entry.get("orders", {})
            demand_map = {
                "retailer": int(entry.get("demand", 0)),
                "wholesaler": int(orders.get("retailer", {}).get("quantity", 0)),
                "distributor": int(orders.get("wholesaler", {}).get("quantity", 0)),
                "manufacturer": int(orders.get("distributor", {}).get("quantity", 0)),
            }

            round_number = entry.get("round")
            for role in ROLES:
                starting_inventory = prev_inventory[role]
                supply_value = pipelines[role].pop(0) if pipelines[role] else 0
                demand_value = demand_map.get(role, 0)
                ending_inventory = starting_inventory + supply_value - demand_value
                holding_cost = max(starting_inventory, 0) * holding_rate
                backlog_cost = max(-starting_inventory, 0) * backlog_rate
                order_record = orders.get(role, {})
                comment_text = ""
                if isinstance(order_record, dict):
                    comment_text = str(order_record.get("comment", "") or "")

                writer.writerow(
                    [
                        round_number,
                        role,
                        starting_inventory,
                        demand_value,
                        supply_value,
                        ending_inventory,
                        backlog_cost,
                        holding_cost,
                        comment_text,
                    ]
                )

                order_qty = int(orders.get(role, {}).get("quantity", 0))
                pipelines[role].append(order_qty)
                prev_inventory[role] = ending_inventory

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scenario-id",
        type=int,
        action="append",
        dest="scenario_ids",
        help="Specific scenario ID to export (can be passed multiple times).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Export every scenario in the database (ignores --scenario-id).",
    )
    parser.add_argument(
        "--output-dir",
        default="exports",
        help="Directory where CSV files will be written (default: exports).",
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        if args.all:
            scenario_data = session.query(Scenario.id, Scenario.name).order_by(Scenario.id.asc()).all()
        elif args.scenario_ids:
            scenario_data = session.query(Scenario.id, Scenario.name).filter(Scenario.id.in_(set(args.scenario_ids))).order_by(Scenario.id.asc()).all()
            missing = set(args.scenario_ids) - {gid for gid, _ in scenario_data}
            if missing:
                raise SystemExit(f"Scenario id(s) not found: {', '.join(str(i) for i in sorted(missing))}")
        else:
            raise SystemExit("Must specify --all or at least one --scenario-id")
    finally:
        session.close()

    if not scenario_data:
        raise SystemExit("No scenarios to export.")

    for scenario_id, name in scenario_data:
        try:
            path = export_game(scenario_id, args.output_dir)
            label = f" ({name})" if name else ""
            print(f"Exported scenario {scenario_id}{label} -> {path}")
        except RuntimeError as exc:
            print(f"Skipping scenario {scenario_id}: {exc}")


if __name__ == "__main__":
    main()
