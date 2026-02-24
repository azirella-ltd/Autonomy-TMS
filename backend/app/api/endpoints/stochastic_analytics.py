"""
Stochastic Analytics API Endpoints

Endpoints for analyzing stochastic supply chain simulations:
- Variability analysis
- Confidence intervals
- Risk metrics (VaR, CVaR)
- Distribution fit testing
- Scenario comparison
- Monte Carlo simulation management

Used by analytics dashboards for visualizing supply chain performance under uncertainty.
"""

from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
import numpy as np

from app.services.stochastic_analytics_service import StochasticAnalyticsService
from app.api.deps import get_current_user
from app.models.user import User

router = APIRouter(prefix="/stochastic/analytics", tags=["stochastic-analytics"])


# ============================================================================
# REQUEST/RESPONSE MODELS
# ============================================================================

class VariabilityAnalysisRequest(BaseModel):
    """Request to analyze variability in data"""
    samples: List[float] = Field(..., description="Sample data to analyze", min_items=2)


class VariabilityAnalysisResponse(BaseModel):
    """Response with variability metrics"""
    mean: float
    std: float
    cv: float
    min: float
    max: float
    range: float
    iqr: float
    mad: float


class ConfidenceIntervalRequest(BaseModel):
    """Request to calculate confidence interval"""
    samples: List[float] = Field(..., min_items=2)
    confidence: float = Field(0.95, ge=0.5, le=0.999, description="Confidence level (0.5-0.999)")


class ConfidenceIntervalResponse(BaseModel):
    """Response with confidence interval"""
    lower: float
    upper: float
    mean: float
    confidence: float
    margin_of_error: float


class RiskMetricsRequest(BaseModel):
    """Request to calculate risk metrics"""
    samples: List[float] = Field(..., min_items=2, description="Cost/loss values")


class RiskMetricsResponse(BaseModel):
    """Response with risk metrics"""
    var_95: float
    var_99: float
    cvar_95: float
    cvar_99: float
    max_drawdown: float


class DistributionFitRequest(BaseModel):
    """Request to test distribution fit"""
    samples: List[float] = Field(..., min_items=5)
    distribution: str = Field("norm", description="Distribution type to test (norm, lognorm, gamma, etc.)")


class DistributionFitResponse(BaseModel):
    """Response with goodness-of-fit test results"""
    distribution_type: str
    statistic: float
    p_value: float
    significant: bool
    interpretation: str


class ScenarioComparisonRequest(BaseModel):
    """Request to compare multiple scenarios"""
    scenarios: Dict[str, List[float]] = Field(..., description="Scenario name -> samples")
    metric: str = Field("total_cost", description="Metric being compared")


class ScenarioComparisonResponse(BaseModel):
    """Response with scenario comparison"""
    scenarios: Dict[str, Dict[str, float]]
    rankings: Dict[str, str]


class MonteCarloRequest(BaseModel):
    """Request to run Monte Carlo simulation"""
    game_id: int
    num_runs: int = Field(100, ge=10, le=1000, description="Number of simulation runs")
    base_seed: int = Field(42, description="Base random seed")


class MonteCarloStatusResponse(BaseModel):
    """Response with Monte Carlo simulation status"""
    task_id: str
    status: str  # 'pending', 'running', 'complete', 'failed'
    progress: Optional[float] = None
    result: Optional[Dict[str, Any]] = None


# ============================================================================
# API ENDPOINTS
# ============================================================================

