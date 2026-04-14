"""
Food Dist TMS Overlay Generator

Reads the SCP Food Dist tenant's existing Shipment / OutboundOrder /
InboundOrder history (3 years, ~daily) and synthesizes a full TMS
operational layer on top: carriers, carrier lanes, rates, equipment fleet,
loads, tender waterfalls, tracking events, dock appointments, exceptions,
and empty equipment repositioning moves.

The output writes into TMS tables only — source SCP rows are read-only.

Produces training-grade data for all 11 TMS TRM behavioral-cloning runs:
  CapacityPromiseState ← lane/date capacity snapshot
  ShipmentTrackingState ← tracking events + ETA drift
  DemandSensingState ← rolling lane volumes + forecast bias
  CapacityBufferState ← tender reject rate + demand CV rollups
  ExceptionManagementState ← ShipmentException rows
  FreightProcurementState ← FreightTender waterfall
  BrokerRoutingState ← broker tender paths
  DockSchedulingState ← Appointment + dock queue
  LoadBuildState ← Load + LoadItem (consolidation decisions)
  IntermodalTransferState ← ShipmentLeg mode-change legs
  EquipmentRepositionState ← EquipmentMove rows

Usage:
    generator = FoodDistTMSOverlay(sync_session, tms_tenant_id, sc_config_id)
    generator.seed_carrier_network()              # one-shot setup
    generator.generate_day(date(2023, 6, 15))     # or:
    generator.generate_range(start, end)          # multi-day
"""
from __future__ import annotations

import logging
import math
import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

from sqlalchemy import and_, func, select, text
from sqlalchemy.orm import Session

from app.models.tms_entities import (
    Carrier, CarrierLane, CarrierType, Equipment, EquipmentType,
    EquipmentMove, EquipmentMoveReason, EquipmentMoveStatus,
    Load, LoadItem, LoadStatus,
    FreightRate, RateType,
    FreightTender, TenderStatus,
    Shipment as TmsShipment, ShipmentStatus, ShipmentLeg,
    TransportMode,
    Appointment, AppointmentType, AppointmentStatus, DockDoor,
    ShipmentException, ExceptionType, ExceptionSeverity,
    ExceptionResolutionStatus,
    TrackingEvent, TrackingEventType,
)

# SCP source data is read from `tms_src_scp_*` staging tables, populated by
# scripts/extract_scp_food_dist.py. We use Core-level SQL (text/RowMapping)
# rather than ORM models so the overlay doesn't need SCP's mappers in scope.
from .scp_etl import (
    tms_src_scp_site,
    tms_src_scp_lane,
    tms_src_scp_shipment,
    tms_src_scp_product,
)

# Local TMS Site / TransportationLane (canonical re-export)
from app.models.supply_chain_config import (
    Site as TmsSite,
    TransportationLane as TmsLane,
    SupplyChainConfig as TmsSCConfig,
)


@dataclass
class ScpShipmentRow:
    """Minimal duck-typed view of an SCP shipment row read from staging.

    Exposes the same attribute names the rest of the overlay used to access
    on the ORM Shipment so downstream code (load building, tendering,
    tracking, exception injection) is unchanged.
    """
    id: str
    order_id: Optional[str]
    product_id: Optional[str]
    quantity: Optional[float]
    from_site_id: int   # TMS-side site id (translated from SCP id)
    to_site_id: int
    ship_date: Optional[datetime]
    expected_delivery_date: Optional[datetime]

