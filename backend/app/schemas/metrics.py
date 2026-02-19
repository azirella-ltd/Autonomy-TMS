from typing import List, Dict, Optional
from pydantic import BaseModel
from datetime import datetime

class MarginMetrics(BaseModel):
    selling_price: float = 100.0  # Default selling price per unit
    standard_cost: float = 60.0   # Default standard cost per unit
    gross_margin: float           # Selling price - standard cost
    net_margin: float             # Gross margin - operational costs
    margin_erosion: float         # Percentage of margin lost to costs

class CostMetrics(BaseModel):
    total_cost: float
    holding_cost: float
    backorder_cost: float
    average_weekly_cost: float
    operational_cost: float       # Sum of holding and backorder costs

class InventoryMetrics(BaseModel):
    average_inventory: float
    inventory_turns: float
    stockout_weeks: int
    service_level: float  # Percentage of demand met from stock

class OrderMetrics(BaseModel):
    average_order: float
    order_variability: float  # Coefficient of variation
    bullwhip_effect: Optional[float]  # Variance ratio between orders and demand

class PlayerRoundMetrics(BaseModel):
    round_number: int
    inventory: int
    backorders: int
    order_placed: int
    order_received: int
    holding_cost: float
    backorder_cost: float
    total_cost: float
    revenue: float = 0.0
    gross_margin: float = 0.0
    net_margin: float = 0.0
    margin_erosion: float = 0.0  # Percentage of margin lost to costs

class PlayerPerformance(BaseModel):
    player_id: int
    player_name: str
    role: str
    total_cost: float
    total_revenue: float = 0.0
    total_gross_margin: float = 0.0
    total_net_margin: float = 0.0
    average_margin_erosion: float = 0.0
    cost_metrics: CostMetrics
    margin_metrics: MarginMetrics
    inventory_metrics: InventoryMetrics
    order_metrics: OrderMetrics
    round_metrics: List[PlayerRoundMetrics]

class GameMetricsResponse(BaseModel):
    game_id: int
    game_name: str
    total_rounds: int
    start_date: datetime
    end_date: Optional[datetime]
    players: List[PlayerPerformance]
    total_supply_chain_cost: float
    average_weekly_demand: float
    bullwhip_effect: Optional[float]  # Overall supply chain bullwhip effect
