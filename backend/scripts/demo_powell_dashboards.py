#!/usr/bin/env python3
"""
Powell Framework Dashboard Demo Script

Demonstrates the Powell Framework role-based dashboards:
- Executive Dashboard (SC_VP) - Strategic performance metrics
- S&OP Worklist (SOP_DIRECTOR) - Tactical worklist with Ask Why
- Agent Performance - Detailed agent performance analysis

Prerequisites:
    docker compose exec backend python scripts/seed_us_foods_demo.py

Demo User:
    Email: demo@distdemo.com
    Password: Autonomy@2026
    Access: All Powell dashboards (no login/logout needed!)

Run:
    cd backend
    python scripts/demo_powell_dashboards.py

Options:
    --no-pause      Run without pauses (for video recording)
    --delay N       Delay N seconds between steps (default: 3)
    --seed          Seed demo data before running
"""

import sys
import os
import argparse
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.tree import Tree
from rich import print as rprint

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


def demo_overview():
    """Show Powell Framework overview."""
    console.rule("[bold magenta]Powell Framework - AI-as-Labor Dashboard Demo[/bold magenta]")

    tree = Tree("[bold]Powell Framework Role Hierarchy[/bold]")

    sc_vp = tree.add("[cyan]SC_VP (VP Supply Chain)[/cyan] - Strategic/CFA Level")
    sc_vp.add("[dim]Landing: Executive Dashboard[/dim]")
    sc_vp.add("[dim]Focus: Agent performance, human overrides, ROI, category automation[/dim]")
    sc_vp.add("[dim]Capability: view_executive_dashboard[/dim]")

    sop_dir = tree.add("[yellow]SOP_DIRECTOR (S&OP Director)[/yellow] - Tactical/S&OP Level")
    sop_dir.add("[dim]Landing: S&OP Worklist[/dim]")
    sop_dir.add("[dim]Focus: Worklist items, agent recommendations, Ask Why[/dim]")
    sop_dir.add("[dim]Capability: view_sop_worklist[/dim]")

    mps_mgr = tree.add("[green]MPS_MANAGER (MPS Manager)[/green] - Operational/TRM Level")
    mps_mgr.add("[dim]Landing: Agent Decisions (/insights/actions)[/dim]")
    mps_mgr.add("[dim]Focus: Execution items, agent decision monitoring[/dim]")
    mps_mgr.add("[dim]Capability: view_agent_decisions[/dim]")

    demo = tree.add("[bold magenta]DEMO USER[/bold magenta] - All Levels Combined")
    demo.add("[dim]Email: demo@distdemo.com[/dim]")
    demo.add("[dim]Access: All Powell dashboards (no login/logout!)[/dim]")

    console.print(tree)

    console.print(Panel(
        "[bold]Demo User Advantage:[/bold]\n"
        "Single login grants access to all Powell dashboards.\n"
        "Switch views via navigation - no logout needed!",
        title="Demo Setup",
        border_style="magenta"
    ))


def demo_executive_dashboard():
    """Demonstrate Executive Dashboard."""
    console.rule("[bold cyan]Executive Dashboard (SC_VP Landing)[/bold cyan]")

    console.print(Panel(
        "[bold]URL:[/bold] /executive-dashboard\n"
        "[bold]Capability:[/bold] view_executive_dashboard\n"
        "[bold]Persona:[/bold] VP Supply Chain (Strategic Level)",
        title="Page Info"
    ))

    # KPI Cards
    console.print("\n[bold]Key Performance Indicators (KPIs)[/bold]")

    table = Table(title="Executive KPI Cards")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    table.add_column("Description")

    table.add_row("Agent Score", "+42", "Agent Performance Score (-100 to +100)")
    table.add_row("Override Rate", "22%", "Human Override Rate (% decisions overridden)")
    table.add_row("Touchless Rate", "65%", "% decisions executed without human intervention")
    table.add_row("Automation", "78%", "Automation adoption rate")

    console.print(table)

    # Agent explanation
    console.print(Panel(
        "[bold cyan]What These Metrics Mean:[/bold cyan]\n\n"
        "[bold]Agent Performance Score:[/bold]\n"
        "  • Scale: -100 to +100\n"
        "  • Positive = Agent decisions better than baseline\n"
        "  • Measures: cost savings, service level improvement\n\n"
        "[bold]Human Override Rate:[/bold]\n"
        "  • Scale: 0-100%\n"
        "  • Lower = More trust in AI (fewer overrides)\n"
        "  • Target: <20% for mature AI adoption\n\n"
        "[bold]Touchless Rate:[/bold]\n"
        "  • % of decisions that execute without ANY human touch\n"
        "  • The holy grail of AI-as-Labor automation",
        title="Metric Definitions",
        border_style="cyan"
    ))


