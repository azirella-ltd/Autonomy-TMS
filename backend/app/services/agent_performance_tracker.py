"""
Agent Performance Tracker Service

Phase 4: Multi-Agent Orchestration (Week 13)
Tracks and benchmarks agent performance across scenarios, rounds, and decision types.

Metrics Tracked:
- Accuracy: Deviation from optimal/baseline decisions
- Cost: Total supply chain cost (holding + shortage)
- Service Level: Fill rate and OTIF performance
- Inventory Metrics: Avg inventory, stockouts, excess
- Bullwhip Ratio: Demand amplification measure

Use Cases:
- Agent comparison and benchmarking
- Performance degradation detection
- A/B testing of agent strategies
- RLHF training feedback
"""

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, Float, String, DateTime, JSON, ForeignKey
import statistics
import logging

from app.models.base import Base
from app.models.scenario_user import ScenarioUser
from app.models.scenario import Scenario

# Aliases for backwards compatibility
ScenarioUser = ScenarioUser

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Snapshot of agent performance metrics."""
    scenario_user_id: int
    scenario_id: int
    round_number: int
    agent_type: str
    agent_mode: str  # manual, copilot, autonomous

    # Cost metrics
    total_cost: float
    holding_cost: float
    shortage_cost: float

    # Service metrics
    service_level: float  # Fill rate (0-1)
    stockout_count: int
    backlog: int

    # Inventory metrics
    avg_inventory: float
    inventory_variance: float

    # Bullwhip metrics
    demand_amplification: Optional[float] = None
    order_variance: Optional[float] = None

    # Decision metrics
    order_quantity: Optional[int] = None
    optimal_order: Optional[int] = None  # If known
    decision_error: Optional[float] = None  # Abs deviation from optimal

    timestamp: Optional[str] = None


@dataclass
class PerformanceComparison:
    """Comparison of agent performance vs baseline."""
    agent_type: str
    baseline_type: str

    # Relative performance (agent vs baseline)
    cost_improvement: float  # Negative = worse, positive = better
    service_level_improvement: float
    inventory_improvement: float

    # Statistical significance
    num_samples: int
    confidence: float  # 0-1

    # Raw metrics
    agent_metrics: Dict[str, float]
    baseline_metrics: Dict[str, float]


class AgentPerformanceTracker:
    """
    Tracks and benchmarks agent performance over time.

    Responsibilities:
    - Record per-round performance metrics
    - Calculate aggregate performance statistics
    - Compare agents against baselines (naive, optimal)
    - Generate performance reports
    - Detect performance degradation
    """

    def __init__(self, db: Session):
        self.db = db

    def record_performance(
        self,
        performance_metrics: PerformanceMetrics
    ) -> int:
        """
        Record performance metrics for a scenario_user in a round.

        Args:
            performance_metrics: Performance snapshot

        Returns:
            ID of created performance log record
        """
        # Create performance log record
        performance_log = AgentPerformanceLog(
            scenario_user_id=performance_metrics.scenario_user_id,
            scenario_id=performance_metrics.scenario_id,
            round_number=performance_metrics.round_number,
            agent_type=performance_metrics.agent_type,
            agent_mode=performance_metrics.agent_mode,
            total_cost=performance_metrics.total_cost,
            holding_cost=performance_metrics.holding_cost,
            shortage_cost=performance_metrics.shortage_cost,
            service_level=performance_metrics.service_level,
            stockout_count=performance_metrics.stockout_count,
            backlog=performance_metrics.backlog,
            avg_inventory=performance_metrics.avg_inventory,
            inventory_variance=performance_metrics.inventory_variance,
            demand_amplification=performance_metrics.demand_amplification,
            order_variance=performance_metrics.order_variance,
            order_quantity=performance_metrics.order_quantity,
            optimal_order=performance_metrics.optimal_order,
            decision_error=performance_metrics.decision_error,
            timestamp=datetime.utcnow()
        )

        self.db.add(performance_log)
        self.db.commit()
        self.db.refresh(performance_log)

        return performance_log.id

    def get_agent_performance_summary(
        self,
        scenario_user_id: Optional[int] = None,
        scenario_id: Optional[int] = None,
        agent_type: Optional[str] = None,
        min_rounds: int = 5
    ) -> Dict[str, Any]:
        """
        Get aggregate performance summary.

        Args:
            scenario_user_id: Filter by scenario_user
            scenario_id: Filter by scenario
            agent_type: Filter by agent type (llm, gnn, trm)
            min_rounds: Minimum rounds for statistical significance

        Returns:
            Dict with aggregate performance metrics
        """
        query = self.db.query(AgentPerformanceLog)

        if scenario_user_id:
            query = query.filter_by(scenario_user_id=scenario_user_id)
        if scenario_id:
            query = query.filter_by(scenario_id=scenario_id)
        if agent_type:
            query = query.filter_by(agent_type=agent_type)

        logs = query.all()

        if len(logs) < min_rounds:
            return {
                "num_samples": len(logs),
                "insufficient_data": True,
                "message": f"Need at least {min_rounds} rounds for statistical significance"
            }

        # Calculate aggregate metrics
        return {
            "num_samples": len(logs),
            "avg_total_cost": statistics.mean([log.total_cost for log in logs]),
            "avg_service_level": statistics.mean([log.service_level for log in logs]),
            "avg_inventory": statistics.mean([log.avg_inventory for log in logs]),
            "total_stockouts": sum([log.stockout_count for log in logs]),
            "avg_backlog": statistics.mean([log.backlog for log in logs]),
            "cost_variance": statistics.variance([log.total_cost for log in logs]) if len(logs) > 1 else 0,
            "avg_decision_error": statistics.mean([
                log.decision_error for log in logs if log.decision_error is not None
            ]) if any(log.decision_error is not None for log in logs) else None,
        }

    def compare_agents(
        self,
        agent_type: str,
        baseline_type: str,
        scenario_id: int
    ) -> PerformanceComparison:
        """
        Compare agent performance vs baseline.

        Args:
            agent_type: Agent to evaluate (llm, gnn, trm)
            baseline_type: Baseline to compare against (naive, optimal)
            scenario_id: Scenario context

        Returns:
            PerformanceComparison with relative metrics

        Raises:
            ValueError: If insufficient data for comparison
        """
        # Get agent performance
        agent_logs = self.db.query(AgentPerformanceLog).filter_by(
            scenario_id=scenario_id,
            agent_type=agent_type
        ).all()

        # Get baseline performance
        baseline_logs = self.db.query(AgentPerformanceLog).filter_by(
            scenario_id=scenario_id,
            agent_type=baseline_type
        ).all()

        if not agent_logs or not baseline_logs:
            raise ValueError(f"Insufficient data for comparison (agent: {len(agent_logs)}, baseline: {len(baseline_logs)})")

        # Calculate aggregate metrics
        agent_metrics = {
            "avg_cost": statistics.mean([log.total_cost for log in agent_logs]),
            "avg_service_level": statistics.mean([log.service_level for log in agent_logs]),
            "avg_inventory": statistics.mean([log.avg_inventory for log in agent_logs]),
        }

        baseline_metrics = {
            "avg_cost": statistics.mean([log.total_cost for log in baseline_logs]),
            "avg_service_level": statistics.mean([log.service_level for log in baseline_logs]),
            "avg_inventory": statistics.mean([log.avg_inventory for log in baseline_logs]),
        }

        # Calculate improvements (positive = agent better)
        cost_improvement = (baseline_metrics["avg_cost"] - agent_metrics["avg_cost"]) / baseline_metrics["avg_cost"] * 100
        service_level_improvement = (agent_metrics["avg_service_level"] - baseline_metrics["avg_service_level"]) * 100
        inventory_improvement = (baseline_metrics["avg_inventory"] - agent_metrics["avg_inventory"]) / baseline_metrics["avg_inventory"] * 100

        # Calculate confidence (based on sample size)
        num_samples = min(len(agent_logs), len(baseline_logs))
        confidence = min(1.0, num_samples / 30.0)  # Full confidence at 30+ samples

        return PerformanceComparison(
            agent_type=agent_type,
            baseline_type=baseline_type,
            cost_improvement=cost_improvement,
            service_level_improvement=service_level_improvement,
            inventory_improvement=inventory_improvement,
            num_samples=num_samples,
            confidence=confidence,
            agent_metrics=agent_metrics,
            baseline_metrics=baseline_metrics
        )

    def get_performance_trends(
        self,
        scenario_user_id: int,
        window_size: int = 10
    ) -> Dict[str, Any]:
        """
        Get performance trends over time (rolling window).

        Args:
            scenario_user_id: ScenarioUser to analyze
            window_size: Rolling window size in rounds

        Returns:
            Dict with trend data (improving, stable, degrading)
        """
        logs = self.db.query(AgentPerformanceLog).filter_by(
            scenario_user_id=scenario_user_id
        ).order_by(AgentPerformanceLog.round_number).all()

        if len(logs) < window_size * 2:
            return {
                "insufficient_data": True,
                "message": f"Need at least {window_size * 2} rounds for trend analysis"
            }

        # Calculate rolling averages
        costs = [log.total_cost for log in logs]
        service_levels = [log.service_level for log in logs]

        # Recent window vs previous window
        recent_cost = statistics.mean(costs[-window_size:])
        previous_cost = statistics.mean(costs[-window_size * 2:-window_size])

        recent_service = statistics.mean(service_levels[-window_size:])
        previous_service = statistics.mean(service_levels[-window_size * 2:-window_size])

        # Determine trend
        cost_change = (recent_cost - previous_cost) / previous_cost * 100
        service_change = (recent_service - previous_service) * 100

        if cost_change < -5 and service_change > 5:
            trend = "improving"
        elif cost_change > 10 or service_change < -10:
            trend = "degrading"
        else:
            trend = "stable"

        return {
            "trend": trend,
            "cost_change_pct": cost_change,
            "service_change_pct": service_change,
            "recent_avg_cost": recent_cost,
            "previous_avg_cost": previous_cost,
            "recent_avg_service": recent_service,
            "previous_avg_service": previous_service,
            "num_samples": len(logs),
            "window_size": window_size
        }

    def detect_performance_anomalies(
        self,
        scenario_user_id: int,
        threshold_std: float = 2.0
    ) -> List[Dict[str, Any]]:
        """
        Detect performance anomalies (outliers).

        Args:
            scenario_user_id: ScenarioUser to analyze
            threshold_std: Standard deviations for anomaly detection

        Returns:
            List of anomalous rounds with details
        """
        logs = self.db.query(AgentPerformanceLog).filter_by(
            scenario_user_id=scenario_user_id
        ).all()

        if len(logs) < 10:
            return []

        # Calculate mean and std for cost
        costs = [log.total_cost for log in logs]
        mean_cost = statistics.mean(costs)
        std_cost = statistics.stdev(costs)

        # Detect anomalies
        anomalies = []
        for log in logs:
            z_score = abs((log.total_cost - mean_cost) / std_cost) if std_cost > 0 else 0

            if z_score > threshold_std:
                anomalies.append({
                    "round_number": log.round_number,
                    "total_cost": log.total_cost,
                    "mean_cost": mean_cost,
                    "std_cost": std_cost,
                    "z_score": z_score,
                    "severity": "high" if z_score > 3.0 else "medium"
                })

        return anomalies

    def get_leaderboard(
        self,
        scenario_id: int,
        metric: str = "total_cost"
    ) -> List[Dict[str, Any]]:
        """
        Get scenario_user leaderboard sorted by performance metric.

        Args:
            scenario_id: Scenario to analyze
            metric: Metric to sort by (total_cost, service_level, etc.)

        Returns:
            List of scenario_users with aggregate metrics, sorted by performance
        """
        # Get all scenario_users in scenario
        scenario_users = self.db.query(ScenarioUser).filter_by(scenario_id=scenario_id).all()

        leaderboard = []
        for scenario_user in scenario_users:
            summary = self.get_agent_performance_summary(
                scenario_user_id=scenario_user.id,
                scenario_id=scenario_id
            )

            if summary.get("insufficient_data"):
                continue

            leaderboard.append({
                "scenario_user_id": scenario_user.id,
                "scenario_user_name": scenario_user.user.username if scenario_user.user else f"ScenarioUser {scenario_user.id}",
                "agent_type": scenario_user.agent_config.agent_type if scenario_user.agent_config else "manual",
                "agent_mode": scenario_user.agent_mode or "manual",
                **summary
            })

        # Sort by metric (lower cost = better, higher service = better)
        reverse = metric in ["service_level", "avg_service_level"]
        metric_key = f"avg_{metric}" if not metric.startswith("avg_") else metric

        leaderboard.sort(
            key=lambda x: x.get(metric_key, float('inf') if not reverse else 0),
            reverse=reverse
        )

        return leaderboard


# Database model for performance logs
class AgentPerformanceLog(Base):
    """
    Logs agent performance metrics per round.

    Used for:
    - Agent benchmarking and comparison
    - Performance trend analysis
    - Anomaly detection
    - RLHF training feedback
    """
    __tablename__ = "agent_performance_logs"

    id = Column(Integer, primary_key=True, index=True)
    scenario_user_id = Column(Integer, ForeignKey("scenario_users.id"), nullable=False, index=True)
    scenario_id = Column(Integer, ForeignKey("scenarios.id"), nullable=False, index=True)
    round_number = Column(Integer, nullable=False, index=True)

    agent_type = Column(String(20), nullable=False, index=True)  # llm, gnn, trm, manual
    agent_mode = Column(String(20), nullable=False)  # manual, copilot, autonomous

    # Cost metrics
    total_cost = Column(Float, nullable=False)
    holding_cost = Column(Float, nullable=False)
    shortage_cost = Column(Float, nullable=False)

    # Service metrics
    service_level = Column(Float, nullable=False)
    stockout_count = Column(Integer, nullable=False, default=0)
    backlog = Column(Integer, nullable=False, default=0)

    # Inventory metrics
    avg_inventory = Column(Float, nullable=False)
    inventory_variance = Column(Float, nullable=True)

    # Bullwhip metrics
    demand_amplification = Column(Float, nullable=True)
    order_variance = Column(Float, nullable=True)

    # Decision metrics
    order_quantity = Column(Integer, nullable=True)
    optimal_order = Column(Integer, nullable=True)
    decision_error = Column(Float, nullable=True)

    timestamp = Column(DateTime, nullable=False, index=True)


# Dependency injection
def get_agent_performance_tracker(db: Session) -> AgentPerformanceTracker:
    """FastAPI dependency for AgentPerformanceTracker."""
    return AgentPerformanceTracker(db)