@router.post("/variability", response_model=VariabilityAnalysisResponse)
async def analyze_variability(
    request: VariabilityAnalysisRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Analyze variability in sample data

    Returns comprehensive variability metrics including:
    - Mean and standard deviation
    - Coefficient of variation (CV)
    - Range and interquartile range (IQR)
    - Median absolute deviation (MAD)

    Requires authentication.
    """
    try:
        service = StochasticAnalyticsService()
        samples = np.array(request.samples)

        metrics = service.analyze_variability(samples)

        return VariabilityAnalysisResponse(
            mean=metrics.mean,
            std=metrics.std,
            cv=metrics.cv,
            min=metrics.min,
            max=metrics.max,
            range=metrics.range,
            iqr=metrics.iqr,
            mad=metrics.mad
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze variability: {str(e)}"
        )


@router.post("/confidence-interval", response_model=ConfidenceIntervalResponse)
async def calculate_confidence_interval(
    request: ConfidenceIntervalRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Calculate confidence interval for the mean

    Uses t-distribution for accurate intervals with small samples.

    Requires authentication.
    """
    try:
        service = StochasticAnalyticsService()
        samples = np.array(request.samples)

        ci = service.confidence_interval(samples, confidence=request.confidence)

        return ConfidenceIntervalResponse(
            lower=ci.lower,
            upper=ci.upper,
            mean=ci.mean,
            confidence=ci.confidence,
            margin_of_error=ci.margin_of_error
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to calculate confidence interval: {str(e)}"
        )


@router.post("/risk-metrics", response_model=RiskMetricsResponse)
async def calculate_risk_metrics(
    request: RiskMetricsRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Calculate risk metrics (VaR, CVaR)

    Value at Risk (VaR): Threshold such that probability of exceeding is α
    Conditional VaR (CVaR): Expected value beyond VaR threshold

    Requires authentication.
    """
    try:
        service = StochasticAnalyticsService()
        samples = np.array(request.samples)

        metrics = service.calculate_risk_metrics(samples)

        return RiskMetricsResponse(
            var_95=metrics.var_95,
            var_99=metrics.var_99,
            cvar_95=metrics.cvar_95,
            cvar_99=metrics.cvar_99,
            max_drawdown=metrics.max_drawdown
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to calculate risk metrics: {str(e)}"
        )


@router.post("/distribution-fit", response_model=DistributionFitResponse)
async def test_distribution_fit(
    request: DistributionFitRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Test goodness-of-fit for a distribution

    Performs Kolmogorov-Smirnov test to assess whether samples
    come from the specified distribution.

    Requires authentication.
    """
    try:
        service = StochasticAnalyticsService()
        samples = np.array(request.samples)

        fit = service.kolmogorov_smirnov_test(samples, distribution=request.distribution)

        # Interpretation
        if fit.significant:
            interpretation = f"Samples do NOT appear to follow a {fit.distribution_type} distribution (reject null hypothesis, p={fit.p_value:.4f})"
        else:
            interpretation = f"Samples are consistent with a {fit.distribution_type} distribution (fail to reject null hypothesis, p={fit.p_value:.4f})"

        return DistributionFitResponse(
            distribution_type=fit.distribution_type,
            statistic=fit.statistic,
            p_value=fit.p_value,
            significant=fit.significant,
            interpretation=interpretation
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to test distribution fit: {str(e)}"
        )


@router.post("/compare-scenarios", response_model=ScenarioComparisonResponse)
async def compare_scenarios(
    request: ScenarioComparisonRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Compare multiple scenarios across a metric

    Provides comprehensive comparison including:
    - Mean, std, CV for each scenario
    - Confidence intervals
    - Risk metrics (VaR, CVaR)
    - Rankings (best/worst by various criteria)

    Requires authentication.
    """
    try:
        service = StochasticAnalyticsService()

        # Convert to numpy arrays
        scenarios = {
            name: np.array(samples)
            for name, samples in request.scenarios.items()
        }

        comparison = service.compare_scenarios(scenarios, metric=request.metric)

        return ScenarioComparisonResponse(
            scenarios={k: v for k, v in comparison.items() if k != 'rankings'},
            rankings=comparison['rankings']
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to compare scenarios: {str(e)}"
        )


# In-memory task store for Monte Carlo background tasks
# In production, use Redis or a database table
_monte_carlo_tasks: Dict[str, Dict[str, Any]] = {}


def _run_monte_carlo_task(task_id: str, game_id: int, num_runs: int, base_seed: int):
    """
    Background task that runs Monte Carlo simulation using ParallelMonteCarloRunner.

    Executes in background thread, updates task store with progress and results.
    """
    import logging
    mc_logger = logging.getLogger(__name__)

    try:
        _monte_carlo_tasks[task_id]["status"] = "running"

        from app.services.parallel_monte_carlo import (
            ParallelMonteCarloConfig, ParallelMonteCarloRunner,
        )

        config = ParallelMonteCarloConfig(
            game_id=game_id,
            num_runs=num_runs,
            base_seed=base_seed,
        )

        runner = ParallelMonteCarloRunner(config)

        def progress_callback(completed: int, total: int):
            _monte_carlo_tasks[task_id]["progress"] = completed / total

        results = runner.run(progress_callback=progress_callback)
        summary = runner.summarize_results(results)

        _monte_carlo_tasks[task_id]["status"] = "complete"
        _monte_carlo_tasks[task_id]["progress"] = 1.0
        _monte_carlo_tasks[task_id]["result"] = summary

        mc_logger.info(f"Monte Carlo task {task_id} completed: {summary.get('successful_runs', 0)}/{num_runs} runs")

    except Exception as e:
        mc_logger.error(f"Monte Carlo task {task_id} failed: {e}")
        _monte_carlo_tasks[task_id]["status"] = "failed"
        _monte_carlo_tasks[task_id]["result"] = {"error": str(e)}


@router.post("/monte-carlo/start", response_model=MonteCarloStatusResponse)
async def start_monte_carlo(
    request: MonteCarloRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user)
):
    """
    Start Monte Carlo simulation (background task)

    Runs multiple stochastic simulations using the real supply chain planning
    engine with stochastic sampling. Returns a task ID for polling progress.

    Requires authentication.
    """
    try:
        import uuid
        task_id = str(uuid.uuid4())

        # Initialize task tracking
        _monte_carlo_tasks[task_id] = {
            "status": "pending",
            "progress": 0.0,
            "result": None,
            "game_id": request.game_id,
            "num_runs": request.num_runs,
        }

        # Queue background task
        background_tasks.add_task(
            _run_monte_carlo_task,
            task_id,
            request.game_id,
            request.num_runs,
            request.base_seed,
        )

        return MonteCarloStatusResponse(
            task_id=task_id,
            status='pending',
            progress=0.0,
            result=None,
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start Monte Carlo simulation: {str(e)}"
        )


@router.get("/monte-carlo/{task_id}", response_model=MonteCarloStatusResponse)
async def get_monte_carlo_status(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get Monte Carlo simulation status

    Check progress and retrieve results for a Monte Carlo simulation task.

    Requires authentication.
    """
    task = _monte_carlo_tasks.get(task_id)

    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    return MonteCarloStatusResponse(
        task_id=task_id,
        status=task["status"],
        progress=task.get("progress", 0.0),
        result=task.get("result"),
    )
