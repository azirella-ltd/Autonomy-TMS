"""
Supply Plan API Endpoints

REST API for supply plan generation, status checking, and result retrieval.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime

from app.api import deps
from app.models.user import User
from app.models.supply_plan import (
    SupplyPlanRequest,
    SupplyPlanResult,
    SupplyPlanComparison,
    SupplyPlanExport,
    PlanStatus
)
from app.models.supply_chain_config import SupplyChainConfig
from app.schemas.supply_plan import (
    SupplyPlanGenerateRequest,
    SupplyPlanGenerateResponse,
    SupplyPlanStatusResponse,
    SupplyPlanResultResponse,
    SupplyPlanComparisonRequest,
    SupplyPlanComparisonResponse,
    SupplyPlanExportRequest,
    SupplyPlanExportResponse,
    ConfigComparisonRequest,
    ConfigComparisonResponse,
)
from app.services.supply_plan_service import SupplyPlanService
from app.services.stochastic_sampling import StochasticParameters
from app.services.monte_carlo_planner import PlanObjectives


router = APIRouter()


def run_supply_plan_generation(
    request_id: int,
    db: Session
):
    """
    Background task to generate supply plan.

    Args:
        request_id: Supply plan request ID
        db: Database session
    """
    try:
        # Load request
        request = db.query(SupplyPlanRequest).filter(SupplyPlanRequest.id == request_id).first()
        if not request:
            return

        # Update status
        request.status = PlanStatus.RUNNING
        request.started_at = datetime.utcnow()
        db.commit()

        # Load configuration
        config = db.query(SupplyChainConfig).filter(SupplyChainConfig.id == request.config_id).first()
        if not config:
            request.status = PlanStatus.FAILED
            request.error_message = f"Configuration {request.config_id} not found"
            db.commit()
            return

        # Parse parameters
        stochastic_params = StochasticParameters(**request.stochastic_params)
        objectives = PlanObjectives(**request.objectives)

        # Generate plan
        service = SupplyPlanService(db, config)

        def progress_callback(completed: int, total: int):
            """Update progress."""
            request.progress = completed / total
            db.commit()

        result_data = service.generate_supply_plan(
            stochastic_params,
            objectives,
            num_scenarios=request.num_scenarios,
            progress_callback=progress_callback
        )

        # Save result including plan detail (orders + inventory targets)
        plan_result = SupplyPlanResult(
            request_id=request.id,
            scorecard=result_data["scorecard"],
            recommendations=result_data["recommendations"],
            orders=result_data.get("orders"),
            inventory_targets=result_data.get("inventory_targets"),
            total_cost_expected=result_data["scorecard"]["financial"]["total_cost"]["expected"],
            total_cost_p10=result_data["scorecard"]["financial"]["total_cost"]["p10"],
            total_cost_p90=result_data["scorecard"]["financial"]["total_cost"]["p90"],
            otif_expected=result_data["scorecard"]["customer"]["otif"]["expected"],
            otif_probability_above_target=result_data["scorecard"]["customer"]["otif"]["probability_above_target"],
            fill_rate_expected=result_data["scorecard"]["customer"]["fill_rate"]["expected"],
            inventory_turns_expected=result_data["scorecard"]["operational"]["inventory_turns"]["expected"],
            bullwhip_ratio_expected=result_data["scorecard"]["operational"]["bullwhip_ratio"]["expected"],
        )

        db.add(plan_result)

        # Update request status
        request.status = PlanStatus.COMPLETED
        request.completed_at = datetime.utcnow()
        request.progress = 1.0

        db.commit()

    except Exception as e:
        # Update request with error
        request.status = PlanStatus.FAILED
        request.error_message = str(e)
        db.commit()


@router.post("/generate", response_model=SupplyPlanGenerateResponse)
def generate_supply_plan(
    *,
    db: Session = Depends(deps.get_db),
    request_data: SupplyPlanGenerateRequest,
    current_user: User = Depends(deps.get_current_user),
    background_tasks: BackgroundTasks
) -> SupplyPlanGenerateResponse:
    """
    Generate a supply plan using Monte Carlo simulation.

    Creates a background task to run the plan generation and returns
    a task ID for status checking.
    """
    # Resolve config: explicit or tenant's active baseline
    effective_config_id = request_data.config_id
    if effective_config_id is None:
        effective_config_id = deps.get_active_baseline_config(db, current_user.tenant_id).id

    config = db.query(SupplyChainConfig).filter(
        SupplyChainConfig.id == effective_config_id
    ).first()

    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supply chain configuration {effective_config_id} not found"
        )

    # Create supply plan request
    plan_request = SupplyPlanRequest(
        user_id=current_user.id,
        config_id=effective_config_id,
        config_name=config.name,
        agent_strategy=request_data.agent_strategy,
        num_scenarios=request_data.num_scenarios,
        stochastic_params=request_data.stochastic_params.dict(),
        objectives=request_data.objectives.dict(),
        status=PlanStatus.PENDING,
        progress=0.0,
    )

    db.add(plan_request)
    db.commit()
    db.refresh(plan_request)

    # Schedule background task
    background_tasks.add_task(run_supply_plan_generation, plan_request.id, db)

    return SupplyPlanGenerateResponse(
        task_id=plan_request.id,
        status=PlanStatus.RUNNING,
        message=f"Supply plan generation started with {request_data.num_scenarios} scenarios"
    )


@router.get("/status/{task_id}", response_model=SupplyPlanStatusResponse)
def get_supply_plan_status(
    *,
    db: Session = Depends(deps.get_db),
    task_id: int,
    current_user: User = Depends(deps.get_current_user)
) -> SupplyPlanStatusResponse:
    """
    Get status of supply plan generation task.
    """
    plan_request = db.query(SupplyPlanRequest).filter(
        SupplyPlanRequest.id == task_id,
        SupplyPlanRequest.user_id == current_user.id
    ).first()

    if not plan_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supply plan request {task_id} not found"
        )

    return SupplyPlanStatusResponse(
        task_id=plan_request.id,
        status=plan_request.status,
        progress=plan_request.progress,
        created_at=plan_request.created_at,
        started_at=plan_request.started_at,
        completed_at=plan_request.completed_at,
        error_message=plan_request.error_message
    )


@router.get("/result/{task_id}", response_model=SupplyPlanResultResponse)
def get_supply_plan_result(
    *,
    db: Session = Depends(deps.get_db),
    task_id: int,
    current_user: User = Depends(deps.get_current_user)
) -> SupplyPlanResultResponse:
    """
    Get complete supply plan result.
    """
    plan_request = db.query(SupplyPlanRequest).filter(
        SupplyPlanRequest.id == task_id,
        SupplyPlanRequest.user_id == current_user.id
    ).first()

    if not plan_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supply plan request {task_id} not found"
        )

    if plan_request.status != PlanStatus.COMPLETED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Supply plan is not completed yet. Current status: {plan_request.status}"
        )

    result = db.query(SupplyPlanResult).filter(
        SupplyPlanResult.request_id == task_id
    ).first()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supply plan result not found"
        )

    # Compute conformal summary from plan orders if available
    conformal_summary = None
    if result.orders:
        plans_with_demand = sum(1 for o in result.orders if o.get('demand_coverage'))
        plans_with_lt = sum(1 for o in result.orders if o.get('lead_time_coverage'))
        total_plans = len(result.orders)
        avg_demand_coverage = 0.0
        avg_lt_coverage = 0.0
        if plans_with_demand > 0:
            avg_demand_coverage = sum(
                o['demand_coverage'] for o in result.orders if o.get('demand_coverage')
            ) / plans_with_demand
        if plans_with_lt > 0:
            avg_lt_coverage = sum(
                o['lead_time_coverage'] for o in result.orders if o.get('lead_time_coverage')
            ) / plans_with_lt

        if plans_with_demand > 0 or plans_with_lt > 0:
            conformal_summary = {
                "demand_intervals_available": plans_with_demand,
                "lead_time_intervals_available": plans_with_lt,
                "total_plans": total_plans,
                "avg_demand_coverage": round(avg_demand_coverage, 4),
                "avg_lead_time_coverage": round(avg_lt_coverage, 4),
            }

    return SupplyPlanResultResponse(
        task_id=task_id,
        status=plan_request.status,
        config_id=plan_request.config_id,
        config_name=plan_request.config_name,
        agent_strategy=plan_request.agent_strategy,
        num_scenarios=plan_request.num_scenarios,
        planning_horizon=plan_request.objectives.get("planning_horizon", 52),
        scorecard=result.scorecard,
        recommendations=result.recommendations,
        orders=result.orders,
        inventory_targets=result.inventory_targets,
        total_cost_expected=result.total_cost_expected,
        total_cost_p10=result.total_cost_p10,
        total_cost_p90=result.total_cost_p90,
        otif_expected=result.otif_expected,
        otif_probability_above_target=result.otif_probability_above_target,
        fill_rate_expected=result.fill_rate_expected,
        inventory_turns_expected=result.inventory_turns_expected,
        bullwhip_ratio_expected=result.bullwhip_ratio_expected,
        created_at=plan_request.created_at,
        completed_at=plan_request.completed_at,
        conformal_summary=conformal_summary,
        plan_confidence=result.plan_confidence,
    )


@router.get("/confidence/{task_id}")
def get_plan_confidence(
    *,
    db: Session = Depends(deps.get_db),
    task_id: int,
    current_user: User = Depends(deps.get_current_user),
):
    """
    Get the plan-level confidence score for a completed supply plan.

    Returns the composite confidence with diagnostic breakdown.
    The confidence score is computed from conformal prediction calibration
    coverage across demand, lead time, safety stock, and predictor freshness.
    """
    plan_request = db.query(SupplyPlanRequest).filter(
        SupplyPlanRequest.id == task_id,
        SupplyPlanRequest.user_id == current_user.id,
    ).first()

    if not plan_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supply plan request {task_id} not found"
        )

    result = db.query(SupplyPlanResult).filter(
        SupplyPlanResult.request_id == task_id
    ).first()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Supply plan result not found"
        )

    if not result.plan_confidence:
        return {
            "task_id": task_id,
            "plan_confidence": None,
            "message": "Plan confidence not available. Run planning with conformal intervals enabled."
        }

    return {
        "task_id": task_id,
        "plan_confidence": result.plan_confidence,
    }


@router.post("/compare", response_model=SupplyPlanComparisonResponse)
def compare_supply_plans(
    *,
    db: Session = Depends(deps.get_db),
    comparison_data: SupplyPlanComparisonRequest,
    current_user: User = Depends(deps.get_current_user)
) -> SupplyPlanComparisonResponse:
    """
    Compare multiple supply plans.
    """
    # Validate all plans exist and belong to user
    plans = []
    for plan_id in comparison_data.plan_ids:
        plan = db.query(SupplyPlanRequest).filter(
            SupplyPlanRequest.id == plan_id,
            SupplyPlanRequest.user_id == current_user.id
        ).first()

        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Supply plan {plan_id} not found"
            )

        if plan.status != PlanStatus.COMPLETED:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Supply plan {plan_id} is not completed"
            )

        plans.append(plan)

    # Get results
    results = {}
    for plan in plans:
        result = db.query(SupplyPlanResult).filter(
            SupplyPlanResult.request_id == plan.id
        ).first()

        if result:
            results[plan.agent_strategy] = result

    # Compute comparison metrics
    metrics = {
        "total_cost": {},
        "otif": {},
        "fill_rate": {},
        "inventory_turns": {},
    }

    for strategy, result in results.items():
        metrics["total_cost"][strategy] = result.total_cost_expected
        metrics["otif"][strategy] = result.otif_expected
        metrics["fill_rate"][strategy] = result.fill_rate_expected
        metrics["inventory_turns"][strategy] = result.inventory_turns_expected

    # Determine winner (best OTIF with reasonable cost)
    winner = max(results.keys(), key=lambda s: results[s].otif_expected)

    # Save comparison
    comparison = SupplyPlanComparison(
        user_id=current_user.id,
        name=comparison_data.name,
        description=comparison_data.description,
        plan_ids=comparison_data.plan_ids,
        comparison_data={
            "winner": winner,
            "metrics": metrics
        }
    )

    db.add(comparison)
    db.commit()
    db.refresh(comparison)

    return SupplyPlanComparisonResponse(
        comparison_id=comparison.id,
        name=comparison.name,
        plan_ids=comparison.plan_ids,
        winner=winner,
        metrics=metrics,
        created_at=comparison.created_at
    )


@router.post("/compare-configs", response_model=ConfigComparisonResponse)
def compare_config_plans(
    *,
    db: Session = Depends(deps.get_db),
    request_data: ConfigComparisonRequest,
    current_user: User = Depends(deps.get_current_user)
) -> ConfigComparisonResponse:
    """
    Compare supply plans from baseline vs branch configs side-by-side.

    Returns balanced scorecard deltas and configuration diff (topology,
    sourcing rules, etc.) to support alternate sourcing evaluation.
    """
    # Load both plans
    baseline_plan = db.query(SupplyPlanRequest).filter(
        SupplyPlanRequest.id == request_data.baseline_plan_id
    ).first()
    branch_plan = db.query(SupplyPlanRequest).filter(
        SupplyPlanRequest.id == request_data.branch_plan_id
    ).first()

    if not baseline_plan:
        raise HTTPException(404, f"Baseline plan {request_data.baseline_plan_id} not found")
    if not branch_plan:
        raise HTTPException(404, f"Branch plan {request_data.branch_plan_id} not found")

    for plan in [baseline_plan, branch_plan]:
        if plan.status != PlanStatus.COMPLETED:
            raise HTTPException(400, f"Plan {plan.id} is not completed (status: {plan.status})")

    # Load results
    baseline_result = db.query(SupplyPlanResult).filter(
        SupplyPlanResult.request_id == baseline_plan.id
    ).first()
    branch_result = db.query(SupplyPlanResult).filter(
        SupplyPlanResult.request_id == branch_plan.id
    ).first()

    if not baseline_result or not branch_result:
        raise HTTPException(404, "One or both plans have no results")

    # Build scorecards
    def _scorecard(r):
        return {
            "total_cost": r.total_cost_expected,
            "otif": r.otif_expected,
            "fill_rate": r.fill_rate_expected,
            "inventory_turns": r.inventory_turns_expected,
            "total_cost_p10": getattr(r, "total_cost_p10", None),
            "total_cost_p90": getattr(r, "total_cost_p90", None),
        }

    baseline_sc = _scorecard(baseline_result)
    branch_sc = _scorecard(branch_result)

    # Compute deltas
    cost_delta = (branch_sc["total_cost"] or 0) - (baseline_sc["total_cost"] or 0)
    baseline_cost = baseline_sc["total_cost"] or 1
    cost_delta_pct = (cost_delta / baseline_cost) * 100 if baseline_cost else 0.0

    # Config diff (topology + sourcing rules)
    config_diff = {}
    if baseline_plan.config_id and branch_plan.config_id:
        try:
            from app.services.scenario_branching_service import ScenarioBranchingService
            branching = ScenarioBranchingService(db)
            config_diff = branching.diff_scenarios(baseline_plan.config_id, branch_plan.config_id)
        except Exception:
            config_diff = {"error": "Could not compute config diff"}

    # Generate recommendation
    parts = []
    if cost_delta < 0:
        parts.append(f"Branch reduces cost by {abs(cost_delta_pct):.1f}%")
    elif cost_delta > 0:
        parts.append(f"Branch increases cost by {cost_delta_pct:.1f}%")

    otif_delta = (branch_sc["otif"] or 0) - (baseline_sc["otif"] or 0)
    if otif_delta > 0:
        parts.append(f"OTIF improves by {otif_delta:.1f}pp")
    elif otif_delta < 0:
        parts.append(f"OTIF decreases by {abs(otif_delta):.1f}pp")

    recommendation = ". ".join(parts) + "." if parts else None

    return ConfigComparisonResponse(
        baseline_plan_id=request_data.baseline_plan_id,
        branch_plan_id=request_data.branch_plan_id,
        cost_delta=cost_delta,
        cost_delta_pct=cost_delta_pct,
        otif_delta=otif_delta,
        fill_rate_delta=(branch_sc["fill_rate"] or 0) - (baseline_sc["fill_rate"] or 0),
        inventory_turns_delta=(branch_sc["inventory_turns"] or 0) - (baseline_sc["inventory_turns"] or 0),
        baseline_scorecard=baseline_sc,
        branch_scorecard=branch_sc,
        config_diff=config_diff,
        recommendation=recommendation,
    )


@router.get("/list")
def list_supply_plans(
    *,
    db: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    skip: int = 0,
    limit: int = 100
):
    """
    List supply plans for current user.
    """
    plans = db.query(SupplyPlanRequest).filter(
        SupplyPlanRequest.user_id == current_user.id
    ).order_by(SupplyPlanRequest.created_at.desc()).offset(skip).limit(limit).all()

    return {
        "plans": [
            {
                "id": plan.id,
                "config_name": plan.config_name,
                "agent_strategy": plan.agent_strategy,
                "status": plan.status,
                "progress": plan.progress,
                "created_at": plan.created_at,
                "completed_at": plan.completed_at,
            }
            for plan in plans
        ],
        "total": db.query(SupplyPlanRequest).filter(
            SupplyPlanRequest.user_id == current_user.id
        ).count()
    }
