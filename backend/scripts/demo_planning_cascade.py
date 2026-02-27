#!/usr/bin/env python3
"""
Planning Cascade Demo Script

Demonstrates the full planning cascade for a Food Dist distributor:
S&OP → MPS → Supply Agent → Allocation Agent

Run with:
    cd backend
    python scripts/demo_planning_cascade.py

Options:
    --no-pause      Run without pauses (for video recording)
    --delay N       Delay N seconds between steps (default: 3 for no-pause mode)
"""

import sys
import os
import argparse
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import date
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
from rich import print as rprint

# Import the cascade components
from app.services.food_dist_config_generator import FoodDistCascadeDataGenerator
from app.services.planning_cascade.sop_service import (
    SOPParameters, ServiceTierTarget, CategoryPolicy, create_default_sop_parameters_for_food_dist
)

console = Console()

# Global config for pause behavior
INTERACTIVE_MODE = True
STEP_DELAY = 3  # seconds between steps in non-interactive mode


def wait_for_next():
    """Wait for user input or delay based on mode."""
    if INTERACTIVE_MODE:
        input("\nPress Enter to continue...")
    else:
        console.print(f"\n[dim]Next step in {STEP_DELAY} seconds...[/dim]")
        time.sleep(STEP_DELAY)


def demo_step_1_sop_policy():
    """Demonstrate S&OP Policy Envelope creation"""
    console.rule("[bold blue]Step 1: S&OP Policy Envelope[/bold blue]")

    # Get default parameters for Food Dist
    sop_params = create_default_sop_parameters_for_food_dist()

    # Display service tiers
    table = Table(title="Service Level Targets by Segment")
    table.add_column("Segment", style="cyan")
    table.add_column("OTIF Floor", justify="right")
    table.add_column("Fill Rate Target", justify="right")

    for tier in sop_params.service_tiers:
        table.add_row(
            tier.segment.upper(),
            f"{tier.otif_floor:.0%}",
            f"{tier.fill_rate_target:.0%}"
        )
    console.print(table)

    # Display category policies
    table2 = Table(title="Inventory Policies by Category")
    table2.add_column("Category", style="cyan")
    table2.add_column("Safety Stock (WOS)", justify="right")
    table2.add_column("DOS Ceiling", justify="right")
    table2.add_column("Expedite Cap", justify="right")

    for policy in sop_params.category_policies:
        table2.add_row(
            policy.category.replace("_", " ").title(),
            f"{policy.safety_stock_wos:.1f} weeks",
            f"{policy.dos_ceiling} days",
            f"${policy.expedite_cap:,.0f}"
        )
    console.print(table2)

    # Display financial guardrails
    console.print(Panel(
        f"[bold]Financial Guardrails[/bold]\n"
        f"• Total Inventory Cap: ${sop_params.total_inventory_cap:,.0f}\n"
        f"• GMROI Target: {sop_params.gmroi_target:.1f}x",
        title="θ_SOP Parameters"
    ))

    return sop_params


def demo_step_2_inventory_state():
    """Demonstrate inventory and demand data generation"""
    console.rule("[bold blue]Step 2: Current Inventory State[/bold blue]")

    generator = FoodDistCascadeDataGenerator(seed=42)
    data = generator.generate_inventory_and_demand_data(planning_horizon_days=28)

    # Display products
    table = Table(title=f"Inventory State ({len(data['products'])} SKUs)")
    table.add_column("SKU", style="cyan")
    table.add_column("Name")
    table.add_column("Category")
    table.add_column("On Hand", justify="right")
    table.add_column("In Transit", justify="right")
    table.add_column("Avg Daily Demand", justify="right")
    table.add_column("DOS", justify="right")

    for product in data['products'][:10]:  # Show first 10
        dos = product['on_hand'] / product['avg_daily_demand'] if product['avg_daily_demand'] > 0 else 0
        table.add_row(
            product['sku'],
            product['name'][:25],
            product['category'][:12],
            f"{product['on_hand']:,}",
            f"{product['in_transit']:,}",
            f"{product['avg_daily_demand']:.1f}",
            f"{dos:.1f} days"
        )

    if len(data['products']) > 10:
        table.add_row("...", f"+ {len(data['products']) - 10} more", "", "", "", "", "")

    console.print(table)

    # Display demand by segment
    console.print("\n[bold]Demand by Customer Segment (Weekly)[/bold]")
    for segment, demands in data['demand_by_segment'].items():
        total = sum(demands.values())
        console.print(f"  • {segment.title()}: {total:,.0f} units")

    return data


