"""
Visibility Dashboard API Endpoints
Phase 7 Sprint 4 - Feature 3: Supply Chain Visibility

Provides REST API for:
- Supply chain health monitoring
- Bottleneck detection
- Bullwhip effect measurement
- Visibility sharing permissions
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.visibility_service import get_visibility_service

router = APIRouter(prefix="/visibility", tags=["visibility"])


# =============================================================================
# REQUEST/RESPONSE SCHEMAS
# =============================================================================

class HealthScoreResponse(BaseModel):
    """Response containing supply chain health score."""
    health_score: float = Field(..., ge=0, le=100, description="Overall health score (0-100)")
    components: dict = Field(..., description="Component scores")
    status: str = Field(..., description="Status: excellent, good, moderate, poor, critical")
    insights: List[str] = Field(..., description="Actionable insights")
    round_number: int = Field(..., description="Round analyzed")

    class Config:
        from_attributes = True


class BottleneckMetrics(BaseModel):
    """Bottleneck metrics."""
    backlog: int
    inventory: int
    service_level: float


class Bottleneck(BaseModel):
    """Bottleneck information."""
    role: str
    severity: str
    metrics: BottleneckMetrics
    impact: str
    recommendation: str


class BottlenecksResponse(BaseModel):
    """Response containing bottleneck detection results."""
    bottlenecks: List[Bottleneck]
    total_bottlenecks: int
    supply_chain_flow: str = Field(..., description="smooth, restricted, or congested")
    round_number: int


class RoleMetrics(BaseModel):
    """Order variance metrics per role."""
    variance: float
    cv: float
    avg_order: float


class BullwhipResponse(BaseModel):
    """Response containing bullwhip effect analysis."""
    severity: str = Field(..., description="low, moderate, high, severe")
    amplification_ratio: float = Field(..., description="Demand variance amplification")
    by_role: dict = Field(..., description="Metrics per role")
    insights: List[str]


class VisibilityPermissionsRequest(BaseModel):
    """Request to set visibility sharing permissions."""
    share_inventory: bool = Field(False, description="Share inventory levels")
    share_backlog: bool = Field(False, description="Share backlog levels")
    share_orders: bool = Field(False, description="Share order quantities")


class VisibilityPermissionsResponse(BaseModel):
    """Response containing visibility permissions."""
    player_id: int
    permissions: dict
    updated_at: str


class PlayerVisibilityPermissions(BaseModel):
    """Player with visibility permissions."""
    player_id: int
    role: str
    permissions: dict


class AllVisibilityPermissionsResponse(BaseModel):
    """Response containing all player permissions."""
    players: List[PlayerVisibilityPermissions]


class SnapshotResponse(BaseModel):
    """Response after creating snapshot."""
    snapshot_id: int
    created_at: str


class HistoricalSnapshot(BaseModel):
    """Historical visibility snapshot."""
    id: int
    round_number: int
    health_score: float
    snapshot_data: str
    created_at: Optional[str]


class SnapshotsListResponse(BaseModel):
    """Response containing list of snapshots."""
    snapshots: List[HistoricalSnapshot]
    total_count: int


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.get("/scenarios/{scenario_id}/health", response_model=HealthScoreResponse)
async def get_supply_chain_health(
    scenario_id: int,
    round_number: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get supply chain health score.

    Calculates comprehensive health score (0-100) based on:
    - **Inventory balance** (30%): Optimal inventory levels across nodes
    - **Service level** (25%): Customer demand fulfillment
    - **Cost efficiency** (20%): Total supply chain costs
    - **Order stability** (15%): Bullwhip effect severity
    - **Backlog pressure** (10%): Unfulfilled orders

    **Health Status**:
    - `excellent`: 80-100 (green)
    - `good`: 65-79 (light green)
    - `moderate`: 50-64 (yellow)
    - `poor`: 35-49 (orange)
    - `critical`: 0-34 (red)

    **Query Parameters**:
    - `round_number`: Specific round to analyze (default: latest round)

    **Example Response**:
    ```json
    {
      "health_score": 72.5,
      "components": {
        "inventory_balance": 68.0,
        "service_level": 85.0,
        "cost_efficiency": 70.0,
        "order_stability": 60.0,
        "backlog_pressure": 80.0
      },
      "status": "good",
      "insights": [
        "✅ Supply chain is operating well",
        "📊 High order volatility detected"
      ],
      "round_number": 15
    }
    ```
    """
    try:
        visibility_service = get_visibility_service(db)

        health = await visibility_service.calculate_supply_chain_health(
            scenario_id=scenario_id,
            round_number=round_number
        )

        return HealthScoreResponse(**health)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate health score: {str(e)}"
        )


