"""
API endpoints for predictive analytics and explainable AI.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.predictive_analytics_service import (
    PredictiveAnalyticsService,
    ForecastResult,
    BullwhipPrediction,
    CostTrajectory
)

router = APIRouter()


# Request/Response Models
class ForecastRequest(BaseModel):
    """Request for demand forecasting."""
    scenario_id: int
    node_id: int
    horizon: int = Field(default=10, ge=1, le=52)
    confidence_level: float = Field(default=0.95, ge=0.5, le=0.99)


class ForecastResponse(BaseModel):
    """Forecast response."""
    forecasts: List[Dict[str, Any]]
    metadata: Dict[str, Any]


class BullwhipRequest(BaseModel):
    """Request for bullwhip prediction."""
    scenario_id: int


class BullwhipResponse(BaseModel):
    """Bullwhip prediction response."""
    predictions: List[Dict[str, Any]]
    summary: Dict[str, Any]


class CostTrajectoryRequest(BaseModel):
    """Request for cost trajectory."""
    scenario_id: int
    node_id: int
    horizon: int = Field(default=10, ge=1, le=52)


class CostTrajectoryResponse(BaseModel):
    """Cost trajectory response."""
    trajectory: Dict[str, Any]
    insights: List[str]


class ExplanationRequest(BaseModel):
    """Request for prediction explanation."""
    scenario_id: int
    node_id: int
    round_number: int


class ExplanationResponse(BaseModel):
    """Explanation response with SHAP values."""
    feature_importances: List[Dict[str, Any]]
    interpretation: str
    visualization_data: Optional[Dict[str, Any]] = None


class WhatIfScenario(BaseModel):
    """What-if scenario definition."""
    name: str
    changes: Dict[str, float]


class WhatIfRequest(BaseModel):
    """Request for what-if analysis."""
    scenario_id: int
    node_id: int
    scenarios: List[WhatIfScenario]


class WhatIfResponse(BaseModel):
    """What-if analysis response."""
    baseline: Dict[str, Any]
    scenarios: List[Dict[str, Any]]
    recommendations: List[str]


class InsightsReportRequest(BaseModel):
    """Request for comprehensive insights report."""
    scenario_id: int


class InsightsReportResponse(BaseModel):
    """Comprehensive insights report."""
    scenario_id: int
    generated_at: str
    demand_forecasts: Dict[str, List[Dict[str, Any]]]
    bullwhip_predictions: List[Dict[str, Any]]
    cost_trajectories: Dict[str, Any]
    risk_assessment: Dict[str, Any]
    recommendations: List[str]


# Endpoints
@router.post("/forecast/demand", response_model=ForecastResponse)
async def forecast_demand(
    request: ForecastRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Forecast demand for a node over specified horizon.

    Returns forecasts with confidence bounds.
    """
    service = PredictiveAnalyticsService(db)

    try:
        forecasts = await service.forecast_demand(
            scenario_id=request.scenario_id,
            node_id=request.node_id,
            horizon=request.horizon,
            confidence_level=request.confidence_level
        )

        # Convert dataclasses to dicts
        forecast_dicts = []
        for f in forecasts:
            forecast_dicts.append({
                "timestep": f.timestep,
                "value": f.value,
                "lower_bound": f.lower_bound,
                "upper_bound": f.upper_bound,
                "confidence": f.confidence
            })

        metadata = {
            "horizon": request.horizon,
            "confidence_level": request.confidence_level,
            "num_forecasts": len(forecasts)
        }

        return ForecastResponse(
            forecasts=forecast_dicts,
            metadata=metadata
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Forecasting failed: {str(e)}"
        )


