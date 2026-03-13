"""
Monte Carlo Simulation Models

Stores Monte Carlo simulation runs, scenarios, and statistical results.
Enables probabilistic planning and risk analysis.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, ForeignKey,
    Text, Boolean, JSON, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from enum import Enum

from .base import Base
from app.models.compatibility import Item, ProductSiteConfig  # Temporary compat


class SimulationStatus(str, Enum):
    """Monte Carlo simulation status"""
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class MonteCarloRun(Base):
    """
    Monte Carlo simulation run configuration and results

    Stores metadata about a Monte Carlo simulation including:
    - Number of scenarios
    - Random seed for reproducibility
    - Overall status and timing
    - Summary statistics across all scenarios
    """
    __tablename__ = "monte_carlo_runs"

    id = Column(Integer, primary_key=True, index=True)

    # Configuration reference
    supply_chain_config_id = Column(Integer, ForeignKey("supply_chain_configs.id"), nullable=False)
    mps_plan_id = Column(Integer, ForeignKey("mps_plans.id"), nullable=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    # Simulation parameters
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    num_scenarios = Column(Integer, nullable=False, default=1000)
    random_seed = Column(Integer, nullable=True)

    # Time horizon
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    planning_horizon_weeks = Column(Integer, nullable=False)

    # Execution metadata
    status = Column(SQLEnum(SimulationStatus), nullable=False, default=SimulationStatus.QUEUED)
    progress_percent = Column(Float, default=0.0)
    scenarios_completed = Column(Integer, default=0)

    # Timing
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    execution_time_seconds = Column(Float, nullable=True)

    # Error tracking
    error_message = Column(Text, nullable=True)

    # Summary statistics (JSON)
    # Structure: {
    #   "inventory": {"mean": X, "p5": Y, "p50": Z, "p95": W, "std": S},
    #   "backlog": {...},
    #   "total_cost": {...},
    #   "service_level": {...}
    # }
    summary_statistics = Column(JSON, nullable=True)

    # Risk metrics (JSON)
    # Structure: {
    #   "stockout_probability": 0.15,
    #   "overstock_probability": 0.25,
    #   "capacity_violation_probability": 0.05,
    #   "service_level_below_target_probability": 0.10
    # }
    risk_metrics = Column(JSON, nullable=True)

    # Audit fields
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    supply_chain_config = relationship("SupplyChainConfig")  # back_populates removed due to circular import
    mps_plan = relationship("MPSPlan")  # back_populates removed due to circular import
    scenarios = relationship("MonteCarloScenario", back_populates="run", cascade="all, delete-orphan")
    time_series_results = relationship("MonteCarloTimeSeries", back_populates="run", cascade="all, delete-orphan")


class MonteCarloScenario(Base):
    """
    Individual scenario within a Monte Carlo run

    Each scenario represents one simulation path with:
    - Sampled stochastic variable values (lead times, demands, yields, etc.)
    - Resulting KPIs (total cost, service level, etc.)
    - Time-series data stored separately in MonteCarloTimeSeries
    """
    __tablename__ = "monte_carlo_scenarios"

    id = Column(Integer, primary_key=True, index=True)

    run_id = Column(Integer, ForeignKey("monte_carlo_runs.id"), nullable=False, index=True)
    scenario_number = Column(Integer, nullable=False)

    # Sampled input variables (JSON)
    # Structure: {
    #   "lead_times": {"Retailer->Wholesaler": 2, "Wholesaler->Distributor": 3, ...},
    #   "demands": {"week_1": 100, "week_2": 120, ...},
    #   "yields": {"Factory": 0.98, ...},
    #   "capacities": {"Factory": 1000, ...}
    # }
    sampled_inputs = Column(JSON, nullable=False)

    # Scenario-level KPIs
    total_cost = Column(Float, nullable=True)
    holding_cost = Column(Float, nullable=True)
    backlog_cost = Column(Float, nullable=True)
    ordering_cost = Column(Float, nullable=True)
    service_level = Column(Float, nullable=True)  # Percentage

    # Final state metrics
    final_inventory = Column(Float, nullable=True)
    final_backlog = Column(Float, nullable=True)
    max_inventory = Column(Float, nullable=True)
    max_backlog = Column(Float, nullable=True)

    # Flags
    had_stockout = Column(Boolean, default=False)
    had_overstock = Column(Boolean, default=False)
    had_capacity_violation = Column(Boolean, default=False)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    run = relationship("MonteCarloRun", back_populates="scenarios")


class MonteCarloTimeSeries(Base):
    """
    Time-series data for Monte Carlo simulations

    Stores weekly/period-level data across all scenarios:
    - Inventory levels by product/site/week
    - Backlog by product/site/week
    - Orders placed, received, fulfilled
    - Statistical summaries (mean, P5, P50, P95)

    This enables time-series charts with confidence bands.
    """
    __tablename__ = "monte_carlo_time_series"

    id = Column(Integer, primary_key=True, index=True)

    run_id = Column(Integer, ForeignKey("monte_carlo_runs.id"), nullable=False, index=True)

    # Dimension keys
    # Updated to use SC Product table with String PK
    product_id = Column(String(100), ForeignKey("product.id"), nullable=True)
    site_id = Column(Integer, ForeignKey("site.id"), nullable=True)
    period_week = Column(Integer, nullable=False)  # Week number from start
    period_date = Column(DateTime, nullable=False)  # Date of week start

    # Metric name (inventory, backlog, orders_placed, etc.)
    metric_name = Column(String(100), nullable=False, index=True)

    # Statistical summaries across all scenarios
    mean_value = Column(Float, nullable=True)
    median_value = Column(Float, nullable=True)
    std_dev = Column(Float, nullable=True)

    # Percentiles for confidence bands
    p5_value = Column(Float, nullable=True)  # 5th percentile
    p10_value = Column(Float, nullable=True)
    p25_value = Column(Float, nullable=True)
    p75_value = Column(Float, nullable=True)
    p90_value = Column(Float, nullable=True)
    p95_value = Column(Float, nullable=True)  # 95th percentile

    min_value = Column(Float, nullable=True)
    max_value = Column(Float, nullable=True)

    # Optional: Store all scenario values as JSON array for detailed analysis
    # [scenario_1_value, scenario_2_value, ...]
    all_scenario_values = Column(JSON, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    run = relationship("MonteCarloRun", back_populates="time_series_results")
    product = relationship("Product")  # Changed from "Item" to "Product"
    site = relationship("Site")


class MonteCarloRiskAlert(Base):
    """
    Risk alerts generated from Monte Carlo analysis

    Flags high-risk situations identified during simulation:
    - High stockout probability
    - Capacity constraints
    - Service level violations
    - Cost overruns
    """
    __tablename__ = "monte_carlo_risk_alerts"

    id = Column(Integer, primary_key=True, index=True)

    run_id = Column(Integer, ForeignKey("monte_carlo_runs.id"), nullable=False, index=True)

    # Alert details
    alert_type = Column(String(100), nullable=False)  # stockout_risk, capacity_risk, etc.
    severity = Column(String(50), nullable=False)  # low, medium, high, critical

    # Location
    # Updated to use SC Product table with String PK
    product_id = Column(String(100), ForeignKey("product.id"), nullable=True)
    site_id = Column(Integer, ForeignKey("site.id"), nullable=True)
    period_week = Column(Integer, nullable=True)
    period_date = Column(DateTime, nullable=True)

    # Alert message
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)

    # Quantitative data
    probability = Column(Float, nullable=True)  # Probability of risk event
    expected_impact = Column(Float, nullable=True)  # Expected cost/quantity impact

    # Recommendation
    recommendation = Column(Text, nullable=True)

    # Acknowledgement
    acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    run = relationship("MonteCarloRun")
    product = relationship("Product")  # Changed from "Item" to "Product"
    site = relationship("Site")
