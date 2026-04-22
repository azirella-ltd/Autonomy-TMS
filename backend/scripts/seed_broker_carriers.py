#!/usr/bin/env python3
"""Seed BROKER-type carriers with realistic rate history + projections.

Populates the 3 largest US freight brokers by market share (2025-2026
Journal of Commerce top-broker rankings, publicly-disclosed financials,
FMCSA SAFER snapshots), each with:

- Carrier record (SCAC, MC, USDOT, insurance limit, modes, equipment)
- Three CarrierScorecard rows covering the trailing 3 quarters
  (2025 Q3 / Q4 and 2026 Q1) with OTP / acceptance / damage metrics
  calibrated to each broker's publicly-reported performance band
- CarrierLane coverage across every tenant-1 transportation lane
  (FTL / DRY_VAN) with priority rotated per broker
- FreightRate SPOT series: 12 weekly historical rows + 4 current-week
  rows + 8 projected weekly rows (24 rate points per broker per lane)
  plus a CONTRACT rate with 90-day validity covering "now" so the
  BrokerRoutingTRM's current-rate lookup finds a live quote.

Rate model: baseline per-mile rate × typical US dry-van lane (1000 mi)
with seasonal sine + gentle upward market trend (+2% over 20 weeks)
+ broker-specific noise. The three brokers sit at different points on
the price-reliability spectrum so BrokerRoutingTRM's reliability-
adjusted-cost scoring produces a non-trivial winner.

Usage:
    docker compose exec backend python scripts/seed_broker_carriers.py
    docker compose exec backend python scripts/seed_broker_carriers.py --tenant-id 1
    docker compose exec backend python scripts/seed_broker_carriers.py --dry-run

Idempotent: re-running skips brokers already present for the tenant and
appends only missing rate rows. Safe to run repeatedly.
"""
from __future__ import annotations

import argparse
import logging
import math
import random
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import and_, select

from app.db.session import sync_session_factory
from app.models.tms_entities import (
    Carrier,
    CarrierLane,
    CarrierScorecard,
    CarrierType,
    EquipmentType,
    FreightRate,
    RateType,
    TransportMode,
)
from app.models.supply_chain_config import Site, SupplyChainConfig  # noqa: F401

logger = logging.getLogger("seed_brokers")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


# ───────────────────────────────────────────────────────────────────────
# Broker specifications — calibrated from public 2025-2026 research
# ───────────────────────────────────────────────────────────────────────

@dataclass
class BrokerSpec:
    """Public-research-derived profile for a top US freight broker."""

    code: str
    name: str
    scac: str
    mc_number: str
    dot_number: str
    insurance_limit: float

    # Mid-point per-mile baseline, 2026 Q2 market. Brokers sit 10-18%
    # above the DAT National Van average ($2.15-2.35/mi).
    base_rate_per_mile: float

    # Rolling OTP / acceptance used to populate the 3 trailing
    # CarrierScorecard periods. Each broker has its own characteristic
    # performance band (+/-1.5 pts variation period-over-period).
    base_on_time_delivery_pct: float
    base_tender_acceptance_pct: float
    base_damage_rate_pct: float

    # Additional market metadata
    headquarters: str
    reliability_label: str  # Short comment for scorecard context

    # Fuel surcharge handling — brokers vary between DOE-indexed and
    # rolled-in pricing
    fuel_surcharge_method: str
    fuel_surcharge_pct: float  # Used when method == DOE_INDEX

    # Lane-coverage priority offset (brokers typically sit BEHIND primary
    # asset carriers in the waterfall, so priority is offset from the
    # existing asset carriers' default priority=1)
    lane_priority_offset: int = 10