def demo_step_3_supply_candidates():
    """Demonstrate MPS candidate generation"""
    console.rule("[bold blue]Step 3: Supply Baseline Pack (SupBP) Candidates[/bold blue]")

    # In FULL mode, we generate 5 candidate methods
    methods = [
        ("REORDER_POINT", "Classic (r, Q) policy with safety stock buffer", 125000, 0.94),
        ("PERIODIC_REVIEW", "(R, S) policy with fixed review intervals", 118000, 0.95),
        ("MIN_COST_EOQ", "Economic Order Quantity minimizing total cost", 105000, 0.92),
        ("SERVICE_MAXIMIZED", "Maximize service level within budget", 142000, 0.98),
        ("PARAMETRIC_CFA", "Powell CFA with learned θ parameters", 115000, 0.96),
    ]

    table = Table(title="Candidate Supply Plans (Tradeoff Frontier)")
    table.add_column("Method", style="cyan")
    table.add_column("Description")
    table.add_column("Est. Cost", justify="right")
    table.add_column("Est. OTIF", justify="right")

    for method, desc, cost, otif in methods:
        table.add_row(
            method,
            desc[:45],
            f"${cost:,}",
            f"{otif:.0%}"
        )

    console.print(table)

    console.print(Panel(
        "[yellow]In INPUT mode:[/yellow] Customer uploads their existing MRP output\n"
        "[green]In FULL mode:[/green] System generates 5 candidates for tradeoff analysis",
        title="Mode Comparison"
    ))

    return methods


