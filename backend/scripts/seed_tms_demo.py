#!/usr/bin/env python3
"""
Seed TMS demo data for a tenant.

Creates realistic transportation demo data: facilities, carriers, lanes,
rates, loads, shipments, appointments, exceptions, and commodities.

Usage:
    docker compose exec backend python scripts/seed_tms_demo.py --tenant-id 1 --config-id 1
"""

import argparse
import sys
import os
from datetime import datetime, date, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.db.session import sync_session_factory
from app.models.tms_entities import (
    Commodity, CommodityHierarchy,
    Carrier, CarrierLane, CarrierScorecard, Equipment,
    Shipment, Load, FreightRate,
    Appointment, ShipmentException,
    CarrierType, TransportMode, EquipmentType,
    ShipmentStatus, LoadStatus, ExceptionType, ExceptionSeverity,
    ExceptionResolutionStatus, AppointmentType, AppointmentStatus, RateType,
)
from app.models.transportation_config import (
    FacilityConfig, LaneProfile, FacilityType, LaneDirection,
)
from app.models.supply_chain_config import Site, TransportationLane
from sqlalchemy import select


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _get_or_skip(session, model, tenant_id, unique_field, unique_value):
    """Return existing record or None (meaning caller should create)."""
    stmt = select(model).where(
        getattr(model, 'tenant_id') == tenant_id,
        getattr(model, unique_field) == unique_value,
    )
    return session.execute(stmt).scalar_one_or_none()


def _get_site_by_name(session, config_id, name):
    stmt = select(Site).where(Site.config_id == config_id, Site.name == name)
    return session.execute(stmt).scalar_one_or_none()


def _get_lane(session, config_id, from_site_id, to_site_id):
    stmt = select(TransportationLane).where(
        TransportationLane.config_id == config_id,
        TransportationLane.from_site_id == from_site_id,
        TransportationLane.to_site_id == to_site_id,
    )
    return session.execute(stmt).scalar_one_or_none()


# ---------------------------------------------------------------------------
# Commodities
# ---------------------------------------------------------------------------

COMMODITIES = [
    {"code": "DRY-GROCERY", "description": "Dry Grocery", "freight_class": "70",
     "weight": 40.0, "weight_uom": "LBS", "base_uom": "CS"},
    {"code": "REFRIG-PRODUCE", "description": "Refrigerated Produce", "freight_class": "85",
     "weight": 35.0, "weight_uom": "LBS", "base_uom": "CS",
     "is_temperature_sensitive": True, "temp_min": 33.0, "temp_max": 40.0},
    {"code": "ELECTRONICS", "description": "Electronics", "freight_class": "125",
     "weight": 25.0, "weight_uom": "LBS", "base_uom": "EA", "value_per_unit": 450.0},
    {"code": "BUILDING-MAT", "description": "Building Materials", "freight_class": "50",
     "weight": 80.0, "weight_uom": "LBS", "base_uom": "EA"},
    {"code": "CHEM-HAZMAT", "description": "Chemicals/Hazmat", "freight_class": "150",
     "weight": 55.0, "weight_uom": "LBS", "base_uom": "DR",
     "is_hazmat": True, "hazmat_class": "3", "hazmat_un_number": "UN1993"},
]


def seed_commodities(session, tenant_id, config_id):
    created = 0
    for c in COMMODITIES:
        if _get_or_skip(session, Commodity, tenant_id, 'code', c['code']):
            continue
        session.add(Commodity(
            tenant_id=tenant_id, config_id=config_id,
            code=c['code'], description=c['description'],
            freight_class=c['freight_class'], weight=c['weight'],
            weight_uom=c['weight_uom'], base_uom=c['base_uom'],
            is_hazmat=c.get('is_hazmat', False),
            hazmat_class=c.get('hazmat_class'),
            hazmat_un_number=c.get('hazmat_un_number'),
            is_temperature_sensitive=c.get('is_temperature_sensitive', False),
            temp_min=c.get('temp_min'), temp_max=c.get('temp_max'),
            value_per_unit=c.get('value_per_unit'),
            source="DEMO_SEED",
        ))
        created += 1
    session.flush()
    print(f"  Commodities: {created} created, {len(COMMODITIES) - created} already exist")


# ---------------------------------------------------------------------------
# Facilities (Sites + FacilityConfig)
# ---------------------------------------------------------------------------