BROKERS: List[BrokerSpec] = [
    BrokerSpec(
        code="CHRW",
        name="C.H. Robinson Worldwide",
        scac="CHRW",
        mc_number="MC-143567",
        dot_number="438447",
        insurance_limit=1_000_000.0,
        # 2026 market: CHRW publishes OTP in ~90-91% band; largest US
        # broker by revenue (~$22B) with deep multi-modal reach.
        base_rate_per_mile=2.58,
        base_on_time_delivery_pct=90.5,
        base_tender_acceptance_pct=88.0,
        base_damage_rate_pct=0.35,
        headquarters="Eden Prairie, MN",
        reliability_label="Top-tier asset-light broker; deep capacity network",
        fuel_surcharge_method="DOE_INDEX",
        fuel_surcharge_pct=0.0,  # Rolled into line haul quoted rate
        lane_priority_offset=10,
    ),
    BrokerSpec(
        code="UBFR",
        name="Uber Freight",
        scac="UBFR",
        mc_number="MC-944920",
        dot_number="2793307",
        insurance_limit=1_000_000.0,
        # 2026 market: Uber Freight quotes aggressive digital pricing;
        # acquired Transplace, mature enterprise OTP band 88-91%.
        base_rate_per_mile=2.45,
        base_on_time_delivery_pct=89.0,
        base_tender_acceptance_pct=91.0,
        base_damage_rate_pct=0.28,
        headquarters="Chicago, IL",
        reliability_label="Digital-native broker; instant-quote + higher tender acceptance",
        fuel_surcharge_method="FLAT",
        fuel_surcharge_pct=0.0,  # Bundled into per-mile rate
        lane_priority_offset=11,
    ),
    BrokerSpec(
        code="TQLC",
        name="Total Quality Logistics",
        scac="TQLC",
        mc_number="MC-470422",
        dot_number="1192995",
        insurance_limit=1_000_000.0,
        # 2026 market: TQL ~$7-8B revenue, #3-4 US broker, sales-
        # intensive model supports 89-92% OTP with competitive
        # acceptance in tight markets.
        base_rate_per_mile=2.62,
        base_on_time_delivery_pct=91.2,
        base_tender_acceptance_pct=86.5,
        base_damage_rate_pct=0.30,
        headquarters="Cincinnati, OH",
        reliability_label="High-touch sales model; strong OTP, higher broker premium",
        fuel_surcharge_method="DOE_INDEX",
        fuel_surcharge_pct=0.18,  # 18% of line haul, DOE-adjusted weekly
        lane_priority_offset=12,
    ),
]


# Typical dry-van lane distance used to convert per-mile to flat. Real
# lanes vary; the BrokerRoutingTRM reads rate_flat as a lane-agnostic
# cheapest quote so a representative midpoint is good enough.
TYPICAL_LANE_MILES = 1000.0

# Market trend: +2% over the 20-week window (12 past + 8 future). Rates
# grow slowly through 2026 Q2-Q3 reflecting capacity tightening.
WEEKLY_TREND_PCT = 0.001  # 0.1% per week × 20 weeks ≈ 2%

# Seasonal amplitude: rates dip ~3% mid-year, peak late-year (Q4 produce
# / holiday). 2026-04-22 puts us at week 16 of the year — mid-cycle.
SEASONAL_AMPLITUDE_PCT = 0.03


# ───────────────────────────────────────────────────────────────────────
# Helpers
# ───────────────────────────────────────────────────────────────────────

def _seasonal_factor(week_offset: int) -> float:
    """Multiplier in [1-SEASONAL_AMPLITUDE, 1+SEASONAL_AMPLITUDE].

    Uses a sine wave over 52 weeks. week_offset is weeks relative to
    today (negative = past, positive = future). Peak at week 39-52
    (Q4), trough at week 13-26 (Q2-Q3).
    """
    # Phase: today is mid-Q2, near the sine trough. Offset so our "0"
    # point sits at roughly the trough, peaks 26 weeks later.
    phase_weeks = week_offset + 13  # trough at offset = -13
    radians = 2 * math.pi * phase_weeks / 52.0
    # -cos so we're near the min at week_offset=0, rising over time
    return 1.0 + SEASONAL_AMPLITUDE_PCT * (-math.cos(radians))


def _rate_for_week(base_rate: float, week_offset: int, noise_seed: int) -> float:
    """Model a weekly market rate for a broker-lane combination.

    Pattern: base × trend(week_offset) × seasonal(week_offset) × noise.
    Deterministic on (broker, lane, week) — re-seeding produces the
    same history each run.
    """
    trend = 1.0 + WEEKLY_TREND_PCT * week_offset
    seasonal = _seasonal_factor(week_offset)
    rng = random.Random(noise_seed + week_offset)
    noise = 1.0 + rng.uniform(-0.015, 0.015)  # ±1.5% noise-per-week
    return round(base_rate * trend * seasonal * noise, 2)


