#!/usr/bin/env python3
"""
Generate TRM Training Corpus — per-TRM parquet files of (state, action, reward)

Sweeps each TRM's state dataclass across realistic distributions, labels
each sample with the deterministic heuristic teacher, and writes parquet
files suitable for TRM behavioral-cloning training.

Architecture (matches TMS_TRM_TRAINING_DATA_SPECIFICATION.md):
  State Sampler → compute_tms_decision() → (state_dict, action, reward) → parquet

Unlike SCP (8 teachers per state for consensus), TMS uses a single
deterministic teacher per state — appropriate because transportation
heuristics are discrete (waterfall, threshold-based) with less legitimate
disagreement across methods.

Usage:
    python scripts/pretraining/generate_tms_corpus.py --trm capacity_promise --samples 50000
    python scripts/pretraining/generate_tms_corpus.py --all --samples 50000
    python scripts/pretraining/generate_tms_corpus.py --all --samples 50000 --output-dir /data/tms_corpus

Output: one parquet file per TRM in output_dir, e.g.:
    capacity_promise_50000.parquet
    freight_procurement_50000.parquet
    ...
"""
from __future__ import annotations

import argparse
import logging
import random
import sys
import time
from dataclasses import asdict, fields
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    HAS_PARQUET = True
except ImportError:
    HAS_PARQUET = False

# Import heuristic library by loading the .py files directly — avoids
# triggering `import torch` from the parent powell/__init__.py package
# (site_agent_model.py needs torch at module level, but corpus generation
# is heuristic-only / no neural network inference).
import importlib.util as _ilu
import os as _os

def _load_module_direct(name: str, path: str):
    spec = _ilu.spec_from_file_location(name, path)
    mod = _ilu.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

_CORE_TMS_HL = _os.path.join(
    _os.path.dirname(__file__), "..", "..", "..",
    "Autonomy-Core", "packages", "data-model", "src",
    "azirella_data_model", "powell", "tms", "heuristic_library",
)
# Fallback: installed package location
if not _os.path.isdir(_CORE_TMS_HL):
    import azirella_data_model as _adm
    _CORE_TMS_HL = _os.path.join(
        _os.path.dirname(_adm.__file__), "powell", "tms", "heuristic_library",
    )

_base_mod = _load_module_direct("tms_hl_base", _os.path.join(_CORE_TMS_HL, "base.py"))
# Inject base into sys.modules so dispatch.py can import from it
import sys as _sys
_sys.modules["azirella_data_model.powell.tms.heuristic_library.base"] = _base_mod

_dispatch_mod = _load_module_direct("tms_hl_dispatch", _os.path.join(_CORE_TMS_HL, "dispatch.py"))
compute_tms_decision = _dispatch_mod.compute_tms_decision
Actions = _dispatch_mod.Actions