FACILITIES = [
    {"name": "Chicago Distribution Center", "type": "inventory", "ftype": FacilityType.SHIPPER,
     "lat": 41.8781, "lon": -87.6298, "dock_doors": 16, "yard_spots": 60,
     "hours": {"mon": {"open": "05:00", "close": "22:00"}, "tue": {"open": "05:00", "close": "22:00"},
               "wed": {"open": "05:00", "close": "22:00"}, "thu": {"open": "05:00", "close": "22:00"},
               "fri": {"open": "05:00", "close": "22:00"}, "sat": {"open": "06:00", "close": "14:00"}}},
    {"name": "Dallas Warehouse", "type": "inventory", "ftype": FacilityType.SHIPPER,
     "lat": 32.7767, "lon": -96.7970, "dock_doors": 12, "yard_spots": 45,
     "hours": {"mon": {"open": "06:00", "close": "21:00"}, "tue": {"open": "06:00", "close": "21:00"},
               "wed": {"open": "06:00", "close": "21:00"}, "thu": {"open": "06:00", "close": "21:00"},
               "fri": {"open": "06:00", "close": "21:00"}}},
    {"name": "Atlanta Hub", "type": "inventory", "ftype": FacilityType.SHIPPER,
     "lat": 33.7490, "lon": -84.3880, "dock_doors": 14, "yard_spots": 50,
     "hours": {"mon": {"open": "05:00", "close": "23:00"}, "tue": {"open": "05:00", "close": "23:00"},
               "wed": {"open": "05:00", "close": "23:00"}, "thu": {"open": "05:00", "close": "23:00"},
               "fri": {"open": "05:00", "close": "23:00"}, "sat": {"open": "07:00", "close": "15:00"}}},
    {"name": "Memphis Intermodal Terminal", "type": "inventory", "ftype": FacilityType.TERMINAL,
     "lat": 35.1495, "lon": -90.0490, "dock_doors": 20, "yard_spots": 80,
     "hours": {"mon": {"open": "00:00", "close": "23:59"}, "tue": {"open": "00:00", "close": "23:59"},
               "wed": {"open": "00:00", "close": "23:59"}, "thu": {"open": "00:00", "close": "23:59"},
               "fri": {"open": "00:00", "close": "23:59"}, "sat": {"open": "00:00", "close": "23:59"},
               "sun": {"open": "00:00", "close": "23:59"}}},
    {"name": "Kansas City Cross-Dock", "type": "inventory", "ftype": FacilityType.CROSS_DOCK,
     "lat": 39.0997, "lon": -94.5786, "dock_doors": 18, "yard_spots": 40,
     "hours": {"mon": {"open": "04:00", "close": "23:00"}, "tue": {"open": "04:00", "close": "23:00"},
               "wed": {"open": "04:00", "close": "23:00"}, "thu": {"open": "04:00", "close": "23:00"},
               "fri": {"open": "04:00", "close": "23:00"}, "sat": {"open": "06:00", "close": "18:00"}}},
    {"name": "New York Retail DC", "type": "inventory", "ftype": FacilityType.CONSIGNEE,
     "lat": 40.7128, "lon": -74.0060, "dock_doors": 10, "yard_spots": 30,
     "hours": {"mon": {"open": "06:00", "close": "20:00"}, "tue": {"open": "06:00", "close": "20:00"},
               "wed": {"open": "06:00", "close": "20:00"}, "thu": {"open": "06:00", "close": "20:00"},
               "fri": {"open": "06:00", "close": "20:00"}}},
    {"name": "Los Angeles Grocery DC", "type": "inventory", "ftype": FacilityType.CONSIGNEE,
     "lat": 33.9425, "lon": -118.2551, "dock_doors": 12, "yard_spots": 35,
     "hours": {"mon": {"open": "05:00", "close": "21:00"}, "tue": {"open": "05:00", "close": "21:00"},
               "wed": {"open": "05:00", "close": "21:00"}, "thu": {"open": "05:00", "close": "21:00"},
               "fri": {"open": "05:00", "close": "21:00"}}},
    {"name": "Port of Long Beach", "type": "inventory", "ftype": FacilityType.PORT,
     "lat": 33.7701, "lon": -118.1937, "dock_doors": 6, "yard_spots": 75,
     "hours": {"mon": {"open": "00:00", "close": "23:59"}, "tue": {"open": "00:00", "close": "23:59"},
               "wed": {"open": "00:00", "close": "23:59"}, "thu": {"open": "00:00", "close": "23:59"},
               "fri": {"open": "00:00", "close": "23:59"}, "sat": {"open": "00:00", "close": "23:59"},
               "sun": {"open": "00:00", "close": "23:59"}}},
]


def seed_facilities(session, tenant_id, config_id):
    created_sites = 0
    created_configs = 0
    for f in FACILITIES:
        site = _get_site_by_name(session, config_id, f['name'])
        if not site:
            site = Site(
                config_id=config_id, name=f['name'], type=f['type'],
                latitude=f['lat'], longitude=f['lon'],
            )
            session.add(site)
            session.flush()
            created_sites += 1

        existing_fc = session.execute(
            select(FacilityConfig).where(
                FacilityConfig.site_id == site.id,
                FacilityConfig.config_id == config_id,
            )
        ).scalar_one_or_none()
        if not existing_fc:
            inbound = f['dock_doors'] // 2
            session.add(FacilityConfig(
                site_id=site.id, config_id=config_id, tenant_id=tenant_id,
                facility_type=f['ftype'],
                total_dock_doors=f['dock_doors'],
                inbound_dock_doors=inbound,
                outbound_dock_doors=f['dock_doors'] - inbound,
                total_yard_spots=f['yard_spots'],
                reefer_yard_spots=f['yard_spots'] // 5,
                operating_hours=f['hours'],
                timezone="America/Chicago",
                requires_appointment=True,
                appointment_lead_time_hrs=24,
                default_appointment_duration_min=60,
                capabilities=["LIVE_LOAD", "DROP_TRAILER"],
                equipment_compatible=["DRY_VAN", "REEFER", "FLATBED"],
                max_daily_inbound_loads=f['dock_doors'] * 3,
                max_daily_outbound_loads=f['dock_doors'] * 3,
            ))
            created_configs += 1
    session.flush()
    print(f"  Sites: {created_sites} created, {len(FACILITIES) - created_sites} already exist")
    print(f"  FacilityConfigs: {created_configs} created")


