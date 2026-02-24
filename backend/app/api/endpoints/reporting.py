"""
Reporting API Endpoints

Provides endpoints for scenario reports, analytics, exports, and trend analysis.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
import io

from app.db.session import get_db
from app.models.user import User
from app.api.deps import get_current_user
from app.services.reporting_service import get_reporting_service
from pydantic import BaseModel, Field


router = APIRouter()


# Schemas
class ScenarioReportResponse(BaseModel):
    """Scenario report response schema."""
    scenario_id: int
    generated_at: str
    overview: dict
    player_performance: List[dict]
    key_insights: List[str]
    recommendations: List[str]
    charts_data: dict

    model_config = {"from_attributes": True}


class TrendAnalysisResponse(BaseModel):
    """Trend analysis response schema."""
    scenario_user_id: int
    metric: str
    lookback: int
    scenarios_analyzed: int
    data_points: List[dict]
    statistics: dict
    insights: List[str]

    model_config = {"from_attributes": True}


class ScenarioComparisonResponse(BaseModel):
    """Scenario comparison response schema."""
    scenarios_compared: int
    metrics: List[str]
    comparisons: List[dict]
    best_performers: dict

    model_config = {"from_attributes": True}


# Endpoints

@router.get("/scenarios/{scenario_id}", response_model=ScenarioReportResponse)
async def get_scenario_report(
    scenario_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get comprehensive scenario report.

    Returns detailed analytics including:
    - Scenario overview (cost, service level, bullwhip effect)
    - ScenarioUser performance comparison
    - Key insights
    - Actionable recommendations
    - Chart data for visualization

    **Requires authentication**
    """
    service = get_reporting_service(db)

    try:
        report = await service.generate_scenario_report(scenario_id)
        return report
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate report: {str(e)}")


@router.get("/scenarios/{scenario_id}/export")
async def export_scenario_data(
    scenario_id: int,
    format: str = Query('csv', pattern='^(csv|json|excel)$'),
    include_rounds: bool = Query(True, description="Include round-by-round data"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Export scenario data in specified format.

    Supported formats:
    - **csv**: Comma-separated values
    - **json**: JSON format with full report
    - **excel**: Excel spreadsheet (requires openpyxl)

    Returns file for download.

    **Requires authentication**
    """
    service = get_reporting_service(db)

    try:
        file_content = await service.export_scenario_data(
            scenario_id=scenario_id,
            format=format,
            include_rounds=include_rounds
        )

        # Determine content type and filename
        if format == 'csv':
            media_type = 'text/csv'
            filename = f'scenario_{scenario_id}_report.csv'
        elif format == 'json':
            media_type = 'application/json'
            filename = f'scenario_{scenario_id}_report.json'
        elif format == 'excel':
            media_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            filename = f'scenario_{scenario_id}_report.xlsx'
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")

        # Return as streaming response
        return StreamingResponse(
            io.BytesIO(file_content),
            media_type=media_type,
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"'
            }
        )

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.get("/trends/{scenario_user_id}", response_model=TrendAnalysisResponse)
async def get_player_trends(
    scenario_user_id: int,
    metric: str = Query('cost', pattern='^(cost|service_level|inventory|bullwhip)$'),
    lookback: int = Query(10, ge=1, le=50, description="Number of recent scenarios to analyze"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get scenario_user performance trends over recent scenarios.

    Analyzes scenario_user's historical performance for specified metric:
    - **cost**: Total scenario cost trend
    - **service_level**: Service level performance
    - **inventory**: Average inventory levels
    - **bullwhip**: Order variability (bullwhip effect)

    Returns:
    - Data points for each scenario
    - Statistical analysis (mean, std, min, max)
    - Trend direction (improving, declining, stable)
    - Insights and recommendations

    **Requires authentication**
    """
    service = get_reporting_service(db)

    try:
        trends = await service.get_trend_analysis(
            scenario_user_id=scenario_user_id,
            metric=metric,
            lookback=lookback
        )
        return trends
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Trend analysis failed: {str(e)}")


@router.get("/comparisons", response_model=ScenarioComparisonResponse)
async def compare_scenarios(
    scenario_ids: List[int] = Query(..., description="List of scenario IDs to compare (2-10 scenarios)"),
    metrics: Optional[List[str]] = Query(
        None,
        description="Metrics to compare (default: all)"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Compare performance across multiple scenarios.

    Provides side-by-side comparison of:
    - Total cost
    - Service level
    - Average inventory
    - Bullwhip effect
    - Custom metrics

    Returns:
    - Comparison table with all metrics
    - Best performer identification
    - Relative performance analysis

    **Requires authentication**

    **Limitations**: 2-10 scenarios maximum
    """
    # Validate input
    if len(scenario_ids) < 2:
        raise HTTPException(status_code=400, detail="At least 2 scenarios required for comparison")
    if len(scenario_ids) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 scenarios allowed for comparison")

    service = get_reporting_service(db)

    try:
        comparison = await service.compare_scenarios(
            scenario_ids=scenario_ids,
            metrics=metrics
        )
        return comparison
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")


@router.get("/analytics/summary/{scenario_user_id}")
async def get_player_analytics_summary(
    scenario_user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get quick analytics summary for a scenario_user.

    Returns key metrics across all scenarios in a single call.
    Useful for dashboard widgets and quick overviews.

    **Requires authentication**
    """
    service = get_reporting_service(db)

    try:
        # Get trends for multiple metrics
        cost_trends = await service.get_trend_analysis(scenario_user_id, 'cost', 5)
        service_trends = await service.get_trend_analysis(scenario_user_id, 'service_level', 5)

        return {
            "scenario_user_id": scenario_user_id,
            "cost": {
                "recent_avg": cost_trends["statistics"].get("mean"),
                "trend": cost_trends["statistics"].get("trend"),
                "scenarios_analyzed": cost_trends["scenarios_analyzed"]
            },
            "service_level": {
                "recent_avg": service_trends["statistics"].get("mean"),
                "trend": service_trends["statistics"].get("trend"),
                "scenarios_analyzed": service_trends["scenarios_analyzed"]
            },
            "quick_insights": cost_trends["insights"][:2] + service_trends["insights"][:2]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analytics summary failed: {str(e)}")


@router.get("/health")
async def reporting_health_check():
    """
    Health check endpoint for reporting service.

    Returns service status and availability.
    """
    return {
        "service": "reporting",
        "status": "healthy",
        "features": [
            "scenario_reports",
            "data_export",
            "trend_analysis",
            "scenario_comparison"
        ]
    }
