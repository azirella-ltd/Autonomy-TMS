"""
Analytics API Endpoints

Provides analytics and reporting endpoints for SC Phase 3+ features:
- Order aggregation metrics
- Capacity utilization
- Policy effectiveness
- Comparative analysis

Routes:
    GET /api/v1/analytics/aggregation/{scenario_id}
    GET /api/v1/analytics/capacity/{scenario_id}
    GET /api/v1/analytics/policies/{config_id}
    GET /api/v1/analytics/comparison/{scenario_id}
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict
import csv
import json
import io

from app.db.session import get_db
from app.services.analytics_service import AnalyticsService
from app.models.scenario import Scenario
from app.models.supply_chain import ScenarioUserPeriod, ScenarioPeriod
from datetime import datetime, timedelta
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
from fastapi import Query


router = APIRouter()


@router.get("/aggregation/{scenario_id}", response_model=Dict)
async def get_aggregation_metrics(
    scenario_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get order aggregation metrics for a game

    Returns:
        - Aggregation summary (total orders, groups, cost savings)
        - Metrics by round
        - Metrics by site pair
    """
    # Verify game exists
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    service = AnalyticsService(db)
    metrics = await service.get_aggregation_metrics(scenario_id)

    return metrics


@router.get("/capacity/{scenario_id}", response_model=Dict)
async def get_capacity_metrics(
    scenario_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get capacity constraint metrics for a game

    Returns:
        - Capacity summary (sites, utilization, queued orders)
        - Metrics by site
        - Metrics by round
    """
    # Verify game exists
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    service = AnalyticsService(db)
    metrics = await service.get_capacity_metrics(scenario_id)

    return metrics


@router.get("/policies/{config_id}", response_model=Dict)
async def get_policy_effectiveness(
    config_id: int,
    tenant_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get policy effectiveness metrics

    Args:
        config_id: Supply chain configuration ID
        tenant_id: Tenant ID for multi-tenancy

    Returns:
        - Policy list with usage counts
        - Cost savings per policy
        - Effectiveness scores
    """
    service = AnalyticsService(db)
    metrics = await service.get_policy_effectiveness(config_id, tenant_id)

    return metrics


@router.get("/comparison/{scenario_id}", response_model=Dict)
async def get_comparative_analytics(
    scenario_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get comparative analytics (with vs. without features)

    Returns:
        - Features enabled status
        - Theoretical vs. actual metrics
        - Cost savings and efficiency gains
        - Capacity impact
    """
    # Verify game exists
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    service = AnalyticsService(db)
    metrics = await service.get_comparative_analytics(scenario_id)

    return metrics


@router.get("/summary/{scenario_id}", response_model=Dict)
async def get_analytics_summary(
    scenario_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get combined analytics summary for a game

    Returns all analytics in a single response for dashboard display.
    """
    # Verify game exists
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    service = AnalyticsService(db)

    # Get all metrics
    aggregation = await service.get_aggregation_metrics(scenario_id)
    capacity = await service.get_capacity_metrics(scenario_id)
    comparison = await service.get_comparative_analytics(scenario_id)

    return {
        'scenario_id': scenario_id,
        'scenario_name': scenario.name,
        'features_enabled': comparison.get('features_enabled', {}),
        'aggregation': aggregation,
        'capacity': capacity,
        'comparison': comparison
    }


@router.get("/export/aggregation/{scenario_id}/csv")
async def export_aggregation_csv(
    scenario_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Export aggregation metrics to CSV format

    Returns a CSV file with aggregation metrics by site pair
    """
    # Verify game exists
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    service = AnalyticsService(db)
    metrics = await service.get_aggregation_metrics(scenario_id)

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Write headers
    writer.writerow([
        'From Site', 'To Site', 'Groups Created', 'Orders Aggregated',
        'Total Cost Savings', 'Average Adjustment'
    ])

    # Write data rows
    for pair in metrics.get('by_site_pair', []):
        writer.writerow([
            pair.get('from_site', ''),
            pair.get('to_site', ''),
            pair.get('groups_created', 0),
            pair.get('orders_aggregated', 0),
            round(pair.get('total_savings', 0.0), 2),
            round(pair.get('avg_adjustment', 0.0), 2)
        ])

    # Prepare response
    output.seek(0)
    filename = f"aggregation_metrics_game_{scenario_id}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/export/capacity/{scenario_id}/csv")
async def export_capacity_csv(
    scenario_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Export capacity metrics to CSV format

    Returns a CSV file with capacity utilization by site
    """
    # Verify game exists
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    service = AnalyticsService(db)
    metrics = await service.get_capacity_metrics(scenario_id)

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Write headers
    writer.writerow([
        'Site', 'Max Capacity', 'Total Used', 'Utilization %', 'Status'
    ])

    # Write data rows
    for site in metrics.get('by_site', []):
        utilization = site.get('utilization_pct', 0.0)
        status = 'Critical' if utilization >= 90 else ('High' if utilization >= 70 else 'Normal')

        writer.writerow([
            site.get('site', ''),
            site.get('max_capacity', 0),
            round(site.get('total_used', 0.0), 2),
            round(utilization, 2),
            status
        ])

    # Prepare response
    output.seek(0)
    filename = f"capacity_metrics_game_{scenario_id}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/export/policies/{config_id}/csv")
async def export_policies_csv(
    config_id: int,
    tenant_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Export policy effectiveness metrics to CSV format

    Returns a CSV file with policy effectiveness data
    """
    service = AnalyticsService(db)
    metrics = await service.get_policy_effectiveness(config_id, tenant_id)

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Write headers
    writer.writerow([
        'Policy ID', 'Type', 'Route/Site', 'Usage Count',
        'Total Savings', 'Avg Savings per Use', 'Effectiveness Score', 'Capacity'
    ])

    # Write data rows
    for policy in metrics.get('policies', []):
        route_or_site = ''
        if policy['type'] == 'aggregation':
            route_or_site = f"{policy.get('from_site', '')} → {policy.get('to_site', '')}"
        else:
            route_or_site = policy.get('site', '')

        writer.writerow([
            policy.get('policy_id', ''),
            policy.get('type', ''),
            route_or_site,
            policy.get('usage_count', 0) if policy['type'] == 'aggregation' else '-',
            round(policy.get('total_savings', 0.0), 2) if policy['type'] == 'aggregation' else '-',
            round(policy.get('avg_savings_per_use', 0.0), 2) if policy['type'] == 'aggregation' else '-',
            round(policy.get('effectiveness_score', 0.0), 2) if policy['type'] == 'aggregation' else '-',
            round(policy.get('capacity', 0.0), 2) if policy['type'] == 'capacity' else '-'
        ])

    # Prepare response
    output.seek(0)
    filename = f"policy_effectiveness_config_{config_id}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/export/comparison/{scenario_id}/csv")
async def export_comparison_csv(
    scenario_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Export comparative analytics to CSV format

    Returns a CSV file with feature comparison data
    """
    # Verify game exists
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    service = AnalyticsService(db)
    metrics = await service.get_comparative_analytics(scenario_id)

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Write feature status
    writer.writerow(['Feature Status'])
    writer.writerow(['Order Aggregation', 'Enabled' if metrics.get('features_enabled', {}).get('order_aggregation') else 'Disabled'])
    writer.writerow(['Capacity Constraints', 'Enabled' if metrics.get('features_enabled', {}).get('capacity_constraints') else 'Disabled'])
    writer.writerow([])

    # Write comparison metrics
    comparison = metrics.get('comparison', {})
    if comparison:
        writer.writerow(['Metric', 'Without Features', 'With Features', 'Improvement'])

        theoretical = comparison.get('theoretical_without_aggregation', {})
        actual = comparison.get('actual_with_aggregation', {})
        savings = comparison.get('savings', {})

        writer.writerow([
            'Total Orders',
            theoretical.get('total_orders', 0),
            actual.get('total_orders', 0),
            f"-{savings.get('orders_reduced', 0)} orders"
        ])

        writer.writerow([
            'Total Cost',
            round(theoretical.get('total_cost', 0.0), 2),
            round(actual.get('total_cost', 0.0), 2),
            f"-${round(savings.get('cost_saved', 0.0), 2)}"
        ])

        writer.writerow([
            'Efficiency Gain',
            '-',
            '-',
            f"+{round(savings.get('efficiency_gain_pct', 0.0), 1)}%"
        ])

    # Prepare response
    output.seek(0)
    filename = f"comparative_analytics_game_{scenario_id}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/export/{scenario_id}/json")
async def export_all_json(
    scenario_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Export all analytics data to JSON format

    Returns a JSON file with complete analytics data for the game
    """
    # Verify game exists
    scenario = await db.get(Scenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")

    service = AnalyticsService(db)

    # Get all metrics
    aggregation = await service.get_aggregation_metrics(scenario_id)
    capacity = await service.get_capacity_metrics(scenario_id)
    comparison = await service.get_comparative_analytics(scenario_id)

    # Combine into single export
    export_data = {
        'scenario_id': scenario_id,
        'scenario_name': scenario.name,
        'export_timestamp': None,  # Will be set by frontend if needed
        'aggregation_metrics': aggregation,
        'capacity_metrics': capacity,
        'comparative_analytics': comparison
    }

    # Convert to JSON string
    json_str = json.dumps(export_data, indent=2)

    # Prepare response
    filename = f"analytics_export_game_{scenario_id}.json"

    return StreamingResponse(
        iter([json_str]),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ==============================================================================
# KPI Monitoring Endpoints
# ==============================================================================

class TimeRange(str, Enum):
    last_7_days = "last_7_days"
    last_30_days = "last_30_days"
    last_90_days = "last_90_days"
    last_12_months = "last_12_months"
    ytd = "ytd"


class FinancialKPIs(BaseModel):
    total_cost: float
    total_cost_trend: float
    inventory_holding_cost: float
    backlog_cost: float
    transportation_cost: float
    production_cost: float
    cost_by_week: List[Dict]


class CustomerKPIs(BaseModel):
    otif: float
    otif_trend: float
    otif_target: float
    fill_rate: float
    fill_rate_trend: float
    service_level: float
    service_level_trend: float
    customer_complaints: int
    complaints_trend: float
    otif_by_week: List[Dict]


class OperationalKPIs(BaseModel):
    inventory_turns: float
    inventory_turns_trend: float
    days_of_supply: float
    days_of_supply_trend: float
    bullwhip_ratio: float
    bullwhip_trend: float
    stockout_incidents: int
    stockout_trend: float
    capacity_utilization: float
    utilization_trend: float
    on_time_delivery: float
    delivery_trend: float
    inventory_trend: List[Dict]


class StrategicKPIs(BaseModel):
    supplier_reliability: float
    supplier_trend: float
    network_flexibility: float
    flexibility_trend: float
    forecast_accuracy: float
    forecast_trend: float
    carbon_emissions: float
    emissions_trend: float
    risk_score: float
    risk_trend: float


class KPIResponse(BaseModel):
    financial: FinancialKPIs
    customer: CustomerKPIs
    operational: OperationalKPIs
    strategic: StrategicKPIs


def get_date_range(time_range: TimeRange) -> tuple:
    """Get start and end dates for the given time range."""
    end_date = datetime.utcnow()

    if time_range == TimeRange.last_7_days:
        start_date = end_date - timedelta(days=7)
    elif time_range == TimeRange.last_30_days:
        start_date = end_date - timedelta(days=30)
    elif time_range == TimeRange.last_90_days:
        start_date = end_date - timedelta(days=90)
    elif time_range == TimeRange.last_12_months:
        start_date = end_date - timedelta(days=365)
    elif time_range == TimeRange.ytd:
        start_date = datetime(end_date.year, 1, 1)
    else:
        start_date = end_date - timedelta(days=30)

    return start_date, end_date


@router.get("/kpis", response_model=KPIResponse)
async def get_kpis(
    time_range: TimeRange = Query(TimeRange.last_30_days),
    db: AsyncSession = Depends(get_db)
):
    """
    Get comprehensive KPI dashboard data.

    Calculates KPIs across 4 categories:
    - Financial: Costs, trends
    - Customer: OTIF, fill rate, service level
    - Operational: Inventory turns, bullwhip, stockouts
    - Strategic: Reliability, flexibility, forecast accuracy
    """
    start_date, end_date = get_date_range(time_range)

    # Query scenario_user rounds in date range
    from sqlalchemy import select
    result = await db.execute(
        select(ScenarioUserPeriod)
        .join(ScenarioPeriod)
        .join(Scenario)
        .where(Scenario.created_at >= start_date)
        .where(Scenario.created_at <= end_date)
    )
    scenario_user_periods = result.scalars().all()

    if not scenario_user_periods:
        # Return default/mock values if no data
        return KPIResponse(
            financial=FinancialKPIs(
                total_cost=0,
                total_cost_trend=0,
                inventory_holding_cost=0,
                backlog_cost=0,
                transportation_cost=0,
                production_cost=0,
                cost_by_week=[]
            ),
            customer=CustomerKPIs(
                otif=0,
                otif_trend=0,
                otif_target=95.0,
                fill_rate=0,
                fill_rate_trend=0,
                service_level=0,
                service_level_trend=0,
                customer_complaints=0,
                complaints_trend=0,
                otif_by_week=[]
            ),
            operational=OperationalKPIs(
                inventory_turns=0,
                inventory_turns_trend=0,
                days_of_supply=0,
                days_of_supply_trend=0,
                bullwhip_ratio=0,
                bullwhip_trend=0,
                stockout_incidents=0,
                stockout_trend=0,
                capacity_utilization=0,
                utilization_trend=0,
                on_time_delivery=0,
                delivery_trend=0,
                inventory_trend=[]
            ),
            strategic=StrategicKPIs(
                supplier_reliability=0,
                supplier_trend=0,
                network_flexibility=0,
                flexibility_trend=0,
                forecast_accuracy=0,
                forecast_trend=0,
                carbon_emissions=0,
                emissions_trend=0,
                risk_score=0,
                risk_trend=0
            )
        )

    # ── Financial KPIs ──
    total_cost = sum(pr.total_cost or 0 for pr in scenario_user_periods)
    inventory_cost = sum(pr.holding_cost or 0 for pr in scenario_user_periods)
    backlog_cost = sum(pr.backlog_cost or 0 for pr in scenario_user_periods)
    # Derive transport/production as remainder split evenly (no dedicated columns)
    other_cost = max(0, total_cost - inventory_cost - backlog_cost)
    transportation_cost = other_cost * 0.5
    production_cost = other_cost * 0.5

    cost_by_week = []
    for i in range(12):
        week_start = end_date - timedelta(weeks=12-i)
        week_end = week_start + timedelta(weeks=1)
        week_cost = sum(
            pr.total_cost or 0 for pr in scenario_user_periods
            if hasattr(pr, 'created_at') and pr.created_at and week_start <= pr.created_at < week_end
        )
        cost_by_week.append({"week": i + 1, "cost": round(week_cost, 2)})

    # ── Helper: compute % trend from first-half vs second-half ──
    total_rounds = len(scenario_user_periods)
    mid = total_rounds // 2

    def _pct_trend(values):
        """Compute percentage change between first and second halves."""
        if len(values) < 4:
            return 0.0
        m = len(values) // 2
        first_avg = sum(values[:m]) / m if m > 0 else 0
        second_avg = sum(values[m:]) / (len(values) - m) if (len(values) - m) > 0 else 0
        if first_avg == 0:
            return 0.0
        return round((second_avg - first_avg) / abs(first_avg) * 100, 1)

    cost_trend = _pct_trend([pr.total_cost or 0 for pr in scenario_user_periods])

    # ── Customer KPIs ──
    rounds_no_backlog = sum(1 for pr in scenario_user_periods if (pr.backlog or 0) == 0)
    otif = (rounds_no_backlog / total_rounds * 100) if total_rounds > 0 else 0

    total_demand = sum(pr.demand or 0 for pr in scenario_user_periods)
    total_fulfilled = sum(pr.shipment_downstream or 0 for pr in scenario_user_periods)
    fill_rate = (total_fulfilled / total_demand * 100) if total_demand > 0 else 100

    complaints = sum(1 for pr in scenario_user_periods if (pr.backlog or 0) > 10)

    otif_values = [
        (1 if (pr.backlog or 0) == 0 else 0) for pr in scenario_user_periods
    ]
    otif_trend = _pct_trend(otif_values) if otif_values else 0
    fill_values = [
        ((pr.shipment_downstream or 0) / (pr.demand or 1) * 100)
        for pr in scenario_user_periods
    ]
    fill_trend = _pct_trend(fill_values)

    # Real per-week OTIF from data
    otif_by_week = []
    for i in range(12):
        week_start = end_date - timedelta(weeks=12-i)
        week_end = week_start + timedelta(weeks=1)
        week_prs = [
            pr for pr in scenario_user_periods
            if hasattr(pr, 'created_at') and pr.created_at and week_start <= pr.created_at < week_end
        ]
        if week_prs:
            wk_otif = sum(1 for pr in week_prs if (pr.backlog or 0) == 0) / len(week_prs) * 100
        else:
            wk_otif = otif  # use overall average when no data for this week
        otif_by_week.append({"week": i + 1, "otif": round(wk_otif, 2)})

    # ── Operational KPIs ──
    avg_inventory = sum(pr.inventory or 0 for pr in scenario_user_periods) / total_rounds if total_rounds > 0 else 0
    inventory_turns = (total_fulfilled / avg_inventory * 12) if avg_inventory > 0 else 0

    avg_demand = total_demand / total_rounds if total_rounds > 0 else 0
    days_of_supply = (avg_inventory / avg_demand * 7) if avg_demand > 0 else 0

    orders = [pr.order_upstream for pr in scenario_user_periods if pr.order_upstream is not None]
    demands = [pr.demand for pr in scenario_user_periods if pr.demand is not None]

    if len(orders) > 1 and len(demands) > 1:
        import statistics
        order_var = statistics.variance(orders) if len(orders) > 1 else 1
        demand_var = statistics.variance(demands) if len(demands) > 1 else 1
        bullwhip_ratio = (order_var / demand_var) if demand_var > 0 else 1.0
    else:
        bullwhip_ratio = 1.0

    stockout_incidents = sum(1 for pr in scenario_user_periods if (pr.inventory or 0) < 0)

    inv_trend = _pct_trend([pr.inventory or 0 for pr in scenario_user_periods])
    turns_trend = _pct_trend(
        [(pr.shipment_downstream or 0) / max(pr.inventory or 1, 1) for pr in scenario_user_periods]
    )
    dos_trend = _pct_trend(
        [(pr.inventory or 0) / max(pr.demand or 1, 1) for pr in scenario_user_periods]
    )

    # Capacity utilization: fulfilled / (fulfilled + backlog) as proxy
    total_capacity_proxy = total_fulfilled + sum(pr.backlog or 0 for pr in scenario_user_periods)
    capacity_utilization = (total_fulfilled / total_capacity_proxy * 100) if total_capacity_proxy > 0 else 0

    # Real per-week inventory from data
    inventory_trend_data = []
    for i in range(12):
        week_start = end_date - timedelta(weeks=12-i)
        week_end = week_start + timedelta(weeks=1)
        week_prs = [
            pr for pr in scenario_user_periods
            if hasattr(pr, 'created_at') and pr.created_at and week_start <= pr.created_at < week_end
        ]
        wk_inv = sum(pr.inventory or 0 for pr in week_prs) / len(week_prs) if week_prs else avg_inventory
        inventory_trend_data.append({"week": i + 1, "inventory": round(wk_inv, 2)})

    # ── Strategic KPIs ──
    stockouts = sum(1 for pr in scenario_user_periods if (pr.inventory or 0) < 0)
    supplier_reliability = max(80, 100 - (stockouts / total_rounds * 100))

    # Forecast accuracy: compare demand vs order placed (demand-matching proxy)
    forecast_accuracy = fill_rate  # best available proxy

    # Network flexibility: ratio of rounds where inventory > safety threshold
    safety_threshold = avg_demand * 2 if avg_demand > 0 else 0
    flex_rounds = sum(1 for pr in scenario_user_periods if (pr.inventory or 0) > safety_threshold)
    network_flexibility = (flex_rounds / total_rounds * 100) if total_rounds > 0 else 0

    # Risk score: weighted composite (lower is better, 1-5 scale)
    stockout_rate = stockouts / total_rounds if total_rounds > 0 else 0
    backlog_rate = complaints / total_rounds if total_rounds > 0 else 0
    risk_score = min(5.0, max(1.0, 1.0 + stockout_rate * 10 + backlog_rate * 5 + max(0, bullwhip_ratio - 1) * 2))

    return KPIResponse(
        financial=FinancialKPIs(
            total_cost=round(total_cost, 2),
            total_cost_trend=cost_trend,
            inventory_holding_cost=round(inventory_cost, 2),
            backlog_cost=round(backlog_cost, 2),
            transportation_cost=round(transportation_cost, 2),
            production_cost=round(production_cost, 2),
            cost_by_week=cost_by_week
        ),
        customer=CustomerKPIs(
            otif=round(otif, 2),
            otif_trend=otif_trend,
            otif_target=95.0,
            fill_rate=round(fill_rate, 2),
            fill_rate_trend=fill_trend,
            service_level=round(fill_rate, 2),
            service_level_trend=fill_trend,
            customer_complaints=complaints,
            complaints_trend=_pct_trend([1 if (pr.backlog or 0) > 10 else 0 for pr in scenario_user_periods]),
            otif_by_week=otif_by_week
        ),
        operational=OperationalKPIs(
            inventory_turns=round(inventory_turns, 2),
            inventory_turns_trend=turns_trend,
            days_of_supply=round(days_of_supply, 2),
            days_of_supply_trend=dos_trend,
            bullwhip_ratio=round(bullwhip_ratio, 2),
            bullwhip_trend=_pct_trend(
                [abs((pr.order_upstream or 0) - (pr.demand or 0)) for pr in scenario_user_periods]
            ),
            stockout_incidents=stockout_incidents,
            stockout_trend=_pct_trend([1 if (pr.inventory or 0) < 0 else 0 for pr in scenario_user_periods]),
            capacity_utilization=round(capacity_utilization, 2),
            utilization_trend=_pct_trend(
                [(pr.shipment_downstream or 0) / max((pr.shipment_downstream or 0) + (pr.backlog or 0), 1) for pr in scenario_user_periods]
            ),
            on_time_delivery=round(otif, 2),
            delivery_trend=otif_trend,
            inventory_trend=inventory_trend_data
        ),
        strategic=StrategicKPIs(
            supplier_reliability=round(supplier_reliability, 2),
            supplier_trend=_pct_trend(
                [0 if (pr.inventory or 0) < 0 else 1 for pr in scenario_user_periods]
            ),
            network_flexibility=round(network_flexibility, 2),
            flexibility_trend=_pct_trend(
                [1 if (pr.inventory or 0) > safety_threshold else 0 for pr in scenario_user_periods]
            ),
            forecast_accuracy=round(forecast_accuracy, 2),
            forecast_trend=fill_trend,
            carbon_emissions=round(total_fulfilled * 0.5, 2),
            emissions_trend=_pct_trend([pr.shipment_downstream or 0 for pr in scenario_user_periods]),
            risk_score=round(risk_score, 1),
            risk_trend=_pct_trend(
                [((pr.backlog or 0) + max(0, -(pr.inventory or 0))) for pr in scenario_user_periods]
            ),
        )
    )
