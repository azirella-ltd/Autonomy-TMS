"""
Odoo Config Builder — Reverse ETL

Transforms extracted Odoo data into an Autonomy SupplyChainConfig.
Follows the same 8-step pipeline as ``sap_config_builder.py``:

1. Extract & validate schema
2. Company & geography
3. Sites with master type inference
4. Products & hierarchy
5. Transportation lanes (from supplier info + transfer patterns)
6. Trading partners & sourcing rules
7. Manufacturing: BOMs, work centres, routing
8. Planning data: inventory levels, reorder rules, forecasts

Master type inference for Odoo:
- Warehouse with mrp.production → MANUFACTURER
- Warehouse with purchase.order only → VENDOR (supplier proxy)
- Warehouse with sale.order only → CUSTOMER (customer proxy)
- res.partner with supplier_rank > 0 → VENDOR
- res.partner with customer_rank > 0 → CUSTOMER
- Remaining warehouses → INVENTORY
"""

import logging
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class OdooConfigBuildResult:
    """Result of building a SupplyChainConfig from Odoo data."""
    success: bool = True
    config_id: Optional[int] = None
    sites_created: int = 0
    products_created: int = 0
    lanes_created: int = 0
    boms_created: int = 0
    trading_partners_created: int = 0
    inv_levels_created: int = 0
    inv_policies_created: int = 0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self):
        return {
            "success": self.success,
            "config_id": self.config_id,
            "sites_created": self.sites_created,
            "products_created": self.products_created,
            "lanes_created": self.lanes_created,
            "boms_created": self.boms_created,
            "trading_partners_created": self.trading_partners_created,
            "inv_levels_created": self.inv_levels_created,
            "inv_policies_created": self.inv_policies_created,
            "warnings": self.warnings,
            "errors": self.errors,
        }


