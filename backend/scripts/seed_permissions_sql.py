#!/usr/bin/env python3
"""
Seed RBAC Permissions using Raw SQL

This script directly inserts permissions into the database using raw SQL
to avoid model relationship issues.
"""

import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from app.db.session import sync_engine


# All 60 permissions (59 + manage_groups which was missing)
PERMISSIONS = [
    # Strategic Planning (10)
    ("view_sop", "sop", "view", "View Sales & Operations Planning", "Strategic Planning"),
    ("manage_sop", "sop", "manage", "Configure S&OP plans and cycles", "Strategic Planning"),
    ("view_network_design", "network_design", "view", "View supply chain network", "Strategic Planning"),
    ("manage_network_design", "network_design", "manage", "Create/edit network configurations", "Strategic Planning"),
    ("view_demand_forecasting", "demand_forecasting", "view", "View demand forecasts", "Strategic Planning"),
    ("manage_demand_forecasting", "demand_forecasting", "manage", "Create/edit forecasts", "Strategic Planning"),
    ("view_inventory_optimization", "inventory_optimization", "view", "View inventory policies", "Tactical Planning"),
    ("manage_inventory_optimization", "inventory_optimization", "manage", "Configure inventory policies", "Tactical Planning"),
    ("view_stochastic_planning", "stochastic_planning", "view", "View probabilistic scenarios", "Strategic Planning"),
    ("manage_stochastic_planning", "stochastic_planning", "manage", "Configure stochastic parameters", "Strategic Planning"),

    # Tactical Planning (9)
    ("view_mps", "mps", "view", "View Master Production Schedule", "Tactical Planning"),
    ("manage_mps", "mps", "manage", "Create/edit MPS plans", "Tactical Planning"),
    ("approve_mps", "mps", "approve", "Approve MPS plans", "Tactical Planning"),
    ("view_lot_sizing", "lot_sizing", "view", "View lot sizing analysis", "Tactical Planning"),
    ("manage_lot_sizing", "lot_sizing", "manage", "Configure lot sizing parameters", "Tactical Planning"),
    ("view_capacity_check", "capacity_check", "view", "View capacity utilization", "Tactical Planning"),
    ("manage_capacity_check", "capacity_check", "manage", "Configure capacity parameters", "Tactical Planning"),
    ("view_mrp", "mrp", "view", "View Material Requirements Planning", "Tactical Planning"),
    ("manage_mrp", "mrp", "manage", "Run MRP and manage exceptions", "Tactical Planning"),

    # Operational Planning (9)
    ("view_supply_plan", "supply_plan", "view", "View generated supply plans", "Operational Planning"),
    ("manage_supply_plan", "supply_plan", "manage", "Generate and edit supply plans", "Operational Planning"),
    ("approve_supply_plan", "supply_plan", "approve", "Approve supply plans", "Operational Planning"),
    ("view_atp_ctp", "atp_ctp", "view", "View ATP/CTP", "Operational Planning"),
    ("manage_atp_ctp", "atp_ctp", "manage", "Configure ATP/CTP parameters", "Operational Planning"),
    ("view_sourcing_allocation", "sourcing_allocation", "view", "View sourcing rules", "Operational Planning"),
    ("manage_sourcing_allocation", "sourcing_allocation", "manage", "Configure sourcing rules", "Operational Planning"),
    ("view_order_planning", "order_planning", "view", "View planned orders", "Operational Planning"),
    ("manage_order_planning", "order_planning", "manage", "Create/edit planned orders", "Operational Planning"),

    # Execution & Monitoring (8)
    ("view_order_management", "order_management", "view", "View purchase/transfer orders", "Execution"),
    ("manage_order_management", "order_management", "manage", "Create/edit orders", "Execution"),
    ("approve_orders", "order_management", "approve", "Approve orders for release", "Execution"),
    ("view_shipment_tracking", "shipment_tracking", "view", "Track shipments", "Execution"),
    ("manage_shipment_tracking", "shipment_tracking", "manage", "Update shipment status", "Execution"),
    ("view_inventory_visibility", "inventory_visibility", "view", "View inventory levels", "Execution"),
    ("manage_inventory_visibility", "inventory_visibility", "manage", "Adjust inventory levels", "Execution"),
    ("view_ntier_visibility", "ntier_visibility", "view", "View multi-tier visibility", "Execution"),

    # Analytics & Insights (7)
    ("view_analytics", "analytics", "view", "View analytics dashboards", "Analytics"),
    ("view_kpi_monitoring", "kpi_monitoring", "view", "View KPI dashboards", "Analytics"),
    ("manage_kpi_monitoring", "kpi_monitoring", "manage", "Configure KPI thresholds", "Analytics"),
    ("view_scenario_comparison", "scenario_comparison", "view", "View scenario analysis", "Analytics"),
    ("manage_scenario_comparison", "scenario_comparison", "manage", "Create/run scenarios", "Analytics"),
    ("view_risk_analysis", "risk_analysis", "view", "View risk analysis", "Analytics"),
    ("manage_risk_analysis", "risk_analysis", "manage", "Configure risk parameters", "Analytics"),

    # AI & Agents (8)
    ("view_ai_agents", "ai_agents", "view", "View AI agent configurations", "AI & Agents"),
    ("manage_ai_agents", "ai_agents", "manage", "Configure/deploy AI agents", "AI & Agents"),
    ("view_trm_training", "trm_training", "view", "View TRM training status", "AI & Agents"),
    ("manage_trm_training", "trm_training", "manage", "Train/manage TRM models", "AI & Agents"),
    ("view_gnn_training", "gnn_training", "view", "View GNN training status", "AI & Agents"),
    ("manage_gnn_training", "gnn_training", "manage", "Train/manage GNN models", "AI & Agents"),
    ("view_llm_agents", "llm_agents", "view", "View LLM agent performance", "AI & Agents"),
    ("manage_llm_agents", "llm_agents", "manage", "Configure LLM agents", "AI & Agents"),

    # Simulation (5)
    ("view_simulations", "simulations", "view", "View simulation sessions", "Simulation"),
    ("create_simulation", "simulations", "create", "Create new simulation sessions", "Simulation"),
    ("play_simulation", "simulations", "play", "Participate in simulations", "Simulation"),
    ("manage_simulations", "simulations", "manage", "Administer simulation sessions", "Simulation"),
    ("view_scenario_analytics", "game_analytics", "view", "View simulation performance metrics", "Simulation"),

    # Administration (6)
    ("view_users", "users", "view", "View user list", "Administration"),
    ("create_user", "users", "create", "Create new users", "Administration"),
    ("edit_user", "users", "edit", "Edit user details", "Administration"),
    ("manage_permissions", "permissions", "manage", "Assign user capabilities", "Administration"),
    ("view_tenants", "tenants", "view", "View organization information", "Administration"),
    ("manage_tenants", "tenants", "manage", "Manage organization settings", "Administration"),
]