@router.get("/scenarios/{scenario_id}/bottlenecks", response_model=BottlenecksResponse)
async def detect_bottlenecks(
    scenario_id: int,
    round_number: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Detect supply chain bottlenecks.

    Identifies nodes causing flow restrictions based on:
    - High backlog (>20 units)
    - Low inventory (<10 units)
    - Poor service level (<0.7)

    **Severity Levels**:
    - `critical`: Backlog >40 units
    - `high`: Backlog 30-40 units
    - `moderate`: Backlog 20-30 units or low service

    **Supply Chain Flow Status**:
    - `smooth`: No bottlenecks
    - `restricted`: 1 bottleneck
    - `congested`: 2+ bottlenecks

    **Example Response**:
    ```json
    {
      "bottlenecks": [
        {
          "role": "WHOLESALER",
          "severity": "high",
          "metrics": {
            "backlog": 35,
            "inventory": 5,
            "service_level": 0.62
          },
          "impact": "Blocking 35 units from downstream",
          "recommendation": "Increase order quantity by 70%"
        }
      ],
      "total_bottlenecks": 1,
      "supply_chain_flow": "restricted",
      "round_number": 15
    }
    ```
    """
    try:
        visibility_service = get_visibility_service(db)

        bottlenecks = await visibility_service.detect_bottlenecks(
            scenario_id=scenario_id,
            round_number=round_number
        )

        return BottlenecksResponse(**bottlenecks)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to detect bottlenecks: {str(e)}"
        )


@router.get("/scenarios/{scenario_id}/bullwhip", response_model=BullwhipResponse)
async def measure_bullwhip_effect(
    scenario_id: int,
    window_size: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Measure bullwhip effect severity.

    The **bullwhip effect** is demand variance amplification as orders move upstream.

    **Measurement**:
    - Calculates coefficient of variation (CV) for each role's orders
    - Computes amplification ratio: upstream CV / downstream CV
    - Higher ratio = worse bullwhip effect

    **Severity Levels**:
    - `low`: Amplification ≤1.2 (good coordination)
    - `moderate`: Amplification 1.2-1.8
    - `high`: Amplification 1.8-2.5
    - `severe`: Amplification >2.5 (poor information sharing)

    **Query Parameters**:
    - `window_size`: Number of recent rounds to analyze (default: 10)

    **Example Response**:
    ```json
    {
      "severity": "moderate",
      "amplification_ratio": 1.6,
      "by_role": {
        "RETAILER": {"variance": 12.5, "cv": 0.25, "avg_order": 50},
        "WHOLESALER": {"variance": 28.7, "cv": 0.40, "avg_order": 52},
        "DISTRIBUTOR": {"variance": 45.2, "cv": 0.48, "avg_order": 55},
        "FACTORY": {"variance": 62.8, "cv": 0.52, "avg_order": 58}
      },
      "insights": [
        "⚠️ Moderate bullwhip effect detected",
        "📊 FACTORY has high order volatility (CV=0.52)"
      ]
    }
    ```
    """
    try:
        visibility_service = get_visibility_service(db)

        bullwhip = await visibility_service.measure_bullwhip_severity(
            scenario_id=scenario_id,
            window_size=window_size
        )

        return BullwhipResponse(**bullwhip)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to measure bullwhip effect: {str(e)}"
        )


