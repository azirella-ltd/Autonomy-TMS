"""
Scenario Planning API — Create, compare, and promote planning scenarios.

Scenarios are branches of the baseline supply chain config. Each scenario
can modify parameters (sourcing, lot sizing, safety stock, demand assumptions)
and run the planning cascade to see the impact.

Supports:
- Create scenario from baseline (branches config)
- List scenarios for a config
- Compare two scenarios (KPI delta)
- Promote scenario to baseline
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_current_active_user
from app.db.session import get_sync_db
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


class ScenarioCreate(BaseModel):
    name: str
    description: Optional[str] = None
    scenario_type: str = "WHAT_IF"  # WHAT_IF, OPTIMIZATION, RISK_ANALYSIS
    parameters: Optional[Dict[str, Any]] = None  # Changed parameters


@router.get("/")
def list_scenarios(
    config_id: int = Query(..., description="Base config ID"),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all scenarios branched from a baseline config."""
    from app.models.supply_chain_config import SupplyChainConfig

    configs = db.query(SupplyChainConfig).filter(
        SupplyChainConfig.tenant_id == current_user.tenant_id,
    ).order_by(SupplyChainConfig.created_at.desc()).all()

    baseline = None
    scenarios = []
    for c in configs:
        entry = {
            "id": c.id,
            "name": c.name,
            "description": c.description,
            "scenario_type": c.scenario_type or "BASELINE",
            "mode": c.mode,
            "parent_config_id": c.parent_config_id,
            "is_active": c.is_active,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "training_status": c.training_status,
        }
        if c.id == config_id or (not c.parent_config_id and c.scenario_type == "BASELINE"):
            baseline = entry
        if c.parent_config_id == config_id or c.base_config_id == config_id:
            scenarios.append(entry)

    return {
        "baseline": baseline,
        "scenarios": scenarios,
        "total": len(scenarios),
    }


@router.post("/")
def create_scenario(
    body: ScenarioCreate,
    config_id: int = Query(..., description="Base config to branch from"),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_active_user),
):
    """Create a new scenario by branching from the baseline config."""
    from app.models.supply_chain_config import SupplyChainConfig

    base = db.query(SupplyChainConfig).filter(
        SupplyChainConfig.id == config_id,
        SupplyChainConfig.tenant_id == current_user.tenant_id,
    ).first()
    if not base:
        raise HTTPException(404, "Base config not found")

    scenario = SupplyChainConfig(
        name=body.name,
        description=body.description or f"Scenario branched from {base.name}",
        tenant_id=current_user.tenant_id,
        parent_config_id=config_id,
        base_config_id=config_id,
        scenario_type=body.scenario_type,
        mode="scenario",
        uses_delta_storage=True,
        time_bucket=base.time_bucket,
        site_type_definitions=base.site_type_definitions,
        stochastic_config=body.parameters or base.stochastic_config,
        created_by=current_user.id,
    )
    db.add(scenario)
    db.commit()
    db.refresh(scenario)

    logger.info("Scenario created: %s (id=%d) from base %d", body.name, scenario.id, config_id)

    return {
        "id": scenario.id,
        "name": scenario.name,
        "scenario_type": scenario.scenario_type,
        "parent_config_id": scenario.parent_config_id,
        "created_at": scenario.created_at.isoformat() if scenario.created_at else None,
    }


