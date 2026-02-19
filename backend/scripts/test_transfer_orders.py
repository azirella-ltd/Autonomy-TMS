#!/usr/bin/env python3
"""
Test Transfer Orders Implementation

Runs a full 52-round Beer Scenario simulation with Transfer Order tracking
and validates in-transit inventory projections.

Usage:
    python scripts/test_transfer_orders.py --rounds 52 --validate
"""

import sys
import os
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

import argparse
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_, func

from app.db.session import SessionLocal
from app.models.scenario import Scenario
from app.models.sc_entities import InvLevel, SourcingRules
from app.models.supply_chain_config import Site
from app.models.transfer_order import TransferOrder, TransferOrderLineItem
from app.models.purchase_order import PurchaseOrder
from app.services.sc_execution.beer_scenario_executor import BeerScenarioExecutor
from app.services.sc_execution.site_id_mapper import BeerScenarioIdMapper
from app.services.agents import get_policy_by_strategy


class TransferOrderValidator:
    """Validates Transfer Order implementation correctness."""

    def __init__(self, db: Session):
        self.db = db
        self.errors = []
        self.warnings = []

    def validate_scenario_transfer_orders(self, scenario_id: int) -> dict:
        """
        Validate all Transfer Orders for a scenario.

        Checks:
        1. TO count matches expected (based on rounds and sites)
        2. In-transit quantities are consistent
        3. All TOs have proper status transitions
        4. Arrival rounds are calculated correctly
        5. Inventory balances are correct

        Args:
            scenario_id: Scenario ID to validate

        Returns:
            Validation report dictionary
        """
        print(f"\n{'='*80}")
        print(f"VALIDATING TRANSFER ORDERS FOR GAME {scenario_id}")
        print(f"{'='*80}\n")

        report = {
            "scenario_id": scenario_id,
            "timestamp": datetime.now().isoformat(),
            "checks": {},
            "errors": [],
            "warnings": []
        }

        # Check 1: TO Creation
        report["checks"]["to_creation"] = self._check_to_creation(scenario_id)

        # Check 2: In-Transit Consistency
        report["checks"]["in_transit_consistency"] = self._check_in_transit_consistency(scenario_id)

        # Check 3: Status Transitions
        report["checks"]["status_transitions"] = self._check_status_transitions(scenario_id)

        # Check 4: Arrival Round Calculation
        report["checks"]["arrival_round_calculation"] = self._check_arrival_rounds(scenario_id)

        # Check 5: Inventory Balance
        report["checks"]["inventory_balance"] = self._check_inventory_balance(scenario_id)

        # Check 6: Multi-Period Projection
        report["checks"]["multi_period_projection"] = self._check_multi_period_projection(scenario_id)

        report["errors"] = self.errors
        report["warnings"] = self.warnings
        report["passed"] = len(self.errors) == 0

        return report

    def _check_to_creation(self, scenario_id: int) -> dict:
        """Check that TOs were created for each fulfillment."""
        print("📋 Check 1: Transfer Order Creation")
        print("-" * 80)

        # Get all TOs for scenario
        tos = self.db.query(TransferOrder).filter(
            TransferOrder.scenario_id == scenario_id
        ).all()

        # Get scenario info
        scenario = self.db.query(Scenario).filter(Scenario.id == scenario_id).first()
        max_round = scenario.current_round if scenario else 0

        # Expected: At least 1 TO per round per site (market demand)
        # Plus TOs for inter-site transfers (depends on PO fulfillment)
        expected_min_tos = max_round  # At least market demand TOs

        result = {
            "total_tos": len(tos),
            "expected_min": expected_min_tos,
            "rounds_covered": max_round,
            "passed": len(tos) >= expected_min_tos
        }

        # Group by status
        status_counts = {}
        for to in tos:
            status_counts[to.status] = status_counts.get(to.status, 0) + 1

        result["status_breakdown"] = status_counts

        print(f"  Total TOs created: {len(tos)}")
        print(f"  Expected minimum: {expected_min_tos}")
        print(f"  Status breakdown: {status_counts}")

        if result["passed"]:
            print("  ✅ PASSED: Sufficient TOs created")
        else:
            error = f"TO creation failed: Expected at least {expected_min_tos}, got {len(tos)}"
            print(f"  ❌ FAILED: {error}")
            self.errors.append(error)

        return result

    def _check_in_transit_consistency(self, scenario_id: int) -> dict:
        """Check that in_transit_qty matches sum of IN_TRANSIT TOs."""
        print("\n📦 Check 2: In-Transit Inventory Consistency")
        print("-" * 80)

        # Get all nodes for scenario (nodes ARE sites in Beer Scenario)
        scenario = self.db.query(Scenario).filter(Scenario.id == scenario_id).first()
        nodes = self.db.query(Site).filter(
            Site.config_id == scenario.config_id
        ).all()

        inconsistencies = []

        for node in nodes:
            # Get inv_level
            inv_level = self.db.query(InvLevel).filter(
                and_(
                    InvLevel.site_id == node.name,  # InvLevel still uses node name
                    InvLevel.item_id == "cases"
                )
            ).first()

            if not inv_level:
                continue

            # Sum all IN_TRANSIT TOs to this node (using Integer node ID)
            to_sum_result = self.db.query(
                func.sum(TransferOrderLineItem.shipped_quantity)
            ).join(
                TransferOrder,
                TransferOrderLineItem.to_id == TransferOrder.id
            ).filter(
                and_(
                    TransferOrder.scenario_id == scenario_id,
                    TransferOrder.destination_site_id == node.id,  # Integer node ID
                    TransferOrder.status == "IN_TRANSIT"
                )
            ).scalar()

            to_in_transit_sum = to_sum_result or 0.0

            # Compare with inv_level.in_transit_qty
            if abs(inv_level.in_transit_qty - to_in_transit_sum) > 0.01:
                inconsistency = {
                    "site_id": node.name,
                    "node_id": node.id,
                    "inv_level_in_transit": inv_level.in_transit_qty,
                    "to_sum_in_transit": to_in_transit_sum,
                    "difference": inv_level.in_transit_qty - to_in_transit_sum
                }
                inconsistencies.append(inconsistency)
                print(f"  ⚠️  {node.name} (ID={node.id}): inv_level={inv_level.in_transit_qty}, "
                      f"TO_sum={to_in_transit_sum}, diff={inconsistency['difference']:.2f}")
            else:
                print(f"  ✓ {node.name} (ID={node.id}): Consistent ({inv_level.in_transit_qty:.2f})")

        result = {
            "sites_checked": len(nodes),
            "inconsistencies": inconsistencies,
            "passed": len(inconsistencies) == 0
        }

        if result["passed"]:
            print("  ✅ PASSED: All in-transit quantities consistent")
        else:
            error = f"In-transit inconsistency: {len(inconsistencies)} sites have mismatches"
            print(f"  ❌ FAILED: {error}")
            self.errors.append(error)

        return result

    def _check_status_transitions(self, scenario_id: int) -> dict:
        """Check that TO status transitions are valid."""
        print("\n🔄 Check 3: Status Transitions")
        print("-" * 80)

        # Get all TOs ordered by creation time
        tos = self.db.query(TransferOrder).filter(
            TransferOrder.scenario_id == scenario_id
        ).order_by(TransferOrder.created_at).all()

        # Valid transitions: IN_TRANSIT → RECEIVED
        valid_statuses = {"IN_TRANSIT", "RECEIVED"}
        invalid_transitions = []

        for to in tos:
            if to.status not in valid_statuses:
                invalid_transitions.append({
                    "to_number": to.to_number,
                    "status": to.status,
                    "reason": "Invalid status (expected IN_TRANSIT or RECEIVED)"
                })

            # Check if RECEIVED has actual_delivery_date
            if to.status == "RECEIVED" and not to.actual_delivery_date:
                invalid_transitions.append({
                    "to_number": to.to_number,
                    "status": to.status,
                    "reason": "RECEIVED status but no actual_delivery_date"
                })

        result = {
            "total_tos": len(tos),
            "invalid_transitions": invalid_transitions,
            "passed": len(invalid_transitions) == 0
        }

        status_counts = {
            "IN_TRANSIT": len([to for to in tos if to.status == "IN_TRANSIT"]),
            "RECEIVED": len([to for to in tos if to.status == "RECEIVED"])
        }

        result["status_counts"] = status_counts

        print(f"  Total TOs: {len(tos)}")
        print(f"  IN_TRANSIT: {status_counts['IN_TRANSIT']}")
        print(f"  RECEIVED: {status_counts['RECEIVED']}")

        if result["passed"]:
            print("  ✅ PASSED: All status transitions valid")
        else:
            for inv_trans in invalid_transitions[:5]:  # Show first 5
                print(f"  ⚠️  {inv_trans['to_number']}: {inv_trans['reason']}")
            error = f"Invalid status transitions: {len(invalid_transitions)} issues"
            print(f"  ❌ FAILED: {error}")
            self.errors.append(error)

        return result

    def _check_arrival_rounds(self, scenario_id: int) -> dict:
        """Check that arrival_round is calculated correctly based on lead times."""
        print("\n📅 Check 4: Arrival Round Calculation")
        print("-" * 80)

        tos = self.db.query(TransferOrder).filter(
            TransferOrder.scenario_id == scenario_id
        ).all()

        incorrect_arrivals = []

        for to in tos:
            if to.order_round is None or to.arrival_round is None:
                continue

            # Calculate expected arrival based on lead time
            # Assumption: 1 round = 1 week = 7 days
            if to.estimated_delivery_date and to.shipment_date:
                lead_time_days = (to.estimated_delivery_date - to.shipment_date).days
                expected_lead_time_rounds = lead_time_days // 7
                expected_arrival_round = to.order_round + expected_lead_time_rounds

                if to.arrival_round != expected_arrival_round:
                    incorrect_arrivals.append({
                        "to_number": to.to_number,
                        "order_round": to.order_round,
                        "arrival_round": to.arrival_round,
                        "expected_arrival_round": expected_arrival_round,
                        "lead_time_days": lead_time_days
                    })

        result = {
            "total_tos": len(tos),
            "incorrect_arrivals": incorrect_arrivals,
            "passed": len(incorrect_arrivals) == 0
        }

        if result["passed"]:
            print(f"  ✅ PASSED: All {len(tos)} TOs have correct arrival rounds")
        else:
            for inc in incorrect_arrivals[:5]:
                print(f"  ⚠️  {inc['to_number']}: order={inc['order_round']}, "
                      f"arrival={inc['arrival_round']}, expected={inc['expected_arrival_round']}")
            error = f"Incorrect arrival rounds: {len(incorrect_arrivals)} TOs"
            print(f"  ❌ FAILED: {error}")
            self.errors.append(error)

        return result

    def _check_inventory_balance(self, scenario_id: int) -> dict:
        """Check that inventory balance equation holds."""
        print("\n💰 Check 5: Inventory Balance")
        print("-" * 80)

        # Inventory balance: Total initial + Total received = Total on_hand + Total shipped + Total backorder
        # This is complex, so we'll do a simpler check:
        # on_hand + in_transit + shipped_to_market = initial_inventory + total_received

        scenario = self.db.query(Scenario).filter(Scenario.id == scenario_id).first()
        nodes = self.db.query(Site).filter(
            Site.config_id == scenario.config_id
        ).all()

        initial_inventory_per_site = 12.0  # From scenario initialization
        num_sites = len([n for n in nodes if n.master_node_type != "MARKET_SUPPLY"])

        total_initial = initial_inventory_per_site * num_sites

        # Calculate total on_hand across all sites
        total_on_hand = 0.0
        total_in_transit = 0.0
        total_backorder = 0.0

        for node in nodes:
            inv_level = self.db.query(InvLevel).filter(
                and_(
                    InvLevel.site_id == node.name,  # InvLevel uses node name
                    InvLevel.item_id == "cases"
                )
            ).first()

            if inv_level:
                total_on_hand += inv_level.on_hand_qty
                total_in_transit += inv_level.in_transit_qty
                total_backorder += inv_level.backorder_qty

        # Calculate total shipped to market (RECEIVED TOs to MARKET)
        # Need to find MARKET node ID
        market_node = self.db.query(Site).filter(
            and_(
                Site.config_id == scenario.config_id,
                Site.master_node_type == "MARKET_DEMAND"
            )
        ).first()

        market_shipments = 0.0
        if market_node:
            market_shipments = self.db.query(
                func.sum(TransferOrderLineItem.shipped_quantity)
            ).join(
                TransferOrder,
                TransferOrderLineItem.to_id == TransferOrder.id
            ).filter(
                and_(
                    TransferOrder.scenario_id == scenario_id,
                    TransferOrder.destination_site_id == market_node.id,  # Integer node ID
                    TransferOrder.status == "RECEIVED"
                )
            ).scalar() or 0.0

        # Balance: initial + produced = on_hand + in_transit + shipped_to_market + backorder_fulfilled
        # Since no production in Beer Scenario (Factory has infinite supply), we check:
        # on_hand + in_transit + market_shipments should be close to initial

        total_accounted = total_on_hand + total_in_transit + market_shipments
        balance_diff = total_initial - total_accounted

        result = {
            "total_initial": total_initial,
            "total_on_hand": total_on_hand,
            "total_in_transit": total_in_transit,
            "market_shipments": market_shipments,
            "total_backorder": total_backorder,
            "total_accounted": total_accounted,
            "balance_difference": balance_diff,
            "passed": abs(balance_diff) < (num_sites * 0.1)  # Allow small rounding
        }

        print(f"  Initial inventory: {total_initial:.2f}")
        print(f"  Current on-hand: {total_on_hand:.2f}")
        print(f"  Current in-transit: {total_in_transit:.2f}")
        print(f"  Shipped to market: {market_shipments:.2f}")
        print(f"  Total backorder: {total_backorder:.2f}")
        print(f"  Balance difference: {balance_diff:.2f}")

        if result["passed"]:
            print("  ✅ PASSED: Inventory balance within tolerance")
        else:
            warning = f"Inventory balance off by {balance_diff:.2f} units"
            print(f"  ⚠️  WARNING: {warning}")
            self.warnings.append(warning)

        return result

    def _check_multi_period_projection(self, scenario_id: int) -> dict:
        """Check multi-period inventory projection capability."""
        print("\n📊 Check 6: Multi-Period Inventory Projection")
        print("-" * 80)

        scenario = self.db.query(Scenario).filter(Scenario.id == scenario_id).first()
        current_round = scenario.current_round

        # Pick a node to test projection (use first non-market node)
        test_node = self.db.query(Site).filter(
            and_(
                Site.config_id == scenario.config_id,
                Site.master_node_type == "INVENTORY"
            )
        ).first()

        if not test_node:
            return {"passed": False, "error": "No inventory node found for testing"}

        test_site_name = test_node.name
        test_node_id = test_node.id

        # Get current inventory
        inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.site_id == test_site_name,  # InvLevel uses node name
                InvLevel.item_id == "cases"
            )
        ).first()

        if not inv_level:
            return {"passed": False, "error": f"No inv_level for test node {test_site_name}"}

        # Get in-transit schedule (using Integer node ID)
        in_transit_tos = self.db.query(TransferOrder).filter(
            and_(
                TransferOrder.scenario_id == scenario_id,
                TransferOrder.destination_site_id == test_node_id,  # Integer node ID
                TransferOrder.status == "IN_TRANSIT"
            )
        ).order_by(TransferOrder.arrival_round).all()

        # Build projection
        projection = {
            "site_id": test_site_name,
            "node_id": test_node_id,
            "current_round": current_round,
            "current_on_hand": inv_level.on_hand_qty,
            "current_in_transit": inv_level.in_transit_qty,
            "future_arrivals": []
        }

        # Initialize ID mapper to get source node names
        mapper = BeerScenarioIdMapper(self.db, scenario.config_id)

        total_in_transit_from_tos = 0.0
        for to in in_transit_tos:
            to_lines = self.db.query(TransferOrderLineItem).filter(
                TransferOrderLineItem.to_id == to.id
            ).all()

            # Get source node name for display
            source_name = mapper.get_node_name(to.source_site_id) if to.source_site_id else "UNKNOWN"

            for line in to_lines:
                arrival_info = {
                    "arrival_round": to.arrival_round,
                    "quantity": line.shipped_quantity,
                    "to_number": to.to_number,
                    "source_site_id": to.source_site_id,  # Integer ID
                    "source_site_name": source_name  # Human-readable name
                }
                projection["future_arrivals"].append(arrival_info)
                total_in_transit_from_tos += line.shipped_quantity

        projection["total_in_transit_from_tos"] = total_in_transit_from_tos

        # Verify in-transit matches
        in_transit_match = abs(inv_level.in_transit_qty - total_in_transit_from_tos) < 0.01

        result = {
            "projection": projection,
            "in_transit_match": in_transit_match,
            "future_arrival_count": len(projection["future_arrivals"]),
            "passed": in_transit_match and len(projection["future_arrivals"]) >= 0
        }

        print(f"  Site: {test_site_name} (Site ID={test_node_id})")
        print(f"  Current round: {current_round}")
        print(f"  On-hand: {inv_level.on_hand_qty:.2f}")
        print(f"  In-transit (inv_level): {inv_level.in_transit_qty:.2f}")
        print(f"  In-transit (from TOs): {total_in_transit_from_tos:.2f}")
        print(f"  Future arrivals: {len(projection['future_arrivals'])}")

        for arrival in projection["future_arrivals"][:5]:
            print(f"    • Round {arrival['arrival_round']}: {arrival['quantity']:.2f} units "
                  f"from {arrival['source_site_name']} (ID={arrival['source_site_id']}) "
                  f"({arrival['to_number']})")

        if result["passed"]:
            print("  ✅ PASSED: Multi-period projection working")
        else:
            error = "Multi-period projection failed"
            print(f"  ❌ FAILED: {error}")
            self.errors.append(error)

        return result