from .carriers_seed import (
    CarrierSpec, TOP_FOODSERVICE_CARRIERS,
    reefer_carriers, dry_van_carriers, ut_hub_preferred,
)
from .freight_rate_model import (
    MarketRegime, market_regime, quote_rate, seasonal_multiplier,
    tender_reject_probability,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Geography helpers — map US state codes to regional buckets used by rate model
# ============================================================================

_STATE_TO_REGION: Dict[str, str] = {
    # Mountain (Food Dist DC in UT)
    "UT": "US_MOUNTAIN", "CO": "US_MOUNTAIN", "WY": "US_MOUNTAIN",
    "ID": "US_MOUNTAIN", "MT": "US_MOUNTAIN", "NV": "US_MOUNTAIN",
    # Southwest
    "AZ": "US_SOUTHWEST", "NM": "US_SOUTHWEST", "TX": "US_SOUTH",
    "OK": "US_SOUTH", "AR": "US_SOUTH", "LA": "US_SOUTH",
    # West Coast
    "CA": "US_WEST",
    # Northwest
    "OR": "US_NORTHWEST", "WA": "US_NORTHWEST",
    # Central
    "IL": "US_CENTRAL", "IN": "US_CENTRAL", "IA": "US_CENTRAL",
    "MN": "US_CENTRAL", "MO": "US_CENTRAL", "WI": "US_CENTRAL",
    "KS": "US_CENTRAL", "NE": "US_CENTRAL", "OH": "US_CENTRAL",
    "MI": "US_CENTRAL",
    # Southeast
    "GA": "US_SOUTHEAST", "AL": "US_SOUTHEAST", "MS": "US_SOUTHEAST",
    "TN": "US_SOUTHEAST", "FL": "US_SOUTHEAST", "NC": "US_SOUTHEAST",
    "SC": "US_SOUTHEAST",
    # Northeast
    "PA": "US_NORTHEAST", "NY": "US_NORTHEAST", "NJ": "US_NORTHEAST",
    "CT": "US_NORTHEAST", "MA": "US_NORTHEAST", "VA": "US_NORTHEAST",
    "DE": "US_NORTHEAST",
}


def region_for_state(state: Optional[str]) -> str:
    if not state:
        return "US_CENTRAL"
    return _STATE_TO_REGION.get(state.upper(), "US_CENTRAL")


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles — used when Site has lat/lon."""
    if None in (lat1, lon1, lat2, lon2):
        return 500.0  # Conservative default
    r = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a)) * 1.17  # 1.17 = road-vs-crow-fly fudge


# ============================================================================
# Temperature classification — Food Dist has frozen/refrigerated/dry
# ============================================================================

def equipment_for_temperature(temp_category: Optional[str]) -> str:
    """Pick equipment type from Food Dist product temperature category."""
    if not temp_category:
        return "DRY_VAN"
    t = temp_category.lower()
    if t in ("frozen", "refrigerated", "reefer"):
        return "REEFER"
    return "DRY_VAN"


# ============================================================================
# Configuration knobs
# ============================================================================

@dataclass
class OverlayConfig:
    # Network scale
    equipment_per_carrier_tractor_ratio: float = 2.5   # Trailers per tractor
    reefer_fleet_at_ut_dc: int = 40                    # Reefer trailers parked at UT DC
    dry_fleet_at_ut_dc: int = 20

    # Load building
    ftl_weight_threshold_lbs: float = 26000.0          # ≥ this → FTL; else pool
    ltl_pooling_window_hours: int = 24                 # Same-day same-lane pooling

    # Tender waterfall
    max_tender_attempts: int = 4
    primary_acceptance_floor: float = 0.70             # Below this, cascade to backup

    # Tracking
    truck_tracking_frequency_hours: float = 2.0
    eta_drift_stddev_hours: float = 1.5

    # Exceptions
    exception_base_rate: float = 0.04                  # 4% of shipments
    late_delivery_fraction: float = 0.60               # Most exceptions are late
    temp_excursion_rate_reefer: float = 0.005          # 0.5% of reefer shipments

    # Reposition
    reposition_frequency_days: int = 3                 # Check every N days
    reposition_cost_per_mile: float = 1.85             # Deadhead rate

    # Reproducibility
    random_seed: int = 20260414


# ============================================================================
# Overlay Generator
# ============================================================================

class FoodDistTMSOverlay:
    """
    Reads SCP Food Dist tenant source data, writes synthesized TMS rows.

    All writes are tenant-scoped to `tms_tenant_id` so the source tenant is
    untouched. `sc_config_id` points at the Food Dist supply chain config
    so we can read its sites/lanes/shipments.
    """

    def __init__(
        self,
        session: Session,
        tms_tenant_id: int,
        sc_config_id: int,
        *,
        source_tenant_id: Optional[int] = None,
        config: Optional[OverlayConfig] = None,
    ):
        self.session = session
        self.tms_tenant_id = tms_tenant_id
        self.sc_config_id = sc_config_id
        self.source_tenant_id = source_tenant_id or tms_tenant_id
        self.cfg = config or OverlayConfig()
        self.rng = random.Random(self.cfg.random_seed)

        # Lazily loaded network caches
        self._sites_by_id: Dict[int, TmsSite] = {}        # TMS-side site id → row
        self._lanes: List[TmsLane] = []                    # TMS-side lanes
        self._carriers: List[Carrier] = []
        self._carrier_lanes: Dict[Tuple[int, int], List[CarrierLane]] = {}  # (lane_id, equipment_enum_idx)
        self._equipment_pool: List[Equipment] = []
        self._scp_to_tms_site: Dict[int, int] = {}        # SCP site id → TMS site id
        self._tms_food_dist_config_id: Optional[int] = None

    # -----------------------------------------------------------------
    # Phase 1 — one-shot seeding of carriers, lanes, equipment, rates
    # -----------------------------------------------------------------

    def seed_carrier_network(self) -> None:
        """
        Idempotent: creates Carrier rows, CarrierLane coverage, Equipment
        fleet, and baseline FreightRate cards for the Food Dist network.
        """
        self._load_network()
        self._seed_carriers()
        self._seed_equipment_fleet()
        self._seed_carrier_lanes()
        self._seed_freight_rates()
        self.session.commit()
        logger.info(
            "Food Dist TMS overlay seeded: %d carriers, %d equipment, %d lanes",
            len(self._carriers), len(self._equipment_pool), len(self._lanes),
        )

    def _load_network(self) -> None:
        """
        Materialize SCP Food Dist network (sites + lanes) from staging into
        TMS-side `site` / `transportation_lane` tables, scoped to a dedicated
        TMS SC config "Food Dist (from SCP)" under the LEARNING tenant.

        Builds `self._scp_to_tms_site` mapping so shipment rows from staging
        can be translated to TMS site ids before being consumed by the
        downstream overlay logic.

        Idempotent: re-running picks up existing rows by name.
        """
        # Step 1 — find or create the TMS-side Food Dist SC config
        tms_cfg = self.session.execute(
            select(TmsSCConfig).where(
                and_(
                    TmsSCConfig.tenant_id == self.tms_tenant_id,
                    TmsSCConfig.name == "Food Dist (from SCP)",
                )
            )
        ).scalar_one_or_none()
        if tms_cfg is None:
            tms_cfg = TmsSCConfig(
                name="Food Dist (from SCP)",
                tenant_id=self.tms_tenant_id,
            )
            self.session.add(tms_cfg)
            self.session.flush()
        self._tms_food_dist_config_id = tms_cfg.id
        # Override sc_config_id so all downstream writes are scoped here
        self.sc_config_id = tms_cfg.id

        # Step 2 — materialize sites
        scp_sites = self.session.execute(
            text("""
                SELECT scp_site_id, name, type, master_type,
                       latitude, longitude, attributes
                FROM tms_src_scp_site
            """)
        ).mappings().all()

        existing_tms_sites = self.session.execute(
            select(TmsSite).where(TmsSite.config_id == tms_cfg.id)
        ).scalars().all()
        by_name: Dict[str, TmsSite] = {s.name: s for s in existing_tms_sites}

        for r in scp_sites:
            tms_site = by_name.get(r["name"])
            if tms_site is None:
                tms_site = TmsSite(
                    config_id=tms_cfg.id,
                    name=r["name"],
                    type=r["type"] or "INVENTORY",
                    master_type=r.get("master_type"),
                    latitude=r.get("latitude"),
                    longitude=r.get("longitude"),
                    attributes=r.get("attributes") or {},
                )
                self.session.add(tms_site)
                self.session.flush()
            self._scp_to_tms_site[r["scp_site_id"]] = tms_site.id
            self._sites_by_id[tms_site.id] = tms_site

        # Step 3 — materialize lanes (only internal site→site for now;
        # partner-based lanes need TradingPartner mirrors, deferred)
        scp_lanes = self.session.execute(
            text("""
                SELECT scp_lane_id, from_site_id, to_site_id
                FROM tms_src_scp_lane
                WHERE from_site_id IS NOT NULL AND to_site_id IS NOT NULL
            """)
        ).mappings().all()

        existing_tms_lanes = self.session.execute(
            select(TmsLane).where(TmsLane.config_id == tms_cfg.id)
        ).scalars().all()
        by_pair = {(l.from_site_id, l.to_site_id): l for l in existing_tms_lanes}

        for r in scp_lanes:
            from_tms = self._scp_to_tms_site.get(r["from_site_id"])
            to_tms = self._scp_to_tms_site.get(r["to_site_id"])
            if from_tms is None or to_tms is None:
                continue
            lane = by_pair.get((from_tms, to_tms))
            if lane is None:
                lane = TmsLane(
                    config_id=tms_cfg.id,
                    from_site_id=from_tms,
                    to_site_id=to_tms,
                    capacity=1000,  # synthetic default; overlay doesn't plan on it
                )
                self.session.add(lane)
                self.session.flush()
            self._lanes.append(lane)
        self.session.flush()

    def _seed_carriers(self) -> None:
        existing = {
            c.code: c for c in self.session.execute(
                select(Carrier).where(Carrier.tenant_id == self.tms_tenant_id)
            ).scalars().all()
        }

        for spec in TOP_FOODSERVICE_CARRIERS:
            if spec.code in existing:
                self._carriers.append(existing[spec.code])
                continue
            carrier = Carrier(
                code=spec.code,
                name=spec.name,
                scac=spec.scac,
                carrier_type=CarrierType(spec.carrier_type),
                modes=list(spec.modes),
                equipment_types=list(spec.equipment_types),
                service_regions=list(spec.service_regions),
                is_hazmat_certified=spec.is_hazmat_certified,
                insurance_limit=spec.insurance_limit,
                is_active=True,
                onboarding_status="ACTIVE",
                onboarding_date=date(2022, 1, 1),
                source="food_dist_tms_seed",
                tenant_id=self.tms_tenant_id,
                config_id=self.sc_config_id,
            )
            self.session.add(carrier)
            self._carriers.append(carrier)
        self.session.flush()

    def _seed_equipment_fleet(self) -> None:
        """
        Give each carrier a modest fleet of trailers distributed across
        the internal DCs (Food Dist has a CDC in UT and RDCs in WA + CA).
        Distributing the initial pool is what makes the reposition TRM
        have non-trivial imbalances to act on.
        """
        # Build the list of internal DCs by cross-referencing staging.
        # is_external=0 + internal sites are treated as DCs for placement.
        internal_scp_ids = {
            r[0] for r in self.session.execute(
                text("""
                    SELECT scp_site_id FROM tms_src_scp_site
                    WHERE is_external = 0
                """)
            ).all()
        }
        dcs: List[TmsSite] = [
            site for scp_id, tms_id in self._scp_to_tms_site.items()
            if scp_id in internal_scp_ids
            and (site := self._sites_by_id.get(tms_id)) is not None
        ]
        if not dcs:
            # Fallback — first materialized site
            dcs = list(self._sites_by_id.values())[:1]
        logger.info("Equipment will be distributed across %d internal DCs: %s",
                    len(dcs), [d.name for d in dcs])

        # Collect existing equipment per carrier for idempotency
        existing_by_carrier: Dict[int, int] = dict(
            self.session.execute(
                select(Equipment.carrier_id, func.count())
                .where(Equipment.tenant_id == self.tms_tenant_id)
                .group_by(Equipment.carrier_id)
            ).all()
        )

        for carrier in self._carriers:
            spec = next(
                (s for s in TOP_FOODSERVICE_CARRIERS if s.code == carrier.code), None
            )
            if not spec or not spec.is_asset:
                continue
            if existing_by_carrier.get(carrier.id, 0) > 0:
                # Already seeded equipment for this carrier
                continue
            # Small fleet: 10-30 trailers per carrier (training scale, not real fleet)
            count = min(30, max(5, spec.approx_fleet_size // 500))
            for i in range(count):
                eq_type = (
                    "REEFER" if spec.is_reefer_specialist
                    or (i % 3 == 0 and "REEFER" in spec.equipment_types)
                    else "DRY_VAN"
                )
                equipment = Equipment(
                    equipment_id=f"{carrier.code}-{eq_type[:3]}-{i:04d}",
                    equipment_type=EquipmentType(eq_type),
                    carrier_id=carrier.id,
                    length_ft=53.0,
                    max_weight_lbs=44000.0,
                    max_volume_cuft=3489.0 if eq_type == "DRY_VAN" else 3100.0,
                    is_gps_tracked=True,
                    is_temperature_controlled=(eq_type == "REEFER"),
                    temp_min=-10.0 if eq_type == "REEFER" else None,
                    temp_max=40.0 if eq_type == "REEFER" else None,
                    status="AVAILABLE",
                    # Round-robin across DCs so reposition TRM has imbalances
                    current_site_id=dcs[i % len(dcs)].id,
                    source="food_dist_tms_seed",
                    tenant_id=self.tms_tenant_id,
                    config_id=self.sc_config_id,
                )
                self.session.add(equipment)
                self._equipment_pool.append(equipment)
        self.session.flush()

    def _seed_carrier_lanes(self) -> None:
        """
        Assign 3-5 carriers to each lane with priority tiers forming the
        waterfall. UT-preferred carriers get priority on UT-touching lanes.
        """
        ut_pref_codes = {c.code for c in ut_hub_preferred()}
        reefer_codes = {c.code for c in reefer_carriers()}
        dry_codes = {c.code for c in dry_van_carriers()}

        for lane in self._lanes:
            from_site = self._sites_by_id.get(lane.from_site_id)
            to_site = self._sites_by_id.get(lane.to_site_id)
            lane_touches_ut = any(
                s and getattr(s, "name", "") and "UT" in s.name
                for s in (from_site, to_site)
            )

            for equipment in ("REEFER", "DRY_VAN"):
                candidates = reefer_codes if equipment == "REEFER" else dry_codes
                eligible = [c for c in self._carriers if c.code in candidates]

                # Prefer UT-hub carriers for UT-touching lanes
                if lane_touches_ut:
                    eligible.sort(
                        key=lambda c: (0 if c.code in ut_pref_codes else 1, c.id)
                    )

                # 3-5 carriers per lane × equipment
                picks = eligible[: self.rng.randint(3, 5)]
                for pos, carrier in enumerate(picks):
                    spec = next(
                        (s for s in TOP_FOODSERVICE_CARRIERS if s.code == carrier.code),
                        None,
                    )
                    cl = CarrierLane(
                        carrier_id=carrier.id,
                        lane_id=lane.id,
                        mode=TransportMode.FTL,
                        equipment_type=EquipmentType(equipment),
                        weekly_capacity=self.rng.randint(5, 25),
                        avg_transit_days=2.5,  # Regionalize on read
                        priority=pos + 1,
                        is_primary=(pos == 0),
                        is_active=True,
                        eff_start_date=date(2022, 1, 1),
                        tenant_id=self.tms_tenant_id,
                    )
                    self.session.add(cl)
                    key = (lane.id, 0 if equipment == "REEFER" else 1)
                    self._carrier_lanes.setdefault(key, []).append(cl)
        self.session.flush()

    def _seed_freight_rates(self) -> None:
        """
        One contract rate card per (carrier × lane × equipment) effective
        for a full year; spot rates are generated on the fly per tender.
        """
        rate_year_start = date(2022, 1, 1)
        rate_year_end = date(2026, 12, 31)

        for (lane_id, eq_idx), cls in self._carrier_lanes.items():
            equipment = "REEFER" if eq_idx == 0 else "DRY_VAN"
            lane = next((l for l in self._lanes if l.id == lane_id), None)
            if lane is None:
                continue
            from_site = self._sites_by_id.get(lane.from_site_id)
            to_site = self._sites_by_id.get(lane.to_site_id)

            miles = haversine_miles(
                getattr(from_site, "latitude", None),
                getattr(from_site, "longitude", None),
                getattr(to_site, "latitude", None),
                getattr(to_site, "longitude", None),
            ) if from_site and to_site else 500.0

            origin_region = region_for_state(self._site_state(from_site))
            dest_region = region_for_state(self._site_state(to_site))

            quote = quote_rate(
                miles=miles,
                equipment=equipment,
                origin_region=origin_region,
                dest_region=dest_region,
                rate_date=rate_year_start,
                stops=2,
                lumper=True,
                reefer_pretrip=(equipment == "REEFER"),
                temp_recording=(equipment == "REEFER"),
                rng=self.rng,
            )

            fsc_pct = (quote.fsc / quote.linehaul) if quote.linehaul > 0 else 0.0
            for cl in cls:
                rate = FreightRate(
                    carrier_id=cl.carrier_id,
                    lane_id=lane_id,
                    mode=TransportMode.FTL,
                    equipment_type=EquipmentType(equipment),
                    rate_type=RateType.CONTRACT,
                    rate_per_mile=round(quote.linehaul / miles, 3) if miles > 0 else None,
                    rate_flat=quote.contract_total,
                    fuel_surcharge_pct=round(fsc_pct, 4),
                    fuel_surcharge_method="DOE_INDEX",
                    accessorial_schedule={
                        "DETENTION": 75.0,
                        "LUMPER": 250.0,
                        "MULTI_STOP": 50.0,
                        "REEFER_PRETRIP": 35.0 if equipment == "REEFER" else 0.0,
                    },
                    eff_start_date=rate_year_start,
                    eff_end_date=rate_year_end,
                    is_active=True,
                    market_rate_at_contract=quote.spot_total,
                    source="food_dist_tms_seed",
                    tenant_id=self.tms_tenant_id,
                    config_id=self.sc_config_id,
                )
                self.session.add(rate)

    @staticmethod
    def _site_state(site: Optional[Site]) -> Optional[str]:
        """Extract state from Site — Food Dist puts it in attributes or name."""
        if site is None:
            return None
        attrs = getattr(site, "attributes", {}) or {}
        if "state" in attrs:
            return attrs["state"]
        # Fall back to parsing name like "DC - West Valley City, UT"
        name = site.name or ""
        if "," in name:
            tail = name.rsplit(",", 1)[-1].strip().split()
            if tail and len(tail[0]) == 2:
                return tail[0]
        return None

    # -----------------------------------------------------------------
    # Phase 2 — daily generation from SCP Shipments
    # -----------------------------------------------------------------

    def generate_range(self, start: date, end: date) -> Dict[str, int]:
        """Run generate_day over an inclusive date range."""
        totals: Dict[str, int] = {}
        d = start
        while d <= end:
            stats = self.generate_day(d)
            for k, v in stats.items():
                totals[k] = totals.get(k, 0) + v
            d += timedelta(days=1)
            if d.day == 1:
                self.session.commit()
                logger.info("TMS overlay progress through %s: %s", d, totals)
        self.session.commit()
        return totals

    def generate_day(self, d: date) -> Dict[str, int]:
        """
        For date `d`: read SCP Shipments shipping that day, consolidate into
        TMS Loads, run tender waterfall, create the TMS Shipment + tracking
        events + appointments, inject exceptions at calibrated rates, and
        emit any equipment repositioning decisions.
        """
        # Idempotency: skip days that already have loads for this tenant.
        # Load.load_number encodes YYYYMMDD so we check by the prefix.
        day_prefix = f"FD-{d.strftime('%Y%m%d')}-"
        already = self.session.execute(
            select(func.count()).select_from(Load).where(
                and_(
                    Load.tenant_id == self.tms_tenant_id,
                    Load.load_number.like(f"{day_prefix}%"),
                )
            )
        ).scalar_one()
        if already:
            return {"skipped_existing_loads": already}

        scp_shipments = self._scp_shipments_on(d)
        if not scp_shipments:
            return {}

        loads = self._build_loads(scp_shipments, d)
        stats = {
            "scp_shipments": len(scp_shipments),
            "loads": len(loads),
            "tenders": 0,
            "tms_shipments": 0,
            "tracking_events": 0,
            "appointments": 0,
            "exceptions": 0,
            "reposition_moves": 0,
        }

        for load in loads:
            assigned, tender_count = self._run_tender_waterfall(load, d)
            stats["tenders"] += tender_count
            if assigned:
                tms_ship = self._create_tms_shipment(load, assigned, d)
                stats["tms_shipments"] += 1
                stats["tracking_events"] += self._emit_tracking_events(tms_ship)
                stats["appointments"] += self._emit_appointments(tms_ship)
                if self._maybe_inject_exception(tms_ship, d):
                    stats["exceptions"] += 1

        if d.day % self.cfg.reposition_frequency_days == 0:
            stats["reposition_moves"] += self._emit_reposition_moves(d)

        return stats

    def _scp_shipments_on(self, d: date) -> List[ScpShipmentRow]:
        """Read SCP shipments shipping on date d from staging, translating
        from_site_id / to_site_id from SCP IDs to TMS-side IDs via the map."""
        start = datetime.combine(d, datetime.min.time())
        end = start + timedelta(days=1)
        rows = self.session.execute(
            text("""
                SELECT scp_shipment_id, scp_order_id, scp_product_id,
                       quantity, from_site_id, to_site_id,
                       ship_date, expected_delivery_date
                FROM tms_src_scp_shipment
                WHERE ship_date >= :s AND ship_date < :e
            """),
            {"s": start, "e": end},
        ).mappings().all()
        out: List[ScpShipmentRow] = []
        for r in rows:
            from_tms = self._scp_to_tms_site.get(r["from_site_id"])
            to_tms = self._scp_to_tms_site.get(r["to_site_id"])
            if from_tms is None or to_tms is None:
                # Shipment touches a site not in our materialized set
                # (e.g., a partner-based site). Skip for now.
                continue
            out.append(ScpShipmentRow(
                id=r["scp_shipment_id"],
                order_id=r["scp_order_id"],
                product_id=r["scp_product_id"],
                quantity=r["quantity"],
                from_site_id=from_tms,
                to_site_id=to_tms,
                ship_date=r["ship_date"],
                expected_delivery_date=r["expected_delivery_date"],
            ))
        return out

    # -----------------------------------------------------------------
    # Load building — consolidate SCP shipments into TMS Loads
    # -----------------------------------------------------------------

    def _build_loads(self, scp_shipments: List[ScpShipment], d: date) -> List[Load]:
        """
        Group by (lane, equipment) and consolidate into FTL where combined
        weight clears the threshold; smaller combinations become LTL pools.
        """
        from collections import defaultdict
        groups: Dict[Tuple[int, int, str], List[ScpShipment]] = defaultdict(list)
        for ship in scp_shipments:
            equipment = equipment_for_temperature(
                self._infer_temp_category(ship.product_id)
            )
            key = (ship.from_site_id, ship.to_site_id, equipment)
            groups[key].append(ship)

        loads: List[Load] = []
        for (from_site_id, to_site_id, equipment), ships in groups.items():
            # Weight model: product quantity × assumed 40 lbs/case (Food Dist avg)
            total_weight = sum((s.quantity or 0) * 40.0 for s in ships)
            lane_id = self._resolve_lane_id(from_site_id, to_site_id)

            # Consolidate chunks into trucks up to FTL weight
            remaining = list(ships)
            while remaining:
                truck_ships: List[ScpShipment] = []
                truck_weight = 0.0
                while remaining and truck_weight < 42000:
                    s = remaining.pop(0)
                    w = (s.quantity or 0) * 40.0
                    if truck_weight + w > 44000 and truck_ships:
                        remaining.insert(0, s)
                        break
                    truck_ships.append(s)
                    truck_weight += w

                mode = TransportMode.FTL if truck_weight >= self.cfg.ftl_weight_threshold_lbs \
                    else TransportMode.LTL

                load = Load(
                    load_number=f"FD-{d.strftime('%Y%m%d')}-{from_site_id}-{to_site_id}-{len(loads):04d}",
                    status=LoadStatus.PLANNING,
                    origin_site_id=from_site_id,
                    destination_site_id=to_site_id,
                    mode=mode,
                    equipment_type=EquipmentType(equipment),
                    total_weight=truck_weight,
                    planned_departure=datetime.combine(d, datetime.min.time())
                                      + timedelta(hours=8),
                    planned_arrival=datetime.combine(d, datetime.min.time())
                                    + timedelta(days=2, hours=14),
                    optimization_metadata={
                        "scp_source": "food_dist_history",
                        "scp_shipment_ids": [str(s.id) for s in truck_ships],
                        "resolved_lane_id": lane_id,
                    },
                    tenant_id=self.tms_tenant_id,
                    config_id=self.sc_config_id,
                )
                self.session.add(load)
                self.session.flush()

                # Create a TMS Shipment per SCP shipment grouped into this load,
                # so LoadItem.shipment_id can reference a real tms_shipment row.
                for s in truck_ships:
                    tms_ship_stub = TmsShipment(
                        shipment_number=f"FD-SH-{s.id}",
                        status=ShipmentStatus.DRAFT,
                        mode=mode,
                        required_equipment=EquipmentType(equipment),
                        origin_site_id=from_site_id,
                        destination_site_id=to_site_id,
                        lane_id=lane_id,
                        quantity=s.quantity,
                        weight=(s.quantity or 0) * 40.0,
                        requested_pickup_date=load.planned_departure,
                        requested_delivery_date=load.planned_arrival,
                        load_id=load.id,
                        reference_numbers={"scp_shipment_id": str(s.id),
                                           "scp_order_id": str(s.order_id or "")},
                        source="food_dist_tms_overlay",
                        tenant_id=self.tms_tenant_id,
                        config_id=self.sc_config_id,
                    )
                    self.session.add(tms_ship_stub)
                    self.session.flush()

                    self.session.add(LoadItem(
                        load_id=load.id,
                        shipment_id=tms_ship_stub.id,
                        quantity=s.quantity,
                        weight=(s.quantity or 0) * 40.0,
                        tenant_id=self.tms_tenant_id,
                    ))

                # Stash lane on the load for the waterfall step to consume
                load._overlay_lane_id = lane_id
                loads.append(load)
        self.session.flush()
        return loads

    def _resolve_lane_id(self, from_site: int, to_site: int) -> Optional[int]:
        lane = next(
            (l for l in self._lanes
             if l.from_site_id == from_site and l.to_site_id == to_site),
            None,
        )
        return lane.id if lane else None

    def _infer_temp_category(self, product_id: str) -> str:
        """
        Temp is stored on Product in Food Dist — but parsing each row is
        slow. Infer from sku pattern (FZN/RFG/DRY prefix) set by generator.
        """
        if not product_id:
            return "dry"
        pid = product_id.upper()
        if pid.startswith("FZ") or "FROZEN" in pid:
            return "frozen"
        if pid.startswith("RF") or "REFRIG" in pid or "CHILL" in pid:
            return "refrigerated"
        return "dry"

    # -----------------------------------------------------------------
    # Tender waterfall
    # -----------------------------------------------------------------

    def _run_tender_waterfall(
        self, load: Load, d: date
    ) -> Tuple[Optional[Carrier], int]:
        """
        Simulate the carrier waterfall. Returns (assigned_carrier, tenders_sent).
        """
        lane_id = getattr(load, "_overlay_lane_id", None)
        if lane_id is None:
            return None, 0
        eq_idx = 0 if load.equipment_type == EquipmentType.REEFER else 1
        cls = self._carrier_lanes.get((lane_id, eq_idx), [])
        if not cls:
            return None, 0

        reject_prob = tender_reject_probability(d, load.equipment_type.value)
        tenders_sent = 0
        assigned: Optional[Carrier] = None

        for attempt, cl in enumerate(sorted(cls, key=lambda x: x.priority), start=1):
            if attempt > self.cfg.max_tender_attempts:
                break
            carrier = next((c for c in self._carriers if c.id == cl.carrier_id), None)
            if carrier is None:
                continue
            spec = next(
                (s for s in TOP_FOODSERVICE_CARRIERS if s.code == carrier.code), None
            )
            carrier_reject_bias = (1.0 - spec.typical_acceptance_rate) if spec else 0.15

            tenders_sent += 1
            offered_rate = self._lookup_contract_rate(carrier.id, lane_id, load.equipment_type)
            tender = FreightTender(
                shipment_id=None,
                load_id=load.id,
                carrier_id=carrier.id,
                tender_sequence=attempt,
                status=TenderStatus.CREATED,
                offered_rate=offered_rate,
                tendered_at=datetime.combine(d, datetime.min.time()) + timedelta(hours=6),
                response_deadline=datetime.combine(d, datetime.min.time()) + timedelta(hours=9),
                tenant_id=self.tms_tenant_id,
            )
            self.session.add(tender)

            # Acceptance decision: combine market reject prob with carrier bias
            effective_reject = min(0.9, reject_prob + carrier_reject_bias * 0.5)
            if self.rng.random() > effective_reject:
                tender.status = TenderStatus.ACCEPTED
                tender.responded_at = tender.tendered_at + timedelta(minutes=45)
                tender.final_rate = offered_rate
                tender.selection_rationale = {
                    "attempt": attempt,
                    "reject_prob_at_tender": effective_reject,
                    "regime": market_regime(d).value,
                }
                assigned = carrier
                load.status = LoadStatus.ASSIGNED
                break
            else:
                tender.status = TenderStatus.DECLINED
                tender.responded_at = tender.tendered_at + timedelta(hours=1)
                tender.decline_reason = "Capacity not available"

        self.session.flush()
        return assigned, tenders_sent

    def _lookup_contract_rate(
        self, carrier_id: int, lane_id: int, equipment: EquipmentType
    ) -> float:
        rate = self.session.execute(
            select(FreightRate).where(
                and_(
                    FreightRate.carrier_id == carrier_id,
                    FreightRate.lane_id == lane_id,
                    FreightRate.equipment_type == equipment,
                    FreightRate.rate_type == RateType.CONTRACT,
                    FreightRate.is_active.is_(True),
                )
            ).limit(1)
        ).scalar_one_or_none()
        return float(rate.rate_flat) if rate and rate.rate_flat else 2500.0

    # -----------------------------------------------------------------
    # TMS Shipment creation + tracking events + appointments
    # -----------------------------------------------------------------

    def _create_tms_shipment(
        self, load: Load, carrier: Carrier, d: date
    ) -> TmsShipment:
        """
        Create a load-level TMS shipment record for the assigned carrier.
        Per-SCP-shipment stubs were already created during load building; this
        record represents the truck itself and is what TrackingEvent / Appointment
        / Exception refer to.
        """
        lane_id = getattr(load, "_overlay_lane_id", None)
        tms_ship = TmsShipment(
            shipment_number=f"S-{load.load_number}",
            status=ShipmentStatus.DISPATCHED,
            mode=load.mode,
            required_equipment=load.equipment_type,
            origin_site_id=load.origin_site_id,
            destination_site_id=load.destination_site_id,
            lane_id=lane_id,
            carrier_id=carrier.id,
            load_id=load.id,
            requested_pickup_date=load.planned_departure,
            actual_pickup_date=load.planned_departure,
            requested_delivery_date=load.planned_arrival,
            source="food_dist_tms_overlay",
            tenant_id=self.tms_tenant_id,
            config_id=self.sc_config_id,
        )
        self.session.add(tms_ship)
        self.session.flush()
        return tms_ship

    def _emit_tracking_events(self, tms_ship: TmsShipment) -> int:
        """Synthesize EDI 214-style events along the trip."""
        pickup = tms_ship.requested_pickup_date
        delivery = tms_ship.requested_delivery_date
        if not pickup or not delivery:
            return 0
        transit_hrs = (delivery - pickup).total_seconds() / 3600
        if transit_hrs <= 0:
            return 0

        events = []
        events.append((pickup - timedelta(hours=1),
                       TrackingEventType.CREATED, "Carrier dispatched"))
        events.append((pickup, TrackingEventType.PICKED_UP, "Picked up at origin"))
        events.append((pickup + timedelta(minutes=90),
                       TrackingEventType.DEPARTED, "Departed origin"))
        ping_interval = self.cfg.truck_tracking_frequency_hours
        pings = max(1, int(transit_hrs / ping_interval) - 1)
        for i in range(1, pings + 1):
            t = pickup + timedelta(hours=ping_interval * i)
            events.append((t, TrackingEventType.IN_TRANSIT, f"In transit ping {i}"))
        drift = self.rng.gauss(0, self.cfg.eta_drift_stddev_hours)
        events.append((delivery + timedelta(hours=drift),
                       TrackingEventType.ARRIVAL_AT_STOP, "Arrived at destination"))
        events.append((delivery + timedelta(hours=drift, minutes=90),
                       TrackingEventType.DELIVERED, "Delivered"))

        count = 0
        for ts, etype, desc in events:
            self.session.add(TrackingEvent(
                shipment_id=tms_ship.id,
                event_type=etype,
                event_timestamp=ts,
                status_description=desc,
                source="AGENT",
                tenant_id=self.tms_tenant_id,
            ))
            count += 1
        return count

    def _emit_appointments(self, tms_ship: TmsShipment) -> int:
        """One delivery appointment per shipment at the destination DC."""
        delivery = tms_ship.requested_delivery_date
        if not delivery:
            return 0
        appt = Appointment(
            appointment_type=AppointmentType.DELIVERY,
            status=AppointmentStatus.CONFIRMED,
            shipment_id=tms_ship.id,
            load_id=tms_ship.load_id,
            site_id=tms_ship.destination_site_id,
            carrier_id=tms_ship.carrier_id,
            scheduled_start=delivery,
            scheduled_end=delivery + timedelta(minutes=60),
            tenant_id=self.tms_tenant_id,
        )
        self.session.add(appt)
        return 1

    # -----------------------------------------------------------------
    # Exception injection
    # -----------------------------------------------------------------

    def _maybe_inject_exception(self, tms_ship: TmsShipment, d: date) -> bool:
        base_rate = self.cfg.exception_base_rate
        # Tight market → more exceptions
        if market_regime(d) in (MarketRegime.TIGHT, MarketRegime.EXTREME):
            base_rate *= 1.4
        # Reefer has dedicated temp-excursion path
        if tms_ship.required_equipment == EquipmentType.REEFER:
            if self.rng.random() < self.cfg.temp_excursion_rate_reefer:
                self._create_exception(
                    tms_ship, ExceptionType.TEMPERATURE_EXCURSION,
                    ExceptionSeverity.HIGH, "Temperature out of range during transit",
                )
                return True

        if self.rng.random() > base_rate:
            return False

        # Exception type mix
        roll = self.rng.random()
        if roll < self.cfg.late_delivery_fraction:
            etype = ExceptionType.LATE_DELIVERY
            severity = ExceptionSeverity.MEDIUM
            desc = "Delivery behind schedule"
        elif roll < 0.80:
            etype = ExceptionType.DETENTION
            severity = ExceptionSeverity.LOW
            desc = "Driver detained at receiver"
        elif roll < 0.90:
            etype = ExceptionType.CARRIER_BREAKDOWN
            severity = ExceptionSeverity.HIGH
            desc = "Equipment failure in transit"
        elif roll < 0.96:
            etype = ExceptionType.WEATHER_DELAY
            severity = ExceptionSeverity.MEDIUM
            desc = "Weather-related route delay"
        else:
            etype = ExceptionType.REFUSED
            severity = ExceptionSeverity.CRITICAL
            desc = "Receiver refused delivery"

        self._create_exception(tms_ship, etype, severity, desc)
        return True

    def _create_exception(
        self, tms_ship: TmsShipment,
        etype: ExceptionType, severity: ExceptionSeverity, desc: str,
    ) -> None:
        self.session.add(ShipmentException(
            shipment_id=tms_ship.id,
            exception_type=etype,
            severity=severity,
            resolution_status=ExceptionResolutionStatus.DETECTED,
            description=desc,
            detected_at=datetime.utcnow(),
            detection_source="SYNTHETIC",
            tenant_id=self.tms_tenant_id,
        ))

    # -----------------------------------------------------------------
    # Equipment repositioning
    # -----------------------------------------------------------------

    def _emit_reposition_moves(self, d: date) -> int:
        """
        Periodic rebalance: check imbalances across sites, emit EquipmentMove
        rows for the top N most-justified moves.
        """
        # Count equipment per (site, equipment_type)
        rows = self.session.execute(
            select(Equipment.current_site_id, Equipment.equipment_type, func.count())
            .where(Equipment.tenant_id == self.tms_tenant_id)
            .group_by(Equipment.current_site_id, Equipment.equipment_type)
        ).all()
        by_site: Dict[Tuple[int, EquipmentType], int] = {
            (site_id, etype): cnt for site_id, etype, cnt in rows if site_id
        }

        # Simple imbalance rule: move from max to min for each equipment type
        moves_created = 0
        for eq_type in (EquipmentType.REEFER, EquipmentType.DRY_VAN):
            sites_with = [(sid, cnt) for (sid, et), cnt in by_site.items() if et == eq_type]
            if len(sites_with) < 2:
                continue
            sites_with.sort(key=lambda x: x[1])
            low_site, low_cnt = sites_with[0]
            high_site, high_cnt = sites_with[-1]
            if high_cnt - low_cnt < 5:
                continue

            from_site = self._sites_by_id.get(high_site)
            to_site = self._sites_by_id.get(low_site)
            miles = haversine_miles(
                getattr(from_site, "latitude", None),
                getattr(from_site, "longitude", None),
                getattr(to_site, "latitude", None),
                getattr(to_site, "longitude", None),
            ) if from_site and to_site else 500.0
            cost = miles * self.cfg.reposition_cost_per_mile
            avoided_premium = cost * self.rng.uniform(1.2, 2.5)

            # Pick an available equipment at high_site
            eq = self.session.execute(
                select(Equipment).where(and_(
                    Equipment.tenant_id == self.tms_tenant_id,
                    Equipment.current_site_id == high_site,
                    Equipment.equipment_type == eq_type,
                    Equipment.status == "AVAILABLE",
                )).limit(1)
            ).scalar_one_or_none()
            if eq is None:
                continue

            self.session.add(EquipmentMove(
                equipment_id=eq.id,
                carrier_id=eq.carrier_id,
                from_site_id=high_site,
                to_site_id=low_site,
                miles=miles,
                dispatched_at=datetime.combine(d, datetime.min.time()) + timedelta(hours=14),
                planned_arrival_at=datetime.combine(d, datetime.min.time())
                                   + timedelta(hours=14 + miles / 50),
                cost=cost,
                cost_of_not_repositioning=avoided_premium,
                roi=avoided_premium / max(1.0, cost),
                reason=EquipmentMoveReason.REBALANCE,
                status=EquipmentMoveStatus.DISPATCHED,
                decision_rationale={
                    "high_site_count": high_cnt,
                    "low_site_count": low_cnt,
                    "gap": high_cnt - low_cnt,
                },
                tenant_id=self.tms_tenant_id,
                config_id=self.sc_config_id,
            ))
            eq.current_site_id = low_site  # Optimistic update
            moves_created += 1
        return moves_created