def demo_step_4_supply_agent():
    """Demonstrate Supply Agent decision-making"""
    console.rule("[bold blue]Step 4: Supply Agent → Supply Commit (SC)[/bold blue]")

    # Agent Reasoning Panel
    console.print(Panel(
        "[bold cyan]AGENT REASONING[/bold cyan]\n\n"
        "[bold]Decision Summary:[/bold]\n"
        "Selected PARAMETRIC_CFA method based on optimal cost-service tradeoff.\n"
        "This method uses learned θ parameters from CFA optimization.\n\n"
        "[bold]Key Factors:[/bold]\n"
        "• Cost optimization (weight: 0.4)\n"
        "• Service level constraints (weight: 0.35)\n"
        "• Lead time feasibility (weight: 0.25)\n\n"
        "[bold]Confidence Score:[/bold] 87%\n"
        "[dim]Based on data quality and model fit for current demand patterns[/dim]",
        title="🤖 Why Did The Agent Choose This?",
        border_style="cyan"
    ))

    # Simulated agent decision
    console.print(Panel(
        "[bold]Agent Analysis:[/bold]\n"
        "• Selected Method: PARAMETRIC_CFA (best cost/service balance)\n"
        "• Generated 47 purchase orders\n"
        "• Total Order Value: $115,000\n"
        "• Projected OTIF: 96%\n"
        "• Projected DOS: 18.5 days",
        title="Supply Commit Summary"
    ))

    # Integrity checks
    console.print("\n[bold]Integrity Checks (Blocking):[/bold]")
    console.print("  ✓ No negative inventory projections")
    console.print("  ✓ All orders within lead time feasibility")
    console.print("  ✓ All orders meet MOQ requirements")

    # Risk flags
    console.print("\n[bold]Risk Flags (Advisory):[/bold]")
    console.print("  ⚠ [yellow]SERVICE_RISK[/yellow]: FP003 (Pork Chops) projected OTIF 89% < 90% floor")
    console.print("  ⚠ [yellow]DOS_CEILING[/yellow]: DP002 (Rice) projected DOS 48 > 45 day ceiling")

    console.print(Panel(
        "[bold]Status:[/bold] PENDING_REVIEW\n"
        "[bold]Requires Review:[/bold] Yes (2 risk flags)",
        title="Supply Commit Status"
    ))

    # Human Adjustment Example
    console.print("\n")
    console.print(Panel(
        "[bold yellow]HUMAN REVIEW[/bold yellow]\n\n"
        "[bold]User Review Actions:[/bold]\n"
        "• [green]Accept[/green] - Use agent recommendation unchanged\n"
        "• [red]Override[/red] - Make any changes (adjustments to complete replacement)\n\n"
        "[bold]Example Override (with adjustments):[/bold]\n"
        "┌─────────────────────────────────────────────────────────────┐\n"
        "│ SKU      │ Agent Qty │ Your Adj │ Change  │ Rationale      │\n"
        "├─────────────────────────────────────────────────────────────┤\n"
        "│ FP003    │ 500       │ 600      │ +20%    │ Low ROP risk   │\n"
        "│ DP002    │ 300       │ 250      │ -17%    │ DOS ceiling    │\n"
        "│ BV001    │ 400       │ 400      │ —       │ (no change)    │\n"
        "└─────────────────────────────────────────────────────────────┘\n\n"
        "[dim]User's overrides are tracked and compared to agent baseline[/dim]\n"
        "[dim]for continuous learning and agent performance scoring[/dim]",
        title="👤 Human-in-the-Loop Override",
        border_style="yellow"
    ))


def demo_step_5_allocation_agent():
    """Demonstrate Allocation Agent decision-making"""
    console.rule("[bold blue]Step 5: Allocation Agent → Allocation Commit (AC)[/bold blue]")

    # Simulated allocation decision
    table = Table(title="Allocation by Customer Segment")
    table.add_column("Segment", style="cyan")
    table.add_column("Requested", justify="right")
    table.add_column("Allocated", justify="right")
    table.add_column("Fill Rate", justify="right")
    table.add_column("OTIF Floor", justify="right")
    table.add_column("Status")

    table.add_row("Strategic", "45,000", "44,800", "99.6%", "99%", "[green]✓[/green]")
    table.add_row("Standard", "75,000", "73,500", "98.0%", "95%", "[green]✓[/green]")
    table.add_row("Transactional", "30,000", "27,000", "90.0%", "90%", "[yellow]⚠[/yellow]")

    console.print(table)

    console.print("\n[bold]Allocation Method:[/bold] PRIORITY_HEURISTIC")
    console.print("[bold]Logic:[/bold] Strategic → Standard → Transactional (OTIF floors honored)")

    # Integrity checks
    console.print("\n[bold]Integrity Checks:[/bold]")
    console.print("  ✓ Supply conservation maintained (allocated ≤ available)")
    console.print("  ✓ All segment OTIF floors met")

    console.print(Panel(
        "[bold]Status:[/bold] APPROVED\n"
        "[bold]Ready for Execution:[/bold] Yes",
        title="Allocation Commit Status"
    ))


