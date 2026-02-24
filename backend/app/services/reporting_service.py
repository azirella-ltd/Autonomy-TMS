"""
Reporting Service - Game Analytics and Data Export

Provides comprehensive reporting, analytics, and export capabilities for games.
Generates insights, recommendations, and trend analysis.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from sqlalchemy import select, func, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession
import json
import csv
import io
from statistics import mean, stdev

from app.models.scenario import Scenario
from app.models.participant import Participant
from app.models.supply_chain import ScenarioRound, ParticipantRound
from app.models.user import User

# Aliases for backwards compatibility
Game = Scenario
Player = Participant
GameRound = ScenarioRound
PlayerRound = ParticipantRound


class ReportingService:
    """Service for game reporting, analytics, and exports."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def generate_game_report(self, scenario_id: int) -> Dict[str, Any]:
        """
        Generate comprehensive game report with overview, performance, insights.

        Args:
            scenario_id: ID of the game to report on

        Returns:
            Complete game report with overview, player performance, insights, recommendations
        """
        # Fetch game data
        game = await self._get_game_with_rounds(scenario_id)
        if not game:
            raise ValueError(f"Game {scenario_id} not found")

        # Fetch all player rounds
        player_rounds = await self._get_player_rounds(scenario_id)

        # Calculate overview metrics
        overview = await self._calculate_overview(game, player_rounds)

        # Calculate per-player performance
        player_performance = await self._calculate_player_performance(scenario_id, player_rounds)

        # Generate insights
        insights = await self._generate_insights(game, player_rounds, player_performance)

        # Generate recommendations
        recommendations = await self._generate_recommendations(game, player_rounds, insights)

        return {
            "scenario_id": scenario_id,
            "generated_at": datetime.utcnow().isoformat(),
            "overview": overview,
            "player_performance": player_performance,
            "key_insights": insights,
            "recommendations": recommendations,
            "charts_data": await self._prepare_charts_data(scenario_id, player_rounds)
        }

    async def export_game_data(
        self,
        scenario_id: int,
        format: str = 'csv',
        include_rounds: bool = True
    ) -> bytes:
        """
        Export game data in specified format.

        Args:
            scenario_id: Game to export
            format: Export format (csv, json, excel)
            include_rounds: Whether to include round-by-round data

        Returns:
            File content as bytes
        """
        if format == 'csv':
            return await self._export_csv(scenario_id, include_rounds)
        elif format == 'json':
            return await self._export_json(scenario_id, include_rounds)
        elif format == 'excel':
            return await self._export_excel(scenario_id, include_rounds)
        else:
            raise ValueError(f"Unsupported format: {format}")

    async def get_trend_analysis(
        self,
        player_id: int,
        metric: str = 'cost',
        lookback: int = 10
    ) -> Dict[str, Any]:
        """
        Analyze player performance trends across recent games.

        Args:
            player_id: Player to analyze
            metric: Metric to analyze (cost, service_level, inventory, bullwhip)
            lookback: Number of recent games to include

        Returns:
            Trend analysis with data points, statistics, and insights
        """
        # Get recent player rounds
        stmt = (
            select(PlayerRound, Game)
            .join(Game, PlayerRound.scenario_id == Game.id)
            .where(PlayerRound.player_id == player_id)
            .where(Game.status == 'completed')
            .order_by(desc(Game.created_at))
            .limit(lookback * 20)  # Approximate: lookback games * avg rounds per game
        )
        result = await self.db.execute(stmt)
        player_rounds = result.all()

        if not player_rounds:
            return {
                "player_id": player_id,
                "metric": metric,
                "message": "No completed games found",
                "data_points": []
            }

        # Group by game and calculate per-game metrics
        games_data = {}
        for pr, game in player_rounds:
            if game.id not in games_data:
                games_data[game.id] = {
                    "scenario_id": game.id,
                    "created_at": game.created_at,
                    "rounds": []
                }
            games_data[game.id]["rounds"].append(pr)

        # Calculate metric for each game
        data_points = []
        for scenario_id, game_data in sorted(
            games_data.items(),
            key=lambda x: x[1]["created_at"]
        )[-lookback:]:
            value = self._calculate_metric_for_game(game_data["rounds"], metric)
            data_points.append({
                "scenario_id": scenario_id,
                "date": game_data["created_at"].isoformat(),
                "value": value
            })

        # Calculate statistics
        values = [dp["value"] for dp in data_points if dp["value"] is not None]
        stats = {
            "mean": mean(values) if values else None,
            "std": stdev(values) if len(values) > 1 else None,
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "trend": self._calculate_trend(values) if len(values) >= 3 else "insufficient_data"
        }

        return {
            "player_id": player_id,
            "metric": metric,
            "lookback": lookback,
            "games_analyzed": len(data_points),
            "data_points": data_points,
            "statistics": stats,
            "insights": self._generate_trend_insights(metric, data_points, stats)
        }

    async def compare_games(
        self,
        scenario_ids: List[int],
        metrics: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Compare performance across multiple games.

        Args:
            scenario_ids: List of game IDs to compare
            metrics: Metrics to compare (default: all)

        Returns:
            Comparison data with side-by-side metrics
        """
        if not metrics:
            metrics = ['total_cost', 'service_level', 'avg_inventory', 'bullwhip_effect']

        comparisons = []
        for scenario_id in scenario_ids:
            game = await self._get_game_with_rounds(scenario_id)
            if not game:
                continue

            player_rounds = await self._get_player_rounds(scenario_id)
            overview = await self._calculate_overview(game, player_rounds)

            game_data = {
                "scenario_id": scenario_id,
                "config_name": game.config.name if game.config else "Unknown",
                "rounds": game.num_rounds,
                "players": len(set(pr.player_id for pr in player_rounds)),
                "status": game.status
            }

            for metric in metrics:
                game_data[metric] = overview.get(metric)

            comparisons.append(game_data)

        return {
            "games_compared": len(comparisons),
            "metrics": metrics,
            "comparisons": comparisons,
            "best_performers": self._identify_best_performers(comparisons, metrics)
        }

    # Private helper methods

    async def _get_game_with_rounds(self, scenario_id: int):
        """Fetch game with rounds."""
        stmt = select(Game).where(Game.id == scenario_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_player_rounds(self, scenario_id: int) -> List[PlayerRound]:
        """Fetch all player rounds for a game."""
        stmt = (
            select(PlayerRound)
            .where(PlayerRound.scenario_id == scenario_id)
            .order_by(PlayerRound.round_number, PlayerRound.player_id)
        )
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def _calculate_overview(
        self,
        game: Game,
        player_rounds: List[PlayerRound]
    ) -> Dict[str, Any]:
        """Calculate game overview metrics."""
        if not player_rounds:
            return {
                "scenario_id": game.id,
                "status": game.status,
                "rounds": 0,
                "message": "No player data available"
            }

        total_cost = sum(
            (pr.holding_cost or 0) + (pr.backlog_cost or 0)
            for pr in player_rounds
        )

        service_levels = [
            pr.service_level for pr in player_rounds
            if pr.service_level is not None
        ]
        avg_service_level = mean(service_levels) if service_levels else None

        inventories = [
            pr.inventory for pr in player_rounds
            if pr.inventory is not None
        ]
        avg_inventory = mean(inventories) if inventories else None

        # Calculate bullwhip effect (variance amplification)
        bullwhip = await self._calculate_bullwhip_effect(game.id, player_rounds)

        max_round = max((pr.round_number for pr in player_rounds), default=0)

        return {
            "scenario_id": game.id,
            "config_name": game.config.name if game.config else "Unknown",
            "status": game.status,
            "rounds_played": max_round,
            "total_rounds": game.num_rounds,
            "duration": f"{max_round} rounds",
            "total_cost": round(total_cost, 2),
            "service_level": round(avg_service_level, 3) if avg_service_level else None,
            "avg_inventory": round(avg_inventory, 2) if avg_inventory else None,
            "bullwhip_effect": round(bullwhip, 3) if bullwhip else None
        }

    async def _calculate_player_performance(
        self,
        scenario_id: int,
        player_rounds: List[PlayerRound]
    ) -> List[Dict[str, Any]]:
        """Calculate per-player performance metrics."""
        # Group by player
        players_data = {}
        for pr in player_rounds:
            if pr.player_id not in players_data:
                players_data[pr.player_id] = []
            players_data[pr.player_id].append(pr)

        performance = []
        for player_id, rounds in players_data.items():
            # Get player info
            player = await self.db.get(Player, player_id)
            if not player:
                continue

            total_cost = sum(
                (r.holding_cost or 0) + (r.backlog_cost or 0)
                for r in rounds
            )

            service_levels = [r.service_level for r in rounds if r.service_level is not None]
            avg_service = mean(service_levels) if service_levels else None

            inventories = [r.inventory for r in rounds if r.inventory is not None]
            avg_inventory = mean(inventories) if inventories else None

            orders = [r.order_quantity for r in rounds if r.order_quantity is not None]

            performance.append({
                "player_id": player_id,
                "role": player.role,
                "total_cost": round(total_cost, 2),
                "service_level": round(avg_service, 3) if avg_service else None,
                "orders_placed": len([o for o in orders if o is not None]),
                "avg_inventory": round(avg_inventory, 2) if avg_inventory else None,
                "avg_order_size": round(mean(orders), 2) if orders else None,
                "order_variance": round(stdev(orders), 2) if len(orders) > 1 else None
            })

        return sorted(performance, key=lambda x: x["total_cost"])

    async def _calculate_bullwhip_effect(
        self,
        scenario_id: int,
        player_rounds: List[PlayerRound]
    ) -> Optional[float]:
        """Calculate bullwhip effect (order variance amplification)."""
        # Group orders by player
        players_orders = {}
        for pr in player_rounds:
            if pr.order_quantity is None:
                continue
            if pr.player_id not in players_orders:
                players_orders[pr.player_id] = []
            players_orders[pr.player_id].append(pr.order_quantity)

        # Calculate variance for each player
        variances = []
        for player_id, orders in players_orders.items():
            if len(orders) > 1:
                variance = stdev(orders) ** 2
                variances.append(variance)

        if len(variances) < 2:
            return None

        # Bullwhip effect = max variance / min variance
        return max(variances) / min(variances) if min(variances) > 0 else None

    async def _generate_insights(
        self,
        game: Game,
        player_rounds: List[PlayerRound],
        player_performance: List[Dict]
    ) -> List[str]:
        """Generate key insights about game performance."""
        insights = []

        # Service level insights
        service_levels = [
            p["service_level"] for p in player_performance
            if p["service_level"] is not None
        ]
        if service_levels:
            avg_service = mean(service_levels)
            if avg_service >= 0.95:
                insights.append("Excellent service levels maintained across all players")
            elif avg_service >= 0.85:
                insights.append("Good service levels with some room for improvement")
            else:
                insights.append("Service levels below target - frequent stockouts occurred")

        # Cost insights
        if player_performance:
            best_performer = player_performance[0]
            worst_performer = player_performance[-1]
            cost_spread = worst_performer["total_cost"] - best_performer["total_cost"]

            insights.append(
                f"{best_performer['role']} achieved lowest cost ({best_performer['total_cost']:.2f})"
            )

            if cost_spread > 500:
                insights.append(
                    f"Large cost variation ({cost_spread:.2f}) indicates coordination issues"
                )

        # Order variance insights
        high_variance_players = [
            p for p in player_performance
            if p.get("order_variance") and p["order_variance"] > 10
        ]
        if high_variance_players:
            roles = ", ".join(p["role"] for p in high_variance_players)
            insights.append(f"High order variability observed in: {roles}")

        return insights

    async def _generate_recommendations(
        self,
        game: Game,
        player_rounds: List[PlayerRound],
        insights: List[str]
    ) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []

        # Analyze patterns and suggest improvements
        if "stockouts" in " ".join(insights).lower():
            recommendations.append(
                "Consider increasing safety stock levels to reduce stockouts"
            )

        if "variability" in " ".join(insights).lower() or "variation" in " ".join(insights).lower():
            recommendations.append(
                "Implement more consistent ordering patterns to reduce bullwhip effect"
            )

        if "coordination" in " ".join(insights).lower():
            recommendations.append(
                "Use visibility sharing and negotiations to improve supply chain coordination"
            )

        # Generic recommendations
        recommendations.append(
            "Review AI suggestions to identify optimization opportunities"
        )

        recommendations.append(
            "Consider using global optimization for system-wide cost reduction"
        )

        return recommendations

    async def _prepare_charts_data(
        self,
        scenario_id: int,
        player_rounds: List[PlayerRound]
    ) -> Dict[str, List]:
        """Prepare data for frontend charts."""
        # Group by round
        rounds_data = {}
        for pr in player_rounds:
            round_num = pr.round_number
            if round_num not in rounds_data:
                rounds_data[round_num] = {
                    "round": round_num,
                    "inventory": [],
                    "orders": [],
                    "costs": []
                }

            if pr.inventory is not None:
                rounds_data[round_num]["inventory"].append(pr.inventory)
            if pr.order_quantity is not None:
                rounds_data[round_num]["orders"].append(pr.order_quantity)
            if pr.holding_cost is not None or pr.backlog_cost is not None:
                total = (pr.holding_cost or 0) + (pr.backlog_cost or 0)
                rounds_data[round_num]["costs"].append(total)

        # Calculate averages per round
        charts_data = []
        for round_num in sorted(rounds_data.keys()):
            rd = rounds_data[round_num]
            charts_data.append({
                "round": round_num,
                "avg_inventory": mean(rd["inventory"]) if rd["inventory"] else None,
                "avg_orders": mean(rd["orders"]) if rd["orders"] else None,
                "total_cost": sum(rd["costs"]) if rd["costs"] else None
            })

        return {
            "inventory_trend": charts_data,
            "order_pattern": charts_data,
            "cost_accumulation": charts_data
        }

    def _calculate_metric_for_game(
        self,
        rounds: List[PlayerRound],
        metric: str
    ) -> Optional[float]:
        """Calculate a specific metric for a game's rounds."""
        if metric == 'cost':
            costs = [
                (r.holding_cost or 0) + (r.backlog_cost or 0)
                for r in rounds
            ]
            return sum(costs)
        elif metric == 'service_level':
            service_levels = [r.service_level for r in rounds if r.service_level is not None]
            return mean(service_levels) if service_levels else None
        elif metric == 'inventory':
            inventories = [r.inventory for r in rounds if r.inventory is not None]
            return mean(inventories) if inventories else None
        elif metric == 'bullwhip':
            orders = [r.order_quantity for r in rounds if r.order_quantity is not None]
            if len(orders) > 1:
                return stdev(orders)
            return None
        else:
            return None

    def _calculate_trend(self, values: List[float]) -> str:
        """Determine if trend is improving, declining, or stable."""
        if len(values) < 3:
            return "insufficient_data"

        # Simple linear regression slope
        n = len(values)
        x = list(range(n))
        mean_x = mean(x)
        mean_y = mean(values)

        numerator = sum((x[i] - mean_x) * (values[i] - mean_y) for i in range(n))
        denominator = sum((x[i] - mean_x) ** 2 for i in range(n))

        if denominator == 0:
            return "stable"

        slope = numerator / denominator

        if slope < -0.1:
            return "improving"  # Values decreasing (good for cost)
        elif slope > 0.1:
            return "declining"  # Values increasing (bad for cost)
        else:
            return "stable"

    def _generate_trend_insights(
        self,
        metric: str,
        data_points: List[Dict],
        stats: Dict
    ) -> List[str]:
        """Generate insights about performance trends."""
        insights = []

        trend = stats.get("trend")
        if trend == "improving":
            insights.append(f"Your {metric} performance is improving over time")
        elif trend == "declining":
            insights.append(f"Your {metric} performance shows room for improvement")
        elif trend == "stable":
            insights.append(f"Your {metric} performance is consistent")

        if stats.get("std") and stats.get("mean"):
            cv = stats["std"] / stats["mean"]  # Coefficient of variation
            if cv > 0.3:
                insights.append("High variability in performance - consider more consistent strategies")
            elif cv < 0.1:
                insights.append("Very consistent performance across games")

        return insights

    def _identify_best_performers(
        self,
        comparisons: List[Dict],
        metrics: List[str]
    ) -> Dict[str, Any]:
        """Identify best performing games for each metric."""
        best = {}

        for metric in metrics:
            values = [
                (c["scenario_id"], c.get(metric))
                for c in comparisons
                if c.get(metric) is not None
            ]

            if not values:
                continue

            # For cost metrics, lower is better
            if 'cost' in metric.lower():
                best_game = min(values, key=lambda x: x[1])
            else:
                # For service level, etc., higher is better
                best_game = max(values, key=lambda x: x[1])

            best[metric] = {
                "scenario_id": best_game[0],
                "value": best_game[1]
            }

        return best

    async def _export_csv(self, scenario_id: int, include_rounds: bool) -> bytes:
        """Export game data as CSV."""
        player_rounds = await self._get_player_rounds(scenario_id)

        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            'Game ID', 'Round', 'Player ID', 'Role', 'Inventory',
            'Backlog', 'Order Quantity', 'Holding Cost', 'Backlog Cost',
            'Service Level'
        ])

        # Write data
        for pr in player_rounds:
            player = await self.db.get(Player, pr.player_id)
            writer.writerow([
                scenario_id,
                pr.round_number,
                pr.player_id,
                player.role if player else 'Unknown',
                pr.inventory,
                pr.backlog,
                pr.order_quantity,
                pr.holding_cost,
                pr.backlog_cost,
                pr.service_level
            ])

        return output.getvalue().encode('utf-8')

    async def _export_json(self, scenario_id: int, include_rounds: bool) -> bytes:
        """Export game data as JSON."""
        report = await self.generate_game_report(scenario_id)
        return json.dumps(report, indent=2).encode('utf-8')

    async def _export_excel(self, scenario_id: int, include_rounds: bool) -> bytes:
        """Export game data as Excel (requires openpyxl)."""
        try:
            from openpyxl import Workbook
            from openpyxl.utils import get_column_letter
        except ImportError:
            # Fallback to CSV if openpyxl not available
            return await self._export_csv(scenario_id, include_rounds)

        wb = Workbook()
        ws = wb.active
        ws.title = "Game Report"

        # Get data
        player_rounds = await self._get_player_rounds(scenario_id)

        # Write headers
        headers = [
            'Game ID', 'Round', 'Player ID', 'Role', 'Inventory',
            'Backlog', 'Order Quantity', 'Holding Cost', 'Backlog Cost',
            'Service Level'
        ]
        ws.append(headers)

        # Write data
        for pr in player_rounds:
            player = await self.db.get(Player, pr.player_id)
            ws.append([
                scenario_id,
                pr.round_number,
                pr.player_id,
                player.role if player else 'Unknown',
                pr.inventory,
                pr.backlog,
                pr.order_quantity,
                pr.holding_cost,
                pr.backlog_cost,
                pr.service_level
            ])

        # Save to bytes
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return output.read()


# Factory function
def get_reporting_service(db: AsyncSession) -> ReportingService:
    """Factory function to get ReportingService instance."""
    return ReportingService(db)
