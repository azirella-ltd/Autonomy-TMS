"""
Pattern Analysis API Endpoints
Phase 7 Sprint 4 - Feature 2

Tracks suggestion outcomes and analyzes scenario_user patterns.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.pattern_analysis_service import get_pattern_analysis_service

router = APIRouter(prefix="/analytics", tags=["pattern-analysis"])


# =============================================================================
# REQUEST/RESPONSE SCHEMAS
# =============================================================================

class SuggestionOutcomeRequest(BaseModel):
    """Request to track suggestion outcome."""
    suggestion_id: int
    accepted: bool
    actual_order_placed: int
    modified_quantity: Optional[int] = None


class PerformanceScoreRequest(BaseModel):
    """Request to calculate performance score."""
    outcome_id: int
    inventory_cost: float
    backlog_cost: float
    service_level: float = Field(..., ge=0.0, le=1.0)


class ScenarioUserPatternsResponse(BaseModel):
    """ScenarioUser pattern analysis response."""
    scenario_user_id: int
    scenario_id: int
    pattern_type: str
    acceptance_rate: float
    avg_modification: float
    preferred_priorities: List[str]
    total_suggestions: int
    total_accepted: int
    insights: List[str]
    risk_tolerance: str
    last_analyzed: str


class AIEffectivenessResponse(BaseModel):
    """AI effectiveness metrics response."""
    scenario_id: int
    total_suggestions: int
    acceptance_rate: float
    avg_confidence_accepted: float
    avg_confidence_rejected: float
    performance_comparison: dict
    confidence_calibration: dict
    insights: List[str]


class SuggestionHistoryItem(BaseModel):
    """Single suggestion history record."""
    id: int
    round: int
    agent_name: str
    suggested_quantity: int
    confidence: float
    accepted: bool
    actual_quantity: int
    modified: bool
    performance_score: Optional[float]
    outcome: Optional[dict]
    created_at: str


class SuggestionHistoryResponse(BaseModel):
    """Suggestion history response."""
    suggestions: List[SuggestionHistoryItem]
    total_count: int
    scenario_id: int


class AcceptanceTrendsResponse(BaseModel):
    """Acceptance rate trends response."""
    scenario_user_id: int
    scenario_id: int
    window_size: int
    current_acceptance_rate: float
    trend: str
    rolling_averages: List[dict]
    confidence_correlation: dict
    insights: List[str]


class InsightsResponse(BaseModel):
    """Generated insights response."""
    scenario_id: int
    scenario_user_id: Optional[int]
    insights: List[str]


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/scenarios/{scenario_id}/track-outcome")
async def track_suggestion_outcome(
    scenario_id: int,
    request: SuggestionOutcomeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Track the outcome of an AI suggestion.

    Records whether the scenario_user accepted, rejected, or modified
    the suggestion, and what they actually ordered.

    This data feeds into pattern analysis and effectiveness metrics.

    **Triggers**:
    - Automatically updates scenario_user_patterns table via database trigger
    - Increments total_suggestions and total_accepted counters
    - Recalculates acceptance_rate
    """
    try:
        service = get_pattern_analysis_service(db)

        outcome = await service.track_suggestion_outcome(
            suggestion_id=request.suggestion_id,
            accepted=request.accepted,
            actual_order_placed=request.actual_order_placed,
            modified_quantity=request.modified_quantity,
        )

        return {"status": "success", "outcome": outcome}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to track outcome: {str(e)}",
        )