@router.post("/predict/bullwhip", response_model=BullwhipResponse)
async def predict_bullwhip(
    request: BullwhipRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Predict bullwhip effect for all sites in a scenario.

    Returns risk levels and contributing factors.
    """
    service = PredictiveAnalyticsService(db)

    try:
        predictions = await service.predict_bullwhip(scenario_id=request.scenario_id)

        # Convert to dicts
        prediction_dicts = []
        for p in predictions:
            prediction_dicts.append({
                "node_id": p.node_id,
                "node_role": p.node_role,
                "current_ratio": p.current_ratio,
                "predicted_ratio": p.predicted_ratio,
                "risk_level": p.risk_level,
                "contributing_factors": p.contributing_factors
            })

        # Calculate summary statistics
        if predictions:
            avg_ratio = sum(p.predicted_ratio for p in predictions) / len(predictions)
            high_risk_count = sum(1 for p in predictions if p.risk_level == "high")
            medium_risk_count = sum(1 for p in predictions if p.risk_level == "medium")
        else:
            avg_ratio = 0
            high_risk_count = 0
            medium_risk_count = 0

        summary = {
            "average_predicted_ratio": avg_ratio,
            "high_risk_nodes": high_risk_count,
            "medium_risk_nodes": medium_risk_count,
            "overall_risk": "high" if high_risk_count > 0 else "medium" if medium_risk_count > 0 else "low"
        }

        return BullwhipResponse(
            predictions=prediction_dicts,
            summary=summary
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Bullwhip prediction failed: {str(e)}"
        )


@router.post("/forecast/cost-trajectory", response_model=CostTrajectoryResponse)
async def forecast_cost_trajectory(
    request: CostTrajectoryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Forecast cost trajectory for a node with risk scenarios.
    """
    service = PredictiveAnalyticsService(db)

    try:
        trajectory = await service.forecast_cost_trajectory(
            scenario_id=request.scenario_id,
            node_id=request.node_id,
            horizon=request.horizon
        )

        # Convert to dict
        trajectory_dict = {
            "node_id": trajectory.node_id,
            "node_role": trajectory.node_role,
            "current_cost": trajectory.current_cost,
            "forecasted_costs": trajectory.forecasted_costs,
            "expected_total": trajectory.expected_total,
            "risk_scenarios": trajectory.risk_scenarios
        }

        # Generate insights
        insights = []
        if trajectory.expected_total > trajectory.current_cost * 1.3:
            insights.append("Cost is expected to increase by over 30%. Review ordering policy.")
        elif trajectory.expected_total > trajectory.current_cost * 1.1:
            insights.append("Cost is expected to increase moderately. Monitor inventory levels.")
        else:
            insights.append("Cost trajectory is stable.")

        worst_case = trajectory.risk_scenarios["worst"][-1]
        if worst_case > trajectory.current_cost * 1.5:
            insights.append("Worst-case scenario shows significant risk. Consider safety stock adjustments.")

        return CostTrajectoryResponse(
            trajectory=trajectory_dict,
            insights=insights
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cost trajectory forecast failed: {str(e)}"
        )


@router.post("/explain/prediction", response_model=ExplanationResponse)
async def explain_prediction(
    request: ExplanationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Explain a prediction using SHAP values.

    Provides feature importance and interpretation.
    """
    service = PredictiveAnalyticsService(db)

    try:
        explanation = await service.explain_prediction(
            scenario_id=request.scenario_id,
            node_id=request.node_id,
            round_number=request.round_number
        )

        if "error" in explanation:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=explanation["message"]
            )

        return ExplanationResponse(
            feature_importances=explanation.get("feature_importances", []),
            interpretation=explanation.get("interpretation", "No interpretation available"),
            visualization_data=explanation.get("visualization_data")
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Explanation failed: {str(e)}"
        )


@router.post("/analyze/what-if", response_model=WhatIfResponse)
async def analyze_what_if(
    request: WhatIfRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Analyze what-if scenarios.

    Compare baseline against alternative scenarios.
    """
    service = PredictiveAnalyticsService(db)

    try:
        # Convert scenarios to dicts
        scenarios_list = [
            {
                "name": s.name,
                "changes": s.changes
            }
            for s in request.scenarios
        ]

        analysis = await service.analyze_what_if(
            scenario_id=request.scenario_id,
            node_id=request.node_id,
            scenarios=scenarios_list
        )

        # Generate recommendations
        recommendations = []
        baseline_cost = analysis["baseline"]["predicted_cost"]

        for scenario_result in analysis["scenarios"]:
            delta_cost = scenario_result["delta_vs_baseline"]["cost"]
            if delta_cost < -baseline_cost * 0.1:
                recommendations.append(
                    f"Scenario '{scenario_result['name']}' could reduce costs by "
                    f"{abs(delta_cost):.2f} ({abs(delta_cost)/baseline_cost*100:.1f}%)"
                )
            elif delta_cost > baseline_cost * 0.1:
                recommendations.append(
                    f"Scenario '{scenario_result['name']}' would increase costs by "
                    f"{delta_cost:.2f} ({delta_cost/baseline_cost*100:.1f}%)"
                )

        if not recommendations:
            recommendations.append("All scenarios show similar cost outcomes to baseline.")

        return WhatIfResponse(
            baseline=analysis["baseline"],
            scenarios=analysis["scenarios"],
            recommendations=recommendations
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"What-if analysis failed: {str(e)}"
        )


@router.post("/insights/report", response_model=InsightsReportResponse)
async def generate_insights_report(
    request: InsightsReportRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate comprehensive insights report for a scenario.

    Includes demand forecasts, bullwhip predictions, cost trajectories,
    risk assessment, and recommendations.
    """
    service = PredictiveAnalyticsService(db)

    try:
        report = await service.generate_insights_report(scenario_id=request.scenario_id)

        return InsightsReportResponse(**report)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Report generation failed: {str(e)}"
        )


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "predictive-analytics",
        "version": "1.0.0"
    }
