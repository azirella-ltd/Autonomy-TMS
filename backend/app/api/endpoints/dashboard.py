from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, List

from ... import models, schemas
from ...crud import crud_dashboard as crud
from ...db.session import get_sync_db as get_db
from ...core.security import get_current_active_user
from ...models.player import Player as SupplyChainPlayer
from ...models.game import Game, GameStatus

# Router for dashboard endpoints
dashboard_router = APIRouter()

@dashboard_router.get("/user-games")
async def get_user_games(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Get all active games for the current user.
    Returns a list of games with basic info (id, name, status, role).
    """
    # Get all games where user is a player
    games = (
        db.query(Game)
        .join(SupplyChainPlayer, SupplyChainPlayer.game_id == Game.id)
        .filter(SupplyChainPlayer.user_id == current_user.id)
        .all()
    )

    if not games:
        return []

    # Get player roles for each game
    result = []
    for game in games:
        player = (
            db.query(SupplyChainPlayer)
            .filter(
                SupplyChainPlayer.user_id == current_user.id,
                SupplyChainPlayer.game_id == game.id
            )
            .first()
        )

        if player:
            role_value = getattr(player.role, "name", str(player.role)).upper()
            result.append({
                "id": game.id,
                "name": game.name,
                "status": game.status.value if hasattr(game.status, 'value') else str(game.status),
                "role": role_value,
                "current_round": game.current_round,
                "max_rounds": game.max_rounds,
                "created_at": game.created_at.isoformat() if game.created_at else None
            })

    return result

@dashboard_router.get("/human-dashboard", response_model=schemas.DashboardResponse)
async def get_human_dashboard(
    game_id: Optional[int] = Query(None, description="Specific game ID to view. If not provided, returns the most recent active game."),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_active_user)
):
    """
    Get dashboard data for a human player.
    Returns game info, player role, current round, and metrics.

    If game_id is provided, returns data for that specific game.
    Otherwise, returns data for the most recent active game.
    """
    # Get active game for the user (either specific game_id or most recent)
    if game_id:
        active_game = db.query(Game).filter(Game.id == game_id).first()
        if not active_game:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Game with ID {game_id} not found"
            )
        # Verify user is a player in this game
        player_check = (
            db.query(SupplyChainPlayer)
            .filter(
                SupplyChainPlayer.user_id == current_user.id,
                SupplyChainPlayer.game_id == game_id
            )
            .first()
        )
        if not player_check:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a player in this game"
            )
    else:
        active_game = crud.get_active_game_for_user(db, user_id=current_user.id)
        if not active_game:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active game found for the user"
            )
    
    # Get player's role in the game
    player = (
        db.query(SupplyChainPlayer)
        .filter(
            SupplyChainPlayer.user_id == current_user.id,
            SupplyChainPlayer.game_id == active_game.id,
        )
        .first()
    )

    if not player:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Player data not found for this game"
        )
    
    # Get game metrics
    metrics = crud.get_player_metrics(db, player_id=player.id, game_id=active_game.id)
    
    # Get time series data for the player
    role_value = getattr(player.role, "name", str(player.role)).upper()

    time_series = crud.get_time_series_metrics(
        db,
        player_id=player.id,
        game_id=active_game.id,
        role=role_value,
    )

    # Convert time series data to TimeSeriesPoint models
    time_series_points = [
        schemas.TimeSeriesPoint(
            week=point.get('week', 0),
            inventory=point.get('inventory', 0),
            order=point.get('order', 0),
            cost=point.get('cost', 0),
            backlog=point.get('backlog', 0),
            demand=point.get('demand'),
            supply=point.get('supply'),
            reason=point.get('reason'),
        )
        for point in time_series
    ]

    # Create the response model
    return schemas.DashboardResponse(
        game_id=active_game.id,
        player_id=player.id,
        game_name=active_game.name,
        current_round=active_game.current_round,
        max_rounds=active_game.max_rounds,
        player_role=role_value,
        metrics=schemas.PlayerMetrics(**metrics),
        time_series=time_series_points,
        last_updated=datetime.utcnow().isoformat()
    )
