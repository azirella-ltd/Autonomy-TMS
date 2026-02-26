"""
Monte Carlo Simulation Engine

Orchestrates probabilistic simulation runs by:
1. Sampling stochastic variables (lead times, demands, yields, capacities)
2. Running N scenario simulations
3. Collecting time-series data and KPIs per scenario
4. Computing statistical summaries (mean, percentiles, confidence intervals)
5. Generating risk alerts

Reference:
- Powell SDAM Chapter 11: Stochastic Programming
- Stanford Stochastic Programming Solutions
"""

import asyncio
import numpy as np
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal
from app.models.monte_carlo import (
    MonteCarloRun, MonteCarloScenario, MonteCarloTimeSeries,
    MonteCarloRiskAlert, SimulationStatus
)
from app.models.supply_chain_config import SupplyChainConfig
from app.models.mps import MPSPlan
from app.services.sc_planning.planner import SupplyChainPlanner
from app.services.sc_planning.stochastic_sampler import StochasticSampler
from app.services.sc_planning.simulation_execution_adapter import SimulationExecutionAdapter


class MonteCarloEngine:
    """
    Monte Carlo simulation orchestrator

    Runs N scenarios with sampled stochastic variables and computes
    statistical summaries for probabilistic planning and risk analysis.
    """

    def __init__(
        self,
        run_id: int,
        config_id: int,
        tenant_id: int,
        num_scenarios: int = 1000,
        random_seed: Optional[int] = None
    ):
        """
        Initialize Monte Carlo engine

        Args:
            run_id: MonteCarloRun ID for storing results
            config_id: Supply chain configuration ID
            tenant_id: Customer ID for multi-tenancy
            num_scenarios: Number of scenarios to simulate (default: 1000)
            random_seed: Random seed for reproducibility (optional)
        """
        self.run_id = run_id
        self.config_id = config_id
        self.tenant_id = tenant_id
        self.num_scenarios = num_scenarios
        self.random_seed = random_seed

        # Initialize random state
        self.rng = np.random.RandomState(seed=random_seed)

        # Initialize components
        self.sampler = StochasticSampler(config_id, tenant_id, scenario_id=None)

        # Results storage
        self.scenario_results: List[Dict[str, Any]] = []
        self.time_series_data: Dict[str, List[float]] = {}  # key: (product, site, week, metric)

    async def run_simulation(self, start_date: date, planning_horizon_weeks: int) -> None:
        """
        Execute Monte Carlo simulation

        Args:
            start_date: Simulation start date
            planning_horizon_weeks: Number of weeks to simulate
        """
        print("=" * 80)
        print(f"🎲 MONTE CARLO SIMULATION")
        print("=" * 80)
        print(f"Run ID: {self.run_id}")
        print(f"Config ID: {self.config_id}")
        print(f"Number of Scenarios: {self.num_scenarios}")
        print(f"Planning Horizon: {planning_horizon_weeks} weeks")
        print(f"Random Seed: {self.random_seed or 'None (non-deterministic)'}")
        print()

        # Update status to RUNNING
        await self._update_run_status(SimulationStatus.RUNNING, started_at=datetime.utcnow())

        try:
            # Run scenarios
            for scenario_num in range(1, self.num_scenarios + 1):
                print(f"Running scenario {scenario_num}/{self.num_scenarios}...")

                # Run single scenario
                scenario_result = await self._run_single_scenario(
                    scenario_num, start_date, planning_horizon_weeks
                )

                # Store results
                self.scenario_results.append(scenario_result)

                # Save scenario to database periodically (every 100 scenarios)
                if scenario_num % 100 == 0:
                    await self._save_scenarios_batch(scenario_num - 99, scenario_num)
                    await self._update_progress(scenario_num)

            # Save remaining scenarios
            remainder = self.num_scenarios % 100
            if remainder > 0:
                await self._save_scenarios_batch(self.num_scenarios - remainder + 1, self.num_scenarios)

            # Compute statistical summaries
            print("\n📊 Computing statistical summaries...")
            await self._compute_summary_statistics()

            # Compute time-series statistics
            print("📈 Computing time-series confidence bands...")
            await self._compute_time_series_statistics()

            # Generate risk alerts
            print("⚠️  Generating risk alerts...")
            await self._generate_risk_alerts()

            # Mark as completed
            execution_time = (datetime.utcnow() - (await self._get_run()).started_at).total_seconds()
            await self._update_run_status(
                SimulationStatus.COMPLETED,
                completed_at=datetime.utcnow(),
                execution_time_seconds=execution_time,
                progress_percent=100.0
            )

            print()
            print("=" * 80)
            print(f"✅ SIMULATION COMPLETE")
            print("=" * 80)
            print(f"Total Scenarios: {self.num_scenarios}")
            print(f"Execution Time: {execution_time:.2f} seconds")
            print()

        except Exception as e:
            print(f"\n❌ ERROR: {str(e)}")
            await self._update_run_status(
                SimulationStatus.FAILED,
                error_message=str(e),
                completed_at=datetime.utcnow()
            )
            raise

    async def _run_single_scenario(
        self,
        scenario_num: int,
        start_date: date,
        planning_horizon_weeks: int
    ) -> Dict[str, Any]:
        """
        Run a single simulation scenario with sampled stochastic variables

        Returns:
            Dictionary with scenario results including KPIs and time-series data
        """
        # Sample stochastic variables for this scenario
        sampled_inputs = await self._sample_scenario_inputs(start_date, planning_horizon_weeks)

        # Run supply chain planner with sampled inputs
        planner = SupplyChainPlanner(
            config_id=self.config_id,
            tenant_id=self.tenant_id,
            planning_horizon=planning_horizon_weeks * 7  # Convert weeks to days
        )

        # Override planner's sampler with our scenario-specific sampled values
        # This ensures deterministic behavior for this scenario
        planner.net_requirements_calculator.sampler = ScenarioSampler(sampled_inputs)

        # Execute planning
        supply_plans = await planner.run_planning(start_date=start_date)

        # Simulate execution and collect metrics
        # NOTE: This is a simplified simulation - in practice, you'd use
        # SimulationExecutionAdapter or a dedicated simulation engine
        metrics = await self._simulate_execution(supply_plans, sampled_inputs, planning_horizon_weeks)

        return {
            "scenario_number": scenario_num,
            "sampled_inputs": sampled_inputs,
            "kpis": metrics["kpis"],
            "time_series": metrics["time_series"],
        }

    async def _sample_scenario_inputs(
        self,
        start_date: date,
        planning_horizon_weeks: int
    ) -> Dict[str, Any]:
        """
        Sample all stochastic variables for one scenario

        Returns:
            Dictionary with sampled values for:
            - lead_times: {(from_node, to_node): days}
            - demands: {(product, site, week): quantity}
            - yields: {(product, site): percentage}
            - capacities: {(resource, site, week): quantity}
        """
        sampled = {
            "lead_times": {},
            "demands": {},
            "yields": {},
            "capacities": {},
            "setup_times": {},
        }

        # Sample lead times for all sourcing lanes
        async with SessionLocal() as db:
            config = await db.get(SupplyChainConfig, self.config_id)

            # Sample lead times for each lane
            for lane in config.lanes:
                lead_time = self.sampler.sample_lead_time(
                    from_node_id=lane.from_node_id,
                    to_node_id=lane.to_node_id,
                    product_id=lane.item_id
                )
                sampled["lead_times"][f"{lane.from_node_id}->{lane.to_node_id}"] = lead_time

            # Sample demand — lookup forecast mean from market_demands, fall back to 100
            from app.models.supply_chain_config import MarketDemand
            market_demands = {
                (md.product_id, md.market_id): md
                for md in (config.market_demands or [])
            }

            for node in config.nodes:
                if node.master_node_type == "MARKET_DEMAND":
                    for item in config.items:
                        # Try to find forecast mean from market demand config
                        md = market_demands.get((item.id, node.id)) or market_demands.get((str(item.id), node.id))
                        if md and md.demand_pattern:
                            params = md.demand_pattern.get("parameters", {})
                            mean_demand = params.get("mean", params.get("final_demand", 100))
                        else:
                            mean_demand = 100  # Fallback when no forecast exists
                        std_demand = max(1, mean_demand * 0.2)

                        for week in range(planning_horizon_weeks):
                            demand = max(0, self.rng.normal(mean_demand, std_demand))
                            sampled["demands"][f"{item.id}_{node.id}_week{week}"] = demand

            # Sample yields for manufacturing nodes
            for node in config.nodes:
                if node.master_node_type == "MANUFACTURER":
                    for item in config.items:
                        # Sample yield percentage (e.g., 0.98 = 98% yield)
                        yield_pct = self.sampler.sample_yield(
                            product_id=item.id,
                            site_id=node.id
                        )
                        sampled["yields"][f"{item.id}_{node.id}"] = yield_pct

            # Sample capacities for production resources
            for node in config.nodes:
                if node.master_node_type == "MANUFACTURER":
                    for week in range(planning_horizon_weeks):
                        capacity = self.sampler.sample_capacity(
                            site_id=node.id,
                            resource_name="Production",
                            period_start=start_date + timedelta(weeks=week)
                        )
                        sampled["capacities"][f"{node.id}_week{week}"] = capacity

        return sampled

    async def _simulate_execution(
        self,
        supply_plans: List,
        sampled_inputs: Dict[str, Any],
        planning_horizon_weeks: int
    ) -> Dict[str, Any]:
        """
        Simulate execution of supply plans and collect metrics

        This is a simplified simulation that computes KPIs based on
        the supply plan and sampled stochastic variables.

        In practice, you'd integrate with SimulationExecutionAdapter or
        a dedicated SimPy-based simulation engine.

        Returns:
            Dictionary with:
            - kpis: Scenario-level KPIs (total_cost, service_level, etc.)
            - time_series: Week-by-week metrics for confidence bands
        """
        # Initialize metrics
        kpis = {
            "total_cost": 0.0,
            "holding_cost": 0.0,
            "backlog_cost": 0.0,
            "ordering_cost": 0.0,
            "service_level": 95.0,  # Placeholder
            "final_inventory": 0.0,
            "final_backlog": 0.0,
            "max_inventory": 0.0,
            "max_backlog": 0.0,
            "had_stockout": False,
            "had_overstock": False,
            "had_capacity_violation": False,
        }

        time_series = []

        # Simulate week by week
        inventory = 1000  # Starting inventory
        backlog = 0

        for week in range(planning_horizon_weeks):
            # Get demand for this week
            demand_key = f"1_1_week{week}"  # Simplified: product 1, site 1
            demand = sampled_inputs["demands"].get(demand_key, 100)

            # Simplified inventory dynamics
            # Receive shipments (from supply plans with lead time offset)
            receipts = 100  # Placeholder

            # Update inventory
            inventory += receipts
            inventory -= demand

            # Track backlog
            if inventory < 0:
                backlog += abs(inventory)
                inventory = 0
                kpis["had_stockout"] = True

            # Calculate costs
            holding_cost_per_unit = 1.0
            backlog_cost_per_unit = 2.0

            period_holding_cost = inventory * holding_cost_per_unit
            period_backlog_cost = backlog * backlog_cost_per_unit

            kpis["holding_cost"] += period_holding_cost
            kpis["backlog_cost"] += period_backlog_cost

            # Track max values
            kpis["max_inventory"] = max(kpis["max_inventory"], inventory)
            kpis["max_backlog"] = max(kpis["max_backlog"], backlog)

            # Store time-series data
            time_series.append({
                "week": week,
                "inventory": inventory,
                "backlog": backlog,
                "demand": demand,
                "receipts": receipts,
                "holding_cost": period_holding_cost,
                "backlog_cost": period_backlog_cost,
            })

        # Final metrics
        kpis["final_inventory"] = inventory
        kpis["final_backlog"] = backlog
        kpis["total_cost"] = kpis["holding_cost"] + kpis["backlog_cost"] + kpis["ordering_cost"]

        # Check for overstock (inventory > 2x target)
        target_inventory = 500
        if kpis["max_inventory"] > 2 * target_inventory:
            kpis["had_overstock"] = True

        return {
            "kpis": kpis,
            "time_series": time_series,
        }

    async def _compute_summary_statistics(self) -> None:
        """Compute summary statistics across all scenarios"""
        # Extract KPIs from all scenarios
        total_costs = [s["kpis"]["total_cost"] for s in self.scenario_results]
        service_levels = [s["kpis"]["service_level"] for s in self.scenario_results]
        final_inventories = [s["kpis"]["final_inventory"] for s in self.scenario_results]
        final_backlogs = [s["kpis"]["final_backlog"] for s in self.scenario_results]

        # Compute statistics
        summary_stats = {
            "total_cost": {
                "mean": float(np.mean(total_costs)),
                "median": float(np.median(total_costs)),
                "std": float(np.std(total_costs)),
                "p5": float(np.percentile(total_costs, 5)),
                "p50": float(np.percentile(total_costs, 50)),
                "p95": float(np.percentile(total_costs, 95)),
                "min": float(np.min(total_costs)),
                "max": float(np.max(total_costs)),
            },
            "service_level": {
                "mean": float(np.mean(service_levels)),
                "median": float(np.median(service_levels)),
                "std": float(np.std(service_levels)),
                "p5": float(np.percentile(service_levels, 5)),
                "p95": float(np.percentile(service_levels, 95)),
            },
            "final_inventory": self._compute_stats(final_inventories),
            "final_backlog": self._compute_stats(final_backlogs),
        }

        # Compute risk metrics
        stockout_count = sum(1 for s in self.scenario_results if s["kpis"]["had_stockout"])
        overstock_count = sum(1 for s in self.scenario_results if s["kpis"]["had_overstock"])
        capacity_violation_count = sum(1 for s in self.scenario_results if s["kpis"]["had_capacity_violation"])

        risk_metrics = {
            "stockout_probability": stockout_count / self.num_scenarios,
            "overstock_probability": overstock_count / self.num_scenarios,
            "capacity_violation_probability": capacity_violation_count / self.num_scenarios,
        }

        # Save to database
        async with SessionLocal() as db:
            run = await db.get(MonteCarloRun, self.run_id)
            run.summary_statistics = summary_stats
            run.risk_metrics = risk_metrics
            await db.commit()

        print(f"  Summary Statistics:")
        print(f"    Total Cost: ${summary_stats['total_cost']['mean']:.2f} "
              f"(P5: ${summary_stats['total_cost']['p5']:.2f}, "
              f"P95: ${summary_stats['total_cost']['p95']:.2f})")
        print(f"    Service Level: {summary_stats['service_level']['mean']:.1f}%")
        print(f"  Risk Metrics:")
        print(f"    Stockout Probability: {risk_metrics['stockout_probability']:.1%}")
        print(f"    Overstock Probability: {risk_metrics['overstock_probability']:.1%}")

    async def _compute_time_series_statistics(self) -> None:
        """Compute time-series statistics for confidence bands"""
        # Aggregate time-series data by week
        weeks_data: Dict[int, Dict[str, List[float]]] = {}

        for scenario in self.scenario_results:
            for ts_point in scenario["time_series"]:
                week = ts_point["week"]
                if week not in weeks_data:
                    weeks_data[week] = {
                        "inventory": [],
                        "backlog": [],
                        "demand": [],
                        "receipts": [],
                    }

                weeks_data[week]["inventory"].append(ts_point["inventory"])
                weeks_data[week]["backlog"].append(ts_point["backlog"])
                weeks_data[week]["demand"].append(ts_point["demand"])
                weeks_data[week]["receipts"].append(ts_point["receipts"])

        # Compute statistics for each week and metric
        async with SessionLocal() as db:
            run = await db.get(MonteCarloRun, self.run_id)
            start_date = run.start_date

            time_series_records = []

            for week, metrics in weeks_data.items():
                week_date = start_date + timedelta(weeks=week)

                for metric_name, values in metrics.items():
                    ts_record = MonteCarloTimeSeries(
                        run_id=self.run_id,
                        product_id=1,  # Simplified
                        site_id=1,  # Simplified
                        period_week=week,
                        period_date=week_date,
                        metric_name=metric_name,
                        mean_value=float(np.mean(values)),
                        median_value=float(np.median(values)),
                        std_dev=float(np.std(values)),
                        p5_value=float(np.percentile(values, 5)),
                        p10_value=float(np.percentile(values, 10)),
                        p25_value=float(np.percentile(values, 25)),
                        p75_value=float(np.percentile(values, 75)),
                        p90_value=float(np.percentile(values, 90)),
                        p95_value=float(np.percentile(values, 95)),
                        min_value=float(np.min(values)),
                        max_value=float(np.max(values)),
                    )
                    time_series_records.append(ts_record)

            # Bulk insert
            db.add_all(time_series_records)
            await db.commit()

        print(f"  Created {len(time_series_records)} time-series statistical records")

    async def _generate_risk_alerts(self) -> None:
        """Generate risk alerts based on simulation results"""
        async with SessionLocal() as db:
            run = await db.get(MonteCarloRun, self.run_id)
            risk_metrics = run.risk_metrics

            alerts = []

            # High stockout risk
            if risk_metrics["stockout_probability"] > 0.10:  # >10% chance
                alerts.append(MonteCarloRiskAlert(
                    run_id=self.run_id,
                    alert_type="stockout_risk",
                    severity="high" if risk_metrics["stockout_probability"] > 0.25 else "medium",
                    title="High Stockout Risk Detected",
                    description=f"Stockout probability is {risk_metrics['stockout_probability']:.1%}, "
                                f"exceeding acceptable threshold of 10%.",
                    probability=risk_metrics["stockout_probability"],
                    recommendation="Consider increasing safety stock levels or expediting supplier lead times."
                ))

            # High overstock risk
            if risk_metrics["overstock_probability"] > 0.20:  # >20% chance
                alerts.append(MonteCarloRiskAlert(
                    run_id=self.run_id,
                    alert_type="overstock_risk",
                    severity="medium",
                    title="Overstock Risk Detected",
                    description=f"Overstock probability is {risk_metrics['overstock_probability']:.1%}.",
                    probability=risk_metrics["overstock_probability"],
                    recommendation="Review inventory targets and consider reducing order quantities."
                ))

            # Capacity violations
            if risk_metrics["capacity_violation_probability"] > 0.05:  # >5% chance
                alerts.append(MonteCarloRiskAlert(
                    run_id=self.run_id,
                    alert_type="capacity_risk",
                    severity="critical" if risk_metrics["capacity_violation_probability"] > 0.15 else "high",
                    title="Capacity Constraint Violations",
                    description=f"Capacity violation probability is {risk_metrics['capacity_violation_probability']:.1%}.",
                    probability=risk_metrics["capacity_violation_probability"],
                    recommendation="Review production capacity and consider adding shifts or outsourcing."
                ))

            # Bulk insert alerts
            db.add_all(alerts)
            await db.commit()

            print(f"  Generated {len(alerts)} risk alerts")

    def _compute_stats(self, values: List[float]) -> Dict[str, float]:
        """Helper to compute statistics for a list of values"""
        return {
            "mean": float(np.mean(values)),
            "median": float(np.median(values)),
            "std": float(np.std(values)),
            "p5": float(np.percentile(values, 5)),
            "p50": float(np.percentile(values, 50)),
            "p95": float(np.percentile(values, 95)),
            "min": float(np.min(values)),
            "max": float(np.max(values)),
        }

    async def _save_scenarios_batch(self, start_num: int, end_num: int) -> None:
        """Save a batch of scenarios to database"""
        async with SessionLocal() as db:
            scenario_records = []

            for scenario in self.scenario_results[start_num-1:end_num]:
                record = MonteCarloScenario(
                    run_id=self.run_id,
                    scenario_number=scenario["scenario_number"],
                    sampled_inputs=scenario["sampled_inputs"],
                    total_cost=scenario["kpis"]["total_cost"],
                    holding_cost=scenario["kpis"]["holding_cost"],
                    backlog_cost=scenario["kpis"]["backlog_cost"],
                    ordering_cost=scenario["kpis"]["ordering_cost"],
                    service_level=scenario["kpis"]["service_level"],
                    final_inventory=scenario["kpis"]["final_inventory"],
                    final_backlog=scenario["kpis"]["final_backlog"],
                    max_inventory=scenario["kpis"]["max_inventory"],
                    max_backlog=scenario["kpis"]["max_backlog"],
                    had_stockout=scenario["kpis"]["had_stockout"],
                    had_overstock=scenario["kpis"]["had_overstock"],
                    had_capacity_violation=scenario["kpis"]["had_capacity_violation"],
                )
                scenario_records.append(record)

            db.add_all(scenario_records)
            await db.commit()

    async def _update_run_status(
        self,
        status: SimulationStatus,
        **kwargs
    ) -> None:
        """Update run status and metadata"""
        async with SessionLocal() as db:
            run = await db.get(MonteCarloRun, self.run_id)
            run.status = status

            for key, value in kwargs.items():
                setattr(run, key, value)

            await db.commit()

    async def _update_progress(self, scenarios_completed: int) -> None:
        """Update progress percentage"""
        progress = (scenarios_completed / self.num_scenarios) * 100
        await self._update_run_status(
            SimulationStatus.RUNNING,
            scenarios_completed=scenarios_completed,
            progress_percent=progress
        )

    async def _get_run(self) -> MonteCarloRun:
        """Get the current run object"""
        async with SessionLocal() as db:
            return await db.get(MonteCarloRun, self.run_id)


class ScenarioSampler:
    """
    Deterministic sampler that returns pre-sampled values for a scenario

    This replaces StochasticSampler during scenario execution to ensure
    each scenario uses its pre-sampled stochastic variable values.
    """

    def __init__(self, sampled_inputs: Dict[str, Any]):
        self.sampled_inputs = sampled_inputs

    def sample_lead_time(self, from_node_id: int, to_node_id: int, product_id: int) -> int:
        key = f"{from_node_id}->{to_node_id}"
        return self.sampled_inputs["lead_times"].get(key, 2)  # Default 2 days

    def sample_yield(self, product_id: int, site_id: int) -> float:
        key = f"{product_id}_{site_id}"
        return self.sampled_inputs["yields"].get(key, 1.0)  # Default 100% yield

    def sample_capacity(self, site_id: int, resource_name: str, period_start: date) -> float:
        key = f"{site_id}_week{(period_start - date.today()).days // 7}"
        return self.sampled_inputs["capacities"].get(key, 1000)  # Default 1000 units
