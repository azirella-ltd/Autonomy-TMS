"""TMS Demo Importer — counterpart to SCP's tms-demo-export.

Ingests the JSON package SCP exposes at
`GET /api/v1/tactical/tms-demo-export/{scp_config_id}` (schema 1.0) and
materialises it as a TMS tenant with mapped sites / partners / lanes /
shipments. Runs the synthetic capacity seeder at the end so the new
tenant has constraint envelopes ready for the constrained planner work.

REMAPPING RULES (the caveat from §10's transmittal note):
  scp_site_id  → site.id (Integer surrogate, looked up by Site.name)
  scp_partner_id → trading_partners.id (String, namespaced as
                    f"SCP{scp_config_id}_{scp_partner_id}")
  Lane endpoints — after the site map is built, lanes are looked up by
                    (origin_site_id, dest_site_id) within the new config
  Shipment refs  — uses the cached site / partner maps from previous steps

See docs/TACTICAL_PLANNING_REARCHITECTURE.md §10.3 for the contract.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tenant import Tenant, TenantMode
from app.models.supply_chain_config import (
    Site,
    SupplyChainConfig,
    TransportationLane,
)
from app.models.tms_entities import Shipment, ShipmentStatus, TransportMode
from azirella_data_model.master.entities import TradingPartner

logger = logging.getLogger(__name__)


SUPPORTED_SCHEMA = "1.0"


class TMSDemoImporter:
    """Materialise an SCP demo export into a TMS tenant."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.site_map: Dict[str, int] = {}      # scp_site_id → tms site.id
        self.partner_map: Dict[str, str] = {}    # scp_partner_id → tms trading_partners.id
        self.lane_map: Dict[Tuple[int, int], int] = {}  # (origin_id, dest_id) → tms lane.id
        self.remapping_rules_applied: List[str] = []

    # ── Public entrypoints ──────────────────────────────────────────

    async def import_from_url(self, source_url: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.get(source_url)
            r.raise_for_status()
            payload = r.json()
        return await self.import_from_payload(payload, source_url=source_url)

    async def import_from_payload(
        self,
        payload: Dict[str, Any],
        source_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run the full ingest pipeline. Steps mirror §10.3."""
        # 1. Schema validation
        version = payload.get("schema_version")
        if version != SUPPORTED_SCHEMA:
            raise ValueError(
                f"Unsupported schema version: {version}. "
                f"Importer accepts {SUPPORTED_SCHEMA} only."
            )

        provenance = payload.get("exported_from", {}) or {}
        scp_config_id = provenance.get("config_id")
        if scp_config_id is None:
            raise ValueError("Payload missing exported_from.config_id")

        # 2. Tenant + Config
        tenant = await self._create_or_get_tenant(provenance)
        config = await self._create_or_get_config(tenant.id, provenance)

        # 3. Sites — build the site map
        sites_in = payload.get("sites", []) or []
        await self._import_sites(tenant.id, config.id, sites_in)
        self.remapping_rules_applied.append(
            "scp_site_id → site.id via Site.name match within tenant"
        )

        # 4. Partners — namespaced trading_partners
        partners_in = payload.get("partners", []) or []
        await self._import_partners(tenant.id, scp_config_id, partners_in)
        self.remapping_rules_applied.append(
            f'scp_partner_id namespaced to "SCP{scp_config_id}_*"'
        )

        # 5. Lanes — after-site lookup or insert
        lanes_in = payload.get("lanes", []) or []
        await self._import_lanes(tenant.id, config.id, lanes_in)
        self.remapping_rules_applied.append(
            "Lane endpoints translated via site_map; lanes upserted by (origin, dest) within new config"
        )

        # 6. Shipments — use cached maps
        shipments_in = payload.get("shipments", []) or []
        shipment_count = await self._import_shipments(tenant.id, config.id, shipments_in)

        await self.db.commit()

        # 7. Run the synthetic capacity seeder
        from app.services.tms_planning.synthetic_capacity_seeder import (
            SyntheticCapacitySeeder,
        )
        capacity_summary = await SyntheticCapacitySeeder(self.db).seed(
            tenant_id=tenant.id, config_id=config.id,
        )

        return {
            "tenant_id": tenant.id,
            "config_id": config.id,
            "imported_from": {
                "scp_config_id": scp_config_id,
                "source_url": source_url,
                "schema_version": version,
            },
            "counts": {
                "sites": len(self.site_map),
                "partners": len(self.partner_map),
                "lanes": len(self.lane_map),
                "shipments": shipment_count,
            },
            "remapping_rules_applied": self.remapping_rules_applied,
            "synthetic_capacity": capacity_summary,
            "completed_at": datetime.utcnow().isoformat() + "Z",
        }

    # ── Step implementations ────────────────────────────────────────

    async def _create_or_get_tenant(self, provenance: Dict[str, Any]) -> Tenant:
        scp_cfg = provenance.get("config_id")
        slug = f"scp-import-{scp_cfg}"
        existing = (await self.db.execute(
            select(Tenant).where(Tenant.slug == slug)
        )).scalar_one_or_none()
        if existing:
            return existing
        # Re-use the system admin user as the bootstrap admin for the tenant
        from app.models.user import User
        admin = (await self.db.execute(
            select(User).where(User.email == "systemadmin@autonomy.ai")
        )).scalar_one_or_none()

        tenant = Tenant(
            name=f"SCP Import — config {scp_cfg}",
            slug=slug,
            subdomain=slug,
            description=(
                f"Tenant materialised from SCP config {scp_cfg} via "
                "tms-demo-export schema 1.0."
            ),
            admin_id=admin.id if admin else None,
            mode=TenantMode.PRODUCTION,
        )
        self.db.add(tenant)
        await self.db.flush()
        return tenant

    async def _create_or_get_config(
        self, tenant_id: int, provenance: Dict[str, Any],
    ) -> SupplyChainConfig:
        scp_cfg = provenance.get("config_id")
        name = f"SCP Import — config {scp_cfg}"
        existing = (await self.db.execute(
            select(SupplyChainConfig).where(
                SupplyChainConfig.tenant_id == tenant_id,
                SupplyChainConfig.name == name,
            )
        )).scalar_one_or_none()
        if existing:
            return existing
        cfg = SupplyChainConfig(
            tenant_id=tenant_id,
            name=name,
            is_active=True,
        )
        self.db.add(cfg)
        await self.db.flush()
        return cfg

    async def _import_sites(
        self, tenant_id: int, config_id: int, sites_in: List[Dict[str, Any]],
    ) -> None:
        for s in sites_in:
            scp_id = s.get("scp_site_id") or s.get("id") or s.get("name")
            if not scp_id:
                continue
            scp_id = str(scp_id)

            # Site is scoped via config_id (which itself FKs to
            # supply_chain_configs.tenant_id) — no direct tenant_id column.
            existing = (await self.db.execute(
                select(Site).where(
                    Site.config_id == config_id,
                    Site.name == scp_id,
                )
            )).scalar_one_or_none()
            if existing:
                self.site_map[scp_id] = existing.id
                continue

            site = Site(
                config_id=config_id,
                name=scp_id,
                type=s.get("type", "DC"),
                dag_type=s.get("dag_type", "INVENTORY"),
                master_type=s.get("master_type", "DC"),
                attributes={
                    "imported_from_scp": True,
                    "scp_site_id": scp_id,
                    **(s.get("attributes") or {}),
                },
            )
            self.db.add(site)
            await self.db.flush()
            self.site_map[scp_id] = site.id

    async def _import_partners(
        self, tenant_id: int, scp_config_id: int, partners_in: List[Dict[str, Any]],
    ) -> None:
        for p in partners_in:
            scp_id = p.get("scp_partner_id") or p.get("id")
            if not scp_id:
                continue
            scp_id = str(scp_id)
            tms_id = f"SCP{scp_config_id}_{scp_id}"

            existing = (await self.db.execute(
                select(TradingPartner).where(TradingPartner.id == tms_id)
            )).scalar_one_or_none()
            if existing:
                self.partner_map[scp_id] = tms_id
                continue

            kind = (p.get("kind") or p.get("tpartner_type") or "vendor").lower()
            tp = TradingPartner(
                id=tms_id,
                tpartner_type=kind,
                description=p.get("description") or p.get("name") or scp_id,
                country=p.get("country", "USA"),
                city=p.get("city"),
                state_prov=p.get("state"),
                is_active="true",
            )
            self.db.add(tp)
            self.partner_map[scp_id] = tms_id

    async def _import_lanes(
        self, tenant_id: int, config_id: int, lanes_in: List[Dict[str, Any]],
    ) -> None:
        for ln in lanes_in:
            o_scp = str(ln.get("origin_scp_site_id") or ln.get("origin") or "")
            d_scp = str(ln.get("dest_scp_site_id") or ln.get("destination") or "")
            origin_id = self.site_map.get(o_scp)
            dest_id = self.site_map.get(d_scp)
            if origin_id is None or dest_id is None:
                continue

            key = (origin_id, dest_id)
            if key in self.lane_map:
                continue

            existing = (await self.db.execute(
                select(TransportationLane).where(
                    TransportationLane.config_id == config_id,
                    TransportationLane.from_site_id == origin_id,
                    TransportationLane.to_site_id == dest_id,
                )
            )).scalar_one_or_none()
            if existing:
                self.lane_map[key] = existing.id
                continue

            lane = TransportationLane(
                config_id=config_id,
                from_site_id=origin_id,
                to_site_id=dest_id,
                lead_time_days=ln.get("lead_time_days") or 3,
                # NOT NULL on transportation_lane — coalesce missing AND explicit null
                capacity=ln.get("capacity") or 1000,
            )
            self.db.add(lane)
            await self.db.flush()
            self.lane_map[key] = lane.id

    async def _import_shipments(
        self, tenant_id: int, config_id: int, shipments_in: List[Dict[str, Any]],
    ) -> int:
        n = 0
        for s in shipments_in:
            o_scp = str(s.get("origin_scp_site_id") or s.get("origin") or "")
            d_scp = str(s.get("dest_scp_site_id") or s.get("destination") or "")
            origin_id = self.site_map.get(o_scp)
            dest_id = self.site_map.get(d_scp)
            if origin_id is None or dest_id is None:
                continue

            shipment_number = (
                s.get("shipment_number")
                or s.get("id")
                or f"SCP-{config_id}-{n+1:06d}"
            )

            mode_str = (s.get("mode") or "FTL").upper()
            try:
                mode = TransportMode(mode_str)
            except ValueError:
                mode = TransportMode.FTL

            try:
                status = ShipmentStatus(s.get("status", "DRAFT"))
            except ValueError:
                status = ShipmentStatus.DRAFT

            requested_pickup = self._parse_dt(s.get("requested_pickup_date"))
            requested_delivery = self._parse_dt(s.get("requested_delivery_date"))

            self.db.add(Shipment(
                tenant_id=tenant_id,
                config_id=config_id,
                shipment_number=shipment_number,
                origin_site_id=origin_id,
                destination_site_id=dest_id,
                lane_id=self.lane_map.get((origin_id, dest_id)),
                quantity=s.get("quantity"),
                weight=s.get("weight"),
                mode=mode,
                status=status,
                requested_pickup_date=requested_pickup or datetime.utcnow(),
                requested_delivery_date=requested_delivery or datetime.utcnow(),
                source="scp_import_v1",
            ))
            n += 1
        await self.db.flush()
        return n

    @staticmethod
    def _parse_dt(s: Any) -> Optional[datetime]:
        if not s:
            return None
        if isinstance(s, datetime):
            return s
        try:
            return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        except Exception:
            return None