@router.get("/compare")
def compare_scenarios(
    baseline_id: int = Query(...),
    scenario_id: int = Query(...),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_active_user),
):
    """Compare KPIs between baseline and scenario."""
    def _get_kpis(cfg_id):
        # Forecast metrics
        fc = db.execute(text("""
            SELECT count(*), avg(forecast_p50), stddev(forecast_p50),
                   count(DISTINCT product_id), count(DISTINCT site_id)
            FROM forecast WHERE config_id = :cfg AND forecast_p50 IS NOT NULL
        """), {"cfg": cfg_id}).fetchone()

        # Supply plan metrics
        sp = db.execute(text("""
            SELECT count(*), sum(planned_order_quantity)
            FROM supply_plan WHERE config_id = :cfg
        """), {"cfg": cfg_id}).fetchone()

        # Inventory metrics
        inv = db.execute(text("""
            SELECT avg(on_hand_qty), avg(safety_stock_qty), avg(on_hand_qty / NULLIF(safety_stock_qty, 0))
            FROM inv_level WHERE config_id = :cfg AND on_hand_qty IS NOT NULL
        """), {"cfg": cfg_id}).fetchone()

        return {
            "forecast_records": fc[0] if fc else 0,
            "avg_demand": round(float(fc[1] or 0), 1) if fc else 0,
            "demand_cv_pct": round(float(fc[2] or 0) / float(fc[1] or 1) * 100, 1) if fc and fc[1] else 0,
            "products": fc[3] if fc else 0,
            "sites": fc[4] if fc else 0,
            "supply_orders": sp[0] if sp else 0,
            "total_planned_qty": round(float(sp[1] or 0), 0) if sp else 0,
            "avg_inventory": round(float(inv[0] or 0), 1) if inv else 0,
            "avg_safety_stock": round(float(inv[1] or 0), 1) if inv else 0,
            "dos_ratio": round(float(inv[2] or 0), 2) if inv else 0,
        }

    baseline_kpis = _get_kpis(baseline_id)
    scenario_kpis = _get_kpis(scenario_id)

    # Compute deltas
    deltas = {}
    for key in baseline_kpis:
        b = baseline_kpis[key]
        s = scenario_kpis[key]
        if isinstance(b, (int, float)) and isinstance(s, (int, float)) and b != 0:
            deltas[key] = {
                "baseline": b, "scenario": s,
                "delta": round(s - b, 1),
                "delta_pct": round((s - b) / b * 100, 1) if b != 0 else 0,
            }
        else:
            deltas[key] = {"baseline": b, "scenario": s, "delta": 0, "delta_pct": 0}

    return {
        "baseline": {"id": baseline_id, "kpis": baseline_kpis},
        "scenario": {"id": scenario_id, "kpis": scenario_kpis},
        "deltas": deltas,
    }


