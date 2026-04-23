"""
Predictive Analytics Service with Explainable AI

Provides:
- Demand forecasting with uncertainty quantification
- Bullwhip effect prediction
- Cost trajectory forecasting
- What-if scenario analysis
- SHAP-based feature importance
- Attention visualization
"""

import numpy as np
import torch
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import logging
from dataclasses import dataclass, asdict

try:
    import shap
    SHAP_AVAILABLE = True
except ImportError:
    SHAP_AVAILABLE = False
    logging.warning("SHAP not available. Install with: pip install shap")

from app.models.supply_chain import ScenarioPeriod, ScenarioUserPeriod
from app.models.scenario import Scenario
from app.models.scenario_user import ScenarioUser

# Aliases for backwards compatibility
Game = Scenario
ScenarioUser = ScenarioUser

logger = logging.getLogger(__name__)


@dataclass
class ForecastResult:
    """Forecast result with uncertainty."""
    timestep: int
    value: float
    lower_bound: float
    upper_bound: float
    confidence: float


@dataclass
class BullwhipPrediction:
    """Bullwhip effect prediction."""
    node_id: int
    node_role: str
    current_ratio: float
    predicted_ratio: float
    risk_level: str  # "low", "medium", "high"
    contributing_factors: Dict[str, float]


@dataclass
class CostTrajectory:
    """Cost trajectory forecast."""
    node_id: int
    node_role: str
    current_cost: float
    forecasted_costs: List[float]
    expected_total: float
    risk_scenarios: Dict[str, List[float]]  # best, worst, likely


@dataclass
class FeatureImportance:
    """Feature importance analysis."""
    feature_name: str
    importance_score: float
    direction: str  # "increases", "decreases", "neutral"
    example_values: Dict[str, float]