def demo_step_6_feed_back():
    """Demonstrate feed-back signals"""
    console.rule("[bold blue]Step 6: Feed-Back Signals (Execution → Re-tuning)[/bold blue]")

    table = Table(title="Feed-Back Signals from Last Execution Cycle")
    table.add_column("Signal Type", style="cyan")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_column("Threshold", justify="right")
    table.add_column("Fed Back To")

    table.add_row("ACTUAL_OTIF", "Strategic OTIF", "98.5%", "99%", "Supply Agent")
    table.add_row("EXPEDITE_FREQUENCY", "Frozen expedites/week", "3.2", "2.0", "S&OP")
    table.add_row("EO_WRITEOFF", "E&O write-off %", "0.8%", "1.0%", "S&OP")
    table.add_row("ALLOCATION_SHORTFALL", "Transactional shortfall", "4.2%", "5.0%", "Supply Agent")

    console.print(table)

    console.print(Panel(
        "[bold]Continuous Improvement Loop:[/bold]\n"
        "• Expedite frequency above target → Consider increasing safety stock for frozen\n"
        "• Strategic OTIF slightly below floor → Review allocation reserves",
        title="Re-tuning Recommendations"
    ))


def demo_cascade_flow():
    """Show the full cascade flow"""
    console.rule("[bold magenta]Planning Cascade Flow[/bold magenta]")

    tree = Tree("[bold]Planning Cascade[/bold]")

    sop = tree.add("📋 S&OP Policy Envelope (θ_SOP)")
    sop.add("[dim]Service tiers, safety stock targets, expedite caps[/dim]")

    mps = tree.add("📦 MPS / Supply Baseline Pack (SupBP)")
    mps.add("[dim]5 candidate methods with tradeoff frontier[/dim]")

    sc = tree.add("🚚 Supply Agent → Supply Commit (SC)")
    sc.add("[dim]PO recommendations with integrity/risk checks[/dim]")

    ac = tree.add("📊 Allocation Agent → Allocation Commit (AC)")
    ac.add("[dim]Segment allocations with priority sequencing[/dim]")

    exec_node = tree.add("⚡ Execution")
    exec_node.add("[dim]Feed-back signals for re-tuning[/dim]")

    console.print(tree)

    console.print("\n[bold]Feed-Forward Contracts:[/bold] Each layer produces hash-linked artifacts")
    console.print("[bold]Feed-Back Signals:[/bold] Execution outcomes re-tune upstream parameters")
    console.print("\n[bold]Dual-Mode Architecture:[/bold]")
    console.print("  • [yellow]INPUT mode:[/yellow] Customer provides S&OP params + MRP output")
    console.print("  • [green]FULL mode:[/green] Autonomy simulation optimizes all layers")


def main():
    global INTERACTIVE_MODE, STEP_DELAY

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Planning Cascade Demo")
    parser.add_argument("--no-pause", action="store_true",
                        help="Run without pauses (for video recording)")
    parser.add_argument("--delay", type=int, default=3,
                        help="Delay in seconds between steps (default: 3)")
    args = parser.parse_args()

    if args.no_pause:
        INTERACTIVE_MODE = False
        STEP_DELAY = args.delay
        console.print("[dim]Running in video recording mode (no pauses)...[/dim]\n")

    console.print(Panel.fit(
        "[bold magenta]Autonomy Supply Chain Platform[/bold magenta]\n"
        "[bold]Planning Cascade Demo - Food Dist Distributor[/bold]",
        border_style="magenta"
    ))

    # Show the cascade flow
    demo_cascade_flow()
    wait_for_next()

    # Step through the cascade
    demo_step_1_sop_policy()
    wait_for_next()

    demo_step_2_inventory_state()
    wait_for_next()

    demo_step_3_supply_candidates()
    wait_for_next()

    demo_step_4_supply_agent()
    wait_for_next()

    demo_step_5_allocation_agent()
    wait_for_next()

    demo_step_6_feed_back()

    console.print("\n")
    console.print(Panel.fit(
        "[bold green]Demo Complete![/bold green]\n\n"
        "To see the full implementation:\n"
        "• API: http://localhost:8000/docs → planning-cascade\n"
        "• Frontend: http://localhost:8088/planning/cascade-dashboard\n"
        "• Models: backend/app/models/planning_cascade.py\n"
        "• Services: backend/app/services/planning_cascade/",
        border_style="green"
    ))


if __name__ == "__main__":
    main()