# ---------------------------------------------------------------------------
# Carriers
# ---------------------------------------------------------------------------

CARRIERS = [
    {"code": "SWFT", "name": "Swift Transportation", "scac": "SWFT",
     "carrier_type": CarrierType.ASSET, "modes": ["FTL"],
     "equipment_types": ["DRY_VAN", "REEFER"], "otd": 92.0, "score": 88},
    {"code": "WERN", "name": "Werner Enterprises", "scac": "WERN",
     "carrier_type": CarrierType.ASSET, "modes": ["FTL", "LTL"],
     "equipment_types": ["DRY_VAN", "REEFER", "FLATBED"], "otd": 89.0, "score": 84},
    {"code": "JBHT", "name": "J.B. Hunt", "scac": "JBHT",
     "carrier_type": CarrierType.ASSET, "modes": ["INTERMODAL", "FTL"],
     "equipment_types": ["CONTAINER_40", "CONTAINER_40HC", "DRY_VAN"], "otd": 94.0, "score": 91},
    {"code": "XPOL", "name": "XPO Logistics", "scac": "XPOL",
     "carrier_type": CarrierType.THREE_PL, "modes": ["LTL"],
     "equipment_types": ["DRY_VAN"], "otd": 87.0, "score": 80},
    {"code": "SNDR", "name": "Schneider National", "scac": "SNDR",
     "carrier_type": CarrierType.ASSET, "modes": ["FTL", "INTERMODAL"],
     "equipment_types": ["DRY_VAN", "REEFER", "CONTAINER_40HC"], "otd": 91.0, "score": 87},
    {"code": "ECHO", "name": "Echo Global Logistics", "scac": "ECHO",
     "carrier_type": CarrierType.BROKER, "modes": ["FTL", "LTL", "INTERMODAL"],
     "equipment_types": ["DRY_VAN", "REEFER", "FLATBED"], "otd": 85.0, "score": 76},
]


