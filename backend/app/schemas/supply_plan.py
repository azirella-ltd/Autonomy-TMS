"""
Supply Plan Pydantic Schemas

Request/response models for supply plan generation API.
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class DemandModel(str, Enum):
    """Demand distribution model."""
    NORMAL = "normal"
    POISSON = "poisson"
    LOGNORMAL = "lognormal"
    AUTO = "auto"  # Auto-detect best distribution from historical data


class LeadTimeModel(str, Enum):
    """Lead time distribution model."""
    DETERMINISTIC = "deterministic"
    NORMAL = "normal"
    UNIFORM = "uniform"
    WEIBULL = "weibull"        # Weibull (natural for time-to-event, always positive)
    LOGNORMAL = "lognormal"    # Lognormal (right-skewed, always positive)
    AUTO = "auto"              # Auto-detect best distribution from historical data


class PrimaryObjective(str, Enum):
    """Primary planning objective."""
    MINIMIZE_COST = "minimize_cost"
    MAXIMIZE_SERVICE = "maximize_service"
    BALANCE = "balance"


class PlanStatus(str, Enum):
    """Status of supply plan generation."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ============================================================================
# Stochastic Parameters
# ============================================================================

class StochasticParametersSchema(BaseModel):
    """Stochastic parameter configuration."""
    demand_model: DemandModel = Field(default=DemandModel.NORMAL)
    demand_variability: float = Field(default=0.15, ge=0.0, le=1.0, description="Coefficient of variation (std/mean)")

    lead_time_model: LeadTimeModel = Field(default=LeadTimeModel.NORMAL)
    lead_time_variability: float = Field(default=0.10, ge=0.0, le=1.0)

    supplier_reliability: float = Field(default=0.95, ge=0.0, le=1.0, description="On-time delivery probability")

    random_seed: Optional[int] = Field(default=None, ge=0, description="Random seed for reproducibility")

    class Config:
        json_schema_extra = {
            "example": {
                "demand_model": "normal",
                "demand_variability": 0.15,
                "lead_time_model": "normal",
                "lead_time_variability": 0.10,
                "supplier_reliability": 0.95,
                "random_seed": 42
            }
        }


# ============================================================================
# Plan Objectives
# ============================================================================

class PlanObjectivesSchema(BaseModel):
    """Business objectives and constraints."""
    planning_horizon: int = Field(default=52, ge=1, le=104, description="Planning horizon in weeks")

    primary_objective: PrimaryObjective = Field(default=PrimaryObjective.MINIMIZE_COST)

    service_level_target: float = Field(default=0.95, ge=0.0, le=1.0, description="OTIF target")
    service_level_confidence: float = Field(default=0.90, ge=0.0, le=1.0, description="P(OTIF > target) >= confidence")

    budget_limit: Optional[float] = Field(default=None, gt=0, description="Maximum budget constraint")

    inventory_dos_min: Optional[int] = Field(default=None, ge=0, description="Minimum days of supply")
    inventory_dos_max: Optional[int] = Field(default=None, ge=0, description="Maximum days of supply")

    @validator("inventory_dos_max")
    def validate_dos_range(cls, v, values):
        """Ensure max >= min if both are set."""
        if v is not None and "inventory_dos_min" in values:
            min_dos = values["inventory_dos_min"]
            if min_dos is not None and v < min_dos:
                raise ValueError("inventory_dos_max must be >= inventory_dos_min")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "planning_horizon": 52,
                "primary_objective": "minimize_cost",
                "service_level_target": 0.95,
                "service_level_confidence": 0.90,
                "budget_limit": 500000.0,
                "inventory_dos_min": 10,
                "inventory_dos_max": 30
            }
        }


# ============================================================================
# Request/Response Models
# ============================================================================

class SupplyPlanGenerateRequest(BaseModel):
    """Request to generate a supply plan."""
    config_id: int = Field(..., gt=0, description="Supply chain configuration ID")
    agent_strategy: str = Field(default="trm", description="Agent strategy (naive, pid, trm, gnn, llm)")
    num_scenarios: int = Field(default=1000, ge=10, le=10000, description="Number of Monte Carlo scenarios")

    stochastic_params: StochasticParametersSchema
    objectives: PlanObjectivesSchema

    class Config:
        json_schema_extra = {
            "example": {
                "config_id": 7,
                "agent_strategy": "trm",
                "num_scenarios": 1000,
                "stochastic_params": {
                    "demand_model": "normal",
                    "demand_variability": 0.15,
                    "lead_time_model": "normal",
                    "lead_time_variability": 0.10,
                    "supplier_reliability": 0.95
                },
                "objectives": {
                    "planning_horizon": 52,
                    "service_level_target": 0.95,
                    "service_level_confidence": 0.90,
                    "budget_limit": 500000.0
                }
            }
        }