class PredictiveAnalyticsService:
    """Service for predictive analytics and explainable AI."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.model = None  # Will be loaded from checkpoint
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    async def load_model(self, model_path: str):
        """Load trained GNN model for predictions."""
        try:
            self.model = torch.load(model_path, map_location=self.device)
            self.model.eval()
            logger.info(f"Loaded model from {model_path}")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            self.model = None

    async def forecast_demand(
        self,
        scenario_id: int,
        node_id: int,
        horizon: int = 10,
        confidence_level: float = 0.95
    ) -> List[ForecastResult]:
        """
        Forecast demand for a node over specified horizon.

        Args:
            scenario_id: Game ID
            node_id: Node/ScenarioUser ID
            horizon: Number of rounds to forecast
            confidence_level: Confidence level for bounds (default 0.95)

        Returns:
            forecasts: List of forecast results
        """
        # Get historical data
        historical_data = await self._get_historical_data(scenario_id, node_id, lookback=20)

        if len(historical_data) < 5:
            logger.warning(f"Insufficient data for forecasting (got {len(historical_data)} rounds)")
            return []

        # Simple time series forecasting (can be replaced with GNN predictions)
        forecasts = []

        # Extract demand series
        demands = [d["incoming_order"] for d in historical_data]

        # Calculate statistics
        mean_demand = np.mean(demands)
        std_demand = np.std(demands)

        # Detect trend
        if len(demands) >= 5:
            recent_mean = np.mean(demands[-5:])
            overall_mean = np.mean(demands)
            trend = (recent_mean - overall_mean) / (overall_mean + 1e-6)
        else:
            trend = 0

        # Generate forecasts
        for t in range(1, horizon + 1):
            # Simple trend + noise model
            base_forecast = mean_demand * (1 + trend * t * 0.1)

            # Uncertainty grows with horizon
            uncertainty = std_demand * np.sqrt(t) * 0.5

            # Confidence bounds (assuming normal distribution)
            z_score = 1.96 if confidence_level == 0.95 else 2.576  # 95% or 99%

            forecast = ForecastResult(
                timestep=t,
                value=base_forecast,
                lower_bound=max(0, base_forecast - z_score * uncertainty),
                upper_bound=base_forecast + z_score * uncertainty,
                confidence=confidence_level
            )
            forecasts.append(forecast)

        return forecasts

    async def predict_bullwhip(
        self,
        scenario_id: int
    ) -> List[BullwhipPrediction]:
        """
        Predict bullwhip effect for all nodes in a game.

        Args:
            scenario_id: Game ID

        Returns:
            predictions: Bullwhip predictions per node
        """
        # Get all scenario_users in game
        stmt = select(ScenarioUser).where(ScenarioUser.scenario_id == scenario_id)
        result = await self.db.execute(stmt)
        scenario_users = result.scalars().all()

        predictions = []

        for scenario_user in scenario_users:
            # Get historical orders and demands
            historical = await self._get_historical_data(scenario_id, scenario_user.id, lookback=20)

            if len(historical) < 10:
                continue

            # Calculate current bullwhip ratio
            orders_placed = [h["last_order_placed"] for h in historical if h["last_order_placed"] is not None]
            orders_received = [h["incoming_order"] for h in historical if h["incoming_order"] is not None]

            if len(orders_placed) < 5 or len(orders_received) < 5:
                continue

            std_placed = np.std(orders_placed)
            std_received = np.std(orders_received)
            current_ratio = std_placed / (std_received + 1e-6)

            # Predict future ratio (simple heuristic, can be replaced with ML model)
            recent_orders = orders_placed[-5:]
            recent_demands = orders_received[-5:]
            recent_ratio = np.std(recent_orders) / (np.std(recent_demands) + 1e-6)

            # Weighted average (more weight on recent)
            predicted_ratio = 0.7 * recent_ratio + 0.3 * current_ratio

            # Risk level
            if predicted_ratio < 1.2:
                risk_level = "low"
            elif predicted_ratio < 1.5:
                risk_level = "medium"
            else:
                risk_level = "high"

            # Contributing factors (simplified)
            contributing_factors = {
                "order_variability": std_placed / (np.mean(orders_placed) + 1e-6),
                "demand_variability": std_received / (np.mean(orders_received) + 1e-6),
                "lead_time_effect": 0.1 * (scenario_user.lead_time if hasattr(scenario_user, 'lead_time') else 2),
                "inventory_policy": 0.05  # Placeholder
            }

            prediction = BullwhipPrediction(
                node_id=scenario_user.id,
                node_role=scenario_user.role,
                current_ratio=current_ratio,
                predicted_ratio=predicted_ratio,
                risk_level=risk_level,
                contributing_factors=contributing_factors
            )
            predictions.append(prediction)

        return predictions

    async def forecast_cost_trajectory(
        self,
        scenario_id: int,
        node_id: int,
        horizon: int = 10
    ) -> CostTrajectory:
        """
        Forecast cost trajectory for a node.

        Args:
            scenario_id: Game ID
            node_id: Node/ScenarioUser ID
            horizon: Forecast horizon

        Returns:
            trajectory: Cost trajectory with scenarios
        """
        # Get historical data
        historical = await self._get_historical_data(scenario_id, node_id, lookback=20)

        if len(historical) < 5:
            raise ValueError("Insufficient historical data")

        # Extract cost data
        holding_costs = [h["holding_cost"] for h in historical]
        backlog_costs = [h["backlog_cost"] for h in historical]
        total_costs = [h["total_cost"] for h in historical]

        # Current cost
        current_cost = total_costs[-1] if total_costs else 0

        # Calculate average round cost
        recent_costs = total_costs[-10:] if len(total_costs) >= 10 else total_costs
        avg_round_cost = np.mean(np.diff(recent_costs)) if len(recent_costs) > 1 else np.mean(recent_costs)

        # Forecasted costs (best, likely, worst)
        forecasted_costs_likely = []
        forecasted_costs_best = []
        forecasted_costs_worst = []

        std_cost = np.std(np.diff(recent_costs)) if len(recent_costs) > 1 else np.std(recent_costs)

        for t in range(1, horizon + 1):
            # Likely scenario (extrapolate trend)
            likely_cost = current_cost + avg_round_cost * t
            forecasted_costs_likely.append(likely_cost)

            # Best case (20% reduction)
            best_cost = current_cost + avg_round_cost * 0.8 * t
            forecasted_costs_best.append(best_cost)

            # Worst case (50% increase)
            worst_cost = current_cost + avg_round_cost * 1.5 * t
            forecasted_costs_worst.append(worst_cost)

        trajectory = CostTrajectory(
            node_id=node_id,
            node_role=historical[-1]["role"] if historical else "Unknown",
            current_cost=current_cost,
            forecasted_costs=forecasted_costs_likely,
            expected_total=forecasted_costs_likely[-1] if forecasted_costs_likely else current_cost,
            risk_scenarios={
                "best": forecasted_costs_best,
                "likely": forecasted_costs_likely,
                "worst": forecasted_costs_worst
            }
        )

        return trajectory

    async def explain_prediction(
        self,
        scenario_id: int,
        node_id: int,
        round_number: int
    ) -> Dict[str, Any]:
        """
        Explain a prediction using SHAP values.

        Args:
            scenario_id: Game ID
            node_id: Node/ScenarioUser ID
            round_number: Round number to explain

        Returns:
            explanation: Dictionary with SHAP values and interpretation
        """
        if not SHAP_AVAILABLE:
            return {
                "error": "SHAP not available",
                "message": "Install SHAP for explainability: pip install shap"
            }

        if self.model is None:
            return {
                "error": "Model not loaded",
                "message": "Load a trained model first"
            }

        # Get data for this round
        historical = await self._get_historical_data(scenario_id, node_id, lookback=10)

        if not historical:
            return {"error": "No data found"}

        # Prepare features (simplified)
        features = self._prepare_features(historical)

        # SHAP explainer (simplified - full implementation needs background data)
        try:
            # Create a wrapper function for model prediction
            def model_predict(X):
                # Convert to torch tensor
                X_tensor = torch.FloatTensor(X).to(self.device)
                with torch.no_grad():
                    output = self.model(X_tensor)
                return output.cpu().numpy()

            # Use Kernel SHAP (model-agnostic)
            explainer = shap.KernelExplainer(model_predict, features[:100])  # Use subset as background
            shap_values = explainer.shap_values(features[-1:])

            # Feature names
            feature_names = [
                "inventory", "backlog", "incoming_shipment", "incoming_order",
                "last_order", "round_number", "holding_cost", "backlog_cost"
            ]

            # Create feature importance list
            feature_importances = []
            for i, (name, value) in enumerate(zip(feature_names, shap_values[0])):
                importance = FeatureImportance(
                    feature_name=name,
                    importance_score=abs(float(value)),
                    direction="increases" if value > 0 else "decreases" if value < 0 else "neutral",
                    example_values={
                        "current": float(features[-1][i]),
                        "shap_value": float(value)
                    }
                )
                feature_importances.append(importance)

            # Sort by importance
            feature_importances.sort(key=lambda x: x.importance_score, reverse=True)

            return {
                "node_id": node_id,
                "round_number": round_number,
                "feature_importances": [asdict(fi) for fi in feature_importances],
                "interpretation": self._interpret_shap_values(feature_importances)
            }

        except Exception as e:
            logger.error(f"SHAP explanation failed: {e}")
            return {
                "error": "Explanation failed",
                "message": str(e)
            }

    def _interpret_shap_values(self, feature_importances: List[FeatureImportance]) -> str:
        """Generate natural language interpretation of SHAP values."""
        top_3 = feature_importances[:3]

        interpretation = "The prediction is most influenced by: "
        factors = []

        for fi in top_3:
            if fi.direction == "increases":
                factors.append(f"{fi.feature_name} (increases order quantity)")
            elif fi.direction == "decreases":
                factors.append(f"{fi.feature_name} (decreases order quantity)")

        interpretation += ", ".join(factors)
        return interpretation

    async def analyze_what_if(
        self,
        scenario_id: int,
        node_id: int,
        scenarios: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze what-if scenarios.

        Args:
            scenario_id: Game ID
            node_id: Node/ScenarioUser ID
            scenarios: List of scenarios to test
                Each scenario: {"name": "...", "changes": {"inventory": 20, ...}}

        Returns:
            analysis: Scenario comparison
        """
        # Get baseline data
        historical = await self._get_historical_data(scenario_id, node_id, lookback=10)
        baseline_features = self._prepare_features(historical)

        results = {
            "baseline": {
                "name": "Current State",
                "predicted_order": await self._predict_order(baseline_features[-1]),
                "predicted_cost": await self._predict_cost(baseline_features[-1])
            },
            "scenarios": []
        }

        for scenario in scenarios:
            # Modify features according to scenario
            modified_features = baseline_features[-1].copy()

            for key, value in scenario.get("changes", {}).items():
                # Map feature names to indices (simplified)
                feature_map = {
                    "inventory": 0,
                    "backlog": 1,
                    "incoming_shipment": 2,
                    "incoming_order": 3,
                    "last_order": 4
                }
                if key in feature_map:
                    modified_features[feature_map[key]] = value

            scenario_result = {
                "name": scenario.get("name", "Unnamed Scenario"),
                "changes": scenario.get("changes", {}),
                "predicted_order": await self._predict_order(modified_features),
                "predicted_cost": await self._predict_cost(modified_features),
                "delta_vs_baseline": {}
            }

            # Calculate deltas
            scenario_result["delta_vs_baseline"] = {
                "order": scenario_result["predicted_order"] - results["baseline"]["predicted_order"],
                "cost": scenario_result["predicted_cost"] - results["baseline"]["predicted_cost"]
            }

            results["scenarios"].append(scenario_result)

        return results

    async def _get_historical_data(
        self,
        scenario_id: int,
        scenario_user_id: int,
        lookback: int = 20
    ) -> List[Dict[str, Any]]:
        """Get historical data for a scenario_user."""
        stmt = (
            select(ScenarioUserPeriod)
            .where(and_(
                ScenarioUserPeriod.scenario_id == scenario_id,
                ScenarioUserPeriod.scenario_user_id == scenario_user_id
            ))
            .order_by(ScenarioUserPeriod.round_number.desc())
            .limit(lookback)
        )

        result = await self.db.execute(stmt)
        rounds = result.scalars().all()

        # Convert to list of dicts (most recent first)
        data = []
        for round_data in reversed(rounds):  # Reverse to chronological order
            data.append({
                "round_number": round_data.round_number,
                "inventory": round_data.inventory_end,
                "backlog": round_data.backlog,
                "incoming_order": round_data.incoming_order,
                "incoming_shipment": round_data.incoming_shipment,
                "last_order_placed": round_data.order_placed,
                "holding_cost": round_data.holding_cost,
                "backlog_cost": round_data.backlog_cost,
                "total_cost": round_data.total_cost,
                "role": round_data.scenario_user.role if hasattr(round_data, 'scenario_user') else "Unknown"
            })

        return data

    def _prepare_features(self, historical_data: List[Dict[str, Any]]) -> np.ndarray:
        """Prepare feature matrix from historical data."""
        features = []

        for round_data in historical_data:
            feature_vec = [
                round_data.get("inventory", 0),
                round_data.get("backlog", 0),
                round_data.get("incoming_shipment", 0),
                round_data.get("incoming_order", 0),
                round_data.get("last_order_placed", 0),
                round_data.get("round_number", 0) / 52.0,  # Normalized
                round_data.get("holding_cost", 0),
                round_data.get("backlog_cost", 0)
            ]
            features.append(feature_vec)

        return np.array(features, dtype=np.float32)

    async def _predict_order(self, features: np.ndarray) -> float:
        """Predict order quantity from features."""
        if self.model is None:
            # Fallback heuristic
            inventory = features[0]
            backlog = features[1]
            incoming_order = features[3]
            target_stock = 20
            return max(0, target_stock - inventory + backlog + incoming_order)

        # Use model
        with torch.no_grad():
            X = torch.FloatTensor(features).unsqueeze(0).to(self.device)
            output = self.model(X)
            predicted_order = output.item()
            return max(0, predicted_order)

    async def _predict_cost(self, features: np.ndarray) -> float:
        """Predict cost from features using historically-derived cost rates.

        features[6] = holding_cost (actual per-period cost from ScenarioUserPeriod.holding_cost)
        features[7] = backlog_cost (actual per-period cost from ScenarioUserPeriod.backlog_cost)

        Cost rates are derived from actual historical costs divided by their corresponding
        quantities to ensure rates reflect real InvPolicy data, not hardcoded Beer Game values.
        """
        inventory = float(features[0])
        backlog = float(features[1])
        last_holding_cost = float(features[6])  # actual historical holding cost
        last_backlog_cost = float(features[7])   # actual historical backlog cost

        # Derive effective rates from historical actuals
        # (avoids hardcoding Beer Game-specific $0.50/$1.00 defaults)
        holding_cost_rate = last_holding_cost / inventory if inventory > 0 else last_holding_cost
        backlog_cost_rate = last_backlog_cost / backlog if backlog > 0 else last_backlog_cost

        return inventory * holding_cost_rate + backlog * backlog_cost_rate

    async def generate_insights_report(
        self,
        scenario_id: int
    ) -> Dict[str, Any]:
        """
        Generate comprehensive insights report for a game.

        Args:
            scenario_id: Game ID

        Returns:
            report: Comprehensive analytics report
        """
        # Get all scenario_users
        stmt = select(ScenarioUser).where(ScenarioUser.scenario_id == scenario_id)
        result = await self.db.execute(stmt)
        scenario_users = result.scalars().all()

        insights = {
            "scenario_id": scenario_id,
            "generated_at": datetime.utcnow().isoformat(),
            "demand_forecasts": {},
            "bullwhip_predictions": [],
            "cost_trajectories": {},
            "risk_assessment": {},
            "recommendations": []
        }

        # Demand forecasts for each scenario_user
        for scenario_user in scenario_users:
            try:
                forecast = await self.forecast_demand(scenario_id, scenario_user.id, horizon=10)
                insights["demand_forecasts"][scenario_user.role] = [asdict(f) for f in forecast]
            except Exception as e:
                logger.error(f"Forecast failed for scenario_user {scenario_user.id}: {e}")

        # Bullwhip predictions
        try:
            bullwhip_preds = await self.predict_bullwhip(scenario_id)
            insights["bullwhip_predictions"] = [asdict(bp) for bp in bullwhip_preds]
        except Exception as e:
            logger.error(f"Bullwhip prediction failed: {e}")

        # Cost trajectories
        for scenario_user in scenario_users:
            try:
                trajectory = await self.forecast_cost_trajectory(scenario_id, scenario_user.id, horizon=10)
                insights["cost_trajectories"][scenario_user.role] = asdict(trajectory)
            except Exception as e:
                logger.error(f"Cost trajectory failed for scenario_user {scenario_user.id}: {e}")

        # Risk assessment
        insights["risk_assessment"] = self._assess_overall_risk(insights)

        # Recommendations
        insights["recommendations"] = self._generate_recommendations(insights)

        return insights

    def _assess_overall_risk(self, insights: Dict[str, Any]) -> Dict[str, Any]:
        """Assess overall risk from insights."""
        risk_factors = []
        risk_score = 0

        # Check bullwhip
        for bp in insights.get("bullwhip_predictions", []):
            if bp["risk_level"] == "high":
                risk_factors.append(f"High bullwhip risk at {bp['node_role']}")
                risk_score += 30
            elif bp["risk_level"] == "medium":
                risk_score += 15

        # Check cost trends
        for role, trajectory in insights.get("cost_trajectories", {}).items():
            worst_case = trajectory["risk_scenarios"]["worst"][-1]
            current = trajectory["current_cost"]
            if worst_case > current * 1.5:
                risk_factors.append(f"High cost risk for {role}")
                risk_score += 25

        # Overall risk level
        if risk_score >= 50:
            risk_level = "high"
        elif risk_score >= 25:
            risk_level = "medium"
        else:
            risk_level = "low"

        return {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "risk_factors": risk_factors
        }

    def _generate_recommendations(self, insights: Dict[str, Any]) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []

        # Bullwhip recommendations
        for bp in insights.get("bullwhip_predictions", []):
            if bp["risk_level"] in ["medium", "high"]:
                recommendations.append(
                    f"Reduce order variability at {bp['node_role']} to mitigate bullwhip effect. "
                    f"Consider smoothing orders or sharing demand information."
                )

        # Cost recommendations
        for role, trajectory in insights.get("cost_trajectories", {}).items():
            if trajectory["expected_total"] > trajectory["current_cost"] * 1.3:
                recommendations.append(
                    f"Cost trajectory for {role} is increasing. Review ordering policy and inventory targets."
                )

        # General recommendations
        if len(recommendations) == 0:
            recommendations.append("Supply chain performance is stable. Continue monitoring key metrics.")

        return recommendations
