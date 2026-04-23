"""
Visibility Dashboard Service
Phase 7 Sprint 4 - Feature 3: Supply Chain Visibility

Provides opt-in supply chain visibility with:
- Supply chain health scoring
- Bottleneck detection
- Bullwhip effect severity measurement
- Visibility sharing permissions
- Historical snapshots
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
import logging

logger = logging.getLogger(__name__)


class VisibilityService:
    """
    Service for supply chain visibility and health monitoring.

    Features:
    - Calculate supply chain health score (0-100)
    - Detect bottlenecks in the supply chain
    - Measure bullwhip effect severity
    - Manage visibility sharing permissions
    - Create and retrieve visibility snapshots
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    # =============================================================================
    # HEALTH SCORE CALCULATION
    # =============================================================================

    async def calculate_supply_chain_health(
        self,
        scenario_id: int,
        round_number: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Calculate overall supply chain health score (0-100).

        Health score combines:
        - Inventory balance (30%): Optimal inventory levels across nodes
        - Service level (25%): Customer demand fulfillment
        - Cost efficiency (20%): Total supply chain costs
        - Order stability (15%): Bullwhip effect severity
        - Backlog pressure (10%): Unfulfilled orders

        Args:
            scenario_id: Scenario ID
            round_number: Specific round to analyze (None = latest)

        Returns:
            {
                "health_score": 72.5,
                "components": {
                    "inventory_balance": 68.0,
                    "service_level": 85.0,
                    "cost_efficiency": 70.0,
                    "order_stability": 60.0,
                    "backlog_pressure": 80.0
                },
                "status": "moderate",  # excellent, good, moderate, poor, critical
                "insights": [...]
            }
        """
        try:
            # Get scenario metrics
            if round_number is None:
                # Get latest round
                query = text("""
                    SELECT MAX(round_number) as latest_round
                    FROM rounds
                    WHERE scenario_id = :scenario_id
                """)
                result = await self.db.execute(query, {"scenario_id": scenario_id})
                row = result.fetchone()
                round_number = row.latest_round if row and row.latest_round else 1

            # Get scenario_user round metrics
            query = text("""
                SELECT
                    pr.inventory_after,
                    pr.backlog_after,
                    pr.order_placed,
                    pr.inventory_cost,
                    pr.backlog_cost,
                    pr.total_cost,
                    pr.service_level,
                    p.role
                FROM scenario_user_periods pr
                JOIN scenario_users p ON pr.scenario_user_id = p.id
                WHERE p.scenario_id = :scenario_id
                AND pr.round_number = :round_number
            """)
            result = await self.db.execute(query, {
                "scenario_id": scenario_id,
                "round_number": round_number
            })
            rows = result.fetchall()

            if not rows:
                return {
                    "health_score": 0.0,
                    "components": {},
                    "status": "unknown",
                    "insights": ["No data available for health calculation"]
                }

            # Calculate component scores
            inventory_balance_score = await self._calculate_inventory_balance_score(rows)
            service_level_score = await self._calculate_service_level_score(rows)
            cost_efficiency_score = await self._calculate_cost_efficiency_score(rows)
            order_stability_score = await self._calculate_order_stability_score(scenario_id, round_number)
            backlog_pressure_score = await self._calculate_backlog_pressure_score(rows)

            # Weighted health score
            health_score = (
                inventory_balance_score * 0.30 +
                service_level_score * 0.25 +
                cost_efficiency_score * 0.20 +
                order_stability_score * 0.15 +
                backlog_pressure_score * 0.10
            )

            # Determine status
            if health_score >= 80:
                status = "excellent"
            elif health_score >= 65:
                status = "good"
            elif health_score >= 50:
                status = "moderate"
            elif health_score >= 35:
                status = "poor"
            else:
                status = "critical"

            # Generate insights
            insights = self._generate_health_insights(
                health_score,
                inventory_balance_score,
                service_level_score,
                cost_efficiency_score,
                order_stability_score,
                backlog_pressure_score
            )

            return {
                "health_score": round(health_score, 2),
                "components": {
                    "inventory_balance": round(inventory_balance_score, 2),
                    "service_level": round(service_level_score, 2),
                    "cost_efficiency": round(cost_efficiency_score, 2),
                    "order_stability": round(order_stability_score, 2),
                    "backlog_pressure": round(backlog_pressure_score, 2)
                },
                "status": status,
                "insights": insights,
                "round_number": round_number
            }

        except Exception as e:
            logger.error(f"Failed to calculate supply chain health: {e}", exc_info=True)
            raise

    async def _calculate_inventory_balance_score(self, rows: List) -> float:
        """Score based on optimal inventory levels (target: 40-60 units)."""
        if not rows:
            return 0.0

        scores = []
        for row in rows:
            inventory = row.inventory_after or 0

            # Optimal range: 40-60 units
            if 40 <= inventory <= 60:
                score = 100.0
            elif inventory < 40:
                # Penalty for too low
                score = max(0, (inventory / 40) * 100)
            else:
                # Penalty for too high
                excess = inventory - 60
                score = max(0, 100 - (excess / 40) * 50)

            scores.append(score)

        return sum(scores) / len(scores)

    async def _calculate_service_level_score(self, rows: List) -> float:
        """Score based on service levels (higher is better)."""
        if not rows:
            return 0.0

        service_levels = [row.service_level or 0.0 for row in rows]
        avg_service_level = sum(service_levels) / len(service_levels)

        return avg_service_level * 100

    async def _calculate_cost_efficiency_score(self, rows: List) -> float:
        """Score based on total costs (lower is better)."""
        if not rows:
            return 0.0

        costs = [row.total_cost or 0.0 for row in rows]
        avg_cost = sum(costs) / len(costs)

        # Expected max cost per node per round: 100
        max_expected_cost = 100.0

        if avg_cost <= max_expected_cost * 0.5:
            score = 100.0
        elif avg_cost >= max_expected_cost * 2:
            score = 0.0
        else:
            # Linear scaling
            score = max(0, 100 - ((avg_cost / max_expected_cost) * 50))

        return score

    async def _calculate_order_stability_score(self, scenario_id: int, round_number: int) -> float:
        """Score based on order volatility (bullwhip effect)."""
        try:
            # Get last 5 rounds of orders
            query = text("""
                SELECT pr.order_placed
                FROM scenario_user_periods pr
                JOIN scenario_users p ON pr.scenario_user_id = p.id
                WHERE p.scenario_id = :scenario_id
                AND pr.round_number BETWEEN :start_round AND :end_round
                ORDER BY pr.round_number DESC
                LIMIT 5
            """)
            result = await self.db.execute(query, {
                "scenario_id": scenario_id,
                "start_round": max(1, round_number - 4),
                "end_round": round_number
            })
            rows = result.fetchall()

            if len(rows) < 2:
                return 50.0  # Neutral score for insufficient data

            orders = [row.order_placed or 0 for row in rows]

            # Calculate coefficient of variation
            avg_order = sum(orders) / len(orders)
            if avg_order == 0:
                return 50.0

            variance = sum((x - avg_order) ** 2 for x in orders) / len(orders)
            std_dev = variance ** 0.5
            cv = std_dev / avg_order

            # Lower CV = higher stability = higher score
            # CV < 0.2: Excellent (100)
            # CV > 1.0: Poor (0)
            if cv <= 0.2:
                score = 100.0
            elif cv >= 1.0:
                score = 0.0
            else:
                score = 100 - (cv / 1.0) * 100

            return score

        except Exception as e:
            logger.warning(f"Failed to calculate order stability: {e}")
            return 50.0

    async def _calculate_backlog_pressure_score(self, rows: List) -> float:
        """Score based on backlog levels (lower is better)."""
        if not rows:
            return 100.0

        backlogs = [row.backlog_after or 0 for row in rows]
        avg_backlog = sum(backlogs) / len(backlogs)

        # 0 backlog = 100 score
        # 50+ backlog = 0 score
        if avg_backlog == 0:
            score = 100.0
        elif avg_backlog >= 50:
            score = 0.0
        else:
            score = 100 - (avg_backlog / 50) * 100

        return score

    def _generate_health_insights(
        self,
        health_score: float,
        inventory_balance: float,
        service_level: float,
        cost_efficiency: float,
        order_stability: float,
        backlog_pressure: float
    ) -> List[str]:
        """Generate actionable insights based on health components."""
        insights = []

        # Overall health
        if health_score >= 80:
            insights.append("✅ Supply chain is operating at optimal health")
        elif health_score >= 50:
            insights.append("⚠️ Supply chain has moderate health - improvements possible")
        else:
            insights.append("🚨 Supply chain health is critical - immediate action needed")

        # Component-specific insights
        if inventory_balance < 50:
            insights.append("📦 Inventory levels are suboptimal - consider rebalancing")

        if service_level < 70:
            insights.append("📉 Service levels are below target - risk of customer dissatisfaction")

        if cost_efficiency < 50:
            insights.append("💰 Costs are high - review ordering policies")

        if order_stability < 50:
            insights.append("📊 High order volatility detected - bullwhip effect present")

        if backlog_pressure < 60:
            insights.append("⏳ Backlog pressure building - increase order quantities")

        # Positive reinforcement
        if service_level >= 80:
            insights.append("🎯 Excellent service levels - customers are satisfied")

        if order_stability >= 80:
            insights.append("📈 Orders are stable - good demand forecasting")

        return insights

    # =============================================================================
    # BOTTLENECK DETECTION
    # =============================================================================

    async def detect_bottlenecks(
        self,
        scenario_id: int,
        round_number: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Detect bottlenecks in the supply chain.

        A bottleneck is a node where:
        - High backlog (>20 units)
        - Low inventory (<10 units)
        - Service level < 0.7

        Args:
            scenario_id: Scenario ID
            round_number: Specific round (None = latest)

        Returns:
            {
                "bottlenecks": [
                    {
                        "role": "WHOLESALER",
                        "severity": "high",
                        "metrics": {
                            "backlog": 35,
                            "inventory": 5,
                            "service_level": 0.62
                        },
                        "impact": "Blocking 35 units from downstream",
                        "recommendation": "Increase order quantity by 40%"
                    }
                ],
                "total_bottlenecks": 1,
                "supply_chain_flow": "restricted"
            }
        """
        try:
            # Get latest round if not specified
            if round_number is None:
                query = text("""
                    SELECT MAX(round_number) as latest_round
                    FROM rounds
                    WHERE scenario_id = :scenario_id
                """)
                result = await self.db.execute(query, {"scenario_id": scenario_id})
                row = result.fetchone()
                round_number = row.latest_round if row and row.latest_round else 1

            # Get scenario_user metrics
            query = text("""
                SELECT
                    p.role,
                    pr.inventory_after,
                    pr.backlog_after,
                    pr.service_level,
                    pr.order_placed,
                    pr.total_cost
                FROM scenario_user_periods pr
                JOIN scenario_users p ON pr.scenario_user_id = p.id
                WHERE p.scenario_id = :scenario_id
                AND pr.round_number = :round_number
            """)
            result = await self.db.execute(query, {
                "scenario_id": scenario_id,
                "round_number": round_number
            })
            rows = result.fetchall()

            bottlenecks = []

            for row in rows:
                backlog = row.backlog_after or 0
                inventory = row.inventory_after or 0
                service_level = row.service_level or 0.0

                # Bottleneck criteria
                is_bottleneck = False
                severity = "none"

                if backlog > 20 and inventory < 10:
                    is_bottleneck = True
                    if backlog > 40:
                        severity = "critical"
                    elif backlog > 30:
                        severity = "high"
                    else:
                        severity = "moderate"
                elif service_level < 0.6:
                    is_bottleneck = True
                    severity = "moderate"

                if is_bottleneck:
                    # Calculate recommended action
                    if backlog > 30:
                        recommendation = f"Increase order quantity by {min(100, int((backlog / row.order_placed) * 100))}%"
                    elif inventory < 10:
                        recommendation = "Build safety stock to at least 20 units"
                    else:
                        recommendation = "Review ordering policy and lead times"

                    bottlenecks.append({
                        "role": row.role,
                        "severity": severity,
                        "metrics": {
                            "backlog": backlog,
                            "inventory": inventory,
                            "service_level": round(service_level, 2)
                        },
                        "impact": f"Blocking {backlog} units from downstream" if backlog > 0 else "Low service level",
                        "recommendation": recommendation
                    })

            # Determine overall flow status
            if len(bottlenecks) == 0:
                flow_status = "smooth"
            elif len(bottlenecks) == 1:
                flow_status = "restricted"
            else:
                flow_status = "congested"

            return {
                "bottlenecks": bottlenecks,
                "total_bottlenecks": len(bottlenecks),
                "supply_chain_flow": flow_status,
                "round_number": round_number
            }

        except Exception as e:
            logger.error(f"Failed to detect bottlenecks: {e}", exc_info=True)
            raise

    # =============================================================================
    # BULLWHIP EFFECT MEASUREMENT
    # =============================================================================

    async def measure_bullwhip_severity(
        self,
        scenario_id: int,
        window_size: int = 10
    ) -> Dict[str, Any]:
        """
        Measure bullwhip effect severity across supply chain.

        Bullwhip effect = demand variance amplification upstream.

        Args:
            scenario_id: Scenario ID
            window_size: Number of rounds to analyze

        Returns:
            {
                "severity": "moderate",  # low, moderate, high, severe
                "amplification_ratio": 2.3,
                "by_role": {
                    "RETAILER": {"variance": 12.5, "cv": 0.25},
                    "WHOLESALER": {"variance": 28.7, "cv": 0.52},
                    ...
                },
                "insights": [...]
            }
        """
        try:
            # Get order data for each role
            query = text("""
                SELECT
                    p.role,
                    pr.round_number,
                    pr.order_placed
                FROM scenario_user_periods pr
                JOIN scenario_users p ON pr.scenario_user_id = p.id
                WHERE p.scenario_id = :scenario_id
                ORDER BY p.role, pr.round_number DESC
                LIMIT :limit
            """)
            result = await self.db.execute(query, {
                "scenario_id": scenario_id,
                "limit": window_size * 4  # 4 roles
            })
            rows = result.fetchall()

            # Group by role
            role_orders = {}
            for row in rows:
                if row.role not in role_orders:
                    role_orders[row.role] = []
                role_orders[row.role].append(row.order_placed or 0)

            # Calculate variance for each role
            role_metrics = {}
            for role, orders in role_orders.items():
                if len(orders) < 2:
                    continue

                avg_order = sum(orders) / len(orders)
                variance = sum((x - avg_order) ** 2 for x in orders) / len(orders)
                std_dev = variance ** 0.5
                cv = std_dev / avg_order if avg_order > 0 else 0.0

                role_metrics[role] = {
                    "variance": round(variance, 2),
                    "cv": round(cv, 2),
                    "avg_order": round(avg_order, 2)
                }

            # Calculate amplification ratio (upstream CV / downstream CV)
            roles_ordered = ["RETAILER", "WHOLESALER", "DISTRIBUTOR", "FACTORY"]
            amplifications = []

            for i in range(len(roles_ordered) - 1):
                downstream_role = roles_ordered[i]
                upstream_role = roles_ordered[i + 1]

                if downstream_role in role_metrics and upstream_role in role_metrics:
                    downstream_cv = role_metrics[downstream_role]["cv"]
                    upstream_cv = role_metrics[upstream_role]["cv"]

                    if downstream_cv > 0:
                        ratio = upstream_cv / downstream_cv
                        amplifications.append(ratio)

            avg_amplification = sum(amplifications) / len(amplifications) if amplifications else 1.0

            # Determine severity
            if avg_amplification <= 1.2:
                severity = "low"
            elif avg_amplification <= 1.8:
                severity = "moderate"
            elif avg_amplification <= 2.5:
                severity = "high"
            else:
                severity = "severe"

            # Generate insights
            insights = []
            if severity == "low":
                insights.append("✅ Bullwhip effect is minimal - good coordination")
            elif severity == "moderate":
                insights.append("⚠️ Moderate bullwhip effect detected")
            else:
                insights.append("🚨 Severe bullwhip effect - poor information sharing")

            # Role-specific insights
            for role, metrics in role_metrics.items():
                if metrics["cv"] > 0.5:
                    insights.append(f"📊 {role} has high order volatility (CV={metrics['cv']:.2f})")

            return {
                "severity": severity,
                "amplification_ratio": round(avg_amplification, 2),
                "by_role": role_metrics,
                "insights": insights
            }

        except Exception as e:
            logger.error(f"Failed to measure bullwhip severity: {e}", exc_info=True)
            raise

    # =============================================================================
    # VISIBILITY PERMISSIONS
    # =============================================================================

    async def set_visibility_permission(
        self,
        scenario_id: int,
        scenario_user_id: int,
        share_inventory: bool = False,
        share_backlog: bool = False,
        share_orders: bool = False
    ) -> Dict[str, Any]:
        """
        Set visibility sharing permissions for a scenario_user.

        Args:
            scenario_id: Scenario ID
            scenario_user_id: ScenarioUser ID
            share_inventory: Share inventory levels
            share_backlog: Share backlog levels
            share_orders: Share order quantities

        Returns:
            {
                "scenario_user_id": 123,
                "permissions": {
                    "share_inventory": true,
                    "share_backlog": false,
                    "share_orders": false
                },
                "updated_at": "2026-01-14T12:00:00"
            }
        """
        try:
            # Upsert permission
            query = text("""
                INSERT INTO visibility_permissions
                (scenario_id, scenario_user_id, share_inventory, share_backlog, share_orders, updated_at)
                VALUES (:scenario_id, :scenario_user_id, :share_inventory, :share_backlog, :share_orders, NOW())
                ON DUPLICATE KEY UPDATE
                    share_inventory = :share_inventory,
                    share_backlog = :share_backlog,
                    share_orders = :share_orders,
                    updated_at = NOW()
            """)
            await self.db.execute(query, {
                "scenario_id": scenario_id,
                "scenario_user_id": scenario_user_id,
                "share_inventory": share_inventory,
                "share_backlog": share_backlog,
                "share_orders": share_orders
            })
            await self.db.commit()

            return {
                "scenario_user_id": scenario_user_id,
                "permissions": {
                    "share_inventory": share_inventory,
                    "share_backlog": share_backlog,
                    "share_orders": share_orders
                },
                "updated_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to set visibility permission: {e}", exc_info=True)
            raise

    async def get_visibility_permissions(
        self,
        scenario_id: int
    ) -> Dict[str, Any]:
        """
        Get visibility permissions for all scenario_users in a scenario.

        Returns:
            {
                "scenario_users": [
                    {
                        "scenario_user_id": 123,
                        "role": "RETAILER",
                        "permissions": {...}
                    }
                ]
            }
        """
        try:
            query = text("""
                SELECT
                    p.id as scenario_user_id,
                    p.role,
                    vp.share_inventory,
                    vp.share_backlog,
                    vp.share_orders
                FROM scenario_users p
                LEFT JOIN visibility_permissions vp
                    ON p.id = vp.scenario_user_id AND p.scenario_id = vp.scenario_id
                WHERE p.scenario_id = :scenario_id
            """)
            result = await self.db.execute(query, {"scenario_id": scenario_id})
            rows = result.fetchall()

            scenario_users = []
            for row in rows:
                scenario_users.append({
                    "scenario_user_id": row.scenario_user_id,
                    "role": row.role,
                    "permissions": {
                        "share_inventory": row.share_inventory or False,
                        "share_backlog": row.share_backlog or False,
                        "share_orders": row.share_orders or False
                    }
                })

            return {"scenario_users": scenario_users}

        except Exception as e:
            logger.error(f"Failed to get visibility permissions: {e}", exc_info=True)
            raise

    # =============================================================================
    # VISIBILITY SNAPSHOTS
    # =============================================================================

    async def create_visibility_snapshot(
        self,
        scenario_id: int,
        round_number: int
    ) -> Dict[str, Any]:
        """
        Create a visibility snapshot for the current round.

        Snapshots capture:
        - Supply chain health score
        - Bottleneck status
        - Bullwhip severity
        - Per-scenario_user metrics (if shared)

        Args:
            scenario_id: Scenario ID
            round_number: Round number

        Returns:
            {"snapshot_id": 456, "created_at": "..."}
        """
        try:
            # Calculate health score
            health = await self.calculate_supply_chain_health(scenario_id, round_number)

            # Detect bottlenecks
            bottlenecks = await self.detect_bottlenecks(scenario_id, round_number)

            # Measure bullwhip
            bullwhip = await self.measure_bullwhip_severity(scenario_id, window_size=10)

            # Get shared metrics
            permissions = await self.get_visibility_permissions(scenario_id)

            shared_metrics = {}
            for scenario_user in permissions["scenario_users"]:
                if any(scenario_user["permissions"].values()):
                    # Get scenario_user metrics
                    query = text("""
                        SELECT inventory_after, backlog_after, order_placed
                        FROM scenario_user_periods pr
                        WHERE pr.scenario_user_id = :scenario_user_id
                        AND pr.round_number = :round_number
                    """)
                    result = await self.db.execute(query, {
                        "scenario_user_id": scenario_user["scenario_user_id"],
                        "round_number": round_number
                    })
                    row = result.fetchone()

                    if row:
                        metrics = {}
                        if scenario_user["permissions"]["share_inventory"]:
                            metrics["inventory"] = row.inventory_after
                        if scenario_user["permissions"]["share_backlog"]:
                            metrics["backlog"] = row.backlog_after
                        if scenario_user["permissions"]["share_orders"]:
                            metrics["order"] = row.order_placed

                        if metrics:
                            shared_metrics[scenario_user["role"]] = metrics

            # Store snapshot
            snapshot_data = {
                "health_score": health["health_score"],
                "bottlenecks": len(bottlenecks["bottlenecks"]),
                "bullwhip_severity": bullwhip["severity"],
                "shared_metrics": shared_metrics
            }

            query = text("""
                INSERT INTO visibility_snapshots
                (scenario_id, round_number, health_score, snapshot_data, created_at)
                VALUES (:scenario_id, :round_number, :health_score, :snapshot_data, NOW())
            """)
            result = await self.db.execute(query, {
                "scenario_id": scenario_id,
                "round_number": round_number,
                "health_score": health["health_score"],
                "snapshot_data": str(snapshot_data)  # JSON as string
            })
            await self.db.commit()

            snapshot_id = result.lastrowid

            return {
                "snapshot_id": snapshot_id,
                "created_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to create visibility snapshot: {e}", exc_info=True)
            raise

    async def get_visibility_snapshots(
        self,
        scenario_id: int,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Get historical visibility snapshots.

        Args:
            scenario_id: Scenario ID
            limit: Maximum snapshots to return

        Returns:
            List of snapshots with health scores and metrics
        """
        try:
            query = text("""
                SELECT
                    id,
                    round_number,
                    health_score,
                    snapshot_data,
                    created_at
                FROM visibility_snapshots
                WHERE scenario_id = :scenario_id
                ORDER BY round_number DESC
                LIMIT :limit
            """)
            result = await self.db.execute(query, {
                "scenario_id": scenario_id,
                "limit": limit
            })
            rows = result.fetchall()

            snapshots = []
            for row in rows:
                snapshots.append({
                    "id": row.id,
                    "round_number": row.round_number,
                    "health_score": float(row.health_score),
                    "snapshot_data": row.snapshot_data,
                    "created_at": row.created_at.isoformat() if row.created_at else None
                })

            return snapshots

        except Exception as e:
            logger.error(f"Failed to get visibility snapshots: {e}", exc_info=True)
            raise


# =============================================================================
# SERVICE FACTORY
# =============================================================================

def get_visibility_service(db: AsyncSession) -> VisibilityService:
    """Get or create visibility service instance."""
    return VisibilityService(db)