class SupplyPlanGenerateResponse(BaseModel):
    """Response from supply plan generation request."""
    task_id: int = Field(..., description="Task ID for checking status")
    status: PlanStatus
    message: str = Field(default="Supply plan generation started")

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": 123,
                "status": "running",
                "message": "Monte Carlo simulation running with 1000 scenarios"
            }
        }


class SupplyPlanStatusResponse(BaseModel):
    """Status of supply plan generation task."""
    task_id: int
    status: PlanStatus
    progress: float = Field(..., ge=0.0, le=1.0, description="Progress from 0.0 to 1.0")

    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    error_message: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": 123,
                "status": "running",
                "progress": 0.65,
                "created_at": "2026-01-17T10:30:00Z",
                "started_at": "2026-01-17T10:30:05Z",
                "completed_at": None,
                "error_message": None
            }
        }


class MetricStatistics(BaseModel):
    """Statistical summary for a metric."""
    expected: float
    p10: float
    p50: float
    p90: float
    min: float
    max: float
    std_dev: float


class OTIFMetric(MetricStatistics):
    """OTIF metric with probability."""
    probability_above_target: float = Field(..., ge=0.0, le=1.0)
    target: float
    confidence_requirement: float


class BalancedScorecard(BaseModel):
    """Probabilistic balanced scorecard."""
    financial: Dict[str, MetricStatistics]
    customer: Dict[str, Any]  # Contains OTIFMetric
    operational: Dict[str, MetricStatistics]
    strategic: Dict[str, MetricStatistics]


class Recommendation(BaseModel):
    """Actionable recommendation."""
    type: str
    severity: str = Field(..., pattern="^(high|medium|low)$")
    metric: str
    message: str
    recommendation: str


class SupplyPlanResultResponse(BaseModel):
    """Complete supply plan result."""
    task_id: int
    status: PlanStatus

    config_id: int
    config_name: str
    agent_strategy: str
    num_scenarios: int
    planning_horizon: int

    scorecard: BalancedScorecard
    recommendations: List[Recommendation]

    # Plan detail: orders (PO/MO/STO) and inventory targets (safety stock / ROP)
    orders: Optional[List[Dict[str, Any]]] = None
    inventory_targets: Optional[List[Dict[str, Any]]] = None

    # Summary metrics
    total_cost_expected: float
    total_cost_p10: Optional[float] = None
    total_cost_p90: Optional[float] = None
    otif_expected: float
    otif_probability_above_target: Optional[float] = None
    fill_rate_expected: float
    inventory_turns_expected: float
    bullwhip_ratio_expected: float

    created_at: datetime
    completed_at: datetime

    # Conformal prediction summary across all supply plan lines
    conformal_summary: Optional[Dict[str, Any]] = Field(
        None,
        description="Summary of conformal interval coverage across plan lines"
    )

    # Plan-level confidence score (composite of all conformal sub-scores)
    plan_confidence: Optional[Dict[str, Any]] = Field(
        None,
        description="Composite plan confidence from conformal prediction calibration"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": 123,
                "status": "completed",
                "config_id": 7,
                "config_name": "Complex_SC",
                "agent_strategy": "trm",
                "num_scenarios": 1000,
                "planning_horizon": 52,
                "total_cost_expected": 340512.0,
                "otif_expected": 0.935,
                "fill_rate_expected": 0.955,
                "inventory_turns_expected": 11.4,
                "bullwhip_ratio_expected": 1.65
            }
        }


class SupplyPlanComparisonRequest(BaseModel):
    """Request to compare multiple supply plans."""
    plan_ids: List[int] = Field(..., min_items=2, max_items=10)
    name: str = Field(..., max_length=200)
    description: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "plan_ids": [123, 124, 125],
                "name": "Agent Strategy Comparison",
                "description": "Compare naive vs PID vs TRM agents"
            }
        }


class SupplyPlanComparisonResponse(BaseModel):
    """Supply plan comparison result."""
    comparison_id: int
    name: str
    plan_ids: List[int]

    winner: str = Field(..., description="Best performing agent/plan")
    metrics: Dict[str, Dict[str, float]]

    created_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "comparison_id": 45,
                "name": "Agent Strategy Comparison",
                "plan_ids": [123, 124, 125],
                "winner": "trm",
                "metrics": {
                    "total_cost": {"naive": 12000, "pid": 10500, "trm": 9700},
                    "otif": {"naive": 0.85, "pid": 0.91, "trm": 0.935}
                }
            }
        }


class SupplyPlanExportRequest(BaseModel):
    """Request to export a supply plan."""
    task_id: int
    format: str = Field(..., pattern="^(csv|excel|pdf|json)$")

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": 123,
                "format": "excel"
            }
        }


class SupplyPlanExportResponse(BaseModel):
    """Supply plan export result."""
    export_id: int
    task_id: int
    format: str
    file_url: str
    file_size_bytes: int
    created_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "export_id": 789,
                "task_id": 123,
                "format": "excel",
                "file_url": "/api/v1/supply-plan/downloads/789",
                "file_size_bytes": 45678,
                "created_at": "2026-01-17T11:00:00Z"
            }
        }
