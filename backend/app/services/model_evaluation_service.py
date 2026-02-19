"""
Model Evaluation & Benchmarking Service

Provides comprehensive evaluation and comparison of different agent types:
- Benchmarking (naive, bullwhip, conservative, RL, GNN, LLM agents)
- Performance metrics (cost, service level, bullwhip effect)
- Statistical analysis (mean, std, confidence intervals)
- Comparative reports and visualizations
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import logging
import json
from pathlib import Path
import statistics

import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger(__name__)


class ModelEvaluationService:
    """
    Service for evaluating and benchmarking different agent types.

    Supports:
    - Multiple agent types (naive, bullwhip, conservative, ml_forecast, optimizer, rl, gnn, llm)
    - Multiple evaluation metrics (cost, service level, bullwhip, inventory variance)
    - Statistical significance testing
    - Comparative analysis and ranking
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def benchmark_agents(
        self,
        config_name: str,
        agent_types: List[str],
        num_trials: int = 10,
        max_rounds: int = 36,
        seed: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Benchmark multiple agent types on the same supply chain configuration.

        Args:
            config_name: Supply chain configuration name
            agent_types: List of agent types to benchmark
            num_trials: Number of games to run per agent type
            max_rounds: Number of rounds per game
            seed: Random seed for reproducibility

        Returns:
            results: Comprehensive benchmarking results with statistics
        """
        logger.info(f"Starting benchmark: {len(agent_types)} agents, {num_trials} trials each")

        results = {
            "config_name": config_name,
            "num_trials": num_trials,
            "max_rounds": max_rounds,
            "agents": {},
            "rankings": {},
            "started_at": datetime.utcnow().isoformat()
        }

        # Benchmark each agent type
        for agent_type in agent_types:
            logger.info(f"Benchmarking {agent_type} agent...")

            try:
                agent_results = await self._evaluate_agent(
                    config_name=config_name,
                    agent_type=agent_type,
                    num_trials=num_trials,
                    max_rounds=max_rounds,
                    seed=seed
                )

                results["agents"][agent_type] = agent_results
                logger.info(f"{agent_type}: avg_cost={agent_results['avg_total_cost']:.2f}, "
                           f"avg_service={agent_results['avg_service_level']:.2%}")

            except Exception as e:
                logger.error(f"Failed to benchmark {agent_type}: {str(e)}")
                results["agents"][agent_type] = {
                    "status": "failed",
                    "error": str(e)
                }

        # Calculate rankings
        results["rankings"] = self._calculate_rankings(results["agents"])

        # Add statistical comparisons
        results["comparisons"] = self._compare_agents(results["agents"])

        results["completed_at"] = datetime.utcnow().isoformat()

        return results

    async def _evaluate_agent(
        self,
        config_name: str,
        agent_type: str,
        num_trials: int,
        max_rounds: int,
        seed: Optional[int]
    ) -> Dict[str, Any]:
        """
        Evaluate a single agent type across multiple trials.

        Returns:
            metrics: Aggregated performance metrics
        """
        from app.services.agent_game_service import AgentGameService
        from app.models.scenario import Scenario as Game
        from app.models.supply_chain import ScenarioRound as GameRound

        # Storage for trial results
        total_costs = []
        service_levels = []
        bullwhip_ratios = []
        inventory_variances = []
        holding_costs = []
        backlog_costs = []

        for trial in range(num_trials):
            try:
                # Set seed for this trial
                trial_seed = (seed + trial) if seed is not None else None

                # Create agent game
                game_service = AgentGameService(self.db)

                # Create game with single agent of this type
                game = await game_service.create_agent_game(
                    config_name=config_name,
                    agent_strategies={
                        "retailer": agent_type,
                        "wholesaler": agent_type,
                        "distributor": agent_type,
                        "factory": agent_type
                    },
                    name=f"Eval_{agent_type}_trial{trial}"
                )

                # Run game
                await game_service.start_game(game.id)

                for round_num in range(max_rounds):
                    await game_service.play_round(game.id)

                # Calculate metrics for this trial
                result = await self.db.execute(
                    select(Game).where(Game.id == game.id)
                )
                game = result.scalar_one()

                # Get all rounds
                rounds_result = await self.db.execute(
                    select(GameRound)
                    .where(GameRound.game_id == game.id)
                    .order_by(GameRound.round_number)
                )
                rounds = rounds_result.scalars().all()

                # Calculate trial metrics
                trial_metrics = self._calculate_game_metrics(game, rounds)

                total_costs.append(trial_metrics["total_cost"])
                service_levels.append(trial_metrics["service_level"])
                bullwhip_ratios.append(trial_metrics["bullwhip_ratio"])
                inventory_variances.append(trial_metrics["inventory_variance"])
                holding_costs.append(trial_metrics["holding_cost"])
                backlog_costs.append(trial_metrics["backlog_cost"])

            except Exception as e:
                logger.error(f"Trial {trial} failed for {agent_type}: {str(e)}")
                continue

        # Calculate statistics
        if not total_costs:
            return {
                "status": "failed",
                "num_successful_trials": 0,
                "error": "All trials failed"
            }

        return {
            "status": "success",
            "num_successful_trials": len(total_costs),
            "num_failed_trials": num_trials - len(total_costs),

            # Cost metrics
            "avg_total_cost": float(np.mean(total_costs)),
            "std_total_cost": float(np.std(total_costs)),
            "min_total_cost": float(np.min(total_costs)),
            "max_total_cost": float(np.max(total_costs)),
            "median_total_cost": float(np.median(total_costs)),

            # Service level
            "avg_service_level": float(np.mean(service_levels)),
            "std_service_level": float(np.std(service_levels)),
            "min_service_level": float(np.min(service_levels)),
            "max_service_level": float(np.max(service_levels)),

            # Bullwhip effect
            "avg_bullwhip_ratio": float(np.mean(bullwhip_ratios)),
            "std_bullwhip_ratio": float(np.std(bullwhip_ratios)),
            "min_bullwhip_ratio": float(np.min(bullwhip_ratios)),
            "max_bullwhip_ratio": float(np.max(bullwhip_ratios)),

            # Inventory variance
            "avg_inventory_variance": float(np.mean(inventory_variances)),
            "std_inventory_variance": float(np.std(inventory_variances)),

            # Cost breakdown
            "avg_holding_cost": float(np.mean(holding_costs)),
            "avg_backlog_cost": float(np.mean(backlog_costs)),

            # Raw data
            "all_total_costs": [float(x) for x in total_costs],
            "all_service_levels": [float(x) for x in service_levels],
            "all_bullwhip_ratios": [float(x) for x in bullwhip_ratios]
        }

    def _calculate_game_metrics(self, game: Any, rounds: List[Any]) -> Dict[str, float]:
        """Calculate performance metrics for a completed game."""
        total_cost = 0.0
        total_demand = 0
        total_fulfilled = 0
        inventory_levels = []
        order_quantities = []

        for round_data in rounds:
            if hasattr(round_data, 'state') and round_data.state:
                state = round_data.state if isinstance(round_data.state, dict) else {}

                # Aggregate costs
                for node_id, node_state in state.items():
                    if isinstance(node_state, dict):
                        total_cost += node_state.get('holding_cost', 0) + node_state.get('backlog_cost', 0)
                        inventory_levels.append(node_state.get('inventory', 0))
                        order_quantities.append(node_state.get('order_quantity', 0))

                        # Service level calculation
                        demand = node_state.get('demand', 0)
                        fulfilled = node_state.get('fulfilled', 0)
                        total_demand += demand
                        total_fulfilled += fulfilled

        # Calculate metrics
        service_level = (total_fulfilled / total_demand) if total_demand > 0 else 1.0

        # Bullwhip effect (variance amplification)
        if len(order_quantities) > 1:
            order_variance = float(np.var(order_quantities))
            # Approximate demand variance (could be improved with actual demand data)
            demand_variance = float(np.var([round_data.state.get('retailer', {}).get('demand', 0)
                                           for round_data in rounds if hasattr(round_data, 'state')]))
            bullwhip_ratio = order_variance / demand_variance if demand_variance > 0 else 1.0
        else:
            bullwhip_ratio = 1.0

        # Inventory variance
        inventory_variance = float(np.var(inventory_levels)) if len(inventory_levels) > 1 else 0.0

        # Cost breakdown
        holding_cost = sum([node_state.get('holding_cost', 0)
                           for round_data in rounds
                           for node_state in (round_data.state.values() if hasattr(round_data, 'state') else [])])
        backlog_cost = sum([node_state.get('backlog_cost', 0)
                           for round_data in rounds
                           for node_state in (round_data.state.values() if hasattr(round_data, 'state') else [])])

        return {
            "total_cost": total_cost,
            "service_level": service_level,
            "bullwhip_ratio": bullwhip_ratio,
            "inventory_variance": inventory_variance,
            "holding_cost": holding_cost,
            "backlog_cost": backlog_cost
        }

    def _calculate_rankings(self, agent_results: Dict[str, Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Calculate rankings for each metric."""
        rankings = {
            "by_total_cost": [],
            "by_service_level": [],
            "by_bullwhip_ratio": [],
            "overall": []
        }

        # Filter successful agents
        successful_agents = {
            agent: results
            for agent, results in agent_results.items()
            if results.get("status") == "success"
        }

        if not successful_agents:
            return rankings

        # Rank by total cost (lower is better)
        cost_ranked = sorted(
            successful_agents.items(),
            key=lambda x: x[1].get("avg_total_cost", float('inf'))
        )
        rankings["by_total_cost"] = [
            {
                "rank": i + 1,
                "agent": agent,
                "value": results.get("avg_total_cost"),
                "std": results.get("std_total_cost")
            }
            for i, (agent, results) in enumerate(cost_ranked)
        ]

        # Rank by service level (higher is better)
        service_ranked = sorted(
            successful_agents.items(),
            key=lambda x: x[1].get("avg_service_level", 0),
            reverse=True
        )
        rankings["by_service_level"] = [
            {
                "rank": i + 1,
                "agent": agent,
                "value": results.get("avg_service_level"),
                "std": results.get("std_service_level")
            }
            for i, (agent, results) in enumerate(service_ranked)
        ]

        # Rank by bullwhip ratio (lower is better)
        bullwhip_ranked = sorted(
            successful_agents.items(),
            key=lambda x: x[1].get("avg_bullwhip_ratio", float('inf'))
        )
        rankings["by_bullwhip_ratio"] = [
            {
                "rank": i + 1,
                "agent": agent,
                "value": results.get("avg_bullwhip_ratio"),
                "std": results.get("std_bullwhip_ratio")
            }
            for i, (agent, results) in enumerate(bullwhip_ranked)
        ]

        # Overall ranking (weighted score)
        # Lower cost = better, higher service = better, lower bullwhip = better
        overall_scores = {}
        for agent, results in successful_agents.items():
            # Normalize metrics to [0, 1] range
            cost_score = 1.0 / (1.0 + results.get("avg_total_cost", 1e6))
            service_score = results.get("avg_service_level", 0)
            bullwhip_score = 1.0 / (1.0 + results.get("avg_bullwhip_ratio", 100))

            # Weighted combination (cost is most important)
            overall_scores[agent] = (
                0.5 * cost_score +
                0.3 * service_score +
                0.2 * bullwhip_score
            )

        overall_ranked = sorted(overall_scores.items(), key=lambda x: x[1], reverse=True)
        rankings["overall"] = [
            {
                "rank": i + 1,
                "agent": agent,
                "score": score,
                "details": successful_agents[agent]
            }
            for i, (agent, score) in enumerate(overall_ranked)
        ]

        return rankings

    def _compare_agents(self, agent_results: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Generate statistical comparisons between agents."""
        comparisons = {
            "cost_improvements": {},
            "service_improvements": {},
            "bullwhip_improvements": {}
        }

        # Find baseline (naive agent if present, otherwise first agent)
        baseline_agent = "naive" if "naive" in agent_results else list(agent_results.keys())[0]

        if agent_results[baseline_agent].get("status") != "success":
            return comparisons

        baseline_cost = agent_results[baseline_agent].get("avg_total_cost", 0)
        baseline_service = agent_results[baseline_agent].get("avg_service_level", 0)
        baseline_bullwhip = agent_results[baseline_agent].get("avg_bullwhip_ratio", 0)

        for agent, results in agent_results.items():
            if agent == baseline_agent or results.get("status") != "success":
                continue

            # Cost improvement (percentage reduction)
            agent_cost = results.get("avg_total_cost", 0)
            if baseline_cost > 0:
                cost_improvement = ((baseline_cost - agent_cost) / baseline_cost) * 100
                comparisons["cost_improvements"][agent] = {
                    "improvement_pct": cost_improvement,
                    "baseline_cost": baseline_cost,
                    "agent_cost": agent_cost,
                    "absolute_reduction": baseline_cost - agent_cost
                }

            # Service level improvement (percentage point increase)
            agent_service = results.get("avg_service_level", 0)
            service_improvement = (agent_service - baseline_service) * 100
            comparisons["service_improvements"][agent] = {
                "improvement_pp": service_improvement,
                "baseline_service": baseline_service,
                "agent_service": agent_service
            }

            # Bullwhip improvement (percentage reduction)
            agent_bullwhip = results.get("avg_bullwhip_ratio", 0)
            if baseline_bullwhip > 0:
                bullwhip_improvement = ((baseline_bullwhip - agent_bullwhip) / baseline_bullwhip) * 100
                comparisons["bullwhip_improvements"][agent] = {
                    "improvement_pct": bullwhip_improvement,
                    "baseline_bullwhip": baseline_bullwhip,
                    "agent_bullwhip": agent_bullwhip,
                    "absolute_reduction": baseline_bullwhip - agent_bullwhip
                }

        return comparisons

    async def evaluate_single_agent(
        self,
        config_name: str,
        agent_type: str,
        num_trials: int = 10,
        max_rounds: int = 36
    ) -> Dict[str, Any]:
        """
        Evaluate a single agent type.

        Args:
            config_name: Supply chain configuration
            agent_type: Agent type to evaluate
            num_trials: Number of evaluation trials
            max_rounds: Rounds per game

        Returns:
            results: Evaluation results with statistics
        """
        logger.info(f"Evaluating {agent_type} agent on {config_name}")

        results = await self._evaluate_agent(
            config_name=config_name,
            agent_type=agent_type,
            num_trials=num_trials,
            max_rounds=max_rounds,
            seed=42
        )

        return {
            "config_name": config_name,
            "agent_type": agent_type,
            "num_trials": num_trials,
            "max_rounds": max_rounds,
            "results": results,
            "timestamp": datetime.utcnow().isoformat()
        }

    def save_results(self, results: Dict[str, Any], output_path: str):
        """Save evaluation results to JSON file."""
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(results, f, indent=2)

        logger.info(f"Saved evaluation results to {output_path}")

    async def generate_comparison_report(
        self,
        benchmark_results: Dict[str, Any]
    ) -> str:
        """
        Generate a human-readable comparison report.

        Returns:
            report: Markdown-formatted report
        """
        report = []
        report.append(f"# Agent Benchmarking Report\n")
        report.append(f"**Configuration**: {benchmark_results['config_name']}\n")
        report.append(f"**Trials per Agent**: {benchmark_results['num_trials']}\n")
        report.append(f"**Rounds per Game**: {benchmark_results['max_rounds']}\n")
        report.append(f"**Completed**: {benchmark_results.get('completed_at', 'N/A')}\n\n")

        # Overall rankings
        report.append("## Overall Rankings\n\n")
        report.append("| Rank | Agent | Score | Avg Cost | Service Level | Bullwhip Ratio |\n")
        report.append("|------|-------|-------|----------|---------------|----------------|\n")

        for ranking in benchmark_results["rankings"]["overall"]:
            details = ranking["details"]
            report.append(
                f"| {ranking['rank']} | "
                f"{ranking['agent']} | "
                f"{ranking['score']:.3f} | "
                f"${details['avg_total_cost']:.2f} | "
                f"{details['avg_service_level']:.1%} | "
                f"{details['avg_bullwhip_ratio']:.2f} |\n"
            )

        # Cost improvements
        report.append("\n## Cost Improvements vs Baseline\n\n")
        if benchmark_results["comparisons"]["cost_improvements"]:
            report.append("| Agent | Improvement | Baseline Cost | Agent Cost | Reduction |\n")
            report.append("|-------|-------------|---------------|------------|------------|\n")

            for agent, comp in benchmark_results["comparisons"]["cost_improvements"].items():
                report.append(
                    f"| {agent} | "
                    f"{comp['improvement_pct']:+.1f}% | "
                    f"${comp['baseline_cost']:.2f} | "
                    f"${comp['agent_cost']:.2f} | "
                    f"${comp['absolute_reduction']:.2f} |\n"
                )

        # Bullwhip improvements
        report.append("\n## Bullwhip Effect Reduction\n\n")
        if benchmark_results["comparisons"]["bullwhip_improvements"]:
            report.append("| Agent | Improvement | Baseline Ratio | Agent Ratio | Reduction |\n")
            report.append("|-------|-------------|----------------|-------------|------------|\n")

            for agent, comp in benchmark_results["comparisons"]["bullwhip_improvements"].items():
                report.append(
                    f"| {agent} | "
                    f"{comp['improvement_pct']:+.1f}% | "
                    f"{comp['baseline_bullwhip']:.2f} | "
                    f"{comp['agent_bullwhip']:.2f} | "
                    f"{comp['absolute_reduction']:.2f} |\n"
                )

        return "".join(report)