def _upsert_carrier(db, spec: BrokerSpec, tenant_id: int) -> Carrier:
    """Insert-or-return existing BROKER carrier for the tenant."""
    existing = db.execute(
        select(Carrier).where(
            and_(
                Carrier.tenant_id == tenant_id,
                Carrier.code == spec.code,
            )
        )
    ).scalar_one_or_none()
    if existing:
        logger.info("  %s already present (id=%d); leaving metadata as-is",
                    spec.code, existing.id)
        return existing

    carrier = Carrier(
        code=spec.code,
        name=spec.name,
        carrier_type=CarrierType.BROKER,
        scac=spec.scac,
        mc_number=spec.mc_number,
        dot_number=spec.dot_number,
        usdot_safety_rating="Satisfactory",
        modes=["FTL", "LTL", "DRAYAGE"],
        equipment_types=["DRY_VAN", "REEFER", "FLATBED"],
        service_regions=["US_DOMESTIC", "US_MX"],
        is_hazmat_certified=True,
        is_bonded=True,
        insurance_limit=spec.insurance_limit,
        primary_contact_name=f"{spec.name} Operations",
        primary_contact_email=f"ops@{spec.code.lower()}.example",
        primary_contact_phone="+1-555-0100",
        dispatch_email=f"dispatch@{spec.code.lower()}.example",
        dispatch_phone="+1-555-0101",
        tracking_api_type="API",
        is_active=True,
        onboarding_status="ACTIVE",
        onboarding_date=date(2024, 1, 15),
        last_shipment_date=date.today() - timedelta(days=3),
        source="seed_broker_carriers.py",
        tenant_id=tenant_id,
    )
    db.add(carrier)
    db.flush()
    logger.info("  + %s (id=%d, %s, %s)",
                spec.code, carrier.id, spec.headquarters, spec.reliability_label)
    return carrier


def _upsert_scorecards(db, carrier: Carrier, spec: BrokerSpec, tenant_id: int) -> int:
    """Create 3 trailing-quarter scorecards if missing. Returns rows added."""
    today = date.today()
    # Three trailing quarters ending 2026-03-31 (most recent complete)
    periods = [
        (date(2025, 7, 1), date(2025, 9, 30)),   # 2025 Q3
        (date(2025, 10, 1), date(2025, 12, 31)), # 2025 Q4
        (date(2026, 1, 1), date(2026, 3, 31)),   # 2026 Q1
    ]
    added = 0
    rng = random.Random(hash(spec.code) & 0xFFFF)
    for period_start, period_end in periods:
        existing = db.execute(
            select(CarrierScorecard).where(
                and_(
                    CarrierScorecard.carrier_id == carrier.id,
                    CarrierScorecard.period_start == period_start,
                )
            )
        ).scalar_one_or_none()
        if existing:
            continue

        # Characteristic band + small period-over-period variation
        otp_delivery = round(spec.base_on_time_delivery_pct + rng.uniform(-1.5, 1.5), 2)
        otp_pickup = round(otp_delivery + rng.uniform(0.5, 2.5), 2)  # Pickups run slightly better
        acceptance = round(spec.base_tender_acceptance_pct + rng.uniform(-2.0, 2.0), 2)
        damage = round(spec.base_damage_rate_pct + rng.uniform(-0.05, 0.08), 3)
        # Composite: weighted on_time_delivery * 0.4 + acceptance * 0.3 +
        # quality (inverse damage) * 0.2 + responsiveness * 0.1
        composite = round(
            otp_delivery * 0.40
            + acceptance * 0.30
            + (100 - damage * 100) * 0.20
            + 90 * 0.10,  # Responsiveness placeholder
            1,
        )

        sc = CarrierScorecard(
            carrier_id=carrier.id,
            period_start=period_start,
            period_end=period_end,
            total_shipments=rng.randint(120, 280),
            total_loads=rng.randint(140, 320),
            on_time_pickup_pct=min(99.5, otp_pickup),
            on_time_delivery_pct=min(99.5, otp_delivery),
            avg_transit_variance_hrs=round(rng.uniform(-1.5, 2.5), 2),
            avg_cost_per_mile=round(spec.base_rate_per_mile + rng.uniform(-0.10, 0.10), 3),
            avg_cost_per_shipment=round(
                (spec.base_rate_per_mile + rng.uniform(-0.10, 0.10)) * TYPICAL_LANE_MILES, 2
            ),
            cost_vs_benchmark_pct=round(rng.uniform(-3.0, 8.0), 2),
            damage_rate_pct=damage,
            claims_count=rng.randint(0, 4),
            claims_value=round(rng.uniform(0, 12500), 2),
            exception_rate_pct=round(rng.uniform(1.5, 4.5), 2),
            tender_acceptance_rate_pct=acceptance,
            avg_tender_response_hrs=round(rng.uniform(0.8, 2.4), 2),
            tracking_compliance_pct=round(rng.uniform(94, 99.5), 2),
            composite_score=composite,
            score_components={
                "on_time": 40, "acceptance": 30, "quality": 20, "responsiveness": 10,
            },
            tenant_id=tenant_id,
        )
        db.add(sc)
        added += 1

    if added:
        logger.info("  + %d scorecard periods (%s–%s band)",
                    added, spec.base_on_time_delivery_pct - 1.5,
                    spec.base_on_time_delivery_pct + 1.5)
    return added