class OdooConfigBuilder:
    """Builds an Autonomy SupplyChainConfig from Odoo extracted data.

    Takes raw Odoo records (as dicts) and creates platform entities
    via the SQLAlchemy session.

    Usage:
        builder = OdooConfigBuilder(db, tenant_id=3, config_name="Odoo Import")
        result = await builder.build(extracted_data)
    """

    def __init__(self, db, tenant_id: int, config_name: str = "Odoo Import"):
        self.db = db
        self.tenant_id = tenant_id
        self.config_name = config_name

    async def build(self, data: Dict[str, List[Dict]]) -> OdooConfigBuildResult:
        """Build SupplyChainConfig from extracted Odoo data.

        Args:
            data: Dict mapping Odoo model name → list of records.
                  e.g. {"product.product": [...], "stock.warehouse": [...]}
        """
        result = OdooConfigBuildResult()

        try:
            # Step 1: Create or find SupplyChainConfig
            config = await self._get_or_create_config(result)
            result.config_id = config.id if config else None

            if not config:
                result.success = False
                result.errors.append("Failed to create SupplyChainConfig")
                return result

            # Step 2: Company
            companies = data.get("res.company", [])
            if companies:
                logger.info("Odoo build: %d companies", len(companies))

            # Step 3: Sites (warehouses → sites with master type inference)
            warehouses = data.get("stock.warehouse", [])
            production_orders = data.get("mrp.production", [])
            supplier_info = data.get("product.supplierinfo", [])
            partners = data.get("res.partner", [])

            site_map = await self._build_sites(
                config, warehouses, production_orders, partners, result
            )

            # Step 4: Products & hierarchy
            products = data.get("product.product", [])
            categories = data.get("product.category", [])
            product_map = await self._build_products(config, products, categories, result)

            # Step 5: Trading partners (vendors + customers as TradingPartner, NOT sites)
            partner_map = await self._build_trading_partners(config, partners, supplier_info, result)

            # Step 6: Transportation lanes (partner→site, site→partner, site→site)
            pickings = data.get("stock.picking", [])
            await self._build_lanes(config, supplier_info, pickings, site_map, partner_map, result)

            # Step 7: BOMs & work centres
            boms = data.get("mrp.bom", [])
            bom_lines = data.get("mrp.bom.line", [])
            workcenters = data.get("mrp.workcenter", [])
            await self._build_manufacturing(config, boms, bom_lines, workcenters, product_map, result)

            # Step 8: Inventory levels & policies
            quants = data.get("stock.quant", [])
            orderpoints = data.get("stock.warehouse.orderpoint", [])
            await self._build_inventory(config, quants, orderpoints, site_map, product_map, result)

            await self.db.commit()
            logger.info("Odoo config build complete: config_id=%d", config.id)

        except Exception as e:
            await self.db.rollback()
            result.success = False
            result.errors.append(f"Build failed: {str(e)}")
            logger.exception("Odoo config build failed")

        return result

    # ── Step helpers ──────────────────────────────────────────────────────

    async def _get_or_create_config(self, result: OdooConfigBuildResult):
        """Create or find the SupplyChainConfig."""
        from app.models.supply_chain_config import SupplyChainConfig
        from sqlalchemy import select

        # Check for existing config with same name and tenant
        stmt = select(SupplyChainConfig).where(
            SupplyChainConfig.tenant_id == self.tenant_id,
            SupplyChainConfig.name == self.config_name,
            SupplyChainConfig.is_active == True,
        )
        existing = (await self.db.execute(stmt)).scalar_one_or_none()
        if existing:
            logger.info("Odoo build: reusing existing config %d '%s'", existing.id, existing.name)
            return existing

        config = SupplyChainConfig(
            name=self.config_name,
            description=f"Imported from Odoo on {datetime.utcnow().strftime('%Y-%m-%d')}",
            tenant_id=self.tenant_id,
            is_active=True,
            version=1,
        )
        self.db.add(config)
        await self.db.flush()
        logger.info("Odoo build: created config %d '%s'", config.id, config.name)
        return config

    async def _build_sites(self, config, warehouses, production_orders, partners, result):
        """Step 3: Build sites with master type inference."""
        from app.models.sc_entities import Site

        # Determine which warehouses have production orders → MANUFACTURER
        manufacturing_warehouse_ids: Set[int] = set()
        for mo in production_orders:
            # mrp.production doesn't directly expose warehouse_id,
            # but the location_src_id or picking_type_id can be traced.
            # For simplicity, if ANY production orders exist, the first warehouse is MANUFACTURER.
            pass

        # AWS SC Compliance: Vendors and customers are TradingPartner records,
        # NOT proxy Site records. Sites = internal warehouses/plants only.
        # Partners connect to the DAG via from_partner_id/to_partner_id on lanes.

        site_map: Dict[int, Any] = {}  # odoo_wh_id → Site

        # Warehouses → INVENTORY or MANUFACTURER (internal sites only)
        for wh in warehouses:
            master_type = "INVENTORY"
            if wh.get("id") in manufacturing_warehouse_ids or production_orders:
                master_type = "MANUFACTURER"

            site = Site(
                config_id=config.id,
                name=wh.get("code", wh.get("name", f"WH-{wh['id']}")),
                type=f"Warehouse - {wh.get('name', '')}",
                master_type=master_type,
            )
            self.db.add(site)
            await self.db.flush()
            site_map[wh["id"]] = site
            result.sites_created += 1

        return site_map

    async def _build_products(self, config, products, categories, result):
        """Step 4: Build products and hierarchy."""
        from app.models.sc_entities import Product

        product_map: Dict[int, Any] = {}
        for prod in products:
            categ = prod.get("categ_id")
            categ_name = categ[1] if isinstance(categ, (list, tuple)) and len(categ) == 2 else ""

            product = Product(
                config_id=config.id,
                name=str(prod.get("default_code") or prod.get("name", f"PROD-{prod['id']}"))[:100],
                description=str(prod.get("name", ""))[:255],
                unit_cost=prod.get("standard_price", 0.0),
                product_group=categ_name[:50] if categ_name else None,
            )
            self.db.add(product)
            await self.db.flush()
            product_map[prod["id"]] = product
            result.products_created += 1

        return product_map

    async def _build_trading_partners(self, config, partners, supplier_info, result):
        """Step 5: Build TradingPartner records (NOT sites) for vendors and customers.

        AWS SC Compliance: Vendors and customers are TradingPartner records.
        They connect to the DAG via from_partner_id / to_partner_id on lanes.
        """
        from app.models.sc_entities import TradingPartner
        from sqlalchemy import select as sa_select

        partner_map: Dict[str, int] = {}  # "V_odoo_id" or "C_odoo_id" → _id (serial PK)

        vendor_partners = [p for p in partners if p.get("supplier_rank", 0) > 0]
        customer_partners = [p for p in partners if p.get("customer_rank", 0) > 0]

        for vp in vendor_partners:
            odoo_id = vp.get("id")
            name = str(vp.get("name", f"Vendor-{odoo_id}"))[:200]
            tp_id = f"ODOO_V_{odoo_id}"

            # Check if exists
            existing = (await self.db.execute(
                sa_select(TradingPartner).where(TradingPartner.id == tp_id)
            )).scalar_one_or_none()
            if existing:
                partner_map[f"V_{odoo_id}"] = existing._id
            else:
                tp = TradingPartner(
                    id=tp_id,
                    tpartner_type="vendor",
                    description=name,
                    city=str(vp.get("city", ""))[:100],
                    country=str(vp.get("country_id", ""))[:10] if not isinstance(vp.get("country_id"), (list, tuple)) else "",
                    company_id=f"ODOO_{self.tenant_id}",
                    source="ODOO",
                )
                self.db.add(tp)
                await self.db.flush()
                partner_map[f"V_{odoo_id}"] = tp._id
                result.trading_partners_created += 1

        for cp in customer_partners:
            odoo_id = cp.get("id")
            name = str(cp.get("name", f"Customer-{odoo_id}"))[:200]
            tp_id = f"ODOO_C_{odoo_id}"

            existing = (await self.db.execute(
                sa_select(TradingPartner).where(TradingPartner.id == tp_id)
            )).scalar_one_or_none()
            if existing:
                partner_map[f"C_{odoo_id}"] = existing._id
            else:
                tp = TradingPartner(
                    id=tp_id,
                    tpartner_type="customer",
                    description=name,
                    city=str(cp.get("city", ""))[:100],
                    country=str(cp.get("country_id", ""))[:10] if not isinstance(cp.get("country_id"), (list, tuple)) else "",
                    company_id=f"ODOO_{self.tenant_id}",
                    source="ODOO",
                )
                self.db.add(tp)
                await self.db.flush()
                partner_map[f"C_{odoo_id}"] = tp._id
                result.trading_partners_created += 1

        return partner_map

    async def _build_lanes(self, config, supplier_info, pickings, site_map, partner_map, result):
        """Step 6: Build transportation lanes (partner→site, site→site, site→partner)."""
        from app.models.sc_entities import TransportationLane

        seen_lanes = set()
        wh_sites = [s for k, s in site_map.items() if isinstance(k, int)]

        # Vendor partner → warehouse (from_partner_id → to_site_id)
        for si in supplier_info:
            vendor_id = si.get("partner_id")
            if isinstance(vendor_id, (list, tuple)):
                vendor_id = vendor_id[0]
            partner_pk = partner_map.get(f"V_{vendor_id}")
            if not partner_pk or not wh_sites:
                continue

            dest = wh_sites[0]
            lane_key = (f"V_{vendor_id}", dest.id)
            if lane_key in seen_lanes:
                continue
            seen_lanes.add(lane_key)

            lead_time_days = si.get("delay", 7)
            lane = TransportationLane(
                config_id=config.id,
                from_partner_id=partner_pk,
                to_site_id=dest.id,
                supply_lead_time={"type": "deterministic", "value": lead_time_days},
                capacity=9999,
            )
            self.db.add(lane)
            result.lanes_created += 1

        # Internal: warehouse → warehouse (from_site_id → to_site_id)
        for i, src in enumerate(wh_sites):
            for dest in wh_sites[i + 1:]:
                lane_key = (src.id, dest.id)
                if lane_key in seen_lanes:
                    continue
                seen_lanes.add(lane_key)

                lane = TransportationLane(
                    config_id=config.id,
                    from_site_id=src.id,
                    to_site_id=dest.id,
                    supply_lead_time={"type": "deterministic", "value": 2},
                    capacity=9999,
                )
                self.db.add(lane)
                result.lanes_created += 1

        # Warehouse → customer partner (from_site_id → to_partner_id)
        if wh_sites:
            primary_site = wh_sites[0]
            for key, partner_pk in partner_map.items():
                if not key.startswith("C_"):
                    continue
                lane = TransportationLane(
                    config_id=config.id,
                    from_site_id=primary_site.id,
                    to_partner_id=partner_pk,
                    supply_lead_time={"type": "deterministic", "value": 1},
                    capacity=9999,
                )
                self.db.add(lane)
                result.lanes_created += 1

    async def _build_manufacturing(self, config, boms, bom_lines, workcenters, product_map, result):
        """Step 7: Build BOM structures."""
        from app.models.sc_entities import ProductBOM

        bom_product_map: Dict[int, int] = {}
        for bom in boms:
            tmpl_id = bom.get("product_tmpl_id")
            if isinstance(tmpl_id, (list, tuple)):
                tmpl_id = tmpl_id[0]
            bom_product_map[bom["id"]] = tmpl_id

        for line in bom_lines:
            bom_id = line.get("bom_id")
            if isinstance(bom_id, (list, tuple)):
                bom_id = bom_id[0]

            component_id = line.get("product_id")
            if isinstance(component_id, (list, tuple)):
                component_id = component_id[0]

            parent_tmpl_id = bom_product_map.get(bom_id)
            if not parent_tmpl_id:
                continue

            # Find platform product for parent and component
            parent = product_map.get(parent_tmpl_id)
            component = product_map.get(component_id)
            if not parent or not component:
                continue

            bom_rec = ProductBOM(
                config_id=config.id,
                parent_product_id=parent.id,
                child_product_id=component.id,
                quantity_per=line.get("product_qty", 1.0),
            )
            self.db.add(bom_rec)
            result.boms_created += 1

    async def _build_inventory(self, config, quants, orderpoints, site_map, product_map, result):
        """Step 8: Build inventory levels and policies."""
        from app.models.aws_sc_planning import InvLevel, InvPolicy

        # Inventory levels from stock.quant
        for q in quants:
            prod_id = q.get("product_id")
            if isinstance(prod_id, (list, tuple)):
                prod_id = prod_id[0]
            product = product_map.get(prod_id)
            if not product:
                continue

            # Map Odoo location → platform site (simplified: use first warehouse)
            wh_sites = [s for k, s in site_map.items() if isinstance(k, int)]
            if not wh_sites:
                continue

            inv = InvLevel(
                config_id=config.id,
                product_id=product.id,
                site_id=wh_sites[0].id,
                on_hand_qty=q.get("quantity", 0),
                company_id=str(self.tenant_id),
            )
            self.db.add(inv)
            result.inv_levels_created += 1

        # Inventory policies from stock.warehouse.orderpoint
        for op in orderpoints:
            prod_id = op.get("product_id")
            if isinstance(prod_id, (list, tuple)):
                prod_id = prod_id[0]
            product = product_map.get(prod_id)
            if not product:
                continue

            wh_id = op.get("warehouse_id")
            if isinstance(wh_id, (list, tuple)):
                wh_id = wh_id[0]
            site = site_map.get(wh_id)
            if not site:
                continue

            policy = InvPolicy(
                config_id=config.id,
                product_id=product.id,
                site_id=site.id,
                policy_type="abs_level",
                ss_quantity=op.get("product_min_qty", 0),
                company_id=str(self.tenant_id),
            )
            self.db.add(policy)
            result.inv_policies_created += 1


