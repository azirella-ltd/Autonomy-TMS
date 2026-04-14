"""
Top ~50 US Foodservice / Refrigerated Carriers — Static Seed Dataset

Curated list representative of the US carrier market serving foodservice
distribution, structured to match Food Dist's UT-hub network (reefer-heavy
outbound to West Coast, dry/reefer inbound from Central/NE/SE).

Fields are grounded in publicly known carrier attributes (SCAC, HQ state,
approximate fleet size bracket, primary mode mix, equipment specialty).
Numbers marked ~approximate~ are realistic market-shape estimates, not
scraped from carrier filings — this is training data, not a directory.

Carrier mix target for Food Dist:
  - ~12 reefer asset carriers (national + regional)
  - ~10 dry-van asset carriers (national + regional)
  - ~8 LTL carriers (national + regional)
  - ~6 brokers (asset-light)
  - ~4 intermodal marketing companies (IMCs)
  - ~6 small/regional specialists (temperature + final-mile food)
  = ~46 carriers (within "top 50" target)

Usage:
    from app.services.tms.carriers_seed import TOP_FOODSERVICE_CARRIERS

    for spec in TOP_FOODSERVICE_CARRIERS:
        # build Carrier ORM row
        ...
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass(frozen=True)
class CarrierSpec:
    # Identity
    code: str                    # Internal code (SCAC if asset carrier)
    name: str
    scac: str                    # Standard Carrier Alpha Code
    carrier_type: str            # ASSET, BROKER, IMC, LTL, REGIONAL (matches CarrierType enum)
    hq_state: str                # Two-letter US state

    # Capabilities
    modes: Tuple[str, ...]       # TMS TransportMode enum values
    equipment_types: Tuple[str, ...]  # TMS EquipmentType enum values
    is_reefer_specialist: bool = False
    is_hazmat_certified: bool = False

    # Market shape (synthetic training knobs)
    approx_fleet_size: int = 500     # Tractors (brokers: managed loads/yr approx)
    service_regions: Tuple[str, ...] = ("US_DOMESTIC",)
    typical_acceptance_rate: float = 0.85   # Tender acceptance, used in waterfall sim
    otd_performance: float = 0.93           # On-time delivery baseline
    avg_linehaul_rate_cpm: float = 2.30     # $/mile dry van baseline (reefer gets +25%)
    insurance_limit: float = 1_000_000.0

    # Asset class flags
    is_national: bool = True         # vs regional
    is_asset: bool = True            # vs broker


# ------------------------------------------------------------------
# REEFER ASSET CARRIERS (national & super-regional)
# ------------------------------------------------------------------
REEFER_ASSET = [
    CarrierSpec("CRST", "CRST The Transportation Solution", "CRST", "ASSET", "IA",
                ("FTL",), ("DRY_VAN", "REEFER"), is_reefer_specialist=False,
                approx_fleet_size=4500, otd_performance=0.94, avg_linehaul_rate_cpm=2.35),
    CarrierSpec("PRME", "Prime Inc.", "PRME", "ASSET", "MO",
                ("FTL",), ("REEFER", "DRY_VAN", "TANKER"), is_reefer_specialist=True,
                approx_fleet_size=8500, otd_performance=0.95, avg_linehaul_rate_cpm=2.55),
    CarrierSpec("CTII", "C.R. England", "CTII", "ASSET", "UT",
                ("FTL",), ("REEFER",), is_reefer_specialist=True,
                approx_fleet_size=4200, otd_performance=0.93, avg_linehaul_rate_cpm=2.50,
                typical_acceptance_rate=0.90),  # UT-based, high acceptance on UT lanes
    CarrierSpec("STTK", "Stevens Transport", "STTK", "ASSET", "TX",
                ("FTL", "INTERMODAL"), ("REEFER",), is_reefer_specialist=True,
                approx_fleet_size=3600, otd_performance=0.92, avg_linehaul_rate_cpm=2.52),
    CarrierSpec("KLLM", "KLLM Transport Services", "KLLM", "ASSET", "MS",
                ("FTL",), ("REEFER",), is_reefer_specialist=True,
                approx_fleet_size=1400, otd_performance=0.91, avg_linehaul_rate_cpm=2.48),
    CarrierSpec("MRTN", "Marten Transport", "MRTN", "ASSET", "WI",
                ("FTL", "INTERMODAL"), ("REEFER", "DRY_VAN"), is_reefer_specialist=True,
                approx_fleet_size=3200, otd_performance=0.94, avg_linehaul_rate_cpm=2.52),
    CarrierSpec("HNTB", "Hunt Transport (reefer div.)", "HNTB", "ASSET", "AR",
                ("FTL", "INTERMODAL"), ("REEFER",), is_reefer_specialist=True,
                approx_fleet_size=2800, otd_performance=0.93, avg_linehaul_rate_cpm=2.50),
    CarrierSpec("BTCY", "Bay & Bay Transportation", "BTCY", "ASSET", "MN",
                ("FTL",), ("REEFER",), is_reefer_specialist=True,
                approx_fleet_size=800, otd_performance=0.92, avg_linehaul_rate_cpm=2.55,
                is_national=False),
    CarrierSpec("NUTN", "Nussbaum Transportation", "NUTN", "ASSET", "IL",
                ("FTL",), ("DRY_VAN", "REEFER"), is_reefer_specialist=False,
                approx_fleet_size=600, otd_performance=0.95, avg_linehaul_rate_cpm=2.45,
                is_national=False),
    CarrierSpec("WEYN", "Wel Companies", "WEYN", "ASSET", "WI",
                ("FTL",), ("REEFER",), is_reefer_specialist=True,
                approx_fleet_size=450, otd_performance=0.92, avg_linehaul_rate_cpm=2.50,
                is_national=False),
    CarrierSpec("WRNT", "Werner Enterprises (reefer)", "WRNT", "ASSET", "NE",
                ("FTL",), ("REEFER", "DRY_VAN"), is_reefer_specialist=False,
                approx_fleet_size=7800, otd_performance=0.94, avg_linehaul_rate_cpm=2.40),
    CarrierSpec("TNTL", "Trinity Logistics (reefer)", "TNTL", "ASSET", "DE",
                ("FTL",), ("REEFER",), is_reefer_specialist=True,
                approx_fleet_size=350, otd_performance=0.90, avg_linehaul_rate_cpm=2.55,
                is_national=False),
]

# ------------------------------------------------------------------
# DRY VAN ASSET CARRIERS
# ------------------------------------------------------------------
DRY_VAN_ASSET = [
    CarrierSpec("SCNN", "Schneider National", "SCNN", "ASSET", "WI",
                ("FTL", "INTERMODAL"), ("DRY_VAN",),
                approx_fleet_size=11500, otd_performance=0.95, avg_linehaul_rate_cpm=2.30),
    CarrierSpec("SWFT", "Swift Transportation (Knight-Swift)", "SWFT", "ASSET", "AZ",
                ("FTL",), ("DRY_VAN", "REEFER"),
                approx_fleet_size=18000, otd_performance=0.93, avg_linehaul_rate_cpm=2.25),
    CarrierSpec("KNGT", "Knight Transportation", "KNGT", "ASSET", "AZ",
                ("FTL",), ("DRY_VAN",),
                approx_fleet_size=6500, otd_performance=0.94, avg_linehaul_rate_cpm=2.32),
    CarrierSpec("USXI", "U.S. Xpress", "USXI", "ASSET", "TN",
                ("FTL",), ("DRY_VAN",),
                approx_fleet_size=7200, otd_performance=0.91, avg_linehaul_rate_cpm=2.28),
    CarrierSpec("HRTJ", "Heartland Express", "HRTJ", "ASSET", "IA",
                ("FTL",), ("DRY_VAN",),
                approx_fleet_size=5800, otd_performance=0.95, avg_linehaul_rate_cpm=2.35),
    CarrierSpec("CVTI", "Covenant Logistics", "CVTI", "ASSET", "TN",
                ("FTL",), ("DRY_VAN", "REEFER"),
                approx_fleet_size=2600, otd_performance=0.93, avg_linehaul_rate_cpm=2.32),
    CarrierSpec("USAK", "USA Truck", "USAK", "ASSET", "AR",
                ("FTL",), ("DRY_VAN",),
                approx_fleet_size=1800, otd_performance=0.91, avg_linehaul_rate_cpm=2.26),
    CarrierSpec("PAMT", "PAM Transport", "PAMT", "ASSET", "AR",
                ("FTL",), ("DRY_VAN",),
                approx_fleet_size=1900, otd_performance=0.92, avg_linehaul_rate_cpm=2.28),
    CarrierSpec("CTGS", "Cargo Transporters", "CTGS", "ASSET", "NC",
                ("FTL",), ("DRY_VAN",),
                approx_fleet_size=550, otd_performance=0.94, avg_linehaul_rate_cpm=2.30,
                is_national=False),
    CarrierSpec("WIHS", "Western Flyer Xpress", "WIHS", "ASSET", "OK",
                ("FTL",), ("DRY_VAN", "FLATBED"),
                approx_fleet_size=900, otd_performance=0.92, avg_linehaul_rate_cpm=2.27,
                is_national=False),
]

# ------------------------------------------------------------------
# LTL CARRIERS (foodservice LTL + national LTL)
# ------------------------------------------------------------------
LTL_CARRIERS = [
    CarrierSpec("ODFL", "Old Dominion Freight Line", "ODFL", "ASSET", "NC",
                ("ASSET",), ("DRY_VAN",),
                approx_fleet_size=10500, otd_performance=0.98, avg_linehaul_rate_cpm=3.80,
                typical_acceptance_rate=0.92),
    CarrierSpec("SEFL", "Southeastern Freight Lines", "SEFL", "ASSET", "SC",
                ("ASSET",), ("DRY_VAN",),
                approx_fleet_size=3200, otd_performance=0.97, avg_linehaul_rate_cpm=3.65),
    CarrierSpec("ABFS", "ABF Freight", "ABFS", "ASSET", "AR",
                ("ASSET",), ("DRY_VAN",),
                approx_fleet_size=4800, otd_performance=0.95, avg_linehaul_rate_cpm=3.70),
    CarrierSpec("RLCA", "R+L Carriers", "RLCA", "ASSET", "OH",
                ("ASSET",), ("DRY_VAN",),
                approx_fleet_size=5200, otd_performance=0.94, avg_linehaul_rate_cpm=3.55),
    CarrierSpec("SAIA", "Saia LTL Freight", "SAIA", "ASSET", "GA",
                ("ASSET",), ("DRY_VAN",),
                approx_fleet_size=5600, otd_performance=0.96, avg_linehaul_rate_cpm=3.60),
    CarrierSpec("EXLA", "Estes Express Lines", "EXLA", "ASSET", "VA",
                ("ASSET",), ("DRY_VAN",),
                approx_fleet_size=8500, otd_performance=0.95, avg_linehaul_rate_cpm=3.60),
    CarrierSpec("CRST", "Central Transport", "CTII", "ASSET", "MI",
                ("ASSET",), ("DRY_VAN",),
                approx_fleet_size=4200, otd_performance=0.92, avg_linehaul_rate_cpm=3.45),
    CarrierSpec("FCSY", "FedEx Freight", "FXFE", "ASSET", "TN",
                ("ASSET",), ("DRY_VAN",),
                approx_fleet_size=14000, otd_performance=0.95, avg_linehaul_rate_cpm=3.75),
]

# ------------------------------------------------------------------
# BROKERS (asset-light)
# ------------------------------------------------------------------
BROKERS = [
    CarrierSpec("CHRW", "C.H. Robinson", "CHRW", "BROKER", "MN",
                ("FTL", "ASSET", "INTERMODAL"), ("DRY_VAN", "REEFER"),
                approx_fleet_size=0, otd_performance=0.90, avg_linehaul_rate_cpm=2.45,
                typical_acceptance_rate=0.75, is_asset=False),
    CarrierSpec("TQLI", "Total Quality Logistics", "TQLI", "BROKER", "OH",
                ("FTL", "ASSET"), ("DRY_VAN", "REEFER"),
                approx_fleet_size=0, otd_performance=0.89, avg_linehaul_rate_cpm=2.48,
                typical_acceptance_rate=0.72, is_asset=False),
    CarrierSpec("XPOB", "RXO (XPO spinoff)", "RXOB", "BROKER", "CT",
                ("FTL", "INTERMODAL"), ("DRY_VAN", "REEFER"),
                approx_fleet_size=0, otd_performance=0.90, avg_linehaul_rate_cpm=2.44,
                typical_acceptance_rate=0.76, is_asset=False),
    CarrierSpec("CODA", "Coyote Logistics", "CODA", "BROKER", "IL",
                ("FTL",), ("DRY_VAN", "REEFER"),
                approx_fleet_size=0, otd_performance=0.89, avg_linehaul_rate_cpm=2.47,
                typical_acceptance_rate=0.74, is_asset=False),
    CarrierSpec("ECHO", "Echo Global Logistics", "ECHO", "BROKER", "IL",
                ("FTL", "ASSET"), ("DRY_VAN", "REEFER"),
                approx_fleet_size=0, otd_performance=0.88, avg_linehaul_rate_cpm=2.46,
                typical_acceptance_rate=0.72, is_asset=False),
    CarrierSpec("UBER", "Uber Freight", "UBER", "BROKER", "IL",
                ("FTL",), ("DRY_VAN", "REEFER"),
                approx_fleet_size=0, otd_performance=0.87, avg_linehaul_rate_cpm=2.50,
                typical_acceptance_rate=0.70, is_asset=False),
]

# ------------------------------------------------------------------
# INTERMODAL MARKETING COMPANIES (rail)
# ------------------------------------------------------------------
IMC_CARRIERS = [
    CarrierSpec("JBHT", "J.B. Hunt Intermodal", "JBHT", "THREE_PL", "AR",
                ("INTERMODAL", "RAIL_INTERMODAL", "DRAYAGE"),
                ("CONTAINER_53", "REEFER_CONTAINER"),
                approx_fleet_size=100000, otd_performance=0.91, avg_linehaul_rate_cpm=1.80,
                typical_acceptance_rate=0.88),
    CarrierSpec("SCHN", "Schneider Intermodal", "SCNN", "THREE_PL", "WI",
                ("INTERMODAL", "RAIL_INTERMODAL"),
                ("CONTAINER_53",),
                approx_fleet_size=25000, otd_performance=0.90, avg_linehaul_rate_cpm=1.85),
    CarrierSpec("HUBG", "Hub Group", "HUBG", "THREE_PL", "IL",
                ("INTERMODAL", "RAIL_INTERMODAL", "DRAYAGE"),
                ("CONTAINER_53", "REEFER_CONTAINER"),
                approx_fleet_size=40000, otd_performance=0.90, avg_linehaul_rate_cpm=1.82),
    CarrierSpec("STGC", "STG Logistics", "STGC", "THREE_PL", "IL",
                ("INTERMODAL", "DRAYAGE"),
                ("CONTAINER_40", "CONTAINER_53"),
                approx_fleet_size=15000, otd_performance=0.88, avg_linehaul_rate_cpm=1.88,
                is_asset=False),
]

# ------------------------------------------------------------------
# REGIONAL / SPECIALIST CARRIERS (reefer + final-mile food)
# ------------------------------------------------------------------
REGIONAL_SPECIALISTS = [
    CarrierSpec("TRMC", "Transco Lines (reefer)", "TRMC", "ASSET", "AR",
                ("FTL",), ("REEFER",), is_reefer_specialist=True,
                approx_fleet_size=300, otd_performance=0.93, avg_linehaul_rate_cpm=2.55,
                is_national=False, service_regions=("US_CENTRAL", "US_SOUTH")),
    CarrierSpec("CAAA", "Cheeseman Transport", "CAAA", "ASSET", "IN",
                ("FTL",), ("REEFER",), is_reefer_specialist=True,
                approx_fleet_size=250, otd_performance=0.92, avg_linehaul_rate_cpm=2.52,
                is_national=False),
    CarrierSpec("DCTR", "Decker Truck Line", "DCTR", "ASSET", "IA",
                ("FTL",), ("REEFER", "DRY_VAN"),
                approx_fleet_size=700, otd_performance=0.93, avg_linehaul_rate_cpm=2.45,
                is_national=False, service_regions=("US_CENTRAL", "US_WEST")),
    CarrierSpec("MCER", "McElroy Truck Lines", "MCER", "ASSET", "AL",
                ("FTL",), ("REEFER",), is_reefer_specialist=True,
                approx_fleet_size=450, otd_performance=0.92, avg_linehaul_rate_cpm=2.50,
                is_national=False, service_regions=("US_SOUTHEAST",)),
    CarrierSpec("WRDT", "Western Distributing Transportation", "WRDT", "ASSET", "CO",
                ("FTL",), ("REEFER", "DRY_VAN"),
                approx_fleet_size=400, otd_performance=0.92, avg_linehaul_rate_cpm=2.48,
                is_national=False, service_regions=("US_WEST", "US_MOUNTAIN"),
                typical_acceptance_rate=0.88),  # Strong on UT-CA lanes
    CarrierSpec("TRSM", "TransAm Trucking", "TRSM", "ASSET", "KS",
                ("FTL",), ("REEFER",), is_reefer_specialist=True,
                approx_fleet_size=900, otd_performance=0.93, avg_linehaul_rate_cpm=2.50,
                is_national=False),
]


# ============================================================================
# Composite List — pass to the seed loader
# ============================================================================

TOP_FOODSERVICE_CARRIERS: List[CarrierSpec] = (
    REEFER_ASSET
    + DRY_VAN_ASSET
    + LTL_CARRIERS
    + BROKERS
    + IMC_CARRIERS
    + REGIONAL_SPECIALISTS
)


def carriers_by_type(carrier_type: str) -> List[CarrierSpec]:
    """Filter seed carriers by type for waterfall construction."""
    return [c for c in TOP_FOODSERVICE_CARRIERS if c.carrier_type == carrier_type]


def reefer_carriers() -> List[CarrierSpec]:
    """Carriers capable of moving frozen/refrigerated freight."""
    return [c for c in TOP_FOODSERVICE_CARRIERS
            if "REEFER" in c.equipment_types or "REEFER_CONTAINER" in c.equipment_types]


def dry_van_carriers() -> List[CarrierSpec]:
    return [c for c in TOP_FOODSERVICE_CARRIERS if "DRY_VAN" in c.equipment_types]


def ut_hub_preferred() -> List[CarrierSpec]:
    """Carriers with elevated UT-centric acceptance (Food Dist DC is in UT)."""
    return [c for c in TOP_FOODSERVICE_CARRIERS
            if c.hq_state in ("UT", "CO", "AZ", "ID", "WY")
            or c.typical_acceptance_rate >= 0.88]
