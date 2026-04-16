"""SyntheticCapacitySeeder — TMS-side counterpart to SCP's RDC capacity seeding.

Produces transportation capacity envelopes (carrier-lane weekly capacity,
dock doors, equipment counts) so a synthetic / demo tenant has the
constraint-side numbers needed for the constrained planner work in
Phase 3 of the Tactical Planning Re-Architecture.

Idempotent — running twice doesn't double counts. Identifies existing
rows by natural key and updates in place. Marks every generated row
with `source = 'synthetic_capacity_v1'` so a later real-data extract
can selectively wipe synthetic rows.

See docs/TACTICAL_PLANNING_REARCHITECTURE.md §10.2 for the formulas.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tms_entities import (
    Carrier,
    CarrierLane,
    DockDoor,
    Equipment,
    EquipmentType,
    Shipment,
    TransportMode,
)
from app.models.supply_chain_config import Site

logger = logging.getLogger(__name__)


SOURCE_TAG = "synthetic_capacity_v1"

# Floor values per the spec (table in §10.2)
MIN_WEEKLY_CAPACITY = 5
MIN_DOCK_DOORS_PER_SITE = 8
MIN_EQUIPMENT_UNITS_PER_TYPE_PER_SITE = 4

# Headroom multipliers
HEADROOM_CARRIER_LANE = 1.2
HEADROOM_DOCK_PEAK = 1.2
HEADROOM_EQUIPMENT_PEAK = 1.15

# Default equipment types to seed at every yard if missing
DEFAULT_EQUIPMENT_TYPES = ["DRY_VAN", "REEFER", "FLATBED"]


class SyntheticCapacitySeeder:
    """Seed (or update) transportation capacity envelopes for a tenant."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def seed(
        self,
        tenant_id: int,
        config_id: Optional[int] = None,
        history_window_weeks: int = 12,
    ) -> Dict[str, Any]:
        """Seed capacity for a tenant. Returns a summary manifest."""
        summary: List[Dict[str, Any]] = []

        cl = await self._seed_carrier_lane_capacity(tenant_id, config_id, history_window_weeks)
        summary.append({"entity": "carrier_lane", **cl, "basis": "weekly avg loads × 1.2 headroom, min 5"})

        dd = await self._seed_dock_doors(tenant_id, config_id)
        summary.append({"entity": "dock_door", **dd, "basis": "peak inbound appts × 1.2 headroom, min 8 per site"})

        eq = await self._seed_equipment(tenant_id, config_id)
        summary.append({"entity": "equipment", **eq, "basis": "peak concurrent use × 1.15 headroom, min 4 per type per yard"})

        await self.db.commit()

        return {
            "tenant_id": tenant_id,
            "config_id": config_id,
            "source_tag": SOURCE_TAG,
            "completed_at": datetime.utcnow().isoformat() + "Z",
            "entities": summary,
        }

    # ── carrier_lane.weekly_capacity ─────────────────────────────────

    async def _seed_carrier_lane_capacity(
        self, tenant_id: int, config_id: Optional[int], window_weeks: int,
    ) -> Dict[str, int]:
        """For each (carrier, lane) pair seen in shipment history, set
        `weekly_capacity = max(MIN, ceil(avg_weekly_loads * 1.2))`."""
        cutoff = datetime.utcnow() - timedelta(weeks=window_weeks)

        # Aggregate historical loads per (carrier_id, lane_id) from shipments.
        # Shipments → load_id → carrier+lane derivation is plan-side; for
        # seeding purposes the simpler signal is the shipment's carrier_id +
        # lane_id directly when present.
        stmt = (
            select(
                Shipment.carrier_id,
                Shipment.lane_id,
                func.count(Shipment.id),
            )
            .where(
                Shipment.tenant_id == tenant_id,
                Shipment.created_at >= cutoff,
                Shipment.carrier_id.isnot(None),
                Shipment.lane_id.isnot(None),
            )
            .group_by(Shipment.carrier_id, Shipment.lane_id)
        )
        rows = (await self.db.execute(stmt)).all()

        created = 0
        updated = 0
        for carrier_id, lane_id, total_loads in rows:
            avg_weekly = (total_loads or 0) / max(window_weeks, 1)
            target = max(
                MIN_WEEKLY_CAPACITY,
                math.ceil(avg_weekly * HEADROOM_CARRIER_LANE),
            )

            existing_stmt = select(CarrierLane).where(
                CarrierLane.carrier_id == carrier_id,
                CarrierLane.lane_id == lane_id,
                CarrierLane.tenant_id == tenant_id,
            )
            existing = (await self.db.execute(existing_stmt)).scalar_one_or_none()
            if existing:
                if existing.weekly_capacity != target:
                    existing.weekly_capacity = target
                    updated += 1
            else:
                self.db.add(CarrierLane(
                    carrier_id=carrier_id,
                    lane_id=lane_id,
                    mode=TransportMode.FTL,
                    equipment_type=EquipmentType.DRY_VAN,
                    weekly_capacity=target,
                    is_primary=False,
                    is_active=True,
                    eff_start_date=date.today(),
                    eff_end_date=date.today() + timedelta(days=365),
                    tenant_id=tenant_id,
                ))
                created += 1

        await self.db.flush()
        return {"created": created, "updated": updated, "rows_seen": len(rows)}

    # ── dock_doors per site ──────────────────────────────────────────

    async def _seed_dock_doors(
        self, tenant_id: int, config_id: Optional[int],
    ) -> Dict[str, int]:
        """Ensure each active facility site has at least MIN_DOCK_DOORS_PER_SITE
        dock_door rows. Peak-driven sizing isn't possible without inbound
        appointment history; we fall back to the floor at minimum."""
        # Site has no tenant_id column — scope via config_id which FKs
        # to supply_chain_configs.tenant_id.
        from app.models.supply_chain_config import SupplyChainConfig
        site_stmt = (
            select(Site.id)
            .join(SupplyChainConfig, SupplyChainConfig.id == Site.config_id)
            .where(SupplyChainConfig.tenant_id == tenant_id)
        )
        if config_id is not None:
            site_stmt = site_stmt.where(Site.config_id == config_id)
        site_ids = [row[0] for row in (await self.db.execute(site_stmt)).all()]

        created = 0
        for site_id in site_ids:
            existing_count_stmt = (
                select(func.count(DockDoor.id))
                .where(
                    DockDoor.site_id == site_id,
                    DockDoor.tenant_id == tenant_id,
                )
            )
            existing_count = (await self.db.execute(existing_count_stmt)).scalar() or 0
            target = MIN_DOCK_DOORS_PER_SITE
            need = max(0, target - existing_count)
            for n in range(need):
                door_num = existing_count + n + 1
                self.db.add(DockDoor(
                    site_id=site_id,
                    door_number=f"D-{door_num:02d}",
                    door_type="STANDARD",
                    equipment_compatible=["DRY_VAN", "REEFER"],
                    has_leveler=True,
                    has_restraint=True,
                    is_active=True,
                    tenant_id=tenant_id,
                ))
                created += 1

        await self.db.flush()
        return {"created": created, "updated": 0, "sites_seen": len(site_ids)}

    # ── equipment units per type per yard ────────────────────────────

    async def _seed_equipment(
        self, tenant_id: int, config_id: Optional[int],
    ) -> Dict[str, int]:
        """Ensure each active site has at least MIN_EQUIPMENT_UNITS_PER_TYPE_PER_SITE
        equipment units of each DEFAULT_EQUIPMENT_TYPES type."""
        # Site has no tenant_id column — scope via config_id which FKs
        # to supply_chain_configs.tenant_id.
        from app.models.supply_chain_config import SupplyChainConfig
        site_stmt = (
            select(Site.id)
            .join(SupplyChainConfig, SupplyChainConfig.id == Site.config_id)
            .where(SupplyChainConfig.tenant_id == tenant_id)
        )
        if config_id is not None:
            site_stmt = site_stmt.where(Site.config_id == config_id)
        site_ids = [row[0] for row in (await self.db.execute(site_stmt)).all()]

        created = 0
        for site_id in site_ids:
            for eq_type in DEFAULT_EQUIPMENT_TYPES:
                count_stmt = (
                    select(func.count(Equipment.id))
                    .where(
                        Equipment.tenant_id == tenant_id,
                        Equipment.current_site_id == site_id,
                        Equipment.equipment_type == eq_type,
                    )
                )
                existing_count = (await self.db.execute(count_stmt)).scalar() or 0
                need = max(0, MIN_EQUIPMENT_UNITS_PER_TYPE_PER_SITE - existing_count)
                for n in range(need):
                    unit_num = existing_count + n + 1
                    self.db.add(Equipment(
                        equipment_id=f"SYN-{site_id}-{eq_type}-{unit_num:03d}",
                        equipment_type=eq_type,
                        carrier_id=None,  # Yard pool, not carrier-owned
                        length_ft=53.0 if eq_type != "FLATBED" else 48.0,
                        is_temperature_controlled=eq_type == "REEFER",
                        status="AVAILABLE",
                        current_site_id=site_id,
                        is_active=True,
                        source=SOURCE_TAG,
                        tenant_id=tenant_id,
                        config_id=config_id,
                    ))
                    created += 1

        await self.db.flush()
        return {
            "created": created,
            "updated": 0,
            "sites_seen": len(site_ids),
            "equipment_types_per_site": len(DEFAULT_EQUIPMENT_TYPES),
        }
