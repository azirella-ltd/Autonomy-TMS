"""
DAG-Aware Stochastic Supply Chain Simulator (SimPy)

Wraps the same DAG topology as dag_simulator.py but introduces stochastic
elements via SimPy discrete-event simulation:

- Lead times sampled from distributions (triangular/normal per VendorLeadTime CV)
- Demand sampled from forecast distributions (P10/P50/P90)
- Supplier reliability: random fulfillment failures per supplier.reliability
- Capacity disruptions: random capacity reductions

Used for Monte Carlo runs (128 runs x 52 weeks) to generate robust training
data with variance across scenarios.

Usage:
    topology = await load_topology(config_id, db)
    simulator = DAGSimPySimulator(topology)
    results = simulator.run_monte_carlo(num_runs=128, num_periods=52, seed=42)

This is permanent deployment infrastructure for warm-starting AI models.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import simpy

from app.services.dag_simulator import (
    LoadedTopology,
    SimulationResult,
    SimDecision,
    SimPeriodState,
    SimKPIs,
    PipelineShipment,
    SiteProductState,
    OrderingStrategy,
    _is_supply,
    _is_demand,
    _is_inventory,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Stochastic Configuration
# ============================================================================


@dataclass
class StochasticConfig:
    """Configuration for stochastic simulation parameters."""

    # Lead time variability
    lead_time_cv: float = 0.20          # Coefficient of variation for lead times
    lead_time_distribution: str = "triangular"  # "triangular", "normal", "lognormal"

    # Demand variability
    demand_cv: float = 0.15             # CV around forecast
    demand_distribution: str = "lognormal"  # "normal", "lognormal", "triangular"
    use_forecast_percentiles: bool = True   # Use P10/P50/P90 if available

    # Supplier reliability
    enable_supplier_failures: bool = True
    default_reliability: float = 0.95   # P(on-time & full delivery)
    partial_delivery_min: float = 0.5   # Min fraction if partial

    # Capacity disruptions
    enable_capacity_disruptions: bool = True
    disruption_probability: float = 0.02    # Per site per period
    disruption_severity_range: Tuple[float, float] = (0.3, 0.7)  # Capacity reduction

    # Yield variability (for manufacturers)
    yield_cv: float = 0.05
    enable_yield_variability: bool = False


@dataclass
class MonteCarloResult:
    """Aggregated Monte Carlo results across runs."""
    num_runs: int
    num_periods: int
    config_id: int
    config_name: str

    # Individual run results
    runs: List[SimulationResult]

    # Aggregated KPIs (across runs)
    kpi_mean: SimKPIs
    kpi_std: SimKPIs
    kpi_p10: SimKPIs
    kpi_p90: SimKPIs

    # Per-site per-product aggregated time series
    # site_name -> product_id -> metric_name -> [mean, std] arrays of length num_periods
    aggregated_history: Dict[str, Dict[str, Dict[str, Tuple[List[float], List[float]]]]]


# ============================================================================
# SimPy Event-Driven Simulator
# ============================================================================


class DAGSimPySimulator:
    """
    Stochastic discrete-event simulator for arbitrary DAG topologies.

    Uses SimPy for event scheduling (shipment arrivals, demand events,
    disruptions) rather than period-by-period stepping.

    Produces Monte Carlo training data for GNN and TRM models.
    """

    def __init__(
        self,
        topology: LoadedTopology,
        strategy: OrderingStrategy = OrderingStrategy.BASE_STOCK,
        stochastic_config: Optional[StochasticConfig] = None,
        holding_cost_rate: float = 0.005,
        backlog_cost_rate: float = 0.01,
        pid_kp: float = 0.6,
        pid_ki: float = 0.15,
        pid_kd: float = 0.05,
    ):
        self.topology = topology
        self.strategy = strategy
        self.stoch = stochastic_config or StochasticConfig()
        self.holding_cost_rate = holding_cost_rate
        self.backlog_cost_rate = backlog_cost_rate
        self.pid_kp = pid_kp
        self.pid_ki = pid_ki
        self.pid_kd = pid_kd

    def run_monte_carlo(
        self,
        num_runs: int = 128,
        num_periods: int = 52,
        seed: int = 42,
        progress_callback=None,
    ) -> MonteCarloResult:
        """
        Execute Monte Carlo simulation: multiple stochastic runs.

        Args:
            num_runs: Number of independent simulation runs
            num_periods: Periods per run (typically weeks)
            seed: Base random seed (each run uses seed + run_index)
            progress_callback: Optional callable(run, num_runs) for progress

        Returns:
            MonteCarloResult with individual and aggregated results
        """
        runs: List[SimulationResult] = []

        for run_idx in range(num_runs):
            run_seed = seed + run_idx
            result = self.simulate(
                num_periods=num_periods,
                seed=run_seed,
            )
            runs.append(result)

            if progress_callback:
                progress_callback(run_idx + 1, num_runs)

        # Aggregate KPIs
        kpi_mean, kpi_std, kpi_p10, kpi_p90 = self._aggregate_kpis(runs)

        # Aggregate time series
        agg_history = self._aggregate_history(runs, num_periods)

        return MonteCarloResult(
            num_runs=num_runs,
            num_periods=num_periods,
            config_id=self.topology.config.id,
            config_name=self.topology.config.name,
            runs=runs,
            kpi_mean=kpi_mean,
            kpi_std=kpi_std,
            kpi_p10=kpi_p10,
            kpi_p90=kpi_p90,
            aggregated_history=agg_history,
        )

    def simulate(
        self,
        num_periods: int = 52,
        seed: int = 42,
    ) -> SimulationResult:
        """
        Run a single stochastic simulation using SimPy.

        Each period is a SimPy timeout(1). Within each period:
        1. Process arriving shipments (with stochastic delivery)
        2. Generate stochastic demand
        3. Process inventory sites (fulfill, order, track)
        4. Schedule new shipments with stochastic lead times
        5. Apply disruptions
        """
        rng = np.random.default_rng(seed)
        env = simpy.Environment()

        # Initialize per-run state
        state: Dict[str, Dict[str, SiteProductState]] = {}
        pipeline: List[_StochasticShipment] = []
        period_states: List[SimPeriodState] = []
        decisions: List[SimDecision] = []
        all_shipments: List[PipelineShipment] = []
        total_demand = 0.0
        total_fulfilled = 0.0

        # Disruption state: site_name -> capacity_multiplier (1.0 = normal)
        capacity_mult: Dict[str, float] = {
            s.name: 1.0 for s in self.topology.sites
        }

        # Initialize state
        topo = self.topology
        for site in topo.sites:
            state[site.name] = {}
            for product in topo.products:
                pid = self._product_id(product)
                initial_inv = topo.initial_inventory.get(site.name, {}).get(pid, 0.0)

                policy_params = topo.inv_policies.get(site.name, {}).get(pid, {})
                ss_days = policy_params.get("safety_stock_days", 14)
                forecast = self._get_forecast(site.name, pid, 0)
                daily_demand = forecast / 7.0 if forecast > 0 else 0
                ss = daily_demand * ss_days
                target = ss + forecast * 2

                state[site.name][pid] = SiteProductState(
                    on_hand=initial_inv,
                    safety_stock=ss,
                    target_inventory=target,
                )

        # SimPy process: weekly period loop
        def weekly_process(env):
            nonlocal total_demand, total_fulfilled

            for period in range(num_periods):
                # Step 1: Apply capacity disruptions
                if self.stoch.enable_capacity_disruptions:
                    self._apply_disruptions(rng, capacity_mult, period)

                # Step 2: Receive arriving shipments (stochastic delivery)
                self._receive_stochastic_shipments(
                    pipeline, state, period, rng, capacity_mult
                )

                # Step 3: Generate stochastic demand
                demand_by_site = self._generate_stochastic_demand(period, rng)

                # Step 4: Process in reverse topo order
                for site_name in reversed(topo.topo_order):
                    site = self._get_site(site_name)
                    if not site:
                        continue

                    if _is_demand(site):
                        pass

                    elif _is_inventory(site):
                        d, f = self._process_inventory_site_stochastic(
                            site, period, state, demand_by_site,
                            pipeline, decisions, all_shipments, rng,
                            capacity_mult,
                        )
                        total_demand += d
                        total_fulfilled += f

                    elif _is_supply(site):
                        pass  # Supply sites fulfilled via pipeline scheduling

                # Step 5: Record period state
                self._record_period_state(
                    period, state, period_states, topo,
                )

                # Step 6: Track in-flight orders for exceptions
                self._track_orders_stochastic(
                    pipeline, period, decisions,
                )

                yield env.timeout(1)

        env.process(weekly_process(env))
        env.run()

        # Compute KPIs
        kpis = self._compute_kpis(
            total_demand, total_fulfilled, period_states,
            state, num_periods, topo,
        )

        # Build history
        history = self._build_history(topo, state, period_states)

        return SimulationResult(
            config_id=topo.config.id,
            config_name=topo.config.name,
            num_periods=num_periods,
            num_sites=len(topo.sites),
            num_products=len(topo.products),
            period_states=period_states,
            decisions=decisions,
            shipments=[s.to_pipeline_shipment() for s in all_shipments]
            if all_shipments and hasattr(all_shipments[0], 'to_pipeline_shipment')
            else all_shipments,
            kpis=kpis,
            site_product_history=history,
            strategy=self.strategy.value,
            seed=seed,
        )

    # ========================================================================
    # Stochastic Demand Generation
    # ========================================================================

    def _generate_stochastic_demand(
        self, period: int, rng: np.random.Generator,
    ) -> Dict[str, Dict[str, float]]:
        """Generate demand with stochastic noise around forecast."""
        demand_by_site: Dict[str, Dict[str, float]] = {}
        topo = self.topology

        for site in topo.demand_sites:
            demand_by_site[site.name] = {}
            for product in topo.products:
                pid = self._product_id(product)
                forecast = self._get_forecast(site.name, pid, period)

                if forecast <= 0:
                    demand_by_site[site.name][pid] = 0.0
                    continue

                demand = self._sample_demand(forecast, rng)
                demand_by_site[site.name][pid] = max(0.0, demand)

        return demand_by_site

    def _sample_demand(self, forecast: float, rng: np.random.Generator) -> float:
        """Sample demand from configured distribution around forecast."""
        cv = self.stoch.demand_cv
        if cv <= 0:
            return forecast

        dist = self.stoch.demand_distribution

        if dist == "normal":
            std = forecast * cv
            return rng.normal(forecast, std)

        elif dist == "lognormal":
            # LogNormal: E[X] = forecast, CV = cv
            sigma2 = math.log(1 + cv ** 2)
            sigma = math.sqrt(sigma2)
            mu = math.log(forecast) - sigma2 / 2
            return float(rng.lognormal(mu, sigma))

        elif dist == "triangular":
            low = forecast * (1 - 2 * cv)
            high = forecast * (1 + 2 * cv)
            return float(rng.triangular(max(0, low), forecast, high))

        else:
            # Fallback to normal
            return rng.normal(forecast, forecast * cv)

    # ========================================================================
    # Stochastic Lead Times & Shipment Processing
    # ========================================================================

    def _sample_lead_time(
        self, base_lead_time_days: int, rng: np.random.Generator
    ) -> int:
        """Sample a stochastic lead time around the base value."""
        cv = self.stoch.lead_time_cv
        if cv <= 0 or base_lead_time_days <= 0:
            return max(1, base_lead_time_days)

        dist = self.stoch.lead_time_distribution
        base = float(base_lead_time_days)

        if dist == "triangular":
            low = base * (1 - cv)
            high = base * (1 + 2 * cv)
            sampled = rng.triangular(max(1, low), base, high)

        elif dist == "normal":
            std = base * cv
            sampled = rng.normal(base, std)

        elif dist == "lognormal":
            sigma2 = math.log(1 + cv ** 2)
            sigma = math.sqrt(sigma2)
            mu = math.log(base) - sigma2 / 2
            sampled = rng.lognormal(mu, sigma)

        else:
            sampled = rng.normal(base, base * cv)

        # Lead time must be at least 1 day, convert to periods (weeks)
        return max(1, round(sampled / 7.0))

    def _receive_stochastic_shipments(
        self,
        pipeline: List[_StochasticShipment],
        state: Dict[str, Dict[str, SiteProductState]],
        period: int,
        rng: np.random.Generator,
        capacity_mult: Dict[str, float],
    ):
        """Process arriving shipments with supplier reliability."""
        arriving = [s for s in pipeline if s.arrival_period <= period]
        remaining = [s for s in pipeline if s.arrival_period > period]
        pipeline.clear()
        pipeline.extend(remaining)

        for shipment in arriving:
            target_site = shipment.target_site
            pid = shipment.product_id

            sp = state.get(target_site, {}).get(pid)
            if not sp:
                continue

            delivered_qty = shipment.quantity

            # Apply supplier reliability
            if self.stoch.enable_supplier_failures:
                reliability = self.topology.vendor_reliability.get(
                    shipment.source_site, self.stoch.default_reliability
                )
                if rng.random() > reliability:
                    # Delivery failure: partial or no delivery
                    if rng.random() < 0.5:
                        # Complete failure
                        delivered_qty = 0.0
                    else:
                        # Partial delivery
                        frac = rng.uniform(
                            self.stoch.partial_delivery_min, 0.95
                        )
                        delivered_qty = shipment.quantity * frac

            # Apply capacity disruption at receiving site
            site_cap = capacity_mult.get(target_site, 1.0)
            if site_cap < 1.0:
                delivered_qty *= site_cap

            sp.on_hand += delivered_qty
            sp.in_transit -= shipment.quantity  # Remove full expected qty
            sp.in_transit = max(0, sp.in_transit)

    # ========================================================================
    # Inventory Site Processing (Stochastic)
    # ========================================================================

    def _process_inventory_site_stochastic(
        self,
        site,
        period: int,
        state: Dict[str, Dict[str, SiteProductState]],
        demand_by_site: Dict[str, Dict[str, float]],
        pipeline: List[_StochasticShipment],
        decisions: List[SimDecision],
        all_shipments: list,
        rng: np.random.Generator,
        capacity_mult: Dict[str, float],
    ) -> Tuple[float, float]:
        """Process an inventory site with stochastic elements. Returns (demand, fulfilled)."""
        topo = self.topology
        period_demand = 0.0
        period_fulfilled = 0.0

        for product in topo.products:
            pid = self._product_id(product)
            sp = state.get(site.name, {}).get(pid)
            if not sp:
                continue

            # Aggregate demand from downstream
            total_demand = 0.0
            for ds_name, lane in topo.downstream_map.get(site.name, []):
                ds_demand = demand_by_site.get(ds_name, {}).get(pid, 0.0)
                ds_state = state.get(ds_name, {}).get(pid)
                if ds_state and _is_inventory(self._get_site(ds_name)):
                    ds_demand = ds_state.backlog
                total_demand += ds_demand

            total_need = total_demand + sp.backlog

            # Apply capacity constraint
            site_cap = capacity_mult.get(site.name, 1.0)
            available = sp.on_hand * site_cap

            fulfilled = min(available, total_need)
            sp.on_hand -= fulfilled
            sp.backlog = total_need - fulfilled

            sp.demand_history.append(total_demand)
            period_demand += total_demand
            period_fulfilled += fulfilled

            # Ship downstream
            if fulfilled > 0:
                self._ship_downstream_stochastic(
                    site, pid, fulfilled, period, state,
                    pipeline, all_shipments, decisions, rng,
                )

            # Record ATP decision
            decisions.append(SimDecision(
                period=period,
                site_id=site.id,
                site_name=site.name,
                product_id=pid,
                decision_type="atp",
                quantity=fulfilled,
                context={
                    "demand": total_demand,
                    "on_hand_before": sp.on_hand + fulfilled,
                    "fill_rate": fulfilled / total_need if total_need > 0 else 1.0,
                    "capacity_multiplier": site_cap,
                },
            ))

            # Compute order
            inv_position = sp.on_hand + sp.in_transit - sp.backlog
            order_qty = self._compute_order(sp, inv_position, pid, period)

            if order_qty > 0:
                sp.order_history.append(order_qty)
                self._place_order_upstream_stochastic(
                    site, pid, order_qty, period, state,
                    pipeline, all_shipments, rng,
                )

                decisions.append(SimDecision(
                    period=period,
                    site_id=site.id,
                    site_name=site.name,
                    product_id=pid,
                    decision_type="order",
                    quantity=order_qty,
                    context={
                        "on_hand": sp.on_hand,
                        "backlog": sp.backlog,
                        "in_transit": sp.in_transit,
                        "safety_stock": sp.safety_stock,
                        "target_inventory": sp.target_inventory,
                        "strategy": self.strategy.value,
                    },
                ))
            else:
                sp.order_history.append(0)

            # Periodic safety stock update with decision recording
            if period > 0 and period % 4 == 0 and len(sp.demand_history) >= 4:
                old_ss = sp.safety_stock
                self._update_safety_stock(sp)
                if abs(sp.safety_stock - old_ss) > 0.01:
                    decisions.append(SimDecision(
                        period=period,
                        site_id=site.id,
                        site_name=site.name,
                        product_id=pid,
                        decision_type="safety_stock",
                        quantity=sp.safety_stock,
                        context={
                            "old_safety_stock": old_ss,
                            "new_safety_stock": sp.safety_stock,
                            "avg_demand": float(np.mean(sp.demand_history[-4:])),
                        },
                    ))

            # Rebalancing decision
            if sp.on_hand > 0 and sp.demand_history:
                avg_d = float(np.mean(sp.demand_history[-4:])) if len(sp.demand_history) >= 4 else sp.demand_history[-1]
                if avg_d > 0:
                    this_dos = sp.on_hand / (avg_d / 7.0)
                    for ds_name, lane in topo.downstream_map.get(site.name, []):
                        ds_sp = state.get(ds_name, {}).get(pid)
                        if ds_sp and ds_sp.demand_history:
                            ds_avg = float(np.mean(ds_sp.demand_history[-4:])) if len(ds_sp.demand_history) >= 4 else ds_sp.demand_history[-1]
                            if ds_avg > 0:
                                ds_dos = ds_sp.on_hand / (ds_avg / 7.0)
                                if this_dos > 2 * ds_dos and ds_dos < 14:
                                    qty = min(sp.on_hand * 0.2, (avg_d / 7.0) * 7)
                                    if qty > 0:
                                        decisions.append(SimDecision(
                                            period=period, site_id=site.id, site_name=site.name,
                                            product_id=pid, decision_type="rebalance", quantity=qty,
                                            context={"to_site": ds_name, "source_dos": this_dos, "dest_dos": ds_dos, "reason": "dos_imbalance"},
                                        ))
                                        break

            # Forecast adjustment decision
            if period >= 4 and len(sp.demand_history) >= 4:
                recent_avg = float(np.mean(sp.demand_history[-4:]))
                forecast = self._get_forecast(site.name, pid, period)
                if forecast > 0:
                    dev = (recent_avg - forecast) / forecast
                    if abs(dev) > 0.15:
                        decisions.append(SimDecision(
                            period=period, site_id=site.id, site_name=site.name,
                            product_id=pid, decision_type="forecast_adjustment", quantity=recent_avg,
                            context={"current_forecast": forecast, "deviation_pct": round(dev, 4),
                                     "direction": "up" if dev > 0 else "down", "signal_source": "simulation"},
                        ))

            # Quality decision (stochastic, 5% chance)
            if period > 0 and period % 2 == 0 and sp.on_hand > 0 and rng.random() < 0.05:
                defect_rate = float(rng.uniform(0.01, 0.08))
                disp = "accept" if defect_rate < 0.03 else "rework" if defect_rate < 0.06 else "reject"
                decisions.append(SimDecision(
                    period=period, site_id=site.id, site_name=site.name,
                    product_id=pid, decision_type="quality", quantity=min(sp.on_hand * 0.1, 50),
                    context={"defect_rate": round(defect_rate, 4), "disposition": disp, "inspection_type": "incoming"},
                ))

            # Maintenance decision (every 8 periods)
            if period > 0 and period % 8 == 0:
                decisions.append(SimDecision(
                    period=period, site_id=site.id, site_name=site.name,
                    product_id=pid, decision_type="maintenance", quantity=0,
                    context={"maintenance_type": "preventive", "decision_type": "schedule",
                             "asset_id": f"EQUIP-{site.name}-01", "estimated_downtime_hours": 4.0},
                ))

            # MO execution + subcontracting for manufacturer sites
            master_type = str(getattr(site, 'master_type', '')).lower()
            if master_type == 'manufacturer' and order_qty > 0:
                decisions.append(SimDecision(
                    period=period, site_id=site.id, site_name=site.name,
                    product_id=pid, decision_type="mo_execution", quantity=order_qty,
                    context={"decision_type": "release", "production_order_id": f"MO-{period:04d}-{pid[:6]}",
                             "expedite": sp.backlog > sp.safety_stock},
                ))
                # Subcontracting if over capacity
                typical = sp.target_inventory * 0.5 if sp.target_inventory > 0 else 100
                if order_qty > typical * 0.8:
                    ext = order_qty - typical * 0.8
                    decisions.append(SimDecision(
                        period=period, site_id=site.id, site_name=site.name,
                        product_id=pid, decision_type="subcontracting", quantity=ext,
                        context={"decision_type": "split", "internal_quantity": typical * 0.8,
                                 "external_quantity": ext, "reason": "capacity_constraint"},
                    ))

        return period_demand, period_fulfilled

    # ========================================================================
    # Shipment Management (Stochastic Lead Times)
    # ========================================================================

    def _ship_downstream_stochastic(
        self,
        source_site,
        product_id: str,
        quantity: float,
        period: int,
        state: Dict[str, Dict[str, SiteProductState]],
        pipeline: List[_StochasticShipment],
        all_shipments: list,
        decisions: list,
        rng: np.random.Generator,
    ):
        """Ship to downstream with stochastic lead times."""
        topo = self.topology
        downstream = topo.downstream_map.get(source_site.name, [])
        if not downstream:
            return

        # Proportional allocation
        total_ds_demand = 0.0
        ds_demands = {}
        for ds_name, lane in downstream:
            ds_sp = state.get(ds_name, {}).get(product_id)
            if ds_sp:
                demand = ds_sp.demand_history[-1] if ds_sp.demand_history else 0
                ds_demands[ds_name] = demand + ds_sp.backlog
                total_ds_demand += ds_demands[ds_name]

        for ds_name, lane in downstream:
            if total_ds_demand > 0:
                share = ds_demands.get(ds_name, 0) / total_ds_demand
                qty = quantity * share
            else:
                qty = quantity / len(downstream)

            if qty <= 0:
                continue

            base_lt = self._lane_lead_time(lane)
            stochastic_lt = self._sample_lead_time(base_lt, rng)

            shipment = _StochasticShipment(
                product_id=product_id,
                quantity=qty,
                ship_period=period,
                arrival_period=period + stochastic_lt,
                lane_id=lane.id,
                order_type="transfer",
                source_site=source_site.name,
                target_site=ds_name,
                base_lead_time=base_lt,
                actual_lead_time=stochastic_lt,
            )
            pipeline.append(shipment)
            all_shipments.append(shipment.to_pipeline_shipment())

            ds_sp = state.get(ds_name, {}).get(product_id)
            if ds_sp:
                ds_sp.in_transit += qty

            # Record TO decision
            decisions.append(SimDecision(
                period=period,
                site_id=source_site.id,
                site_name=source_site.name,
                product_id=product_id,
                decision_type="transfer_order",
                quantity=qty,
                context={
                    "dest_site": ds_name,
                    "base_lead_time": base_lt,
                    "actual_lead_time": stochastic_lt,
                    "trigger_reason": "demand_fulfillment",
                },
            ))

    def _place_order_upstream_stochastic(
        self,
        site,
        product_id: str,
        quantity: float,
        period: int,
        state: Dict[str, Dict[str, SiteProductState]],
        pipeline: List[_StochasticShipment],
        all_shipments: list,
        rng: np.random.Generator,
    ):
        """Place order upstream with stochastic lead time."""
        topo = self.topology
        upstream = topo.upstream_map.get(site.name, [])
        if not upstream:
            return

        # Find eligible supplier
        eligible = []
        for us_name, lane in upstream:
            us_site = self._get_site(us_name)
            if us_site and _is_supply(us_site):
                vendor_products = topo.vendor_lead_times.get(us_name, {})
                if product_id in vendor_products or not vendor_products:
                    eligible.append((us_name, lane))

        if not eligible:
            eligible = upstream[:1]

        us_name, lane = eligible[0]
        base_lt_days = topo.vendor_lead_times.get(us_name, {}).get(
            product_id, self._lane_lead_time(lane)
        )
        stochastic_lt = self._sample_lead_time(base_lt_days, rng)

        shipment = _StochasticShipment(
            product_id=product_id,
            quantity=quantity,
            ship_period=period,
            arrival_period=period + stochastic_lt,
            lane_id=lane.id,
            order_type="purchase",
            source_site=us_name,
            target_site=site.name,
            base_lead_time=base_lt_days,
            actual_lead_time=stochastic_lt,
        )
        pipeline.append(shipment)
        all_shipments.append(shipment.to_pipeline_shipment())

        sp = state.get(site.name, {}).get(product_id)
        if sp:
            sp.in_transit += quantity

    # ========================================================================
    # Disruption Modeling
    # ========================================================================

    def _apply_disruptions(
        self,
        rng: np.random.Generator,
        capacity_mult: Dict[str, float],
        period: int,
    ):
        """Apply random capacity disruptions to sites."""
        for site in self.topology.inventory_sites:
            if rng.random() < self.stoch.disruption_probability:
                severity = rng.uniform(*self.stoch.disruption_severity_range)
                capacity_mult[site.name] = 1.0 - severity
                logger.debug(
                    f"Period {period}: Disruption at {site.name}, "
                    f"capacity reduced to {capacity_mult[site.name]:.0%}"
                )
            else:
                # Recover from disruption (gradual)
                current = capacity_mult.get(site.name, 1.0)
                if current < 1.0:
                    capacity_mult[site.name] = min(1.0, current + 0.2)

    # ========================================================================
    # Order Tracking (Stochastic)
    # ========================================================================

    def _track_orders_stochastic(
        self,
        pipeline: List[_StochasticShipment],
        period: int,
        decisions: List[SimDecision],
    ):
        """Track in-flight shipments for exceptions."""
        from app.services.powell.engines.order_tracking_engine import (
            OrderTrackingEngine,
            OrderTrackingConfig,
            OrderSnapshot,
        )

        engine = OrderTrackingEngine(config=OrderTrackingConfig())

        for shipment in pipeline:
            days_in_transit = (period - shipment.ship_period) * 7
            expected_transit = shipment.base_lead_time
            days_until_expected = expected_transit - days_in_transit

            snapshot = OrderSnapshot(
                order_id=f"PO-{shipment.ship_period}-{shipment.product_id[:8]}",
                order_type="purchase_order" if shipment.order_type == "purchase" else "transfer_order",
                status="in_transit",
                days_until_expected=days_until_expected,
                days_since_created=days_in_transit,
                typical_transit_days=expected_transit,
                ordered_qty=shipment.quantity,
                received_qty=0,
            )

            result = engine.evaluate_order(snapshot)
            if result.exception_type != "no_exception":
                decisions.append(SimDecision(
                    period=period,
                    site_id=0,
                    site_name="tracking",
                    product_id=shipment.product_id,
                    decision_type="exception",
                    quantity=shipment.quantity,
                    context={
                        "exception_type": result.exception_type,
                        "severity": result.severity,
                        "recommended_action": result.recommended_action,
                        "days_in_transit": days_in_transit,
                        "base_lead_time": shipment.base_lead_time,
                        "actual_lead_time": shipment.actual_lead_time,
                        "is_stochastic_delay": shipment.actual_lead_time > shipment.base_lead_time // 7,
                    },
                ))

    # ========================================================================
    # Ordering Heuristics (same as deterministic)
    # ========================================================================

    def _compute_order(
        self,
        sp: SiteProductState,
        inv_position: float,
        product_id: str,
        period: int,
    ) -> float:
        """Compute order quantity using configured heuristic."""
        if self.strategy == OrderingStrategy.BASE_STOCK:
            order = sp.target_inventory - inv_position
            return max(0, order)

        elif self.strategy == OrderingStrategy.CONSERVATIVE:
            if len(sp.demand_history) < 2:
                return max(0, sp.target_inventory - inv_position)
            lookback = min(4, len(sp.demand_history))
            avg_demand = sum(sp.demand_history[-lookback:]) / lookback
            gap = sp.target_inventory - inv_position
            return max(0, avg_demand + 0.3 * gap)

        elif self.strategy == OrderingStrategy.PID:
            error = sp.target_inventory - inv_position
            sp.pid_integral += error
            sp.pid_integral = max(
                -sp.target_inventory * 5,
                min(sp.target_inventory * 5, sp.pid_integral)
            )
            derivative = error - sp.pid_prev_error
            sp.pid_prev_error = error

            if sp.demand_history:
                lookback = min(4, len(sp.demand_history))
                anchor = sum(sp.demand_history[-lookback:]) / lookback
            else:
                anchor = sp.target_inventory / 4

            control = (
                self.pid_kp * error
                + self.pid_ki * sp.pid_integral
                + self.pid_kd * derivative
            )
            return max(0, anchor + control)

        elif self.strategy == OrderingStrategy.EOQ:
            reorder_point = sp.safety_stock + sp.target_inventory * 0.3
            if inv_position > reorder_point:
                return 0.0
            if len(sp.demand_history) >= 4:
                avg_weekly = sum(sp.demand_history[-4:]) / 4
            else:
                avg_weekly = sp.target_inventory / 4
            annual_demand = avg_weekly * 52
            holding = self.holding_cost_rate * 52
            if holding > 0 and annual_demand > 0:
                eoq = math.sqrt(2 * annual_demand * 100.0 / holding)
                return max(eoq, sp.target_inventory - inv_position)
            return max(0, sp.target_inventory - inv_position)

        return max(0, sp.target_inventory - inv_position)

    # ========================================================================
    # Safety Stock Update
    # ========================================================================

    def _update_safety_stock(self, sp: SiteProductState):
        """Update safety stock from demand history (simplified)."""
        if len(sp.demand_history) < 4:
            return
        recent = sp.demand_history[-min(12, len(sp.demand_history)):]
        avg_weekly = np.mean(recent)
        std_weekly = np.std(recent) if len(recent) > 1 else avg_weekly * 0.2

        # z = 1.88 for 97% service level
        z = 1.88
        daily_demand = avg_weekly / 7.0
        daily_std = std_weekly / math.sqrt(7.0)
        lead_time = 14  # Default

        ss = z * math.sqrt(lead_time * daily_std ** 2 + daily_demand ** 2 * (lead_time * 0.15) ** 2)
        sp.safety_stock = ss
        sp.target_inventory = ss + avg_weekly * 2

    # ========================================================================
    # State Recording & KPI Computation
    # ========================================================================

    def _record_period_state(
        self,
        period: int,
        state: Dict[str, Dict[str, SiteProductState]],
        period_states: List[SimPeriodState],
        topo: LoadedTopology,
    ):
        """Record state snapshot for all sites and products."""
        for site in topo.sites:
            for product in topo.products:
                pid = self._product_id(product)
                sp = state.get(site.name, {}).get(pid)
                if not sp:
                    continue

                incoming = sp.demand_history[-1] if sp.demand_history else 0
                order = sp.order_history[-1] if sp.order_history else 0

                period_states.append(SimPeriodState(
                    period=period,
                    site_id=site.id,
                    site_name=site.name,
                    product_id=pid,
                    on_hand=sp.on_hand,
                    backlog=sp.backlog,
                    in_transit=sp.in_transit,
                    incoming_demand=incoming,
                    fulfilled_qty=min(sp.on_hand + incoming, incoming),
                    order_placed=order,
                    holding_cost=max(0, sp.on_hand) * self.holding_cost_rate,
                    backlog_cost=max(0, sp.backlog) * self.backlog_cost_rate,
                    safety_stock=sp.safety_stock,
                ))

    def _compute_kpis(
        self,
        total_demand: float,
        total_fulfilled: float,
        period_states: List[SimPeriodState],
        state: Dict[str, Dict[str, SiteProductState]],
        num_periods: int,
        topo: LoadedTopology,
    ) -> SimKPIs:
        """Compute aggregate KPIs."""
        fill_rate = total_fulfilled / total_demand if total_demand > 0 else 1.0

        total_holding = sum(ps.holding_cost for ps in period_states)
        total_backlog = sum(ps.backlog_cost for ps in period_states)

        inv_sites = [s.name for s in topo.inventory_sites]
        total_throughput = 0.0
        total_avg_inv = 0.0

        for site_name in inv_sites:
            for product in topo.products:
                pid = self._product_id(product)
                sp = state.get(site_name, {}).get(pid)
                if not sp:
                    continue
                throughput = sum(sp.demand_history) if sp.demand_history else 0
                inv_vals = [
                    ps.on_hand for ps in period_states
                    if ps.site_name == site_name and ps.product_id == pid
                ]
                avg_inv = np.mean(inv_vals) if inv_vals else 0
                total_throughput += throughput
                total_avg_inv += avg_inv

        turns = (
            (total_throughput / total_avg_inv) * (52 / num_periods)
            if total_avg_inv > 0 else 0.0
        )

        # Bullwhip
        all_demands, all_orders = [], []
        for site_name in inv_sites:
            for product in topo.products:
                pid = self._product_id(product)
                sp = state.get(site_name, {}).get(pid)
                if sp:
                    all_demands.extend(sp.demand_history)
                    all_orders.extend(sp.order_history)

        demand_var = np.var(all_demands) if all_demands else 1
        order_var = np.var(all_orders) if all_orders else 0
        bullwhip = order_var / demand_var if demand_var > 0 else 1.0

        # Days of supply
        dos_values = []
        for site_name in inv_sites:
            for product in topo.products:
                pid = self._product_id(product)
                sp = state.get(site_name, {}).get(pid)
                if sp and sp.demand_history:
                    avg_d = np.mean(sp.demand_history) / 7.0
                    if avg_d > 0:
                        dos_values.append(sp.on_hand / avg_d)

        return SimKPIs(
            fill_rate=fill_rate,
            otif_rate=fill_rate * 0.95,
            avg_inventory_turns=turns,
            total_holding_cost=total_holding,
            total_backlog_cost=total_backlog,
            total_cost=total_holding + total_backlog,
            avg_days_of_supply=float(np.mean(dos_values)) if dos_values else 0,
            bullwhip_ratio=bullwhip,
        )

    def _build_history(
        self,
        topo: LoadedTopology,
        state: Dict[str, Dict[str, SiteProductState]],
        period_states: List[SimPeriodState],
    ) -> Dict[str, Dict[str, List[Dict[str, float]]]]:
        """Build per-site per-product time series."""
        history: Dict[str, Dict[str, List[Dict[str, float]]]] = {}

        for site in topo.sites:
            history[site.name] = {}
            for product in topo.products:
                pid = self._product_id(product)
                series = []
                for ps in period_states:
                    if ps.site_name == site.name and ps.product_id == pid:
                        series.append({
                            "period": ps.period,
                            "on_hand": ps.on_hand,
                            "backlog": ps.backlog,
                            "in_transit": ps.in_transit,
                            "demand": ps.incoming_demand,
                            "fulfilled": ps.fulfilled_qty,
                            "order_placed": ps.order_placed,
                            "holding_cost": ps.holding_cost,
                            "backlog_cost": ps.backlog_cost,
                            "safety_stock": ps.safety_stock,
                        })
                history[site.name][pid] = series

        return history

    # ========================================================================
    # Monte Carlo Aggregation
    # ========================================================================

    def _aggregate_kpis(
        self, runs: List[SimulationResult]
    ) -> Tuple[SimKPIs, SimKPIs, SimKPIs, SimKPIs]:
        """Compute mean, std, P10, P90 of KPIs across runs."""
        fields = [
            "fill_rate", "otif_rate", "avg_inventory_turns",
            "total_holding_cost", "total_backlog_cost", "total_cost",
            "avg_days_of_supply", "bullwhip_ratio",
        ]

        arrays = {f: [] for f in fields}
        for run in runs:
            for f in fields:
                arrays[f].append(getattr(run.kpis, f, 0.0))

        def make_kpi(func) -> SimKPIs:
            return SimKPIs(**{f: float(func(arrays[f])) for f in fields})

        return (
            make_kpi(np.mean),
            make_kpi(np.std),
            make_kpi(lambda a: np.percentile(a, 10)),
            make_kpi(lambda a: np.percentile(a, 90)),
        )

    def _aggregate_history(
        self,
        runs: List[SimulationResult],
        num_periods: int,
    ) -> Dict[str, Dict[str, Dict[str, Tuple[List[float], List[float]]]]]:
        """Aggregate time series across runs: compute mean and std per period."""
        if not runs:
            return {}

        # Build structure from first run
        first = runs[0]
        metrics = ["on_hand", "backlog", "in_transit", "demand", "fulfilled",
                    "order_placed", "holding_cost", "backlog_cost", "safety_stock"]

        result: Dict[str, Dict[str, Dict[str, Tuple[List[float], List[float]]]]] = {}

        for site_name, products in first.site_product_history.items():
            result[site_name] = {}
            for pid, series in products.items():
                result[site_name][pid] = {}

                for metric in metrics:
                    # Collect this metric across all runs
                    run_series = []
                    for run in runs:
                        run_data = run.site_product_history.get(
                            site_name, {}
                        ).get(pid, [])
                        values = [
                            entry.get(metric, 0.0) for entry in run_data
                        ]
                        # Pad to num_periods if short
                        while len(values) < num_periods:
                            values.append(values[-1] if values else 0.0)
                        run_series.append(values[:num_periods])

                    if run_series:
                        arr = np.array(run_series)
                        means = np.mean(arr, axis=0).tolist()
                        stds = np.std(arr, axis=0).tolist()
                    else:
                        means = [0.0] * num_periods
                        stds = [0.0] * num_periods

                    result[site_name][pid][metric] = (means, stds)

        return result

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _get_site(self, name: str):
        """Get site by name."""
        for s in self.topology.sites:
            if s.name == name:
                return s
        return None

    def _get_forecast(self, site_name: str, product_id: str, period: int) -> float:
        """Get forecast value for site-product-period."""
        site_fc = self.topology.forecasts.get(site_name, {})
        prod_fc = site_fc.get(product_id, [])
        if prod_fc and period < len(prod_fc):
            return prod_fc[period]
        elif prod_fc:
            return prod_fc[-1]
        return 0.0

    def _product_id(self, product) -> str:
        """Extract product ID string."""
        if hasattr(product, 'product_id'):
            return str(product.product_id)
        if hasattr(product, 'id'):
            return str(product.id)
        return str(product)

    def _lane_lead_time(self, lane) -> int:
        """Extract lead time in days from lane."""
        if hasattr(lane, 'lead_time') and lane.lead_time:
            lt = lane.lead_time
            if isinstance(lt, dict):
                return int(lt.get('min', 7) + lt.get('max', 7)) // 2
            return int(lt)
        return 7


# ============================================================================
# Internal Data Structures
# ============================================================================


@dataclass
class _StochasticShipment:
    """Shipment with stochastic timing metadata."""
    product_id: str
    quantity: float
    ship_period: int
    arrival_period: int
    lane_id: int
    order_type: str  # "purchase", "transfer"
    source_site: str
    target_site: str
    base_lead_time: int      # Original deterministic lead time (days)
    actual_lead_time: int    # Sampled stochastic lead time (periods)

    def to_pipeline_shipment(self) -> PipelineShipment:
        """Convert to the shared PipelineShipment format."""
        return PipelineShipment(
            product_id=self.product_id,
            quantity=self.quantity,
            ship_period=self.ship_period,
            arrival_period=self.arrival_period,
            lane_id=self.lane_id,
            order_type=self.order_type,
        )