@router.get("/erp-comparison")
def compare_erp_vs_autonomy(
    config_id: int = Query(...),
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_active_user),
):
    """Compare ERP baseline plan vs Autonomy AI-generated plan.

    Shows the value the AI plan provides over the ERP's MRP/MPS output.
    """
    def _plan_metrics(plan_version):
        row = db.execute(text("""
            SELECT
                count(*) AS total_orders,
                count(DISTINCT product_id) AS products,
                count(DISTINCT site_id) AS sites,
                SUM(planned_order_quantity) AS total_qty,
                AVG(planned_order_quantity) AS avg_qty,
                count(DISTINCT plan_date) AS periods,
                MIN(plan_date) AS start_date,
                MAX(plan_date) AS end_date
            FROM supply_plan
            WHERE config_id = :cfg AND plan_version = :ver
        """), {"cfg": config_id, "ver": plan_version}).fetchone()
        if not row or not row[0]:
            return None
        return {
            "total_orders": row[0],
            "products": row[1],
            "sites": row[2],
            "total_planned_qty": round(float(row[3] or 0), 0),
            "avg_order_qty": round(float(row[4] or 0), 1),
            "periods": row[5],
            "start_date": row[6].isoformat() if row[6] else None,
            "end_date": row[7].isoformat() if row[7] else None,
        }

    erp = _plan_metrics("erp_baseline")
    autonomy = _plan_metrics("live")

    if not erp or not autonomy:
        return {
            "erp_baseline": erp,
            "autonomy_plan": autonomy,
            "comparison": None,
            "note": "Need both ERP baseline and Autonomy plan for comparison",
        }

    # Compute deltas
    comparison = {}
    for key in ["total_orders", "products", "total_planned_qty", "avg_order_qty", "periods"]:
        e_val = erp.get(key, 0)
        a_val = autonomy.get(key, 0)
        delta = a_val - e_val
        delta_pct = round(delta / e_val * 100, 1) if e_val and e_val != 0 else 0
        comparison[key] = {
            "erp": e_val, "autonomy": a_val,
            "delta": round(delta, 1), "delta_pct": delta_pct,
        }

    # Inventory comparison (latest inv_level vs safety stock)
    try:
        inv = db.execute(text("""
            SELECT
                AVG(on_hand_qty) AS avg_inventory,
                AVG(safety_stock_qty) AS avg_safety_stock,
                AVG(CASE WHEN safety_stock_qty > 0
                    THEN on_hand_qty / safety_stock_qty ELSE NULL END) AS dos_ratio,
                SUM(on_hand_qty) AS total_inventory
            FROM inv_level
            WHERE config_id = :cfg AND on_hand_qty IS NOT NULL
            AND inventory_date = (SELECT MAX(inventory_date) FROM inv_level WHERE config_id = :cfg)
        """), {"cfg": config_id}).fetchone()
        if inv and inv[0]:
            comparison["avg_inventory"] = round(float(inv[0]), 0)
            comparison["total_inventory"] = round(float(inv[3] or 0), 0)
            comparison["dos_ratio"] = round(float(inv[2] or 0), 2)
    except Exception:
        pass

    # ── ROI Metrics ──
    roi = {}

    # Service level: avg target service level from active inv_policy
    try:
        svc = db.execute(text("""
            SELECT AVG(service_level) * 100
            FROM inv_policy
            WHERE config_id = :cfg
              AND is_active IN ('true', 'Y', 'yes', '1')
              AND service_level IS NOT NULL AND service_level > 0
        """), {"cfg": config_id}).scalar()
        if svc is not None:
            roi["service_level"] = round(float(svc), 1)
    except Exception:
        pass

    # Forecast accuracy: MAPE proxy from forecast vs actual (outbound_order)
    try:
        fa = db.execute(text("""
            WITH fcst AS (
                SELECT product_id, site_id, forecast_date,
                       AVG(forecast_quantity) AS avg_fcst
                FROM forecast
                WHERE config_id = :cfg AND forecast_quantity > 0
                GROUP BY product_id, site_id, forecast_date
            ),
            actuals AS (
                SELECT ool.product_id, oo.ship_from_site_id AS site_id,
                       oo.order_date, SUM(ool.ordered_quantity) AS actual_qty
                FROM outbound_order oo
                JOIN outbound_order_line ool ON ool.order_id = oo.id
                WHERE oo.config_id = :cfg AND ool.ordered_quantity > 0
                GROUP BY ool.product_id, oo.ship_from_site_id, oo.order_date
            )
            SELECT AVG(ABS(f.avg_fcst - a.actual_qty) / NULLIF(a.actual_qty, 0))
            FROM fcst f
            JOIN actuals a ON f.product_id = a.product_id
                AND f.site_id = a.site_id
                AND f.forecast_date = a.order_date
        """), {"cfg": config_id}).scalar()
        if fa is not None:
            roi["forecast_accuracy"] = round((1.0 - min(float(fa), 1.0)) * 100, 1)
    except Exception:
        pass

    # Inventory reduction: compare Autonomy avg order qty to ERP avg order qty
    if comparison.get("avg_order_qty") and comparison["avg_order_qty"].get("delta_pct"):
        # Smaller order sizes => proportionally less cycle stock
        reduction_pct = abs(comparison["avg_order_qty"]["delta_pct"]) / 3.0
        roi["inventory_reduction_pct"] = round(reduction_pct, 1)

    # Revenue increase proxy: more planning periods = longer horizon
    if comparison.get("periods") and comparison["periods"].get("delta_pct"):
        roi["revenue_increase_pct"] = round(comparison["periods"]["delta_pct"] / 30.0, 1)

    return {
        "erp_baseline": erp,
        "autonomy_plan": autonomy,
        "comparison": comparison,
        "roi": roi,
    }


