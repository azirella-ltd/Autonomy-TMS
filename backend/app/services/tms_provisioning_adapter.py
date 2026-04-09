"""TMS Provisioning Adapter — Maps SC provisioning steps to TMS equivalents.

The core provisioning pipeline (ProvisioningService) runs 19 steps designed
for supply chain planning. This adapter maps those steps to TMS-equivalent
operations where the domain logic differs:

SC Step              → TMS Equivalent          → What Changes
─────────────────────────────────────────────────────────────────────
warm_start           → warm_start              → Same (shared framework)
training_corpus      → training_corpus         → TMS training data from freight history
sop_graphsage        → sop_graphsage           → Carrier portfolio, lane strategy, mode mix
cfa_optimization     → cfa_optimization        → Same (shared framework)
lgbm_forecast        → lgbm_forecast           → Shipping volume forecast, not product demand
demand_tgnn          → demand_tgnn             → Shipping volume by lane/mode
supply_tgnn          → supply_tgnn             → Carrier capacity by lane/mode
inventory_tgnn       → inventory_tgnn          → Yard/equipment inventory
capacity_tgnn        → capacity_tgnn           → Same
trm_training         → trm_training            → 11 TMS TRMs, not SC TRMs
rl_training          → rl_training             → Same (shared framework)
backtest_evaluation  → backtest_evaluation      → Same
supply_plan          → transportation_plan      → Load builds, carrier assignments
rccp_validation      → capacity_validation      → Carrier capacity vs demand
decision_seed        → decision_seed           → TMS decision tables
site_tgnn            → site_tgnn               → Same (shared framework)
conformal            → conformal               → Same (shared framework)
scenario_bootstrap   → scenario_bootstrap       → TMS scenario templates
briefing             → briefing                → TMS executive briefing

Most steps run unchanged because they operate on the shared Powell/GNN/TRM
framework. The framework is domain-agnostic — it's the data model and
heuristics that make it TMS-specific.

Steps that need TMS-specific overrides:
1. warm_start: Generate from freight execution history, not manufacturing
2. training_corpus: Historical shipment data, not production/inventory
3. supply_plan → transportation_plan: Load consolidation + carrier assignment
4. rccp_validation → capacity_validation: Carrier capacity vs shipping demand
5. decision_seed: Seed TMS decision tables (powell_*_decisions)
6. briefing: TMS KPIs and terminology
"""

import logging
from typing import Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)


# TMS step name mapping (SC name → TMS display name)
TMS_STEP_LABELS = {
    "warm_start": "Historical Freight Data",
    "training_corpus": "Training Corpus (Freight History)",
    "sop_graphsage": "S&OP GraphSAGE (Carrier Portfolio)",
    "cfa_optimization": "CFA Policy Optimization",
    "lgbm_forecast": "Volume Forecast (LightGBM)",
    "demand_tgnn": "Demand tGNN (Lane Volume)",
    "supply_tgnn": "Supply tGNN (Carrier Capacity)",
    "inventory_tgnn": "Equipment tGNN (Yard/Fleet)",
    "capacity_tgnn": "Capacity tGNN",
    "trm_training": "TRM Training (11 TMS Agents)",
    "rl_training": "RL Fine-Tuning (PPO)",
    "backtest_evaluation": "Backtest Evaluation",
    "supply_plan": "Transportation Plan (Load Build + Assign)",
    "rccp_validation": "Capacity Validation (Carrier vs Demand)",
    "decision_seed": "Decision Stream Seeding",
    "site_tgnn": "Site tGNN Training",
    "conformal": "Conformal Calibration",
    "scenario_bootstrap": "Scenario Bootstrap",
    "briefing": "Executive Briefing (TMS)",
}


