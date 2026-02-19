"""Dashboard schemas for simulation performance metrics.

Terminology (Feb 2026):
- Game -> Scenario
- Player -> Participant
- Round -> Period
"""
from pydantic import BaseModel, Field
from typing import List, Optional


class TimeSeriesPoint(BaseModel):
    """Represents a single data point in the time series."""

    period: int = Field(..., alias="week", description="The period number in the scenario")
    inventory: float = Field(0, description="Current inventory level")
    order: float = Field(0, description="Current order quantity")
    cost: float = Field(0, description="Accumulated cost for this period")
    backlog: float = Field(0, description="Current backlog amount")
    demand: Optional[float] = Field(None, description="Demand for this period (if applicable)")
    supply: Optional[float] = Field(None, description="Supply for this period (if applicable)")
    reason: Optional[str] = Field(None, description="Comment or rationale for the order this period")

    class Config:
        populate_by_name = True


class ParticipantMetrics(BaseModel):
    """Key performance metrics for a participant."""

    current_inventory: float = Field(..., description="Current inventory level")
    inventory_change: float = Field(0, description="Percentage change in inventory from last period")
    backlog: float = Field(0, description="Current backlog amount")
    total_cost: float = Field(0, description="Total accumulated cost")
    avg_period_cost: float = Field(0, alias="avg_weekly_cost", description="Average cost per period")
    service_level: float = Field(1.0, description="Current service level (0-1)")
    service_level_change: float = Field(0, description="Change in service level from last period")

    class Config:
        populate_by_name = True


class DashboardResponse(BaseModel):
    """Dashboard data response model."""

    scenario_id: int = Field(..., alias="game_id", description="Identifier of the active scenario")
    participant_id: int = Field(..., alias="player_id", description="Identifier of the participant viewing the dashboard")
    scenario_name: str = Field(..., alias="game_name", description="Name of the current scenario")
    current_period: int = Field(..., alias="current_round", description="Current period number in the scenario")
    max_periods: int = Field(..., alias="max_rounds", description="Total number of periods configured for the scenario")
    participant_role: str = Field(..., alias="player_role", description="Participant's role in the scenario")
    metrics: ParticipantMetrics = Field(..., description="Participant performance metrics")
    time_series: List[TimeSeriesPoint] = Field(..., description="Time series data for the participant")
    last_updated: str = Field(..., description="ISO timestamp of when the data was last updated")

    class Config:
        populate_by_name = True