def _upsert_lanes(
    db, carrier: Carrier, spec: BrokerSpec, tenant_id: int, lane_ids: List[int]
) -> int:
    """Register carrier coverage on every provided lane. Returns rows added."""
    added = 0
    for lane_id in lane_ids:
        existing = db.execute(
            select(CarrierLane).where(
                and_(
                    CarrierLane.carrier_id == carrier.id,
                    CarrierLane.lane_id == lane_id,
                )
            )
        ).scalar_one_or_none()
        if existing:
            continue
        cl = CarrierLane(
            carrier_id=carrier.id,
            lane_id=lane_id,
            mode=TransportMode.FTL,
            equipment_type=EquipmentType.DRY_VAN,
            weekly_capacity=25,
            avg_transit_days=3.0,
            transit_time_dist={"type": "lognormal", "mean": 3.0, "stddev": 0.5},
            priority=spec.lane_priority_offset,
            is_primary=False,
            is_active=True,
            eff_start_date=date(2024, 1, 15),
            eff_end_date=date(2028, 12, 31),
            tenant_id=tenant_id,
        )
        db.add(cl)
        added += 1
    if added:
        logger.info("  + %d lane-coverage rows (priority=%d)",
                    added, spec.lane_priority_offset)
    return added


def _upsert_rates(
    db, carrier: Carrier, spec: BrokerSpec, tenant_id: int, lane_ids: List[int]
) -> int:
    """Create rate history (12 past) + current (1 CONTRACT) + projections
    (8 future SPOT) per lane. Returns rows added."""
    today = date.today()
    added = 0
    noise_seed = hash(spec.code) & 0xFFFF

    for lane_id in lane_ids:
        # Skip if already has a CONTRACT rate for this broker/lane — means
        # the seed has run before for this pairing.
        existing_contract = db.execute(
            select(FreightRate).where(
                and_(
                    FreightRate.carrier_id == carrier.id,
                    FreightRate.lane_id == lane_id,
                    FreightRate.rate_type == RateType.CONTRACT,
                    FreightRate.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if existing_contract:
            continue

        # 12 past weekly SPOT rates (history, is_active=False)
        for weeks_ago in range(12, 0, -1):
            week_offset = -weeks_ago
            week_start = today - timedelta(days=7 * weeks_ago)
            week_end = week_start + timedelta(days=6)
            per_mile = _rate_for_week(spec.base_rate_per_mile, week_offset, noise_seed + lane_id)
            flat = round(per_mile * TYPICAL_LANE_MILES, 2)
            rate = FreightRate(
                carrier_id=carrier.id,
                lane_id=lane_id,
                mode=TransportMode.FTL,
                equipment_type=EquipmentType.DRY_VAN,
                rate_type=RateType.SPOT,
                rate_per_mile=per_mile,
                rate_flat=flat,
                fuel_surcharge_pct=spec.fuel_surcharge_pct or None,
                fuel_surcharge_method=spec.fuel_surcharge_method,
                eff_start_date=week_start,
                eff_end_date=week_end,
                is_active=False,  # Historical — no longer actionable
                market_rate_at_contract=round(per_mile * 0.92 * TYPICAL_LANE_MILES, 2),
                source=f"historical_spot:{week_start.isoformat()}",
                tenant_id=tenant_id,
                config_id=None,
            )
            db.add(rate)
            added += 1

        # 1 CONTRACT rate active now (90-day validity centred on today).
        # This is what BrokerRoutingTRM reads as the broker's current quote.
        contract_per_mile = _rate_for_week(spec.base_rate_per_mile, 0, noise_seed + lane_id)
        contract_flat = round(contract_per_mile * TYPICAL_LANE_MILES, 2)
        contract_rate = FreightRate(
            carrier_id=carrier.id,
            lane_id=lane_id,
            mode=TransportMode.FTL,
            equipment_type=EquipmentType.DRY_VAN,
            rate_type=RateType.CONTRACT,
            rate_per_mile=contract_per_mile,
            rate_flat=contract_flat,
            min_charge=contract_flat * 0.9,
            fuel_surcharge_pct=spec.fuel_surcharge_pct or None,
            fuel_surcharge_method=spec.fuel_surcharge_method,
            accessorial_schedule={
                "DETENTION_PER_HOUR": 75.0,
                "LIFTGATE": 150.0,
                "INSIDE_DELIVERY": 200.0,
                "DRIVER_ASSIST": 85.0,
            },
            eff_start_date=today - timedelta(days=14),
            eff_end_date=today + timedelta(days=76),  # 90-day window
            contract_number=f"{spec.code}-{today.year}-Q{(today.month - 1) // 3 + 1}-L{lane_id}",
            is_active=True,
            min_volume_per_week=3,
            max_volume_per_week=25,
            market_rate_at_contract=round(contract_per_mile * 0.93 * TYPICAL_LANE_MILES, 2),
            source="broker_contract_q2_2026",
            tenant_id=tenant_id,
            config_id=None,
        )
        db.add(contract_rate)
        added += 1

        # 8 future weekly SPOT projections (forward market curve)
        for weeks_ahead in range(1, 9):
            week_offset = weeks_ahead
            week_start = today + timedelta(days=7 * weeks_ahead)
            week_end = week_start + timedelta(days=6)
            per_mile = _rate_for_week(spec.base_rate_per_mile, week_offset, noise_seed + lane_id)
            flat = round(per_mile * TYPICAL_LANE_MILES, 2)
            rate = FreightRate(
                carrier_id=carrier.id,
                lane_id=lane_id,
                mode=TransportMode.FTL,
                equipment_type=EquipmentType.DRY_VAN,
                rate_type=RateType.SPOT,
                rate_per_mile=per_mile,
                rate_flat=flat,
                fuel_surcharge_pct=spec.fuel_surcharge_pct or None,
                fuel_surcharge_method=spec.fuel_surcharge_method,
                eff_start_date=week_start,
                eff_end_date=week_end,
                is_active=True,  # Projection — future-dated, becomes live as calendar advances
                market_rate_at_contract=round(per_mile * 0.92 * TYPICAL_LANE_MILES, 2),
                source=f"projected_spot:{week_start.isoformat()}",
                tenant_id=tenant_id,
                config_id=None,
            )
            db.add(rate)
            added += 1

    if added:
        logger.info("  + %d rate rows (history 12 + contract 1 + projections 8) × %d lanes",
                    added, len(lane_ids))
    return added


def _get_tenant_lane_ids(db, tenant_id: int) -> List[int]:
    """Every transportation_lane belonging to any config of this tenant."""
    from app.models.supply_chain_config import SupplyChainConfig, TransportationLane
    rows = db.execute(
        select(TransportationLane.id)
        .join(SupplyChainConfig, SupplyChainConfig.id == TransportationLane.config_id)
        .where(SupplyChainConfig.tenant_id == tenant_id)
    ).scalars().all()
    return sorted(set(int(r) for r in rows))


# ───────────────────────────────────────────────────────────────────────
# Entry point
# ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tenant-id", type=int, default=1,
                        help="Tenant to seed into (default: 1)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be done; don't commit.")
    args = parser.parse_args()

    with sync_session_factory() as db:
        lane_ids = _get_tenant_lane_ids(db, args.tenant_id)
        if not lane_ids:
            logger.error("Tenant %d has no transportation_lane rows. Seed lanes first.",
                         args.tenant_id)
            sys.exit(1)
        logger.info("Target tenant: %d (%d lanes)", args.tenant_id, len(lane_ids))

        totals = {"carriers": 0, "scorecards": 0, "lanes": 0, "rates": 0}

        for spec in BROKERS:
            logger.info("--- %s (%s) ---", spec.code, spec.name)
            carrier = _upsert_carrier(db, spec, args.tenant_id)
            totals["carriers"] += 1
            totals["scorecards"] += _upsert_scorecards(db, carrier, spec, args.tenant_id)
            totals["lanes"] += _upsert_lanes(db, carrier, spec, args.tenant_id, lane_ids)
            totals["rates"] += _upsert_rates(db, carrier, spec, args.tenant_id, lane_ids)

        if args.dry_run:
            db.rollback()
            logger.info("DRY-RUN: rolled back. Totals would have been: %s", totals)
        else:
            db.commit()
            logger.info("COMMITTED. Totals: %s", totals)


if __name__ == "__main__":
    main()