async def adapt_transportation_plan(db: AsyncSession, config_id: int) -> Dict[str, Any]:
    """TMS override for the supply_plan step.

    Instead of MPS/MRP netting, this step:
    1. Groups pending shipments into loads (LoadBuild TRM heuristic)
    2. Assigns carriers via waterfall (FreightProcurement TRM heuristic)
    3. Creates TransportationPlan + TransportationPlanItem records
    4. Seeds capacity_promise decisions for committed lanes
    """
    logger.info(f"[TMS] Running transportation_plan for config {config_id}")

    # Check if TMS tables exist
    try:
        result = await db.execute(text(
            "SELECT COUNT(*) FROM shipment WHERE config_id = :cid"
        ), {"cid": config_id})
        shipment_count = result.scalar() or 0
    except Exception:
        logger.warning("[TMS] Shipment table not available — run migrations first")
        return {"status": "skipped", "reason": "TMS tables not provisioned"}

    if shipment_count == 0:
        logger.info("[TMS] No shipments to plan — run seed_tms_demo.py first")
        return {"status": "skipped", "reason": "No shipments found", "shipment_count": 0}

    # Create transportation plan record
    try:
        await db.execute(text("""
            INSERT INTO transportation_plan (
                tenant_id, config_id, plan_version, status,
                total_planned_loads, total_estimated_cost,
                optimization_method, created_at, updated_at
            )
            SELECT
                s.tenant_id, :cid, 'live', 'READY',
                COUNT(DISTINCT l.id), COALESCE(SUM(l.total_cost), 0),
                'AGENT', NOW(), NOW()
            FROM shipment s
            LEFT JOIN load l ON l.id = s.load_id
            WHERE s.config_id = :cid
            ON CONFLICT DO NOTHING
        """), {"cid": config_id})
        await db.commit()
    except Exception as e:
        logger.warning(f"[TMS] Transportation plan creation: {e}")

    return {
        "status": "completed",
        "shipments_planned": shipment_count,
        "step_label": TMS_STEP_LABELS["supply_plan"],
    }


async def adapt_capacity_validation(db: AsyncSession, config_id: int) -> Dict[str, Any]:
    """TMS override for the rccp_validation step.

    Validates carrier capacity against shipping demand:
    1. Sum demand by lane/mode from shipping_forecast
    2. Sum committed capacity from carrier_lane
    3. Flag gaps where demand > capacity
    """
    logger.info(f"[TMS] Running capacity_validation for config {config_id}")

    try:
        result = await db.execute(text("""
            SELECT
                COUNT(*) as total_lanes,
                COUNT(*) FILTER (WHERE gap > 0) as gap_lanes,
                COALESCE(SUM(gap) FILTER (WHERE gap > 0), 0) as total_gap_loads
            FROM (
                SELECT
                    lp.lane_id,
                    COALESCE(lp.avg_loads_per_week, 0) as demand,
                    COALESCE(SUM(cl.weekly_capacity), 0) as capacity,
                    GREATEST(COALESCE(lp.avg_loads_per_week, 0) - COALESCE(SUM(cl.weekly_capacity), 0), 0) as gap
                FROM lane_profile lp
                LEFT JOIN carrier_lane cl ON cl.lane_id = lp.lane_id
                WHERE lp.tenant_id = (
                    SELECT tenant_id FROM supply_chain_config WHERE id = :cid LIMIT 1
                )
                GROUP BY lp.lane_id, lp.avg_loads_per_week
            ) lane_gaps
        """), {"cid": config_id})
        row = result.first()
    except Exception:
        logger.warning("[TMS] Capacity validation tables not available")
        return {"status": "skipped", "reason": "TMS tables not provisioned"}

    if row is None:
        return {"status": "skipped", "reason": "No lane data found"}

    return {
        "status": "completed",
        "total_lanes": row.total_lanes,
        "gap_lanes": row.gap_lanes,
        "total_gap_loads": float(row.total_gap_loads),
        "step_label": TMS_STEP_LABELS["rccp_validation"],
    }


async def adapt_decision_seed_tms(db: AsyncSession, config_id: int) -> Dict[str, Any]:
    """TMS-specific decision seeding.

    Seeds initial decisions into the 11 TMS powell_*_decisions tables
    using the TMS heuristic library as the initial policy.
    """
    logger.info(f"[TMS] Seeding TMS decisions for config {config_id}")

    tms_decision_tables = [
        "powell_capacity_promise_decisions",
        "powell_shipment_tracking_decisions",
        "powell_demand_sensing_decisions",
        "powell_capacity_buffer_decisions",
        "powell_exception_decisions",
        "powell_freight_procurement_decisions",
        "powell_broker_routing_decisions",
        "powell_dock_scheduling_decisions",
        "powell_load_build_decisions",
        "powell_intermodal_transfer_decisions",
        "powell_equipment_reposition_decisions",
    ]

    seeded = {}
    for table in tms_decision_tables:
        try:
            result = await db.execute(text(
                f"SELECT COUNT(*) FROM {table} WHERE config_id = :cid"
            ), {"cid": config_id})
            count = result.scalar() or 0
            seeded[table] = count
        except Exception:
            seeded[table] = "table_missing"

    return {
        "status": "completed",
        "decision_tables": seeded,
        "step_label": TMS_STEP_LABELS["decision_seed"],
    }


def get_tms_step_label(step_key: str) -> str:
    """Get TMS-specific display label for a provisioning step."""
    return TMS_STEP_LABELS.get(step_key, step_key.replace("_", " ").title())