def demo_sop_worklist():
    """Demonstrate S&OP Worklist."""
    console.rule("[bold yellow]S&OP Worklist (SOP_DIRECTOR Landing)[/bold yellow]")

    console.print(Panel(
        "[bold]URL:[/bold] /sop-worklist\n"
        "[bold]Capability:[/bold] view_sop_worklist\n"
        "[bold]Persona:[/bold] S&OP Director (Tactical Level)",
        title="Page Info"
    ))

    # Worklist items
    console.print("\n[bold]Worklist Items (Exception Triage)[/bold]")

    table = Table(title="S&OP Worklist")
    table.add_column("ID", style="dim")
    table.add_column("Type", style="cyan")
    table.add_column("Product/Site")
    table.add_column("Agent Rec.", justify="right")
    table.add_column("Confidence", justify="right")
    table.add_column("Status")

    table.add_row("WL-001", "Safety Stock", "Frozen Proteins / DC-Chicago", "2.5 weeks", "87%", "[yellow]Pending[/yellow]")
    table.add_row("WL-002", "Expedite", "Pork Chops / DC-Indianapolis", "Rush Order", "92%", "[yellow]Pending[/yellow]")
    table.add_row("WL-003", "Allocation", "Strategic Segment", "+15% reserve", "78%", "[yellow]Pending[/yellow]")
    table.add_row("WL-004", "DOS Ceiling", "Rice / DC-Chicago", "Reduce order", "85%", "[green]Accepted[/green]")
    table.add_row("WL-005", "OTIF Alert", "Dairy / Regional", "Increase buffer", "81%", "[red]Rejected[/red]")

    console.print(table)

    # Ask Why panel
    console.print("\n")
    console.print(Panel(
        "[bold cyan]ASK WHY - Agent Reasoning[/bold cyan]\n\n"
        "[bold]User clicks 'Ask Why' on WL-001 (Safety Stock)...[/bold]\n\n"
        "┌─────────────────────────────────────────────────────────────────┐\n"
        "│ 🤖 AGENT REASONING                                              │\n"
        "├─────────────────────────────────────────────────────────────────┤\n"
        "│                                                                  │\n"
        "│ [bold]Recommendation:[/bold] Increase safety stock to 2.5 weeks          │\n"
        "│                                                                  │\n"
        "│ [bold]Evidence:[/bold]                                                    │\n"
        "│ • Order #ORD-2847: Stockout on Feb 3 (lost $4,200)             │\n"
        "│ • Demand variance increased 23% over past 4 weeks              │\n"
        "│ • Lead time from supplier extended by 2 days                   │\n"
        "│                                                                  │\n"
        "│ [bold]Confidence:[/bold] 87%                                              │\n"
        "│ [dim]Based on 12 months historical data, current forecast[/dim]        │\n"
        "│                                                                  │\n"
        "│ [bold]Expected Impact:[/bold]                                             │\n"
        "│ • OTIF improvement: +3.2%                                       │\n"
        "│ • Inventory cost: +$12,400/month                               │\n"
        "│ • ROI payback: 2.1 months                                      │\n"
        "└─────────────────────────────────────────────────────────────────┘",
        title="Ask Why Modal",
        border_style="cyan"
    ))

    # Human override panel
    console.print("\n")
    console.print(Panel(
        "[bold yellow]HUMAN OVERRIDE CAPTURE[/bold yellow]\n\n"
        "[bold]User clicks 'Reject' on WL-001...[/bold]\n\n"
        "┌─────────────────────────────────────────────────────────────────┐\n"
        "│ 📝 OVERRIDE REASON (Required)                                   │\n"
        "├─────────────────────────────────────────────────────────────────┤\n"
        "│                                                                  │\n"
        "│ [Select reason or type custom]:                                 │\n"
        "│ ○ Disagree with analysis                                        │\n"
        "│ ○ Budget constraints                                            │\n"
        "│ ○ Known upcoming changes                                        │\n"
        "│ ● [x] Custom: ________________________________                   │\n"
        "│                                                                  │\n"
        "│ [dim]\"We're transitioning to new supplier next month with[/dim]        │\n"
        "│ [dim]shorter lead times. Wait until cutover.\"[/dim]                    │\n"
        "│                                                                  │\n"
        "│               [Cancel]              [Submit Override]           │\n"
        "└─────────────────────────────────────────────────────────────────┘\n\n"
        "[dim]Override reasons feed back into performance calculations and[/dim]\n"
        "[dim]become training data for agent improvement (RLHF-style).[/dim]",
        title="Override Capture",
        border_style="yellow"
    ))