from azirella_data_model.powell.tms.heuristic_library.base import (  # noqa: E402
    CapacityPromiseState,
    ShipmentTrackingState,
    DemandSensingState,
    CapacityBufferState,
    ExceptionManagementState,
    FreightProcurementState,
    BrokerRoutingState,
    DockSchedulingState,
    LoadBuildState,
    IntermodalTransferState,
    EquipmentRepositionState,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("generate_tms_corpus")


# ============================================================================
# State samplers — one per TRM
# ============================================================================
# Each returns a populated state dataclass with realistic field distributions.
# Distributions are calibrated against DAT/FreightWaves benchmarks and the
# Food Dist network topology.

def _sample_capacity_promise(rng: random.Random) -> CapacityPromiseState:
    total_cap = rng.randint(5, 50)
    booked = rng.randint(0, total_cap)
    return CapacityPromiseState(
        shipment_id=rng.randint(1, 100000),
        lane_id=rng.randint(1, 50),
        requested_loads=rng.randint(1, 5),
        mode=rng.choice(["FTL", "LTL", "INTERMODAL"]),
        priority=rng.choices([1, 2, 3, 4, 5], weights=[5, 10, 50, 25, 10])[0],
        committed_capacity=booked,
        total_capacity=total_cap,
        buffer_capacity=rng.randint(0, max(1, total_cap // 5)),
        forecast_loads=rng.randint(3, 30),
        booked_loads=booked,
        primary_carrier_available=rng.random() > 0.15,
        backup_carriers_count=rng.randint(0, 5),
        spot_rate_premium_pct=rng.uniform(0.0, 0.40),
        lane_acceptance_rate=rng.uniform(0.50, 0.98),
        market_tightness=rng.uniform(0.0, 1.0),
        primary_carrier_otp=rng.uniform(0.75, 0.99),
        allocation_compliance_pct=rng.uniform(0.50, 1.20),
    )


def _sample_shipment_tracking(rng: random.Random) -> ShipmentTrackingState:
    now = datetime.utcnow()
    planned_delivery = now + timedelta(hours=rng.uniform(4, 96))
    pct = rng.uniform(0.0, 1.0)
    eta_offset = rng.gauss(0, 4)
    return ShipmentTrackingState(
        shipment_id=rng.randint(1, 100000),
        shipment_status=rng.choices(["IN_TRANSIT", "DELIVERED", "HELD"], weights=[80, 15, 5])[0],
        planned_delivery=planned_delivery,
        current_eta=planned_delivery + timedelta(hours=eta_offset),
        eta_p10=planned_delivery + timedelta(hours=eta_offset - 3),
        eta_p90=planned_delivery + timedelta(hours=eta_offset + 3),
        last_update_hours_ago=rng.expovariate(0.5),
        total_miles=rng.uniform(100, 2500),
        pct_complete=pct,
        miles_remaining=rng.uniform(0, 2000) * (1 - pct),
        carrier_otp_pct=rng.uniform(0.70, 0.99),
        carrier_reliability_score=rng.uniform(0.50, 0.99),
        is_temperature_sensitive=rng.random() < 0.35,
        current_temp=rng.uniform(-15, 80) if rng.random() < 0.3 else None,
        temp_min=-10.0 if rng.random() < 0.35 else None,
        temp_max=40.0 if rng.random() < 0.35 else None,
        transport_mode=rng.choice(["FTL", "LTL", "FCL", "AIR_STD", "RAIL_INTERMODAL"]),
    )


def _sample_demand_sensing(rng: random.Random) -> DemandSensingState:
    forecast = rng.uniform(5, 100)
    actual = forecast * rng.uniform(0.5, 1.5)
    return DemandSensingState(
        lane_id=rng.randint(1, 50),
        forecast_loads=forecast,
        forecast_mape=rng.uniform(0.05, 0.40),
        actual_loads_current=actual,
        actual_loads_prior=forecast * rng.uniform(0.7, 1.3),
        week_over_week_change_pct=rng.uniform(-0.40, 0.50),
        rolling_4wk_avg=forecast * rng.uniform(0.8, 1.2),
        signal_type=rng.choice(["", "VOLUME_SURGE", "SEASONAL_SHIFT", "PROMO_LIFT"]),
        signal_magnitude=rng.uniform(0, 0.3) if rng.random() < 0.3 else 0.0,
        signal_confidence=rng.uniform(0.3, 0.95) if rng.random() < 0.3 else 0.0,
        is_peak_season=rng.random() < 0.25,
        order_pipeline_loads_24h=rng.uniform(0, 20),
        order_pipeline_loads_prior_24h=rng.uniform(0, 20),
        cumulative_forecast_error=rng.gauss(0, forecast * 0.3),
        cumulative_mad=max(0.1, abs(rng.gauss(0, forecast * 0.15))),
    )


def _sample_capacity_buffer(rng: random.Random) -> CapacityBufferState:
    forecast = rng.randint(5, 50)
    return CapacityBufferState(
        lane_id=rng.randint(1, 50),
        baseline_buffer_loads=rng.randint(1, 15),
        forecast_loads=forecast,
        forecast_p10=max(0, forecast - rng.randint(2, 10)),
        forecast_p90=forecast + rng.randint(2, 15),
        committed_loads=rng.randint(0, forecast),
        contract_capacity=forecast + rng.randint(0, 20),
        recent_tender_reject_rate=rng.uniform(0.0, 0.40),
        demand_cv=rng.uniform(0.05, 0.80),
        demand_trend=rng.uniform(-0.3, 0.5),
        is_peak_season=rng.random() < 0.25,
        recent_capacity_miss_count=rng.choices([0, 1, 2, 3, 4, 5], weights=[40, 25, 15, 10, 5, 5])[0],
    )


def _sample_exception_management(rng: random.Random) -> ExceptionManagementState:
    exc_types = ["LATE_DELIVERY", "LATE_PICKUP", "DETENTION", "CARRIER_BREAKDOWN",
                 "WEATHER_DELAY", "REFUSED", "TEMPERATURE_EXCURSION", "DAMAGE"]
    severities = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    return ExceptionManagementState(
        exception_type=rng.choice(exc_types),
        severity=rng.choices(severities, weights=[20, 40, 25, 15])[0],
        estimated_delay_hrs=rng.expovariate(0.2),
        estimated_cost_impact=rng.uniform(50, 5000),
        revenue_at_risk=rng.uniform(200, 20000),
        shipment_priority=rng.choices([1, 2, 3, 4, 5], weights=[5, 10, 50, 25, 10])[0],
        delivery_window_remaining_hrs=rng.uniform(0, 48),
        carrier_reliability_score=rng.uniform(0.50, 0.99),
        can_retender=rng.random() > 0.20,
        alternate_carriers_available=rng.randint(0, 5),
        can_reroute=rng.random() > 0.60,
        shipment_value=rng.uniform(500, 50000),
        penalty_exposure=rng.uniform(0, 5000),
        expedite_cost_estimate=rng.uniform(200, 3000),
        appointment_buffer_hrs=rng.choice([1.0, 2.0, 4.0]),
        downstream_shipments_affected=rng.choices([0, 1, 2, 3, 5], weights=[50, 25, 15, 7, 3])[0],
        customer_tier=rng.choices([1, 2, 3, 4, 5], weights=[10, 15, 40, 25, 10])[0],
    )


def _sample_freight_procurement(rng: random.Random) -> FreightProcurementState:
    contract_rate = rng.uniform(1500, 4000)
    return FreightProcurementState(
        load_id=rng.randint(1, 100000),
        lane_id=rng.randint(1, 50),
        mode=rng.choice(["FTL", "LTL"]),
        weight=rng.uniform(5000, 44000),
        lead_time_hours=rng.uniform(1, 96),
        primary_carrier_id=rng.randint(1, 50) if rng.random() > 0.1 else None,
        primary_carrier_rate=contract_rate,
        primary_carrier_acceptance_pct=rng.uniform(0.30, 0.98),
        backup_carriers=[
            {"id": rng.randint(51, 100), "rate": contract_rate * rng.uniform(1.0, 1.15),
             "acceptance_pct": rng.uniform(0.40, 0.95), "priority": i + 2,
             "otp_pct": rng.uniform(0.80, 0.98)}
            for i in range(rng.randint(0, 4))
        ],
        spot_rate=contract_rate * rng.uniform(0.90, 1.40),
        contract_rate=contract_rate,
        market_tightness=rng.uniform(0.0, 1.0),
        dat_benchmark_rate=contract_rate * rng.uniform(0.95, 1.10),
        tender_attempt=rng.randint(1, 5),
        max_tender_attempts=rng.choice([3, 4, 5]),
        hours_to_tender_deadline=rng.uniform(2, 48),
    )


def _sample_broker_routing(rng: random.Random) -> BrokerRoutingState:
    contract_rate = rng.uniform(1500, 4000)
    return BrokerRoutingState(
        load_id=rng.randint(1, 100000),
        hours_to_pickup=rng.uniform(1, 48),
        available_brokers=[
            {"id": rng.randint(1, 20), "name": f"Broker_{i}",
             "rate": contract_rate * rng.uniform(1.05, 1.45),
             "reliability": rng.uniform(0.60, 0.98),
             "fallthrough_rate": rng.uniform(0.02, 0.20),
             "coverage_score": rng.uniform(0.50, 0.95)}
            for i in range(rng.randint(0, 5))
        ],
        contract_rate=contract_rate,
        spot_rate=contract_rate * rng.uniform(0.90, 1.35),
        shipment_priority=rng.choices([1, 2, 3, 4, 5], weights=[5, 10, 50, 25, 10])[0],
        market_tightness=rng.uniform(0.0, 1.0),
        dat_benchmark_rate=contract_rate * rng.uniform(0.95, 1.10),
    )


def _sample_dock_scheduling(rng: random.Random) -> DockSchedulingState:
    total_doors = rng.randint(4, 20)
    return DockSchedulingState(
        facility_id=rng.randint(1, 10),
        appointment_type=rng.choice(["PICKUP", "DELIVERY", "CROSS_DOCK"]),
        total_dock_doors=total_doors,
        available_dock_doors=rng.randint(0, total_doors),
        yard_spots_total=rng.randint(20, 100),
        yard_spots_available=rng.randint(0, 50),
        appointments_in_window=rng.randint(0, 10),
        current_queue_depth=rng.choices([0, 1, 2, 3, 4, 5, 6], weights=[20, 25, 20, 15, 10, 5, 5])[0],
        shipment_priority=rng.choices([1, 2, 3, 4, 5], weights=[5, 10, 50, 25, 10])[0],
        is_live_load=rng.random() > 0.30,
        estimated_load_time_minutes=rng.uniform(30, 120),
        free_time_minutes=rng.choice([60, 90, 120, 180]),
        detention_rate_per_hour=rng.choice([50, 75, 100]),
        carrier_avg_dwell_minutes=rng.uniform(30, 240),
        equipment_type=rng.choice(["DRY_VAN", "REEFER", "FLATBED"]),
    )


def _sample_load_build(rng: random.Random) -> LoadBuildState:
    n_ships = rng.randint(1, 8)
    weight_per = rng.uniform(2000, 12000)
    ftl_rate = rng.uniform(1500, 4000)
    return LoadBuildState(
        shipment_ids=list(range(n_ships)),
        lane_id=rng.randint(1, 50),
        mode=rng.choice(["FTL", "LTL"]),
        equipment_type=rng.choice(["DRY_VAN", "REEFER"]),
        total_weight=weight_per * n_ships,
        total_volume=rng.uniform(100, 2700),
        total_pallets=rng.randint(1, 26),
        shipment_count=n_ships,
        has_hazmat_conflict=rng.random() < 0.03,
        has_temp_conflict=rng.random() < 0.05,
        has_destination_conflict=rng.random() < 0.10,
        max_stops=rng.choice([3, 4, 5]),
        consolidation_window_hours=rng.choice([12, 24, 48]),
        ftl_rate=ftl_rate,
        ltl_rate_sum=ftl_rate * rng.uniform(0.8, 2.0) if n_ships > 1 else ftl_rate * 0.6,
        consolidation_savings=rng.uniform(-200, 1500) if n_ships > 1 else 0,
        stop_count=min(n_ships, rng.randint(1, 5)),
        stop_off_charge_per_stop=rng.choice([50, 75, 100, 150]),
        delivery_windows_compatible=rng.random() > 0.10,
        volume_ltl_rate=ftl_rate * rng.uniform(0.6, 0.95) if rng.random() < 0.3 else 0,
    )


def _sample_intermodal_transfer(rng: random.Random) -> IntermodalTransferState:
    truck_miles = rng.uniform(200, 2500)
    truck_rate = truck_miles * rng.uniform(2.0, 3.5)
    im_rate = truck_rate * rng.uniform(0.60, 1.05)
    return IntermodalTransferState(
        shipment_id=rng.randint(1, 100000),
        total_truck_miles=truck_miles,
        truck_rate=truck_rate,
        intermodal_rate=im_rate,
        drayage_rate_origin=rng.uniform(200, 600),
        drayage_rate_dest=rng.uniform(200, 600),
        truck_transit_days=truck_miles / rng.uniform(400, 600),
        intermodal_transit_days=truck_miles / rng.uniform(250, 400),
        delivery_window_days=rng.uniform(0, 5),
        ramp_congestion_level=rng.uniform(0.0, 1.0),
        intermodal_reliability_pct=rng.uniform(0.75, 0.96),
        is_hazmat=rng.random() < 0.05,
        is_temperature_controlled=rng.random() < 0.30,
        commodity_value_per_lb=rng.uniform(0.0, 5.0),
        origin_ramp_distance_miles=rng.uniform(5, 150),
        dest_ramp_distance_miles=rng.uniform(5, 150),
    )


def _sample_equipment_reposition(rng: random.Random) -> EquipmentRepositionState:
    src_eq = rng.randint(5, 40)
    tgt_eq = rng.randint(0, 30)
    src_demand = rng.randint(2, 25)
    tgt_demand = rng.randint(2, 25)
    miles = rng.uniform(50, 800)
    cost = miles * rng.uniform(1.5, 2.5)
    return EquipmentRepositionState(
        equipment_type=rng.choice(["DRY_VAN", "REEFER"]),
        source_equipment_count=src_eq,
        source_demand_next_7d=src_demand,
        target_equipment_count=tgt_eq,
        target_demand_next_7d=tgt_demand,
        reposition_miles=miles,
        reposition_cost=cost,
        cost_of_not_repositioning=cost * rng.uniform(0.5, 3.5),
        total_fleet_size=rng.randint(100, 1000),
        fleet_utilization_pct=rng.uniform(0.50, 0.98),
        breakeven_loads=rng.randint(1, 5),
    )


SAMPLERS = {
    "capacity_promise": (_sample_capacity_promise, CapacityPromiseState),
    "shipment_tracking": (_sample_shipment_tracking, ShipmentTrackingState),
    "demand_sensing": (_sample_demand_sensing, DemandSensingState),
    "capacity_buffer": (_sample_capacity_buffer, CapacityBufferState),
    "exception_management": (_sample_exception_management, ExceptionManagementState),
    "freight_procurement": (_sample_freight_procurement, FreightProcurementState),
    "broker_routing": (_sample_broker_routing, BrokerRoutingState),
    "dock_scheduling": (_sample_dock_scheduling, DockSchedulingState),
    "load_build": (_sample_load_build, LoadBuildState),
    "intermodal_transfer": (_sample_intermodal_transfer, IntermodalTransferState),
    "equipment_reposition": (_sample_equipment_reposition, EquipmentRepositionState),
}

ALL_TRMS = list(SAMPLERS.keys())


# ============================================================================
# Reward function
# ============================================================================

def compute_reward(action: int, urgency: float, quantity: float) -> float:
    """
    Reward signal for behavioral cloning.
    Positive for correct decisive actions, scaled by urgency.
    HOLD/DEFER penalized slightly to encourage action-taking (AIIO: agent always acts).
    """
    if action in (Actions.ACCEPT, Actions.CONSOLIDATE, Actions.REPOSITION,
                  Actions.RETENDER, Actions.REROUTE):
        return 1.0 + urgency * 0.5
    if action == Actions.ESCALATE:
        return 0.8 + urgency * 0.3
    if action in (Actions.MODIFY,):
        return 0.7 + urgency * 0.2
    if action in (Actions.DEFER, Actions.HOLD):
        return 0.3
    if action == Actions.REJECT:
        return 0.5 + urgency * 0.2
    return 0.5


# ============================================================================
# Corpus generator
# ============================================================================

def _state_to_flat_dict(state) -> Dict[str, Any]:
    """Flatten a state dataclass to a dict suitable for parquet columns.
    Handles datetime → ISO string, lists → JSON string, nested dicts → JSON."""
    import json
    d = {}
    for f in fields(state):
        val = getattr(state, f.name)
        if isinstance(val, datetime):
            val = val.isoformat()
        elif isinstance(val, date):
            val = val.isoformat()
        elif isinstance(val, (list, dict)):
            val = json.dumps(val)
        d[f"state_{f.name}"] = val
    return d


def generate_corpus(
    trm_type: str,
    n_samples: int,
    seed: int = 42,
    output_dir: Optional[Path] = None,
) -> Path:
    """Generate n_samples of (state, action, reward) for one TRM."""
    sampler_fn, state_cls = SAMPLERS[trm_type]
    rng = random.Random(seed)

    rows: List[Dict[str, Any]] = []
    t0 = time.time()
    for i in range(n_samples):
        state = sampler_fn(rng)
        decision = compute_tms_decision(trm_type, state)

        row = _state_to_flat_dict(state)
        row["action"] = decision.action
        row["action_name"] = {
            0: "ACCEPT", 1: "REJECT", 2: "DEFER", 3: "ESCALATE",
            4: "MODIFY", 5: "RETENDER", 6: "REROUTE", 7: "CONSOLIDATE",
            8: "SPLIT", 9: "REPOSITION", 10: "HOLD",
        }.get(decision.action, f"UNKNOWN_{decision.action}")
        row["quantity"] = decision.quantity
        row["urgency"] = decision.urgency
        row["confidence"] = decision.confidence
        row["reasoning"] = decision.reasoning
        row["reward"] = compute_reward(decision.action, decision.urgency, decision.quantity)
        rows.append(row)

        if (i + 1) % 10000 == 0:
            logger.info(f"  {trm_type}: {i+1}/{n_samples} ({time.time()-t0:.1f}s)")

    elapsed = time.time() - t0
    logger.info(f"{trm_type}: {n_samples} samples generated in {elapsed:.1f}s")

    # Action distribution
    from collections import Counter
    action_dist = Counter(r["action_name"] for r in rows)
    logger.info(f"  Action distribution: {dict(action_dist)}")

    # Write output
    if output_dir is None:
        output_dir = Path(BACKEND_ROOT) / "training_data" / "tms_corpus"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{trm_type}_{n_samples}.parquet"

    if HAS_PARQUET:
        table = pa.Table.from_pylist(rows)
        pq.write_table(table, out_path)
        logger.info(f"  Written: {out_path} ({out_path.stat().st_size / 1024:.0f} KB)")
    else:
        # Fallback to JSON lines if pyarrow not available
        import json
        out_path = out_path.with_suffix(".jsonl")
        with open(out_path, "w") as f:
            for row in rows:
                f.write(json.dumps(row, default=str) + "\n")
        logger.info(f"  Written: {out_path} (jsonl fallback, {out_path.stat().st_size / 1024:.0f} KB)")

    return out_path


# ============================================================================
# Entry points
# ============================================================================

def main():
    ap = argparse.ArgumentParser(description="Generate TMS TRM training corpus")
    ap.add_argument("--trm", type=str, default=None, choices=ALL_TRMS,
                    help="Single TRM to generate (default: all)")
    ap.add_argument("--all", action="store_true", help="Generate all 11 TRMs")
    ap.add_argument("--samples", type=int, default=50000,
                    help="Samples per TRM (default: 50000)")
    ap.add_argument("--seed", type=int, default=42, help="Random seed")
    ap.add_argument("--output-dir", type=str, default=None,
                    help="Output directory (default: training_data/tms_corpus/)")
    args = ap.parse_args()

    if not args.trm and not args.all:
        ap.error("Specify --trm <name> or --all")

    trms = ALL_TRMS if args.all else [args.trm]
    output_dir = Path(args.output_dir) if args.output_dir else None

    logger.info(f"Generating corpus: {len(trms)} TRMs × {args.samples} samples, seed={args.seed}")
    paths = []
    for trm in trms:
        p = generate_corpus(trm, args.samples, seed=args.seed, output_dir=output_dir)
        paths.append(p)

    logger.info(f"Done. {len(paths)} files written.")
    for p in paths:
        logger.info(f"  {p}")


if __name__ == "__main__":
    main()
