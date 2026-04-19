"""
Global Carrier Seed — Ocean, Air, Intermodal, and International Truck

Supplements the US foodservice carriers (carriers_seed.py) with global
carriers for the SAP S/4HANA demo network (11 countries, manufacturing/
industrial supply chain).

Carrier mix for global industrial:
  - ~8 ocean carriers (container lines)
  - ~6 air freight forwarders
  - ~4 international 3PL/freight forwarders
  - ~6 European road hauliers
  - ~4 Asian logistics providers
  - ~4 container/intermodal specialists
  = ~32 carriers

Usage:
    from app.services.tms.global_carriers_seed import GLOBAL_CARRIERS
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

from .carriers_seed import CarrierSpec


# ------------------------------------------------------------------
# OCEAN CARRIERS (container lines)
# ------------------------------------------------------------------
OCEAN_CARRIERS = [
    CarrierSpec("MAEU", "Maersk Line", "MAEU", "ASSET", "DK",
                ("FCL", "LCL"), ("CONTAINER_40", "CONTAINER_40HC", "REEFER_CONTAINER"),
                approx_fleet_size=700, otd_performance=0.90, avg_linehaul_rate_cpm=0.08,
                service_regions=("GLOBAL",), is_national=True),
    CarrierSpec("MSCU", "MSC (Mediterranean Shipping)", "MSCU", "ASSET", "CH",
                ("FCL", "LCL"), ("CONTAINER_40", "CONTAINER_40HC"),
                approx_fleet_size=800, otd_performance=0.88, avg_linehaul_rate_cpm=0.07,
                service_regions=("GLOBAL",)),
    CarrierSpec("CMAU", "CMA CGM", "CMAU", "ASSET", "FR",
                ("FCL",), ("CONTAINER_40", "CONTAINER_40HC", "REEFER_CONTAINER"),
                approx_fleet_size=600, otd_performance=0.89, avg_linehaul_rate_cpm=0.08,
                service_regions=("GLOBAL",)),
    CarrierSpec("HLCU", "Hapag-Lloyd", "HLCU", "ASSET", "DE",
                ("FCL",), ("CONTAINER_40", "CONTAINER_40HC"),
                approx_fleet_size=250, otd_performance=0.91, avg_linehaul_rate_cpm=0.09,
                service_regions=("GLOBAL",)),
    CarrierSpec("EGLV", "Evergreen Line", "EGLV", "ASSET", "TW",
                ("FCL",), ("CONTAINER_40", "CONTAINER_40HC"),
                approx_fleet_size=200, otd_performance=0.89, avg_linehaul_rate_cpm=0.07,
                service_regions=("ASIA_EUROPE", "TRANSPACIFIC")),
    CarrierSpec("COSU", "COSCO Shipping", "COSU", "ASSET", "CN",
                ("FCL",), ("CONTAINER_40", "CONTAINER_40HC"),
                approx_fleet_size=500, otd_performance=0.87, avg_linehaul_rate_cpm=0.06,
                service_regions=("ASIA_EUROPE", "TRANSPACIFIC")),
    CarrierSpec("ONEY", "ONE (Ocean Network Express)", "ONEY", "ASSET", "JP",
                ("FCL",), ("CONTAINER_40", "CONTAINER_40HC"),
                approx_fleet_size=230, otd_performance=0.90, avg_linehaul_rate_cpm=0.08,
                service_regions=("ASIA_EUROPE", "TRANSPACIFIC")),
    CarrierSpec("YMLU", "Yang Ming Line", "YMLU", "ASSET", "TW",
                ("FCL",), ("CONTAINER_40",),
                approx_fleet_size=100, otd_performance=0.88, avg_linehaul_rate_cpm=0.07,
                service_regions=("ASIA_EUROPE", "TRANSPACIFIC")),
]

# ------------------------------------------------------------------
# AIR FREIGHT FORWARDERS
# ------------------------------------------------------------------
AIR_CARRIERS = [
    CarrierSpec("DHLG", "DHL Global Forwarding", "DHLG", "THREE_PL", "DE",
                ("AIR_STD", "AIR_EXPRESS"), ("CONTAINER_20",),
                approx_fleet_size=0, otd_performance=0.94, avg_linehaul_rate_cpm=8.50,
                service_regions=("GLOBAL",), is_asset=False),
    CarrierSpec("KNAG", "Kuehne+Nagel", "KNAG", "THREE_PL", "CH",
                ("AIR_STD", "AIR_EXPRESS", "FCL"), ("CONTAINER_40",),
                approx_fleet_size=0, otd_performance=0.93, avg_linehaul_rate_cpm=8.00,
                service_regions=("GLOBAL",), is_asset=False),
    CarrierSpec("DBSC", "DB Schenker", "DBSC", "THREE_PL", "DE",
                ("AIR_STD", "RAIL_INTERMODAL", "FCL"), ("CONTAINER_40",),
                approx_fleet_size=0, otd_performance=0.92, avg_linehaul_rate_cpm=7.50,
                service_regions=("EUROPE", "ASIA_EUROPE"), is_asset=False),
    CarrierSpec("EXPD", "Expeditors International", "EXPD", "THREE_PL", "US",
                ("AIR_STD", "FCL"), ("CONTAINER_40",),
                approx_fleet_size=0, otd_performance=0.93, avg_linehaul_rate_cpm=8.20,
                service_regions=("GLOBAL",), is_asset=False),
    CarrierSpec("DSVM", "DSV Panalpina", "DSVM", "THREE_PL", "DK",
                ("AIR_STD", "FCL", "FTL"), ("CONTAINER_40", "DRY_VAN"),
                approx_fleet_size=0, otd_performance=0.91, avg_linehaul_rate_cpm=7.80,
                service_regions=("GLOBAL",), is_asset=False),
    CarrierSpec("UPSF", "UPS Supply Chain Solutions", "UPSF", "THREE_PL", "US",
                ("AIR_EXPRESS", "PARCEL"), ("CONTAINER_20",),
                approx_fleet_size=0, otd_performance=0.96, avg_linehaul_rate_cpm=12.00,
                service_regions=("GLOBAL",), is_asset=False),
]

# ------------------------------------------------------------------
# EUROPEAN ROAD HAULIERS
# ------------------------------------------------------------------
EUROPEAN_ROAD = [
    CarrierSpec("GIRT", "Girteka Logistics", "GIRT", "ASSET", "LT",
                ("FTL",), ("DRY_VAN", "FLATBED"),
                approx_fleet_size=9000, otd_performance=0.92, avg_linehaul_rate_cpm=1.80,
                service_regions=("EUROPE",), is_national=False),
    CarrierSpec("WABR", "Waberer's International", "WABR", "ASSET", "HU",
                ("FTL",), ("DRY_VAN",),
                approx_fleet_size=4500, otd_performance=0.91, avg_linehaul_rate_cpm=1.70,
                service_regions=("EUROPE",), is_national=False),
    CarrierSpec("RHNS", "Rhenus Logistics", "RHNS", "THREE_PL", "DE",
                ("FTL", "LTL"), ("DRY_VAN", "FLATBED"),
                approx_fleet_size=0, otd_performance=0.93, avg_linehaul_rate_cpm=2.10,
                service_regions=("EUROPE",), is_asset=False),
    CarrierSpec("DACH", "Dachser", "DACH", "THREE_PL", "DE",
                ("FTL", "LTL", "AIR_STD"), ("DRY_VAN",),
                approx_fleet_size=0, otd_performance=0.94, avg_linehaul_rate_cpm=2.20,
                service_regions=("EUROPE",), is_asset=False),
    CarrierSpec("GEOD", "Geodis", "GEOD", "THREE_PL", "FR",
                ("FTL", "LTL", "FCL"), ("DRY_VAN", "CONTAINER_40"),
                approx_fleet_size=0, otd_performance=0.92, avg_linehaul_rate_cpm=2.00,
                service_regions=("EUROPE", "GLOBAL"), is_asset=False),
    CarrierSpec("XPOE", "XPO Logistics Europe", "XPOE", "THREE_PL", "FR",
                ("FTL", "LTL"), ("DRY_VAN", "FLATBED"),
                approx_fleet_size=0, otd_performance=0.93, avg_linehaul_rate_cpm=2.15,
                service_regions=("EUROPE",), is_asset=False),
]

# ------------------------------------------------------------------
# ASIAN LOGISTICS PROVIDERS
# ------------------------------------------------------------------
ASIAN_CARRIERS = [
    CarrierSpec("NIPX", "Nippon Express", "NIPX", "THREE_PL", "JP",
                ("AIR_STD", "FCL", "FTL"), ("CONTAINER_40", "DRY_VAN"),
                approx_fleet_size=0, otd_performance=0.94, avg_linehaul_rate_cpm=3.50,
                service_regions=("ASIA",), is_asset=False),
    CarrierSpec("SINO", "Sinotrans", "SINO", "THREE_PL", "CN",
                ("FCL", "FTL"), ("CONTAINER_40", "DRY_VAN"),
                approx_fleet_size=0, otd_performance=0.88, avg_linehaul_rate_cpm=1.50,
                service_regions=("ASIA", "ASIA_EUROPE"), is_asset=False),
    CarrierSpec("KERY", "Kerry Logistics", "KERY", "THREE_PL", "HK",
                ("AIR_STD", "FCL"), ("CONTAINER_40",),
                approx_fleet_size=0, otd_performance=0.91, avg_linehaul_rate_cpm=3.00,
                service_regions=("ASIA", "GLOBAL"), is_asset=False),
    CarrierSpec("YUND", "YunDa Express", "YUND", "ASSET", "CN",
                ("PARCEL", "LTL"), ("BOX_TRUCK",),
                approx_fleet_size=30000, otd_performance=0.85, avg_linehaul_rate_cpm=0.80,
                service_regions=("ASIA",), is_national=False),
]

# ------------------------------------------------------------------
# CONTAINER / INTERMODAL SPECIALISTS
# ------------------------------------------------------------------
CONTAINER_SPECIALISTS = [
    CarrierSpec("TRIT", "Triton International", "TRIT", "ASSET", "US",
                ("INTERMODAL",), ("CONTAINER_20", "CONTAINER_40", "CONTAINER_40HC"),
                approx_fleet_size=6000000, otd_performance=0.90, avg_linehaul_rate_cpm=0.05,
                service_regions=("GLOBAL",), typical_acceptance_rate=0.95),
    CarrierSpec("BNSF", "BNSF Railway", "BNSF", "ASSET", "US",
                ("RAIL_INTERMODAL", "RAIL_CARLOAD"), ("CONTAINER_45", "RAILCAR_BOX"),
                approx_fleet_size=8000, otd_performance=0.88, avg_linehaul_rate_cpm=0.04,
                service_regions=("US_DOMESTIC",)),
    CarrierSpec("DBCG", "DB Cargo", "DBCG", "ASSET", "DE",
                ("RAIL_INTERMODAL", "RAIL_CARLOAD"), ("CONTAINER_40", "RAILCAR_BOX"),
                approx_fleet_size=4200, otd_performance=0.85, avg_linehaul_rate_cpm=0.05,
                service_regions=("EUROPE",)),
    CarrierSpec("HUPK", "Hupac Intermodal", "HUPK", "ASSET", "CH",
                ("RAIL_INTERMODAL",), ("CONTAINER_40", "CONTAINER_40HC"),
                approx_fleet_size=130, otd_performance=0.90, avg_linehaul_rate_cpm=0.04,
                service_regions=("EUROPE",)),
]


# ============================================================================
# Composite List
# ============================================================================

GLOBAL_CARRIERS: List[CarrierSpec] = (
    OCEAN_CARRIERS
    + AIR_CARRIERS
    + EUROPEAN_ROAD
    + ASIAN_CARRIERS
    + CONTAINER_SPECIALISTS
)


def ocean_carriers() -> List[CarrierSpec]:
    return [c for c in GLOBAL_CARRIERS if any(m in c.modes for m in ("FCL", "LCL"))]


def air_carriers() -> List[CarrierSpec]:
    return [c for c in GLOBAL_CARRIERS if any(m in c.modes for m in ("AIR_STD", "AIR_EXPRESS"))]


def european_road_carriers() -> List[CarrierSpec]:
    return [c for c in GLOBAL_CARRIERS if "EUROPE" in c.service_regions or "EU" in c.hq_state]