@router.post("/scenarios/{scenario_id}/permissions", response_model=VisibilityPermissionsResponse)
async def set_visibility_permissions(
    scenario_id: int,
    request: VisibilityPermissionsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Set visibility sharing permissions.

    Players can opt-in to share their metrics with other players:
    - **Inventory levels**: Current stock on hand
    - **Backlog levels**: Unfulfilled customer orders
    - **Order quantities**: Orders placed to suppliers

    **Benefits of Sharing**:
    - Reduces bullwhip effect through information transparency
    - Enables better coordination and planning
    - Improves overall supply chain performance

    **Privacy**:
    - Sharing is opt-in and granular per metric type
    - Players control what they share
    - Can be changed at any time

    **Example Request**:
    ```json
    {
      "share_inventory": true,
      "share_backlog": false,
      "share_orders": true
    }
    ```

    **Example Response**:
    ```json
    {
      "player_id": 123,
      "permissions": {
        "share_inventory": true,
        "share_backlog": false,
        "share_orders": true
      },
      "updated_at": "2026-01-14T12:00:00"
    }
    ```
    """
    try:
        visibility_service = get_visibility_service(db)

        # TODO: Map current_user to player_id properly
        player_id = current_user.id

        result = await visibility_service.set_visibility_permission(
            scenario_id=scenario_id,
            player_id=player_id,
            share_inventory=request.share_inventory,
            share_backlog=request.share_backlog,
            share_orders=request.share_orders
        )

        return VisibilityPermissionsResponse(**result)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to set permissions: {str(e)}"
        )


@router.get("/scenarios/{scenario_id}/permissions", response_model=AllVisibilityPermissionsResponse)
async def get_visibility_permissions(
    scenario_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get visibility permissions for all participants.

    Returns sharing preferences for each participant in the scenario.
    Only shows participants who have opted in to share at least one metric.

    **Use Cases**:
    - Display "shared metrics" dashboard
    - Show which players are participating in information sharing
    - Enable visibility-based features

    **Example Response**:
    ```json
    {
      "players": [
        {
          "player_id": 123,
          "role": "RETAILER",
          "permissions": {
            "share_inventory": true,
            "share_backlog": false,
            "share_orders": true
          }
        },
        {
          "player_id": 124,
          "role": "WHOLESALER",
          "permissions": {
            "share_inventory": false,
            "share_backlog": false,
            "share_orders": false
          }
        }
      ]
    }
    ```
    """
    try:
        visibility_service = get_visibility_service(db)

        result = await visibility_service.get_visibility_permissions(scenario_id)

        return AllVisibilityPermissionsResponse(**result)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get permissions: {str(e)}"
        )


@router.post("/scenarios/{scenario_id}/snapshots", response_model=SnapshotResponse)
async def create_visibility_snapshot(
    scenario_id: int,
    round_number: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create visibility snapshot for a round.

    Captures current supply chain state including:
    - Health score
    - Bottleneck count
    - Bullwhip severity
    - Shared player metrics (if opted in)

    Snapshots enable:
    - Historical trend analysis
    - Performance tracking over time
    - Identifying when problems started

    **Typically called automatically** after each round completes.

    **Example Response**:
    ```json
    {
      "snapshot_id": 456,
      "created_at": "2026-01-14T12:00:00"
    }
    ```
    """
    try:
        visibility_service = get_visibility_service(db)

        result = await visibility_service.create_visibility_snapshot(
            scenario_id=scenario_id,
            round_number=round_number
        )

        return SnapshotResponse(**result)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create snapshot: {str(e)}"
        )


@router.get("/scenarios/{scenario_id}/snapshots", response_model=SnapshotsListResponse)
async def get_visibility_snapshots(
    scenario_id: int,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get historical visibility snapshots.

    Returns recent snapshots in reverse chronological order.
    Use for trend charts and historical analysis.

    **Query Parameters**:
    - `limit`: Maximum snapshots to return (default: 20, max: 100)

    **Example Response**:
    ```json
    {
      "snapshots": [
        {
          "id": 456,
          "round_number": 15,
          "health_score": 72.5,
          "snapshot_data": "{...}",
          "created_at": "2026-01-14T12:00:00"
        },
        {
          "id": 455,
          "round_number": 14,
          "health_score": 68.3,
          "snapshot_data": "{...}",
          "created_at": "2026-01-14T11:55:00"
        }
      ],
      "total_count": 2
    }
    ```
    """
    if limit > 100:
        limit = 100

    try:
        visibility_service = get_visibility_service(db)

        snapshots = await visibility_service.get_visibility_snapshots(
            scenario_id=scenario_id,
            limit=limit
        )

        return SnapshotsListResponse(
            snapshots=[HistoricalSnapshot(**s) for s in snapshots],
            total_count=len(snapshots)
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get snapshots: {str(e)}"
        )