def seed_carriers(session, tenant_id, config_id):
    created_carriers = 0
    created_scorecards = 0
    today = date.today()
    period_start = today - timedelta(days=90)

    for c in CARRIERS:
        if _get_or_skip(session, Carrier, tenant_id, 'code', c['code']):
            continue
        carrier = Carrier(
            tenant_id=tenant_id, config_id=config_id,
            code=c['code'], name=c['name'], scac=c['scac'],
            carrier_type=c['carrier_type'],
            modes=c['modes'], equipment_types=c['equipment_types'],
            service_regions=["US_DOMESTIC"],
            is_active=True, onboarding_status="ACTIVE",
            onboarding_date=date(2025, 1, 15),
            primary_contact_name=f"{c['name']} Dispatch",
            dispatch_email=f"dispatch@{c['code'].lower()}.com",
            source="DEMO_SEED",
        )
        session.add(carrier)
        session.flush()
        created_carriers += 1

        session.add(CarrierScorecard(
            tenant_id=tenant_id, carrier_id=carrier.id,
            period_start=period_start, period_end=today,
            total_shipments=320, total_loads=280,
            on_time_pickup_pct=c['otd'] - 2.0,
            on_time_delivery_pct=c['otd'],
            avg_transit_variance_hrs=round((100 - c['otd']) * 0.8, 1),
            avg_cost_per_mile=round(2.10 + (100 - c['score']) * 0.02, 2),
            avg_cost_per_shipment=round(1800 + (100 - c['score']) * 30, 0),
            damage_rate_pct=round(0.2 + (100 - c['score']) * 0.01, 2),
            claims_count=max(0, (100 - c['score']) // 5),
            tender_acceptance_rate_pct=round(78 + c['score'] * 0.15, 1),
            tracking_compliance_pct=round(80 + c['score'] * 0.15, 1),
            composite_score=float(c['score']),
            score_components={"on_time": 30, "cost": 25, "quality": 20, "responsiveness": 25},
        ))
        created_scorecards += 1

    session.flush()
    print(f"  Carriers: {created_carriers} created, {len(CARRIERS) - created_carriers} already exist")
    print(f"  CarrierScorecards: {created_scorecards} created")


# ---------------------------------------------------------------------------
# Lanes (TransportationLane + LaneProfile)
# ---------------------------------------------------------------------------

LANE_DEFS = [
    ("Chicago Distribution Center", "New York Retail DC", "FTL", 790, 13.0, 2.1),
    ("Chicago Distribution Center", "Los Angeles Grocery DC", "FTL", 2015, 32.0, 2.45),
    ("Dallas Warehouse", "Atlanta Hub", "FTL", 781, 12.5, 2.05),
    ("Dallas Warehouse", "New York Retail DC", "FTL", 1548, 24.0, 2.30),
    ("Atlanta Hub", "New York Retail DC", "FTL", 868, 14.0, 2.15),
    ("Memphis Intermodal Terminal", "Chicago Distribution Center", "INTERMODAL", 530, 18.0, 1.80),
    ("Kansas City Cross-Dock", "Dallas Warehouse", "LTL", 500, 10.0, 2.60),
    ("Port of Long Beach", "Chicago Distribution Center", "INTERMODAL", 2015, 72.0, 1.85),
    ("Port of Long Beach", "Dallas Warehouse", "INTERMODAL", 1435, 56.0, 1.90),
    ("Atlanta Hub", "Los Angeles Grocery DC", "FTL", 2175, 34.0, 2.50),
]


def seed_lanes(session, tenant_id, config_id):
    created_lanes = 0
    created_profiles = 0

    for (origin_name, dest_name, mode, miles, drive_hrs, cpm) in LANE_DEFS:
        origin = _get_site_by_name(session, config_id, origin_name)
        dest = _get_site_by_name(session, config_id, dest_name)
        if not origin or not dest:
            print(f"    WARN: could not find sites for lane {origin_name} -> {dest_name}")
            continue

        lane = _get_lane(session, config_id, origin.id, dest.id)
        if not lane:
            lane = TransportationLane(
                config_id=config_id,
                from_site_id=origin.id, to_site_id=dest.id,
                capacity=50,
            )
            session.add(lane)
            session.flush()
            created_lanes += 1

        existing_lp = session.execute(
            select(LaneProfile).where(
                LaneProfile.lane_id == lane.id,
                LaneProfile.config_id == config_id,
            )
        ).scalar_one_or_none()
        if not existing_lp:
            transit_days = round(drive_hrs / 10.0, 1)  # ~10 hrs driving/day
            session.add(LaneProfile(
                lane_id=lane.id, config_id=config_id, tenant_id=tenant_id,
                primary_mode=mode, direction=LaneDirection.OUTBOUND,
                distance_miles=float(miles), drive_time_hours=drive_hrs,
                avg_transit_days=transit_days,
                p10_transit_days=round(transit_days * 0.85, 1),
                p50_transit_days=transit_days,
                p90_transit_days=round(transit_days * 1.25, 1),
                avg_weekly_volume=12, peak_weekly_volume=20,
                avg_cost_per_mile=cpm,
                benchmark_rate=round(cpm * miles, 2),
                benchmark_source="DAT",
                benchmark_date=date.today() - timedelta(days=7),
                disruption_frequency=2.5,
                weather_risk_score=0.15,
                congestion_risk_score=0.20,
                is_active=True,
            ))
            created_profiles += 1

    session.flush()
    print(f"  Lanes: {created_lanes} created, {len(LANE_DEFS) - created_lanes} already exist")
    print(f"  LaneProfiles: {created_profiles} created")


# ---------------------------------------------------------------------------
# Freight Rates
# ---------------------------------------------------------------------------

def seed_rates(session, tenant_id, config_id):
    created = 0
    today = date.today()
    carriers = session.execute(
        select(Carrier).where(Carrier.tenant_id == tenant_id)
    ).scalars().all()
    carrier_map = {c.code: c for c in carriers}

    # Build lane lookup
    lanes = []
    for (origin_name, dest_name, mode, miles, _, _) in LANE_DEFS:
        origin = _get_site_by_name(session, config_id, origin_name)
        dest = _get_site_by_name(session, config_id, dest_name)
        if origin and dest:
            lane = _get_lane(session, config_id, origin.id, dest.id)
            if lane:
                lanes.append((lane, mode, miles))

    # Assign 2-4 carriers per lane (20 total rates target)
    rate_assignments = [
        ("SWFT", 0, RateType.CONTRACT, 0.00), ("WERN", 0, RateType.CONTRACT, 0.03),
        ("SNDR", 1, RateType.CONTRACT, -0.02), ("JBHT", 1, RateType.CONTRACT, 0.05),
        ("SWFT", 2, RateType.CONTRACT, 0.01), ("XPOL", 2, RateType.SPOT, 0.10),
        ("WERN", 3, RateType.CONTRACT, 0.02), ("ECHO", 3, RateType.SPOT, 0.08),
        ("SNDR", 4, RateType.CONTRACT, -0.01), ("SWFT", 4, RateType.CONTRACT, 0.04),
        ("JBHT", 5, RateType.CONTRACT, -0.10), ("SNDR", 5, RateType.CONTRACT, 0.00),
        ("XPOL", 6, RateType.CONTRACT, 0.15), ("ECHO", 6, RateType.SPOT, 0.12),
        ("JBHT", 7, RateType.CONTRACT, -0.15), ("SNDR", 7, RateType.CONTRACT, -0.05),
        ("JBHT", 8, RateType.CONTRACT, -0.10), ("ECHO", 8, RateType.SPOT, 0.05),
        ("SWFT", 9, RateType.CONTRACT, 0.02), ("WERN", 9, RateType.CONTRACT, 0.06),
    ]

    mode_to_enum = {
        "FTL": TransportMode.FTL, "LTL": TransportMode.LTL,
        "INTERMODAL": TransportMode.INTERMODAL,
    }

    for (carrier_code, lane_idx, rtype, cpm_delta) in rate_assignments:
        if lane_idx >= len(lanes):
            continue
        lane, mode_str, miles = lanes[lane_idx]
        carrier = carrier_map.get(carrier_code)
        if not carrier:
            continue

        # Check existence by carrier+lane+rate_type
        existing = session.execute(
            select(FreightRate).where(
                FreightRate.tenant_id == tenant_id,
                FreightRate.carrier_id == carrier.id,
                FreightRate.lane_id == lane.id,
                FreightRate.rate_type == rtype,
            )
        ).scalar_one_or_none()
        if existing:
            continue

        base_cpm = LANE_DEFS[lane_idx][5]
        actual_cpm = round(base_cpm + cpm_delta, 2)
        session.add(FreightRate(
            tenant_id=tenant_id, config_id=config_id,
            carrier_id=carrier.id, lane_id=lane.id,
            mode=mode_to_enum.get(mode_str, TransportMode.FTL),
            equipment_type=EquipmentType.DRY_VAN,
            rate_type=rtype,
            rate_per_mile=actual_cpm,
            rate_flat=round(actual_cpm * miles, 2),
            fuel_surcharge_pct=18.5 if rtype == RateType.CONTRACT else 22.0,
            fuel_surcharge_method="DOE_INDEX",
            min_charge=350.0,
            eff_start_date=today - timedelta(days=180),
            eff_end_date=today + timedelta(days=185),
            is_active=True,
            source="DEMO_SEED",
        ))
        created += 1

    session.flush()
    print(f"  FreightRates: {created} created")


# ---------------------------------------------------------------------------
# Carrier Lanes
# ---------------------------------------------------------------------------

def seed_carrier_lanes(session, tenant_id, config_id):
    created = 0
    carriers = session.execute(
        select(Carrier).where(Carrier.tenant_id == tenant_id)
    ).scalars().all()
    carrier_map = {c.code: c for c in carriers}

    mode_to_enum = {
        "FTL": TransportMode.FTL, "LTL": TransportMode.LTL,
        "INTERMODAL": TransportMode.INTERMODAL,
    }

    # Derive carrier-lane from rates already created
    rates = session.execute(
        select(FreightRate).where(FreightRate.tenant_id == tenant_id)
    ).scalars().all()

    seen = set()
    for rate in rates:
        key = (rate.carrier_id, rate.lane_id, str(rate.mode))
        if key in seen:
            continue
        seen.add(key)

        existing = session.execute(
            select(CarrierLane).where(
                CarrierLane.tenant_id == tenant_id,
                CarrierLane.carrier_id == rate.carrier_id,
                CarrierLane.lane_id == rate.lane_id,
            )
        ).scalar_one_or_none()
        if existing:
            continue

        session.add(CarrierLane(
            tenant_id=tenant_id,
            carrier_id=rate.carrier_id,
            lane_id=rate.lane_id,
            mode=rate.mode,
            equipment_type=EquipmentType.DRY_VAN,
            weekly_capacity=15,
            avg_transit_days=2.5,
            priority=1,
            is_primary=(created % 3 == 0),
            is_active=True,
            eff_start_date=date.today() - timedelta(days=180),
            eff_end_date=date.today() + timedelta(days=185),
        ))
        created += 1

    session.flush()
    print(f"  CarrierLanes: {created} created")


# ---------------------------------------------------------------------------
# Loads
# ---------------------------------------------------------------------------

LOAD_STATUSES = (
    [LoadStatus.PLANNING] * 5 +
    [LoadStatus.TENDERED] * 5 +
    [LoadStatus.IN_TRANSIT] * 8 +
    [LoadStatus.DELIVERED] * 7 +
    [LoadStatus.CLOSED] * 5
)


def seed_loads(session, tenant_id, config_id):
    created = 0
    today = datetime.utcnow()

    carriers = session.execute(
        select(Carrier).where(Carrier.tenant_id == tenant_id)
    ).scalars().all()
    if not carriers:
        print("  Loads: skipped (no carriers)")
        return

    # Collect all facility sites
    sites = []
    for f in FACILITIES:
        site = _get_site_by_name(session, config_id, f['name'])
        if site:
            sites.append(site)
    if len(sites) < 2:
        print("  Loads: skipped (not enough sites)")
        return

    for i in range(30):
        load_number = f"LD-2026-{i+1:04d}"
        if _get_or_skip(session, Load, tenant_id, 'load_number', load_number):
            continue

        status = LOAD_STATUSES[i]
        origin = sites[i % 3]  # rotate through shippers
        dest = sites[5 + (i % 2)]  # rotate through consignees (idx 5,6)
        carrier = carriers[i % len(carriers)]
        weight = 22000 + (i * 733) % 22000  # 22k-44k lbs
        modes = [TransportMode.FTL, TransportMode.LTL, TransportMode.INTERMODAL]

        days_offset = -5 + (i % 12)
        departure = today + timedelta(days=days_offset)
        arrival = departure + timedelta(hours=18 + (i % 48))

        session.add(Load(
            tenant_id=tenant_id, config_id=config_id,
            load_number=load_number,
            status=status,
            origin_site_id=origin.id,
            destination_site_id=dest.id,
            mode=modes[i % 3],
            equipment_type=EquipmentType.DRY_VAN,
            carrier_id=carrier.id,
            total_weight=float(weight),
            total_volume=round(weight / 12.0, 1),
            total_pallets=weight // 2200,
            weight_utilization_pct=round(weight / 44000 * 100, 1),
            planned_departure=departure,
            planned_arrival=arrival,
            actual_departure=departure if status in (LoadStatus.IN_TRANSIT, LoadStatus.DELIVERED, LoadStatus.CLOSED) else None,
            actual_arrival=arrival if status in (LoadStatus.DELIVERED, LoadStatus.CLOSED) else None,
            total_miles=float(600 + (i * 97) % 1500),
            cost_per_mile=round(2.0 + (i % 8) * 0.15, 2),
            total_cost=round((600 + (i * 97) % 1500) * (2.0 + (i % 8) * 0.15), 2),
            source="DEMO_SEED",
        ))
        created += 1

    session.flush()
    print(f"  Loads: {created} created, {30 - created} already exist")


# ---------------------------------------------------------------------------
# Shipments
# ---------------------------------------------------------------------------

# In-transit lat/lon points along US highways
TRANSIT_POINTS = [
    (41.59, -83.65), (40.80, -81.37), (40.44, -79.99),  # OH/PA corridor
    (39.95, -75.17), (40.22, -74.76), (40.71, -74.01),  # NJ/NY
    (38.90, -77.04), (37.54, -77.43), (35.23, -80.84),  # VA/NC
    (34.05, -118.24), (35.47, -97.52), (36.16, -95.99), # OK/CA
    (38.63, -90.20), (39.77, -86.16), (41.25, -95.94),  # MO/IN/NE
    (32.78, -96.80), (33.45, -88.82), (35.05, -85.31),  # TX/MS/TN
]


def seed_shipments(session, tenant_id, config_id):
    created = 0
    today = datetime.utcnow()

    loads = session.execute(
        select(Load).where(Load.tenant_id == tenant_id)
    ).scalars().all()
    load_map = {l.load_number: l for l in loads}

    carriers = session.execute(
        select(Carrier).where(Carrier.tenant_id == tenant_id)
    ).scalars().all()
    if not carriers:
        print("  Shipments: skipped (no carriers)")
        return

    commodities = session.execute(
        select(Commodity).where(Commodity.tenant_id == tenant_id)
    ).scalars().all()

    sites = []
    for f in FACILITIES:
        site = _get_site_by_name(session, config_id, f['name'])
        if site:
            sites.append(site)

    statuses_cycle = [
        ShipmentStatus.DRAFT, ShipmentStatus.TENDERED, ShipmentStatus.ACCEPTED,
        ShipmentStatus.DISPATCHED, ShipmentStatus.IN_TRANSIT, ShipmentStatus.IN_TRANSIT,
        ShipmentStatus.IN_TRANSIT, ShipmentStatus.DELIVERED, ShipmentStatus.DELIVERED,
        ShipmentStatus.POD_RECEIVED, ShipmentStatus.CLOSED, ShipmentStatus.EXCEPTION,
    ]

    for i in range(50):
        shipment_number = f"SHP-2026-{i+1:05d}"
        if _get_or_skip(session, Shipment, tenant_id, 'shipment_number', shipment_number):
            continue

        status = statuses_cycle[i % len(statuses_cycle)]
        origin = sites[i % 3]
        dest = sites[5 + (i % 2)]
        carrier = carriers[i % len(carriers)]
        commodity = commodities[i % len(commodities)] if commodities else None

        load_idx = i * 30 // 50  # distribute across loads
        load_num = f"LD-2026-{load_idx+1:04d}"
        load = load_map.get(load_num)

        weight = 4000 + (i * 311) % 10000
        pickup = today + timedelta(days=-3 + (i % 10))
        delivery = pickup + timedelta(hours=20 + (i % 60))

        # Lat/lon for in-transit
        lat, lon = (None, None)
        if status == ShipmentStatus.IN_TRANSIT:
            pt = TRANSIT_POINTS[i % len(TRANSIT_POINTS)]
            lat, lon = pt

        # ETA confidence
        eta_conf = None
        if status in (ShipmentStatus.IN_TRANSIT, ShipmentStatus.DISPATCHED):
            p50 = delivery
            eta_conf = {
                "p10": (p50 - timedelta(hours=6)).isoformat(),
                "p50": p50.isoformat(),
                "p90": (p50 + timedelta(hours=14)).isoformat(),
            }

        session.add(Shipment(
            tenant_id=tenant_id, config_id=config_id,
            shipment_number=shipment_number,
            status=status,
            origin_site_id=origin.id,
            destination_site_id=dest.id,
            commodity_id=commodity.id if commodity else None,
            weight=float(weight), weight_uom="LBS",
            volume=round(weight / 10.0, 1), volume_uom="CUFT",
            pallet_count=max(1, weight // 2200),
            mode=TransportMode.FTL if i % 3 != 2 else TransportMode.INTERMODAL,
            required_equipment=EquipmentType.DRY_VAN,
            requested_pickup_date=pickup,
            requested_delivery_date=delivery,
            actual_pickup_date=pickup if status.value in ("IN_TRANSIT", "DELIVERED", "POD_RECEIVED", "CLOSED") else None,
            actual_delivery_date=delivery if status.value in ("DELIVERED", "POD_RECEIVED", "CLOSED") else None,
            load_id=load.id if load else None,
            carrier_id=carrier.id,
            estimated_cost=round(weight * 0.08, 2),
            priority=1 + (i % 5),
            service_level="STANDARD" if i % 4 != 0 else "EXPEDITED",
            current_lat=lat, current_lon=lon,
            last_tracking_update=today if lat else None,
            estimated_arrival=delivery,
            eta_confidence=eta_conf,
            source="DEMO_SEED",
        ))
        created += 1

    session.flush()
    print(f"  Shipments: {created} created, {50 - created} already exist")


# ---------------------------------------------------------------------------
# Dock Appointments
# ---------------------------------------------------------------------------

def seed_appointments(session, tenant_id, config_id):
    created = 0
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

    # Use first 3 sites (shippers)
    shipper_sites = []
    for f in FACILITIES[:3]:
        site = _get_site_by_name(session, config_id, f['name'])
        if site:
            shipper_sites.append(site)

    carriers = session.execute(
        select(Carrier).where(Carrier.tenant_id == tenant_id)
    ).scalars().all()

    shipments = session.execute(
        select(Shipment).where(Shipment.tenant_id == tenant_id)
    ).scalars().all()

    appt_types = [AppointmentType.PICKUP, AppointmentType.DELIVERY,
                  AppointmentType.LIVE_LOAD, AppointmentType.DROP_TRAILER]
    appt_statuses = [
        AppointmentStatus.CONFIRMED, AppointmentStatus.CONFIRMED,
        AppointmentStatus.CHECKED_IN, AppointmentStatus.LOADING,
        AppointmentStatus.COMPLETED, AppointmentStatus.COMPLETED,
        AppointmentStatus.NO_SHOW, AppointmentStatus.CONFIRMED,
    ]

    for i in range(20):
        site = shipper_sites[i % len(shipper_sites)] if shipper_sites else None
        if not site:
            continue

        day_offset = i // 10  # 0 = today, 1 = tomorrow
        hour = 6 + (i % 10) * 1.5
        start = today + timedelta(days=day_offset, hours=hour)
        end = start + timedelta(minutes=60)

        shipment = shipments[i] if i < len(shipments) else None
        carrier = carriers[i % len(carriers)] if carriers else None

        status = appt_statuses[i % len(appt_statuses)]

        # Check existence loosely by site + time
        existing = session.execute(
            select(Appointment).where(
                Appointment.tenant_id == tenant_id,
                Appointment.site_id == site.id,
                Appointment.scheduled_start == start,
            )
        ).scalar_one_or_none()
        if existing:
            continue

        session.add(Appointment(
            tenant_id=tenant_id,
            site_id=site.id,
            shipment_id=shipment.id if shipment else None,
            carrier_id=carrier.id if carrier else None,
            appointment_type=appt_types[i % len(appt_types)],
            status=status,
            scheduled_start=start,
            scheduled_end=end,
            actual_arrival=start - timedelta(minutes=15) if status in (AppointmentStatus.CHECKED_IN, AppointmentStatus.LOADING, AppointmentStatus.COMPLETED) else None,
            actual_start=start if status in (AppointmentStatus.LOADING, AppointmentStatus.COMPLETED) else None,
            actual_end=end if status == AppointmentStatus.COMPLETED else None,
            dwell_time_minutes=75 if status == AppointmentStatus.COMPLETED else None,
            dock_time_minutes=55 if status == AppointmentStatus.COMPLETED else None,
            wait_time_minutes=20 if status == AppointmentStatus.COMPLETED else None,
            driver_name=f"Driver {i+1}",
            trailer_number=f"TRL-{1000+i}",
        ))
        created += 1

    session.flush()
    print(f"  Appointments: {created} created, {20 - created} already exist")


# ---------------------------------------------------------------------------
# Shipment Exceptions
# ---------------------------------------------------------------------------

EXCEPTIONS = [
    {"type": ExceptionType.LATE_DELIVERY, "severity": ExceptionSeverity.HIGH,
     "desc": "Shipment delayed 8 hours due to highway closure on I-40 near Nashville",
     "delay": 8.0, "cost": 1200.0, "lat": 36.16, "lon": -86.78},
    {"type": ExceptionType.LATE_DELIVERY, "severity": ExceptionSeverity.MEDIUM,
     "desc": "Carrier arrived 4 hours past delivery window at New York Retail DC",
     "delay": 4.0, "cost": 450.0, "lat": 40.71, "lon": -74.01},
    {"type": ExceptionType.WEATHER_DELAY, "severity": ExceptionSeverity.HIGH,
     "desc": "Severe thunderstorms in Dallas-Fort Worth area causing widespread delays",
     "delay": 12.0, "cost": 2100.0, "lat": 32.78, "lon": -96.80},
    {"type": ExceptionType.DAMAGE, "severity": ExceptionSeverity.CRITICAL,
     "desc": "Pallet shift during transit — 12 cases of electronics damaged",
     "delay": 0.0, "cost": 5400.0, "lat": 39.95, "lon": -75.17},
    {"type": ExceptionType.TEMPERATURE_EXCURSION, "severity": ExceptionSeverity.HIGH,
     "desc": "Reefer unit malfunction — produce load exceeded 42F for 3 hours",
     "delay": 6.0, "cost": 8200.0, "lat": 35.15, "lon": -90.05},
    {"type": ExceptionType.CUSTOMS_HOLD, "severity": ExceptionSeverity.MEDIUM,
     "desc": "Container held at Long Beach for additional documentation review",
     "delay": 48.0, "cost": 3500.0, "lat": 33.77, "lon": -118.19},
    {"type": ExceptionType.REFUSED, "severity": ExceptionSeverity.CRITICAL,
     "desc": "Consignee refused delivery — shipment arrived outside appointment window",
     "delay": 24.0, "cost": 4100.0, "lat": 33.94, "lon": -118.26},
    {"type": ExceptionType.ROLLED_CONTAINER, "severity": ExceptionSeverity.HIGH,
     "desc": "Container rolled from vessel at Long Beach — next available sailing in 5 days",
     "delay": 120.0, "cost": 6800.0, "lat": 33.77, "lon": -118.19},
]


def seed_exceptions(session, tenant_id, config_id):
    created = 0
    now = datetime.utcnow()

    shipments = session.execute(
        select(Shipment).where(Shipment.tenant_id == tenant_id)
    ).scalars().all()
    if not shipments:
        print("  Exceptions: skipped (no shipments)")
        return

    for i, exc in enumerate(EXCEPTIONS):
        shipment = shipments[i % len(shipments)]

        # Check by shipment + type
        existing = session.execute(
            select(ShipmentException).where(
                ShipmentException.tenant_id == tenant_id,
                ShipmentException.shipment_id == shipment.id,
                ShipmentException.exception_type == exc['type'],
            )
        ).scalar_one_or_none()
        if existing:
            continue

        session.add(ShipmentException(
            tenant_id=tenant_id,
            shipment_id=shipment.id,
            exception_type=exc['type'],
            severity=exc['severity'],
            resolution_status=ExceptionResolutionStatus.DETECTED if i < 4 else ExceptionResolutionStatus.INVESTIGATING,
            description=exc['desc'],
            detected_at=now - timedelta(hours=i * 6),
            estimated_delay_hrs=exc['delay'],
            estimated_cost_impact=exc['cost'],
            detection_source="DEMO_SEED",
            exception_lat=exc['lat'],
            exception_lon=exc['lon'],
        ))
        created += 1

    session.flush()
    print(f"  Exceptions: {created} created, {len(EXCEPTIONS) - created} already exist")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def seed_all(tenant_id: int, config_id: int):
    session = sync_session_factory()
    try:
        print(f"Seeding TMS demo data for tenant_id={tenant_id}, config_id={config_id}")
        seed_commodities(session, tenant_id, config_id)
        seed_facilities(session, tenant_id, config_id)
        seed_carriers(session, tenant_id, config_id)
        seed_lanes(session, tenant_id, config_id)
        seed_rates(session, tenant_id, config_id)
        seed_carrier_lanes(session, tenant_id, config_id)
        seed_loads(session, tenant_id, config_id)
        seed_shipments(session, tenant_id, config_id)
        seed_appointments(session, tenant_id, config_id)
        seed_exceptions(session, tenant_id, config_id)
        session.commit()
        print(f"\nTMS demo data seeded successfully.")
    except Exception as e:
        session.rollback()
        print(f"\nError seeding TMS demo data: {e}")
        raise
    finally:
        session.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Seed TMS demo data for a tenant")
    parser.add_argument('--tenant-id', type=int, default=1, help="Tenant ID")
    parser.add_argument('--config-id', type=int, default=1, help="Supply chain config ID")
    args = parser.parse_args()
    seed_all(args.tenant_id, args.config_id)
