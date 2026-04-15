"""
Analytics Entity Models - AWS SC Compliant

Implements analytics and optimization entities:
1. Inventory Optimization
2. Capacity Optimization
3. Network Optimization
4. KPI Configuration

These entities support advanced planning and decision-making.

IMPORTANT: This implementation follows the AWS Supply Chain Data Model as the foundation.
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Date, ForeignKey, text, Double, Boolean, JSON
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from datetime import datetime, date
from typing import Optional

from app.models.base import Base


class InventoryOptimization(Base):
    """
    Inventory Optimization - Safety stock and reorder point optimization

    AWS SC Entity: inventory_optimization

    Optimizes inventory parameters using:
    - Service level targets
    - Demand variability
    - Lead time variability
    - Cost constraints

    AWS SC Core Fields:
    - company_id, site_id, product_id
    - optimization_date, optimization_method
    - recommended_safety_stock, recommended_reorder_point
    - expected_service_level, expected_cost

    Extensions:
    - Stochastic analysis (P10/P50/P90)
    - Multi-objective optimization
    - Constraint violations
    """
    __tablename__ = "inventory_optimization"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # AWS SC Core Fields
    company_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("company.id"))
    site_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("site.id"))
    product_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("product.id"))

    # Optimization metadata
    optimization_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    optimization_method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="newsvendor, base_stock, ss_rop, monte_carlo"
    )

    # Current state (before optimization)
    current_safety_stock: Mapped[Optional[float]] = mapped_column(Double)
    current_reorder_point: Mapped[Optional[float]] = mapped_column(Double)
    current_service_level: Mapped[Optional[float]] = mapped_column(Double)
    current_holding_cost: Mapped[Optional[float]] = mapped_column(Double)

    # Recommended parameters (after optimization)
    recommended_safety_stock: Mapped[float] = mapped_column(Double, nullable=False)
    recommended_reorder_point: Mapped[Optional[float]] = mapped_column(Double)
    expected_service_level: Mapped[float] = mapped_column(Double, nullable=False)
    expected_holding_cost: Mapped[Optional[float]] = mapped_column(Double)
    expected_stockout_cost: Mapped[Optional[float]] = mapped_column(Double)
    expected_total_cost: Mapped[Optional[float]] = mapped_column(Double)

    # Stochastic analysis
    demand_mean: Mapped[Optional[float]] = mapped_column(Double)
    demand_std_dev: Mapped[Optional[float]] = mapped_column(Double)
    lead_time_mean: Mapped[Optional[float]] = mapped_column(Double)
    lead_time_std_dev: Mapped[Optional[float]] = mapped_column(Double)

    # Percentile results (stochastic)
    safety_stock_p10: Mapped[Optional[float]] = mapped_column(Double)
    safety_stock_p50: Mapped[Optional[float]] = mapped_column(Double)
    safety_stock_p90: Mapped[Optional[float]] = mapped_column(Double)

    # Objective weights (multi-objective)
    service_level_weight: Mapped[float] = mapped_column(Double, default=0.6)
    cost_weight: Mapped[float] = mapped_column(Double, default=0.4)

    # Constraints
    min_safety_stock: Mapped[Optional[float]] = mapped_column(Double)
    max_safety_stock: Mapped[Optional[float]] = mapped_column(Double)
    has_constraint_violations: Mapped[bool] = mapped_column(Boolean, default=False)
    constraint_violations: Mapped[Optional[str]] = mapped_column(String(500))

    # Approval workflow
    status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        comment="pending, approved, rejected, applied"
    )
    approved_by: Mapped[Optional[str]] = mapped_column(String(100))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Source tracking
    source: Mapped[Optional[str]] = mapped_column(String(100))
    source_event_id: Mapped[Optional[str]] = mapped_column(String(100))
    source_update_dttm: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(100))

    def __repr__(self):
        return (
            f"<InventoryOptimization(id={self.id}, product_id='{self.product_id}', "
            f"recommended_ss={self.recommended_safety_stock}, expected_sl={self.expected_service_level})>"
        )


class CapacityOptimization(Base):
    """
    Capacity Optimization - Production capacity and resource leveling

    AWS SC Entity: capacity_optimization

    Optimizes capacity allocation:
    - Resource leveling across periods
    - Overtime vs. inventory trade-offs
    - Bottleneck resolution
    - Multi-site capacity balancing

    AWS SC Core Fields:
    - company_id, site_id, resource_id
    - optimization_date, optimization_horizon
    - recommended_capacity_plan
    - expected_utilization, expected_cost
    """
    __tablename__ = "capacity_optimization"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # AWS SC Core Fields
    company_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("company.id"))
    site_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("site.id"))
    resource_id: Mapped[Optional[str]] = mapped_column(String(100))

    # Optimization metadata
    optimization_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    optimization_horizon_weeks: Mapped[int] = mapped_column(Integer, default=13)
    optimization_method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="linear_program, constraint_programming, heuristic"
    )

    # Current state
    current_capacity_hours: Mapped[Optional[float]] = mapped_column(Double)
    current_utilization_pct: Mapped[Optional[float]] = mapped_column(Double)
    current_overtime_hours: Mapped[Optional[float]] = mapped_column(Double)
    current_cost: Mapped[Optional[float]] = mapped_column(Double)

    # Recommended plan (JSON: {week: capacity_hours})
    recommended_capacity_plan: Mapped[Optional[str]] = mapped_column(JSON)
    expected_utilization_pct: Mapped[float] = mapped_column(Double, nullable=False)
    expected_overtime_hours: Mapped[Optional[float]] = mapped_column(Double)
    expected_cost: Mapped[Optional[float]] = mapped_column(Double)

    # Bottleneck analysis
    is_bottleneck: Mapped[bool] = mapped_column(Boolean, default=False)
    bottleneck_weeks: Mapped[Optional[str]] = mapped_column(String(500))  # Comma-separated week numbers
    bottleneck_severity: Mapped[Optional[str]] = mapped_column(String(20))  # critical, high, medium, low

    # Leveling metrics
    capacity_variance: Mapped[Optional[float]] = mapped_column(Double)  # Measure of smoothness
    peak_to_average_ratio: Mapped[Optional[float]] = mapped_column(Double)

    # Alternative scenarios
    scenario_name: Mapped[Optional[str]] = mapped_column(String(100))
    alternatives_evaluated: Mapped[Optional[int]] = mapped_column(Integer)

    # Status
    status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        comment="pending, approved, rejected, applied"
    )
    approved_by: Mapped[Optional[str]] = mapped_column(String(100))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Source tracking
    source: Mapped[Optional[str]] = mapped_column(String(100))
    source_event_id: Mapped[Optional[str]] = mapped_column(String(100))
    source_update_dttm: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(100))

    def __repr__(self):
        return (
            f"<CapacityOptimization(id={self.id}, resource_id='{self.resource_id}', "
            f"expected_util={self.expected_utilization_pct}%, is_bottleneck={self.is_bottleneck})>"
        )


class NetworkOptimization(Base):
    """
    Network Optimization - Supply chain network design and optimization

    AWS SC Entity: network_optimization

    Optimizes network structure:
    - DC location optimization
    - Production allocation
    - Transportation lane optimization
    - Network cost minimization

    AWS SC Core Fields:
    - company_id, optimization_date
    - optimization_type (location, allocation, flow)
    - recommended_network_changes
    - expected_cost_reduction
    """
    __tablename__ = "network_optimization"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # AWS SC Core Fields
    company_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("company.id"))

    # Optimization metadata
    optimization_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    optimization_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="dc_location, production_allocation, flow_optimization, end_to_end"
    )
    optimization_method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="mixed_integer_program, genetic_algorithm, simulated_annealing"
    )
    optimization_horizon_weeks: Mapped[int] = mapped_column(Integer, default=52)

    # Current network
    current_sites_count: Mapped[Optional[int]] = mapped_column(Integer)
    current_lanes_count: Mapped[Optional[int]] = mapped_column(Integer)
    current_network_cost: Mapped[Optional[float]] = mapped_column(Double)
    current_avg_lead_time_days: Mapped[Optional[float]] = mapped_column(Double)

    # Recommended network (JSON)
    recommended_network_changes: Mapped[Optional[str]] = mapped_column(JSON)
    recommended_sites_count: Mapped[Optional[int]] = mapped_column(Integer)
    recommended_lanes_count: Mapped[Optional[int]] = mapped_column(Integer)
    expected_network_cost: Mapped[float] = mapped_column(Double, nullable=False)
    expected_cost_reduction_pct: Mapped[Optional[float]] = mapped_column(Double)
    expected_avg_lead_time_days: Mapped[Optional[float]] = mapped_column(Double)
    expected_service_level: Mapped[Optional[float]] = mapped_column(Double)

    # Objectives and constraints
    primary_objective: Mapped[str] = mapped_column(
        String(50),
        default="minimize_cost",
        comment="minimize_cost, minimize_leadtime, maximize_service_level"
    )
    cost_weight: Mapped[float] = mapped_column(Double, default=0.5)
    service_weight: Mapped[float] = mapped_column(Double, default=0.3)
    lead_time_weight: Mapped[float] = mapped_column(Double, default=0.2)

    # Capital investment
    capital_investment_required: Mapped[Optional[float]] = mapped_column(Double)
    payback_period_months: Mapped[Optional[float]] = mapped_column(Double)
    npv: Mapped[Optional[float]] = mapped_column(Double)  # Net Present Value

    # Alternative scenarios
    scenario_name: Mapped[Optional[str]] = mapped_column(String(100))
    alternatives_evaluated: Mapped[Optional[int]] = mapped_column(Integer)

    # Status
    status: Mapped[str] = mapped_column(
        String(50),
        default="pending",
        comment="pending, approved, rejected, applied"
    )
    approved_by: Mapped[Optional[str]] = mapped_column(String(100))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Source tracking
    source: Mapped[Optional[str]] = mapped_column(String(100))
    source_event_id: Mapped[Optional[str]] = mapped_column(String(100))
    source_update_dttm: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(100))

    def __repr__(self):
        return (
            f"<NetworkOptimization(id={self.id}, type='{self.optimization_type}', "
            f"cost_reduction={self.expected_cost_reduction_pct}%)>"
        )


class KPIConfiguration(Base):
    """
    KPI Configuration - Define and track supply chain KPIs

    AWS SC Entity: kpi_configuration

    Configures performance metrics:
    - Service level targets
    - Inventory turns targets
    - Cost targets
    - Custom KPIs

    AWS SC Core Fields:
    - company_id, site_id (optional)
    - kpi_name, kpi_category
    - target_value, threshold_values
    - calculation_method
    """
    __tablename__ = "kpi_configuration"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # AWS SC Core Fields
    company_id: Mapped[Optional[str]] = mapped_column(String(100), ForeignKey("company.id"))
    site_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("site.id"))  # Optional: site-specific KPI

    # KPI metadata
    kpi_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    kpi_category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="financial, customer, operational, strategic"
    )
    kpi_description: Mapped[Optional[str]] = mapped_column(String(500))
    kpi_unit: Mapped[Optional[str]] = mapped_column(String(50))  # %, $, days, units

    # Target and thresholds
    target_value: Mapped[float] = mapped_column(Double, nullable=False)
    threshold_green: Mapped[Optional[float]] = mapped_column(Double)  # Above = green
    threshold_yellow: Mapped[Optional[float]] = mapped_column(Double)  # Above = yellow, below = red
    threshold_red: Mapped[Optional[float]] = mapped_column(Double)  # Below = red

    # Calculation
    calculation_method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="formula, aggregate, custom_function"
    )
    calculation_formula: Mapped[Optional[str]] = mapped_column(String(1000))  # SQL or expression
    aggregation_period: Mapped[Optional[str]] = mapped_column(String(20))  # daily, weekly, monthly, quarterly

    # Trending direction
    is_higher_better: Mapped[bool] = mapped_column(Boolean, default=True)  # True: higher is better, False: lower is better

    # Monitoring
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    monitoring_frequency: Mapped[Optional[str]] = mapped_column(String(20))  # realtime, daily, weekly
    alert_on_breach: Mapped[bool] = mapped_column(Boolean, default=True)
    alert_recipients: Mapped[Optional[str]] = mapped_column(String(500))  # Comma-separated emails

    # Historical tracking
    baseline_value: Mapped[Optional[float]] = mapped_column(Double)
    baseline_date: Mapped[Optional[date]] = mapped_column(Date)

    # Source tracking
    source: Mapped[Optional[str]] = mapped_column(String(100))
    source_event_id: Mapped[Optional[str]] = mapped_column(String(100))
    source_update_dttm: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Audit fields
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(100))
    updated_by: Mapped[Optional[str]] = mapped_column(String(100))

    def __repr__(self):
        return (
            f"<KPIConfiguration(id={self.id}, kpi_name='{self.kpi_name}', "
            f"target={self.target_value}, category='{self.kpi_category}')>"
        )

    def evaluate_performance(self, actual_value: float) -> str:
        """Evaluate performance against thresholds"""
        if self.is_higher_better:
            if self.threshold_green and actual_value >= self.threshold_green:
                return "GREEN"
            elif self.threshold_yellow and actual_value >= self.threshold_yellow:
                return "YELLOW"
            else:
                return "RED"
        else:
            # Lower is better
            if self.threshold_green and actual_value <= self.threshold_green:
                return "GREEN"
            elif self.threshold_yellow and actual_value <= self.threshold_yellow:
                return "YELLOW"
            else:
                return "RED"
