"""
SAP Data Staging Service

Orchestrates the full pipeline: SAP extraction → mapping → validation → upsert
into the AWS SC staging tables (Postgres). The AWS SC entity layer becomes the
operational copy; SAP remains the source of truth.

This service:
1. Accepts extracted SAP DataFrames (from any connector: RFC, HANA, OData, CSV)
2. Maps them to AWS SC entity format via SupplyChainMapper
3. Validates data quality (completeness, referential integrity)
4. Upserts into Postgres (merge on business key, don't duplicate)
5. Tracks staging results for reconciliation

All operations are tenant-scoped.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum

import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text as sql_text, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.supply_chain_config import SupplyChainConfig, Site, TransportationLane
from app.models.sc_entities import (
    Company, Geography, TradingPartner, Product, ProductHierarchy,
    SourcingRules, InvPolicy, InvLevel, ProductBom, ProductionProcess,
    Forecast, OutboundOrderLine, InboundOrder, InboundOrderLine,
    InboundOrderLineSchedule, Shipment, SupplyPlan, ProcessHeader,
    ProcessOperation, ProcessProduct, CustomerCost, FulfillmentOrder,
    Backorder,
)
from app.models.supplier import VendorProduct, VendorLeadTime, SupplierPerformance
from app.models.production_order import ProductionOrder, ProductionOrderComponent
from app.models.sc_planning import ProductionCapacity
from app.integrations.sap.data_mapper import SupplyChainMapper

logger = logging.getLogger(__name__)


class StagingEntityType(str, Enum):
    """Entity types that can be staged from SAP."""
    COMPANY = "company"
    GEOGRAPHY = "geography"
    TRADING_PARTNER = "trading_partner"
    SITE = "site"
    PRODUCT = "product"
    SOURCING_RULES = "sourcing_rules"
    INV_POLICY = "inv_policy"
    INV_LEVEL = "inv_level"
    PRODUCT_BOM = "product_bom"
    PRODUCTION_PROCESS = "production_process"
    FORECAST = "forecast"
    VENDOR_PRODUCT = "vendor_product"
    VENDOR_LEAD_TIME = "vendor_lead_time"
    PRODUCT_HIERARCHY = "product_hierarchy"
    PROCESS_HEADER = "process_header"
    CUSTOMER_COST = "customer_cost"
    SUPPLIER_PERFORMANCE = "supplier_performance"
    PRODUCTION_CAPACITY = "production_capacity"
    PURCHASE_ORDER = "purchase_order"
    SALES_ORDER = "sales_order"
    OUTBOUND_ORDER_LINE = "outbound_order_line"
    INBOUND_ORDER = "inbound_order"
    SHIPMENT = "shipment"
    FULFILLMENT_ORDER = "fulfillment_order"
    BACKORDER = "backorder"
    PRODUCTION_ORDER = "production_order"


@dataclass
class StagingResult:
    """Result of staging one entity type."""
    entity_type: StagingEntityType
    records_mapped: int = 0
    records_inserted: int = 0
    records_updated: int = 0
    records_skipped: int = 0
    validation_errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0

    @property
    def total_upserted(self) -> int:
        return self.records_inserted + self.records_updated


@dataclass
class StagingPipelineResult:
    """Result of a full staging pipeline run."""
    config_id: int
    tenant_id: int
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    entity_results: Dict[str, StagingResult] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)

    @property
    def total_records(self) -> int:
        return sum(r.total_upserted for r in self.entity_results.values())

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "config_id": self.config_id,
            "tenant_id": self.tenant_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_records": self.total_records,
            "success": self.success,
            "errors": self.errors,
            "entities": {
                k: {
                    "mapped": v.records_mapped,
                    "inserted": v.records_inserted,
                    "updated": v.records_updated,
                    "skipped": v.records_skipped,
                    "validation_errors": v.validation_errors,
                    "duration_seconds": v.duration_seconds,
                }
                for k, v in self.entity_results.items()
            },
        }


# ============================================================================
# SAP table → entity staging order (respects FK dependencies)
# ============================================================================
STAGING_ORDER: List[Tuple[StagingEntityType, List[str]]] = [
    # Tier 0: Organization — no FK dependencies
    (StagingEntityType.COMPANY, ["T001"]),
    (StagingEntityType.GEOGRAPHY, ["ADRC"]),
    (StagingEntityType.TRADING_PARTNER, ["LFA1", "KNA1"]),
    # Tier 1: Network — depends on company
    (StagingEntityType.SITE, ["T001W"]),
    (StagingEntityType.PRODUCT, ["MARA", "MAKT"]),
    (StagingEntityType.PRODUCT_HIERARCHY, ["T179"]),
    # Tier 2: Relationships — depends on site + product
    (StagingEntityType.SOURCING_RULES, ["EORD"]),
    (StagingEntityType.INV_POLICY, ["MARC"]),
    (StagingEntityType.PRODUCTION_PROCESS, ["PLKO", "PLPO"]),
    (StagingEntityType.PROCESS_HEADER, ["PLKO", "PLPO"]),
    (StagingEntityType.PRODUCT_BOM, ["STPO", "STKO", "MARC"]),
    (StagingEntityType.VENDOR_PRODUCT, ["EINA", "EINE"]),
    (StagingEntityType.VENDOR_LEAD_TIME, ["EINA", "EINE", "EORD"]),
    (StagingEntityType.PRODUCTION_CAPACITY, ["CRHD"]),
    # Tier 3: Planning data — depends on product + site
    (StagingEntityType.INV_LEVEL, ["MARD"]),
    (StagingEntityType.FORECAST, ["PBIM", "PBED"]),
    # Tier 4: Transactional — depends on all above
    (StagingEntityType.PURCHASE_ORDER, ["EKKO", "EKPO"]),
    (StagingEntityType.INBOUND_ORDER, ["EKKO", "EKPO"]),
    (StagingEntityType.SALES_ORDER, ["VBAK", "VBAP"]),
    (StagingEntityType.OUTBOUND_ORDER_LINE, ["VBAK", "VBAP"]),
    (StagingEntityType.SHIPMENT, ["LIKP", "LIPS"]),
    (StagingEntityType.FULFILLMENT_ORDER, ["LIKP", "LIPS"]),
    (StagingEntityType.PRODUCTION_ORDER, ["AFKO", "AFPO"]),
    # Tier 5: Derived — depends on transactional
    (StagingEntityType.BACKORDER, ["VBAK", "VBAP"]),
    (StagingEntityType.CUSTOMER_COST, ["KONV"]),
    (StagingEntityType.SUPPLIER_PERFORMANCE, ["EKBE"]),
]


class SAPDataStagingService:
    """
    Orchestrates SAP data staging into the AWS SC entity layer.

    Usage:
        service = SAPDataStagingService(db, tenant_id=3, config_id=22)
        result = await service.stage_all(sap_data)
        # or stage individual entities:
        result = await service.stage_entity(StagingEntityType.PRODUCT, sap_data)
    """

    def __init__(
        self,
        db: AsyncSession,
        tenant_id: int,
        config_id: int,
        company_id: Optional[str] = None,
    ):
        self.db = db
        self.tenant_id = tenant_id
        self.config_id = config_id
        self.company_id = company_id
        self.mapper = SupplyChainMapper()

        # Caches populated during staging for cross-entity references
        self._site_key_to_id: Dict[str, int] = {}
        self._product_ids: set = set()

    async def _load_site_map(self):
        """Load existing site key→id mapping for this config."""
        result = await self.db.execute(
            select(Site.id, Site.key).where(Site.config_id == self.config_id)
        )
        self._site_key_to_id = {row.key: row.id for row in result.all()}

    async def _load_product_ids(self):
        """Load existing product IDs for this config."""
        result = await self.db.execute(
            select(Product.id).where(Product.config_id == self.config_id)
        )
        self._product_ids = {row[0] for row in result.all()}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def stage_all(
        self,
        sap_data: Dict[str, pd.DataFrame],
        entity_filter: Optional[List[StagingEntityType]] = None,
    ) -> StagingPipelineResult:
        """
        Run the full staging pipeline for all (or filtered) entity types.

        Args:
            sap_data: Dict of SAP table name → DataFrame
            entity_filter: If set, only stage these entity types
        """
        pipeline_result = StagingPipelineResult(
            config_id=self.config_id,
            tenant_id=self.tenant_id,
        )

        # Pre-load caches
        await self._load_site_map()
        await self._load_product_ids()

        for entity_type, required_tables in STAGING_ORDER:
            if entity_filter and entity_type not in entity_filter:
                continue

            # Check if we have at least one required table
            has_data = any(
                t in sap_data and not sap_data[t].empty for t in required_tables
            )
            if not has_data:
                logger.debug(f"Skipping {entity_type.value}: no data for {required_tables}")
                continue

            try:
                result = await self.stage_entity(entity_type, sap_data)
                pipeline_result.entity_results[entity_type.value] = result
            except Exception as e:
                logger.error(f"Error staging {entity_type.value}: {e}", exc_info=True)
                pipeline_result.errors.append(f"{entity_type.value}: {str(e)}")

        pipeline_result.completed_at = datetime.utcnow()
        await self.db.commit()

        logger.info(
            f"Staging complete: {pipeline_result.total_records} records "
            f"across {len(pipeline_result.entity_results)} entities"
        )
        return pipeline_result

    async def stage_entity(
        self,
        entity_type: StagingEntityType,
        sap_data: Dict[str, pd.DataFrame],
    ) -> StagingResult:
        """Stage a single entity type from SAP data."""
        start = datetime.utcnow()
        result = StagingResult(entity_type=entity_type)

        handler = self._get_handler(entity_type)
        if handler is None:
            result.validation_errors.append(f"No handler for {entity_type.value}")
            return result

        mapped_df = handler(sap_data)
        if mapped_df is None or mapped_df.empty:
            return result

        result.records_mapped = len(mapped_df)

        upsert_result = await self._upsert_entity(entity_type, mapped_df)
        result.records_inserted = upsert_result.get("inserted", 0)
        result.records_updated = upsert_result.get("updated", 0)
        result.records_skipped = upsert_result.get("skipped", 0)
        result.validation_errors.extend(upsert_result.get("errors", []))

        elapsed = (datetime.utcnow() - start).total_seconds()
        result.duration_seconds = elapsed

        logger.info(
            f"Staged {entity_type.value}: {result.records_inserted} inserted, "
            f"{result.records_updated} updated, {result.records_skipped} skipped "
            f"({elapsed:.1f}s)"
        )
        return result

    # ------------------------------------------------------------------
    # Mapping handlers — each extracts the right tables and calls mapper
    # ------------------------------------------------------------------

    def _get_handler(self, entity_type: StagingEntityType):
        """Return the mapping handler function for an entity type."""
        return {
            StagingEntityType.COMPANY: self._map_company,
            StagingEntityType.GEOGRAPHY: self._map_geography,
            StagingEntityType.TRADING_PARTNER: self._map_trading_partners,
            StagingEntityType.SITE: self._map_sites,
            StagingEntityType.PRODUCT: self._map_products,
            StagingEntityType.PRODUCT_HIERARCHY: self._map_product_hierarchy,
            StagingEntityType.SOURCING_RULES: self._map_sourcing_rules,
            StagingEntityType.INV_POLICY: self._map_inv_policy,
            StagingEntityType.INV_LEVEL: self._map_inv_level,
            StagingEntityType.PRODUCT_BOM: self._map_product_bom,
            StagingEntityType.PRODUCTION_PROCESS: self._map_production_process,
            StagingEntityType.PROCESS_HEADER: self._map_process_headers,
            StagingEntityType.PRODUCTION_CAPACITY: self._map_production_capacity,
            StagingEntityType.FORECAST: self._map_forecast,
            StagingEntityType.VENDOR_PRODUCT: self._map_vendor_products,
            StagingEntityType.VENDOR_LEAD_TIME: self._map_vendor_lead_times,
            StagingEntityType.PURCHASE_ORDER: self._map_purchase_orders,
            StagingEntityType.INBOUND_ORDER: self._map_inbound_orders,
            StagingEntityType.SALES_ORDER: self._map_sales_orders,
            StagingEntityType.OUTBOUND_ORDER_LINE: self._map_outbound_order_lines,
            StagingEntityType.SHIPMENT: self._map_shipments,
            StagingEntityType.FULFILLMENT_ORDER: self._map_fulfillment_orders,
            StagingEntityType.PRODUCTION_ORDER: self._map_production_orders,
            StagingEntityType.BACKORDER: self._map_backorders,
            StagingEntityType.CUSTOMER_COST: self._map_customer_costs,
            StagingEntityType.SUPPLIER_PERFORMANCE: self._map_supplier_performance,
        }.get(entity_type)

    def _df(self, sap_data: Dict[str, pd.DataFrame], table: str) -> pd.DataFrame:
        """Get a table from sap_data, returning empty DataFrame if missing."""
        return sap_data.get(table, pd.DataFrame())

    def _map_company(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        return self.mapper.map_company(self._df(sap_data, "T001"))

    def _map_geography(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        return self.mapper.map_geography(self._df(sap_data, "ADRC"))

    def _map_trading_partners(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        return self.mapper.map_trading_partners(
            self._df(sap_data, "LFA1"), self._df(sap_data, "KNA1"),
        )

    def _map_sites(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        return self.mapper.map_s4hana_plants_to_sites(self._df(sap_data, "T001W"))

    def _map_products(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        mara = self._df(sap_data, "MARA")
        makt = self._df(sap_data, "MAKT")
        mbew = self._df(sap_data, "MBEW")
        # Enrich MARA with descriptions from MAKT
        if not mara.empty and not makt.empty and "MATNR" in makt.columns:
            if "MAKTX" not in mara.columns:
                desc = makt[["MATNR", "MAKTX"]].drop_duplicates(subset=["MATNR"])
                mara = mara.merge(desc, on="MATNR", how="left")
        if mara.empty:
            return pd.DataFrame()
        return self.mapper.map_s4hana_materials_to_products(mara, mbew_df=mbew if not mbew.empty else None)

    def _map_sourcing_rules(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        return self.mapper.map_sourcing_rules(self._df(sap_data, "EORD"))

    def _map_inv_policy(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        return self.mapper.map_marc_to_inv_policy(self._df(sap_data, "MARC"))

    def _map_inv_level(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        return self.mapper.map_s4hana_inventory_to_inventory_levels(self._df(sap_data, "MARD"))

    def _map_product_bom(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        return self.mapper.map_bom_items(
            self._df(sap_data, "STPO"),
            self._df(sap_data, "STKO"),
            self._df(sap_data, "MARC"),
        )

    def _map_production_process(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        marc = self._df(sap_data, "MARC")
        return self.mapper.map_production_process(
            self._df(sap_data, "PLKO"), self._df(sap_data, "PLPO"),
            marc_df=marc if not marc.empty else None,
        )

    def _map_forecast(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        # Try S/4HANA PIR first, then APO SNP
        pbim = self._df(sap_data, "PBIM")
        pbed = self._df(sap_data, "PBED")
        if not pbed.empty:
            return self.mapper.map_s4hana_pir_to_forecasts(pbim, pbed)
        # Fallback to APO SNP if available
        snp = self._df(sap_data, "/SAPAPO/SNPFC")
        if not snp.empty:
            return self.mapper.map_apo_snp_to_demand_plans(snp)
        return pd.DataFrame()

    def _map_vendor_products(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        return self.mapper.map_vendor_products(
            self._df(sap_data, "EINA"), self._df(sap_data, "EINE"),
        )

    def _map_vendor_lead_times(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        return self.mapper.map_vendor_lead_times(
            self._df(sap_data, "EINA"),
            self._df(sap_data, "EINE"),
            self._df(sap_data, "EORD"),
        )

    def _map_purchase_orders(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        ekko = self._df(sap_data, "EKKO")
        ekpo = self._df(sap_data, "EKPO")
        if ekko.empty or ekpo.empty:
            return pd.DataFrame()
        return self.mapper.map_s4hana_po_to_purchase_orders(ekko, ekpo)

    def _map_sales_orders(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        vbak = self._df(sap_data, "VBAK")
        vbap = self._df(sap_data, "VBAP")
        if vbak.empty or vbap.empty:
            return pd.DataFrame()
        vbep = self._df(sap_data, "VBEP")
        vbuk = self._df(sap_data, "VBUK")
        return self.mapper.map_s4hana_so_to_sales_orders(
            vbak, vbap,
            vbep_df=vbep if not vbep.empty else None,
            vbuk_df=vbuk if not vbuk.empty else None,
        )

    def _map_shipments(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        likp = self._df(sap_data, "LIKP")
        lips = self._df(sap_data, "LIPS")
        if likp.empty or lips.empty:
            return pd.DataFrame()
        return self.mapper.map_s4hana_deliveries_to_shipments(likp, lips)

    def _map_production_orders(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        afko = self._df(sap_data, "AFKO")
        afpo = self._df(sap_data, "AFPO")
        if afko.empty:
            return pd.DataFrame()
        return self.mapper.map_s4hana_production_orders(afko, afpo)

    def _map_product_hierarchy(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        t179 = self._df(sap_data, "T179")
        t179t = self._df(sap_data, "T179T")
        if t179.empty:
            return pd.DataFrame()
        return self.mapper.map_product_hierarchy(t179, t179t_df=t179t if not t179t.empty else None)

    def _map_process_headers(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """Maps PLKO/PLPO to ProcessHeader+ProcessOperation+ProcessProduct (composite)."""
        plko = self._df(sap_data, "PLKO")
        plpo = self._df(sap_data, "PLPO")
        if plpo.empty:
            return pd.DataFrame()
        marc = self._df(sap_data, "MARC")
        result = self.mapper.map_process_operations(plko, plpo, marc_df=marc if not marc.empty else None)
        # Store sub-DataFrames for composite upsert
        self._process_ops_result = result
        return result.get("headers", pd.DataFrame())

    def _map_production_capacity(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        crhd = self._df(sap_data, "CRHD")
        kako = self._df(sap_data, "KAKO")
        if crhd.empty:
            return pd.DataFrame()
        return self.mapper.map_production_capacity(crhd, kako_df=kako if not kako.empty else None)

    def _map_inbound_orders(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """Maps EKKO/EKPO/EKET/EKBE to InboundOrder+InboundOrderLine+Schedule (composite)."""
        ekko = self._df(sap_data, "EKKO")
        ekpo = self._df(sap_data, "EKPO")
        if ekpo.empty:
            return pd.DataFrame()
        eket = self._df(sap_data, "EKET")
        ekbe = self._df(sap_data, "EKBE")
        result = self.mapper.map_inbound_orders(
            ekko, ekpo,
            eket_df=eket if not eket.empty else None,
            ekbe_df=ekbe if not ekbe.empty else None,
        )
        self._inbound_orders_result = result
        return result.get("orders", pd.DataFrame())

    def _map_outbound_order_lines(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        vbak = self._df(sap_data, "VBAK")
        vbap = self._df(sap_data, "VBAP")
        if vbap.empty:
            return pd.DataFrame()
        vbep = self._df(sap_data, "VBEP")
        vbuk = self._df(sap_data, "VBUK")
        return self.mapper.map_outbound_order_lines(
            vbak, vbap,
            vbep_df=vbep if not vbep.empty else None,
            vbuk_df=vbuk if not vbuk.empty else None,
        )

    def _map_fulfillment_orders(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        likp = self._df(sap_data, "LIKP")
        lips = self._df(sap_data, "LIPS")
        if lips.empty:
            return pd.DataFrame()
        ltak = self._df(sap_data, "LTAK")
        ltap = self._df(sap_data, "LTAP")
        return self.mapper.map_fulfillment_orders(
            likp, lips,
            ltak_df=ltak if not ltak.empty else None,
            ltap_df=ltap if not ltap.empty else None,
        )

    def _map_backorders(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        vbak = self._df(sap_data, "VBAK")
        vbap = self._df(sap_data, "VBAP")
        if vbap.empty:
            return pd.DataFrame()
        vbup = self._df(sap_data, "VBUP")
        vbep = self._df(sap_data, "VBEP")
        return self.mapper.map_backorders(
            vbak, vbap,
            vbup_df=vbup if not vbup.empty else None,
            vbep_df=vbep if not vbep.empty else None,
        )

    def _map_customer_costs(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        konv = self._df(sap_data, "KONV")
        if konv.empty:
            return pd.DataFrame()
        vbak = self._df(sap_data, "VBAK")
        vbap = self._df(sap_data, "VBAP")
        return self.mapper.map_customer_costs(
            konv,
            vbak_df=vbak if not vbak.empty else None,
            vbap_df=vbap if not vbap.empty else None,
        )

    def _map_supplier_performance(self, sap_data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        ekbe = self._df(sap_data, "EKBE")
        if ekbe.empty:
            return pd.DataFrame()
        eket = self._df(sap_data, "EKET")
        ekpo = self._df(sap_data, "EKPO")
        return self.mapper.map_supplier_performance(
            ekbe,
            eket_df=eket if not eket.empty else None,
            ekpo_df=ekpo if not ekpo.empty else None,
        )

    # ------------------------------------------------------------------
    # Upsert logic — per entity type
    # ------------------------------------------------------------------

    async def _upsert_entity(
        self, entity_type: StagingEntityType, mapped_df: pd.DataFrame,
    ) -> Dict[str, Any]:
        """
        Upsert mapped DataFrame into the target table.

        Returns dict with inserted/updated/skipped/errors counts.
        """
        upsert_map = {
            StagingEntityType.COMPANY: self._upsert_company,
            StagingEntityType.GEOGRAPHY: self._upsert_geography,
            StagingEntityType.TRADING_PARTNER: self._upsert_trading_partners,
            StagingEntityType.SITE: self._upsert_sites,
            StagingEntityType.PRODUCT: self._upsert_products,
            StagingEntityType.PRODUCT_HIERARCHY: self._upsert_product_hierarchy,
            StagingEntityType.INV_POLICY: self._upsert_inv_policy,
            StagingEntityType.INV_LEVEL: self._upsert_inv_level,
            StagingEntityType.PRODUCT_BOM: self._upsert_product_bom,
            StagingEntityType.FORECAST: self._upsert_forecast,
            StagingEntityType.VENDOR_PRODUCT: self._upsert_vendor_products,
            StagingEntityType.VENDOR_LEAD_TIME: self._upsert_vendor_lead_times,
            StagingEntityType.SOURCING_RULES: self._upsert_sourcing_rules,
            StagingEntityType.PRODUCTION_PROCESS: self._upsert_production_process,
            StagingEntityType.PROCESS_HEADER: self._upsert_process_headers,
            StagingEntityType.PRODUCTION_CAPACITY: self._upsert_production_capacity,
            StagingEntityType.INBOUND_ORDER: self._upsert_inbound_orders,
            StagingEntityType.OUTBOUND_ORDER_LINE: self._upsert_outbound_order_lines,
            StagingEntityType.FULFILLMENT_ORDER: self._upsert_fulfillment_orders,
            StagingEntityType.BACKORDER: self._upsert_backorders,
            StagingEntityType.CUSTOMER_COST: self._upsert_customer_costs,
            StagingEntityType.SUPPLIER_PERFORMANCE: self._upsert_supplier_performance,
        }

        handler = upsert_map.get(entity_type)
        if handler:
            return await handler(mapped_df)

        # For entity types without custom upsert, log and skip
        logger.warning(
            f"No upsert handler for {entity_type.value} — "
            f"{len(mapped_df)} records mapped but not persisted"
        )
        return {"inserted": 0, "updated": 0, "skipped": len(mapped_df), "errors": []}

    # ------------------------------------------------------------------
    # Individual upsert implementations
    # ------------------------------------------------------------------

    async def _upsert_company(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Upsert Company records. Business key: company_id."""
        inserted = 0
        updated = 0
        for _, row in df.iterrows():
            cid = str(row.get("company_id", "")).strip()
            if not cid:
                continue
            existing = await self.db.get(Company, cid)
            if existing:
                existing.description = row.get("company_name", existing.description)
                existing.country = row.get("country", existing.country)
                updated += 1
            else:
                self.db.add(Company(
                    id=cid,
                    description=row.get("company_name", ""),
                    country=row.get("country", ""),
                ))
                inserted += 1
        await self.db.flush()
        return {"inserted": inserted, "updated": updated, "skipped": 0, "errors": []}

    async def _upsert_geography(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Upsert Geography records. Business key: address_id."""
        inserted = 0
        updated = 0
        for _, row in df.iterrows():
            aid = str(row.get("address_id", "")).strip()
            if not aid:
                continue
            geo_id = f"GEO_{aid}"
            existing = await self.db.get(Geography, geo_id)
            if existing:
                existing.city = row.get("city", existing.city)
                existing.state_prov = row.get("region", existing.state_prov)
                existing.country = row.get("country", existing.country)
                existing.postal_code = row.get("postal_code", existing.postal_code)
                existing.source = "SAP_ADRC"
                updated += 1
            else:
                self.db.add(Geography(
                    id=geo_id,
                    description=row.get("name", ""),
                    company_id=self.company_id,
                    address_1=row.get("street", ""),
                    city=row.get("city", ""),
                    state_prov=row.get("region", ""),
                    country=row.get("country", ""),
                    postal_code=row.get("postal_code", ""),
                    source="SAP_ADRC",
                ))
                inserted += 1
        await self.db.flush()
        return {"inserted": inserted, "updated": updated, "skipped": 0, "errors": []}

    async def _upsert_trading_partners(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Upsert TradingPartner records. Business key: id."""
        inserted = 0
        updated = 0
        for _, row in df.iterrows():
            tp_id = str(row.get("id", "")).strip()
            if not tp_id:
                continue
            # Check by business key (unique column)
            result = await self.db.execute(
                select(TradingPartner).where(TradingPartner.id == tp_id)
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.description = row.get("description", existing.description)
                existing.city = row.get("city", existing.city)
                existing.country = row.get("country", existing.country)
                existing.is_active = row.get("is_active", existing.is_active)
                existing.source = row.get("source", existing.source)
                existing.source_update_dttm = datetime.utcnow()
                updated += 1
            else:
                self.db.add(TradingPartner(
                    id=tp_id,
                    tpartner_type=row.get("tpartner_type", "vendor"),
                    description=row.get("description", ""),
                    company_id=self.company_id,
                    address_1=row.get("address_1", ""),
                    city=row.get("city", ""),
                    state_prov=row.get("state_prov", ""),
                    postal_code=row.get("postal_code", ""),
                    country=row.get("country", ""),
                    phone_number=row.get("phone_number", ""),
                    is_active=row.get("is_active", "true"),
                    source=row.get("source", "SAP"),
                    source_update_dttm=datetime.utcnow(),
                ))
                inserted += 1
        await self.db.flush()
        return {"inserted": inserted, "updated": updated, "skipped": 0, "errors": []}

    async def _upsert_sites(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Upsert Site records into existing config. Business key: site_id (WERKS)."""
        inserted = 0
        updated = 0
        for _, row in df.iterrows():
            site_key = str(row.get("site_id", "")).strip()
            if not site_key:
                continue

            if site_key in self._site_key_to_id:
                # Update existing
                site_id = self._site_key_to_id[site_key]
                result = await self.db.get(Site, site_id)
                if result:
                    result.name = row.get("site_name", result.name)
                    result.address = row.get("address", result.address)
                    result.city = row.get("city", result.city)
                    result.country = row.get("country", result.country)
                    updated += 1
            else:
                site = Site(
                    config_id=self.config_id,
                    key=site_key,
                    name=row.get("site_name", site_key),
                    sc_site_type=row.get("site_type", "PLANT"),
                    master_type="INVENTORY",  # Default; refined by config builder
                    address=row.get("address", ""),
                    city=row.get("city", ""),
                    state=row.get("state", ""),
                    country=row.get("country", ""),
                    postal_code=row.get("postal_code", ""),
                )
                self.db.add(site)
                await self.db.flush()
                self._site_key_to_id[site_key] = site.id
                inserted += 1

        return {"inserted": inserted, "updated": updated, "skipped": 0, "errors": []}

    async def _upsert_products(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Upsert Product records. Business key: product_id (MATNR)."""
        inserted = 0
        updated = 0
        for _, row in df.iterrows():
            pid = str(row.get("product_id", "")).strip()
            if not pid:
                continue

            existing = await self.db.get(Product, pid)
            if existing:
                existing.description = row.get("product_name", existing.description)
                existing.base_uom = row.get("unit_of_measure", existing.base_uom)
                if row.get("weight") and not pd.isna(row["weight"]):
                    existing.weight = float(row["weight"])
                existing.source = "SAP_MARA"
                existing.source_update_dttm = datetime.utcnow()
                updated += 1
            else:
                self.db.add(Product(
                    id=pid,
                    description=row.get("product_name", pid),
                    company_id=self.company_id,
                    config_id=self.config_id,
                    base_uom=row.get("unit_of_measure", "EA"),
                    weight=float(row["weight"]) if row.get("weight") and not pd.isna(row.get("weight")) else None,
                    weight_uom=row.get("weight_unit", "KG"),
                    volume=float(row["volume"]) if row.get("volume") and not pd.isna(row.get("volume")) else None,
                    volume_uom=row.get("volume_unit", "M3"),
                    is_active="true" if row.get("is_active", True) else "false",
                    source="SAP_MARA",
                    source_update_dttm=datetime.utcnow(),
                ))
                self._product_ids.add(pid)
                inserted += 1
        await self.db.flush()
        return {"inserted": inserted, "updated": updated, "skipped": 0, "errors": []}

    async def _upsert_inv_policy(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Upsert InvPolicy records. Business key: (product_id, site_id)."""
        inserted = 0
        updated = 0
        errors = []
        for _, row in df.iterrows():
            pid = str(row.get("product_id", "")).strip()
            site_key = str(row.get("site_id", "")).strip()
            if not pid or not site_key:
                continue

            site_id = self._site_key_to_id.get(site_key)
            if site_id is None:
                errors.append(f"InvPolicy: unknown site {site_key} for product {pid}")
                continue

            result = await self.db.execute(
                select(InvPolicy).where(
                    InvPolicy.product_id == pid,
                    InvPolicy.site_id == site_id,
                    InvPolicy.config_id == self.config_id,
                )
            )
            existing = result.scalar_one_or_none()
            ss_qty = float(row.get("ss_quantity", 0))
            lt_days = int(row.get("lead_time_days", 0))

            if existing:
                existing.ss_policy = row.get("ss_policy", existing.ss_policy)
                existing.ss_quantity = ss_qty
                existing.review_period = lt_days
                existing.source = "SAP_MARC"
                existing.source_update_dttm = datetime.utcnow()
                updated += 1
            else:
                self.db.add(InvPolicy(
                    company_id=self.company_id,
                    site_id=site_id,
                    product_id=pid,
                    config_id=self.config_id,
                    ss_policy=row.get("ss_policy", "abs_level"),
                    ss_quantity=ss_qty,
                    review_period=lt_days,
                    is_active="true",
                    source="SAP_MARC",
                    source_update_dttm=datetime.utcnow(),
                ))
                inserted += 1
        await self.db.flush()
        return {"inserted": inserted, "updated": updated, "skipped": 0, "errors": errors}

    async def _upsert_inv_level(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Upsert InvLevel records. Business key: (product_id, site_id, inventory_date)."""
        inserted = 0
        updated = 0
        errors = []
        today = date.today()
        for _, row in df.iterrows():
            pid = str(row.get("product_id", "")).strip()
            site_key = str(row.get("site_id", "")).strip()
            if not pid or not site_key:
                continue
            site_id = self._site_key_to_id.get(site_key)
            if site_id is None:
                continue

            result = await self.db.execute(
                select(InvLevel).where(
                    InvLevel.product_id == pid,
                    InvLevel.site_id == site_id,
                    InvLevel.inventory_date == today,
                    InvLevel.config_id == self.config_id,
                )
            )
            existing = result.scalar_one_or_none()
            on_hand = float(row.get("available_quantity", 0))
            in_transit = float(row.get("in_transit_quantity", 0))
            reserved = float(row.get("reserved_quantity", 0))

            if existing:
                existing.on_hand_qty = on_hand
                existing.in_transit_qty = in_transit
                existing.reserved_qty = reserved
                existing.available_qty = max(0, on_hand - reserved)
                existing.source = "SAP_MARD"
                existing.source_update_dttm = datetime.utcnow()
                updated += 1
            else:
                self.db.add(InvLevel(
                    company_id=self.company_id,
                    product_id=pid,
                    site_id=site_id,
                    config_id=self.config_id,
                    inventory_date=today,
                    on_hand_qty=on_hand,
                    in_transit_qty=in_transit,
                    reserved_qty=reserved,
                    available_qty=max(0, on_hand - reserved),
                    source="SAP_MARD",
                    source_update_dttm=datetime.utcnow(),
                ))
                inserted += 1
        await self.db.flush()
        return {"inserted": inserted, "updated": updated, "skipped": 0, "errors": errors}

    async def _upsert_product_bom(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Upsert ProductBom records. Business key: (product_id, component_product_id, config_id)."""
        inserted = 0
        updated = 0
        for _, row in df.iterrows():
            pid = str(row.get("product_id", "")).strip()
            comp_id = str(row.get("component_product_id", "")).strip()
            if not pid or not comp_id:
                continue

            result = await self.db.execute(
                select(ProductBom).where(
                    ProductBom.product_id == pid,
                    ProductBom.component_product_id == comp_id,
                    ProductBom.config_id == self.config_id,
                )
            )
            existing = result.scalar_one_or_none()
            comp_qty = float(row.get("component_quantity", 1))
            scrap = float(row.get("scrap_percentage", 0))

            if existing:
                existing.component_quantity = comp_qty
                existing.scrap_percentage = scrap
                existing.source = "SAP_STPO"
                existing.source_update_dttm = datetime.utcnow()
                updated += 1
            else:
                self.db.add(ProductBom(
                    company_id=self.company_id,
                    product_id=pid,
                    component_product_id=comp_id,
                    config_id=self.config_id,
                    component_quantity=comp_qty,
                    component_uom=row.get("component_uom", "EA"),
                    scrap_percentage=scrap,
                    alternate_group=int(row.get("alternate_group", 1)),
                    priority=int(row.get("priority", 1)),
                    is_active=row.get("is_active", "true"),
                    source="SAP_STPO",
                    source_update_dttm=datetime.utcnow(),
                ))
                inserted += 1
        await self.db.flush()
        return {"inserted": inserted, "updated": updated, "skipped": 0, "errors": []}

    async def _upsert_forecast(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Upsert Forecast records. Business key: (product_id, site_id, forecast_date)."""
        inserted = 0
        updated = 0
        errors = []
        for _, row in df.iterrows():
            pid = str(row.get("product_id", "")).strip()
            site_key = str(row.get("site_id", "")).strip()
            if not pid or not site_key:
                continue
            site_id = self._site_key_to_id.get(site_key)
            if site_id is None:
                continue
            fdate = row.get("forecast_date")
            if pd.isna(fdate):
                continue
            fdate = pd.Timestamp(fdate).date() if not isinstance(fdate, date) else fdate

            result = await self.db.execute(
                select(Forecast).where(
                    Forecast.product_id == pid,
                    Forecast.site_id == site_id,
                    Forecast.forecast_date == fdate,
                    Forecast.config_id == self.config_id,
                )
            )
            existing = result.scalar_one_or_none()
            qty = float(row.get("forecast_quantity", 0))

            if existing:
                existing.forecast_quantity = qty
                existing.forecast_p50 = qty
                existing.source = row.get("source", existing.source)
                existing.source_update_dttm = datetime.utcnow()
                updated += 1
            else:
                self.db.add(Forecast(
                    company_id=self.company_id,
                    product_id=pid,
                    site_id=site_id,
                    config_id=self.config_id,
                    forecast_date=fdate,
                    forecast_quantity=qty,
                    forecast_p50=qty,
                    forecast_type=row.get("forecast_type", "statistical"),
                    forecast_level=row.get("forecast_level", "product"),
                    forecast_method=row.get("forecast_method", "sap_pir"),
                    is_active="true",
                    source=row.get("source", "SAP_PIR"),
                    source_update_dttm=datetime.utcnow(),
                ))
                inserted += 1
        await self.db.flush()
        return {"inserted": inserted, "updated": updated, "skipped": 0, "errors": errors}

    async def _upsert_vendor_products(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Upsert VendorProduct records. Business key: (tpartner_id, product_id)."""
        inserted = 0
        updated = 0
        errors = []
        for _, row in df.iterrows():
            vendor_id = str(row.get("vendor_id", "")).strip()
            pid = str(row.get("product_id", "")).strip()
            if not vendor_id or not pid:
                continue

            result = await self.db.execute(
                select(VendorProduct).where(
                    VendorProduct.tpartner_id == vendor_id,
                    VendorProduct.product_id == pid,
                )
            )
            existing = result.scalar_one_or_none()
            net_price = float(row.get("net_price", 0))
            price_unit = float(row.get("price_unit", 1)) or 1
            unit_cost = net_price / price_unit

            if existing:
                existing.vendor_unit_cost = unit_cost
                existing.currency = row.get("currency", existing.currency)
                existing.minimum_order_quantity = float(row.get("min_order_qty", 0)) or None
                existing.source = "SAP_EINA"
                existing.source_update_dttm = datetime.utcnow()
                updated += 1
            else:
                self.db.add(VendorProduct(
                    company_id=self.company_id,
                    tpartner_id=vendor_id,
                    product_id=pid,
                    vendor_unit_cost=unit_cost,
                    currency=row.get("currency", "USD"),
                    minimum_order_quantity=float(row.get("min_order_qty", 0)) or None,
                    is_active="true",
                    source="SAP_EINA",
                    source_update_dttm=datetime.utcnow(),
                ))
                inserted += 1
        await self.db.flush()
        return {"inserted": inserted, "updated": updated, "skipped": 0, "errors": errors}

    async def _upsert_vendor_lead_times(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Upsert VendorLeadTime records. Business key: (tpartner_id, product_id, site_id)."""
        inserted = 0
        updated = 0
        for _, row in df.iterrows():
            vendor_id = str(row.get("vendor_id", "")).strip()
            pid = str(row.get("product_id", "")).strip()
            site_key = str(row.get("site_id", "")).strip()
            if not vendor_id or not pid:
                continue
            site_id = self._site_key_to_id.get(site_key) if site_key else None
            lt_days = float(row.get("lead_time_days", 0))
            if lt_days <= 0:
                continue

            filters = [
                VendorLeadTime.tpartner_id == vendor_id,
                VendorLeadTime.product_id == pid,
            ]
            if site_id:
                filters.append(VendorLeadTime.site_id == site_id)

            result = await self.db.execute(select(VendorLeadTime).where(*filters))
            existing = result.scalar_one_or_none()

            if existing:
                existing.lead_time_days = lt_days
                existing.source = "SAP_EINE"
                existing.source_update_dttm = datetime.utcnow()
                updated += 1
            else:
                self.db.add(VendorLeadTime(
                    company_id=self.company_id,
                    tpartner_id=vendor_id,
                    product_id=pid,
                    site_id=site_id,
                    lead_time_days=lt_days,
                    source="SAP_EINE",
                    source_update_dttm=datetime.utcnow(),
                ))
                inserted += 1
        await self.db.flush()
        return {"inserted": inserted, "updated": updated, "skipped": 0, "errors": []}

    async def _upsert_sourcing_rules(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Upsert SourcingRules. Business key: (product_id, site_id, source_id)."""
        inserted = 0
        updated = 0
        for _, row in df.iterrows():
            pid = str(row.get("product_id", "")).strip()
            site_key = str(row.get("site_id", "")).strip()
            source_id = str(row.get("source_id", "")).strip()
            if not pid or not site_key or not source_id:
                continue
            site_id = self._site_key_to_id.get(site_key)
            if site_id is None:
                continue

            source_type = row.get("source_type", "buy")
            rule_id = f"SR_{pid}_{site_key}_{source_id}"

            existing = await self.db.get(SourcingRules, rule_id)
            if existing:
                existing.sourcing_priority = int(row.get("priority", 1))
                existing.sourcing_rule_type = source_type
                existing.source = "SAP_EORD"
                existing.source_update_dttm = datetime.utcnow()
                updated += 1
            else:
                self.db.add(SourcingRules(
                    id=rule_id,
                    company_id=self.company_id,
                    product_id=pid,
                    to_site_id=site_id,
                    tpartner_id=source_id,
                    config_id=self.config_id,
                    sourcing_rule_type=source_type,
                    sourcing_priority=int(row.get("priority", 1)),
                    is_active="true",
                    source="SAP_EORD",
                    source_update_dttm=datetime.utcnow(),
                ))
                inserted += 1
        await self.db.flush()
        return {"inserted": inserted, "updated": updated, "skipped": 0, "errors": []}

    async def _upsert_production_process(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Upsert ProductionProcess. Business key: process_id."""
        inserted = 0
        updated = 0
        for _, row in df.iterrows():
            proc_id = str(row.get("process_id", "")).strip()
            if not proc_id:
                continue
            site_key = str(row.get("site_id", "")).strip()
            site_id = self._site_key_to_id.get(site_key) if site_key else None

            pp_id = f"PP_{proc_id}_{row.get('operation_number', '0010')}"
            existing = await self.db.get(ProductionProcess, pp_id)

            setup_time = float(row.get("setup_time", 0))
            machine_time = float(row.get("machine_time", 0))
            base_qty = float(row.get("base_quantity", 1)) or 1

            if existing:
                existing.setup_time = setup_time
                existing.operation_time = machine_time / base_qty
                existing.source = "SAP_PLKO"
                existing.source_update_dttm = datetime.utcnow()
                updated += 1
            else:
                self.db.add(ProductionProcess(
                    id=pp_id,
                    company_id=self.company_id,
                    site_id=site_id,
                    config_id=self.config_id,
                    setup_time=setup_time,
                    operation_time=machine_time / base_qty,
                    is_active="true",
                    source="SAP_PLKO",
                    source_update_dttm=datetime.utcnow(),
                ))
                inserted += 1
        await self.db.flush()
        return {"inserted": inserted, "updated": updated, "skipped": 0, "errors": []}

    async def _upsert_product_hierarchy(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Upsert ProductHierarchy records. Business key: id (PRODH)."""
        inserted = 0
        updated = 0
        for _, row in df.iterrows():
            ph_id = str(row.get("id", "")).strip()
            if not ph_id:
                continue
            existing = await self.db.get(ProductHierarchy, ph_id)
            if existing:
                existing.description = row.get("description", existing.description)
                existing.level = int(row.get("level", existing.level or 1))
                existing.parent_product_group_id = row.get("parent_product_group_id", existing.parent_product_group_id)
                updated += 1
            else:
                self.db.add(ProductHierarchy(
                    id=ph_id,
                    description=row.get("description", ""),
                    company_id=self.company_id,
                    level=int(row.get("level", 1)),
                    parent_product_group_id=row.get("parent_product_group_id"),
                    sort_order=int(row.get("sort_order", 0)),
                    is_active=row.get("is_active", "true"),
                ))
                inserted += 1
        await self.db.flush()
        return {"inserted": inserted, "updated": updated, "skipped": 0, "errors": []}

    async def _upsert_process_headers(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Upsert ProcessHeader + ProcessOperation + ProcessProduct (composite)."""
        inserted = 0
        updated = 0
        errors = []

        # Upsert headers
        for _, row in df.iterrows():
            hdr_id = str(row.get("id", "")).strip()
            if not hdr_id:
                continue
            existing = await self.db.get(ProcessHeader, hdr_id)
            if existing:
                existing.description = row.get("description", existing.description)
                existing.version = int(row.get("version", existing.version or 1))
                existing.source = row.get("source", existing.source)
                updated += 1
            else:
                self.db.add(ProcessHeader(
                    id=hdr_id,
                    company_id=self.company_id,
                    process_id=row.get("process_id"),
                    description=row.get("description", ""),
                    version=int(row.get("version", 1)),
                    status=row.get("status", "ACTIVE"),
                    source=row.get("source", "SAP_PLKO"),
                ))
                inserted += 1
        await self.db.flush()

        # Upsert operations from cached result
        ops_df = getattr(self, "_process_ops_result", {}).get("operations", pd.DataFrame())
        op_inserted = 0
        if not ops_df.empty:
            for _, row in ops_df.iterrows():
                hdr_id = str(row.get("header_id", "")).strip()
                op_num = int(row.get("operation_number", 0))
                if not hdr_id:
                    continue
                # Check existing by header + operation number
                result = await self.db.execute(
                    select(ProcessOperation).where(
                        ProcessOperation.header_id == hdr_id,
                        ProcessOperation.operation_number == op_num,
                    )
                )
                existing_op = result.scalar_one_or_none()
                if not existing_op:
                    self.db.add(ProcessOperation(
                        header_id=hdr_id,
                        operation_number=op_num,
                        operation_name=row.get("operation_name", f"Op {op_num}"),
                        work_center_id=row.get("work_center_id", ""),
                        setup_time=float(row.get("setup_time", 0)),
                        run_time_per_unit=float(row.get("run_time_per_unit", 0)),
                        yield_percentage=float(row.get("yield_percentage", 100)),
                        is_subcontracted=bool(row.get("is_subcontracted", False)),
                        source=row.get("source", "SAP_PLPO"),
                    ))
                    op_inserted += 1
            await self.db.flush()

        return {
            "inserted": inserted + op_inserted,
            "updated": updated,
            "skipped": 0,
            "errors": errors,
        }

    async def _upsert_production_capacity(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Upsert ProductionCapacity records. Business key: (site_id, work_center_id)."""
        inserted = 0
        updated = 0
        errors = []
        for _, row in df.iterrows():
            site_key = str(row.get("site_id", "")).strip()
            wc_id = str(row.get("work_center_id", "")).strip()
            if not site_key or not wc_id:
                continue
            site_id = self._site_key_to_id.get(site_key)
            if site_id is None:
                errors.append(f"ProductionCapacity: unknown site {site_key}")
                continue

            result = await self.db.execute(
                select(ProductionCapacity).where(
                    ProductionCapacity.site_id == site_id,
                    ProductionCapacity.capacity_type == row.get("capacity_type", "production"),
                )
            )
            existing = result.first()
            max_cap = float(row.get("max_capacity_per_period", 480))

            if existing:
                existing = existing[0]
                existing.max_capacity_per_period = max_cap
                existing.capacity_uom = row.get("capacity_uom", existing.capacity_uom)
                updated += 1
            else:
                self.db.add(ProductionCapacity(
                    site_id=site_id,
                    config_id=self.config_id,
                    tenant_id=self.tenant_id,
                    max_capacity_per_period=max_cap,
                    capacity_uom=row.get("capacity_uom", "MINUTES"),
                    capacity_type=row.get("capacity_type", "production"),
                    capacity_period=row.get("capacity_period", "day"),
                ))
                inserted += 1
        await self.db.flush()
        return {"inserted": inserted, "updated": updated, "skipped": 0, "errors": errors}

    async def _upsert_inbound_orders(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Upsert InboundOrder + InboundOrderLine + Schedule (composite)."""
        inserted = 0
        updated = 0
        errors = []

        for _, row in df.iterrows():
            order_id = str(row.get("id", "")).strip()
            if not order_id:
                continue
            existing = await self.db.get(InboundOrder, order_id)
            if existing:
                existing.status = row.get("status", existing.status)
                existing.total_ordered_qty = float(row.get("total_ordered_qty", 0)) if not pd.isna(row.get("total_ordered_qty")) else existing.total_ordered_qty
                existing.total_received_qty = float(row.get("total_received_qty", 0)) if not pd.isna(row.get("total_received_qty")) else existing.total_received_qty
                existing.source = row.get("source", existing.source)
                updated += 1
            else:
                order_date = row.get("order_date")
                if pd.isna(order_date):
                    order_date = date.today()
                elif not isinstance(order_date, date):
                    order_date = pd.Timestamp(order_date).date()
                self.db.add(InboundOrder(
                    id=order_id,
                    company_id=self.company_id,
                    order_type=row.get("order_type", "NB"),
                    supplier_id=row.get("supplier_id", ""),
                    order_date=order_date,
                    status=row.get("status", "OPEN"),
                    config_id=self.config_id,
                    currency=row.get("currency", "USD"),
                    source=row.get("source", "SAP_EKKO"),
                ))
                inserted += 1
        await self.db.flush()

        # Upsert lines from cached result
        lines_df = getattr(self, "_inbound_orders_result", {}).get("lines", pd.DataFrame())
        line_inserted = 0
        if not lines_df.empty:
            for _, row in lines_df.iterrows():
                oid = str(row.get("order_id", "")).strip()
                lnum = int(row.get("line_number", 0))
                if not oid:
                    continue
                result = await self.db.execute(
                    select(InboundOrderLine).where(
                        InboundOrderLine.order_id == oid,
                        InboundOrderLine.line_number == lnum,
                    )
                )
                if result.scalar_one_or_none() is None:
                    site_key = str(row.get("site_id", "")).strip()
                    site_id = self._site_key_to_id.get(site_key)
                    if site_id is None:
                        continue
                    self.db.add(InboundOrderLine(
                        order_id=oid,
                        line_number=lnum,
                        product_id=str(row.get("product_id", "")).strip(),
                        site_id=site_id,
                        ordered_quantity=float(row.get("ordered_quantity", 0)),
                        received_quantity=float(row.get("received_quantity", 0)),
                        open_quantity=float(row.get("open_quantity", 0)),
                        unit_price=float(row.get("unit_price", 0)),
                        uom=row.get("uom", "EA"),
                        status=row.get("status", "OPEN"),
                        source=row.get("source", "SAP_EKPO"),
                    ))
                    line_inserted += 1
            await self.db.flush()

        # Upsert schedules
        sched_df = getattr(self, "_inbound_orders_result", {}).get("schedules", pd.DataFrame())
        sched_inserted = 0
        if not sched_df.empty:
            # We need line IDs — query after line insert
            for _, row in sched_df.iterrows():
                oid = str(row.get("order_id", "")).strip()
                lnum = int(row.get("line_number", 0))
                sched_num = int(row.get("schedule_number", 1))
                result = await self.db.execute(
                    select(InboundOrderLine.id).where(
                        InboundOrderLine.order_id == oid,
                        InboundOrderLine.line_number == lnum,
                    )
                )
                line_row = result.first()
                if line_row is None:
                    continue
                line_id = line_row[0]
                # Check existing schedule
                result2 = await self.db.execute(
                    select(InboundOrderLineSchedule).where(
                        InboundOrderLineSchedule.order_line_id == line_id,
                        InboundOrderLineSchedule.schedule_number == sched_num,
                    )
                )
                if result2.scalar_one_or_none() is None:
                    sched_date = row.get("scheduled_date")
                    if pd.isna(sched_date):
                        continue
                    if not isinstance(sched_date, date):
                        sched_date = pd.Timestamp(sched_date).date()
                    self.db.add(InboundOrderLineSchedule(
                        order_line_id=line_id,
                        schedule_number=sched_num,
                        scheduled_quantity=float(row.get("scheduled_quantity", 0)),
                        received_quantity=float(row.get("received_quantity", 0)),
                        scheduled_date=sched_date,
                        status=row.get("status", "SCHEDULED"),
                        source=row.get("source", "SAP_EKET"),
                    ))
                    sched_inserted += 1
            await self.db.flush()

        return {
            "inserted": inserted + line_inserted + sched_inserted,
            "updated": updated,
            "skipped": 0,
            "errors": errors,
        }

    async def _upsert_outbound_order_lines(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Upsert OutboundOrderLine records. Business key: (order_id, line_number)."""
        inserted = 0
        updated = 0
        errors = []
        for _, row in df.iterrows():
            oid = str(row.get("order_id", "")).strip()
            lnum = int(row.get("line_number", 0))
            pid = str(row.get("product_id", "")).strip()
            site_key = str(row.get("site_id", "")).strip()
            if not oid or not pid:
                continue
            site_id = self._site_key_to_id.get(site_key)
            if site_id is None:
                errors.append(f"OutboundOrderLine: unknown site {site_key}")
                continue

            result = await self.db.execute(
                select(OutboundOrderLine).where(
                    OutboundOrderLine.order_id == oid,
                    OutboundOrderLine.line_number == lnum,
                    OutboundOrderLine.config_id == self.config_id,
                )
            )
            existing = result.scalar_one_or_none()
            ordered_qty = float(row.get("ordered_quantity", 0))
            req_date = row.get("requested_delivery_date")
            if pd.isna(req_date):
                req_date = date.today()
            elif not isinstance(req_date, date):
                req_date = pd.Timestamp(req_date).date()

            if existing:
                existing.ordered_quantity = ordered_qty
                existing.status = row.get("status", existing.status)
                existing.promised_quantity = float(row.get("promised_quantity", 0)) if not pd.isna(row.get("promised_quantity")) else existing.promised_quantity
                updated += 1
            else:
                self.db.add(OutboundOrderLine(
                    order_id=oid,
                    line_number=lnum,
                    product_id=pid,
                    site_id=site_id,
                    ordered_quantity=ordered_qty,
                    requested_delivery_date=req_date,
                    status=row.get("status", "DRAFT"),
                    priority_code=row.get("priority_code", "STANDARD"),
                    config_id=self.config_id,
                ))
                inserted += 1
        await self.db.flush()
        return {"inserted": inserted, "updated": updated, "skipped": 0, "errors": errors}

    async def _upsert_fulfillment_orders(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Upsert FulfillmentOrder records. Business key: fulfillment_order_id."""
        inserted = 0
        updated = 0
        errors = []
        for _, row in df.iterrows():
            fo_id = str(row.get("fulfillment_order_id", "")).strip()
            if not fo_id:
                continue
            pid = str(row.get("product_id", "")).strip()
            site_key = str(row.get("site_id", "")).strip()
            site_id = self._site_key_to_id.get(site_key)
            if site_id is None:
                errors.append(f"FulfillmentOrder: unknown site {site_key}")
                continue

            result = await self.db.execute(
                select(FulfillmentOrder).where(FulfillmentOrder.fulfillment_order_id == fo_id)
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.status = row.get("status", existing.status)
                existing.shipped_quantity = float(row.get("shipped_quantity", 0))
                existing.source = row.get("source", existing.source)
                updated += 1
            else:
                self.db.add(FulfillmentOrder(
                    company_id=self.company_id,
                    fulfillment_order_id=fo_id,
                    order_id=str(row.get("order_id", "")).strip(),
                    order_line_id=str(row.get("order_line_id", "")).strip() or None,
                    site_id=site_id,
                    product_id=pid,
                    quantity=float(row.get("quantity", 0)),
                    uom=row.get("uom", "EA"),
                    status=row.get("status", "CREATED"),
                    customer_id=str(row.get("customer_id", "")).strip() or None,
                    tracking_number=str(row.get("tracking_number", "")).strip() or None,
                    carrier=str(row.get("carrier", "")).strip() or None,
                    priority=int(row.get("priority", 3)),
                    source=row.get("source", "SAP_LIKP_LIPS"),
                ))
                inserted += 1
        await self.db.flush()
        return {"inserted": inserted, "updated": updated, "skipped": 0, "errors": errors}

    async def _upsert_backorders(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Upsert Backorder records. Business key: backorder_id."""
        inserted = 0
        updated = 0
        errors = []
        for _, row in df.iterrows():
            bo_id = str(row.get("backorder_id", "")).strip()
            if not bo_id:
                continue
            pid = str(row.get("product_id", "")).strip()
            site_key = str(row.get("site_id", "")).strip()
            site_id = self._site_key_to_id.get(site_key)
            if site_id is None:
                errors.append(f"Backorder: unknown site {site_key}")
                continue

            result = await self.db.execute(
                select(Backorder).where(Backorder.backorder_id == bo_id)
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.backorder_quantity = float(row.get("backorder_quantity", 0))
                existing.allocated_quantity = float(row.get("allocated_quantity", 0))
                existing.status = row.get("status", existing.status)
                existing.aging_days = int(row.get("aging_days", 0))
                updated += 1
            else:
                req_date = row.get("requested_delivery_date")
                if pd.notna(req_date) and not isinstance(req_date, date):
                    req_date = pd.Timestamp(req_date).date()
                elif pd.isna(req_date):
                    req_date = None
                self.db.add(Backorder(
                    company_id=self.company_id,
                    backorder_id=bo_id,
                    order_id=str(row.get("order_id", "")).strip(),
                    product_id=pid,
                    site_id=site_id,
                    customer_id=str(row.get("customer_id", "")).strip() or None,
                    backorder_quantity=float(row.get("backorder_quantity", 0)),
                    allocated_quantity=float(row.get("allocated_quantity", 0)),
                    status=row.get("status", "CREATED"),
                    requested_delivery_date=req_date,
                    priority=int(row.get("priority", 3)),
                    priority_code=row.get("priority_code", "STANDARD"),
                    aging_days=int(row.get("aging_days", 0)),
                    config_id=self.config_id,
                ))
                inserted += 1
        await self.db.flush()
        return {"inserted": inserted, "updated": updated, "skipped": 0, "errors": errors}

    async def _upsert_customer_costs(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Upsert CustomerCost records. Business key: (customer_id, product_id, cost_type, effective_date)."""
        inserted = 0
        updated = 0
        for _, row in df.iterrows():
            cust_id = str(row.get("customer_id", "")).strip()
            cost_type = str(row.get("cost_type", "")).strip()
            if not cost_type:
                continue
            eff_date = row.get("effective_date")
            if pd.isna(eff_date):
                eff_date = date.today()
            elif not isinstance(eff_date, date):
                eff_date = pd.Timestamp(eff_date).date()

            self.db.add(CustomerCost(
                company_id=self.company_id,
                customer_id=cust_id,
                product_id=str(row.get("product_id", "")).strip() or None,
                cost_type=cost_type,
                amount=float(row.get("amount", 0)),
                currency=row.get("currency", "USD"),
                effective_date=eff_date,
                source=row.get("source", "SAP_KONV"),
            ))
            inserted += 1
        await self.db.flush()
        return {"inserted": inserted, "updated": updated, "skipped": 0, "errors": []}

    async def _upsert_supplier_performance(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Upsert SupplierPerformance records. Business key: (tpartner_id, period_start)."""
        inserted = 0
        updated = 0
        for _, row in df.iterrows():
            tp_id = str(row.get("tpartner_id", "")).strip()
            if not tp_id:
                continue
            period_start = row.get("period_start")
            if pd.isna(period_start):
                continue

            result = await self.db.execute(
                select(SupplierPerformance).where(
                    SupplierPerformance.tpartner_id == tp_id,
                    SupplierPerformance.period_start == period_start,
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.orders_placed = int(row.get("orders_placed", 0))
                existing.orders_delivered_on_time = int(row.get("orders_delivered_on_time", 0))
                existing.orders_delivered_late = int(row.get("orders_delivered_late", 0))
                existing.on_time_delivery_rate = row.get("on_time_delivery_rate")
                existing.units_received = int(row.get("units_received", 0))
                updated += 1
            else:
                self.db.add(SupplierPerformance(
                    tpartner_id=tp_id,
                    period_start=period_start,
                    period_end=row.get("period_end", period_start),
                    period_type=row.get("period_type", "MONTHLY"),
                    orders_placed=int(row.get("orders_placed", 0)),
                    orders_delivered_on_time=int(row.get("orders_delivered_on_time", 0)),
                    orders_delivered_late=int(row.get("orders_delivered_late", 0)),
                    average_days_late=row.get("average_days_late"),
                    units_received=int(row.get("units_received", 0)),
                    units_accepted=int(row.get("units_accepted", 0)),
                    units_rejected=int(row.get("units_rejected", 0)),
                    on_time_delivery_rate=row.get("on_time_delivery_rate"),
                    total_spend=float(row.get("total_spend", 0)),
                    currency=row.get("currency", "USD"),
                ))
                inserted += 1
        await self.db.flush()
        return {"inserted": inserted, "updated": updated, "skipped": 0, "errors": []}

    # ------------------------------------------------------------------
    # Reconciliation
    # ------------------------------------------------------------------

    async def reconcile(
        self,
        sap_data: Dict[str, pd.DataFrame],
    ) -> Dict[str, Any]:
        """
        Compare SAP source counts with staged Postgres counts.

        Returns per-entity comparison with match/mismatch status.
        """
        results = {}

        # Product count: MARA rows vs Product table
        mara = sap_data.get("MARA", pd.DataFrame())
        if not mara.empty:
            sap_count = len(mara)
            db_result = await self.db.execute(
                sql_text("SELECT COUNT(*) FROM product WHERE config_id = :cid"),
                {"cid": self.config_id},
            )
            db_count = db_result.scalar() or 0
            results["product"] = {
                "sap_count": sap_count,
                "db_count": db_count,
                "match": sap_count == db_count,
                "delta": db_count - sap_count,
            }

        # Site count: T001W rows vs Site table
        t001w = sap_data.get("T001W", pd.DataFrame())
        if not t001w.empty:
            sap_count = len(t001w)
            db_result = await self.db.execute(
                sql_text("SELECT COUNT(*) FROM site WHERE config_id = :cid"),
                {"cid": self.config_id},
            )
            db_count = db_result.scalar() or 0
            results["site"] = {
                "sap_count": sap_count,
                "db_count": db_count,
                "match": sap_count == db_count,
                "delta": db_count - sap_count,
            }

        # Inventory: MARD rows vs InvLevel today
        mard = sap_data.get("MARD", pd.DataFrame())
        if not mard.empty:
            sap_count = len(mard)
            db_result = await self.db.execute(
                sql_text(
                    "SELECT COUNT(*) FROM inv_level "
                    "WHERE config_id = :cid AND inventory_date = CURRENT_DATE"
                ),
                {"cid": self.config_id},
            )
            db_count = db_result.scalar() or 0
            results["inv_level"] = {
                "sap_count": sap_count,
                "db_count": db_count,
                "match": sap_count == db_count,
                "delta": db_count - sap_count,
            }

        # Forecast: PBED rows vs Forecast table
        pbed = sap_data.get("PBED", pd.DataFrame())
        if not pbed.empty:
            sap_count = len(pbed[pbed.get("PLNMG", 0).astype(float) > 0]) if "PLNMG" in pbed.columns else len(pbed)
            db_result = await self.db.execute(
                sql_text("SELECT COUNT(*) FROM forecast WHERE config_id = :cid AND source = 'SAP_PIR'"),
                {"cid": self.config_id},
            )
            db_count = db_result.scalar() or 0
            results["forecast"] = {
                "sap_count": sap_count,
                "db_count": db_count,
                "match": sap_count == db_count,
                "delta": db_count - sap_count,
            }

        # Trading partners: LFA1 + KNA1 vs trading_partners table
        lfa1 = sap_data.get("LFA1", pd.DataFrame())
        kna1 = sap_data.get("KNA1", pd.DataFrame())
        sap_tp_count = len(lfa1) + len(kna1)
        if sap_tp_count > 0:
            db_result = await self.db.execute(
                sql_text("SELECT COUNT(*) FROM trading_partners WHERE source IN ('SAP_LFA1', 'SAP_KNA1')"),
            )
            db_count = db_result.scalar() or 0
            results["trading_partner"] = {
                "sap_count": sap_tp_count,
                "db_count": db_count,
                "match": sap_tp_count == db_count,
                "delta": db_count - sap_tp_count,
            }

        return results