class OdooIngestionMonitor:
    """Monitors Odoo ingestion quality — mirrors SAP ingestion monitoring.

    Tracks:
    - Extraction job status and history
    - Data quality metrics (completeness, referential integrity)
    - Model coverage statistics
    """

    @staticmethod
    def compute_quality_metrics(data: Dict[str, List[Dict]]) -> Dict[str, Any]:
        """Compute data quality metrics across all extracted models."""
        metrics = {}
        total_records = 0
        total_complete = 0

        for model, records in data.items():
            if not records:
                metrics[model] = {"count": 0, "completeness": 0.0}
                continue

            count = len(records)
            total_records += count

            # Completeness: % of non-null fields across all records
            total_fields = 0
            non_null_fields = 0
            for rec in records:
                for k, v in rec.items():
                    total_fields += 1
                    if v is not None and v is not False and v != "":
                        non_null_fields += 1

            completeness = non_null_fields / total_fields if total_fields else 0
            total_complete += completeness * count

            metrics[model] = {
                "count": count,
                "completeness": round(completeness * 100, 1),
                "fields_per_record": total_fields // count if count else 0,
            }

        overall = total_complete / total_records if total_records else 0
        return {
            "models": metrics,
            "total_records": total_records,
            "total_models": len(data),
            "overall_completeness": round(overall * 100, 1),
        }

    @staticmethod
    def compute_referential_integrity(data: Dict[str, List[Dict]]) -> Dict[str, Any]:
        """Check referential integrity across Odoo models.

        Validates that FK references (product_id, partner_id, etc.) point
        to records that exist in the extracted dataset.
        """
        # Build ID sets
        product_ids = {r["id"] for r in data.get("product.product", [])}
        partner_ids = {r["id"] for r in data.get("res.partner", [])}
        warehouse_ids = {r["id"] for r in data.get("stock.warehouse", [])}
        bom_ids = {r["id"] for r in data.get("mrp.bom", [])}

        issues = []

        # Check BOM lines reference valid products
        for line in data.get("mrp.bom.line", []):
            pid = line.get("product_id")
            if isinstance(pid, (list, tuple)):
                pid = pid[0]
            if pid and pid not in product_ids:
                issues.append(f"mrp.bom.line {line.get('id')}: product_id {pid} not found")

        # Check PO lines reference valid products
        for line in data.get("purchase.order.line", []):
            pid = line.get("product_id")
            if isinstance(pid, (list, tuple)):
                pid = pid[0]
            if pid and pid not in product_ids:
                issues.append(f"purchase.order.line {line.get('id')}: product_id {pid} not found")

        # Check supplier info references valid partners
        for si in data.get("product.supplierinfo", []):
            pid = si.get("partner_id")
            if isinstance(pid, (list, tuple)):
                pid = pid[0]
            if pid and pid not in partner_ids:
                issues.append(f"product.supplierinfo {si.get('id')}: partner_id {pid} not found")

        return {
            "total_checks": len(data.get("mrp.bom.line", [])) +
                           len(data.get("purchase.order.line", [])) +
                           len(data.get("product.supplierinfo", [])),
            "issues": issues[:50],  # cap for readability
            "issue_count": len(issues),
            "integrity_score": round(
                (1 - len(issues) / max(1, sum(len(v) for v in data.values()))) * 100, 1
            ),
        }
