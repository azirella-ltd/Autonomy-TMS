"""
Global Optimization API Endpoint
Phase 7 Sprint 4 - Feature 5: Cross-Agent Optimization

Provides REST API for global supply chain optimization recommendations.
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.services.llm_suggestion_service import generate_global_optimization

router = APIRouter(prefix="/optimization", tags=["optimization"])


# =============================================================================
# REQUEST/RESPONSE SCHEMAS
# =============================================================================

class GlobalOptimizationRequest(BaseModel):
    """Request for global optimization."""
    focus_nodes: Optional[List[str]] = Field(
        None,
        description="Optional list of roles to focus on (e.g., ['RETAILER', 'WHOLESALER'])"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "focus_nodes": ["RETAILER", "WHOLESALER"]
            }
        }


class NodeRecommendation(BaseModel):
    """Recommendation for a single node."""
    order: int
    reasoning: str


class ExpectedImpact(BaseModel):
    """Expected impact of optimization."""
    cost_reduction: float
    service_improvement: float
    bullwhip_reduction: float


class GlobalOptimizationResponse(BaseModel):
    """Response containing global optimization recommendations."""
    optimization_type: str = Field(..., description="coordination, rebalancing, or stabilization")
    recommendations: dict = Field(..., description="Per-node recommendations")
    expected_impact: ExpectedImpact
    coordination_strategy: str
    confidence: float
    note: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "optimization_type": "coordination",
                "recommendations": {
                    "RETAILER": {"order": 45, "reasoning": "Reduce order to stabilize supply chain"},
                    "WHOLESALER": {"order": 52, "reasoning": "Increase slightly to buffer upstream"},
                    "DISTRIBUTOR": {"order": 50, "reasoning": "Maintain current level"},
                    "FACTORY": {"order": 48, "reasoning": "Reduce production to match demand"}
                },
                "expected_impact": {
                    "cost_reduction": 25,
                    "service_improvement": 0.15,
                    "bullwhip_reduction": 0.30
                },
                "coordination_strategy": "Gradual stabilization to reduce bullwhip effect while maintaining service levels",
                "confidence": 0.75
            }
        }


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/scenarios/{scenario_id}/global", response_model=GlobalOptimizationResponse)
async def get_global_optimization(
    scenario_id: int,
    request: GlobalOptimizationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get global optimization recommendations for all nodes.

    **Phase 7 Sprint 4 - Feature 5: Cross-Agent Optimization**

    Unlike single-node suggestions, this analyzes the entire supply chain
    and provides coordinated recommendations for multiple nodes simultaneously.

    **Features**:
    - Multi-node analysis considering system-wide effects
    - Coordination strategies to reduce bullwhip effect
    - Trade-off analysis between individual and system-wide goals
    - Expected impact simulation

    **Optimization Types**:
    - `coordination`: Synchronized ordering to reduce variance
    - `rebalancing`: Inventory redistribution across nodes
    - `stabilization`: Gradual convergence to equilibrium

    **Use Cases**:
    - **Supply Chain Manager**: View system-wide recommendations
    - **Educational Tool**: Demonstrate coordinated planning benefits
    - **Performance Improvement**: Optimize overall supply chain efficiency
    - **Bullwhip Mitigation**: Reduce demand amplification

    **Example Request**:
    ```json
    {
      "focus_nodes": ["RETAILER", "WHOLESALER"]
    }
    ```

    **Example Response**:
    ```json
    {
      "optimization_type": "coordination",
      "recommendations": {
        "RETAILER": {
          "order": 45,
          "reasoning": "Reduce order to stabilize supply chain"
        },
        "WHOLESALER": {
          "order": 52,
          "reasoning": "Increase slightly to buffer upstream"
        },
        "DISTRIBUTOR": {
          "order": 50,
          "reasoning": "Maintain current level"
        },
        "FACTORY": {
          "order": 48,
          "reasoning": "Reduce production to match demand"
        }
      },
      "expected_impact": {
        "cost_reduction": 25,
        "service_improvement": 0.15,
        "bullwhip_reduction": 0.30
      },
      "coordination_strategy": "Gradual stabilization to reduce bullwhip effect while maintaining service levels",
      "confidence": 0.75
    }
    ```

    **Algorithm**:
    1. Retrieve current state for all nodes in game
    2. Build multi-node context with inventory, backlog, orders, costs
    3. Call LLM with system-wide optimization prompt
    4. Parse coordinated recommendations
    5. Simulate expected impact on key metrics

    **Note**: If LLM is unavailable, falls back to heuristic-based stabilization strategy.
    """
    try:
        # Get game state
        from sqlalchemy import text

        # Get current round
        query = text("""
            SELECT current_round
            FROM games
            WHERE id = :game_id
        """)
        result = await db.execute(query, {"game_id": game_id})
        row = result.fetchone()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Game not found"
            )

        current_round = row.current_round

        # Get all players' state
        query = text("""
            SELECT
                p.id,
                p.role,
                pr.inventory_after,
                pr.backlog_after,
                pr.incoming_shipment,
                pr.outgoing_shipment,
                pr.order_placed,
                pr.total_cost,
                pr.service_level
            FROM players p
            JOIN player_rounds pr ON p.id = pr.player_id
            WHERE p.game_id = :game_id
            AND pr.round_number = :round_number
        """)
        result = await db.execute(query, {
            "game_id": game_id,
            "round_number": current_round
        })
        rows = result.fetchall()

        if not rows:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No player data found for current round"
            )

        # Build game state
        players = []
        for row in rows:
            players.append({
                "role": row.role,
                "inventory_after": row.inventory_after,
                "backlog_after": row.backlog_after,
                "incoming_shipment": row.incoming_shipment,
                "outgoing_shipment": row.outgoing_shipment,
                "order_placed": row.order_placed,
                "total_cost": row.total_cost,
                "service_level": row.service_level
            })

        game_state = {
            "current_round": current_round,
            "players": players
        }

        # Generate global optimization
        result = await generate_global_optimization(
            game_state=game_state,
            focus_nodes=request.focus_nodes
        )

        return GlobalOptimizationResponse(**result)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate global optimization: {str(e)}"
        )