@router.post("/outcomes/{outcome_id}/score")
async def calculate_performance_score(
    outcome_id: int,
    request: PerformanceScoreRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Calculate performance score for a suggestion outcome.

    Called after round completes to evaluate how well the
    suggestion (or scenario_user's modification) performed.

    **Score Formula**:
    - 40% cost efficiency (lower costs = better)
    - 60% service level (higher fulfillment = better)
    - Range: 0-100
    """
    try:
        service = get_pattern_analysis_service(db)

        score = await service.calculate_performance_score(
            outcome_id=outcome_id,
            inventory_cost=request.inventory_cost,
            backlog_cost=request.backlog_cost,
            service_level=request.service_level,
        )

        return {"outcome_id": outcome_id, "performance_score": score}

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate score: {str(e)}",
        )


@router.get("/scenarios/{scenario_id}/scenario_users/{scenario_user_id}/patterns", response_model=ScenarioUserPatternsResponse)
async def get_scenario_user_patterns(
    scenario_id: int,
    scenario_user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get detected patterns for a scenario_user.

    Analyzes scenario_user behavior to identify:
    - **Pattern Type**: conservative, aggressive, balanced, reactive
    - **Acceptance Rate**: % of suggestions accepted
    - **Modification Behavior**: How much scenario_user adjusts recommendations
    - **Risk Tolerance**: low, moderate, high
    - **Preferences**: Preferred priorities and strategies

    **Pattern Types**:
    - **Conservative**: Accepts most suggestions, small modifications
    - **Aggressive**: Frequently rejects or heavily modifies
    - **Balanced**: Mix of acceptance and thoughtful adjustments
    - **Reactive**: Behavior varies based on scenario state
    """
    try:
        service = get_pattern_analysis_service(db)

        patterns = await service.get_scenario_user_patterns(scenario_user_id, scenario_id)

        return ScenarioUserPatternsResponse(**patterns)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get patterns: {str(e)}",
        )


@router.get("/scenarios/{scenario_id}/ai-effectiveness", response_model=AIEffectivenessResponse)
async def get_ai_effectiveness(
    scenario_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Measure AI suggestion effectiveness for a scenario.

    Compares outcomes when scenario_users:
    - Accept AI suggestions vs reject them
    - Follow recommendations vs modify them

    **Metrics Provided**:
    - Acceptance rate by confidence level
    - Cost savings from following AI
    - Service level improvement
    - Confidence calibration (how well confidence predicts success)

    **Insights**:
    - "Following AI saves $X per round"
    - "High-confidence suggestions perform Y% better"
    - "AI is well-calibrated" (confidence matches accuracy)
    """
    try:
        service = get_pattern_analysis_service(db)

        effectiveness = await service.get_ai_effectiveness(scenario_id)

        return AIEffectivenessResponse(**effectiveness)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get effectiveness: {str(e)}",
        )


@router.get("/scenarios/{scenario_id}/suggestion-history", response_model=SuggestionHistoryResponse)
async def get_suggestion_history(
    scenario_id: int,
    scenario_user_id: Optional[int] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get suggestion history with outcomes.

    Returns historical suggestions with:
    - Suggested quantity and confidence
    - Whether accepted/rejected/modified
    - Actual quantity ordered
    - Performance score (if available)
    - Round outcomes (inventory, backlog, costs)

    **Use Cases**:
    - Review past suggestions
    - Analyze what worked vs what didn't
    - Learn from historical patterns
    - Export for detailed analysis
    """
    if limit > 200:
        limit = 200

    try:
        service = get_pattern_analysis_service(db)

        history = await service.get_suggestion_history(
            scenario_id=scenario_id,
            scenario_user_id=scenario_user_id,
            limit=limit,
        )

        return SuggestionHistoryResponse(
            suggestions=[SuggestionHistoryItem(**item) for item in history],
            total_count=len(history),
            scenario_id=scenario_id,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get history: {str(e)}",
        )


@router.get("/scenarios/{scenario_id}/scenario_users/{scenario_user_id}/trends", response_model=AcceptanceTrendsResponse)
async def get_acceptance_trends(
    scenario_id: int,
    scenario_user_id: int,
    window: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get acceptance rate trends over time.

    Tracks how scenario_user's acceptance behavior changes:
    - Rolling window averages
    - Trend direction (increasing, decreasing, stable)
    - Confidence correlation
    - Learning curve insights

    **Parameters**:
    - `window`: Rolling window size for trend calculation (default: 10)

    **Insights**:
    - "Acceptance rate improving over time"
    - "Strong correlation between confidence and acceptance"
    - "ScenarioUser learning to trust AI"
    """
    try:
        service = get_pattern_analysis_service(db)

        trends = await service.get_acceptance_trends(
            scenario_id=scenario_id,
            scenario_user_id=scenario_user_id,
            window=window,
        )

        return AcceptanceTrendsResponse(**trends)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get trends: {str(e)}",
        )


@router.get("/scenarios/{scenario_id}/insights", response_model=InsightsResponse)
async def get_insights(
    scenario_id: int,
    scenario_user_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Generate actionable insights from pattern analysis.

    Provides human-readable insights based on:
    - ScenarioUser patterns
    - AI effectiveness
    - Acceptance trends
    - Performance comparisons

    **Example Insights**:
    - "You trust AI recommendations highly (85% acceptance rate)"
    - "Following AI saves $5.70 per round on average"
    - "Your conservative approach minimizes risk but may miss opportunities"
    - "AI suggestions with >80% confidence perform 12% better"

    **Parameters**:
    - `scenario_user_id`: Optional - if provided, includes scenario_user-specific insights
    """
    try:
        service = get_pattern_analysis_service(db)

        insights = await service.generate_insights(
            scenario_id=scenario_id,
            scenario_user_id=scenario_user_id,
        )

        return InsightsResponse(
            scenario_id=scenario_id,
            scenario_user_id=scenario_user_id,
            insights=insights,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate insights: {str(e)}",
        )