def main():
    """Seed permissions using raw SQL."""
    print("=" * 60)
    print("Seeding RBAC Permissions (SQL)")
    print("=" * 60)

    # Create session
    SyncSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=sync_engine
    )

    db = SyncSessionLocal()

    try:
        print(f"\n📦 Seeding {len(PERMISSIONS)} permissions...")

        inserted = 0
        skipped = 0

        for name, resource, action, description, category in PERMISSIONS:
            # Check if permission already exists
            result = db.execute(
                text("SELECT id FROM permissions WHERE name = :name"),
                {"name": name}
            ).first()

            if result:
                skipped += 1
                continue

            # Insert permission
            db.execute(
                text("""
                    INSERT INTO permissions (name, resource, action, description, category, is_system, created_at)
                    VALUES (:name, :resource, :action, :description, :category, :is_system, NOW())
                """),
                {
                    "name": name,
                    "resource": resource,
                    "action": action,
                    "description": description,
                    "category": category,
                    "is_system": True
                }
            )
            inserted += 1

        db.commit()
        print(f"✅ Successfully inserted {inserted} new permissions")
        if skipped > 0:
            print(f"ℹ️  Skipped {skipped} existing permissions")

        # Print summary by category
        result = db.execute(
            text("""
                SELECT category, COUNT(*) as count
                FROM permissions
                GROUP BY category
                ORDER BY category
            """)
        )

        print("\n📋 Permissions by category:")
        total = 0
        for row in result:
            print(f"  • {row[0]}: {row[1]} permissions")
            total += row[1]

        print(f"\n📊 Total permissions in database: {total}")

    except Exception as e:
        print(f"\n❌ Error seeding permissions: {e}")
        db.rollback()
        raise
    finally:
        db.close()

    print("\n" + "=" * 60)
    print("Permission seeding complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