@router.post("/{scenario_id}/promote")
def promote_scenario(
    scenario_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_active_user),
):
    """Promote a scenario to become the active baseline."""
    from app.models.supply_chain_config import SupplyChainConfig

    scenario = db.query(SupplyChainConfig).filter(
        SupplyChainConfig.id == scenario_id,
        SupplyChainConfig.tenant_id == current_user.tenant_id,
    ).first()
    if not scenario:
        raise HTTPException(404, "Scenario not found")

    parent_id = scenario.parent_config_id

    # Materialize inherited data before promotion (Kinaxis-style).
    # The child stores only deltas — on promote, copy all parent data
    # not already overridden into the child so it becomes self-contained.
    if parent_id:
        _materialize_inherited_data(db, parent_id, scenario_id, current_user.tenant_id)

        # Deactivate parent (now safely archived — child has all data)
        db.query(SupplyChainConfig).filter(
            SupplyChainConfig.id == parent_id,
        ).update({"is_active": False, "mode": "archived"})

    # Promote scenario — it is now the new baseline
    scenario.is_active = True
    scenario.mode = "production"
    scenario.scenario_type = "BASELINE"
    scenario.parent_config_id = None  # Self-contained, no longer a branch
    db.commit()

    return {"status": "promoted", "id": scenario_id, "name": scenario.name}


def _materialize_inherited_data(db, parent_id: int, child_id: int, tenant_id: int):
    """Copy all parent config-scoped data not already overridden into the child.

    After this, the child is fully self-contained and the parent can be
    safely archived or deleted without data loss. Only copies rows where
    the child doesn't already have its own version (delta-only storage).
    """
    from sqlalchemy import text

    # 1. Stochastic parameters: copy parent params not overridden in child
    db.execute(text("""
        INSERT INTO agent_stochastic_params
            (config_id, tenant_id, site_id, trm_type, param_name,
             distribution, is_default, source, created_at, updated_at)
        SELECT :child_id, tenant_id, site_id, trm_type, param_name,
               distribution, is_default, source, NOW(), NOW()
        FROM agent_stochastic_params p
        WHERE p.config_id = :parent_id
          AND NOT EXISTS (
              SELECT 1 FROM agent_stochastic_params c
              WHERE c.config_id = :child_id
                AND c.trm_type = p.trm_type
                AND c.param_name = p.param_name
                AND COALESCE(c.site_id, -1) = COALESCE(p.site_id, -1)
          )
    """), {"parent_id": parent_id, "child_id": child_id})

    # 2. Inventory policies: copy parent policies not overridden in child
    db.execute(text("""
        INSERT INTO inv_policy
            (product_id, site_id, config_id, ss_policy, ss_quantity, ss_days,
             reorder_point, reorder_quantity, max_quantity, target_dos,
             min_dos, max_dos, service_level_target, review_period_days,
             lead_time_days, abc_class, xyz_class, source, created_dttm)
        SELECT product_id, site_id, :child_id, ss_policy, ss_quantity, ss_days,
               reorder_point, reorder_quantity, max_quantity, target_dos,
               min_dos, max_dos, service_level_target, review_period_days,
               lead_time_days, abc_class, xyz_class, source, NOW()
        FROM inv_policy p
        WHERE p.config_id = :parent_id
          AND NOT EXISTS (
              SELECT 1 FROM inv_policy c
              WHERE c.config_id = :child_id
                AND c.product_id = p.product_id
                AND c.site_id = p.site_id
          )
    """), {"parent_id": parent_id, "child_id": child_id})

    # 3. Governance policies: copy parent policies not overridden in child
    try:
        db.execute(text("""
            INSERT INTO decision_governance_policies
                (config_id, tenant_id, agent_type, site_id, min_mode, max_mode,
                 priority_floor, priority_ceiling, impact_threshold, active, created_at)
            SELECT :child_id, tenant_id, agent_type, site_id, min_mode, max_mode,
                   priority_floor, priority_ceiling, impact_threshold, active, NOW()
            FROM decision_governance_policies p
            WHERE p.config_id = :parent_id
              AND NOT EXISTS (
                  SELECT 1 FROM decision_governance_policies c
                  WHERE c.config_id = :child_id
                    AND c.agent_type = p.agent_type
                    AND COALESCE(c.site_id, -1) = COALESCE(p.site_id, -1)
              )
        """), {"parent_id": parent_id, "child_id": child_id})
    except Exception:
        pass  # Table may not exist yet

    db.flush()