def demo_agent_performance():
    """Demonstrate Agent Performance page."""
    console.rule("[bold green]Agent Performance Analysis[/bold green]")

    console.print(Panel(
        "[bold]URL:[/bold] /agent-performance\n"
        "[bold]Capability:[/bold] view_executive_dashboard\n"
        "[bold]Purpose:[/bold] Detailed analysis of AI vs Human decisions",
        title="Page Info"
    ))

    # Decision breakdown
    console.print("\n[bold]Performance Breakdown by Category[/bold]")

    table = Table(title="Agent Performance by Decision Type")
    table.add_column("Decision Type", style="cyan")
    table.add_column("Agent Score", justify="right")
    table.add_column("Human Score", justify="right")
    table.add_column("Override Rate", justify="right")
    table.add_column("Trend")

    table.add_row("Safety Stock", "+48", "+35", "18%", "[green]↑ Improving[/green]")
    table.add_row("Order Quantity", "+52", "+41", "15%", "[green]↑ Improving[/green]")
    table.add_row("Expedite Decisions", "+28", "+45", "42%", "[yellow]→ Stable[/yellow]")
    table.add_row("Allocation", "+55", "+38", "12%", "[green]↑ Improving[/green]")
    table.add_row("Rebalancing", "+31", "+29", "35%", "[red]↓ Needs work[/red]")

    console.print(table)

    console.print(Panel(
        "[bold]Key Insights:[/bold]\n\n"
        "• Agent outperforms human on Safety Stock (+13 points)\n"
        "• Expedite decisions: Human expertise still valuable (+17 points)\n"
        "• Allocation showing strong AI adoption (only 12% overrides)\n"
        "• Rebalancing TRM needs additional training data\n\n"
        "[bold]Recommended Actions:[/bold]\n"
        "• Increase agent autonomy for Allocation decisions\n"
        "• Keep human-in-loop for Expedite until Q2\n"
        "• Prioritize Rebalancing TRM training",
        title="Performance Insights",
        border_style="green"
    ))


def demo_navigation_flow():
    """Show navigation flow for demo user."""
    console.rule("[bold magenta]Demo Navigation Flow[/bold magenta]")

    console.print(Panel(
        "[bold]RECOMMENDED DEMO FLOW[/bold]\n\n"
        "1. Login as demo@distdemo.com (password: Autonomy@2026)\n"
        "   → Lands on Executive Dashboard (SC_VP view)\n\n"
        "2. Show Executive Dashboard\n"
        "   → KPI cards: Agent Score, Override Rate, Touchless Rate\n"
        "   → Explain AI-as-Labor metrics\n\n"
        "3. Navigate to S&OP Worklist (via nav menu)\n"
        "   → Show worklist items pending review\n"
        "   → Click 'Ask Why' on an item\n"
        "   → Show agent reasoning with evidence\n\n"
        "4. Demonstrate Override Flow\n"
        "   → Click 'Reject' on an item\n"
        "   → Show override reason capture\n"
        "   → Explain feedback loop to AI training\n\n"
        "5. Navigate to Agent Performance\n"
        "   → Show performance breakdown by category\n"
        "   → Compare Agent vs Human performance\n"
        "   → Identify areas for AI improvement\n\n"
        "[bold]Total Demo Time:[/bold] 5-7 minutes",
        title="Demo Script",
        border_style="magenta"
    ))


def main():
    global INTERACTIVE_MODE, STEP_DELAY

    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Powell Framework Dashboard Demo")
    parser.add_argument("--no-pause", action="store_true",
                        help="Run without pauses (for video recording)")
    parser.add_argument("--delay", type=int, default=3,
                        help="Delay in seconds between steps (default: 3)")
    parser.add_argument("--seed", action="store_true",
                        help="Seed demo data before running")
    args = parser.parse_args()

    if args.no_pause:
        INTERACTIVE_MODE = False
        STEP_DELAY = args.delay
        console.print("[dim]Running in video recording mode (no pauses)...[/dim]\n")

    # Seed demo data if requested
    if args.seed:
        console.print("[bold]Seeding demo data...[/bold]")
        import subprocess
        result = subprocess.run(
            ["python", "scripts/seed_us_foods_demo.py"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        if result.returncode != 0:
            console.print("[red]Failed to seed demo data[/red]")
            return
        console.print("[green]Demo data seeded successfully[/green]\n")

    console.print(Panel.fit(
        "[bold magenta]Autonomy Supply Chain Platform[/bold magenta]\n"
        "[bold]Powell Framework Dashboard Demo - Food Dist[/bold]",
        border_style="magenta"
    ))

    # Step through the demo
    demo_overview()
    wait_for_next()

    demo_executive_dashboard()
    wait_for_next()

    demo_sop_worklist()
    wait_for_next()

    demo_agent_performance()
    wait_for_next()

    demo_navigation_flow()

    console.print("\n")
    console.print(Panel.fit(
        "[bold green]Demo Complete![/bold green]\n\n"
        "[bold]To run the actual UI demo:[/bold]\n"
        "1. Start the stack: make up\n"
        "2. Seed demo data: docker compose exec backend python scripts/seed_us_foods_demo.py\n"
        "3. Open: http://localhost:8088\n"
        "4. Login: demo@distdemo.com / Autonomy@2026\n"
        "5. Navigate: Executive Dashboard → S&OP Worklist → Agent Performance\n\n"
        "[bold]Demo Users:[/bold]\n"
        "• demo@distdemo.com - All access (recommended)\n"
        "• scvp@distdemo.com - SC_VP only\n"
        "• sopdir@distdemo.com - SOP_DIRECTOR only\n"
        "• mpsmanager@distdemo.com - MPS_MANAGER only",
        border_style="green"
    ))


if __name__ == "__main__":
    main()