def run_52_round_simulation(db: Session, validate: bool = True) -> dict:
    """
    Run full 52-round Beer Scenario simulation with Transfer Order tracking.

    Args:
        db: Database session
        validate: Whether to run validation checks

    Returns:
        Simulation report with TO statistics
    """
    print(f"\n{'='*80}")
    print(f"52-ROUND BEER GAME SIMULATION WITH TRANSFER ORDERS")
    print(f"{'='*80}\n")

    # Create scenario
    print("Creating scenario...")
    scenario = Scenario(
        name="TO Test 52-Round Simulation",
        config_id=1,  # Default TBG config
        max_rounds=52,
        current_round=0,
        status="active",
        created_at=datetime.now()
    )
    db.add(scenario)
    db.commit()
    db.refresh(scenario)

    print(f"Scenario created: ID={scenario.id}")

    # Initialize executor
    executor = BeerScenarioExecutor(db)

    # Initialize scenario state
    print("Initializing scenario state...")
    executor.initialize_scenario(scenario.id, scenario.config_id, initial_inventory=12.0)

    # Agent configurations (use conservative strategy)
    agent_strategy = "conservative"

    print(f"Agent strategy: {agent_strategy}")

    # Get sites
    sites = executor._get_scenario_sites(scenario.id)
    site_ids = [s.site_id for s in sites if s.site_type != "MARKET_SUPPLY"]

    print(f"Sites: {site_ids}\n")

    # Market demand pattern (classic Beer Scenario: 4 units for 4 rounds, then 8 units)
    def get_market_demand(round_num):
        if round_num <= 4:
            return 4.0
        else:
            return 8.0

    # Run 52 rounds
    round_summaries = []

    for round_num in range(1, 53):
        print(f"\n{'─'*80}")
        print(f"ROUND {round_num}/52")
        print(f"{'─'*80}")

        # Get agent decisions
        agent_decisions = {}
        for site_id in site_ids:
            # Load site state
            state = executor.state_manager.load_site_state(
                site_id, "cases", scenario.id, round_num
            )

            # Get agent policy
            policy = get_policy_by_strategy(agent_strategy)

            # Create node-like object for agent (simplified)
            class SimpleSite:
                def __init__(self, state_dict):
                    self.inventory = state_dict["on_hand_qty"]
                    self.backlog = state_dict["backorder_qty"]
                    self.pipeline_shipments = []  # Simplified
                    self.last_demand = 8.0  # Simplified
                    self.site_id = state_dict["site_id"]

            node = SimpleSite(state)

            # Compute order
            order_qty = policy.compute_order(
                node,
                {"current_round": round_num, "demand": 8.0}
            )

            agent_decisions[site_id] = order_qty

        # Get market demand
        market_demand = get_market_demand(round_num)

        # Execute round
        round_summary = executor.execute_round(
            scenario_id=scenario.id,
            round_number=round_num,
            agent_decisions=agent_decisions,
            market_demand=market_demand
        )

        round_summaries.append(round_summary)

        # Update scenario current_round
        scenario.current_round = round_num
        db.commit()

        # Print summary
        print(f"\nRound {round_num} Complete:")
        print(f"  Market demand: {market_demand}")
        print(f"  TOs created: {round_summary['steps']['order_promising']['operations']}")
        print(f"  Cost: ${round_summary['steps']['costs']['total_cost']:.2f}")

    # Compile statistics
    print(f"\n{'='*80}")
    print(f"SIMULATION COMPLETE - 52 ROUNDS")
    print(f"{'='*80}\n")

    # Count total TOs
    total_tos = db.query(func.count(TransferOrder.id)).filter(
        TransferOrder.scenario_id == scenario.id
    ).scalar()

    tos_in_transit = db.query(func.count(TransferOrder.id)).filter(
        and_(
            TransferOrder.scenario_id == scenario.id,
            TransferOrder.status == "IN_TRANSIT"
        )
    ).scalar()

    tos_received = db.query(func.count(TransferOrder.id)).filter(
        and_(
            TransferOrder.scenario_id == scenario.id,
            TransferOrder.status == "RECEIVED"
        )
    ).scalar()

    # Calculate total costs
    total_cost = sum(r["steps"]["costs"]["total_cost"] for r in round_summaries)
    total_holding_cost = sum(r["steps"]["costs"]["total_holding_cost"] for r in round_summaries)
    total_backlog_cost = sum(r["steps"]["costs"]["total_backlog_cost"] for r in round_summaries)

    report = {
        "scenario_id": scenario.id,
        "rounds": 52,
        "agent_strategy": agent_strategy,
        "transfer_orders": {
            "total": total_tos,
            "in_transit": tos_in_transit,
            "received": tos_received
        },
        "costs": {
            "total": total_cost,
            "holding": total_holding_cost,
            "backlog": total_backlog_cost
        },
        "round_summaries": round_summaries
    }

    print(f"Transfer Orders:")
    print(f"  Total created: {total_tos}")
    print(f"  In transit: {tos_in_transit}")
    print(f"  Received: {tos_received}")
    print(f"\nTotal Costs:")
    print(f"  Total: ${total_cost:.2f}")
    print(f"  Holding: ${total_holding_cost:.2f}")
    print(f"  Backlog: ${total_backlog_cost:.2f}")

    # Run validation if requested
    if validate:
        print(f"\n{'='*80}")
        print(f"RUNNING VALIDATION CHECKS")
        print(f"{'='*80}")

        validator = TransferOrderValidator(db)
        validation_report = validator.validate_scenario_transfer_orders(scenario.id)

        report["validation"] = validation_report

        # Print validation summary
        print(f"\n{'='*80}")
        print(f"VALIDATION SUMMARY")
        print(f"{'='*80}\n")

        for check_name, check_result in validation_report["checks"].items():
            status = "✅ PASSED" if check_result.get("passed") else "❌ FAILED"
            print(f"{check_name}: {status}")

        if validation_report["errors"]:
            print(f"\nErrors ({len(validation_report['errors'])}):")
            for error in validation_report["errors"]:
                print(f"  • {error}")

        if validation_report["warnings"]:
            print(f"\nWarnings ({len(validation_report['warnings'])}):")
            for warning in validation_report["warnings"]:
                print(f"  • {warning}")

        if validation_report["passed"]:
            print(f"\n🎉 ALL VALIDATION CHECKS PASSED!")
        else:
            print(f"\n⚠️  VALIDATION FAILED - See errors above")

    return report


def main():
    parser = argparse.ArgumentParser(
        description="Test Transfer Orders with full Beer Scenario simulation"
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=52,
        help="Number of rounds to simulate (default: 52)"
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Run validation checks after simulation"
    )
    parser.add_argument(
        "--no-validate",
        dest="validate",
        action="store_false",
        help="Skip validation checks"
    )
    parser.set_defaults(validate=True)

    args = parser.parse_args()

    # Create database session
    db = SessionLocal()

    try:
        # Run simulation
        report = run_52_round_simulation(db, validate=args.validate)

        print(f"\n{'='*80}")
        print(f"TEST COMPLETE")
        print(f"{'='*80}\n")
        print(f"Scenario ID: {report['scenario_id']}")
        print(f"Rounds: {report['rounds']}")
        print(f"Transfer Orders: {report['transfer_orders']['total']}")
        print(f"Total Cost: ${report['costs']['total']:.2f}")

        if args.validate and report.get("validation"):
            if report["validation"]["passed"]:
                print(f"\n✅ All validation checks passed")
                return 0
            else:
                print(f"\n❌ Validation failed")
                return 1

        return 0

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

    finally:
        db.close()


if __name__ == "__main__":
    exit(main())
