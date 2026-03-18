"""
Risk Detection Service
Implements ML-based risk identification for supply chain insights
Sprint 1: Enhanced Insights & Risk Analysis

Production implementation using InvLevel, InvPolicy, Forecast, and VendorLeadTime models.
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta, date
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, desc
import numpy as np
from scipy import stats
import statistics

from app.models.supply_chain_config import Site
from app.models.compatibility import Item
from app.models.sc_entities import Forecast, InvLevel, InvPolicy, Product
from app.models.supplier import VendorLeadTime


class RiskDetectionService:
    """
    Service for detecting supply chain risks using ML and statistical methods.

    Risk Types:
    - Stock-out: Probability of inventory depletion
    - Overstock: Excess inventory above optimal levels
    - Vendor Lead Time Variance: Unreliable supplier performance
    """

    def __init__(self, db: Session):
        self.db = db

        # Risk thresholds
        self.STOCKOUT_CRITICAL = 80  # >80% probability = CRITICAL
        self.STOCKOUT_HIGH = 60      # 60-80% = HIGH
        self.STOCKOUT_MEDIUM = 40    # 40-60% = MEDIUM

        self.OVERSTOCK_CRITICAL_DAYS = 180  # >180 DOS = CRITICAL
        self.OVERSTOCK_HIGH_DAYS = 120      # 120-180 DOS = HIGH
        self.OVERSTOCK_MEDIUM_DAYS = 90     # 90-120 DOS = MEDIUM

    def _calculate_severity(self, probability: float) -> str:
        """Calculate severity level from probability."""
        if probability >= self.STOCKOUT_CRITICAL:
            return "CRITICAL"
        elif probability >= self.STOCKOUT_HIGH:
            return "HIGH"
        elif probability >= self.STOCKOUT_MEDIUM:
            return "MEDIUM"
        else:
            return "LOW"

    def _calculate_overstock_severity(self, days_of_supply: float) -> str:
        """Calculate overstock severity from days of supply."""
        if days_of_supply >= self.OVERSTOCK_CRITICAL_DAYS:
            return "CRITICAL"
        elif days_of_supply >= self.OVERSTOCK_HIGH_DAYS:
            return "HIGH"
        elif days_of_supply >= self.OVERSTOCK_MEDIUM_DAYS:
            return "MEDIUM"
        else:
            return "LOW"

    async def detect_stockout_risk(
        self,
        product_id: str,
        site_id: str,
        horizon_days: int = 30
    ) -> Dict:
        """
        Detect stock-out risk using real inventory data.

        Algorithm:
        1. Get current inventory level
        2. Get demand forecast for horizon
        3. Get inventory policy (safety stock)
        4. Calculate days until stockout
        5. Compute probability based on demand variance
        """
        # Get latest inventory level
        inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.product_id == product_id,
                InvLevel.site_id == site_id
            )
        ).order_by(desc(InvLevel.inventory_date)).first()

        if not inv_level:
            return {
                "product_id": product_id,
                "site_id": site_id,
                "probability": 0,
                "days_until_stockout": None,
                "severity": "LOW",
                "factors": {
                    "message": "No inventory data available",
                    "current_inventory": 0,
                    "safety_stock": 0,
                    "daily_demand": 0
                },
                "recommended_action": "Initialize inventory tracking",
            }

        # Get available inventory (on-hand - allocated + in-transit)
        available_qty = (inv_level.on_hand_qty or 0) - (inv_level.allocated_qty or 0) + (inv_level.in_transit_qty or 0)

        # Get demand forecast for next horizon_days
        forecast_start = date.today()
        forecast_end = forecast_start + timedelta(days=horizon_days)

        forecasts = self.db.query(Forecast).filter(
            and_(
                Forecast.product_id == product_id,
                Forecast.site_id == site_id,
                Forecast.forecast_date >= forecast_start,
                Forecast.forecast_date <= forecast_end,
                Forecast.is_active == "true"
            )
        ).all()

        if not forecasts:
            # No forecast data - use simple heuristic
            return {
                "product_id": product_id,
                "site_id": site_id,
                "probability": 50 if available_qty < 100 else 10,
                "days_until_stockout": int(available_qty / 10) if available_qty > 0 else 0,
                "severity": "MEDIUM" if available_qty < 100 else "LOW",
                "factors": {
                    "current_inventory": round(available_qty, 2),
                    "daily_demand": 10.0,
                    "safety_stock": 0,
                    "message": "No demand forecast available"
                },
                "recommended_action": "Review inventory policy and generate demand forecast",
            }

        # Calculate total forecasted demand
        total_demand = sum(f.forecast_quantity or f.forecast_p50 or 0 for f in forecasts)
        avg_daily_demand = total_demand / len(forecasts) if forecasts else 0

        # Calculate demand standard deviation (from P10/P90 if available)
        if any(f.forecast_std_dev for f in forecasts):
            demand_std_dev = statistics.mean([f.forecast_std_dev for f in forecasts if f.forecast_std_dev])
        elif any(f.forecast_p10 and f.forecast_p90 for f in forecasts):
            # Estimate std dev from P10/P90 (roughly 2.56 std devs apart)
            p10_p90_ranges = [(f.forecast_p90 - f.forecast_p10) for f in forecasts if f.forecast_p10 and f.forecast_p90]
            demand_std_dev = statistics.mean(p10_p90_ranges) / 2.56 if p10_p90_ranges else avg_daily_demand * 0.3
        else:
            # Default: 30% coefficient of variation
            demand_std_dev = avg_daily_demand * 0.3

        # Get safety stock from inventory policy
        inv_policy = self.db.query(InvPolicy).filter(
            and_(
                InvPolicy.product_id == product_id,
                InvPolicy.site_id == site_id,
                InvPolicy.is_active == "true"
            )
        ).first()

        safety_stock = 0
        if inv_policy:
            if inv_policy.ss_policy == "abs_level":
                safety_stock = inv_policy.ss_quantity or 0
            elif inv_policy.ss_policy in ["doc_dem", "doc_fcst"]:
                safety_stock = avg_daily_demand * (inv_policy.ss_days or 0)
            elif inv_policy.ss_policy == "sl" and inv_policy.service_level:
                # Z-score approximation for service level
                from math import sqrt
                z_score = {0.95: 1.65, 0.97: 1.88, 0.99: 2.33}.get(inv_policy.service_level, 1.65)
                # Assuming lead time of 7 days (should get from sourcing rules)
                lead_time = 7
                safety_stock = z_score * demand_std_dev * sqrt(lead_time)

        # Calculate days until stockout
        net_available = available_qty - safety_stock
        days_until_stockout = int(net_available / avg_daily_demand) if avg_daily_demand > 0 else 999

        # Calculate stockout probability using normal distribution approximation
        if avg_daily_demand > 0 and demand_std_dev > 0:
            # Z-score: how many std devs is current inventory above expected demand
            z_score = (available_qty - total_demand) / (demand_std_dev * (len(forecasts) ** 0.5))

            # Convert z-score to probability (rough approximation)
            if z_score >= 2:
                probability = 2
            elif z_score >= 1:
                probability = 16
            elif z_score >= 0:
                probability = 50
            elif z_score >= -1:
                probability = 84
            elif z_score >= -2:
                probability = 98
            else:
                probability = 99
        else:
            probability = 50

        # Adjust probability based on days until stockout
        if days_until_stockout <= 7:
            probability = min(probability + 30, 99)
        elif days_until_stockout <= 14:
            probability = min(probability + 15, 95)

        severity = self._calculate_severity(probability)

        factors = {
            "current_inventory": round(available_qty, 2),
            "safety_stock": round(safety_stock, 2),
            "daily_demand": round(avg_daily_demand, 2),
            "total_demand": round(total_demand, 2),
            "days_of_supply": round(available_qty / avg_daily_demand if avg_daily_demand > 0 else 0, 1),
        }

        if demand_std_dev > avg_daily_demand * 0.5:
            factors["high_variability"] = f"CV: {round(demand_std_dev/avg_daily_demand*100, 1)}%"

        recommended_action = "Monitor inventory levels"
        if severity == "CRITICAL":
            recommended_action = f"URGENT: Expedite emergency order for {product_id}"
        elif severity == "HIGH":
            recommended_action = f"Accelerate replenishment order for {product_id}"
        elif severity == "MEDIUM":
            recommended_action = f"Review and adjust order quantities for {product_id}"

        return {
            "product_id": product_id,
            "site_id": site_id,
            "probability": round(probability, 1),
            "days_until_stockout": max(0, days_until_stockout),
            "severity": severity,
            "factors": factors,
            "recommended_action": recommended_action,
        }

    async def detect_overstock_risk(
        self,
        product_id: str,
        site_id: str,
        threshold_days: int = 90
    ) -> Dict:
        """
        Detect overstock risk using real inventory and forecast data.

        Algorithm:
        1. Get current inventory level
        2. Get average daily demand from recent forecasts
        3. Calculate days of supply
        4. Compare against optimal inventory policy
        """
        # Get latest inventory level
        inv_level = self.db.query(InvLevel).filter(
            and_(
                InvLevel.product_id == product_id,
                InvLevel.site_id == site_id
            )
        ).order_by(desc(InvLevel.inventory_date)).first()

        if not inv_level:
            return {
                "product_id": product_id,
                "site_id": site_id,
                "excess_quantity": 0,
                "days_of_supply": 0,
                "severity": "LOW",
                "cost_impact": 0,
                "factors": {
                    "message": "No inventory data available"
                },
                "recommended_action": "Initialize inventory tracking",
            }

        available_qty = inv_level.on_hand_qty or 0

        # Get recent forecasts to calculate daily demand
        forecast_start = date.today() - timedelta(days=30)
        forecast_end = date.today() + timedelta(days=30)

        forecasts = self.db.query(Forecast).filter(
            and_(
                Forecast.product_id == product_id,
                Forecast.site_id == site_id,
                Forecast.forecast_date >= forecast_start,
                Forecast.forecast_date <= forecast_end,
                Forecast.is_active == "true"
            )
        ).all()

        if not forecasts:
            return {
                "product_id": product_id,
                "site_id": site_id,
                "excess_quantity": 0,
                "days_of_supply": 0,
                "severity": "LOW",
                "cost_impact": 0,
                "factors": {
                    "current_inventory": round(available_qty, 2),
                    "message": "No demand forecast available"
                },
                "recommended_action": "Generate demand forecast to assess overstock risk",
            }

        avg_daily_demand = sum(f.forecast_quantity or f.forecast_p50 or 0 for f in forecasts) / len(forecasts)

        if avg_daily_demand <= 0:
            days_of_supply = 999
        else:
            days_of_supply = available_qty / avg_daily_demand

        # Get inventory policy to determine optimal inventory
        inv_policy = self.db.query(InvPolicy).filter(
            and_(
                InvPolicy.product_id == product_id,
                InvPolicy.site_id == site_id,
                InvPolicy.is_active == "true"
            )
        ).first()

        optimal_inventory = 0
        if inv_policy:
            if inv_policy.ss_policy == "abs_level":
                optimal_inventory = inv_policy.ss_quantity or 0
            elif inv_policy.ss_policy in ["doc_dem", "doc_fcst"]:
                optimal_inventory = avg_daily_demand * (inv_policy.ss_days or 0)
            elif inv_policy.order_up_to_level:
                optimal_inventory = inv_policy.order_up_to_level
        else:
            # Default: 30 days of supply
            optimal_inventory = avg_daily_demand * 30

        excess_qty = max(0, available_qty - optimal_inventory)

        # Get unit holding cost from Product or fall back to $10/unit
        unit_holding_cost = 10.0
        if product_id:
            from app.models.sc_entities import Product as ProductModel
            prod = self.db.query(ProductModel).filter(ProductModel.id == product_id).first()
            if prod and hasattr(prod, 'unit_cost') and prod.unit_cost:
                unit_holding_cost = float(prod.unit_cost) * 0.25 / 365  # 25% annual holding rate / daily
        cost_impact = excess_qty * unit_holding_cost

        severity = self._calculate_overstock_severity(days_of_supply)

        factors = {
            "current_inventory": round(available_qty, 2),
            "optimal_inventory": round(optimal_inventory, 2),
            "daily_demand": round(avg_daily_demand, 2),
            "days_of_supply": round(days_of_supply, 1),
        }

        recommended_action = "Monitor inventory levels"
        if severity == "CRITICAL":
            recommended_action = f"URGENT: Liquidate excess inventory for {product_id}"
        elif severity == "HIGH":
            recommended_action = f"Reduce replenishment orders for {product_id}"
        elif severity == "MEDIUM":
            recommended_action = f"Review inventory policy for {product_id}"

        return {
            "product_id": product_id,
            "site_id": site_id,
            "excess_quantity": round(excess_qty, 2),
            "days_of_supply": round(days_of_supply, 1),
            "severity": severity,
            "cost_impact": round(cost_impact, 2),
            "factors": factors,
            "recommended_action": recommended_action,
        }

    async def predict_vendor_leadtime(
        self,
        vendor_id: str,
        product_id: str,
        site_id: str
    ) -> Dict:
        """
        Predict vendor lead time using historical data.

        Returns P10/P50/P90 percentiles and reliability score.
        """
        # Get historical lead times
        lead_times = self.db.query(VendorLeadTime).filter(
            and_(
                VendorLeadTime.vendor_id == vendor_id,
                VendorLeadTime.product_id == product_id,
                VendorLeadTime.destination_site_id == site_id
            )
        ).all()

        if not lead_times or len(lead_times) == 0:
            return {
                "p10_days": 0,
                "p50_days": 0,
                "p90_days": 0,
                "reliability_score": 0,
                "variance": 0,
                "coefficient_of_variation": 0,
                "recommended_action": "No historical lead time data available",
                "sample_size": 0
            }

        # Use real data
        lt_values = [lt.lead_time_days or lt.p50_days or 7.0 for lt in lead_times]
        p10 = np.percentile(lt_values, 10)
        p50 = np.percentile(lt_values, 50)
        p90 = np.percentile(lt_values, 90)
        variance = np.var(lt_values)
        mean_lt = np.mean(lt_values)
        cv = (np.std(lt_values) / mean_lt * 100) if mean_lt > 0 else 0

        # Calculate reliability score (100 = perfect, 0 = unreliable)
        if cv <= 10:
            reliability_score = 100
        elif cv <= 20:
            reliability_score = 90
        elif cv <= 30:
            reliability_score = 80
        else:
            reliability_score = max(40, 90 - cv)

        severity = "LOW"
        if cv > 40:
            severity = "CRITICAL"
        elif cv > 30:
            severity = "HIGH"
        elif cv > 20:
            severity = "MEDIUM"

        recommended_action = "Vendor performance is acceptable"
        if severity == "CRITICAL":
            recommended_action = f"URGENT: Qualify alternative vendors for {product_id}"
        elif severity == "HIGH":
            recommended_action = f"Review vendor contract and performance for {product_id}"
        elif severity == "MEDIUM":
            recommended_action = f"Monitor vendor lead times for {product_id}"

        return {
            "p10_days": round(p10, 1),
            "p50_days": round(p50, 1),
            "p90_days": round(p90, 1),
            "reliability_score": round(reliability_score, 1),
            "variance": round(variance, 2),
            "coefficient_of_variation": round(cv, 1),
            "severity": severity,
            "recommended_action": recommended_action,
            "sample_size": len(lt_values)
        }

    def _build_resolution_condition(self, alert_type: str, result: Dict) -> Dict:
        """
        Capture the condition that must change for an alert to be auto-resolved.

        The condition encodes what metric, threshold, and operator the agent
        monitors. When the condition is no longer met, the alert moves to
        ACTIONED (auto-resolved without human intervention).
        """
        if alert_type == "STOCKOUT":
            return {
                "metric": "stockout_probability",
                "operator": "lt",
                "threshold": self.STOCKOUT_MEDIUM,
                "current_value": result.get("probability"),
                "description": (
                    f"Stock-out probability must drop below {self.STOCKOUT_MEDIUM}% "
                    f"(currently {result.get('probability', '?')}%)"
                ),
            }
        elif alert_type == "OVERSTOCK":
            return {
                "metric": "days_of_supply",
                "operator": "lt",
                "threshold": self.OVERSTOCK_MEDIUM_DAYS,
                "current_value": result.get("days_of_supply"),
                "description": (
                    f"Days of supply must drop below {self.OVERSTOCK_MEDIUM_DAYS} days "
                    f"(currently {result.get('days_of_supply', '?')} days)"
                ),
            }
        elif alert_type == "VENDOR_LEADTIME":
            return {
                "metric": "coefficient_of_variation",
                "operator": "lt",
                "threshold": 20.0,
                "current_value": result.get("coefficient_of_variation"),
                "description": (
                    f"Vendor lead time CV must drop below 20% "
                    f"(currently {result.get('coefficient_of_variation', '?')}%)"
                ),
            }
        return {}

    def _evaluate_resolution_condition(self, condition: Dict, result: Dict) -> bool:
        """
        Evaluate whether the stored resolution condition is now met.

        Returns True if the condition is satisfied (alert should be resolved).
        """
        if not condition or "metric" not in condition:
            return False

        metric = condition["metric"]
        operator = condition["operator"]
        threshold = condition["threshold"]

        # Map metric names to result keys
        value = result.get(metric)
        if value is None:
            # Try alternate key mappings
            alt_keys = {
                "stockout_probability": "probability",
                "days_of_supply": "days_of_supply",
                "coefficient_of_variation": "coefficient_of_variation",
            }
            value = result.get(alt_keys.get(metric, metric))

        if value is None:
            return False

        if operator == "lt":
            return value < threshold
        elif operator == "gt":
            return value > threshold
        elif operator == "lte":
            return value <= threshold
        elif operator == "gte":
            return value >= threshold
        return False

    async def resolve_informed_alerts(self) -> Dict[str, int]:
        """
        Re-evaluate all INFORMED risk alerts against their stored resolution
        conditions.

        Each alert carries a `resolution_condition` that describes what must
        change for auto-resolution. When the condition is met, the alert moves
        to ACTIONED — the agent auto-resolved it without human intervention.

        Returns counts of resolved vs still-active alerts.
        """
        from app.models.risk import RiskAlert

        informed_alerts = (
            self.db.query(RiskAlert)
            .filter(RiskAlert.status == "INFORMED")
            .all()
        )

        resolved_count = 0
        still_informed = 0

        for alert in informed_alerts:
            # Re-evaluate current conditions
            result = {}
            if alert.type == "STOCKOUT":
                result = await self.detect_stockout_risk(
                    alert.product_id, alert.site_id
                )
            elif alert.type == "OVERSTOCK":
                result = await self.detect_overstock_risk(
                    alert.product_id, alert.site_id
                )
            elif alert.type == "VENDOR_LEADTIME" and alert.vendor_id:
                result = await self.predict_vendor_leadtime(
                    alert.vendor_id, alert.product_id, alert.site_id
                )

            # Use stored condition if available, else fall back to type-based check
            condition = alert.resolution_condition
            if condition:
                is_resolved = self._evaluate_resolution_condition(condition, result)
            else:
                # Legacy alerts without stored condition — build and store one
                condition = self._build_resolution_condition(alert.type, result)
                alert.resolution_condition = condition
                is_resolved = self._evaluate_resolution_condition(condition, result)

            if is_resolved:
                alert.status = "ACTIONED"
                alert.resolved_at = datetime.utcnow()
                alert.resolution_notes = (
                    f"Auto-resolved: {condition.get('description', 'condition no longer met')}"
                )
                resolved_count += 1
            else:
                still_informed += 1

        if resolved_count > 0 or informed_alerts:
            self.db.commit()

        return {
            "resolved": resolved_count,
            "still_informed": still_informed,
        }

    async def generate_risk_alerts(
        self,
        config_id: Optional[int] = None,
        severity_filter: Optional[str] = None
    ) -> List[Dict]:
        """
        Generate risk alerts by scanning all product-site combinations.

        Returns list of alerts sorted by severity.
        """
        # Get all active inventory levels (represents product-site combinations with data)
        subquery = self.db.query(
            InvLevel.product_id,
            InvLevel.site_id,
            func.max(InvLevel.inventory_date).label('max_date')
        ).group_by(
            InvLevel.product_id,
            InvLevel.site_id
        )

        if config_id:
            subquery = subquery.filter(InvLevel.config_id == config_id)

        product_site_combos = subquery.limit(100).all()  # Limit to 100 for performance

        alerts = []

        for product_id, site_id, _ in product_site_combos:
            # Check stockout risk
            stockout_risk = await self.detect_stockout_risk(product_id, site_id)

            if stockout_risk["probability"] >= self.STOCKOUT_MEDIUM:
                if severity_filter is None or stockout_risk["severity"] == severity_filter:
                    alerts.append({
                        "alert_id": f"SO-{product_id}-{site_id}",
                        "type": "STOCKOUT",
                        "product_id": product_id,
                        "site_id": site_id,
                        "severity": stockout_risk["severity"],
                        "probability": stockout_risk["probability"],
                        "days_until_stockout": stockout_risk["days_until_stockout"],
                        "message": f"Stock-out risk: {stockout_risk['days_until_stockout']} days until depletion",
                        "recommended_action": stockout_risk["recommended_action"],
                        "created_at": datetime.utcnow(),
                        "factors": stockout_risk["factors"],
                        "resolution_condition": self._build_resolution_condition("STOCKOUT", stockout_risk),
                    })

            # Check overstock risk
            overstock_risk = await self.detect_overstock_risk(product_id, site_id)

            if overstock_risk["severity"] in ["MEDIUM", "HIGH", "CRITICAL"]:
                if severity_filter is None or overstock_risk["severity"] == severity_filter:
                    alerts.append({
                        "alert_id": f"OS-{product_id}-{site_id}",
                        "type": "OVERSTOCK",
                        "product_id": product_id,
                        "site_id": site_id,
                        "severity": overstock_risk["severity"],
                        "days_of_supply": overstock_risk["days_of_supply"],
                        "excess_quantity": overstock_risk["excess_quantity"],
                        "cost_impact": overstock_risk["cost_impact"],
                        "message": f"Excess inventory: {overstock_risk['days_of_supply']:.0f} days of supply",
                        "recommended_action": overstock_risk["recommended_action"],
                        "created_at": datetime.utcnow(),
                        "factors": overstock_risk["factors"],
                        "resolution_condition": self._build_resolution_condition("OVERSTOCK", overstock_risk),
                    })

        # Sort by severity
        severity_order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
        alerts.sort(key=lambda x: severity_order.get(x["severity"], 4))

        return alerts[:50]  # Return top 50
